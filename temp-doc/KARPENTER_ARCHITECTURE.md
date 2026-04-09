# Karpenter ↔ Spot Optimizer Architecture

> Generated: 9 April 2026  
> Root Cause: Karpenter native consolidation (`WhenEmptyOrUnderutilized`) replacing nodes with t4g.micro even when right-sizing is OFF.

---

## 1. System Overview

```mermaid
flowchart TB
    subgraph Frontend["Frontend (React)"]
        UI_Toggle["ClusterDetails.jsx<br/>Toggle: auto_rebalancing_enabled<br/>Toggle: auto_rightsizing_enabled<br/>Toggle: diversify_pools"]
    end

    subgraph Backend["Backend (FastAPI + Celery)"]
        API_Karp["karpenter_routes.py<br/>PATCH /karpenter/config/{cluster_id}"]
        API_ASCPAI["ascpai_routes.py<br/>Node Recommendations"]
        Celery["auto_rebalancer.py<br/>(Celery Beat every 15s)"]
        KarpSvc["karpenter_service.py<br/>add_allowed_instance_type()<br/>_update_nodepool()<br/>create_spot_trigger_pod()"]
        PoolRank["pool_ranking_service.py<br/>ML Risk + Savings Ranking"]
        SimEngine["simulation_engine.py<br/>Bin-Packing + Consolidation Sim"]
    end

    subgraph EKS["EKS Cluster (K8s)"]
        subgraph Karpenter["Karpenter v1.0.8"]
            NP_Default["NodePool: default<br/>capacity: spot + on-demand<br/>disruption: WhenEmptyOrUnderutilized<br/>consolidateAfter: 30s"]
            NP_Stateless["NodePool: stateless-spot<br/>capacity: spot<br/>disruption: WhenEmptyOrUnderutilized<br/>consolidateAfter: 30s"]
            NP_Stateful["NodePool: stateful-od<br/>capacity: on-demand<br/>disruption: WhenEmpty<br/>consolidateAfter: 60s"]
            KarpCtrl["Karpenter Controller<br/>Provisioning + Consolidation"]
        end
        Agent["Spot Optimizer Agent<br/>(DaemonSet + Orchestrator)"]
        Nodes["EC2 Nodes<br/>(OD + Spot instances)"]
    end

    subgraph AWS["AWS"]
        EC2["EC2 Fleet API"]
        ASG["Auto Scaling Groups"]
    end

    UI_Toggle --> API_Karp
    API_Karp --> KarpSvc
    Celery --> KarpSvc
    Celery --> PoolRank
    KarpSvc -->|"K8s API Patch"| NP_Default
    KarpCtrl -->|"Reads NodePool spec"| NP_Default
    KarpCtrl -->|"Provisions/Terminates"| EC2
    KarpCtrl --> Nodes
    Agent -->|"Heartbeat + Metrics"| Backend
    Agent -->|"Cordon/Drain/Annotate"| Nodes
    Celery -->|"terminate_instance_in_asg()"| ASG
    Celery -->|"terminate_instances()"| EC2
```

---

## 2. Auto-Rebalancer State Machine (Phase 1 → Phase 2)

```mermaid
stateDiagram-v2
    [*] --> CycleStart: Celery Beat (every 15s)
    
    CycleStart --> CooldownCheck: Load cluster settings
    CooldownCheck --> Skip: Cooldown active & no bypass
    CooldownCheck --> OneAtATimeGuard: Cooldown expired OR bypass

    OneAtATimeGuard --> Skip: AgentActions in-flight (S2S mode)
    OneAtATimeGuard --> LastNodeGuard: No in-flight actions
    
    LastNodeGuard --> Skip: Only 1 running node
    LastNodeGuard --> CheckODNodes: ≥2 running nodes
    
    CheckODNodes --> OD_to_Spot: OD instances found
    CheckODNodes --> S2S_Checks: All spot, no OD

    state OD_to_Spot {
        [*] --> BatchSizing: batch_percent% of OD nodes
        BatchSizing --> SemaphoreCheck: Redis INCR/DECR gate
        SemaphoreCheck --> MLRanking: Slot available
        SemaphoreCheck --> WaitNextCycle: At limit
        MLRanking --> CreateAction: Best pool selected
        CreateAction --> Phase1
    }

    state Phase1 {
        [*] --> PatchNodePool: Inject ML types into NodePool
        PatchNodePool --> CreateTriggerPod: Force Karpenter provision
        CreateTriggerPod --> WaitForSpot: Monitor new node join
        WaitForSpot --> Phase2: Spot node Ready
        WaitForSpot --> Timeout: 30 min elapsed
    }

    state Phase2 {
        [*] --> InlineCordon: kubectl cordon old-node
        InlineCordon --> InlineDrain: kubectl drain old-node
        InlineDrain --> TerminateEC2: AWS terminate_instance
        TerminateEC2 --> VerifyTermination: describe_instances
        VerifyTermination --> CleanupNodePool: Remove injected types
        CleanupNodePool --> MarkComplete: Set 24h cooldown
    }

    state S2S_Checks {
        [*] --> DiversifyCheck: Check 1 - Pool distribution
        DiversifyCheck --> FamilyCapCheck: Check 1.5 - Family cap %
        FamilyCapCheck --> RiskCheck: Check 2 - Risk threshold
        RiskCheck --> CreateS2SAction: Trigger found
        RiskCheck --> Skip: No trigger
    }
    
    Phase2 --> [*]: Optimization Complete
    Skip --> [*]: Next 15s cycle
```

---

## 3. Karpenter NodePool Patching Flow

```mermaid
sequenceDiagram
    participant Celery as auto_rebalancer.py
    participant KSvc as karpenter_service.py
    participant K8s as K8s API Server
    participant Karp as Karpenter Controller
    participant EC2 as AWS EC2

    Note over Celery: Phase 1 - Inject ML types
    Celery->>KSvc: add_allowed_instance_type("t3a.medium", "default")
    KSvc->>K8s: GET NodePool "default"
    K8s-->>KSvc: Current spec (requirements)
    KSvc->>KSvc: Append "t3a.medium" to instance-type values
    KSvc->>KSvc: Derive arch (amd64/arm64) from family
    KSvc->>K8s: PATCH NodePool spec.template.spec.requirements
    Note over KSvc: ⚠️ NEVER touches spec.disruption
    
    Note over Celery: Create trigger pod
    Celery->>KSvc: create_spot_trigger_pod("spot-trigger-19")
    KSvc->>K8s: CREATE Pod with nodeSelector: capacity-type=spot
    
    Note over Karp: Karpenter sees pending pod
    Karp->>K8s: Read NodePool requirements
    Karp->>EC2: RunInstances (cheapest fitting type)
    EC2-->>Karp: i-0cd7cc2dc48b429fa (t3a.medium)
    Karp->>K8s: Register new Node
    
    Note over Celery: Phase 2 - Drain + Terminate old
    Celery->>K8s: kubectl cordon old-node
    Celery->>K8s: kubectl drain old-node
    Celery->>EC2: terminate_instance_in_auto_scaling_group()
    
    Note over Celery: Cleanup - Remove injected types
    Celery->>KSvc: remove_allowed_instance_type("t3a.medium", "default")
    KSvc->>K8s: PATCH NodePool (remove from values)
```

---

## 4. The t4g.micro Consolidation Bug

```mermaid
flowchart TD
    subgraph Problem["🔴 PROBLEM: Karpenter Native Consolidation"]
        A["Node running: t3a.medium<br/>Actual usage: CPU 50m, Mem 128Mi"] 
        B["Karpenter evaluates every 30s<br/>consolidationPolicy: WhenEmptyOrUnderutilized"]
        C["Karpenter picks CHEAPEST type<br/>that fits pod requests from NodePool list"]
        D["t4g.micro launched!<br/>Right-sizing was OFF<br/>but Karpenter doesn't know that"]
    end

    A --> B --> C --> D

    subgraph Intent["🟢 INTENDED DESIGN (karpenter_routes.py L410)"]
        E["User enables auto_rebalancing"] 
        F["Backend should patch NodePool:<br/>consolidationPolicy → WhenEmpty"]
        G["Karpenter only consolidates<br/>empty nodes, not underutilized"]
    end
    E --> F --> G

    subgraph Bug["🔴 BUG: Consolidation Policy Never Applied"]
        H["karpenter_routes.py L415:<br/>_ksvc.patch_node_pool_allowed_types(<br/>  cluster_id=...,<br/>  consolidation_policy='WhenEmpty'<br/>)"]
        I["patch_node_pool_allowed_types() signature:<br/>def patch_node_pool_allowed_types(<br/>  self, cluster_id, instance_types, db<br/>)"]
        J["❌ TypeError: unexpected keyword<br/>'consolidation_policy'<br/>Caught by except → logged as warning"]
        K["NodePool keeps:<br/>WhenEmptyOrUnderutilized + 30s<br/>Karpenter freely consolidates"]
    end
    H --> I --> J --> K

    subgraph Bug2["🔴 BUG: _update_nodepool() hardcodes policy"]
        L["karpenter_service.py L766:<br/>disruption: {<br/>  consolidationPolicy:<br/>  'WhenEmptyOrUnderutilized',<br/>  expireAfter: '720h'<br/>}"]
        M["Every NodePool update<br/>resets to WhenEmptyOrUnderutilized"]
    end
    L --> M
```

---

## 5. Consolidation Policy — Current vs Required

```mermaid
flowchart LR
    subgraph Current["CURRENT STATE (Broken)"]
        direction TB
        C1["Agent installs Karpenter"]
        C2["Creates NodePool: default<br/>consolidation: WhenEmptyOrUnderutilized<br/>consolidateAfter: 30s"]
        C3["User enables auto_rebalancing"]
        C4["karpenter_routes.py tries to<br/>set WhenEmpty → FAILS silently"]
        C5["_update_nodepool() always<br/>hardcodes WhenEmptyOrUnderutilized"]
        C6["🔴 Karpenter consolidates freely<br/>Replaces nodes with t4g.micro"]
        C1 --> C2 --> C3 --> C4 --> C5 --> C6
    end

    subgraph Required["REQUIRED STATE (Fix)"]
        direction TB
        R1["Agent installs Karpenter"]
        R2["Creates NodePool: default<br/>consolidation: WhenEmptyOrUnderutilized<br/>consolidateAfter: 30s"]
        R3["User enables auto_rebalancing"]
        R4["Backend patches NodePool:<br/>consolidation → WhenEmpty<br/>OR consolidateAfter → Never"]
        R5["During active rebalance:<br/>consolidateAfter → Never<br/>(prevent any Karpenter interference)"]
        R6["🟢 Only ML rebalancer<br/>controls node replacements"]
        R1 --> R2 --> R3 --> R4 --> R5 --> R6
    end
```

---

## 6. Instance Type Flow — Right-Sizing ON vs OFF

```mermaid
flowchart TD
    Start["Rebalancer picks source node<br/>e.g. t3.medium (CPU: 5%, Mem: 20%)"]
    
    RSCheck{auto_rightsizing_enabled?}
    Start --> RSCheck
    
    RSCheck -->|"ON"| BinPack["Bin-Pack: Find smallest type<br/>that fits actual_usage + 30% buffer<br/>→ could be t4g.micro"]
    RSCheck -->|"OFF"| SameSize["Keep same size class<br/>target = t3.medium"]
    
    BinPack --> MLRank1["ML ranks spots of bin-packed size<br/>e.g. t4g.micro:ap-south-1a, t4g.small:ap-south-1b"]
    SameSize --> MLRank2["ML ranks spots of same size<br/>e.g. t3a.medium:ap-south-1c, c7g.medium:ap-south-1b"]
    
    MLRank1 --> InjectTypes["Inject up to 8 types into NodePool<br/>+ create trigger pod"]
    MLRank2 --> InjectTypes
    
    InjectTypes --> KarpPick["Karpenter provisions cheapest<br/>from injected list"]
    
    KarpPick --> Phase2["Phase 2: Cordon → Drain → Terminate old"]
    Phase2 --> Cleanup["Remove injected types from NodePool"]
    
    Cleanup --> KarpNative{{"⚠️ Karpenter's OWN consolidation<br/>(independent of rebalancer)<br/>Runs every 30s"}}
    
    KarpNative -->|"WhenEmptyOrUnderutilized"| KarpDecide["Karpenter sees node underutilized<br/>Picks cheapest type from NodePool list<br/>→ Could be t4g.micro if types leaked"]
    KarpNative -->|"WhenEmpty (intended fix)"| Safe["Only replaces truly empty nodes<br/>No surprise downsizing"]
```

---

## 7. Three NodePools Created by Agent

```mermaid
flowchart LR
    subgraph NodePools["Karpenter NodePools (created by agent/actuator.py)"]
        direction TB
        
        subgraph Default["NodePool: default (weight=1, catch-all)"]
            D1["Capacity: spot + on-demand"]
            D2["Instance Types: m5.large, m5.xlarge,<br/>m6i.large, m6i.xlarge, m6g.large,<br/>m6g.xlarge, c5.large, c5.xlarge,<br/>c6g.large, c6g.xlarge<br/>+ any ML-injected types"]
            D3["Disruption: WhenEmptyOrUnderutilized, 30s"]
            D4["🔴 THIS is where rebalancer injects types"]
        end
        
        subgraph Stateless["NodePool: stateless-spot (weight=10, preferred)"]
            S1["Capacity: spot only"]
            S2["Instance Types: same defaults"]
            S3["Disruption: WhenEmptyOrUnderutilized, 30s"]
            S4["Labels: workload=stateless"]
        end
        
        subgraph Stateful["NodePool: stateful-od (weight=5)"]
            SF1["Capacity: on-demand only"]
            SF2["Instance Types: same defaults"]
            SF3["Disruption: WhenEmpty, 60s"]
            SF4["Labels: workload=stateful"]
        end
    end
```

---

## 8. S2S Diversify Flow (Fixed: _s2s_risk_only_mode bug)

```mermaid
flowchart TD
    Start["S2S Evaluation<br/>(all nodes are spot)"]
    
    LoadSettings["Load cluster settings:<br/>diversify_pools, max_family_cap_pct,<br/>risk_ceiling_percent"]
    
    RiskMode{"_s2s_risk_only_mode?<br/>(= NOT diversify_pools)"}
    
    Start --> LoadSettings --> RiskMode
    
    RiskMode -->|"True (diversify OFF)"| Check2Only["Only Check 2: Risk threshold<br/>Current risk > ceiling → trigger S2S"]
    
    RiskMode -->|"False (diversify ON)"| Check0["Check 0: Opportunistic<br/>Better risk AND savings?"]
    Check0 -->|"No"| Check1["Check 1: Pool-level diversify<br/>Same (type, az) has >1 node?"]
    Check0 -->|"Yes"| Trigger
    Check1 -->|"No"| Check15["Check 1.5: Family cap<br/>Family X > 40% of nodes?"]
    Check1 -->|"Yes"| Trigger
    Check15 -->|"No"| Check2["Check 2: Risk threshold<br/>Current risk > ceiling?"]
    Check15 -->|"Yes"| Trigger
    Check2 -->|"Yes"| Trigger
    Check2 -->|"No"| Skip["No S2S trigger this cycle"]
    Check2Only -->|"Yes"| Trigger
    Check2Only -->|"No"| Skip
    
    Trigger["Create S2S RebalancingAction<br/>→ Phase 1 → Phase 2"]
    
    style Check0 fill:#e0f7fa
    style Check1 fill:#e8f5e9
    style Check15 fill:#e8f5e9
    style Trigger fill:#c8e6c9
    style Skip fill:#ffcdd2
```

---

## 9. Concurrency Controls

```mermaid
flowchart TD
    subgraph Layer1["Layer 1: ONE-AT-A-TIME GUARDRAIL (line 6627)"]
        G1["Query AgentActions for cluster<br/>Status = PENDING or PICKED_UP"]
        G2{"Any active<br/>AgentActions?"}
        G3{"Is initial<br/>OD→Spot batch?"}
        G1 --> G2
        G2 -->|"Yes"| G3
        G2 -->|"No"| Pass1["✅ Proceed"]
        G3 -->|"Yes"| Pass1
        G3 -->|"No (S2S mode)"| Block1["⛔ Skip cluster this cycle"]
    end
    
    subgraph Layer2["Layer 2: REDIS SEMAPHORE (line 8092)"]
        S1["Redis INCR rebalance:active_count:{cluster_id}"]
        S2{"current > max_concurrent?"}
        S3["max_concurrent =<br/>batch_size (initial OD→Spot)<br/>OR settings value (default 1)"]
        S1 --> S2
        S2 -->|"Yes"| Block2["⛔ DECR & break loop"]
        S2 -->|"No"| Pass2["✅ Create action"]
    end
    
    subgraph Layer3["Layer 3: PER-NODE LOCK (line 8080)"]
        N1["Redis key: spot:node_active_action:{instance_id}"]
        N2{"Key exists?"}
        N1 --> N2
        N2 -->|"Yes"| Block3["⛔ Skip this node"]
        N2 -->|"No"| Pass3["✅ Target this node"]
    end
    
    Pass1 --> Layer2
    Pass2 --> Layer3
```

---

## 10. Bugs Found & Fixes Required

| # | Bug | File | Line | Severity | Status |
|---|-----|------|------|----------|--------|
| 1 | `_s2s_risk_only_mode = True` hardcoded — diversify S2S checks are dead code | `auto_rebalancer.py` | 7266 | **CRITICAL** | ✅ **FIXED** → `not _diversify_s2s` |
| 2 | `patch_node_pool_allowed_types()` called with wrong kwargs — consolidation policy never applied | `karpenter_routes.py` | 415 | **CRITICAL** | 🔴 OPEN |
| 3 | `_update_nodepool()` always hardcodes `WhenEmptyOrUnderutilized` — overrides any consolidation fix | `karpenter_service.py` | 766 | **HIGH** | 🔴 OPEN |
| 4 | No `consolidateAfter: Never` during active rebalance — Karpenter can interfere mid-migration | `karpenter_service.py` | — | **HIGH** | 🔴 OPEN |
| 5 | `add_allowed_instance_type()` only adds, cleanup may miss types → NodePool type list grows unbounded | `karpenter_service.py` | 1041 | **MEDIUM** | 🔴 OPEN |
| 6 | t4g.micro not in default types but Karpenter can pick any type if NodePool list leaks small types | `actuator.py` | 1005 | **MEDIUM** | 🔴 OPEN |

---

## 11. How t4g.micro Happened (Root Cause Chain)

```mermaid
flowchart TD
    A["1. Rebalancer completed OD→Spot migration<br/>Injected types: t3a.medium, c7g.medium, etc."]
    B["2. Cleanup step: remove_allowed_instance_type()<br/>Should remove all injected types"]
    C{"3. Did cleanup succeed<br/>for ALL types?"}
    D["4. Some types remain in NodePool<br/>(or Karpenter has its own type expansion)"]
    E["5. Karpenter consolidation runs (every 30s)<br/>Policy: WhenEmptyOrUnderutilized"]
    F["6. Karpenter evaluates node utilization<br/>Pod requests: CPU 50m, Mem 128Mi"]
    G["7. Karpenter picks CHEAPEST instance type<br/>that satisfies pod resource requests"]
    H["8. t4g.micro selected<br/>(2 vCPU, 1 GiB — fits 50m CPU + 128Mi)"]
    I["9. Old node drained by KARPENTER<br/>(not by rebalancer)"]
    J["10. t4g.micro launched<br/>Right-sizing was OFF but irrelevant —<br/>this was Karpenter's native decision"]
    
    A --> B --> C
    C -->|"Yes (all removed)"| E2["NodePool has only default large types<br/>Karpenter still consolidates down!<br/>Karpenter uses instance-family flexibility"]
    C -->|"No (some leaked)"| D --> E
    E2 --> E
    E --> F --> G --> H --> I --> J
    
    style J fill:#ffcdd2,stroke:#c62828
    style H fill:#fff9c4,stroke:#f9a825
```

> **Key Insight**: Even if our type cleanup is perfect, Karpenter v1.0+ with `WhenEmptyOrUnderutilized` can **independently decide** to consolidate underutilized nodes. The fix is to set `consolidationPolicy: WhenEmpty` (or `consolidateAfter: Never`) when our rebalancer is active.
