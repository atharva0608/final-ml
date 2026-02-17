# All Components Documentation

Complete reference for all frontend components, their APIs, and data flow.

---

## Table of Contents
1. [Dashboard Components](#dashboard-components)
2. [Hibernation Components](#hibernation-components)
3. [Cluster Components](#cluster-components)
4. [Settings Components](#settings-components)
5. [Teams & Permissions](#teams--permissions)
6. [Admin Components](#admin-components)
7. [AtharvaAI Components](#atharvaai-components)
8. [Resource Hygiene Components](#resource-hygiene-components)

---

## Dashboard Components

### Main Dashboard (`/dashboard`)
**File**: `frontend/src/components/dashboard/Dashboard.jsx`

**Purpose**: Main dashboard with role-based widget system

**APIs Used**:
- `GET /api/v1/metrics/dashboard` - Dashboard KPIs
- `GET /api/v1/metrics/cost` - Cost data
- `GET /api/v1/clusters` - Cluster list
- `GET /api/v1/approvals/my-jit-approvals` - Pending approvals

**Widget Registry**: `frontend/src/components/dashboard/widgetRegistry.js`
- Maps widget keys to React components
- Registered widgets:
  - `cost_kpi` - CostKPICard
  - `savings_kpi` - SavingsKPICard
  - `savings_chart` - SavingsChart
  - `fleet_composition` - FleetComposition
  - `spend_forecast` - SpendForecastWidget ✅ NEW
  - `agent_status` - AgentStatusWidget ✅ NEW
  - `ri_health` - RIHealthCard
  - `s3_health` - S3HealthCard
  - `rds_health` - RDSHealthCard
  - `transfer_health` - TransferHealthCard
  - `activity_feed` - ActivityFeed
  - `cluster_health` - ClusterHealthCard
  - `pending_approvals` - PendingApprovalsCard
  - `platform_health` - PlatformHealthCard (Super Admin)
  - `tenant_list` - TenantListCard (Super Admin)

**Role Defaults**: `frontend/src/components/dashboard/roleDefaults.js`
- `SUPER_ADMIN`: platform_health, tenant_list, global_audit, revenue_chart
- `ORG_ADMIN`: cost_kpi, savings_kpi, **spend_forecast**, **agent_status**, ri_health, s3_health, rds_health, transfer_health, savings_chart, fleet_composition, activity_feed
- `CLIENT`: Same as ORG_ADMIN
- `TEAM_LEAD`: team_budget, pending_approvals, **spend_forecast**, cost_kpi, ri_health, rds_health, savings_kpi, activity_feed
- `MEMBER`: cost_kpi, savings_kpi, my_tickets, activity_feed

### New Dashboard Widgets

#### SpendForecastWidget
**File**: `frontend/src/components/dashboard/widgets/SpendForecastWidget.jsx`

**Purpose**: Shows end-of-month cost projection based on current burn rate

**APIs Used**:
- `GET /api/v1/metrics/cost/timeseries` - Time series cost data

**Data Flow**:
1. Fetches cost data from start of month to current date
2. Calculates daily burn rate: `currentSpend / currentDayOfMonth`
3. Projects EOM: `dailyBurnRate * daysInMonth`
4. Shows variance with color coding:
   - Green: < 10% variance
   - Yellow: 10-25% variance
   - Red: > 25% variance

**Features**:
- Real-time burn rate calculation
- Projected vs current spend comparison
- Auto-refresh every 60 seconds

#### AgentStatusWidget
**File**: `frontend/src/components/dashboard/widgets/AgentStatusWidget.jsx`

**Purpose**: Live monitoring of agent heartbeat status across all clusters

**APIs Used**:
- `GET /api/v1/clusters` - Cluster data with agent heartbeat

**Data Flow**:
1. Fetches all clusters with `last_heartbeat` field
2. Calculates heartbeat age in minutes
3. Categories:
   - **Healthy**: < 10 minutes (green)
   - **Warning**: 10-30 minutes (yellow)
   - **Stale**: > 30 minutes or never connected (red)

**Features**:
- Color-coded status dots
- Healthy/Warning/Stale count badges
- Auto-refresh every 30 seconds
- Click to view agent details

---

## Hibernation Components

### HibernationPage (`/hibernation/:clusterId`)
**File**: `frontend/src/pages/HibernationPage.jsx`

**Purpose**: Main hibernation configuration page with strategy selection and scheduling

**Layout**:
```
┌─────────────────────────────────────────────────┐
│ Header (Back to Clusters + Page Title)         │
├─────────────────────────────────────────────────┤
│ Strategy Selector (3 cards)                     │
├──────────────────────────────┬──────────────────┤
│ HibernationScheduler (2/3)   │ Sidebar (1/3)    │
│ - Weekly Grid                │ - ValidationPanel│
│ - Time Rules                 │ - CostAnalytics  │
│ - Quick Templates            │                  │
└──────────────────────────────┴──────────────────┘
```

**Store**: `frontend/src/store/useHibernationStore.js`
- Uses Zustand for state management
- Persists schedule, metrics, validation state

### Hibernation Components Breakdown

#### 1. StrategySelector
**File**: `frontend/src/components/hibernation/StrategySelector.jsx`

**Purpose**: Select hibernation strategy with comparison table

**Strategies**:
- **NAMESPACE_SLEEP**: ~2 min wake | ~80% savings (Default)
  - Scales workloads to 0 replicas
  - Best for: Stateless dev/test workloads

- **NUCLEAR**: ~8 min wake | ~99% savings
  - Scales all ASGs to 0
  - Best for: Non-critical environments

- **SNAPSHOT_RESTORE**: ~12 min wake | ~90% savings
  - Snapshots EBS volumes before shutdown
  - Best for: Stateful workloads, databases

**APIs Used**:
- `GET /api/v1/hibernation/strategies` - Strategy metadata

**Features**:
- 3-card layout with visual indicators
- Expandable comparison table
- Shows wake time, savings %, safety level

#### 2. HibernationScheduler
**File**: `frontend/src/components/hibernation/HibernationScheduler.jsx`

**Purpose**: Visual schedule editor with 168-hour weekly grid

**APIs Used**:
- `GET /api/v1/hibernation/schedules?cluster_id=X` - Load schedule
- `POST /api/v1/hibernation/schedules` - Create schedule
- `PUT /api/v1/hibernation/schedules/:id` - Update schedule
- `POST /api/v1/hibernation/schedules/:id/toggle` - Enable/Disable
- `POST /api/v1/hibernation/schedules/:id/override` - Manual sleep/wake
- `GET /api/v1/metrics/cluster/:id` - Hourly cost for calculations

**Features**:
- 168-hour grid (7 days × 24 hours)
- Time-based rules editor
- Quick templates (Business Hours, Nights Only, Weekends Off)
- Drag-to-paint sleep windows
- Timezone selector
- Pre-warm minutes config
- Real-time cost savings calculation
- Live status polling (30s interval)

**Data Structure**:
```javascript
{
  cluster_id: "cluster-abc",
  strategy: "NAMESPACE_SLEEP",
  schedule_matrix: [1,1,1,...,0,0,0], // 168 binary values (1=awake, 0=sleep)
  timezone: "UTC",
  pre_warm_minutes: 15,
  is_active: true,
  date_overrides: {} // Future: specific date overrides
}
```

**Schedule Matrix**:
- 168-cell array (7 days × 24 hours)
- Monday 12AM = index 0
- Sunday 11PM = index 167
- 1 = awake, 0 = sleep

#### 3. ValidationPanel
**File**: `frontend/src/components/hibernation/ValidationPanel.jsx`

**Purpose**: Real-time schedule validation with warnings/errors

**Validation Rules**:
- Pre-warm time must be 0-60 minutes
- Nuclear strategy shows safety warning
- Checks for conflicts in schedule rules

**Features**:
- Green/Yellow/Red status indicator
- Lists all errors and warnings
- Auto-validates on schedule change

#### 4. CostAnalytics
**File**: `frontend/src/components/hibernation/CostAnalytics.jsx`

**Purpose**: Cost projection and ROI visualization

**APIs Used**:
- Uses metrics from `useHibernationStore`

**Features**:
- Bar chart: With vs Without Hibernation
- Monthly savings estimate
- Efficiency score, ROI, Break-even metrics
- Responsive chart with Recharts library

**Calculations**:
```javascript
sleepHours = schedule_matrix.filter(h => h === 0).length
sleepRatio = sleepHours / 168
strategyEfficiency = strategy.savings_pct / 100
monthlySavings = hourlyCost * 730 * sleepRatio * strategyEfficiency
```

### Hibernation API Endpoints

```
GET    /api/v1/hibernation/schedules           List all schedules
GET    /api/v1/hibernation/schedules?cluster_id=X   Get schedule by cluster
POST   /api/v1/hibernation/schedules           Create new schedule
PUT    /api/v1/hibernation/schedules/:id      Update schedule
DELETE /api/v1/hibernation/schedules/:id      Delete schedule
POST   /api/v1/hibernation/schedules/:id/toggle    Enable/Disable schedule
POST   /api/v1/hibernation/schedules/:id/override  Manual sleep/wake
GET    /api/v1/hibernation/strategies         Get available strategies
```

---

### ⚠️ Common Issue Fixed: Save Schedule Button

**Problem**: Button was disabled and unclickable

**Root Cause**:
- Default rule had `days: []` (empty array)
- Validation checked `hasErrors = rules.some(r => r.days.length === 0)`
- This made button permanently disabled

**Solution Applied** (2026-02-17):

1. **Filter Empty Rules Before Matrix Conversion**:
   ```javascript
   // Filter out rules with no days selected
   const validRules = useMemo(() => rules.filter(r => r.days.length > 0), [rules]);
   const matrix = useMemo(() => rulesToMatrix(validRules), [validRules]);
   ```

2. **Removed hasErrors Validation**:
   ```javascript
   // Allow saving even with no rules (means always awake schedule)
   const hasErrors = false;
   ```

3. **Updated Save Handler**:
   ```javascript
   const handleSave = async () => {
     if (!selectedClusterId) {
       toast.error("Please select a cluster first");
       return;
     }
     // ... save logic
   };
   ```

4. **Improved Button UX**:
   ```javascript
   <button
     onClick={handleSave}
     disabled={saving || !selectedClusterId}
     style={{
       background: savedOk ? "#10b981" : "#2563eb",
       opacity: (saving || !selectedClusterId) ? 0.5 : 1
     }}>
     {saving ? "Saving…" : savedOk ? "✓ Saved" : "Save Schedule"}
   </button>
   ```

**Result**: Button now works correctly. Empty rules are filtered out, creating a valid "always awake" schedule.

---

## Cluster Components

### ClusterList (`/clusters`)
**File**: `frontend/src/pages/ClusterPage.jsx`

**APIs Used**:
- `GET /api/v1/clusters` - List clusters
- `GET /api/v1/accounts` - Account filter

**Features**:
- Cluster cards with health indicators
- Filter by account, region, status
- Quick actions: Hibernate, Configure, Agent Install
- Real-time status badges

### ClusterDetails (`/clusters/:id`)
**File**: `frontend/src/components/cluster/ClusterDetails.jsx`

**APIs Used**:
- `GET /api/v1/clusters/:id` - Cluster details
- `GET /api/v1/metrics/cluster/:id` - Cluster metrics
- `GET /api/v1/instances?cluster_id=X` - Instance list

**Features**:
- Overview tab: Nodes, instances, cost
- Instances tab: Instance type breakdown
- Metrics tab: CPU, memory, cost trends
- Hibernation tab: Quick schedule config

---

## Settings Components

### Settings (`/settings`)
**File**: `frontend/src/components/settings/Settings.jsx`

**Tabs**:
1. **Account** - Profile, preferences
2. **Billing** - Subscription, usage, Stripe portal
3. **Security** - Password, 2FA, API keys
4. **Notifications** - Email, Slack, webhooks

**APIs Used** (Billing Tab):
- `GET /api/v1/billing/status` - Subscription info
- `GET /api/v1/billing/costs/summary` - Cost breakdown
- `POST /api/v1/billing/create-portal-session` - Stripe portal URL

**Data Flow (Billing)**:
1. User clicks "Manage Billing"
2. Frontend calls `billingAPI.createPortalSession()`
3. Backend creates Stripe portal session
4. Opens Stripe portal in new tab
5. User manages subscription in Stripe
6. Returns to app

---

## Teams & Permissions

### Teams Page (`/teams`)
**File**: `frontend/src/pages/Teams.jsx`

**Purpose**: Manage organization members, teams, roles, and permissions

**Layout**:
```
┌──────────────────────────────────────┐
│ Teams & Permissions                  │
├──────────────────────────────────────┤
│ [Team Structure] [Roles & Policies]  │ ← Top tabs
├──────────────────────────────────────┤
│ [Members] [Teams]                    │ ← Inner tabs (Structure)
├──────────────────────────────────────┤
│ Content Area                         │
└──────────────────────────────────────┘
```

**Tabs Structure**:
1. **Team Structure** (Main Tab)
   - **Members** (Sub-tab)
   - **Teams** (Sub-tab)
2. **Roles & Policies** (Main Tab)

---

### MembersTab Component
**File**: `frontend/src/components/teams/MembersTab.jsx`

**Purpose**: View and manage organization members

**APIs Used**:
```javascript
// Get all members
GET /api/v1/organization/members

// Invite new member
POST /api/v1/organization/members
{
  "email": "user@example.com",
  "role": "MEMBER",
  "access_level": "READ"
}

// Update member role
PATCH /api/v1/organization/members/:userId
{
  "role": "TEAM_LEAD",
  "access_level": "WRITE"
}

// Remove member
DELETE /api/v1/organization/members/:userId

// Get pending invitations
GET /api/v1/organization/invitations
```

**Features**:
- Member list with role badges
- Invite new members via email
- Update roles and access levels
- Remove members from organization
- View pending invitations
- Search and filter members

**Real API Integration**: ✅ Uses `organizationAPI`

---

### TeamsTab Component
**File**: `frontend/src/components/teams/TeamsTab.jsx`

**Purpose**: Create and manage teams within the organization

**APIs Used**:
```javascript
// List all teams
GET /api/v1/teams/

// Create new team
POST /api/v1/teams/
{
  "name": "Engineering Team"
}

// Get team details
GET /api/v1/teams/:id

// Rename team
PUT /api/v1/teams/:id/rename
{
  "name": "Updated Name"
}

// Assign member to team
POST /api/v1/teams/:teamId/assign
{
  "member_id": "user-123"
}

// Remove member from team
POST /api/v1/teams/:teamId/remove
{
  "member_id": "user-123"
}

// Invite to team
POST /api/v1/teams/:teamId/invite
{
  "email": "user@example.com",
  "role": "MEMBER",
  "full_name": "John Doe"
}

// Get team stats
GET /api/v1/teams/:teamId/stats

// Update team governance
PUT /api/v1/teams/:teamId/governance
{
  "config": {...}
}

// Update member permissions
PUT /api/v1/teams/:teamId/members/:memberId/permissions
{
  "permissions": [...]
}
```

**Features**:
- Create and manage teams
- Assign members to teams
- Team-based access control
- Team statistics and insights
- Governance rules per team
- Member permission management

**Real API Integration**: ✅ Uses `teamAPI`

---

### RolesPoliciesTopTab Component
**File**: `frontend/src/components/teams/RolesPoliciesTopTab.jsx`

**Purpose**: Manage roles and access policies

**APIs Used**:
```javascript
// Get all roles
GET /api/v1/roles

// Get all permissions
GET /api/v1/roles/permissions

// Create custom role
POST /api/v1/roles
{
  "name": "Custom Role",
  "permissions": ["read_clusters", "write_templates"]
}

// Update role
PUT /api/v1/roles/:id
{
  "permissions": [...]
}
```

**Features**:
- View system roles (SUPER_ADMIN, ORG_ADMIN, TEAM_LEAD, MEMBER)
- Create custom roles
- Assign permissions to roles
- Role-based access control (RBAC)
- Permission matrix view

**Role Hierarchy**:
1. **SUPER_ADMIN** - Platform-wide access
2. **ORG_ADMIN** - Full organization access
3. **TEAM_LEAD** - Team management + resource access
4. **MEMBER** - Limited resource access

---

### Team Management Data Flow

**Creating a Team**:
```
User clicks "Create Team"
  ↓
Enter team name
  ↓
POST /api/v1/teams/ → { name }
  ↓
Backend creates team
  ↓
Returns team { id, name, created_at }
  ↓
Frontend updates team list
  ↓
Success notification
```

**Inviting Members to Team**:
```
User selects team
  ↓
Clicks "Invite Member"
  ↓
Enter email + role
  ↓
POST /api/v1/teams/:id/invite → { email, role }
  ↓
Backend sends invitation email
  ↓
Member receives email with accept link
  ↓
Member accepts → automatically added to team
```

**Assigning Existing Member to Team**:
```
User selects team
  ↓
Clicks "Assign Member"
  ↓
Select from organization members list
  ↓
POST /api/v1/teams/:id/assign → { member_id }
  ↓
Member immediately added to team
  ↓
Member sees team in their dashboard
```

---

### API Client Modules

**organizationAPI**:
```javascript
export const organizationAPI = {
  getMembers: () => api.get('/api/v1/organization/members'),
  getInvitations: () => api.get('/api/v1/organization/invitations'),
  inviteMember: (email, role, access_level) =>
    api.post('/api/v1/organization/members', { email, role, access_level }),
  removeMember: (userId) =>
    api.delete(`/api/v1/organization/members/${userId}`),
  updateMemberRole: (userId, role, access_level) =>
    api.patch(`/api/v1/organization/members/${userId}`, { role, access_level })
};
```

**teamAPI**:
```javascript
export const teamAPI = {
  list: () => api.get('/api/v1/teams/'),
  get: (id) => api.get(`/api/v1/teams/${id}`),
  create: (name) => api.post('/api/v1/teams/', { name }),
  rename: (id, name) => api.put(`/api/v1/teams/${id}/rename`, { name }),
  assign: (teamId, memberId) =>
    api.post(`/api/v1/teams/${teamId}/assign`, { member_id: memberId }),
  remove: (teamId, memberId) =>
    api.post(`/api/v1/teams/${teamId}/remove`, { member_id: memberId }),
  invite: (teamId, email, role = "MEMBER", fullName = null) =>
    api.post(`/api/v1/teams/${teamId}/invite`, { email, role, full_name: fullName }),
  getStats: (teamId) => api.get(`/api/v1/teams/${teamId}/stats`),
  updateGovernance: (teamId, config) =>
    api.put(`/api/v1/teams/${teamId}/governance`, { config }),
  updateMemberPermissions: (teamId, memberId, permissions) =>
    api.put(`/api/v1/teams/${teamId}/members/${memberId}/permissions`, { permissions })
};
```

---

## Approvals & JIT Access

### Approvals Page (`/approvals`)
**File**: `frontend/src/pages/Approvals.jsx`

**Purpose**: Just-In-Time (JIT) access governance system for time-bound permissions

**Role-Based Views**:
- **ORG_ADMIN/CLIENT**: Approval queue + Active grants management
- **TEAM_LEAD**: Team member requests + Active team access
- **MEMBER**: Personal access requests

**APIs Used**:
```javascript
// List all tickets
GET /api/v1/approvals/
  → Returns all approval tickets filtered by role

// Approve a pending request
POST /api/v1/approvals/{id}/approve
  → Status: PENDING → PENDING_CONSENT (awaits user acceptance)

// Reject a pending request
POST /api/v1/approvals/{id}/reject
  → Status: PENDING → REJECTED

// User accepts granted access
POST /api/v1/approvals/{id}/accept
  → Status: PENDING_CONSENT → APPROVED_ACTIVE (timer starts)

// User declines granted access
POST /api/v1/approvals/{id}/reject
  → Status: PENDING_CONSENT → REJECTED

// Revoke active access immediately
POST /api/v1/approvals/{id}/revoke
  → Status: APPROVED_ACTIVE → REVOKED

// Create new JIT request
POST /api/v1/approvals/jit-request
  body: { feature_id, resource_id, duration_hours, reason_category, reason_text }

// Get active access window for current user
GET /api/v1/approvals/active-window
```

**Ticket Lifecycle**:
```
PENDING → PENDING_CONSENT → APPROVED_ACTIVE → EXPIRED
   ↓           ↓                    ↓
REJECTED    REJECTED            REVOKED
```

**Tabs by Role**:

**ORG_ADMIN / CLIENT**:
1. **Pending Requests** (`queue`) - All PENDING tickets awaiting approval
2. **Active Grants** (`active_grants`) - All APPROVED_ACTIVE + PENDING_CONSENT tickets

**TEAM_LEAD**:
1. **Incoming Requests** (`incoming`) - PENDING from team members
2. **Active Team Access** (`active_team_access`) - APPROVED_ACTIVE for team
3. **My Outgoing Requests** (`outgoing`) - Personal requests

**MEMBER**:
1. **My Requests** (`my_requests`) - All personal tickets

**Features**:
- **Stats Summary** (Admin only): Pending / Active / Awaiting Consent counts
- **Pending Grants Alert**: Purple banner when user has PENDING_CONSENT tickets
- **Risk Badges**: Visual risk indicators for JIT features (CRITICAL/HIGH/MEDIUM/LOW)
- **Real-time Events**: Dispatches `approval:changed` event on all state changes
- **Auto-refresh**: Components listen to `approval:changed` for instant updates

**Data Flow (Request → Approval → Activation)**:
1. Member clicks ProtectedButton → Opens JIT request modal
2. Submits request → `POST /api/v1/approvals/jit-request`
3. Approver sees in queue → Clicks "Approve" → `POST /api/v1/approvals/{id}/approve`
4. Status → PENDING_CONSENT, user gets purple banner
5. User clicks "Accept & Start" → `POST /api/v1/approvals/{id}/accept`
6. Status → APPROVED_ACTIVE, timer starts
7. After duration_hours → Status → EXPIRED (auto)
8. OR Admin clicks "Revoke" → Status → REVOKED (immediate)

**Components**:
- `ActiveJITBanner.jsx` - Shows active access window with countdown
- `TicketRequestModal.jsx` - Create new JIT access request
- `RiskBadge.jsx` - Color-coded risk level indicator

---

## Templates (Optimization Templates)

### TemplateList Component
**File**: `frontend/src/components/templates/TemplateList.jsx`

**Purpose**: Manage EC2 instance configuration templates for cluster optimization

**APIs Used**:
```javascript
// List all templates
GET /api/v1/templates
  params: { page, page_size }

// Get template by ID
GET /api/v1/templates/{id}

// Create new template
POST /api/v1/templates
  body: { name, description, architecture, os, instance_families, ... }

// Update existing template
PUT /api/v1/templates/{id}
  body: { ...updated fields }

// Delete template
DELETE /api/v1/templates/{id}

// Set as default template
POST /api/v1/templates/{id}/set-default

// Get configuration options (families, disk types, etc.)
GET /api/v1/templates/options
  → Returns: { families: [], architectures: [], disk_types: [], strategies: [] }
```

**Features**:
- Template cards with name, description, families, strategy
- Default template badge
- Edit/Delete/Set Default actions
- Create new template button

---

### TemplateBuilder Component
**File**: `frontend/src/components/templates/TemplateBuilder.jsx`

**Purpose**: Create/edit optimization templates with tabbed configuration

**Configuration Tabs**:

**1. Compute**:
- Architecture: x86_64 (Intel/AMD) or arm64 (Graviton)
- OS: Linux or Windows
- Allowed Families: Multi-select checkboxes (t3, m5, c5, r5, etc.)
- Min CPUs: Number input
- Min Memory (GB): Number input

**2. Storage**:
- Root Volume Type: GP3/GP2/IO1/IO2/ST1/SC1
- Root Volume Size (GB)
- GP3 specific: IOPS, Throughput (MB/s)

**3. Network**:
- Security Groups: Comma-separated SG IDs
- Subnets: Comma-separated subnet IDs

**4. Kubernetes**:
- Node Taints: Key/Value/Effect (NoSchedule, PreferNoSchedule, NoExecute)
- Labels: Key-value pairs
- User Data: Base64 or plain text startup script

**Template Data Structure**:
```javascript
{
  name: "Production Template",
  description: "Optimized for production workloads",
  architecture: "x86_64",
  os: "linux",
  instance_families: ["m5", "c5", "r5"],
  excluded_families: [],
  min_cpu: 2,
  min_memory: 4,
  root_volume_type: "GP3",
  root_volume_size: 20,
  root_volume_iops: 3000,
  root_volume_throughput: 125,
  security_groups: ["sg-12345"],
  subnets: ["subnet-abc"],
  taints: [
    { key: "workload", value: "production", effect: "NoSchedule" }
  ],
  labels: { env: "prod" },
  user_data: "#!/bin/bash\necho 'Hello'",
  strategy: "BALANCED"
}
```

**Template Tips Sidebar**:
- Use broad families for better spot availability
- Add taints to isolate workloads
- GP3 is recommended for cost/performance

---

## Governance & Policies

### Governance Components

**File**: `frontend/src/components/governance/`

**Purpose**: JIT (Just-In-Time) access enforcement and permission gating

---

### ProtectedButton Component
**File**: `frontend/src/components/governance/ProtectedButton.jsx`

**Purpose**: Button that enforces JIT permission checks before action execution

**Props**:
```javascript
{
  featureId: string,        // JIT feature ID (e.g., "cluster.delete", "instance.terminate")
  resourceId: string,       // Optional resource ID
  onClick: function,        // Action to execute if permission granted
  variant: string,          // Button style: 'primary', 'secondary', 'danger'
  size: string,             // 'sm', 'md', 'lg'
  disabled: boolean,
  children: ReactNode       // Button label
}
```

**Permission Flow**:
1. Component calls `usePermission(featureId, resourceId)` hook
2. **If permission granted**:
   - Shows green checkmark icon
   - onClick executes normally
3. **If permission denied**:
   - Shows lock icon
   - onClick → Opens permission modal
   - Modal shows feature details (name, risk level, max duration)
   - User clicks "Request Access" → Dispatches `governance:required` event
   - JITRequestModal opens to submit formal request

**API Integration**:
```javascript
// Check permission
POST /api/v1/permissions/check
  body: { feature_id, resource_id }
  → Returns: { hasPermission: boolean, ticket: {...}, feature: {...} }

// Get user's active features
GET /api/v1/permissions/my-features
  → Returns: [{ feature_id, expires_at, resource_id }]

// Get feature registry (all available JIT features)
GET /api/v1/permissions/feature-registry
  → Returns: [{ id, name, description, risk_level, max_duration_hours }]
```

**usePermission Hook** (`frontend/src/hooks/usePermission.js`):
```javascript
const { hasPermission, loading, feature, ticket, expiresAt } = usePermission(featureId, resourceId);
```

**States**:
- `loading: true` → Button shows "Loading..."
- `hasPermission: true, ticket: {...}` → Green checkmark, active permission
- `hasPermission: true, ticket: null` → No approval needed (permanent permission)
- `hasPermission: false` → Lock icon, opens modal on click

---

### ActiveJITBanner Component
**File**: `frontend/src/components/governance/ActiveJITBanner.jsx`

**Purpose**: Global banner showing active time-bound access windows

**APIs Used**:
```javascript
GET /api/v1/approvals/active-window
  → Returns: { active: boolean, ticket: {...}, expires_at: "2026-02-17T12:00:00Z" }
```

**Display**:
- Only shows when user has APPROVED_ACTIVE ticket
- Green banner with timer countdown
- Shows feature name + time remaining
- Updates every 30 seconds
- Auto-hides when expired

---

### JITRequestModal Component
**File**: `frontend/src/components/governance/JITRequestModal.jsx`

**Purpose**: Form to create new JIT access request

**Form Fields**:
1. **Feature**: Dropdown of available JIT features
2. **Resource ID**: Optional (e.g., cluster ID, instance ID)
3. **Duration**: Slider (1h - max_duration_hours)
4. **Reason Category**: INCIDENT / MAINTENANCE / COST_OPT / TESTING / OTHER
5. **Reason Text**: Free-form justification

**APIs Used**:
```javascript
// Get available features
GET /api/v1/permissions/feature-registry

// Submit request
POST /api/v1/approvals/jit-request
  body: {
    feature_id,
    resource_id,
    duration_hours,
    reason_category,
    reason_text
  }
```

**Validation**:
- Feature required
- Duration must be ≤ max_duration_hours for selected feature
- Reason category + text required

---

### PermissionGate Component
**File**: `frontend/src/components/governance/PermissionGate.jsx`

**Purpose**: Conditional rendering wrapper for protected content

**Usage**:
```jsx
<PermissionGate featureId="cluster.delete" resourceId={clusterId}>
  <button>Delete Cluster</button>
</PermissionGate>
```

**Behavior**:
- Children rendered only if permission granted
- If denied → Shows lock icon + "Request Access" link

---

### Governance Settings
**File**: `frontend/src/components/settings/GovernanceSettings.jsx`

**Purpose**: Configure JIT features, risk levels, and cleanup policies

**APIs Used**:
```javascript
// Get governance policies
GET /api/v1/governance/policies
  → Returns: { jit_features: [...], cleanup_policies: {...}, automation_config: {...} }

// Update policies
PATCH /api/v1/governance/policies
  body: { jit_features, cleanup_policies, automation_config }

// Run autopilot (execute cleanup)
POST /api/v1/governance/run-autopilot?account_id={accountId}
```

**JIT Feature Configuration**:
```javascript
{
  id: "cluster.delete",
  name: "Delete Cluster",
  description: "Permanently delete a Kubernetes cluster",
  risk_level: "CRITICAL",        // CRITICAL/HIGH/MEDIUM/LOW
  max_duration_hours: 4,
  requires_approval: true,
  auto_approve_roles: ["ORG_ADMIN"],
  enabled: true
}
```

**Cleanup Policies** (See [Resource Hygiene](#resource-hygiene-components) section)

---

## Audit Log

### AuditLog Component
**File**: `frontend/src/components/audit/AuditLog.jsx`

**Purpose**: Immutable audit trail of all platform activities

**APIs Used**:
```javascript
// List audit logs with filters
GET /api/v1/audit/logs
  params: {
    page: 1,
    page_size: 20,
    event_type: "user.login",
    start_date: "2026-02-01",
    end_date: "2026-02-17",
    actor_id: "user-123",
    resource_id: "cluster-abc",
    actor_role: "ORG_ADMIN"
  }
  → Returns: { logs: [...], total_pages: 10, total_count: 200 }

// Export logs as JSON
GET /api/v1/audit/export
  params: { ...same filters }
  → Returns: JSON file download
```

**Event Types**:
```javascript
[
  'user.signup', 'user.login', 'user.logout',
  'cluster.created', 'cluster.updated', 'cluster.deleted',
  'policy.created', 'policy.updated', 'policy.toggled',
  'template.created', 'template.updated', 'template.deleted',
  'schedule.created', 'schedule.updated', 'schedule.toggled',
  'optimization.started', 'optimization.completed',
  'experiment.created', 'experiment.started', 'experiment.completed'
]
```

**Table Columns**:
1. **Timestamp**: ISO 8601 datetime
2. **Event**: Color-coded badge (created=green, updated=blue, deleted=red, auth=purple)
3. **Actor**: User email or "System"
4. **Resource**: resource_type:resource_id (e.g., "cluster:cluster-abc")
5. **IP Address**: Originating IP
6. **Actions**: "View Diff" button (if state changes exist)

**Filters**:
- Event Type dropdown
- Date range (start_date, end_date)
- Actor Role (Admin view only)
- Clear Filters button

**Features**:
- Pagination (20 logs per page)
- Export to JSON
- Diff viewer modal for state changes
- Auto-refresh support
- Filter persistence

**Diff Viewer Modal**:
- Shows before/after state comparison
- Color-coded: Red (before), Green (after)
- Field-by-field diff with change type (added/modified/removed)
- JSON pretty-print

**Data Structure**:
```javascript
{
  id: "audit-123",
  timestamp: "2026-02-17T10:00:00Z",
  event: "cluster.updated",
  actor_id: "user-456",
  actor_email: "admin@acme.com",
  actor_role: "ORG_ADMIN",
  resource_type: "cluster",
  resource_id: "cluster-abc",
  ip_address: "203.0.113.42",
  before_state: { name: "Old Name", replicas: 3 },
  after_state: { name: "New Name", replicas: 5 }
}
```

**Badge Colors**:
- `created` → Green
- `updated` → Blue
- `deleted` → Red
- `login`, `signup` → Purple
- Default → Gray

---

## Authentication

### Login Component
**File**: `frontend/src/components/auth/Login.jsx`

**Purpose**: User authentication

**APIs Used**:
```javascript
// Login
POST /api/v1/auth/login
  body: { email, password }
  → Returns: { access_token, refresh_token, user: {...} }
```

**Data Flow**:
1. User submits email + password
2. `authAPI.login({ email, password })`
3. Backend validates credentials
4. Returns JWT tokens + user object
5. Store tokens in localStorage
6. Update Zustand auth store
7. Redirect to `/dashboard`

**Error Handling**:
- Invalid credentials → "Invalid email or password"
- Account locked → "Account suspended. Contact support."

---

### Signup Component
**File**: `frontend/src/components/auth/Signup.jsx`

**Purpose**: New organization registration

**APIs Used**:
```javascript
// Signup
POST /api/v1/auth/signup
  body: { email, password, full_name, organization_name }
  → Returns: { access_token, refresh_token, user: {...} }
```

**Data Flow**:
1. User fills registration form
2. `authAPI.signup({ email, password, full_name, organization_name })`
3. Backend creates new organization + user (ORG_ADMIN role)
4. Returns JWT tokens
5. Redirects to onboarding flow

---

### InviteAcceptance Component
**File**: `frontend/src/components/auth/InviteAcceptance.jsx`

**Purpose**: Accept team invitation and create account

**APIs Used**:
```javascript
// Accept invitation
POST /api/v1/auth/invitation-response
  body: { token, password, full_name }
  → Returns: { access_token, refresh_token, user: {...} }
```

**URL Pattern**: `/invite?token=<jwt_invite_token>`

**Data Flow**:
1. User receives invite email → Clicks link with token
2. Enters password + full name
3. `authAPI.respondToInvitation({ token, password, full_name })`
4. Backend validates token, creates user account
5. User assigned to organization + team
6. Redirects to dashboard

---

### Auth Store
**File**: `frontend/src/store/useStore.js` (useAuthStore)

**State**:
```javascript
{
  user: {
    id: "user-123",
    email: "user@acme.com",
    full_name: "John Doe",
    role: "ORG_ADMIN",           // SUPER_ADMIN, ORG_ADMIN, CLIENT, TEAM_LEAD, MEMBER
    organization_id: "org-456",
    team_id: "team-789"
  },
  isAuthenticated: true
}
```

**Actions**:
- `login(credentials)` - Authenticate user
- `logout()` - Clear tokens, reset state
- `fetchUser()` - Get current user from `/api/v1/auth/me`
- `updateProfile(data)` - Update user profile

**Auth Interceptor** (`frontend/src/services/api.js`):
- Adds `Authorization: Bearer <token>` to all requests
- On 401 → Clear localStorage + redirect to `/login`
- On 403 with `required_ticket: true` → Dispatch `governance:required` event

---

## Onboarding

### Onboarding Flow
**File**: `frontend/src/components/onboarding/`

**Purpose**: 4-step wizard for AWS account connection

**Steps**:
1. **WelcomeStep** - Introduction
2. **ConnectStep** - AWS IAM role setup
3. **VerifyStep** - Test connection
4. **SuccessStep** - Completion

**APIs Used**:
```javascript
// Get onboarding state
GET /api/v1/onboarding/state
  → Returns: { step: 2, role_arn: "arn:aws:...", verified: false }

// Get AWS console link with pre-filled CloudFormation
GET /api/v1/onboarding/aws-link?mode=FULL_ACCESS
  → Returns: { url: "https://console.aws.amazon.com/cloudformation/...", role_arn: "..." }

// Download CloudFormation template
GET /api/v1/onboarding/template?mode=FULL_ACCESS
  → Returns: YAML file blob

// Verify role ARN
POST /api/v1/onboarding/verify
  body: { role_arn: "arn:aws:iam::123456789012:role/SpotOptimizerRole" }
  → Returns: { verified: true, account_id: "123456789012" }

// Skip onboarding
POST /api/v1/onboarding/skip
```

---

### WelcomeStep
**File**: `frontend/src/components/onboarding/WelcomeStep.jsx`

**Purpose**: Explain what SpotOptimizer does + permission requirements

**Content**:
- Feature highlights (cost optimization, hibernation, right-sizing)
- Required AWS permissions (EC2, EKS, Autoscaling, Cost Explorer)
- Security notes (read-only by default, actions require approval)

---

### ConnectStep
**File**: `frontend/src/components/onboarding/ConnectStep.jsx`

**Purpose**: AWS IAM role creation

**Options**:
1. **Quick Launch** (Recommended):
   - Click "Launch in AWS Console" button
   - Opens AWS CloudFormation with pre-filled stack
   - User clicks "Create Stack"
   - Copies generated Role ARN

2. **Manual Upload**:
   - Downloads CloudFormation template YAML
   - User uploads manually to AWS Console
   - Copies Role ARN

**Permission Modes**:
- **FULL_ACCESS** (default): Read + Write (hibernation, right-sizing actions)
- **READ_ONLY**: Discovery + metrics only

**Generated Role ARN Format**: `arn:aws:iam::123456789012:role/SpotOptimizerRole`

---

### VerifyStep
**File**: `frontend/src/components/onboarding/VerifyStep.jsx`

**Purpose**: Test AWS connection

**Verification Process**:
1. User pastes Role ARN
2. Click "Verify Connection"
3. Backend assumes role → Lists EC2 regions
4. If successful → Shows account ID + region count
5. Click "Continue" to finish

**Error States**:
- Invalid ARN format → "Invalid ARN format"
- Role doesn't exist → "Unable to assume role. Check trust policy."
- Permissions insufficient → "Role missing required permissions"

---

### SuccessStep
**File**: `frontend/src/components/onboarding/SuccessStep.jsx`

**Purpose**: Confirmation + next steps

**Content**:
- Success checkmark animation
- "AWS account connected successfully"
- Account ID + Role ARN summary
- "Go to Dashboard" button

---

## Right-Sizing (Cost Optimization)

### RightSizing Component
**File**: `frontend/src/components/right-sizing/RightSizing.jsx`

**Purpose**: EC2 instance right-sizing recommendations based on actual usage

**APIs Used**:
```javascript
// Get right-sizing recommendations
GET /api/v1/optimization/rightsizing/{clusterId}
  → Returns: [
      {
        instance_id: "i-abc123",
        current_type: "m5.2xlarge",
        recommended_type: "m5.xlarge",
        monthly_savings: 73.00,
        cpu_p95: 32.5,           // 95th percentile CPU %
        memory_p95: 45.2,        // 95th percentile Memory %
        recommendation_age_days: 2,
        status: "pending"         // pending, applied, dismissed
      }
    ]

// Apply recommendation
POST /api/v1/optimization/apply/{recommendation_id}
  → Triggers instance type change
```

**Features**:
- Cluster selector dropdown
- Recommendations table with sortable columns
- Batch apply modal
- Impact summary (total savings, instance count)
- Recommendation age indicator

**Table Columns**:
1. **Instance**: ID + current type
2. **Recommendation**: Suggested type + savings
3. **CPU/Memory**: 95th percentile bars
4. **Age**: Days since recommendation generated
5. **Actions**: Apply / Dismiss buttons

---

### ImpactSummary Component
**File**: `frontend/src/components/right-sizing/ImpactSummary.jsx`

**Purpose**: Summary cards showing optimization impact

**Metrics**:
- **Total Monthly Savings**: Sum of all recommendations
- **Instances Optimized**: Count of applied recommendations
- **Pending Recommendations**: Count of pending
- **Average CPU Utilization**: Across cluster

---

### BatchApplyModal Component
**File**: `frontend/src/components/right-sizing/BatchApplyModal.jsx`

**Purpose**: Apply multiple recommendations at once

**Features**:
- Select multiple instances
- Preview total savings
- Confirmation step
- Apply all → Sequential API calls

---

### InstanceUsageDetailPanel Component
**File**: `frontend/src/components/right-sizing/InstanceUsageDetailPanel.jsx`

**Purpose**: Detailed usage metrics for selected instance

**Displays**:
- CPU usage time series chart (7 days)
- Memory usage time series chart (7 days)
- Network I/O metrics
- Disk I/O metrics
- 95th percentile markers

---

### RecommendationAgeIndicator Component
**File**: `frontend/src/components/right-sizing/RecommendationAgeIndicator.jsx`

**Purpose**: Visual indicator of how old recommendation is

**Color Coding**:
- **< 7 days**: Green (Fresh)
- **7-14 days**: Yellow (Review)
- **> 14 days**: Red (Stale - regenerate)

---

### SavingsTracker Component
**File**: `frontend/src/components/right-sizing/SavingsTracker.jsx`

**Purpose**: Track cumulative savings from applied recommendations

**Data**:
- Monthly savings chart
- Year-to-date total
- Breakdown by cluster

---

## Policies & Cleanup

### PolicyConfig Component
**File**: `frontend/src/components/policies/PolicyConfig.jsx`

**Purpose**: Configure cluster-specific optimization policies

**APIs Used**:
```javascript
// Get policy for cluster
GET /api/v1/policies/cluster/{clusterId}

// Create new policy
POST /api/v1/policies
  body: {
    cluster_id,
    spot_enabled,
    fallback_on_demand,
    max_spot_price,
    diversification_strategy,
    rebalancing_enabled
  }

// Update policy
PUT /api/v1/policies/{policyId}

// Toggle policy on/off
POST /api/v1/policies/{policyId}/toggle
```

**Configuration Fields**:
- **Spot Enabled**: Use spot instances
- **Fallback On-Demand**: Launch on-demand if spot unavailable
- **Max Spot Price**: Bid limit (% of on-demand price)
- **Diversification Strategy**: CAPACITY_OPTIMIZED / LOWEST_PRICE / BALANCED
- **Rebalancing Enabled**: Auto-replace interruption-prone instances

---

### CleanupPolicies Component
**File**: `frontend/src/components/policies/CleanupPolicies.jsx`

**Purpose**: Configure automated resource cleanup rules

**APIs Used**:
```javascript
// Get cleanup policies
GET /api/v1/governance/policies
  → Returns: { cleanup_policies: {...} }

// Update policies
PATCH /api/v1/governance/policies
  body: { cleanup_policies: {...} }
```

**Policy Types**:

**1. Unused EBS Volumes**:
- Age threshold (days)
- Auto-delete toggle
- Exclude tagged volumes

**2. Unattached EIPs**:
- Grace period (hours)
- Auto-release toggle

**3. Old Snapshots**:
- Retention period (days)
- Keep minimum count

**4. Idle Load Balancers**:
- No traffic threshold (days)
- Auto-delete toggle

**5. Orphaned ENIs**:
- Detached for X days
- Auto-cleanup

**Policy Data Structure**:
```javascript
{
  cleanup_policies: {
    ebs_volumes: {
      enabled: true,
      age_days: 30,
      exclude_tags: ["keep", "production"]
    },
    eips: {
      enabled: true,
      grace_hours: 24
    },
    snapshots: {
      enabled: true,
      retention_days: 90,
      keep_minimum: 3
    }
  }
}
```

---

### TagTemplateManager Component
**File**: `frontend/src/components/policies/TagTemplateManager.jsx`

**Purpose**: Manage tag compliance templates

**Features**:
- Define required tags (e.g., Environment, Owner, CostCenter)
- Set allowed values per tag
- Enforce on resource creation
- Audit non-compliant resources

---

### PermissionMatrix Component
**File**: `frontend/src/components/policies/PermissionMatrix.jsx`

**Purpose**: Visual matrix of role permissions

**Display**:
```
                | VIEW | EDIT | DELETE | APPROVE
----------------|------|------|--------|--------
SUPER_ADMIN     |  ✓   |  ✓   |   ✓    |   ✓
ORG_ADMIN       |  ✓   |  ✓   |   ✓    |   ✓
CLIENT          |  ✓   |  ✓   |   ✓    |   ✓
TEAM_LEAD       |  ✓   |  ✓   |   -    |   ✓
MEMBER          |  ✓   |  -   |   -    |   -
```

**Features**:
- Toggle permissions per role
- Save changes → Update role definitions
- Color-coded cells (green = granted, gray = denied)

---

## Admin Components

### Admin Dashboard (`/admin`)
**File**: `frontend/src/components/admin/AdminDashboard.jsx`

**Tabs**:
1. **Overview** - Platform stats, health
2. **Tenants** - Organization management
3. **Agent Fleet** - Platform-wide agent monitoring
4. **Audit** - System-wide audit logs

**APIs Used**:
- `GET /api/v1/admin/stats` - Platform KPIs
- `GET /api/v1/admin/health` - System health
- `GET /api/v1/admin/organizations` - Tenant list
- `GET /api/v1/admin/agent-fleet` - All agents
- `POST /api/v1/admin/impersonate` - Org impersonation

### AdminAgentFleet
**File**: `frontend/src/components/admin/AdminAgentFleet.jsx`

**Purpose**: Platform-wide agent monitoring table

**APIs Used**:
- `GET /api/v1/admin/agent-fleet` - All agents across all orgs

**Features**:
- Stats cards: Total, Healthy, Warning, Stale
- Search by org/cluster/region
- Status filter dropdown
- CSV export functionality
- Auto-refresh every 30 seconds
- Color-coded heartbeat status

**Data Structure**:
```javascript
{
  cluster_id: "cluster-abc",
  cluster_name: "Production East",
  region: "us-east-1",
  last_heartbeat: "2026-02-17T10:00:00Z",
  agent_version: "v1.4.2",
  organization_name: "Acme Corp",
  organization_id: "org-123"
}
```

### AdminTenantDrilldown
**File**: `frontend/src/components/admin/AdminTenantDrilldown.jsx`

**Purpose**: Detailed organization view modal

**Tabs**:
1. **Overview** - Org info, resource summary
2. **Members** - User list (planned)
3. **Clusters** - Org's clusters
4. **Audit** - Org-specific audit log
5. **Billing** - Stripe info
6. **Agent Health** - Org's agents

**APIs Used**:
- `GET /api/v1/admin/organizations/:id` - Org details
- `GET /api/v1/clusters?organization_id=X` - Org clusters

### AdminImpersonation
**File**: `frontend/src/components/admin/AdminImpersonation.jsx`

**Purpose**: Super admin can impersonate organizations

**APIs Used**:
- `POST /api/v1/admin/impersonate` - Generate scoped JWT

**Flow**:
1. Admin clicks "Impersonate" on org
2. Backend generates 4hr scoped JWT token
3. Stores original token + impersonated token in localStorage
4. Shows persistent banner "Impersonating Org X"
5. All API calls use impersonated token
6. Click "Exit" to restore original token
7. Audit log records impersonation event

---

## AtharvaAI Components

### AtharvaAI Dashboard (`/atharvaai`)
**File**: `frontend/src/pages/AtharvaAiPage.jsx`

**Purpose**: ML-powered pool selection and termination monitoring

**Store**: `frontend/src/store/useAtharvaStore.js`
- Uses `api` instance (not axios)
- All endpoints under `/api/v1/atharvaai/*`

**APIs Used**:
- `POST /api/v1/atharvaai/pools/rankings` - Get ranked pools
- `GET /api/v1/atharvaai/blacklist` - Risky pools
- `GET /api/v1/atharvaai/rebalancing/status` - Rebalancing actions
- `GET /api/v1/atharvaai/interruption-heatmap` - Termination heatmap

**Features**:
- Node template filtering (vCPU, memory, family, AZ)
- ML-scored pool recommendations
- Global blacklist view
- 7×24 interruption heatmap
- Auto-rebalancing status

---

## Resource Hygiene Components

### Cleanup Dashboard (`/cleanup`)
**File**: `frontend/src/components/cleanup/CleanupDashboard.jsx`

**Purpose**: AWS resource hygiene and cost optimization

**APIs Used**:
- `GET /api/v1/hygiene/total-cost` - Total hygiene cost
- `GET /api/v1/hygiene/cost-services` - Service breakdown
- `GET /api/v1/hygiene/scanner/latest` - Latest scan results
- `POST /api/v1/hygiene/scanner/run` - Trigger scan

**Features**:
- Service cost breakdown (EC2, VPC, Security Hub, KMS, Config, S3, EFS)
- Resource scanner with actionable recommendations
- Cleanup policy configuration
- Cost projection with cleanup

**Resource Categories**:
- Unattached EBS volumes
- Orphaned snapshots
- Unused Elastic IPs
- Idle load balancers
- Old S3 objects
- Unused security groups

---

## API Client Architecture

### Base API Client
**File**: `frontend/src/services/api.js`

**Setup**:
```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor: Add auth token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: Handle 401 logout
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.clear();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### API Modules

All API modules follow this pattern:
```javascript
export const exampleAPI = {
  list: (params) => api.get('/endpoint', { params }),
  get: (id) => api.get(`/endpoint/${id}`),
  create: (data) => api.post('/endpoint', data),
  update: (id, data) => api.put(`/endpoint/${id}`, data),
  delete: (id) => api.delete(`/endpoint/${id}`)
};
```

**Available Modules**:
- `authAPI` - Authentication
- `userAPI` - User management
- `clusterAPI` - Cluster operations
- `hibernationAPI` - Hibernation schedules
- `metricAPI` - Metrics and analytics
- `billingAPI` - Billing and subscriptions
- `adminAPI` - Super admin operations
- `atharvaaiAPI` - AtharvaAI features
- `hygieneAPI` - Resource cleanup
- `accountsAPI` - AWS accounts
- `approvalsAPI` - JIT access requests
- `auditAPI` - Audit logs
- `templateAPI` - Optimization templates
- `tagsAPI` - Tag policies

---

## Common Patterns

### Loading States
```javascript
const [loading, setLoading] = useState(true);

useEffect(() => {
  const fetchData = async () => {
    try {
      const res = await api.get('/endpoint');
      setData(res.data);
    } catch (err) {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };
  fetchData();
}, []);

if (loading) return <LoadingSpinner />;
```

### Error Handling
```javascript
try {
  const res = await api.post('/endpoint', data);
  toast.success('Success message');
  return res.data;
} catch (err) {
  const message = err.response?.data?.message || 'Operation failed';
  toast.error(message);
  throw err;
}
```

### Auto-Refresh
```javascript
useEffect(() => {
  const interval = setInterval(() => {
    fetchData();
  }, 30000); // 30 seconds

  return () => clearInterval(interval);
}, []);
```

### Zustand Store Pattern
```javascript
import { create } from 'zustand';

export const useExampleStore = create((set, get) => ({
  // State
  data: null,
  loading: false,
  error: null,

  // Actions
  fetchData: async () => {
    set({ loading: true });
    try {
      const res = await api.get('/endpoint');
      set({ data: res.data, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  updateData: (updates) => {
    set({ data: { ...get().data, ...updates } });
  }
}));
```

---

## Best Practices

### 1. Always Use Real APIs
- ✅ DO: `const res = await clusterAPI.list()`
- ❌ DON'T: Hardcoded mock data

### 2. Use API Client Modules
- ✅ DO: `import { api } from '../services/api'`
- ❌ DON'T: `import axios from 'axios'` directly in components

### 3. Handle Loading & Errors
- Always show loading state
- Use toast notifications for errors
- Provide fallback UI

### 4. Follow Component Structure
```
Component.jsx
├── Imports
├── Constants
├── Main Component
│   ├── State hooks
│   ├── useEffect hooks
│   ├── Handler functions
│   ├── Render logic
└── Export
```

### 5. Responsive Design
- Use Tailwind's responsive classes (`md:`, `lg:`)
- Mobile-first approach
- Test on all screen sizes

### 6. Accessibility
- Use semantic HTML
- Add ARIA labels
- Keyboard navigation support
- Color contrast ratios

---

## File Structure

```
frontend/src/
├── components/
│   ├── dashboard/
│   │   ├── widgets/           # Dashboard widgets
│   │   ├── widgetRegistry.js  # Widget mapping
│   │   └── roleDefaults.js    # Role-based layouts
│   ├── hibernation/           # Hibernation components
│   ├── cluster/               # Cluster components
│   ├── admin/                 # Admin components
│   ├── cleanup/               # Resource hygiene
│   ├── atharvaai/             # AtharvaAI components
│   ├── settings/              # Settings tabs
│   └── shared/                # Reusable components
├── pages/                     # Page components
├── store/                     # Zustand stores
├── services/
│   └── api.js                 # API client
├── hooks/                     # Custom hooks
└── utils/                     # Utility functions
```

---

## Updates Log

**2026-02-17 (Latest)**:
- **COMPLETED**: Added 8 missing component sections to documentation
  - **Approvals & JIT Access**: Complete JIT workflow, ticket lifecycle, role-based tabs
  - **Templates**: TemplateBuilder and TemplateList with configuration tabs
  - **Governance & Policies**: ProtectedButton, usePermission hook, JIT enforcement
  - **Audit Log**: Immutable trail with filters, diff viewer, export
  - **Authentication**: Login, Signup, InviteAcceptance flows
  - **Onboarding**: 4-step AWS connection wizard
  - **Right-Sizing**: EC2 optimization recommendations with batch apply
  - **Policies & Cleanup**: CleanupPolicies, TagTemplateManager, PermissionMatrix
- **FIXED**: Save Schedule button now clickable and working
  - Removed blocking validation for empty rules
  - Filter empty rules before matrix conversion
  - Improved button UX with proper disabled states
- Enhanced Hibernation Page layout with better sizing
  - Increased padding from p-6 to p-8
  - Added min-height constraints to all components
  - Improved header styling with shadows and borders
- Added comprehensive Teams & Permissions documentation
  - Verified MembersTab uses real organizationAPI
  - Verified TeamsTab uses real teamAPI
  - Documented all team management endpoints
- Confirmed AtharvaAI components use real APIs (not hardcoded data)

**2026-02-17 (Earlier)**:
- Added SpendForecastWidget and AgentStatusWidget to dashboard
- Registered new widgets in widgetRegistry and roleDefaults
- Fixed useAtharvaStore.js axios errors (replaced with api)
- Created AdminAgentFleet component for platform-wide monitoring
- Added AdminImpersonation for org context switching
- Completed changelogic.md implementation (14/14 tasks)

**Previous**:
- Integrated Cost Explorer for invoice-accurate billing
- Enhanced Resource Hygiene with service-level cost breakdown
- Added hibernation strategies (Namespace Sleep, Nuclear, Snapshot & Restore)
- Implemented visual schedule editor with 168-hour grid
