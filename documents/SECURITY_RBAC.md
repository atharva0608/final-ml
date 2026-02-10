# Security & RBAC — Permissions Registry

> **Last Updated**: 2026-02-10
> **Total Protected Features**: 73+ (54 in JIT registry + 19 granular additions)
> **Naming**: Reflects Global Naming Synchronization

---

## 1. Role Hierarchy

```
SUPER_ADMIN (Platform Owner)
├── Full platform access, impersonation, billing
├── Never sees client sidebar (uses admin navigation)
└── Cannot be assigned to teams

ORG_ADMIN (Client Organization Owner)
├── All operations within own org
├── Bypasses JIT approval for own actions
├── Can approve any request in org
└── Manages automation settings

TEAM_LEAD
├── View operations: Immediate access
├── Write operations: Can approve for team members
├── Delete operations: Requires ORG_ADMIN approval
└── Scoped to own team's members and accounts

MEMBER (Read-Only Shadow Mode)
├── View operations: All *-view permissions
├── Write operations: Requires TEAM_LEAD approval (JIT)
└── Delete operations: Requires ORG_ADMIN approval (JIT)
```

---

## 2. Permission Matrix by Module

### 2.1 Infrastructure & Clusters

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View clusters | YES | YES | YES | YES |
| View cluster details | YES | YES | YES | YES |
| Connect AWS account | — | YES | YES | JIT |
| Disconnect AWS account | — | YES | JIT | JIT |
| Install agent | — | YES | YES | — |
| Disconnect cluster | — | YES | JIT | JIT |
| View nodes | YES | YES | YES | YES |

### 2.2 Compute Operations

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View instances | YES | YES | YES | YES |
| Terminate instance | — | YES | JIT | JIT |
| Stop instance | — | YES | JIT | JIT |
| Reboot instance | — | YES | JIT | JIT |
| Launch spot instance | — | YES | JIT | JIT |
| Modify ASG capacity | — | YES | JIT | JIT |

### 2.3 Storage Operations

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View volumes | YES | YES | YES | YES |
| Detach volume | — | YES | JIT | JIT |
| Delete volume | — | YES | JIT | JIT |
| Resize volume | — | YES | JIT | JIT |
| Edit S3 lifecycle | — | YES | JIT | JIT |
| Delete database | — | YES | JIT | JIT |

### 2.4 Resource Hygiene

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View scan results | YES | YES | YES | YES |
| Execute scan | — | YES | YES | JIT |
| Authorize resources | — | YES | YES | JIT |
| Execute cleanup action | — | YES | JIT | JIT |
| Manage hygiene policies | — | YES | — | — |

### 2.5 Governance & Tags

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View tag policies | YES | YES | YES | YES |
| Create/edit tag policies | — | YES | — | — |
| Delete tag template | — | YES | JIT | JIT |
| Edit bin-packing policy | — | YES | JIT | JIT |
| Toggle global automation | — | YES | — | — |
| Configure HITL | — | YES | — | — |

### 2.6 Team & User Management

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View team members | YES | YES | YES | YES |
| Invite members | — | YES | YES | — |
| Remove members | — | YES | YES | — |
| Promote to Team Lead | — | YES | — | — |
| Change roles | — | YES | — | — |

### 2.7 Approvals

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| View own requests | — | YES | YES | YES |
| Create access request | — | — | YES | YES |
| Approve requests | — | YES | YES (team) | — |
| Reject requests | — | YES | YES (team) | — |
| Revoke active access | — | YES | YES (team) | — |
| Bypass approval | — | YES | — | — |

### 2.8 Admin & Billing

| Action | SUPER_ADMIN | ORG_ADMIN | TEAM_LEAD | MEMBER |
|:-------|:--:|:--:|:--:|:--:|
| Admin dashboard | YES | — | — | — |
| Manage organizations | YES | — | — | — |
| Platform identity | YES | — | — | — |
| System health | YES | — | — | — |
| View billing | YES | YES | — | — |
| Edit billing | YES | YES | — | — |

---

## 3. JIT Privilege Escalation System

### 3.1 How It Works

1. **Member** clicks a protected button (shows lock icon)
2. **JITRequestModal** opens with pre-filled feature metadata
3. Member selects approver, duration, and provides reason
4. **Approval ticket** created (type: `JIT_FEATURE`)
5. **Team Lead** receives and approves/rejects
6. **Active Window Banner** shows countdown timer
7. Access **auto-expires** after duration

### 3.2 Ticket Types

| Type | Purpose | Auto-Triggered |
|:-----|:--------|:---------------|
| `ACCESS_WINDOW` | Time-boxed general access | On 403 with `required_ticket` |
| `ACTION` | Single action approval | On protected button click |
| `JIT_FEATURE` | Feature-specific JIT access | On ProtectedButton click |
| `SYSTEM_CLEANUP` | ML-initiated hygiene action | By automation engine |

### 3.3 Approval Status Flow

```
PENDING → PENDING_CONSENT → APPROVED_ACTIVE → EXPIRED
                                             → REVOKED
```

### 3.4 Reason Categories

`MAINTENANCE` | `INCIDENT` | `DEPLOYMENT` | `DEBUGGING` | `AUDIT` | `OTHER`

### 3.5 Delegation

Grants support hierarchy via `parent_id` for delegated access chains.

---

## 4. Feature Registry (73+ Features)

### Categories & Feature IDs

| Category | Feature ID | Display Name | Risk | Max Duration |
|:---------|:-----------|:-------------|:-----|:-------------|
| **Cloud** | `feat-account-add` | Link AWS Account | HIGH | 4h |
| | `feat-account-remove` | Disconnect AWS Account | CRITICAL | 2h |
| | `feat-iam-reverify` | Validate Credentials | LOW | — |
| | `feat-cluster-deregister` | Deregister Cluster | MEDIUM | 4h |
| **Compute** | `feat-instance-terminate` | Terminate Instance | HIGH | 2h |
| | `feat-instance-reboot` | Reboot Instance | MEDIUM | 4h |
| | `feat-instance-stop` | Stop Instance | MEDIUM | 4h |
| | `feat-instance-launch-spot` | Manual Spot Launch | MEDIUM | 4h |
| | `feat-asg-scale` | Update ASG Capacity | HIGH | 4h |
| **Storage** | `feat-ebs-detach` | Detach Volume | MEDIUM | 4h |
| | `feat-ebs-delete` | Delete Unattached Volume | HIGH | 2h |
| | `feat-ebs-resize` | Modify Volume | MEDIUM | 4h |
| | `feat-s3-policy-edit` | Update S3 Lifecycle Policy | MEDIUM | 4h |
| **Hibernation** | `feat-hibernation-create` | Set New Schedule | MEDIUM | 8h |
| | `feat-hibernation-toggle` | Enable/Disable Schedule | MEDIUM | 8h |
| | `feat-hibernation-override` | Manual Wake/Sleep | MEDIUM | 4h |
| **Governance** | `feat-automation-master-toggle` | Toggle Global Automation | CRITICAL | 2h |
| | `feat-automation-approval-config` | Configure HITL | HIGH | 4h |
| | `feat-policy-binpack-update` | Edit Bin-Packing | MEDIUM | 8h |
| | `feat-tag-template-delete` | Delete Tag Template | LOW | 8h |
| | `feat-team-lead-assign` | Promote to Team Lead | HIGH | 4h |
| **Lab** | `feat-lab-live-switch` | Execute Live Switch | CRITICAL | 1h |
| | `feat-model-promote` | Promote ML Model | CRITICAL | 1h |
| **Hygiene** | `hygiene:execute` | Execute Hygiene Actions | HIGH | 4h |
| | `hygiene:scan` | Run Hygiene Scan | LOW | — |
| **Approval** | `approval:approve` | Approve Requests | MEDIUM | — |
| | `approval:reject` | Reject Requests | LOW | — |
| | `approval:bypass` | Bypass Approval | CRITICAL | 1h |

Plus **30+ view/read features** (always granted to all roles, no JIT required).

---

## 5. Backend Permission Enforcement

### 5.1 PermissionService

```python
from backend.services.permission_service import PermissionService

perm_service = PermissionService(db)
perm_service.enforce(user, "hygiene:execute", resource_id)
# Raises GovernanceError with rich details if denied
```

### 5.2 GovernanceError Response (HTTP 403)

```json
{
  "detail": "Permission denied",
  "required_ticket": true,
  "feature_id": "hygiene:execute",
  "feature_name": "Execute Hygiene Actions",
  "risk_level": "HIGH",
  "max_duration_hours": 4,
  "approver_roles": ["TEAM_LEAD", "ORG_ADMIN"]
}
```

### 5.3 Frontend Auto-Intercept

The API interceptor in `api.js` catches 403 responses with `required_ticket: true` and dispatches a custom `governance:required` browser event, which auto-opens the `TicketRequestModal`.

---

## 6. Frontend Protected Components

### ProtectedButton

```jsx
<ProtectedButton
  featureId="feat-ebs-delete"
  resourceId={volume.id}
  onClick={handleDelete}
>
  Delete Volume
</ProtectedButton>
```

- Shows **lock icon** when permission denied
- Opens **JITRequestModal** on click
- Shows **normal button** when access is active

### usePermission Hook

```javascript
const { hasPermission, loading, feature, ticket, expiresAt } = usePermission(featureId, resourceId);
```

---

## 7. AWS Cross-Account Security

### IAM Role Template

The CloudFormation template (`backend/templates/aws/`) creates a cross-account IAM role with:

| Control | Implementation |
|:--------|:---------------|
| **Confused Deputy Prevention** | `ExternalId` condition on trust policy |
| **Minimal Permissions** | SecurityAudit, EC2ReadOnly, CloudWatch managed policies |
| **Tag-Conditioned Cleanup** | `ec2:TerminateInstances` only when `tag:ManagedBy = SpotOptimizer` |
| **EKS Discovery** | `eks:ListClusters`, `eks:DescribeCluster`, `eks:ListNodegroups` |
| **Cost Analysis** | `ce:GetCostAndUsage`, `pricing:GetProducts` |

### Agent Authentication

- Each cluster gets unique **API key** stored in Kubernetes Secret
- Validated on every heartbeat and WebSocket connection
- RBAC: Agent ServiceAccount has minimal permissions (read nodes/pods, delete pods, create jobs)

---

## 8. Audit Trail

Every action is logged to `audit_logs` table:

| Field | Content |
|:------|:--------|
| `actor` | User ID or "SYSTEM" |
| `action` | Human-readable description |
| `target` | Resource ID |
| `outcome` | SUCCESS / FAILED / DENIED |
| `metadata` | Before/after diff, source IP, request ID |
| `timestamp` | Millisecond precision |

JIT-specific audit fields: who requested, who approved, feature accessed, when expired, actions taken during window.

---

## 9. Security Best Practices

| Practice | Implementation |
|:---------|:---------------|
| **Default Deny** | All new users start with 0 permissions |
| **Time-Bound Access** | All JIT tickets auto-expire; no permanent elevation |
| **Encryption at Rest** | AWS keys encrypted with AES-256 (Fernet) |
| **Encryption in Transit** | TLS 1.3 for all API, WSS for WebSocket |
| **JWT Security** | Access: 60 min, Refresh: 30 days, configurable |
| **Scope Isolation** | All queries filtered by `organization_id` |
| **No Permanent Elevation** | Max duration enforced by feature registry |

---

**Last Updated**: 2026-02-10
