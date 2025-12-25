# AWS Cloud Optimization Platform - Complete Application Guide

## Purpose

This document provides a **complete, human-readable, scenario-based description** of the entire application. It explains what the application does, how users interact with it, and how all components work together.

**Last Updated**: 2025-12-25
**Authority**: HIGH (Master application reference)

---

## Table of Contents

1. [Application Overview](#application-overview)
2. [User Scenarios](#user-scenarios)
3. [Feature Catalog](#feature-catalog)
4. [Technical Architecture](#technical-architecture)
5. [Data Flow](#data-flow)
6. [Security](#security)
7. [Deployment](#deployment)

---

## Application Overview

### What is This Application?

**AWS Cloud Optimization Platform** is a SaaS application that helps businesses optimize their AWS infrastructure costs and performance. It connects to users' AWS accounts, discovers resources, analyzes usage patterns, and provides ML-powered recommendations for cost savings and performance improvements.

### Core Value Proposition

- **Save 30-50% on AWS costs** through automated optimization recommendations
- **Prevent waste** by identifying idle and underutilized resources
- **ML-powered decisions** using predictive models for spot instance stability, pricing, and right-sizing
- **Multi-account support** for managing multiple AWS accounts from one dashboard
- **Real-time monitoring** with live updates and notifications

### Target Users

1. **Engineering Teams** - Optimize infrastructure costs without sacrificing performance
2. **DevOps Engineers** - Automate resource management and waste reduction
3. **Finance/FinOps Teams** - Track and control cloud spending
4. **Data Scientists** - Run ML experiments cost-effectively on optimized instances

---

## User Scenarios

### Scenario 1: New User Onboarding

**User Story**: As a new user, I want to connect my AWS account and see cost savings opportunities.

#### Steps:
1. **Sign Up & Login**
   - User creates account at /signup
   - Enters email, password, organization name
   - Receives verification email (if email verification enabled)
   - Logs in at /login

2. **Account Connection** (Two Methods)

   **Method A: CloudFormation (Recommended)**
   - User clicks "Connect AWS Account"
   - Selects "CloudFormation" method
   - System generates CloudFormation template
   - User clicks "Deploy to AWS" (opens AWS Console)
   - User creates stack in AWS
   - Returns to platform, enters AWS Account ID
   - System verifies IAM role connection
   - Success: Account status → 'connected'

   **Method B: Access Keys (Quick Setup)**
   - User clicks "Connect AWS Account"
   - Selects "Access Keys" method
   - Enters AWS Access Key ID and Secret Access Key
   - System validates credentials via AWS STS
   - Success: Account status → 'connected'

3. **Resource Discovery**
   - Background worker automatically discovers:
     - EC2 instances (all regions)
     - EBS volumes
     - Snapshots
     - Security groups
     - Tags and metadata
   - Discovery takes 30-120 seconds
   - User sees progress: "Discovering resources... 45s elapsed"
   - Account status → 'active' when complete

4. **Dashboard View**
   - User redirected to /client dashboard
   - Sees metrics:
     - Current month cost: $1,234.56
     - Projected savings: $450.00 (36%)
     - Instance count: 23 instances
     - Idle instances: 5
     - Utilization: 42%
   - Charts: Cost trend, usage patterns, instance distribution

5. **First Recommendations**
   - Platform shows top 5 optimization opportunities:
     1. Stop 3 idle instances → Save $120/month
     2. Resize 2 over-provisioned instances → Save $200/month
     3. Use Spot instances for dev/test → Save $100/month
     4. Delete 10 unused snapshots → Save $15/month
     5. Consolidate 2 underutilized instances → Save $80/month

**See**: `/scenarios/client_onboarding_flow.md`

---

### Scenario 2: Daily Usage - Managing AWS Resources

**User Story**: As an existing user, I want to monitor my AWS resources and implement optimization recommendations.

#### Steps:
1. **Login & Dashboard**
   - User logs in
   - AuthGateway checks connected accounts
   - Routes to /client dashboard
   - Sees updated metrics (refreshed via health checks)

2. **View Instance Details**
   - User clicks on an instance (e.g., "i-1234567890abcdef0")
   - Sees detailed view:
     - Instance type: t3.large
     - State: running
     - CPU utilization (7 days): avg 15%, max 22%
     - Memory utilization: avg 18%
     - Cost: $60.74/month (on-demand)
     - Tags: Environment=dev, Owner=john@example.com

3. **Receive Recommendation**
   - Platform shows optimization card:
     - **Recommendation**: Resize to t3.medium
     - **Reason**: Average CPU 15%, consistently underutilized
     - **Savings**: $30.37/month (50% reduction)
     - **Risk Score**: 20/100 (Low risk)
     - **Confidence**: 92%

4. **Implement Optimization**
   - User clicks "Resize Instance"
   - Confirmation dialog shows:
     - Action: Resize i-1234567890abcdef0
     - From: t3.large → To: t3.medium
     - Expected downtime: ~2 minutes
     - Rollback available: Yes
   - User confirms
   - System executes:
     1. Stop instance
     2. Modify instance type
     3. Start instance
     4. Update database
     5. Log action
   - Success notification: "Instance resized successfully!"

5. **Track Savings**
   - Dashboard "Implemented Savings" updates
   - Shows cumulative savings: $30.37/month added
   - Total savings this month: $180.45
   - Projected annual savings: $2,165.40

**See**: Main dashboard and optimization features

---

### Scenario 3: Multi-Account Management

**User Story**: As a large organization, I want to manage multiple AWS accounts from one dashboard.

#### Steps:
1. **Connect Additional Account**
   - User clicks "Add Account" button
   - Follows onboarding flow (CloudFormation or Access Keys)
   - New account added to account list
   - Discovery runs for new account

2. **Switch Between Accounts**
   - User sees account dropdown in header:
     - Production (AWS: 123456789012)
     - Staging (AWS: 234567890123)
     - Development (AWS: 345678901234)
   - User selects "Staging"
   - Dashboard refreshes with Staging account data
   - All actions now apply to Staging account

3. **Cross-Account View**
   - User navigates to "All Accounts" view
   - Sees aggregated metrics:
     - Total cost across all accounts: $5,432.10
     - Total instances: 67
     - Accounts with alerts: 2
   - Can drill down into specific account

4. **Disconnect Account**
   - User clicks "Manage Accounts"
   - Sees list of connected accounts
   - Clicks "Disconnect" on old Development account
   - Confirmation: "Are you sure? This will remove all data for this account."
   - User confirms
   - System deletes:
     - Account record
     - All instances for that account
     - All logs and metrics
   - Success: "Account disconnected"

**See**: `/progress/fixed_issues_log.md#P-2025-12-25-003` (delete endpoint fix)

---

### Scenario 4: ML Experiment Tracking

**User Story**: As a data scientist, I want to track ML experiments on my AWS instances.

#### Steps:
1. **Navigate to Lab**
   - User clicks "Lab" in sidebar
   - Sees experiment dashboard

2. **View Running Experiments**
   - User sees list of experiments:
     - Experiment: "BERT fine-tuning v3"
       - Instance: i-abc123 (p3.2xlarge)
       - Status: Running (GPU: 87%)
       - Progress: 45% (epoch 3/7)
       - Cost: $3.06/hour
       - Estimated completion: 2h 15m

3. **Create New Experiment**
   - User clicks "New Experiment"
   - Fills form:
     - Name: "ResNet image classification"
     - Instance: Select from available GPU instances
     - Training script: Upload .py file
     - Dataset: S3 path
   - User submits
   - System:
     - Starts instance (if stopped)
     - Uploads training script
     - Begins training
     - Streams logs to dashboard

4. **Track Metrics**
   - User sees real-time metrics:
     - Training loss: 0.234 (decreasing)
     - Validation accuracy: 89.3%
     - GPU utilization: 92%
     - Cost so far: $8.45
   - Charts update every 30 seconds

5. **Experiment Completion**
   - Training completes
   - System:
     - Saves model to S3
     - Records final metrics
     - Stops instance (if configured)
     - Logs total cost: $24.18
   - User downloads trained model

**See**: `/frontend/src/components/Lab/` components

---

### Scenario 5: Security & Compliance

**User Story**: As a security engineer, I want to ensure AWS resources comply with security policies.

#### Steps:
1. **Security Dashboard**
   - User navigates to "Security" tab
   - Sees security findings:
     - 🔴 3 Critical issues
     - 🟠 7 High issues
     - 🟡 12 Medium issues

2. **Review Findings**
   - **Critical: Unencrypted EBS volumes**
     - 3 volumes without encryption
     - Instances: i-abc123, i-def456, i-ghi789
     - Risk: Data exposure if volume compromised
     - Action: Enable encryption or delete

   - **High: Security group allows 0.0.0.0/0 on port 22**
     - Security group: sg-12345
     - Rule: SSH from anywhere
     - Risk: Unauthorized access
     - Action: Restrict to specific IP ranges

3. **Auto-Remediation**
   - User enables "Auto-Remediate" for specific rules
   - System automatically:
     - Enables encryption on new volumes
     - Alerts on overly permissive security groups
     - Enforces tagging policies
     - Rotates access keys >90 days old

4. **Compliance Reports**
   - User generates compliance report
   - Selects framework: "CIS AWS Foundations Benchmark"
   - Report shows:
     - 85% compliance score
     - 45/53 controls passing
     - 8 controls failing
     - Remediation steps for each failure

**See**: `/backend/jobs/security_enforcer.py`

---

### Scenario 6: Cost Forecasting & Budgets

**User Story**: As a FinOps manager, I want to forecast AWS costs and set budgets.

#### Steps:
1. **View Cost Trends**
   - User navigates to "Cost Analysis"
   - Sees charts:
     - Last 30 days: Actual vs predicted costs
     - Cost breakdown by service (EC2 70%, EBS 15%, S3 10%, Other 5%)
     - Cost breakdown by environment (Prod 60%, Dev 25%, Test 15%)

2. **Cost Forecast**
   - ML model predicts next month costs:
     - Predicted: $1,850 ± $120
     - Current trend: +12% month-over-month
     - Key drivers: 3 new production instances, increased data transfer

3. **Set Budget Alerts**
   - User sets budget: $2,000/month
   - Configures alerts:
     - 80% of budget ($1,600): Email notification
     - 100% of budget ($2,000): Email + Slack notification
     - 120% of budget ($2,400): Email + Slack + Stop non-production instances

4. **Receive Alert**
   - Month-to-date spend reaches $1,620 (81%)
   - User receives email:
     - "Budget Alert: 81% of monthly budget consumed"
     - Current spend: $1,620
     - Projected month-end: $1,985
     - Days remaining: 8
     - Recommendations to stay under budget

**See**: Cost prediction features

---

## Feature Catalog

### Authentication & User Management

**Components**:
- Frontend: Login, Signup, AuthContext
- Backend: `/api/auth/login`, `/api/auth/me`, JWT tokens
- Database: `users` table

**Features**:
- Email/password authentication
- JWT tokens (24-hour expiration)
- Role-based access control (client, admin, super_admin)
- Session persistence
- Logout

**Security**:
- Bcrypt password hashing (12 rounds)
- HS256 JWT signing
- HTTP-only cookies (optional)
- HTTPS-only in production

**See**: `/scenarios/auth_flow.md`, `/backend/auth/info.md`

---

### AWS Account Connection

**Components**:
- Frontend: ClientSetup component
- Backend: `/api/client/onboarding/*` routes
- Database: `accounts` table, `onboarding_requests` table (temporary)

**Features**:
- **CloudFormation Method**:
  - Generate CloudFormation template
  - Create IAM role with minimal permissions
  - Verify role via AWS STS AssumeRole
  - Global uniqueness check (prevent account takeover)

- **Access Keys Method**:
  - Validate credentials via STS GetCallerIdentity
  - Encrypt credentials with AES-256 (Fernet)
  - Store encrypted in database
  - Global uniqueness check

**Security**:
- AWS account IDs are globally unique (one user per account)
- Credentials encrypted at rest
- IAM permissions: read-only + limited write (stop/start/modify instances)
- Ownership verification on all account operations

**See**: `/scenarios/client_onboarding_flow.md`, `/progress/fixed_issues_log.md#P-2025-12-25-001`

---

### Resource Discovery

**Components**:
- Backend: `discovery_worker.py`
- Database: `instances` table, `accounts` table (status updates)

**Process**:
1. Triggered after account connection
2. Runs in background (FastAPI BackgroundTasks)
3. Discovers:
   - EC2 instances (all regions)
   - EBS volumes
   - Snapshots
   - Instance tags
4. Stores in database
5. Updates account status: 'connected' → 'active'
6. Triggers health checks immediately

**Frequency**:
- Initial discovery: On account connection
- Periodic refresh: Every 6 hours (scheduled job)

**See**: `/backend/workers/info.md`, `/progress/fixed_issues_log.md#P-2025-12-25-002`

---

### Dashboard & Metrics

**Components**:
- Frontend: ClientDashboard component
- Backend: `/api/client/dashboard` endpoint
- Background: Health check worker

**Metrics Displayed**:
- Total monthly cost
- Instance count (running, stopped, total)
- CPU utilization average
- Memory utilization average
- Storage usage
- Cost trend chart (last 30 days)
- Top 5 expensive instances

**Data Sources**:
- Database (instances, accounts)
- AWS CloudWatch (metrics)
- Cost calculation engine

**Refresh Rate**:
- Frontend: 30 seconds (polling)
- Health checks: Hourly + after discovery
- Cost data: Daily (midnight UTC)

**See**: `/frontend/src/components/info.md`, `/backend/utils/component_health_checks.py`

---

### Optimization Recommendations

**Components**:
- Backend: Decision engine, scoring algorithms
- ML Models: Cost prediction, waste detection
- Frontend: Recommendations dashboard

**Recommendation Types**:

1. **Right-Sizing**
   - Detect: CPU/memory < 20% for 7+ days
   - Recommend: Resize to smaller instance type
   - Savings: 30-50% cost reduction
   - Risk: Low (20-30/100)

2. **Idle Instance Stop/Termination**
   - Detect: CPU < 5% for 7+ days
   - Recommend: Stop (if dev/test) or terminate (if unused)
   - Savings: 100% for terminated, 70% for stopped
   - Risk: Medium (40-50/100) - requires confirmation

3. **Spot Instance Migration**
   - Detect: Non-production instances on on-demand
   - Recommend: Switch to Spot instances
   - Savings: 60-80% cost reduction
   - Risk: Medium (50-60/100) - spot interruptions

4. **Reserved Instance Recommendations**
   - Detect: Steady-state workloads (>80% uptime for 30+ days)
   - Recommend: Purchase 1-year or 3-year RIs
   - Savings: 40-60% cost reduction
   - Risk: Low (10-20/100) - commitment

5. **Storage Optimization**
   - Detect: Unattached volumes, old snapshots
   - Recommend: Delete or archive
   - Savings: $0.10/GB/month
   - Risk: Low (if backups exist)

**Scoring Algorithm**:
```
Optimization Score =
  (Cost Savings × 0.4) +
  (Waste Level × 0.3) +
  (Risk Inverse × 0.15) +
  (Urgency × 0.15)
```

**See**: `/backend/decision_engine/info.md`, `/backend/pipelines/info.md`

---

### Action Execution

**Components**:
- Backend: Executor module, AWS API integration
- Frontend: Action confirmation dialogs

**Supported Actions**:
- **Instance Lifecycle**:
  - Stop instance
  - Start instance
  - Terminate instance (requires confirmation)

- **Instance Modification**:
  - Resize (change instance type)
  - Modify security groups
  - Update tags

- **Storage**:
  - Delete volumes
  - Delete snapshots
  - Create snapshots (before risky actions)

**Safety Mechanisms**:
1. **Ownership Verification**: User must own the account
2. **Dry-Run**: AWS dry-run API to validate before execution
3. **Confirmation**: Critical actions require explicit confirmation
4. **Audit Logging**: All actions logged to SystemLog
5. **Rollback**: Ability to revert some actions (e.g., resize back)

**See**: `/backend/executor/info.md`

---

### Multi-Account Management

**Components**:
- Frontend: Account switcher, account list
- Backend: `/api/client/accounts` endpoints
- Database: `accounts` table (one-to-many with users)

**Features**:
- Connect multiple AWS accounts
- Switch between accounts via dropdown
- Aggregate view across all accounts
- Disconnect accounts (with cascade delete)

**Recent Enhancement (2025-12-25)**:
- Added DELETE endpoint for account disconnection
- Fixed HTTP 204 → 200 status code issue
- Cascade delete instances when account deleted

**See**: `/progress/fixed_issues_log.md#P-2025-12-25-003`

---

### Real-Time Updates (WebSocket)

**Components**:
- Backend: WebSocket manager
- Frontend: WebSocket client

**Events**:
- Instance state changes
- Discovery progress
- Cost updates
- Alerts and notifications

**Protocol**:
```javascript
// Client connects
ws = new WebSocket('ws://api.example.com/ws/user123');

// Subscribe to channel
ws.send({
  type: 'subscribe',
  channel: 'instance_status',
  filters: { account_id: '123456789012' }
});

// Receive updates
ws.onmessage = (event) => {
  // { type: 'update', data: { instance_id, status, ... } }
};
```

**See**: `/backend/websocket/info.md`

---

### ML Experiment Tracking

**Components**:
- Frontend: Lab components (ModelExperiments, ModelGovernance)
- Backend: Experiment tracking APIs
- Database: `experiment_logs` table

**Features**:
- Track ML experiments on EC2 instances
- Record metrics (loss, accuracy, etc.)
- Monitor GPU utilization
- Cost tracking per experiment
- Model versioning and governance
- Compare experiments (A/B testing)

**See**: `/frontend/src/components/Lab/info.md`

---

### Security & Compliance

**Components**:
- Backend: Security enforcer job
- Frontend: Security dashboard

**Checks**:
- Unencrypted EBS volumes
- Public instances (0.0.0.0/0 ingress)
- Overly permissive security groups
- Missing required tags
- Outdated AMIs

**Enforcement**:
- Automated tagging
- Alert on violations
- Auto-remediation (optional)

**See**: `/backend/jobs/info.md`

---

## Technical Architecture

### System Components

```
┌──────────────────┐
│   React Frontend │ (Port 5173 dev, nginx prod)
│   - Vite build   │
│   - React 18     │
└────────┬─────────┘
         │ HTTP/WebSocket
         ↓
┌──────────────────┐
│  FastAPI Backend │ (Port 8000)
│  - Python 3.8+   │
│  - RESTful API   │
└────────┬─────────┘
         │ SQL
         ↓
┌──────────────────┐
│   PostgreSQL DB  │ (Port 5432)
│   - SQLAlchemy   │
└──────────────────┘

         ↓ boto3
┌──────────────────┐
│    AWS Services  │
│  - EC2, STS      │
│  - CloudWatch    │
└──────────────────┘
```

### Key Technologies

**Backend**:
- FastAPI (web framework)
- SQLAlchemy (ORM)
- boto3 (AWS SDK)
- python-jose (JWT)
- passlib (password hashing)
- cryptography (AES-256 encryption)

**Frontend**:
- React 18
- Vite (build tool)
- React Router (routing)
- Axios (HTTP client)
- Context API (state management)

**Database**:
- PostgreSQL 12+
- 6 main tables (users, accounts, instances, experiment_logs, system_logs, onboarding_requests)

**Infrastructure**:
- Linux (Ubuntu/Debian)
- Nginx (reverse proxy)
- Systemd (service management)
- Docker (optional deployment)

**See**: `/index/system_index.md`, `/backend/info.md`, `/frontend/info.md`

---

## Data Flow

### Authentication Flow
```
User → Login Form → POST /api/auth/login
  → Verify credentials (bcrypt)
  → Generate JWT (24h expiration)
  → Return token + user data
  → Frontend stores token
  → All requests include Authorization header
```

### Onboarding Flow
```
User → ClientSetup → POST /client/onboarding/create-request
  → Generate CloudFormation template
  → User deploys in AWS
  → POST /client/onboarding/verify-connection
  → AssumeRole verification
  → Create Account record
  → Trigger discovery worker (background)
  → Discover instances (30-120s)
  → Update account status → 'active'
  → Trigger health checks
  → Dashboard displays metrics
```

### Optimization Flow
```
Scheduled Job (6h interval)
  → Waste Scanner
  → Query instances + CloudWatch metrics
  → Decision Engine evaluates
  → Scoring algorithm ranks opportunities
  → Store recommendations
  → User views recommendations
  → User approves action
  → Executor performs AWS API call
  → Update database
  → Log action
  → Recalculate metrics
```

**See**: `/scenarios/*.md` for detailed flows

---

## Security

### Authentication & Authorization

- **Password Storage**: Bcrypt with salt (12 rounds)
- **Session Management**: JWT tokens, 24-hour expiration
- **Token Secret**: Stored in environment variable (never in code)
- **HTTPS**: Required in production
- **Role-Based Access**: client, admin, super_admin roles

**Protected Zones**: See `/progress/regression_guard.md`

### AWS Credential Security

- **CloudFormation Method**: Uses IAM roles (no credentials stored)
- **Access Keys Method**:
  - Encrypted with AES-256 (Fernet)
  - Encryption key in environment variable
  - Decrypted only in memory, never logged
- **Account Uniqueness**: Global check prevents account takeover

**Critical Security Fixes**:
- P-2025-12-25-001: AWS account takeover vulnerability (CRITICAL)

### Data Protection

- **Database**: PostgreSQL with authentication required
- **Backups**: Daily automated backups (recommended)
- **Encryption at Rest**: Database encryption (optional)
- **Encryption in Transit**: HTTPS for all API calls

---

## Deployment

### Development Environment

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev  # Runs on port 5173
```

### Production Deployment

```bash
# Run setup script
./scripts/setup.sh

# Deploy
./scripts/deploy.sh production

# Or Docker
./scripts/deploy_docker.sh
```

**See**: `/scripts/info.md`

---

## Governance & Documentation

This application uses a **comprehensive governance structure** to maintain code quality and prevent regressions:

### Documentation Hierarchy

1. **Instructions** (`/instructions/`) - How to work with the codebase
2. **Index** (`/index/`) - System maps and feature catalog
3. **Progress** (`/progress/`) - Current state and fixed issues
4. **Problems** (`/problems/`) - Issue tracking and problem inbox
5. **Scenarios** (`/scenarios/`) - User flows and business logic
6. **Module info.md** - Folder-level documentation

### Key Governance Files

- `/instructions/master_rules.md` - Mandatory workflow
- `/progress/regression_guard.md` - Protected zones
- `/progress/fixed_issues_log.md` - All bug fixes (immutable)
- `/problems/problems_log.md` - All problems (immutable)
- `/problems/new_problem` - Active problem inbox

### Problem Reporting

Users can report problems directly to `/problems/new_problem` using the provided template. The LLM will:
1. Assign a Problem ID
2. Investigate and fix
3. Remove from new_problem when fixed
4. Document in fixed_issues_log.md

**See**: `/instructions/info.md`, `/problems/info.md`

---

## Recent Major Updates

### 2025-12-25: Comprehensive Governance Structure
- Created complete governance system
- 16 governance files across 5 folders
- info.md in every non-empty folder (40+ files)
- Problem inbox system (new_problem file)
- This scenario-based application guide

### 2025-12-25: Client Experience Improvements
- Multi-account support
- Account disconnect functionality
- AuthGateway smart routing
- Live polling for discovery progress
- Immediate health checks after discovery

### Critical Bug Fixes
- P-2025-12-25-001: AWS account takeover (SECURITY)
- P-2025-12-25-002: Dashboard zero data
- P-2025-12-25-003: DELETE endpoint HTTP 204 error

**See**: `/progress/fixed_issues_log.md`, `/index/recent_changes.md`

---

## Future Roadmap

### Planned Features
1. **Cost Anomaly Detection**: ML-based alerts for unusual spending
2. **Auto-Optimization**: Automated implementation of low-risk optimizations
3. **Multi-Cloud Support**: Extend to Azure, GCP
4. **Kubernetes Optimization**: Deep integration with EKS/K8s
5. **Mobile App**: iOS/Android companion apps
6. **API for Third-Party Integrations**: Public API for custom integrations

### Technical Debt
- TypeScript migration for frontend
- Automated testing (unit, integration, E2E)
- CI/CD pipeline
- Enhanced monitoring (Prometheus/Grafana)

**See**: `/progress/progress_tracker.md`

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Complete application reference_
_This document is automatically updated when new features are added_
