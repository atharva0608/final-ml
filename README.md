# Unified Agentless Cloud Optimization Platform
**Version 3.1 (Production Ready)**

## 1. Executive Summary
This platform is an autonomous infrastructure operator that optimizes cloud compute costs, eliminates waste, and enforces security governance without agents. It connects to customer AWS accounts via cross-account IAM roles and manages resources directly using the AWS and Kubernetes APIs.

## 2. System Architecture

### A. The Three Pillars
1.  **Compute Optimizer:** Replaces On-Demand instances with Spot Instances using ML-driven risk prediction.
    * *Savings:* 60-90% on compute bills.
2.  **Waste Manager:** Scans for and removes unused Elastic IPs, detached EBS volumes, and stale snapshots.
    * *Benefit:* Continuous financial hygiene.
3.  **Security Enforcer:** Audits running instances for authorization tags (`ManagedBy`). Terminates unauthorized "Shadow IT" instances after 24 hours.
    * *Benefit:* Immutable infrastructure enforcement.

### B. Execution Modes
* **🧪 Lab Mode (Linear Pipeline):**
    * **Scope:** Single EC2 instance.
    * **Use Case:** Testing, model validation, atomic switch verification.
    * **Logic:** Scrape Price -> ML Predict -> Snapshot -> Launch Spot -> Swap.
* **🏭 Production Mode (Cluster Pipeline):**
    * **Scope:** Auto Scaling Groups (ASGs) & Kubernetes Clusters.
    * **Use Case:** Fleet-wide optimization.
    * **Logic:** Discovery -> Global Risk Check -> Scale Out -> Attach to ASG -> Detach Old -> Terminate.
    * **K8s Logic:** Scale Out -> Cordon Old Node -> Drain Pods -> Terminate.

### C. Global Intelligence (Risk Manager)
If **any** production client experiences a Spot interruption, that specific pool (Region+AZ+Type) is "Poisoned" globally for 15 days. No other client will attempt to use that pool until it stabilizes.

---

## 3. Technical Stack
* **Backend:** Python (FastAPI), SQLAlchemy, Boto3, Kubernetes Client.
* **Frontend:** React (Vite), Tailwind CSS.
* **Database:** PostgreSQL (State), Redis (Cache/ML Features).
* **Security:** AWS STS AssumeRole (Agentless), JWT Authentication.

---

## 4. Setup & Deployment

### Prerequisites
* Python 3.9+
* Node.js 16+
* PostgreSQL & Redis running locally or in cloud.

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
# Update .env with DB credentials
uvicorn main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Customer Onboarding (Agentless)
1.  User clicks "Connect Account" in Frontend.
2.  System generates CloudFormation Template with unique `ExternalID`.
3.  User deploys template in their AWS account.
4.  System verifies access via `sts.get_caller_identity`.

---

## 5. API Reference (Key Endpoints)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/accounts` | Connect new AWS account |
| `POST` | `/api/v1/lab/evaluate` | Run Lab Mode on specific instance |
| `GET` | `/api/v1/waste` | List detected waste resources |
| `GET` | `/api/v1/governance` | List unauthorized instances |
| `POST` | `/api/v1/approve/{id}` | Approve pending optimization switch |

---

## 6. Directory Structure

```
.
├── backend/
│   ├── pipelines/          # Core optimization logic
│   │   ├── linear_optimizer.py      # Lab Mode (single instance)
│   │   ├── cluster_optimizer.py     # Production ASG Mode
│   │   └── kubernetes_optimizer.py  # Production K8s Mode
│   ├── jobs/               # Background workers
│   │   ├── waste_scanner.py        # Financial hygiene
│   │   └── security_enforcer.py    # Governance cop
│   ├── logic/              # Intelligence layer
│   │   └── risk_manager.py         # Global pool intelligence
│   ├── utils/              # Helper modules
│   │   ├── aws_session.py          # STS AssumeRole
│   │   └── k8s_auth.py             # EKS authentication
│   ├── api/                # FastAPI endpoints
│   ├── database/           # SQLAlchemy models
│   └── ml/                 # Machine learning models
├── frontend/
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Route pages
│   │   └── services/       # API clients
│   └── public/             # Static assets
└── database/
    └── schema.sql          # PostgreSQL schema
```

---

## 7. Core Components

### 7.1 Linear Pipeline (Lab Mode)
**File:** `backend/pipelines/linear_optimizer.py`

**Purpose:** Single-instance optimization for testing and validation.

**Process Flow:**
1. **Scrape:** Fetch current On-Demand price from AWS Pricing API
2. **Filter:** Validate instance is eligible for Spot
3. **ML Predict:** Query risk model for interruption probability
4. **Decision:** Compare TCO (On-Demand vs Spot)
5. **Atomic Switch:** Snapshot → Launch Spot → Swap IPs → Terminate old

**Key Safety Features:**
- Creates EBS snapshot before switch
- Preserves Elastic IP (no DNS changes)
- Rolls back on failure
- Shadow Mode available (simulation only)

---

### 7.2 Cluster Pipeline (Production ASG Mode)
**File:** `backend/pipelines/cluster_optimizer.py`

**Purpose:** Batch optimization for Auto Scaling Groups.

**Process Flow:**
1. **Discovery:** Query AWS Auto Scaling API for ASG instances
2. **Filtration:** Identify On-Demand instances that are InService
3. **Global Risk Check:** Query `SpotPoolRisk` table (Herd Immunity)
4. **Execution:** Scale-Out Swap pattern for each instance
   - Launch new Spot instance
   - Attach to ASG (N → N+1)
   - Detach old instance (N+1 → N)
   - Terminate old instance

**Critical Invariant:** ASG capacity NEVER drops below desired count.

---

### 7.3 Kubernetes Pipeline (Production K8s Mode)
**File:** `backend/pipelines/kubernetes_optimizer.py`

**Purpose:** Zero-downtime worker node replacement in EKS clusters.

**Process Flow (4-Step Safety Dance):**
1. **Phase 1: Scale Out** - Launch new Spot node BEFORE touching old node
2. **Phase 2: Cordon** - Mark old node unschedulable (`kubectl cordon`)
3. **Phase 3: Drain** - Evict pods respecting PodDisruptionBudgets
4. **Phase 4: Terminate** - Remove old EC2 instance

**Key Safety Features:**
- Cluster capacity never drops (scale out first)
- Respects PodDisruptionBudgets (no availability loss)
- Skips DaemonSet pods (can't be evicted)
- Polls for pod termination (max 5 minutes)
- Uses STS-based EKS authentication (no long-lived credentials)

---

### 7.4 Risk Manager (Global Intelligence)
**File:** `backend/logic/risk_manager.py`

**Purpose:** Provide "Herd Immunity" by tracking Spot pool failures globally.

**How It Works:**
1. **Signal Capture:** Listens for AWS EventBridge Spot interruption events
2. **Context Check:** Only Production interruptions trigger poisoning (Lab failures ignored)
3. **The Quarantine:** Mark pool as poisoned for 15 days in `SpotPoolRisk` table
4. **The Shield:** All pipelines check `is_pool_poisoned()` before launching Spot

**Database Table:** `SpotPoolRisk`
```python
{
    "region": "us-east-1",
    "availability_zone": "us-east-1a",
    "instance_type": "c5.large",
    "is_poisoned": True,
    "poison_expires_at": "2025-12-30T00:00:00Z",
    "interruption_count": 3
}
```

**Why 15 Days?** AWS historical data shows pool volatility stabilizes after 2 weeks.

---

### 7.5 Waste Scanner (Financial Janitor)
**File:** `backend/jobs/waste_scanner.py`

**Purpose:** Automated detection and cleanup of unused AWS resources.

**What It Scans:**
1. **Elastic IPs:** Not attached to any instance → $3.60/month waste
2. **EBS Volumes:** Unattached for > 7 days → ~$0.08/GB-month
3. **EBS Snapshots:** > 30 days old AND not linked to AMI → ~$0.05/GB-month

**Process:**
- Runs daily via background job
- Stores findings in `WasteResource` table
- Calculates estimated monthly cost
- Provides cleanup recommendations (manual approval required)

**Safety:** Never auto-deletes. Requires manual approval via API.

---

### 7.6 Security Enforcer (Governance Cop)
**File:** `backend/jobs/security_enforcer.py`

**Purpose:** Detect and terminate unauthorized "Shadow IT" instances.

**Authorization Check (The ID Check):**
An instance is authorized if it has ANY of these tags:
1. `ManagedBy: SpotOptimizer` - System-managed instance
2. `aws:autoscaling:groupName` - Part of Auto Scaling Group
3. `eks:cluster-name` or `kubernetes.io/cluster/...` - Part of EKS cluster

**Enforcement Flow:**
1. **The Audit:** Scan all running EC2 instances in account
2. **The ID Check:** Verify authorization tags
3. **The Verdict:** Flag unauthorized instances in database
4. **The Grace Period:** 24 hours to fix (add tags)
5. **The Execution:** Terminate after grace period expires

**Why Tag Inheritance Matters:** When ASG or EKS creates instances, they automatically inherit tags. This prevents false positives.

---

### 7.7 Kubernetes Authentication
**File:** `backend/utils/k8s_auth.py`

**Purpose:** Authenticate to Amazon EKS clusters using AWS STS (no long-lived credentials).

**How STS Authentication Works:**
1. **Get AWS Credentials:** Use `sts:AssumeRole` to get temporary credentials
2. **Generate EKS Token:** Create presigned URL for `GetCallerIdentity`
3. **Encode Token:** Base64-encode as `k8s-aws-v1.TOKEN`
4. **Get Cluster Info:** Call `eks:DescribeCluster` for endpoint and CA
5. **Create Kubeconfig:** Generate temporary config file
6. **Initialize Client:** Return `kubernetes.client.CoreV1Api()`

**Key Function:**
```python
from utils.k8s_auth import get_k8s_client

k8s_client = get_k8s_client(
    cluster_name='prod-eks',
    region='us-east-1',
    account=account_record,
    db=db_session
)

# Now you can use the client
nodes = k8s_client.list_node()
```

**Security:** Token expires in 15 minutes (AWS default). No credentials stored on disk.

---

## 8. Database Schema

### 8.1 Core Tables

#### `accounts`
Stores connected AWS accounts and their credentials.
```sql
- id (UUID)
- account_id (AWS Account ID)
- account_name (Human-readable name)
- region (Default region)
- role_arn (IAM Role ARN for AssumeRole)
- external_id (Secret for AssumeRole)
- environment_type (PROD or LAB)
```

#### `instances`
Tracks all managed EC2 instances.
```sql
- id (UUID)
- account_id (Foreign key to accounts)
- instance_id (EC2 instance ID)
- instance_type (e.g., c5.large)
- availability_zone (e.g., us-east-1a)
- pricing_type (ON_DEMAND, SPOT, RESERVED)
- pipeline_mode (LINEAR, CLUSTER, KUBERNETES)
- cluster_membership (JSONB - K8s cluster info)
- metadata (JSONB - ASG name, tags, etc.)
- status (active, switching, terminated)
- auth_status (authorized, flagged, grace_period)
```

#### `spot_pool_risk`
Global risk intelligence for Spot pools.
```sql
- id (UUID)
- region (AWS region)
- availability_zone (AZ code)
- instance_type (EC2 type)
- is_poisoned (Boolean)
- poison_expires_at (Timestamp)
- interruption_count (Integer)
- last_interruption_at (Timestamp)
```

#### `waste_resources`
Detected unused resources.
```sql
- id (UUID)
- account_id (Foreign key)
- resource_type (elastic_ip, ebs_volume, ebs_snapshot)
- resource_id (AWS resource ID)
- region (AWS region)
- monthly_cost (Estimated cost)
- detected_at (Timestamp)
- days_unused (Integer)
- status (pending, approved, deleted)
```

#### `approval_requests`
Manual approval gate for risky operations.
```sql
- id (UUID)
- request_type (spot_switch, waste_deletion, unauthorized_termination)
- resource_id (Instance or waste resource ID)
- justification (Text description)
- status (pending, approved, rejected)
- requested_at (Timestamp)
- approved_by (User ID)
```

---

## 9. Frontend Architecture

### 9.1 Key Pages

#### Dashboard (`src/pages/Dashboard.jsx`)
- **Purpose:** Overview of all optimization activity
- **Metrics Displayed:**
  - Total monthly savings
  - Active optimizations
  - Spot instance count
  - Success rate

#### System Monitor (`src/pages/SystemMonitor.jsx`)
- **Purpose:** Real-time cluster health
- **Data Sources:**
  - Live instance list from `/api/v1/instances`
  - Pending switches from `/api/v1/approvals`
  - System metrics (CPU, memory, pod count for K8s nodes)

#### Live Operations (`src/pages/LiveOperations.jsx`)
- **Purpose:** Governance and waste management
- **Tabs:**
  - Waste Detection (Elastic IPs, Volumes, Snapshots)
  - Security Audit (Unauthorized instances)
  - Approval Queue (Manual gate)

### 9.2 Key Components

#### `InstanceCard.jsx`
Displays single instance with status indicator (Spot/On-Demand), cost comparison, and action buttons.

#### `WasteResourceTable.jsx`
Table view of detected waste with estimated monthly cost and cleanup actions.

#### `ApprovalGate.jsx`
Manual approval UI for risky operations (displays risk justification and approve/reject buttons).

---

## 10. Machine Learning Models

### 10.1 Spot Interruption Predictor
**File:** `backend/ml/spot_risk_model.py`

**Purpose:** Predict probability of Spot interruption within next hour.

**Features Used:**
- Historical interruption frequency (last 7 days)
- Time of day (UTC hour)
- Day of week
- Regional capacity indicators
- Current Spot price trend

**Model:** LightGBM Classifier (trained on 6 months of AWS EventBridge data)

**Output:** Risk score 0.0 - 1.0
- < 0.2: Low risk (safe to use)
- 0.2 - 0.5: Medium risk (caution)
- \> 0.5: High risk (avoid)

**Retraining:** Monthly, using latest interruption signals from `SpotPoolRisk` table.

---

## 11. Security & Compliance

### 11.1 Agentless Architecture
No software runs inside customer environments. All operations via AWS APIs using cross-account IAM roles.

**Benefits:**
- No attack surface inside customer VPC
- No credentials stored on customer instances
- Instant revocation (delete IAM role)

### 11.2 Credential Management
- **STS AssumeRole:** All AWS operations use temporary 1-hour credentials
- **ExternalID:** Prevents confused deputy attacks
- **Least Privilege:** IAM roles have minimal permissions
- **Rotation:** No long-lived credentials exist

### 11.3 Audit Trail
All actions logged to structured JSON logs:
```json
{
  "timestamp": "2025-12-15T17:00:00Z",
  "action": "spot_switch",
  "account_id": "123456789012",
  "instance_id": "i-1234567890abcdef0",
  "old_instance_type": "c5.large",
  "new_instance_type": "c5.large",
  "pricing_change": "ON_DEMAND -> SPOT",
  "estimated_savings": 234.50,
  "user": "system",
  "result": "success"
}
```

### 11.4 Compliance Features
- **Immutable Infrastructure:** Security Enforcer prevents drift
- **Change Approval:** Manual gate for production switches
- **Rollback:** Automatic rollback on switch failure
- **Cost Tracking:** All optimizations tracked for audit

---

## 12. Deployment Guide

### 12.1 Production Checklist

#### Infrastructure
- [ ] PostgreSQL 13+ with >= 10GB storage
- [ ] Redis 6+ for ML feature cache
- [ ] Backend server with >= 2GB RAM
- [ ] Frontend CDN or static hosting

#### AWS Prerequisites
- [ ] IAM role template for customer onboarding
- [ ] EventBridge listener for Spot interruptions
- [ ] S3 bucket for EBS snapshots (optional)

#### Application Configuration
- [ ] Set `DATABASE_URL` in backend `.env`
- [ ] Set `REDIS_URL` in backend `.env`
- [ ] Configure CORS for frontend domain
- [ ] Generate JWT secret key
- [ ] Set `VITE_API_URL` in frontend `.env`

#### Post-Deployment
- [ ] Run database migrations: `alembic upgrade head`
- [ ] Seed initial admin user
- [ ] Test account connection flow
- [ ] Schedule background jobs (Waste Scanner: daily, Security Enforcer: hourly)

### 12.2 Production Environment Variables

**Backend `.env`:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
REDIS_URL=redis://host:6379/0
JWT_SECRET=<random-64-char-string>
AWS_REGION=us-east-1
LOG_LEVEL=INFO
ENVIRONMENT=production
```

**Frontend `.env.production`:**
```bash
VITE_API_URL=https://api.yourdomain.com
VITE_APP_NAME=SpotOptimizer
```

---

## 13. Operational Procedures

### 13.1 Customer Onboarding
1. Customer clicks "Connect Account" in UI
2. System generates CloudFormation template with unique ExternalID
3. Customer deploys template in their AWS account (creates IAM role)
4. System validates access: `sts.get_caller_identity()`
5. Background discovery job populates `instances` table

### 13.2 Running Lab Mode Test
```bash
# Via API
POST /api/v1/lab/instances
{
  "account_id": "<account_uuid>",
  "instance_id": "i-1234567890abcdef0",
  "pipeline_mode": "LINEAR",
  "is_shadow_mode": true  # Simulation only
}

POST /api/v1/lab/instances/<instance_uuid>/evaluate
# Returns optimization recommendation

POST /api/v1/lab/instances/<instance_uuid>/execute
# Executes atomic switch (if approved)
```

### 13.3 Enabling Production ASG Mode
1. Tag ASG instances with `ManagedBy: SpotOptimizer`
2. Update instance metadata in database:
```python
instance.metadata = {"asg_name": "my-production-asg"}
instance.pipeline_mode = "CLUSTER"
```
3. Run evaluation: `POST /api/v1/instances/<uuid>/evaluate`
4. Approve switch: `POST /api/v1/approve/<request_id>`

### 13.4 Enabling Production K8s Mode
1. Ensure IAM role has EKS permissions
2. Install `kubernetes` Python package: `pip install kubernetes==26.1.0`
3. Update instance metadata:
```python
instance.cluster_membership = {
    "cluster_name": "prod-eks",
    "node_group": "workers",
    "role": "worker"
}
instance.pipeline_mode = "KUBERNETES"
```
4. Run evaluation (will execute 4-Step Safety Dance)

---

## 14. Troubleshooting

### 14.1 Common Issues

#### "AssumeRole failed"
**Cause:** IAM role trust policy incorrect or ExternalID mismatch.
**Fix:** Verify ExternalID matches database record. Check trust policy allows your account.

#### "Kubernetes authentication failed"
**Cause:** IAM role lacks EKS permissions or cluster RBAC not configured.
**Fix:** Add `eks:DescribeCluster` to IAM policy. Configure K8s RBAC:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spot-optimizer-role
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "pods/eviction"]
  verbs: ["get", "list", "patch", "create"]
```

#### "Atomic switch failed - rollback triggered"
**Cause:** New Spot instance failed health check.
**Fix:** Check Spot instance logs. Verify AMI compatibility. Check Security Group rules.

#### "Pool is poisoned - skipping optimization"
**Cause:** Recent Spot interruption in that region+AZ+type.
**Fix:** Wait for 15-day cooldown or manually clear: `UPDATE spot_pool_risk SET is_poisoned = false WHERE ...`

### 14.2 Logs and Monitoring
- **Application Logs:** `backend/logs/app.log` (structured JSON)
- **Worker Logs:** `backend/logs/workers.log`
- **Database Queries:** Enable SQLAlchemy echo mode for debugging
- **AWS API Calls:** Use AWS CloudTrail for audit

---

## 15. Performance Optimization

### 15.1 Database Indexes
```sql
CREATE INDEX idx_instances_account ON instances(account_id);
CREATE INDEX idx_instances_status ON instances(status);
CREATE INDEX idx_pool_risk_lookup ON spot_pool_risk(region, availability_zone, instance_type);
CREATE INDEX idx_waste_status ON waste_resources(status);
```

### 15.2 Caching Strategy
- **Redis Cache:** ML model predictions (TTL: 1 hour)
- **Database Connection Pool:** 10-20 connections
- **API Response Cache:** Instance lists (TTL: 30 seconds)

### 15.3 Rate Limiting
- AWS API calls: Max 10/second per account (Boto3 built-in retry)
- Frontend API: 100 requests/minute per user

---

## 16. Testing

### 16.1 Unit Tests
```bash
cd backend
pytest tests/unit/
```

### 16.2 Integration Tests
```bash
# Requires AWS credentials and test account
pytest tests/integration/ --aws-account=test
```

### 16.3 End-to-End Tests
```bash
cd frontend
npm run test:e2e
```

---

## 17. Future Enhancements

### Planned Features (V3.2)
- [ ] Multi-cloud support (Azure, GCP)
- [ ] Savings Plans optimization
- [ ] Reserved Instance recommendations
- [ ] Cost anomaly detection
- [ ] Slack/Teams notifications
- [ ] Custom optimization policies

---

## 18. Support & Contribution

### Getting Help
- Documentation: This file
- API Docs: `https://api.yourdomain.com/docs` (Swagger UI)
- Issue Tracker: GitHub Issues

### Contributing
1. Fork the repository
2. Create feature branch
3. Submit pull request with tests

---

## 19. License
[Your License Here]

---

**Document Version:** 3.1.0
**Last Updated:** December 15, 2025
**Status:** Production Ready ✅
