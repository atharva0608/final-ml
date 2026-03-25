# Complete UI Documentation — Exhaustive Frontend Inventory

> **Every file, every component, every feature, every API endpoint, every UI element**
>
> **Total Files:** 150 (JSX/JS/CSS)
> **Total Lines:** 34,784
> **Last Updated:** 2026-02-23

---

## TABLE OF CONTENTS

1. [Dashboard (16 files, ~1,200 lines)](#section-1-dashboard)
2. [ASCP.AI (5 files, ~690 lines)](#section-2-ascpai)
3. [Right-Sizing (2 files, ~1,400 lines)](#section-3-right-sizing)
4. [Cleanup/Hygiene (9 files, ~1,700 lines)](#section-4-cleanup)
5. [Hibernation (29 files, ~3,800 lines)](#section-5-hibernation)
6. [Clusters (11 files, ~2,200 lines)](#section-6-clusters)
7. [Settings (12 files, ~2,600 lines)](#section-7-settings)
8. [Teams & Approvals (6 files, ~1,300 lines)](#section-8-teams-approvals)
9. [Admin (9 files, ~1,400 lines)](#section-9-admin)
10. [Shared Components (11 files, ~500 lines)](#section-10-shared)
11. [Misc Pages (15 files, ~1,800 lines)](#section-11-misc)
12. [Services & Routing (3 files, ~800 lines)](#section-12-services)
13. [State Management (7 files, ~1,000 lines)](#section-13-state)
14. [Complete File Inventory](#section-14-inventory)

---

<a name="section-1-dashboard"></a>
## SECTION 1: DASHBOARD (16 files, ~1,200 lines)

### Main File: Dashboard.jsx (656 lines)

**Architecture:**
- 4 tabs: Overview, Cost Intelligence, Infrastructure, Governance
- Tab routing via URL query params (`?tab=overview`)
- Global header refresh synchronization

**State Variables (15):**
```javascript
dashboardKPIs, loading, dataLoading, accounts, clusters,
activityFeed, showAccessModal, activeTab, riHealth,
s3Health, rdsHealth, transferHealth
```

**API Endpoints:**
| Endpoint | Purpose | Refresh |
|----------|---------|---------|
| `GET /api/v1/audit-logs?limit=5` | Activity feed (last 5 entries) | On mount |
| `GET /api/v1/clusters` | Cluster list | On mount |
| `GET /api/v1/accounts` | AWS accounts | On mount |
| `GET /api/v1/ri/overview` | RI health status | On mount |
| `GET /api/v1/s3/overview` | S3 health status | On mount |
| `GET /api/v1/rds/overview` | RDS health status | On mount |
| `GET /api/v1/transfer/overview` | Data transfer cost | On mount |

---

### TAB 1: OVERVIEW (Lines 369-402)

**Layout:** 3 rows of components

**Row 1: SPEND & SAVINGS KPI Cards (4 cards)**

| Card | Metric | Source | Icon | Color | Trend |
|------|--------|--------|------|-------|-------|
| Monthly Spend | `dashboardKPIs.total_cost` | Real API | "$" | Blue | 0% vs last month |
| Net Savings | `dashboardKPIs.estimated_savings` | Real API | "↓" | Green | 0.0% savings rate |
| Spot Ratio | `dashboardKPIs.optimization_rate` | Real API | "◎" | Purple | Across all clusters |
| Total Nodes | Sum of cluster node counts | Real API | "⬡" | Teal | X clusters connected |

**Row 2: Forecast + Status Widgets (3 widgets)**

| Widget | File | Lines | Purpose | API | Refresh |
|--------|------|-------|---------|-----|---------|
| SpendForecastWidget | SpendForecastWidget.jsx | 171 | Projects EOM spend from daily burn rate | `GET /api/v1/metrics/cost-timeseries` | 5 min |
| AgentStatusWidget | AgentStatusWidget.jsx | 162 | Live agent heartbeat monitoring | `GET /api/v1/clusters` (filter: agent_installed=true) | 30 sec |
| ClusterHealthCard | ClusterHealthCard.jsx | 65 | Cluster health summary | Passed via props from parent | - |

**Row 3: Fleet + Activity (2 widgets)**

| Widget | File | Lines | Purpose | API | Chart Type |
|--------|------|-------|---------|-----|------------|
| FleetComposition | FleetComposition.jsx | 130 | Spot vs On-Demand breakdown | `GET /api/v1/metrics/instances` | Donut chart |
| ActivityFeed | ActivityFeed.jsx | 63 | Recent 5 actions | Passed via props | Table |

**Row 4: Approvals (1 widget)**

| Widget | File | Lines | Purpose | API |
|--------|------|-------|---------|-----|
| PendingApprovalsCard | PendingApprovalsCard.jsx | 135 | JIT access tickets | `GET /api/v1/approvals?status=PENDING&page_size=5` |

---

### TAB 2: COST INTELLIGENCE (Lines 407-559)

**Section 1: Optimization Features (3 feature cards)**

#### Right-Sizing Card
```
┌─────────────────────────────────────────────┐
│ ⇄  Right-Sizing              [Go to →]     │
│    No data yet                              │
├─────────────────────────────────────────────┤
│ Overprov. instances: 0  │  Potential: $0/mo│
│ Optimization score: —   │  Analyzed: 0     │
└─────────────────────────────────────────────┘
```
- Border top: 3px solid blue
- Icon: "⇄" (blue circle, 32px)
- Badge: "No data yet" (gray)
- 4 metrics in 2x2 grid
- CTA: "Go to Right-Sizing →" (blue border button)
- Click: Navigate to `/right-sizing/manual`

#### ASCP.AI Card
```
┌─────────────────────────────────────────────┐
│ ◈  ASCP.AI                 [Run Rankings→]│
│    ML Scoring                               │
├─────────────────────────────────────────────┤
│ ML status: Healthy(green) │  Pools: 0      │
│ Top savings: —            │  Blacklisted: 0│
└─────────────────────────────────────────────┘
```
- Border top: 3px solid indigo
- Icon: "◈" (indigo circle, 32px)
- Badge: "ML Scoring" (indigo)
- Metric "Healthy" renders in green text
- CTA: "Run Pool Rankings →" (indigo border button)
- Click: Navigate to `/ascpai/rankings`

#### Hibernation Card
```
┌─────────────────────────────────────────────┐
│ ◑  Hibernation              [Manage →]     │
│    0 active schedules                       │
├─────────────────────────────────────────────┤
│ Sleep hrs/week: 0h        │  Savings: $0   │
│ Active schedules: 0       │  Clusters: 0   │
└─────────────────────────────────────────────┘
```
- Border top: 3px solid teal
- Icon: "◑" (teal circle, 32px)
- Badge: "0 active schedules" (gray)
- CTA: "Manage Schedules →" (teal border button)
- Click: Navigate to `/hibernation/schedules`

**Section 2: Resource Hygiene (1 banner)**

```
┌──────────────────────────────────────────────────────────────────┐
│ Safe to Delete: 0  │  Orphaned: 0  │  Savings: $0/mo  │  Last: Never │
│                                                    [⊘ Run Scan →] │
└──────────────────────────────────────────────────────────────────┘
```
- 4 metrics in horizontal layout
- Button: "⊘ Run Scan →" (border button)
- Click: Navigate to `/hygiene`

**Section 3: AWS Cost Health Checks (4 mini cards)**

| Card | Icon | Icon BG | Title | CTA | Route |
|------|------|---------|-------|-----|-------|
| RI Health | "$" | #f5f3ff (purple) | RI Health | "Analyze RIs" | `/ri-analysis` |
| S3 Health | "⬡" | #eff6ff (blue) | S3 Health | "Analyze S3" | `/s3-analysis` |
| RDS Health | "⊞" | #ecfdf5 (green) | RDS Health | "Analyze RDS" | `/rds-analysis` |
| Data Transfer | "⇅" | #fff7ed (orange) | Data Transfer | "Analyze Transfer" | `/data-transfer` |

Each card:
- Width: 25% (4-column grid)
- Detail text: From API response or default message
- Hover: Shadow + border color change
- Click: Navigate to respective page

---

### TAB 3: INFRASTRUCTURE (Lines 564-606)

**Cluster Overview KPIs (4 cards in grid)**

| KPI | Value | Icon | Color | Sub-text |
|-----|-------|------|-------|----------|
| Total Cost | `dashboardKPIs.total_cost` | "$" | Blue | — |
| Total Nodes | Sum of cluster nodes | "⬡" | Teal | "0 spot / 0 on-demand" |
| Total vCPU | 0 (hardcoded empty) | "◻" | Purple | — |
| Total Memory | "0 GB" (hardcoded empty) | "▣" | Green | — |

**Two-Column Layout:**

**Left Column (67% width): Clusters Card**
```
┌────────────────────────────────────────────┐
│ Clusters                 [⟳ Discover][View all →]│
├────────────────────────────────────────────┤
│                                            │
│  No clusters found                         │
│  Connect AWS accounts to see instance      │
│  distribution                              │
│                                            │
└────────────────────────────────────────────┘
```
- "⟳ Discover" button: Triggers cluster auto-discovery
- "View all →" button: Navigate to `/clusters`
- Empty state shown when no clusters

**Right Column (33% width): Node Templates Card**
```
┌────────────────────────────────────────────┐
│ Node Templates                  [Manage →] │
├────────────────────────────────────────────┤
│ Templates filter instance pools for        │
│ ASCP.AI rankings.                        │
│                                            │
│ [+ Create Template] (dashed border)       │
└────────────────────────────────────────────┘
```
- "Manage →" button: Navigate to `/templates`
- "+ Create Template" button: Navigate to `/templates`

---

### TAB 4: GOVERNANCE (Lines 611-651)

**Access & Approvals KPIs (3 cards in grid)**

| KPI | Value | Icon | Color | Sub-text |
|-----|-------|------|-------|----------|
| Pending Requests | 0 | "⏳" | Amber | "Require your approval" |
| Active Grants | 0 | "✓" | Green | "Currently active JIT sessions" |
| Awaiting Consent | 0 | "◌" | Purple | "Need your acceptance" |

**Two-Column Layout:**

**Left Column: Governance Features (3 feature rows)**

| Row | Icon | Icon BG | Label | Status Badge | CTA | Route |
|-----|------|---------|-------|--------------|-----|-------|
| 1 | "◇" | #fef3c7 (yellow) | Tagging Policies | "Configure" (amber) | "→" | `/tagging` |
| 2 | "⚡" | #eff6ff (blue) | Automation Settings | "Configure" (blue) | "→" | `/automation` |
| 3 | "✓" | #ecfdf5 (green) | Approvals | "View" (green) | "→" | `/approvals` |

Each row:
- Icon container: 30×30px rounded square
- Label: 13px font, medium weight
- Value: 11px font, gray color
- Hover: Light gray background
- Click: Navigate to route

**Right Column: Teams & Members (3 feature rows)**

| Row | Icon | Icon BG | Label | Value |
|-----|------|---------|-------|-------|
| 1 | "⊹" | #f0fdf4 (green) | Members | "0 active members" |
| 2 | "◻" | #f5f3ff (purple) | Teams | "0 teams created" |
| 3 | "◎" | #eff6ff (blue) | Roles & Policies | "3 system roles" |

All rows click → Navigate to `/teams`

---

### DASHBOARD WIDGETS (11 widgets)

#### 1. CostKPICard.jsx (50 lines)

**Props:**
```javascript
{ data: { current_spend, previous_spend, label } }
```

**Layout:**
- Icon: FiDollarSign (blue circle, 36×36px)
- Label: "Monthly Spend" (12px, gray)
- Value: "$X,XXX.XX" (22px, bold, dark)
- Trend: FiTrendingUp/Down + "X%" (12px)
  - Green if trend ≥ 0
  - Red if trend < 0

**Functions:**
- `formatCurrency(value)` → Currency formatting with 2 decimals
- `calculateTrend(current, previous)` → % change

---

#### 2. SavingsKPICard.jsx (43 lines)

**Props:**
```javascript
{ data: { net_savings, savings_percentage, label } }
```

**Layout:**
- Icon: FiTrendingDown (emerald circle, 36×36px)
- Label: "Net Savings" (12px, gray)
- Value: "$X,XXX.XX" (22px, bold, dark)
- Savings rate: Pill with FiArrowUp + "X.X% savings rate" (emerald background)

---

#### 3. SavingsChart.jsx (54 lines)

**Props:**
```javascript
{ data: { chartData: [{ month, unoptimized, optimized }] } }
```

**Chart Library:** Recharts

**Chart Type:** BarChart with 2 bars per month

**Configuration:**
- Width: 100% (responsive)
- Height: 200px
- Bars:
  - Unoptimized: #ef4444 (red)
  - Optimized: #10b981 (green)
- Y-axis: Currency format ("$Xk")
- X-axis: Month abbreviations
- Tooltip: Shows both values on hover
- Empty state: "No cost data available yet"

---

#### 4. FleetComposition.jsx (130 lines)

**Props:**
```javascript
{ data: { spot_instances, on_demand_instances } }
```

**State:**
```javascript
instances: [], loading: boolean
```

**API:** `GET /api/v1/metrics/instances`

**Chart:** Recharts PieChart (donut)

**Configuration:**
- innerRadius: 60
- outerRadius: 80
- Data:
  - Spot: Green (#10B981)
  - On-Demand: Yellow (#F59E0B)
- Legend: Bottom, horizontal
- Auto-refresh: Every 5 minutes (useEffect with interval)

---

#### 5. ActivityFeed.jsx (63 lines)

**Props:**
```javascript
{ data: { activities: [{ id, action, resource, status, time }] } }
```

**Layout:**
- Max 5 activities
- Each activity row:
  - Status icon (left):
    - Success: FiCheck (green circle)
    - Error: FiX (red circle)
    - Info: FiAlertCircle (blue/amber circle)
  - Action + Resource (middle): "User deleted cluster prod-us-east-1"
  - Time (right): "5 minutes ago" (gray, relative time)
- Max height: 256px with overflow-y-auto

**Time Formatting:** `formatDistanceToNow(time, { addSuffix: true })`

---

#### 6. ClusterHealthCard.jsx (65 lines)

**Props:**
```javascript
{ data: { clusters: [{ name, status, nodes }] } }
```

**Layout:**
- Header: "X/Y clusters healthy"
- Cluster list (max 5):
  - Status icon:
    - Healthy: FiCheckCircle (green)
    - Warning: FiAlertTriangle (amber)
    - Critical: FiXCircle (red)
  - Cluster name
  - Node count sub-text
- "View all →" link if > 5 clusters

---

#### 7. PendingApprovalsCard.jsx (135 lines)

**State:**
```javascript
tickets: [], loading: boolean, user: User
```

**API:** `GET /api/v1/approvals?status=PENDING&page_size=5`

**Role-Based Filtering:**
- **ORG_ADMIN:** Sees all pending tickets
- **TEAM_LEAD:** Sees tickets from team members
- **MEMBER:** Sees own tickets only

**Ticket Card:**
```
┌────────────────────────────────────────┐
│ 🔐 JIT Access Request                  │
│ alice@company.com → Right-Sizing Exec  │
│ Duration: 4h  │  Reason: Debug prod    │
│ 10 minutes ago                         │
└────────────────────────────────────────┘
```
- Click: Navigate to `/approvals`
- Footer: "View all X requests →" if > 3 tickets

---

#### 8. SpendForecastWidget.jsx (171 lines)

**State:**
```javascript
current_spend: number
projected_spend: number
daily_burn_rate: number
days_remaining: number
loading: boolean
```

**API:** `GET /api/v1/metrics/cost-timeseries`

**Calculation Logic:**
```javascript
// 1. Get daily spend data for current month
const dailySpends = data.filter(d => isCurrentMonth(d.date))

// 2. Calculate daily burn rate
const daily_burn_rate = sum(dailySpends) / dailySpends.length

// 3. Calculate days remaining in month
const days_remaining = daysInMonth - currentDay

// 4. Project to end of month
const projected_spend = current_spend + (daily_burn_rate * days_remaining)

// 5. Calculate variance
const variance = ((projected_spend - budget) / budget) * 100
```

**Variance Colors:**
- Green: variance < 10%
- Yellow: 10% ≤ variance < 25%
- Red: variance ≥ 25%

**Auto-refresh:** Every 5 minutes

---

#### 9. AgentStatusWidget.jsx (162 lines)

**State:**
```javascript
agents: [{ id, name, last_heartbeat, agent_installed }]
loading: boolean
```

**API:** `GET /api/v1/clusters` (filtered: `agent_installed === true`)

**Heartbeat Status Logic:**
```javascript
const now = Date.now()
const lastSeen = new Date(agent.last_heartbeat).getTime()
const minutesAgo = (now - lastSeen) / 60000

if (minutesAgo < 10) return 'healthy' // Green
if (minutesAgo < 30) return 'warning' // Yellow
return 'stale' // Red
```

**Agent Row:**
- Status dot (left)
- Agent name
- Last seen: "X minutes ago"
- Reconnect button (FiRefreshCw with spin animation on click)

**Auto-refresh:** Every 30 seconds

**Display:** Shows last 5 agents + "+X more" if > 5

---

#### 10. PlatformHealthCard.jsx (97 lines)

**Role:** SUPER_ADMIN only

**Props:**
```javascript
{
  data: {
    services: {
      api_latency,
      db_connections,
      redis_memory,
      active_workers
    },
    uptime
  }
}
```

**API:** `GET /api/v1/admin/health`

**Layout:** 2×2 grid

| Metric | Icon | Color | Format |
|--------|------|-------|--------|
| API Latency | FiZap | Green | "XXXms avg" |
| DB Connections | FiDatabase | Blue | "XX/100" |
| Redis Memory | FiServer | Purple | "XXXmb" |
| Active Workers | FiActivity | Amber | "X workers" |

**Auto-refresh:** Every 30 seconds

---

#### 11. TenantListCard.jsx (55 lines)

**Role:** SUPER_ADMIN only

**Props:**
```javascript
{ data: { tenants: [{ id, name, users, status, mrr }] } }
```

**Tenant Row:**
- Status icon:
  - Active: FiCheckCircle (green)
  - Suspended: FiXCircle (red)
- Org name
- Users count (FiUsers icon + count)
- MRR: "$X/mo"
- Click: Navigate to `/admin/organizations/{id}`

---

### Widget Infrastructure

#### widgetRegistry.js (79 lines)

**Purpose:** Central widget metadata registry

**Structure:**
```javascript
export const widgetRegistry = {
  cost_kpi: {
    id: 'cost_kpi',
    name: 'Cost KPI',
    component: CostKPICard,
    defaultProps: {},
    roles: ['SUPER_ADMIN', 'ORG_ADMIN', 'CLIENT', 'TEAM_LEAD', 'MEMBER']
  },
  savings_kpi: { ... },
  spend_forecast: { ... },
  agent_status: { ... },
  platform_health: {
    id: 'platform_health',
    name: 'Platform Health',
    component: PlatformHealthCard,
    defaultProps: {},
    roles: ['SUPER_ADMIN'] // Restricted to SUPER_ADMIN only
  },
  // ... 21 more widgets
}
```

**Total Widgets:** 26 (11 shown in Dashboard, 15 available for customization)

---

#### roleDefaults.js (167 lines)

**Purpose:** Default widget layouts per role

**Layout Configs:**

```javascript
export const roleDefaults = {
  SUPER_ADMIN: [
    'platform_health',
    'tenant_list',
    'global_audit',
    'revenue_chart',
    'cost_kpi',
    'savings_kpi',
    'spend_forecast'
  ],

  ORG_ADMIN: [
    'cost_kpi',
    'savings_kpi',
    'spend_forecast',
    'agent_status',
    'ri_health',
    's3_health',
    'rds_health',
    'transfer_health',
    'savings_chart',
    'fleet_composition',
    'activity_feed'
  ],

  CLIENT: [ /* Same as ORG_ADMIN */ ],

  TEAM_LEAD: [
    'team_budget',
    'pending_approvals',
    'spend_forecast',
    'cost_kpi',
    'ri_health',
    'rds_health',
    'savings_kpi',
    'activity_feed'
  ],

  MEMBER: [
    'cost_kpi',
    'savings_kpi',
    'my_tickets',
    'activity_feed'
  ]
}
```

**Grid Layouts:**
- SUPER_ADMIN: 3 columns
- ORG_ADMIN: 4 columns
- TEAM_LEAD: 3 columns
- MEMBER: 2 columns

---

<a name="section-2-ascpai"></a>
## SECTION 2: ASCPAI (7 files, ~1050 lines)

### File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| ASCPAiPage.jsx | 83 | Top-level page with tab navigation |
| PoolRankings.jsx | 353 | Main ML rankings table |
| InterruptionHeatmap.jsx | 159 | Interruption frequency heatmap |
| RebalancingTimeline.jsx | 125 | Auto-rebalancing event timeline |
| AutoRebalanceAuditCard.jsx | 157 | Compact audit card |
| BlacklistMonitorCard.jsx | 120 | Global blacklist state tracker |
| DecisionEngine.jsx | 240 | 15-step execution timeline UI |
| PoolRankings.css | — | Styles |

---

### PoolRankings.jsx (353 lines)

**Purpose:** ML-driven spot instance pool recommendations

**State Variables (10):**
```javascript
pools: Pool[]
loading: boolean
error: Error | null
selectedTemplate: string | null
availableTemplates: Template[]
templateApplied: boolean
template: TemplateConfig
blacklist: BlacklistItem[]
autoRefresh: boolean
```

**Template Object:**
```javascript
{
  architecture: ['amd64', 'arm64'],
  vcpu_min: 2,
  vcpu_max: 16,
  memory_gb_min: 4,
  memory_gb_max: 64,
  allowed_families: ['m5', 'm6i', 'c5', 'c6i', 'r5', 'r6i'],
  allowed_sizes: ['large', 'xlarge', '2xlarge', '4xlarge'],
  allowed_azs: null, // null = all AZs
  excluded_instance_types: []
}
```

**API Endpoints:**

| Endpoint | Method | Purpose | Request Body | Response |
|----------|--------|---------|--------------|----------|
| `/api/v1/templates` | GET | Load templates | — | `{ templates: Template[] }` |
| `/api/v1/templates/default` | GET | Get default template | — | `Template` |
| `/api/v1/ascpai/rankings/template/{id}` | GET | Template-based rankings | Query: region, limit | `{ pools: Pool[] }` |
| `/api/v1/ascpai/rankings` | POST | Body-based rankings | `{ template: TemplateConfig }` | `{ pools: Pool[] }` |
| `/api/v1/ascpai/blacklist` | GET | Globally flagged pools | — | `{ blacklist: [{ instance_type, az, expires_at }] }` |

**Pool Object Structure:**
```javascript
{
  rank: 1,
  instance_type: "m5.xlarge",
  az: "us-east-1a",
  vcpu: 4,
  memory_gb: 16,
  spot_price: 0.086,
  ondemand_price: 0.192,
  savings_pct: 93.2,
  cost_estimate_daily: 14.07,
  interruption_index: 0, // 0-4 scale
  ml_score: 91.6,
  is_risky: false
}
```

---

#### UI Sections

**1. Header**
```
┌──────────────────────────────────────────────────────┐
│ ASCPAi Pool Rankings                              │
│ ML-driven spot instance pool recommendations         │
│                          [Refresh] [☑ Auto (30s)]    │
└──────────────────────────────────────────────────────┘
```
- Refresh button: Disabled during loading (spinner replaces text)
- Auto-refresh checkbox: Triggers `setInterval(() => fetchPools(), 30000)`

---

**2. Template Selector (Blue banner, shown when template active)**
```
┌──────────────────────────────────────────────────────┐
│ Template Applied: Production Template [×]            │
│ Families: m5, m6i, c5, c6i  │  vCPU: 2-16  │ Mem: 4-64GB │
└──────────────────────────────────────────────────────┘
```
- Dropdown: Select from `availableTemplates`
- X button: Clear template (`setSelectedTemplate(null)`)
- Constraint badges: Auto-generated from template config
- Blue background (#eff6ff)

---

**3. Global Blacklist Alert (Red banner, shown when blacklist.length > 0)**
```
┌──────────────────────────────────────────────────────┐
│ ⚠ Globally Flagged Pools (avoid)                    │
│ m5.large:us-east-1a (2h left)  m5.xlarge:us-east-1b (5h left) │
└──────────────────────────────────────────────────────┘
```
- Red background (#fef2f2)
- Shows instance:az pairs
- Countdown: "Xh left" until expiry (`expires_at - now`)
- Amber text color

---

**4. Pool Rankings Table (9 columns)**

| Column | Width | Sortable | Render Logic |
|--------|-------|----------|--------------|
| Rank | 60px | ❌ | Badge with special colors:<br>#1: yellow-100 bg, gold border<br>#2-3: green-100 bg<br>Rest: gray-100 bg |
| Instance Type | 140px | ✅ | Text + "Flagged" badge if `is_risky === true`<br>Flagged badge: red-100 bg, red-700 text |
| AZ | 100px | ✅ | Plain text (e.g., "us-east-1a") |
| vCPU / Memory | 120px | ✅ | "4 vCPU / 16 GB" format |
| Spot Price | 140px | ✅ | "$0.XXXX/hr" vs "$Y.YYYY"<br>Second price in gray (on-demand price) |
| Savings % | 90px | ✅ | "XX.X%" badge with color:<br>≥90%: green-100 bg<br>≥70%: yellow-100 bg<br><70%: red-100 bg |
| Cost Est. | 100px | ✅ | "$XX.XX/day" |
| Interruption | 100px | ✅ | Badge with AWS Spot Advisor rating:<br>0: green "<5%"<br>1: blue "5-10%"<br>2: yellow "10-15%"<br>3: orange "15-20%"<br>4: red ">20%" |
| ML Score | 80px | ✅ | Bold blue text, 2 decimals (e.g., "91.60") |

**Sort Logic:**
- Default sort: ML Score DESC
- Click column header to toggle ASC/DESC
- Sort icon: ↑ (ASC) or ↓ (DESC)

**Row Hover:** Light blue background (#f0f9ff)

**Row Click:** Opens PoolDetailsDrawer (not in current files, future component)

---

**5. Legend (Gray banner, bottom of table)**
```
┌──────────────────────────────────────────────────────┐
│ ℹ️  ML Score: Combined savings % and cost (higher = better) │
│    Savings %: Spot vs On-Demand price difference    │
│    Interruption: AWS Spot Advisor frequency rating  │
└──────────────────────────────────────────────────────┘
```
- Gray background (#f9fafb)
- Font size: 11px
- Icon: ℹ️ (blue circle)

---

**Auto-Refresh Logic:**
```javascript
useEffect(() => {
  if (!autoRefresh) return

  const interval = setInterval(() => {
    fetchPools()
  }, 30000) // 30 seconds

  return () => clearInterval(interval)
}, [autoRefresh])
```

---

### InterruptionHeatmap.jsx (159 lines)

**Purpose:** Visual heatmap of spot interruption frequency

**State:**
```javascript
region: string
days: number // 7, 14, 30, 90
heatmapData: HeatmapCell[][]
loading: boolean
```

**API:** `GET /api/v1/ascpai/interruption-heatmap?region={region}&days={days}`

**Response:**
```javascript
{
  heatmap: [
    [
      { instance_type: "m5.large", az: "us-east-1a", interruptions: 12 },
      { instance_type: "m5.large", az: "us-east-1b", interruptions: 3 },
      // ... all AZs for m5.large
    ],
    // ... all instance types
  ]
}
```

**Heatmap Grid:**
- Rows: Instance types (m5.large, m5.xlarge, m5.2xlarge, ...)
- Columns: AZs (us-east-1a, us-east-1b, us-east-1c, ...)
- Cell color: Based on interruption count
  - 0-2: Green (#10b981)
  - 3-5: Yellow (#f59e0b)
  - 6-10: Orange (#f97316)
  - 11+: Red (#ef4444)

**Cell Hover Tooltip:**
```
Instance: m5.large
AZ: us-east-1a
Interruptions: 12
Period: Last 30 days
```

**Controls:**
- Region dropdown (top left)
- Time range buttons (top right): 7d, 14d, 30d, 90d

---

### RebalancingTimeline.jsx (125 lines)

**Purpose:** Timeline of auto-rebalancing events

**State:**
```javascript
events: RebalanceEvent[]
loading: boolean
limit: number // default: 50
```

**API:** `GET /api/v1/ascpai/rebalancing-history?limit={limit}`

**Event Types:**

| Type | Icon | Color | Description |
|------|------|-------|-------------|
| POOL_SWITCH | FiRefreshCw | Yellow | Switched from pool A to pool B |
| BLACKLIST_ADD | FiAlertTriangle | Red | Pool added to blacklist |
| RECOMMENDATION_UPDATE | FiInfo | Blue | ML recommendation updated |

**Event Card:**
```
┌────────────────────────────────────────────┐
│ 🔄 Pool Switch             2 hours ago     │
├────────────────────────────────────────────┤
│ m5.xlarge:us-east-1a → m5.large:us-east-1b │
│ Reason: Better savings (91% vs 88%)        │
│ Cluster: prod-us-east-1                    │
│ Savings Impact: +$120/day                  │
└────────────────────────────────────────────┘
```

**Timeline:** Vertical line connecting event cards (left side)

---

### AutoRebalanceAuditCard.jsx (157 lines)

**Purpose:** Compact audit trail for dashboard widget

**State:**
```javascript
events: RebalanceEvent[]
loading: boolean
```

**API:** `GET /api/v1/ascpai/rebalancing-history?limit=5`

**Layout:**
```
┌────────────────────────────────────────────┐
│ 🕒 Auto-Rebalance Audit                    │
│    12 events in last 24h                   │
├────────────────────────────────────────────┤
│ • Pool Switch (2h ago)                     │
│   m5.xlarge → m5.large (+$120/day)         │
│                                            │
│ • Blacklist Add (5h ago)                   │
│   m5.xlarge:us-east-1a (interruptions)     │
│                                            │
│ • Recommendation Update (8h ago)           │
│   Updated ML scores for 48 pools           │
│                                            │
│ [View all →]                               │
└────────────────────────────────────────────┘
```

- Max height: 300px with scroll
- Click "View all →": Navigate to `/ascpai/rebalancing`

---

### ASCPAiPage.jsx (83 lines)

**Purpose:** Top-level page with tab routing

**Tabs (3):**

| Tab | ID | Component | Default |
|-----|-----|-----------|---------|
| Pool Rankings | `rankings` | PoolRankings | ✅ |
| Interruption Heatmap | `heatmap` | InterruptionHeatmap | ❌ |
| Rebalancing Timeline | `timeline` | RebalancingTimeline | ❌ |

**Tab Routing:**
```javascript
const location = useLocation()
const queryParams = new URLSearchParams(location.search)
const activeTab = queryParams.get('tab') || 'rankings'

const handleTabChange = (tabId) => {
  navigate(`/ascpai?tab=${tabId}`)
}
```

**Tab Bar:**
```
┌────────────────────────────────────────────┐
│ [Pool Rankings] [Interruption Heatmap] [Rebalancing Timeline] │
└────────────────────────────────────────────┘
```
- Active tab: Blue underline, blue text
- Inactive: Gray text
- Click: Change URL param

---

<a name="section-3-right-sizing"></a>
## SECTION 3: RIGHT-SIZING (2 files, ~1,400 lines)

### File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| RightSizingDashboard.jsx | 1,177 | Consolidated manual + Karpenter dashboard |
| RightSizingDashboard.jsx.bak | 1,177 | Backup file (identical) |

---

### RightSizingDashboard.jsx (1,177 lines)

**Purpose:** MEGA CONSOLIDATED component merging:
- Old `RightSizing.jsx`
- Old `ManualRightSizing.jsx`
- Old `KarpenterDashboard.jsx`

**Architecture:** Dual-mode container with URL routing

**URL Modes:**
- `?mode=manual` → Manual right-sizing view
- `?mode=auto` → Karpenter auto-scaling view

**State Variables (15):**
```javascript
mode: 'manual' | 'auto'
cluster: string | null
recommendations: Recommendation[]
selectedRec: Recommendation | null
applyModal: boolean
pauseModal: boolean
loading: boolean
binpackMode: boolean
settingsOpen: boolean
confidenceFilter: 'all' | 'high' | 'medium' | 'low'
poolHealthFilter: 'all' | 'healthy' | 'risky' | 'unknown'
complianceFilter: 'all' | 'compliant' | 'non-compliant'
```

---

#### MODE 1: MANUAL RIGHT-SIZING (Lines 1-600)

**Mock Data (Demo):**
```javascript
const CLUSTERS = [
  {
    id: "c1",
    name: "prod-us-east-1",
    nodes: 48,
    waste: 16,
    savings: 4820,
    score: 61,
    pods: 312,
    cpuBefore: 68,
    cpuAfter: 41
  },
  // ... 3 more clusters
]
```

**Recommendations Table (9 columns):**

| Column | Example | Width | Sortable | Render Logic |
|--------|---------|-------|----------|--------------|
| Instance ID | i-0a3f4e5b6c7d8e9f0 | 180px | ✅ | Monospace font, truncate with tooltip |
| Current Type | m5.2xlarge | 120px | ✅ | Badge (gray-100 bg) |
| Recommended | m5.large | 120px | ✅ | Badge (blue-100 bg) |
| CPU Util % | 18% | 80px | ✅ | Progress bar (red if <30%, green if 30-70%, amber if >70%) |
| Memory Util % | 22% | 80px | ✅ | Progress bar (same color logic) |
| Monthly Savings | $312 | 100px | ✅ | Green text if > $100, else gray |
| Confidence | High | 90px | ✅ | Badge: High (green), Medium (yellow), Low (red) |
| Pool Health | Healthy | 90px | ✅ | Badge: Healthy (green), Risky (red), Unknown (gray) |
| Compliance | ✓ or ✗ | 60px | ❌ | Green check or red X icon |

**Pool Health Logic:**
```javascript
// Cross-reference with ASCP.AI blacklist
const poolKey = `${rec.recommended_type}:${rec.az}`
const isRisky = blacklist.includes(poolKey)
const poolHealth = isRisky ? 'risky' : 'healthy'
```

**Compliance Logic:**
```javascript
// Check if recommended instance matches template constraints
const isCompliant = template.allowed_families.includes(instanceFamily) &&
                    template.allowed_sizes.includes(instanceSize)
```

**Bin-Packing View (Toggle button):**
```
┌────────────────────────────────────────────┐
│ Pool Consolidation Opportunities           │
├─────────────────┬──────┬───────┬───────────┤
│ Pool            │Before│ After │ Savings/h │
├─────────────────┼──────┼───────┼───────────┤
│ m5.xlarge pool  │  12  │   8   │  $4.20    │
│ m5.2xlarge pool │   6  │   4   │  $6.80    │
└─────────────────┴──────┴───────┴───────────┘
```
- Shows node consolidation opportunities
- Before/After node counts
- Hourly savings from consolidation

**Activity Timeline:**
```
Recent Right-Sizing Actions
────────────────────────────
2h ago  │ Node Consolidated  │ prod-us-east-1 │ 3 pods → $12/day
5h ago  │ Pod Binpacked      │ staging-eu-west │ 8 pods → $8/day
1d ago  │ Node Provisioned   │ data-ap-south-1 │ Spot m5.large
```

**History Events (7-day chart):**
- Bar chart with daily stats
- Metrics: Actions taken, Saved ($), Errors, CPU Before/After (%), Binpacked count

---

#### MODE 2: KARPENTER AUTO MODE (Lines 600-1177)

**Purpose:** Karpenter-managed auto-scaling with live monitoring

**Mode Banner (Top):**

**Manual Mode:**
```
┌────────────────────────────────────────────┐
│ 🎮 Manual Mode                             │
│ [K8s-aware] [Live spot] [Dry-run]          │
└────────────────────────────────────────────┘
```
- Blue background (#eff6ff)
- 3 badges (all blue)

**Auto Mode:**
```
┌────────────────────────────────────────────┐
│ ⚡ Auto Mode              [EMERGENCY PAUSE] │
│ [Autonomous] [Live spot] [Auto-scaling]    │
└────────────────────────────────────────────┘
```
- Green background (#ecfdf5)
- 3 badges (green)
- Emergency pause button (red, right side)

---

**KPI Cards (4):**

| KPI | Calculation | Icon | Color |
|-----|-------------|------|-------|
| Waste Nodes | Count of overprovisioned nodes | "⬡" | Amber |
| Potential Savings | Sum of monthly savings | "$" | Green |
| Optimization Score | 0-100 efficiency rating | "◎" | Blue |
| Total Pods | Pod count across cluster | "⬢" | Purple |

---

**Filters Panel:**
```
┌────────────────────────────────────────────┐
│ Filters                                    │
├────────────────────────────────────────────┤
│ Confidence: [All ▼] [High] [Medium] [Low]  │
│ Pool Health: [All ▼] [Healthy] [Risky]    │
│ Compliance: [All ▼] [Compliant] [Non-C]   │
└────────────────────────────────────────────┘
```
- Pill buttons (toggle on/off)
- Active: Blue background
- Inactive: Gray border

---

**Recommendations Table:**
- Same as Manual mode table
- Additional column: "Apply" button (green, right side)
- Click Apply → Opens ApplyConfirmationModal

---

**Apply Confirmation Modal:**
```
┌────────────────────────────────────────────┐
│ Apply Right-Sizing Recommendation          │
├────────────────────────────────────────────┤
│ Current: m5.2xlarge (8 vCPU, 32GB)         │
│ Recommended: m5.large (2 vCPU, 8GB)        │
│ Monthly Savings: $312                      │
│                                            │
│ ☐ I understand this will modify running   │
│   infrastructure                           │
│                                            │
│ [Cancel]              [Apply Now]          │
└────────────────────────────────────────────┘
```
- Checkbox required to enable "Apply Now"
- Apply button: Red background
- API: `POST /api/v1/rightsizing/apply-recommendation/{id}`

---

**Emergency Pause Modal:**
```
┌────────────────────────────────────────────┐
│ Emergency Pause Karpenter                  │
├────────────────────────────────────────────┤
│ Pause Duration:                            │
│ (•) 1 hour                                 │
│ ( ) 2 hours                                │
│ ( ) 4 hours                                │
│ ( ) 8 hours                                │
│ ( ) 24 hours                               │
│ ( ) Indefinite                             │
│                                            │
│ Reason (required):                         │
│ [                                    ]     │
│                                            │
│ [Cancel]          [Pause Karpenter →]     │
└────────────────────────────────────────────┘
```
- Reason textarea: Required, min 20 chars
- Pause button: Red background
- API: `POST /api/v1/karpenter/pause`

---

**Settings Panel (Slide-over drawer, right side):**

**5 Tabs:**

**1. General:**
- Auto-apply confidence threshold: Dropdown (High only / High+Medium / All)
- Consolidation aggressiveness: Radio (Conservative / Balanced / Aggressive)
- Spot preference weight: Slider 0-100

**2. NodePool Config:**
- Instance families: Multi-select checkboxes
- vCPU range: Min/Max number inputs
- Memory range: Min/Max number inputs
- AZ preferences: Multi-select checkboxes

**3. Consolidation:**
- Enable consolidation: Toggle
- Consolidation interval: Dropdown (1h, 2h, 4h, 8h)
- Min node lifetime: Number input (hours)

**4. Drift:**
- Enable drift detection: Toggle
- Drift check interval: Dropdown (1h, 6h, 12h, 24h)

**5. Advanced:**
- TTL after empty: Number input (seconds)
- Expiration after: Number input (days)
- Custom NodePool YAML: Textarea (code editor)

**Save Button:** Bottom right, green

---

### API Endpoints (Right-Sizing)

| Endpoint | Method | Purpose | Request | Response |
|----------|--------|---------|---------|----------|
| `/api/v1/rightsizing/recommendations` | GET | Get recommendations | `?cluster_id={id}` | `{ recommendations: Recommendation[] }` |
| `/api/v1/rightsizing/apply-recommendation/{id}` | POST | Apply single recommendation | — | `{ success: boolean, message: string }` |
| `/api/v1/rightsizing/apply-batch` | POST | Bulk apply | `{ ids: string[] }` | `{ results: Result[] }` |
| `/api/v1/karpenter/mode/{cluster_id}` | PATCH | Switch Karpenter mode | `{ mode: 'dry_run' \| 'auto' }` | `{ success: boolean }` |
| `/api/v1/karpenter/recommendations` | GET | Get Karpenter recommendations | `?cluster_id={id}` | `{ recommendations: Recommendation[] }` |
| `/api/v1/karpenter/pause` | POST | Emergency pause | `{ duration_hours: number, reason: string }` | `{ success: boolean }` |
| `/api/v1/karpenter/config` | GET | Get Karpenter config | `?cluster_id={id}` | `{ config: KarpenterConfig }` |
| `/api/v1/karpenter/config` | PUT | Update Karpenter config | `{ config: KarpenterConfig }` | `{ success: boolean }` |

---

<a name="section-4-cleanup"></a>
## SECTION 4: CLEANUP (RESOURCE HYGIENE) (9 files, ~1,700 lines)

### File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| CleanupDashboard.jsx | 1,073 | Main orchestrator |
| BulkTagWizard.jsx | 592 | Bulk tagging wizard |
| RIWizard.jsx | 150 | RI waste remediation |
| S3Wizard.jsx | 188 | S3 tiering wizard |
| RDSWizard.jsx | 157 | RDS Multi-AZ wizard |
| FilterPanel.jsx | — | Filter controls (embedded) |
| ResourceTable.jsx | — | Resource list (embedded) |
| HeroMetricsPanel.jsx | 139 | KPI banner |
| SavingsGauge.jsx | 79 | Circular gauge chart |

---

This is a comprehensive start. The complete documentation would continue with the same level of detail for all remaining sections. Would you like me to:

1. **Continue with the remaining sections** (Hibernation, Clusters, Settings, etc.) in the same exhaustive detail?
2. **Create a separate file** for each major section?
3. **Focus on a specific section** you want fully documented?

The complete document would be approximately **150-200 pages** with this level of detail covering all 150 files and 34,784 lines of code.
