# Spot Optimizer Platform - Comprehensive Functional Specification

> **Platform Mission**: An automated cloud infrastructure optimization platform that uses AI to reduce Kubernetes and AWS costs by up to 70% while maintaining 99.99% availability.

---

## Table of Contents
1. [Authentication & Onboarding](#1-authentication--onboarding)
2. [Client Dashboard](#2-client-dashboard)
3. [Node Templates](#3-node-templates)
4. [Cloud Account Management](#4-cloud-account-management)
5. [Optimization Policies](#5-optimization-policies)
6. [Cluster Hibernation](#6-cluster-hibernation)
7. [Audit Logs & Compliance](#7-audit-logs--compliance)
8. [Multi-Cluster Command Center](#8-multi-cluster-command-center)
9. [Super Admin Console](#9-super-admin-console)
10. [Backend Architecture](#10-backend-architecture)
11. [Notifications & Alerting](#11-notifications--alerting)
12. [Billing & Subscription](#12-billing--subscription)
13. [Security & Compliance](#13-security--compliance)

---

## 1. Authentication & Onboarding

### 1.1 Unified Login/Sign-Up Portal

**Component**: `LoginPage.jsx`

#### Sign-Up Flow (New Clients)

**User Input**:
- Organization Name
- Email Address
- Password

**Backend Process** (`POST /api/auth/signup`):
1. **User Creation**: Creates record in `users` table with hashed password (bcrypt)
2. **Placeholder Account**: Generates "Placeholder" row in `accounts` table
   - Status: `pending`
   - Temporary `account_id`
   - **Purpose**: Prevents "Orphan User" state

#### Sign-In Flow

**Authentication** (`POST /api/auth/token`):
- Returns JWT containing User ID and Role

**Smart Routing** (AuthGateway):
```javascript
if (accounts.length == 0 || status == 'pending') {
  redirect('/onboarding')
} else if (accounts.length > 0 && status == 'active') {
  redirect('/dashboard')
}
```

### 1.2 Cloud Connect Interface

**Component**: `ClientSetup.jsx`

#### Option A: CloudFormation (Role-Based Access) 🛡️

**Best For**: Production environments, Enterprise clients

**Process**:
1. User enters AWS Account ID and Target Region
2. System generates unique External ID (UUID) for security
3. User receives pre-generated CloudFormation Template URL
4. User deploys stack in AWS Console
5. User clicks **[Verify]** button
6. Backend assumes IAM Role using `boto3.sts`
7. Validates permissions without storing credentials

#### Option B: Direct Credentials (Access Keys) 🔑

**Best For**: Lab environments, testing, rapid prototyping

**Process**:
1. User inputs AWS Access Key ID and Secret Access Key
2. **Encryption**: Secret Key encrypted using AES-256 (via `fernet`)
3. **Validation**: Backend calls `sts.get_caller_identity()` to verify keys

### 1.3 Connection State Management

**Global Uniqueness Check**:
- Prevents AWS Account ID duplication across users

**Upsert Strategy**:
- Updates pending placeholder account with AWS details
- Avoids duplicate rows

**Live Status Feedback**:
```
pending → scanning → active
```

**Discovery Trigger**:
- `DiscoveryWorker` immediately fetches EC2 instances
- Frontend polls status endpoint
- Displays "Connection Established" message

### 1.4 Security Architecture

| Layer | Protection |
|-------|-----------|
| **Data in Transit** | HTTPS/TLS 1.3 |
| **Data at Rest** | AES-256 encryption for secrets |
| **Scope Isolation** | `filter(Account.user_id == current_user.id)` |

---

## 2. Client Dashboard

### 2.1 Home Dashboard ("Single Pane of Glass")

#### KPI Cards

| Metric | Description | Calculation |
|--------|-------------|-------------|
| **Current Monthly Spend** | Total projected cost | Sum of all instance costs |
| **Net Savings** | Dollar amount saved | Baseline cost - Optimized cost |
| **Fleet Health** | Stability score (0-100%) | Weighted average of metrics |
| **Active Nodes** | Count of Spot vs On-Demand | Real-time inventory |

#### Visualizations

**1. Savings Projection Bar Chart**
- **X-Axis**: Time
- **Y-Axis**: Cost ($)
- **Bars**: 
  - Red: Unoptimized Spend
  - Green: Optimized Spend

**2. Fleet Composition Pie Chart**
- Breakdown by instance type (m5.large 40%, c5.xlarge 20%, etc.)

**3. Cluster Health Trend Line Graph**
- Overlays CPU Utilization with Spot Interruption Events

#### Real-Time Activity Feed

**Example Entries**:
```
Just now: Switched Node-4 from On-Demand to Spot (Saved $0.04/hr)
2 min ago: Cluster prod-us-east-1 scaled down (Removed 3 nodes)
5 min ago: Hibernation activated for dev-cluster
```

### 2.2 Unified Cluster Observability

#### Multi-Cluster Inventory Table

**Columns**:
- Cluster Name
- Region (with flag icon)
- Kubernetes Version (with EOL warnings)
- Node Count
- Monthly Run Rate ($)
- Efficiency Score (A-F grade)

**Calculations**:
```
Monthly Run Rate = SUM(instance_price * 730 hours)
Efficiency Score = Weighted Average(CPU Allocation / CPU Usage)
```

#### Bin Packing & Waste Analysis

**Resource Gap Area Chart**:
- **Red Line**: Actual Capacity (Total CPU/RAM available)
- **Green Line**: Requested Capacity (Total CPU/RAM needed)
- **Gap**: Represents waste (empty space being paid for)

**Calculation**:
```
Potential_Savings = Current_Cost - Cost_of_Perfectly_Packed_Nodes
```

#### Karpenter & Spot Optimization Monitor

**Fleet Composition Sunburst Chart**:
- Inner Ring: Lifecycle (Spot vs On-Demand)
- Outer Ring: Instance Family (m5, c5, r5, etc.)

**Spot Readiness Score**:
- Percentage of pods that are stateless and interruption-tolerant

**Calculation**:
```
Karpenter_Savings = (OnDemand_Price - Spot_Price) * Spot_Ready_Workloads
```

#### Hibernation Opportunities

**Activity Heatmap (24x7 Grid)**:
- **Red Blocks**: High activity (user logins, CI/CD jobs)
- **Blue Blocks**: Idle time (no API calls, low CPU)

**Insight**: Blue zones = wasted money

**Calculation**:
```
Hibernation_Savings = Hourly_Cost * Blue_Block_Count_Per_Month
```

#### Cluster Health & Stability Index

**Stability Gauge (0-100%)**:

**Components**:
- Pressure Events (DiskPressure, MemoryPressure frequency)
- Spot Stability (ML-predicted interruption probability)
- Control Plane Latency (EKS API response time)

**Color Coding**:
- Green: > 80%
- Orange: 60-80%
- Red: < 60%

---

## 3. Node Templates

**Location**: Sidebar → Node Templates

### 3.1 Main List View

**Header**:
- Title: "Node Provisioning Templates"
- Search Bar (real-time filter)
- **[+ Create New Template]** button

**Template Grid Columns**:

| Column | Content | Example |
|--------|---------|---------|
| **Name & Status** | Template name + Default badge | Production-General ⭐ |
| **Compute Constraints** | Family pills | `[m5, c5, r5] • x86_64` |
| **Purchasing Strategy** | Color-coded badge | `SPOT` (Orange) |
| **Storage** | Disk config | `gp3 (100GB)` |
| **Actions** | Three-dot menu | Edit, Clone, Set Default, Delete |

### 3.2 Create Template Wizard

#### Step 1: General Information
- **Template Name** (with live validation)
- **Description** (for team documentation)
- **Toggle**: "Make this the default template"

#### Step 2: Compute & Architecture

**Family Selector** (Visual multi-select grid):
- General Purpose (m5, m6i)
- Compute Optimized (c5, c6i, c7i)
- Memory Optimized (r5, r6i)
- GPU (g4dn, p3)

**Architecture Toggle**:
- x86 (Intel/AMD)
- ARM64 (Graviton)

**Size Exclusions**:
- Blacklist specific sizes (nano, micro, small)

#### Step 3: Spot & Purchasing Strategy

**Capacity Type Cards**:
1. **Spot Only**: Maximum savings, higher risk
2. **On-Demand**: Zero interruption, full price
3. **Hybrid**: Spot for stateless, On-Demand for DBs

**Spot Allocation Strategy**:
- **Lowest Price**: Absolute cheapest node
- **Capacity Optimized**: Least likely to be interrupted

#### Step 4: Storage & Networking

- **Disk Type**: gp2, gp3, io1, ephemeral
- **Disk Size**: Slider (50-500 GB)
- **Security Groups**: Searchable dropdown (fetches from AWS)

### 3.3 Visual Feedback

**Live Cost Estimator**:
```
Avg. Spot Price: $0.04/hr
Monthly Estimate: $29.20
```

**Conflict Detection**:
```
⚠️ Instance type g4dn is incompatible with ARM64
```

---

## 4. Cloud Account Management

**Location**: Sidebar → Settings → Cloud Integrations

### 4.1 Accounts List View

**Account Card Components**:
- Account Name (e.g., "Acme Corp Production")
- AWS Account ID (masked: `1234-****-****`)
- Region (primary: `us-east-1`)
- Connection Method badge (Role-Based 🛡️ / Access Key 🔑)
- Live Status:
  - 🟢 **Active**: Data syncing
  - 🟡 **Scanning**: Discovery in progress
  - 🔴 **Error**: Credentials invalid

**Action Menu** (Three dots):
- **Re-Sync**: Force fresh scan
- **Edit Name**: Rename account alias
- **Disconnect**: Remove account (with confirmation)

### 4.2 Multi-Account Support

**Organization View**:
- Add unlimited accounts
- Backend tags instances with `source_account_id`
- Dashboard shows:
  - Global View (All Accounts)
  - Filtered View (Specific Account)

---

## 5. Optimization Policies

**Location**: Sidebar → Optimization Policies

### 5.1 Infrastructure Layer (Tab A: Node Scaling)

#### Card 1: Intelligent Autoscaling (Karpenter)

**Master Toggle**: [ON / OFF]
- **OFF**: Cluster never adds nodes (pods stuck in Pending)
- **ON**: Reacts to pending pods in 1-2 seconds

**Provisioning Strategy**:
- 🔘 **Lowest Cost**: Cheapest instance per vCPU
  - Use Case: Batch processing, CI/CD, dev environments
- 🔘 **Capacity Optimized** (Recommended): Deepest capacity pools
  - Use Case: Production (reduces interruptions)

**Constraint Boundary**:
- Dropdown: Select Node Template
- Impact: Autoscaler forbidden from launching types not in template

**Spot Fallback Protection**: [Checkbox]
- Auto-fallback to On-Demand if Spot unavailable
- Ensures 100% uptime during AWS outages

#### Card 2: Bin Packing & Consolidation

**Aggressiveness Slider**:

| Level | Threshold | Behavior |
|-------|-----------|----------|
| **Conservative** | < 20% utilized | Very stable, moderate savings |
| **Balanced** | < 50% utilized | Good mix of cost/stability |
| **Aggressive** | < 80% utilized | Maximum savings (70%), frequent restarts |

**Consolidation Method**:
- 🔘 **Delete Empty**: Only deletes naturally empty nodes (zero risk)
- 🔘 **Replace & Move**: Actively evicts pods to force emptiness

**Stabilization Window**:
- Input: Minutes (e.g., 10)
- Purpose: Prevents "flapping" (delete then immediately re-add)

#### Card 3: Smart Hibernation Schedule

**Timezone Selector**:
- Dropdown: `(UTC-05:00) America/New_York`

**Visual Weekly Planner** (24x7 Grid):
- 🟩 **Green**: Active (cluster runs normally)
- ⬜ **Grey**: Hibernating (0 nodes, pods paused)

**Excluded Resources**:
- Multi-select: Tags or Namespaces
- Example: `Keep running if tag env=critical`

**Manual Override**:
- Button: **[Wake Up for 2 Hours]**
- Use Case: Emergency hotfix deployment

### 5.2 Workload Layer (Tab B: Pod Tuning)

#### Card 1: Smart Pod Rightsizing (VPA)

**Operating Mode**:
- 🔘 **Off**: Disabled
- 🔘 **Recommendations Only**: Shows savings, no changes
- 🔘 **Automatic Apply**: Patches deployments with new values

**Safety Buffer**:
- Slider: [10% ---|--- 50%] (Default: 20%)
- Calculation: `If pod uses 100MB RAM, set limit to 120MB`

**Severity Threshold**:
- Dropdown: "Only apply if savings > $10/month"

#### Card 2: Spot Affinity & Deployment Rules

**Spot Preference Strategy**:
- 🔘 **Force Spot** (Hard): `nodeSelector: lifecycle=spot`
  - Pods ONLY run on Spot (stays Pending if none available)
- 🔘 **Prefer Spot** (Soft): `preferredDuringScheduling...`
  - Tries Spot first, falls back to On-Demand

**Burstable Instance Handling**:
- [Checkbox] "Block Burstable Instances (t3/t4g/t3a)"
- Reason: CPU credits can cause performance degradation

**Availability Zone Spread**:
- [Checkbox] "Enforce Multi-AZ High Availability"
- Adds `topologySpreadConstraints`

#### Card 3: Governance & Exemptions

**Namespace Exclusion List**:
- Multi-select: `kube-system`, `monitoring`, `payment-gateway`
- Impact: Never evict, resize, or move pods in these namespaces

**Label Selectors**:
- Key-Value pairs: `karpenter.sh/do-not-evict = true`

### 5.3 Visual Feedback

**Estimated Impact Badge**:
```
💰 Potential Savings: +$150/mo
```

**Unsaved Changes Bar** (Sticky footer):
```
You have unsaved changes. [Reset] [Save Policy]
```

---

## 6. Cluster Hibernation

**Location**: Sidebar → Cluster Hibernation

### 6.1 Command Center Header

**Live Status Indicator**:
- 🟢 **ACTIVE**: "Cluster is Running. Next sleep: Friday 8:00 PM"
- 💤 **HIBERNATING**: "Cluster is Sleeping. Savings rate: $12.50/hour"
- Countdown: "Time until wake up: 08h 12m"

**Manual Override (Panic Button)**:
- **[⚡ Wake Up Now]** or **[🛌 Hibernate Now]**
- Modal: "Keep awake for: [1 Hour | 4 Hours | Until Monday]"

**Savings Ticker**:
```
This Month's Savings: $4,250.00
```

### 6.2 Interactive Weekly Scheduler

**24-Hour x 7-Day Grid**:
- Click-and-drag to paint time blocks
- 🟩 Green: Active
- ⬜ Grey: Sleep
- 🟨 Yellow: Ramp Up (Pre-warming)

**Soft Start (Pre-Warming)**:
- [Checkbox] "Enable 30-minute Pre-warm"
- Logic: If work starts at 9:00 AM, boots at 8:30 AM
- Benefit: Cluster ready before developers login

### 6.3 Annual Calendar (Holidays & Exceptions)

**One-Click Holidays**:
- **[Import National Holidays]** button
- Auto-marks Christmas, Thanksgiving as Force Sleep

**Custom Overrides**:
- Click specific date (Nov 15th)
- Context Menu:
  - Set as Holiday (Sleep 24h)
  - Set as Sprint Day (Active 24h)

### 6.4 Advanced Configuration

**Targeting Scope**:
- 🔘 **Full Hibernation**: Scales ALL worker groups to 0
- 🔘 **Selective Hibernation**: Keep specific groups running
  - List: `[x] worker-spot`, `[ ] worker-databases`

**Critical Namespace Protection**:
- Multi-select: `monitoring`, `vault`
- Logic: "If node runs these pods, DO NOT terminate"

**Notification Integration**:
- Trigger: "Send alert 30 minutes before hibernation"
- Channel: Slack Webhook / Email
- Message: "⚠️ Dev-Cluster-01 going to sleep in 30 mins. [Snooze]"

---

## 7. Audit Logs & Compliance

**Location**: Sidebar → Audit Logs

### 7.1 The Audit Trail

**Data Grid Columns**:

| Column | Content | Example |
|--------|---------|---------|
| **Timestamp** | Millisecond precision | Oct 24, 14:32:01.455 UTC |
| **Actor** | User or System | Alice Admin / 🤖 Autoscaler Bot |
| **Event** | Human-readable summary | "Modified Hibernation Schedule" |
| **Target** | Affected resource | Cluster prod-us-east-1 / Node i-0123... |
| **Outcome** | Status badge | 🟢 Success / 🔴 Failed / 🟡 Denied |

**Deep Dive Drawer**:
- Click row → Slides out details panel
- **Before & After Diff**: "Changed Max Nodes from 10 → 15"
- **Metadata**: Source IP, User Agent, Request ID

### 7.2 Export & Reporting

**Export Controls**:
- Format: CSV (Excel) / JSON (SIEM)
- Time Range: Last 30 Days / Last Quarter / Custom
- **[⬇️ Download Audit Report]** button

**Immutable Checksums**:
- SHA-256 checksum generated for each export
- Purpose: Prove logs haven't been tampered with

### 7.3 Compliance Settings

**Data Retention Policy**:
- Slider: [30 Days ---|--- 1 Year ---|--- Indefinite]
- Warning: "Retaining logs > 1 year may incur storage fees"

**SIEM Integration** (Enterprise):
- Stream logs to external destination
- Configuration: Datadog API Key, Splunk HEC URL, AWS S3 Bucket

---

## 8. Multi-Cluster Command Center

**Location**: Sidebar → Clusters

### 8.1 Cluster Registry

#### Global Status Bar

| Metric | Description |
|--------|-------------|
| **Total Managed Clusters** | 45 |
| **Total vCPU / Memory** | 12,400 vCPU / 48 TB RAM |
| **Global Efficiency Score** | A-F grade (aggregated) |
| **Monthly Run Rate** | Total projected spend |
| **Critical Alerts** | Ticker: "3 Clusters have API High Latency" |

#### Smart Filter & Search

**Unified Search**: Filter by Name, ID, Tags, Region

**Quick Filter Pills**:
- Prod vs Dev
- Healthy vs Degraded
- EKS / GKE / AKS
- High Cost (Top 10% spenders)

#### Cluster Data Grid

**Columns**:

| Column | Visual | Interaction |
|--------|--------|-------------|
| **Cluster Identity** | Name + Provider Icon + Env Tag | Click → Detail Dashboard |
| **Region** | Flag icon + Code | Hover → AZ list |
| **K8s Version** | Version number | EOL warning badge |
| **Fleet Size** | Node/Pod count | Sparkline (24h trend) |
| **Financials** | Monthly cost + % savings | Trend arrow ⬆️⬇️ |
| **Health Score** | Circular gauge (0-100%) | Color-coded |
| **Compliance** | Shield icon | 🟢 CIS Compliant / 🔴 Violations |
| **Actions** | Manage button | Context menu |

#### Bulk Actions Toolbar

(Appears when rows selected):
- **Compare Clusters**: Side-by-side config analysis
- **Apply Policy**: Push template to multiple clusters
- **Upgrade Agent**: Batch update optimization agent

### 8.2 Add Cluster Wizard

**Step 1: Connection Method**
- **Option A**: Auto-Discovery (via Cloud Provider API)
- **Option B**: Manual Kubeconfig (upload file)
- **Option C**: Terraform/IaC (generates code snippet)

**Step 2: Discovery & Selection**
- Region Scanner: Select regions
- System lists "Unmanaged Clusters"
- Metadata Import: Auto-fetches tags (Team, Owner)

**Step 3: Agent Installation**
- **Helm Chart**: Copy-pasteable command
- **Direct Manifest**: `kubectl apply -f ...` URL
- **Pre-Flight Check**: Verifies IAM permissions

**Step 4: Connection Verification**
- Visual "Sonar" animation (waiting for heartbeat)
- Success: "14 Nodes Discovered"
- Options: "Configure Optimization Now" / "Go to Dashboard"

### 8.3 Cluster Detail View

**Header Area**:
- Breadcrumbs: `Clusters > production-us-east-1`
- Sync Status: "Last synced: 12s ago" + **[Sync Now]**
- **Maintenance Mode Toggle**: Pause all automation

#### Tab 1: Overview & Health
- **Topology Map**: Visual graph (Node Groups → Nodes)
- **Cost Burndown**: Actual spend vs budget
- **Alert Feed**: Active warnings

#### Tab 2: Node Groups & Capacity
- **Inventory Table**: Lists ASGs / Karpenter Provisioners
- Features:
  - Toggle Spot Mode per group
  - Set Min/Max limits
  - View Spot Readiness score

#### Tab 3: Workloads & Namespaces
- **Efficiency Report**: Namespaces by cost
- **Insight**: "Namespace analytics requesting 100 CPUs but using 12"
- **Top Spenders**: Most expensive Deployments/StatefulSets

#### Tab 4: Compliance & Drift
- **Drift Detection**: Compares state vs Node Templates
- **Security Scan**: CIS Benchmark results

---

## 9. Super Admin Console

> **⚠️ PLATFORM OWNER ONLY**: This interface is exclusively for internal SaaS staff. Clients NEVER see these screens.

### 9.1 Global Overview

**Business Metrics**:
- Total Managed Spend (Global)
- Total Savings Delivered
- Total Active Clients

**System Health Traffic Lights**:
- Database: 🟢 Healthy
- Redis: 🟢 Healthy
- Celery Workers: 🟡 Queue Depth > 500
- Scraper Health: 🟢 Healthy

### 9.2 Client Management

**Client Registry**:
- List of all customers
- Plan tiers (Free, Pro, Enterprise)

**Feature Flags (Access Control)**:
- Granular toggles per client:
  - `[x] Enable Bin Packing`
  - `[ ] Enable Hibernation`
  - `[x] Enable Multi-Account`

**Impersonation**:
- **[🔑 Log in as Client]** button
- Generates temporary JWT with client's Org ID
- Sticky banner: "⚠ Impersonating Acme Corp"
- Use Case: Customer support, debugging

**Admin Actions**:
- **[Reset Password]**: Sends email link
- **[Delete Client]**: Hard delete (with confirmation)

### 9.3 The Lab (AI Innovation Sandbox)

#### Feature A: Live Single-Instance Switcher

**Purpose**: Test physical node replacement on real infrastructure

**Workflow**:
1. Select target instance (e.g., `i-0abc...` running `m5.large`)
2. Select AI Model (e.g., `Spot-V2-Aggressive`)
3. Click **[⚡ Execute Live Switch]**

**Physical Process**:
```
1. Stop On-Demand instance
2. Detach EBS Data Volume
3. Request new Spot Instance (c5.large)
4. Attach original EBS Volume
5. Boot new node
```

**Real-Time Telemetry**:
```
Volume Detach Time: 4.2s ✓
New Instance Boot Time: 45s ✓
Total Downtime: 52s ✓
```

#### Feature B: Parallel Model Testing (A/B Test)

**Concept**: Run two AI models simultaneously on isolated instances

**Setup**:
- **Instance Group A**: Tag `model=stable` → Managed by "Production Model v1"
- **Instance Group B**: Tag `model=beta` → Managed by "Experimental Model v2"

**Isolation Logic**:
- Lab uses tag-based isolation (`env=lab-mode`)
- Production Optimizer ignores lab nodes
- Lab Models ignore production nodes

**Comparison Dashboard**:
- Side-by-side graphs
- Result: "Instance B switched 3 times, saved $4.50, had 2 min downtime"

#### Feature C: Model Graduation

**Model Registry**:
- List of uploaded `.pkl` / `.h5` files
- Metadata: Version, Upload Date, Test Results

**Promotion Workflow**:
1. Click **[🎓 Graduate to Production]**
2. Safety Checklist:
   - `[✅] Average Boot Time < 60s`
   - `[✅] Volume Attachment Success Rate 100%`
   - `[✅] Application Health Check passed`
3. Confirm → Hot-swaps global model for all clients

### 9.4 System Health & Infrastructure

**Component Status**:
- Database: Connection pool, query latency
- Cache (Redis): Hit rate, memory usage
- Workers (Celery): Queue depth, task success rate
- Scraper Health: Last successful run timestamp

**Live System Logs**:
- **[View Live Logs]** button
- WebSocket stream of backend output
- Filter by severity (INFO, WARNING, ERROR)

---

## 10. Backend Architecture

### 10.1 The Discovery Worker (The Scout)

**Role**: System "eyes"

**Frequency**: Every 5 minutes (configurable)

**Workflow**:
1. Wake Up: Check database for active Cloud Accounts
2. Scan: Call `EC2 DescribeInstances`, `EKS ListClusters`
3. Diff: Compare new state with previous database record
4. Update: Mark missing nodes as "Terminated", new as "Running"
5. Metric Fetch: Pull CPU/Memory from CloudWatch/Prometheus

### 10.2 The Optimizer Engine (The Brain)

**Role**: Decision maker

**Trigger**: After Discovery completes or manual "Optimize Now"

**Logic Flow**:
1. **Policy Check**: Read client's Optimization Policies
2. **Opportunity Detection**:
   - Spot Opportunity: On-Demand → Spot candidates
   - Waste Opportunity: Nodes < 20% utilization
3. **Risk Analysis**: Query AI Model for interruption probability
4. **Decision Output**: Generate "Action Plan"

### 10.3 The Action Executor (The Hands)

**Role**: Cloud interaction component

**Safety**: Only component allowed to write/delete

**Execution Strategy**:
1. **Drain**: Safe pod eviction (respects PodDisruptionBudgets)
2. **Launch**: Request new infrastructure (Spot Instance)
3. **Verify**: Wait for node to be `Ready` in Kubernetes
4. **Terminate**: Only delete old node once new one is taking traffic
5. **Audit**: Log success/failure to Audit Log

---

## 11. Notifications & Alerting

### 11.1 Notification Channels

**In-App Toast**:
- Small pop-ups for immediate actions
- Example: "Settings Saved ✓"

**Email Reports**:
- Weekly/Monthly summaries
- Example: "Total Savings this week: $350"

**Slack/Microsoft Teams Webhook**:
- Real-time operational alerts
- Example: "💤 Hibernation Active: Dev-Cluster-01 sleeping. Saved $40."

### 11.2 Alert Categories

**💰 Cost Alerts**:
- "Projected Bill exceeded $5,000"
- "Saved $100 in the last hour"

**⚠️ Risk Alerts**:
- "Spot Market Volatility detected in us-east-1"
- "Capacity Fallback: Moved to On-Demand due to stockout"

**💤 Schedule Alerts**:
- "Cluster Dev-Alpha going to sleep in 15 minutes"

---

## 12. Billing & Subscription

**Location**: Sidebar → Billing

### 12.1 Plan Management

**Tiers**:

| Tier | Nodes | Pricing | Features |
|------|-------|---------|----------|
| **Free** | Up to 3 | $0 | Basic optimization |
| **Pro** | Up to 50 | Flat fee + % of savings | Advanced policies |
| **Enterprise** | Unlimited | Custom pricing | SSO, Dedicated Support |

**Usage Visualization**:
```
Using 14 of 50 included nodes
[████████░░░░░░░░░░] 28%
```

### 12.2 Invoices & Payment Methods

**Stripe Integration**:
- **Add Card**: Secure input (PCI Compliant via Stripe Elements)
- **Invoice History**: Downloadable PDF invoices
- **Auto-Billing**: Monthly charges

---

## 13. Security & Compliance

### 13.1 Data Protection

**Encryption at Rest**:
- All sensitive fields (AWS Keys, Passwords) encrypted using AES-256
- Stored in database after encryption

**Encryption in Transit**:
- All API communication forced over TLS 1.3 (HTTPS)

### 13.2 Role-Based Access Control (RBAC)

**Location**: Settings → Team Members

**Roles**:

| Role | Permissions |
|------|-------------|
| **Owner** | Delete accounts, change billing |
| **Admin** | Change policies, hibernation schedules |
| **Viewer** | Read-only access (for auditors/managers) |

### 13.3 Compliance

**Audit Trail**:
- Every change logged (as described in Section 7)

**Least Privilege**:
- CloudFormation template requests only specific permissions
- Example: `ec2:Describe*`, `autoscaling:Update*`
- NOT full Admin access

**Certifications**:
- SOC2 compliant
- ISO 27001 ready
- HIPAA compatible (with Enterprise plan)

---

## Appendix: User Journey Examples

### Example 1: Day 0 - The "Aha!" Moment

1. User signs up with email/password
2. Onboarding wizard: Connects AWS via CloudFormation
3. Dashboard loads (30s wait)
4. **Pop!** Graphs fill with data
5. User sees: "Potential Savings: $1,400/mo"
6. **Hook**: "Wow, I'm wasting money!"

### Example 2: Day 1 - Configuration

1. User enables Karpenter (Capacity Optimized strategy)
2. Sets Hibernation schedule (Nights/Weekends = Grey)
3. Adds `kube-system` to Exclusion List
4. Clicks "Optimize Now" on test cluster
5. Watches Real-Time Feed: "Switched Node i-0x89... to Spot"

### Example 3: Day 7 - Automation

1. User is asleep (2:00 AM)
2. Discovery Worker runs every 5 min
3. Optimizer Engine detects waste
4. Dev Cluster enters Sleep Mode
5. User receives Slack: "💤 Saved $40 last night"
6. Monday email: "Total Savings: $350"

### Example 4: Day 30+ - Expansion

1. User sees Usage Bar: "48 of 50 Nodes" (Red)
2. Goes to Billing → Upgrades to Enterprise
3. Enters Credit Card (Stripe)
4. Creates "AI-Workloads" Node Template (GPU families)
5. Sets Spot Affinity for "Training" namespace to "Force Spot"
6. ML jobs now run on cheap Spot instances (70% savings)

---

## Technical Implementation Notes

### Database Schema

**Key Tables**:
- `users`: User accounts with hashed passwords
- `accounts`: AWS account connections
- `clusters`: Kubernetes cluster metadata
- `instances`: EC2 instance inventory
- `node_templates`: Saved configuration blueprints
- `cluster_policies`: Optimization rules (JSONB)
- `hibernation_schedules`: Weekly schedule matrix
- `audit_logs`: Immutable action history

### API Endpoints Summary

**Authentication**:
- `POST /api/auth/signup`
- `POST /api/auth/token`
- `POST /api/auth/logout`

**Client Operations**:
- `GET /api/client/clusters`
- `POST /api/clusters/connect`
- `PATCH /api/policies/karpenter`
- `POST /api/hibernation/schedule`
- `GET /api/audit`

**Admin Operations**:
- `GET /admin/clients`
- `POST /admin/impersonate`
- `POST /lab/live-switch`
- `POST /lab/graduate`
- `WS /admin/logs`

### Background Jobs (Celery)

**Scheduled Tasks**:
- `discovery_worker_loop`: Every 5 minutes
- `optimizer_engine`: After discovery or manual trigger
- `hibernation_checker`: Every 1 minute
- `weekly_report_generator`: Every Monday 9 AM

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-31  
**Status**: Production Ready
