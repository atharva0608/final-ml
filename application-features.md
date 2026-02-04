# Application Feature Catalog

This document provides a comprehensive inventory of the Spot Optimizer platform's features, including active capabilities, hidden "zombie" code, and implementation details.

## 1. Feature Catalog

### Legend
*   **Status**:
    *   🟢 **Active**: Fully implemented and exposed in UI.
    *   🟡 **Partial**: Backend exists but UI is incomplete/mocked.
    *   🔴 **Hidden**: Fully implemented backend but no UI exposure.
    *   🧟 **Zombie**: Deprecated, redundant, or unused code.
*   **Roles**: **SA** (Super Admin), **OA** (Org Admin), **TL** (Team Lead), **MB** (Member).

| Category | Feature | Status | Description & Logic | SA | OA | TL | MB |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **Authentication** | **Login / Validation** | 🟢 | Email/Password auth. JWT (Access 15m / Refresh 7d). | ✅ | ✅ | ✅ | ✅ |
| | **User Invite** | 🟢 | SendGrid-integrated email invites. Token-based signup link. | ✅ | ✅ | ✅ | ❌ |
| | **RBAC Engine** | 🟢 | Middleware-enforced checks (`RequireRole`, `RequireAccess`). | ✅ | ✅ | ✅ | ✅ |
| **Cluster Management** | **Hybrid Discovery** | 🟢 | Cross-account IAM Role assumption to list EKS clusters. | ✅ | ✅ | ❌ | ❌ |
| | **Agent Injection** | 🟢 | **DaemonSet** deployment via `discovery.py` worker. | ✅ | ✅ | ❌ | ❌ |
| | **Cost Insights** | 🟢 | Fetches `ce:GetCostAndUsage` from AWS upon discovery. | ✅ | ✅ | ✅ | ✅ |
| | **Health Monitoring** | 🟢 | Agent heartbeat tracking. Status updates to `DISCONNECTED` after timeout. | ✅ | ✅ | ✅ | ✅ |
| **Optimization** | **Spot Scaling** | 🟢 | `metrics_service.py` analysis. Replaces On-Demand with Spot. | ✅ | ✅ | ❌ | ❌ |
| | **Bin Packing** | 🟢 | Node Template policy matching. Ensures pods fit efficiently. | ✅ | ✅ | ❌ | ❌ |
| | **Hibernation** | 🟢 | Cron-based cluster sleep schedules (`hibernation_routes.py`). | ✅ | ✅ | ❌ | ❌ |
| | **S3 Tiering** | 🟡 | `s3_routes.py` active. **UI mocks bucket list** (Missing List Endpoint). | ✅ | ✅ | ❌ | ❌ |
| | **RDS Rightsizing** | 🟢 | `rds_routes.py` active. Multi-AZ idle detection. | ✅ | ✅ | ❌ | ❌ |
| **Governance** | **Org Policies** | 🟢 | `governance_routes.py`. Global constraints (e.g., "Require Tags"). | ✅ | ✅ | ❌ | ❌ |
| | **Tag Automation** | 🟢 | `auto_tag_routes.py`. Dynamic rules (User, Team, CostCenter). | ✅ | ✅ | ❌ | ❌ |
| | **Audit Logging** | 🟢 | `audit_routes.py`. Logs every Write action (POST/PUT/DELETE). | ✅ | ✅ | ✅ | ❌ |
| **Advanced** | **Chaos Experiments** | 🔴 | `lab_routes.py` mounted but **Hidden**. Stress testing capabilities. | ✅ | ✅ | ❌ | ❌ |
| | **RI Analysis** | 🟢 | `ri_routes.py`. Reserved Instance coverage analysis. | ✅ | ✅ | ❌ | ❌ |
| | **Data Transfer** | 🟢 | `transfer_routes.py`. Analyze VPC Peering/NAT costs. | ✅ | ✅ | ❌ | ❌ |

---

## 2. Zombie & Redundant Code Analysis

These features exist in the codebase but are flagged for cleanup or repair.

| Component | Diagnosis | File Path | Recommendation | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **Smart Tags** | 🧟 **Redundant** | `backend/api/smart_tag_routes.py` | **Delete** | Overlaps with `auto_tag_routes.py` (Rule Engine). Smart Tags appears to be a legacy implementation. |
| **S3 List** | 🟡 **Missing** | `backend/api/s3_routes.py` | **Fix** | API has `get_overview` (aggregate) but lacks `get_bucket_list`. Frontend `S3Analysis.jsx` is forced to mock this data. |
| **Chaos Labs** | 🔴 **Hidden** | `backend/api/lab_routes.py` | **Expose** | Fully functional Chaos Engineering routes are mounted in `api_gateway.py`. Just needs a UI tab. |
| **Transfer UI** | 🟡 **Partial** | `frontend/src/components/transfer` | **Wire Up** | Frontend exists, Backend `transfer_routes.py` exists (1.5KB). Needs verification of data binding. |
| **Governance** | ⚠️ **Confusing** | `governance_routes.py` | **Refactor** | Distinct from `policy_routes.py` (Cluster Optim), but name is ambiguous. Rename to `Compliance`? |

---

## 3. Detailed Logic Specifications

### A. Hybrid Discovery & Cost (The "Magic" Link)
1.  **Trust Establishment:** User provides AWS Role ARN.
2.  **Validation:** `account_service.py` verifies STS `assume_role` capability.
3.  **Discovery Job:**
    *   Worker `discovery.py` lists EKS clusters.
    *   **Cost Fetch:** Calls AWS Cost Explorer (`ce`) for simple monthly spend.
    *   **Savings Calc:** Applies heuristic (e.g., 40% Spot savings) to estimate potential.
    *   **DB Update:** Stores `monthly_cost` and `estimated_savings` on Cluster model.
4.  **Injection:** User clicks "Activate". Backend creates EKS Access Entry and deploys `DaemonSet`.

### B. Auto-Tagging Engine
1.  **Rule Creation:** Admin defines "If Resource matches X, Add Tag Y".
2.  **Preview:** `auto_tag_service.py` allows dry-run against live AWS account.
3.  **Execution:** Background worker applies tags via AWS Resource Groups Tagging API.
4.  **Zombie Check:** `smart_tag_service.py` has similar logic but less flexible.

### C. Governance vs. Policies
| Logic | Governance (`governance_routes`) | Policies (`policy_routes`) |
| :--- | :--- | :--- |
| **Scope** | Organization Wide | Specific Cluster / Node Group |
| **Goal** | Compliance / Audit | performance / Cost Optimization |
| **Examples** | "Require 'Owner' Tag", "Manual Approval for Deletes" | "Use 50% Spot", "Use t3.medium" |
| **Enforcement**| Pre-Action Check | Continuous Optimization Loop |

## 4. Middleware & Infrastructure
*   **CORS:** Configured in `api_gateway.py`. Allows dynamic origin whitelisting.
*   **Request Logging:** Custom middleware logs Method, Path, Status, Duration, and UserID.
*   **Exception Handling:** Global handlers for `SpotOptimizerException`, `Validation`, and 500s.
*   **Rate Limiting:** **MISSING**. No rate limiting middleware observed in `api_gateway.py`.
*   **Health Checks:** `/health` (Basic) and `/health/detailed` (DB + Redis connectivity).
