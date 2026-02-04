# Application Feature Catalog

This document provides a comprehensive list of all non-code features, their underlying logic, role-based access control, and an analysis of "Zombie" features (implemented but unused).

## 1. Feature Catalog

### Legend - Role Access
- **SA**: Super Admin (Platform Owner)
- **OA**: Organization Admin (Customer Admin)
- **TL**: Team Lead
- **MB**: Member (Read-Only/Standard)

| Category | Feature | Description & Logic | SA | OA | TL | MB |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Authentication** | **Login** | Users authenticate via Email/Password. JWT (Access + Refresh) tokens issued. Supports "Keep me signed in". | ✅ | ✅ | ✅ | ✅ |
| | **Signup** | New organization registration. Creates Org, Default Account, and Org Admin user. | N/A | ✅ | ❌ | ❌ |
| | **Password Reset** | Self-service password reset via email link (SendGrid/SMTP integration). | ✅ | ✅ | ✅ | ✅ |
| | **Invite User** | Admin invites new users by email. Generates secure token. Enforces password reset on first login. | ✅ | ✅ | ✅ | ❌ |
| **Cluster Management** | **List Clusters** | View all standard & discovered clusters. Shows CPU/Mem usage, Node counts, and Cost/Savings metrics. | ✅ | ✅ | ✅ | ✅ |
| | **Connect Cluster (Hybrid)** | Connect AWS Account -> Auto Discovery -> One-Click Agent Injection. Uses `discovery.py` worker. | ✅ | ✅ | ❌ | ❌ |
| | **Manual Connect** | Generate `curl` install script for manual agent installation on any K8s cluster. | ✅ | ✅ | ❌ | ❌ |
| | **Cluster Details** | Deep dive into a specific cluster: Nodes, Pods, Namespaces cost breakdown. | ✅ | ✅ | ✅ | ✅ |
| | **Disconnect/Remove** | Uninstall agent or remove cluster from dashboard (sets status to `DISCONNECTED`/`INACTIVE`). | ✅ | ✅ | ❌ | ❌ |
| **Cost & Insights** | **Main Dashboard** | High-level KPIs: Total Savings, Active Clusters, Monthly Spend, Rightsizing Opportunities. | ✅ | ✅ | ✅ | ✅ |
| | **Cost Analysis** | Time-series graphs of EC2/EKS spend. Filters by Region, Cluster, or Tag. Fetched via AWS Cost Explorer. | ✅ | ✅ | ✅ | ✅ |
| | **Resource Hygiene** | Scan for wasted resources (Unattached EBS, Old Snapshots, Idle ELBs). | ✅ | ✅ | ❌ | ❌ |
| **Optimization** | **Rightsizing** | Recommendations to move workloads to smaller/different instances based on utilization metrics. | ✅ | ✅ | ❌ | ❌ |
| | **Spot Scaling** | Replace On-Demand nodes with Spot Instances. Auto-injection of Spot configuration. | ✅ | ✅ | ❌ | ❌ |
| | **Hibernation** | Schedule clusters to sleep during off-hours (e.g., Weekends). Cron-based scheduler. | ✅ | ✅ | ❌ | ❌ |
| | **S3 Integration** | Analyze S3 buckets for Intelligent Tiering opportunities. Moves data to cheaper storage classes. | ✅ | ✅ | ❌ | ❌ |
| | **RDS Optimization** | Analyze RDS instances for Multi-AZ redundancy waste or idle instances. | ✅ | ✅ | ❌ | ❌ |
| **Governance** | **Policy Management** | Define constraints (e.g., "Max Node Cost", "Allowed Regions"). Enforced via OPA or logic checks. | ✅ | ✅ | ❌ | ❌ |
| | **Audit Logs** | Immutable record of all actions (Who, What, When). Critical for compliance. | ✅ | ✅ | ✅ | ❌ |
| **Settings** | **Cloud Integrations** | Link AWS Accounts via CloudFormation (Cross-Account Role). Validation of role permissions. | ✅ | ✅ | ❌ | ❌ |
| | **Team Management** | Create Teams, assign Users, set Budgets/Quotas per team. | ✅ | ✅ | ✅ | ❌ |
| | **Profile Settings** | Update Name, Email, Theme Preferences (Dark/Light). | ✅ | ✅ | ✅ | ✅ |
| **Admin** | **Client Management** | View all Organizations, Toggle Active/Inactive status, View Platform Stats. | ✅ | ❌ | ❌ | ❌ |
| | **Platform Health** | Monitor System Health (Database, Redis, Celery Workers status). | ✅ | ❌ | ❌ | ❌ |

---

## 2. Zombie Features Analysis

These are features found in the codebase that appear to be **implemented logic-wise** but are either disconnected, incomplete, or not currently exposed to the user.

| Feature / Component | Status | Description | Recommendation | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **Lab / Chaos Experiments** | `Implemented` (Logic Exists) | `backend/api/lab_routes.py` and `models/lab_experiment.py` exist. Intended for running chaos experiments (stress tests) on clusters. | **Keep** (Future) | Differentiator feature. Logic is complex and valuable, better to hide than delete. |
| **Data Transfer Opt** | `Partial` (Frontend Only?) | `frontend/src/components/transfer/TransferAnalysis.jsx` exists. Backend logic for analyzing VPC peering/NAT Gateway costs seems thin. | **Connect** | High value for users. If backend support is missing, add `transfer_routes.py`. |
| **S3 Detailed List** | `Partial` | `S3Analysis.jsx` mocks the detailed bucket list because the backend endpoint `/api/v1/s3/overview` only returns aggregated stats. | **Fix** | User expects to click "Analyze" and see *which* buckets need help. Add list endpoint. |
| **Smart Tags** | `Zombie` | `backend/api/smart_tag_routes.py` exists. Logic for auto-tagging resources based on usage patterns. | **Review** | Logic might be outdated or overlapping with "Auto Tags". Verify before exposing. |
| **RI / Savings Plans** | `Implemented` | `backend/api/ri_routes.py` and frontend exist. Handles Reserved Instance analysis. | **Keep** | High value feature. Ensure navigation menu links to it. |
| **Transfer Routes** | `Existing` | `backend/api/transfer_routes.py` exists (1463 bytes), so backend logic IS there. | **Verify** | Frontend might not be calling it correctly, or feature is hidden in UI. |
| **Governance Routes** | `Zombie?` | `backend/api/governance_routes.py` exists. Might overlap with `policy_routes.py`. | **Consolidate** | "Governance" and "Policies" are often the same. Check for duplicate logic. |
| **Tag Templates** | `Advanced` | `tag_template_routes.py`. Allows enforcing tag schemas. | **Expose** | Useful for enterprises. Ensure strictly Org Admins can access. |

## 3. Implementation Logic (Key Features)

### Cluster Connection (Hybrid)
1.  **Link AWS:** User adds AWS Role ARN.
2.  **Discovery:** `discovery.py` worker scans `eks.list_clusters`.
3.  **Insights:** Worker calls `ce.get_cost_and_usage` to populate `monthly_cost`.
4.  **Inject:** User clicks "Activate".
    *   Backend assumes role via STS.
    *   Creates EKS Access Entry.
    *   Connects to K8s API.
    *   Deploys `DaemonSet` (spot-agent).

### Optimization Engine
1.  **Collection:** Agent collects metrics (CPU/Mem) -> Backend `metrics_service.py`.
2.  **Analysis:** `optimization_service.py` compares Real Usage vs. Requests.
3.  **Recommendation:**
    *   If `Max(Usage) < 40% requested` -> Downsize.
    *   If `Spot Available` & `Workload Tolerant` -> Recommend Spot.
    *   If `Node Empty` -> Terminate.

### Cost Analysis
1.  **Ingest:** `cost_service.py` pulls from AWS Cost Explorer Daily.
2.  **Attribute:** Maps costs to Clusters via Tags (`eks:cluster-name`).
3.  **Forecast:** Simple linear regression or `ce.get_cost_forecast` for future spend.

