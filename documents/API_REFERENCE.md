# API Reference — Endpoint Catalog

> **Last Updated**: 2026-02-10
> **Total Endpoints**: 100+
> **Base URL**: `/api/v1`
> **Auth**: JWT Bearer token (unless noted)
> **Naming**: Reflects Global Naming Synchronization

---

## 1. Authentication (`/auth`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `POST` | `/auth/signup` | No | Register user + create organization |
| `POST` | `/auth/login` | No | Authenticate, return JWT access + refresh tokens |
| `POST` | `/auth/refresh` | Refresh Token | Issue new access token |
| `GET` | `/auth/me` | Yes | Current user profile |
| `PATCH` | `/auth/password` | Yes | Change password |
| `POST` | `/auth/invitation-response` | Yes | Accept/decline team invitation |

**Example — Login**:
```
POST /api/v1/auth/login
Body: { "email": "user@example.com", "password": "..." }
Response: { "access_token": "...", "refresh_token": "...", "user": { "id", "email", "role", "organization_id" } }
```

---

## 2. Organizations & Teams (`/organization`, `/teams`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/organization/members` | Yes | List org members |
| `POST` | `/organization/invite` | ORG_ADMIN | Invite member |
| `GET` | `/organization/connection-info` | Yes | Org external ID for CloudFormation |
| `GET` | `/teams` | Yes | List teams |
| `POST` | `/teams` | ORG_ADMIN | Create team |
| `GET` | `/teams/{id}` | Yes | Team details with members |
| `GET/PUT` | `/teams/{id}/governance` | ORG_ADMIN | Team-specific governance config |
| `POST` | `/teams/{id}/invite` | TL+ | Invite user to team |
| `POST` | `/teams/{id}/remove` | TL+ | Remove member from team |

---

## 3. AWS Accounts (`/accounts`, `/onboarding`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/accounts` | Yes | List accounts (RBAC-filtered) |
| `POST` | `/accounts/link` | OA+ | Link new AWS account |
| `POST` | `/accounts/{id}/validate` | OA+ | Verify STS assume-role |
| `POST` | `/accounts/{id}/set-default` | OA+ | Set as default account |
| `POST` | `/accounts/{id}/disconnect` | OA+ | Remove credentials, keep history |
| `GET` | `/onboarding/template` | Yes | CloudFormation template URL |
| `POST` | `/onboarding/aws-link` | Yes | Start onboarding with account |
| `POST` | `/onboarding/verify` | Yes | Verify connection + trigger discovery |
| `POST` | `/onboarding/reset` | Yes | Reset onboarding state |

---

## 4. Clusters (`/clusters`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/clusters` | Yes | Paginated cluster list (Redis cached 30s) |
| `GET` | `/clusters/{id}` | Yes | Cluster detail with instances |
| `POST` | `/clusters/{id}/auto-install` | OA+ | Trigger agent injection (async) |
| `GET` | `/clusters/{id}/install-script` | OA+ | Get Helm install command |
| `POST` | `/clusters/{id}/verify-install` | OA+ | Verify agent connection |
| `POST` | `/clusters/{id}/disconnect` | OA+ | Remove agent, mark disconnected |

---

## 5. Metrics (`/metrics`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/metrics/dashboard` | Yes | Dashboard KPIs (cost, savings, fleet) |
| `GET` | `/metrics/cost` | Yes | Cost time series |
| `GET` | `/metrics/instances` | Yes | Instance-level utilization |
| `GET` | `/metrics/time-series` | Yes | Custom time range metrics |
| `GET` | `/metrics/teams/{id}/summary` | Yes | Consolidated team stats |
| `GET` | `/metrics/accounts/{id}/summary` | Yes | Per-account breakdown |

---

## 6. Resource Hygiene (`/hygiene`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/hygiene/scan/{account_id}` | Yes | Scan resources (11 types, parallel, cached) |
| `POST` | `/hygiene/check-dependencies` | Yes | Pre-flight dependency mapping |
| `POST` | `/hygiene/action` | JIT | Execute cleanup (202 if approval required) |
| `POST` | `/hygiene/authorize` | JIT | Mark resource as authorized |
| `POST` | `/hygiene/unauthorize` | JIT | Remove authorization |
| `GET` | `/hygiene/discover` | JIT | Discover resources in active JIT window |

**Query Parameters for scan**:
- `regions` (array) — specific regions or omit for all
- `force_refresh` (bool) — bypass Redis cache

---

## 7. Hygiene Policies (`/hygiene-policies`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/hygiene-policies` | OA+ | List automated cleanup rules |
| `POST` | `/hygiene-policies` | OA+ | Create cleanup policy |
| `PUT` | `/hygiene-policies/{id}` | OA+ | Update policy |
| `DELETE` | `/hygiene-policies/{id}` | OA+ | Delete policy |

---

## 8. Approvals (`/approvals`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `POST` | `/approvals/create` | Yes | Create access/action ticket |
| `POST` | `/approvals/jit-request` | Yes | Create JIT feature access request |
| `GET` | `/approvals/my-requests` | Yes | List user's own tickets |
| `GET` | `/approvals/my-jit-tickets` | Yes | List active JIT tickets |
| `GET` | `/approvals/active-window` | Yes | Current active access window |
| `POST` | `/approvals/{id}/approve` | TL+ | Approve request |
| `POST` | `/approvals/{id}/reject` | TL+ | Reject request |
| `POST` | `/approvals/{id}/revoke` | TL+ | Revoke active access |
| `POST` | `/approvals/{id}/delegate` | TL+ | Delegate access grant |
| `POST` | `/approvals/{id}/accept` | Yes | Accept delegated grant |

---

## 9. Permissions (`/permissions`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `POST` | `/permissions/check` | Yes | Non-blocking permission check |
| `GET` | `/permissions/my-features` | Yes | List accessible features |
| `GET` | `/permissions/feature-registry` | Yes | Complete 73+ feature catalog |
| `POST` | `/permissions/{user_id}/revoke` | OA+ | Admin revoke user access |

**Example — Permission Check**:
```
POST /api/v1/permissions/check
Body: { "feature_id": "hygiene:execute", "resource_id": "vol-123" }
Response: { "allowed": false, "feature": { "name": "Execute Hygiene Actions", "risk_level": "HIGH", "max_duration_hours": 4 }, "ticket": null }
```

---

## 10. Governance (`/governance`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/governance/rules` | OA+ | Organization governance rules |
| `PATCH` | `/governance/rules` | OA+ | Update rules |
| `POST` | `/governance/run-autopilot` | OA+ | Execute automated governance |
| `GET` | `/governance/compliance` | Yes | Tag compliance status |

---

## 11. Tagging (`/tags/*`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/tags/management/{resource_id}` | Yes | Get tags for resource |
| `PUT` | `/tags/management/{resource_id}` | JIT | Update tags |
| `POST` | `/tags/management/bulk` | JIT | Bulk tag resources |
| `GET` | `/tags/templates` | Yes | List tag templates |
| `POST` | `/tags/templates` | OA+ | Create template |
| `GET` | `/tags/policies` | Yes | List tag policies |
| `POST` | `/tags/policies` | OA+ | Create policy |
| `GET` | `/tags/policies/compliance/stats` | Yes | Compliance stats (stubbed) |
| `GET` | `/tags/rules` | OA+ | List auto-tag rules |
| `POST` | `/tags/rules` | OA+ | Create auto-tag rule |
| `POST` | `/tags/rules/preview` | OA+ | Preview rule output |
| `POST` | `/tags/rules/test` | OA+ | Test rule against resources |
| `POST` | `/tags/rules/execute` | OA+ | Execute rule |
| `GET` | `/tags/rules/variables` | OA+ | Available dynamic variables |
| `POST` | `/tags/smart/process` | OA+ | Process TTL/schedule tags |

---

## 12. Optimization & Policies (`/optimization`, `/policies`, `/templates`, `/hibernation`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/optimization/rightsizing/{id}` | Yes | Rightsizing recommendations |
| `GET` | `/policies/{cluster_id}` | Yes | Get cluster policy |
| `POST` | `/policies` | OA+ | Create/update policy |
| `GET` | `/templates` | Yes | List node templates |
| `POST` | `/templates` | OA+ | Create template |
| `PUT` | `/templates/{id}` | OA+ | Update template |
| `DELETE` | `/templates/{id}` | OA+ | Delete template |
| `GET` | `/hibernation` | Yes | List schedules |
| `POST` | `/hibernation` | JIT | Create schedule |
| `PUT` | `/hibernation/{id}` | JIT | Update schedule |
| `DELETE` | `/hibernation/{id}` | JIT | Delete schedule |
| `POST` | `/hibernation/schedules/{id}/override` | Yes | Manual wake/sleep override |
| `GET` | `/hibernation/strategies` | No | Strategy comparison data |

---

## 13. Cost Analysis (`/ri`, `/s3`, `/rds`, `/transfer`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/ri/overview` | Yes | RI utilization overview |
| `GET` | `/ri/list` | Yes | RI list |
| `GET` | `/ri/recommendations` | Yes | RI purchase recommendations |
| `POST` | `/ri/analysis` | Yes | Run RI analysis |
| `GET` | `/ri/unified-coverage` | Yes | Combined RI + Savings Plans coverage |
| `GET` | `/s3/overview` | Yes | S3 cost overview |
| `POST` | `/s3/analyze` | Yes | S3 tiering analysis |
| `GET` | `/rds/overview` | Yes | RDS cost overview |
| `GET` | `/rds/top-opportunities` | Yes | Top RDS savings opportunities |
| `GET` | `/transfer/overview` | Yes | Data transfer cost overview |
| `GET` | `/transfer/top-opportunities` | Yes | Top transfer savings |

---

## 14. Admin (`/admin`)

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/admin/dashboard` | SA | Platform stats (MRR, users, clusters) |
| `GET` | `/admin/clients` | SA | All organizations |
| `POST` | `/admin/organizations/{id}/toggle` | SA | Suspend/activate org |
| `GET` | `/admin/health` | SA | Detailed system health |
| `GET` | `/admin/platform/connection` | SA | Platform AWS identity status |
| `POST` | `/admin/platform/connect` | SA | Set platform AWS credentials |
| `DELETE` | `/admin/platform/disconnect` | SA | Remove platform credentials |

---

## 15. Other Endpoints

| Method | Path | Auth | Description |
|:-------|:-----|:-----|:------------|
| `GET` | `/health` | No | Basic health check |
| `GET` | `/health/detailed` | SA | DB + Redis + Celery + AWS + data freshness |
| `GET` | `/audit/logs` | Yes | Audit log queries |
| `GET` | `/audit/export` | OA+ | Export audit data (stubbed) |
| `GET` | `/roles` | Yes | List roles |
| `POST` | `/roles` | OA+ | Create custom role |
| `GET` | `/roles/permissions-matrix` | Yes | Role-permission matrix |
| `GET` | `/lab/experiments` | SA | List experiments |
| `POST` | `/lab/experiments` | SA | Create experiment |
| `GET` | `/lab/models` | SA | List ML models |
| `POST` | `/lab/live-switch` | SA | Execute live instance switch |
| `POST` | `/lab/graduate` | SA | Promote model to production |
| `GET/PUT` | `/users/me/preferences` | Yes | Dashboard layout preferences |
| `GET` | `/billing/status` | OA+ | Subscription status |
| `POST` | `/billing/create-portal-session` | OA+ | Stripe billing portal |
| `POST` | `/billing/webhook/stripe` | No | Stripe webhook |
| `POST` | `/agents/heartbeat` | Agent API Key | Agent heartbeat |
| `POST` | `/agent-metrics/batch` | Agent API Key | Batch metrics upload |
| `GET` | `/installer/{cluster_id}` | No | Public installer endpoint |

---

## 16. Common Response Patterns

### Success
```json
{ "data": { ... }, "message": "OK" }
```

### Pagination
```json
{ "items": [...], "total": 100, "page": 1, "page_size": 20 }
```

### Error
```json
{ "detail": "Error message", "status_code": 400 }
```

### Governance Required (403)
```json
{
  "detail": "Permission denied",
  "required_ticket": true,
  "feature_id": "hygiene:execute",
  "feature_name": "Execute Hygiene Actions",
  "risk_level": "HIGH",
  "max_duration_hours": 4
}
```

### Approval Pending (202)
```json
{ "status": "pending_approval", "ticket_id": "uuid", "message": "Approval required" }
```

---

**Auth Legend**: SA = SUPER_ADMIN only, OA+ = ORG_ADMIN or higher, TL+ = TEAM_LEAD or higher, JIT = requires JIT approval for MEMBER role, Yes = any authenticated user
**Last Updated**: 2026-02-10
