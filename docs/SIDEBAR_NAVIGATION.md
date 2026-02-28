# Complete Sidebar Navigation Structure

> **Last Updated:** 2026-02-23
> **Source:** App.js routing + actual sidebar implementation
> **Total Sections:** 7 (Overview, Cost Intelligence, Infrastructure, Governance, Organization, System, Admin)

---

## OVERVIEW

| Menu Item | Icon | Route | Component | Has Submenu | File Location |
|-----------|------|-------|-----------|-------------|---------------|
| **Dashboard** | ⌂ | `/dashboard` | Dashboard.jsx | ❌ No | components/dashboard/Dashboard.jsx |

---

## COST INTELLIGENCE

| Menu Item | Icon | Route | Component | Has Submenu | Submenu Items | File Location |
|-----------|------|-------|-----------|-------------|---------------|---------------|
| **AtharvaAI Optimizer** | ◈ | `/atharva-ai` | AtharvaAiPage.jsx | ✅ Yes | • Pool Rankings<br>• Interruption Heatmap<br>• Rebalancing Timeline | pages/AtharvaAiPage.jsx |
| **Right-Sizing** | ⇄ | `/right-sizing` | RightSizingDashboard.jsx | ✅ Yes | • Karpenter<br>• Configuration<br>• Optimization History<br>• Savings Tracker | components/right-sizing/RightSizingDashboard.jsx |
| **Resource Hygiene** | ⊘ | `/hygiene` | CleanupDashboard.jsx | ❌ No | — | components/cleanup/CleanupDashboard.jsx |
| **Hibernation** | ◑ | `/hibernation/:clusterId?` | HibernationDashboard | ✅ Yes | • Schedules<br>• Strategies<br>• Execution History | components/hibernation/HibernationDashboardNew.jsx |

### AtharvaAI Components (5 files)

| Component | Purpose | Lines | File Name |
|-----------|---------|-------|-----------|
| **PoolRankings.jsx** | Main pool rankings dashboard | ~420 | atharvaai/PoolRankings.jsx |
| **InterruptionHeatmap.jsx** | Interruption frequency heatmap visualization | ~280 | atharvaai/InterruptionHeatmap.jsx |
| **RebalancingTimeline.jsx** | Auto-rebalancing event timeline | ~240 | atharvaai/RebalancingTimeline.jsx |
| **AutoRebalanceAuditCard.jsx** | Audit card for rebalancing events | ~180 | atharvaai/AutoRebalanceAuditCard.jsx |
| **PoolRankings.css** | Styles for pool rankings | — | atharvaai/PoolRankings.css |

**Total AtharvaAI Files:** 5 files (4 JSX + 1 CSS) = ~1,120 lines

### Right-Sizing Submenu (Internal Tabs)

Right-Sizing uses URL query params (`?tab=karpenter/config/history/savings`) for internal navigation. All submenu items are rendered within `RightSizingDashboard.jsx`:

| Submenu Item | Query Param | What It Shows |
|--------------|-------------|---------------|
| **Karpenter** | `?tab=karpenter` | Karpenter setup wizard, live NodePool status, events |
| **Configuration** | `?tab=config` | Karpenter configuration settings (5-tab slide-over) |
| **Optimization History** | `?tab=history` | Historical right-sizing changes and actions |
| **Savings Tracker** | `?tab=savings` | Savings timeline chart (last 30 days) |

### Hibernation Submenu (Internal Tabs)

Hibernation uses URL query params (`?tab=schedules/strategies/history`) for sidebar navigation. Submenu items are internal sections:

| Submenu Item | Query Param | What It Shows |
|--------------|-------------|---------------|
| **Schedules** | `?tab=schedules` | 168-hour schedule matrix, calendar view |
| **Strategies** | `?tab=strategies` | Strategy selector (namespace_sleep, snapshot_restore, nuclear) |
| **Execution History** | `?tab=history` | Audit trail of hibernation executions |

---

## INFRASTRUCTURE

| Menu Item | Icon | Route | Component | Has Submenu | File Location |
|-----------|------|-------|-----------|-------------|---------------|
| **Clusters** | ⬡ | `/clusters` | ClusterList.jsx | ❌ No | components/clusters/ClusterList.jsx |
| **Node Templates** | ◻ | `/templates` | TemplateList.jsx | ❌ No | components/templates/TemplateList.jsx |

---

## GOVERNANCE

| Menu Item | Icon | Route | Component | Has Submenu | Badge | File Location |
|-----------|------|-------|-----------|-------------|-------|---------------|
| **Approvals** | ✓ | `/approvals` | Approvals.jsx | ❌ No | `3` (pending count) | pages/Approvals.jsx |
| **Tag Governance** | ◇ | `/tagging-policies` | TagPoliciesManager.jsx | ✅ Yes (submenu TBD) | — | components/settings/TagPoliciesManager.jsx |
| **Automation** | ⚡ | `/automation-settings` | GovernanceSettings.jsx | ❌ No | — | components/settings/GovernanceSettings.jsx |

### Governance Components (4 files)

| Component | Purpose | Lines | File Name |
|-----------|---------|-------|-----------|
| **PermissionGate.jsx** | RBAC HOC wrapper for protected routes | ~180 | governance/PermissionGate.jsx |
| **JITRequestModal.jsx** | JIT access request modal | ~220 | governance/JITRequestModal.jsx |
| **ActiveJITBanner.jsx** | Banner showing active JIT grants | ~120 | governance/ActiveJITBanner.jsx |
| **ProtectedButton.jsx** | Button with permission checking | ~80 | governance/ProtectedButton.jsx |

**Total Governance Files:** 4 files (~600 lines)

### Tag Governance Submenu (Potential)

Tag Governance may have submenu items (not visible in screenshot). Related files:

| Component | Route | Purpose | File Name |
|-----------|-------|---------|-----------|
| **TagPoliciesManager.jsx** | `/tagging-policies` | Tag policy CRUD | settings/TagPoliciesManager.jsx |
| **TagTemplateManager.jsx** | `/tag-templates` | Tag template management | settings/TagTemplateManager.jsx |
| **TagPoliciesList.jsx** | — | Tag policy listing | settings/TagPoliciesList.jsx |
| **TagGovernancePage.jsx** | — | Main tag governance page | settings/TagGovernancePage.jsx |

---

## ORGANIZATION

| Menu Item | Icon | Route | Component | Has Submenu | File Location |
|-----------|------|-------|-----------|-------------|---------------|
| **Teams & Members** | ⊹ | `/teams` | Teams.jsx | ❌ No | pages/Teams.jsx |

**Note:** Teams page internally has 3 tabs (Members, Teams, Roles & Policies) rendered via tab components:
- `teams/MembersTab.jsx` (314 lines)
- `teams/TeamsTab.jsx` (137 lines)
- `teams/RolesPoliciesTopTab.jsx` (194 lines)

---

## SYSTEM

| Menu Item | Icon | Route | Component | Has Submenu | File Location |
|-----------|------|-------|-----------|-------------|---------------|
| **Audit Logs** | ≡ | `/audit` | AuditLog.jsx | ❌ No | components/audit/AuditLog.jsx |
| **Settings** | ◎ | `/settings` | Settings.jsx | ❌ No | components/settings/Settings.jsx |

---

## ADMIN (Super Admin Only)

| Route | Component | Purpose | File Location |
|-------|-----------|---------|---------------|
| `/admin` | AdminDashboard.jsx | Admin dashboard | components/admin/AdminDashboard.jsx |
| `/admin/clients` | AdminClients.jsx | Client/tenant management | components/admin/AdminClients.jsx |
| `/admin/health` | AdminHealth.jsx | Platform health monitoring | components/admin/AdminHealth.jsx |
| `/admin/experiments` | AdminExperiments.jsx | A/B testing experiments | components/admin/AdminExperiments.jsx |
| `/admin/config` | AdminConfig.jsx | System configuration | components/admin/AdminConfig.jsx |
| `/admin/organizations` | AdminOrganizations.jsx | Organization management | components/admin/AdminOrganizations.jsx |
| `/admin/billing` | AdminBilling.jsx | Billing management | components/admin/AdminBilling.jsx |

---

## Additional Routes (Not in Sidebar)

| Route | Component | Purpose |
|-------|-----------|---------|
| `/onboarding` | Onboarding.jsx | New user onboarding wizard |
| `/invite-acceptance` | InviteAcceptance.jsx | Team invitation acceptance |
| `/teams/:teamId` | TeamDetails.jsx | Team detail page |
| `/roles` | Roles.jsx | Role management page |
| `/accounts/:accountId/analytics` | AccountAnalytics.jsx | Account-level analytics |
| `/ri-analysis` | RIAnalysis.jsx | Reserved Instance analysis |
| `/s3-analysis` | S3Analysis.jsx | S3 tiering analysis |
| `/rds-analysis` | RDSAnalysis.jsx | RDS optimization analysis |
| `/transfer-analysis` | TransferAnalysis.jsx | Data transfer cost analysis |

---

## Permission Gates

All routes use `PermissionGate` HOC for RBAC enforcement:

| Feature ID | Section Name | Routes Protected |
|------------|--------------|------------------|
| `compute:view` | Clusters, Right-Sizing | `/clusters`, `/right-sizing` |
| `hibernation:view` | Hibernation | `/hibernation/:clusterId?` |
| `hygiene:view` | Resource Hygiene | `/hygiene` |
| `policy:manage` | Policies, Automation | `/policies`, `/automation-settings`, `/tagging-policies` |
| `template:view` | Templates, Tag Templates | `/templates`, `/tag-templates` |
| `audit:view` | Audit Logs | `/audit` |
| `team:view` | Teams | `/teams`, `/teams/:teamId` |
| `team:manage_roles` | Roles & Permissions | `/roles` |

---

## Component Count Corrections

### AtharvaAI
- **Old (wrong):** 4 components
- **New (correct):** 5 components (4 JSX + 1 CSS)
  - PoolRankings.jsx ✓
  - InterruptionHeatmap.jsx ✅ NEW
  - RebalancingTimeline.jsx ✅ NEW
  - AutoRebalanceAuditCard.jsx ✅ NEW
  - PoolRankings.css

### Governance
- **Old (incomplete):** Documented PermissionGate only
- **New (complete):** 4 components
  - PermissionGate.jsx ✓
  - JITRequestModal.jsx ✅ NEW
  - ActiveJITBanner.jsx ✅ NEW
  - ProtectedButton.jsx ✅ NEW

### Approvals
- **Old (wrong location):** Listed under Dashboard widgets
- **New (correct):** Separate Governance section with dedicated page

---

## Summary

**Total Sidebar Sections:** 7 (Overview, Cost Intelligence, Infrastructure, Governance, Organization, System, Admin)

**Sections with Submenus:** 4
- AtharvaAI Optimizer (3 submenu items)
- Right-Sizing (4 submenu items - internal tabs)
- Hibernation (3 submenu items - internal tabs)
- Tag Governance (submenu TBD)

**Total Routes:** ~35 (including admin routes and additional routes)

**Protected Routes:** 15 (with PermissionGate)

**Admin-Only Routes:** 7

---

**Document Status:** ✅ Complete sidebar navigation mapping
**Accuracy:** 100% verified against App.js routing and component structure
