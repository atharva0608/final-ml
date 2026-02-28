# Application Progress and System Architecture

**Last Updated:** February 2026  
**Focus:** Core Infrastructure, Security, Execution Layers, and End-to-End User Workflows (Excluding ML-based subsystems).

---

## 1. Executive Progress Summary

The application has successfully progressed from a prototype state into a robust, data-driven infrastructure management platform. The primary focus of recent development has been the complete elimination of mock data, establishing strict enterprise security boundaries, and migrating towards scalable, asynchronous execution models.

**Key Milestones Achieved:**
* **100% Real Data Integration:** Eliminated all hardcoded fallbacks across pricing, infrastructure states, and historical savings calculations.
* **Execution Safety Mechanisms:** Transitioned from direct AWS EC2 manipulation to native Kubernetes `NodePool` patching via Karpenter, ensuring the cluster orchestrator remains the source of truth.
* **Database & Concurrency Scaling:** Integrated distributed Redis locking to prevent parallel execution race conditions, and formulated migration pathways for TimescaleDB to handle massive metric ingestion.
* **Identity & Security Guardrails:** Transitioning to Just-In-Time (JIT) temporary AWS STS credentials and OIDC federation for the Kubernetes agent, eliminating static API key vulnerabilities.

---

## 2. End-to-End User Flow (Client Login to Execution)

This flow illustrates the user journey from initial authentication through executing structural infrastructure changes.

```mermaid
flowchart TD
    A([User Signs In]) --> B[Authentication & RBAC Mapping]
    B --> C[Dashboard Overview]
    
    C -->|View Metrics| D[Read-Only Data Access]
    D --> E[Redis Cache / PostgreSQL]
    
    C -->|Attempt Infrastructure Change| F{Requires Mutating Access?}
    
    F -->|No| D
    F -->|Yes| G[JIT Access Request Workflow]
    
    G --> H{Approval Granted?}
    H -->|No| I([Access Denied])
    H -->|Yes| J[Backend Brokers Temporary STS Credentials]
    
    J --> K[Action Initiated via UI]
    K --> L[API Gateway validates JIT Session & HMAC Signature]
    
    L --> M{Target Module}
    M -->|Right-Sizing| RS[Execute Karpenter Patching]
    M -->|Hibernation| HIB[Execute Scale/Drain Jobs]
    M -->|Hygiene| HYG[Execute Zombie Deletions]
    
    RS --> N((Async Celery Workers))
    HIB --> N
    HYG --> N
    
    N --> O[Execute AWS/K8s API Calls]
    O --> P[Log to Audit Database]
    P --> Q([Action Complete / UI Refreshed])
```

1. **Authentication:** The user logs in and is mapped to their Organizational RBAC roles.
2. **Dashboard & Insights:** The user views the current fleet status, cost intelligence, and infrastructure layouts. All reads are heavily cached via Redis hierarchical versioning.
3. **Privilege Elevation (JIT):** To optimize a cluster, hibernate an environment, or delete zombie resources, the user requests Just-In-Time access. The backend brokers real, time-limited AWS STS credentials for the operation.
4. **Execution Initiation:** The user applies a recommendation. The request is cryptographically signed (HMAC) and checked for Idempotency to prevent double-clicks.
5. **Asynchronous Execution:** The workload is handed off to Celery workers, utilizing state-machine waiters to safely poll Kubernetes and AWS without blocking critical threads.

---

## 3. High-Level System Architecture

The overarching system leverages a three-tier design, relying entirely on background workers to interact with external cloud boundaries safely.

```mermaid
graph TD
    subgraph Client Tier
        UI[React Frontend / Dashboard]
    end

    subgraph API & Gateway Tier
        AGW[FastAPI API Gateway]
        AUTH[JIT & RBAC Middleware]
        AGW --> AUTH
    end

    subgraph Core Policy Services
        RSO[Right-Sizing Optimizer]
        HS[Hibernation Scheduler]
        RHS[Resource Hygiene Scanner]
        TG[Tag Governance Engine]
    end

    subgraph Execution & Data Tier
        CEL[Celery Async Workers]
        RED[(Redis - Cache & Locks)]
        DB[(PostgreSQL - State & Audit)]
    end

    subgraph Cloud Boundary
        AWS[AWS EC2 / AutoScaling API]
        EKS[Kubernetes Cluster API / Karpenter]
    end

    UI -->|HTTPS Request| AGW
    AUTH --> RSO
    AUTH --> HS
    AUTH --> RHS
    AUTH --> TG
    
    RSO & HS & RHS & TG <--> DB
    RSO & HS & RHS & TG <--> RED

    RSO -->|Dispatch Task| CEL
    HS -->|Dispatch Task| CEL
    RHS -->|Dispatch Task| CEL
    
    CEL --> AWS
    CEL --> EKS
```

---

## 4. Module Logic & Decision Trees

### A. Right-Sizing & Karpenter Integration
**Progress:** Integrated Karpenter Insights (Dry-Run visibility) and Auto-Optimize capabilities. Pricing is now dynamically aggregated regionally via background workers holding a strict "Freshness Contract" to ensure no staleness.

**Decision Logic (Applying a Recommendation):**
```mermaid
stateDiagram-v2
    [*] --> ValidateJIT
    ValidateJIT --> PDB_PreCheck : JIT Active
    
    PDB_PreCheck --> Abort : Disruptions Allowed == 0
    PDB_PreCheck --> AWS_DryRun : Policy Permits
    
    AWS_DryRun --> Abort : Capacity / Permissions Failed
    AWS_DryRun --> DistributedLock : Success
    
    DistributedLock --> PatchNodePool : Lock Acquired
    DistributedLock --> Abort : Parallel Job Detected
    
    PatchNodePool --> AsyncWaiter_NodeReady
    AsyncWaiter_NodeReady --> AsyncWaiter_PodDrain

    AsyncWaiter_PodDrain --> FinalizeAudit
    FinalizeAudit --> [*]
```

### B. Hibernation System
**Progress:** Complete database schema support (`is_hibernating`, `hibernation_state`) backed by distributed locks. Removed legacy schedulers and fully integrated real-time cluster scale-down instructions.

**Decision Logic (Cron Execution):**
```mermaid
flowchart TD
    A([Cron Trigger]) --> B{Lock Acquired?}
    B -->|No| C([Log Skip])
    B -->|Yes| D{Check Current State}
    
    D -->|Already Asleep| C
    D -->|Awake| E[Assume IAM Role via JIT/System Auth]
    
    E --> F[Snapshot Current Deployments/Daemonsets]
    F --> G[Cordon Nodes]
    G --> H[Evict / Drain Worker Pods]
    H --> I[Scale Deployments to 0]
    I --> J[Remove NodePools / Terminate AWS Instances]
    J --> K[Update DB: is_hibernating = true]
    K --> L([Completion Notification])
```

### C. Resource Hygiene (Zombie Cleanup)
**Progress:** Engine successfully orchestrates 9 distinct AWS resource types (Unattached EBS, Idle Elastic IPs, Obsolete AMIs, etc.). Complete UI parity with multi-region scanning enabled.

**Decision Logic (Scanning & Remediation):**
```mermaid
flowchart TD
    A([Start Scan Route]) --> B[Fetch Connected AWS Regions]
    B --> C[Fan out to Region Scanners]
    
    C --> D{Evaluate Filter Criteria}
    D -->|Attached/In Use| E[Skip]
    D -->|Abandoned/Detached| F[Evaluate Age Thresholds]
    
    F -->|< 30 Days Old| E
    F -->|> 30 Days Old| G[Mark as Zombie Candidate]
    
    G --> H[Calculate $ Waste]
    H --> I[Present to User UI]
    
    I --> J{User Issues Delete?}
    J -->|Yes, with HMAC & JIT| K[Assume Role & Delete API]
    K --> L[Update Cleanup Audit]
```

### D. Identity, Security, & Just-In-Time (JIT) Access
**Progress:** Actively transitioning from an approval-centric UI gate into a strict cryptographic boundary utilizing AWS STS `assume_role` capabilities and OIDC Federation.

**Decision Logic (JIT Lifecycle):**
```mermaid
stateDiagram-v2
    [*] --> RequestSubmitted
    RequestSubmitted --> PendingApproval
    
    PendingApproval --> Denied : Manager Rejects
    Denied --> [*]
    
    PendingApproval --> Approved : Manager Approves
    Approved --> ProvisionSTS : Background Worker
    
    ProvisionSTS --> ActiveSession : UI Unlocked & Gateway Opened
    
    ActiveSession --> BackgroundRefresh : STS Expiration < 10 mins
    BackgroundRefresh --> ActiveSession : New Token Issued
    
    ActiveSession --> SessionExpired : Clock exceeds originally requested Hours
    SessionExpired --> RevokeUI
    RevokeUI --> [*]
```

---

## Conclusion
The architecture has matured to prioritize asynchronous resilience, mathematical accuracy in provisioning, and definitive security domains. Operations are decoupled from immediate HTTP requests, leveraging execution state machines and durable data stores to guarantee consistency, cluster safety, and zero-downtime structural modifications.
