# Karpenter Rightsizing Simulation — Complete Technical Documentation

> **Last Updated:** 4 April 2026  
> **Scope:** Full-stack coverage — Frontend UI, Backend Services, Database Models, Redis Caching, Simulation Engine

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [User Actions & UI Walkthrough](#2-user-actions--ui-walkthrough)
3. [User-Configurable Settings](#3-user-configurable-settings)
4. [Frontend Components](#4-frontend-components)
5. [Backend API Endpoints](#5-backend-api-endpoints)
6. [Core Services & Logic](#6-core-services--logic)
7. [Simulation Engine — Deep Dive](#7-simulation-engine--deep-dive)
   - [7.3 5-Pass Pool Selection (with total-cost Pass 0)](#73-5-pass-pool-selection-algorithm)
   - [7.6 Fragmentation Correction (small-cluster aware)](#76-fragmentation-correction)
   - [7.6b Empty Node Cleanup](#76b-empty-node-cleanup)
   - [7.6c Capacity-Aware Pod Batching](#76c-capacity-aware-pod-batching)
8. [RightSizing Service](#8-rightsizing-service)
9. [Optimizer Coordinator](#9-optimizer-coordinator)
10. [Database Models](#10-database-models)
11. [Redis Keys & Caching](#11-redis-keys--caching)
12. [Pydantic Schemas](#12-pydantic-schemas)
13. [End-to-End Request Flow](#13-end-to-end-request-flow)
14. [Safety & Guard Rails](#14-safety--guard-rails)

---

## 1. System Overview

The Karpenter Rightsizing Simulation is a multi-layered optimization system that combines:

- **Pod-Level Rightsizing:** Analyzes historical pod CPU/memory metrics (P95/P99) to recommend reduced resource requests
- **Instance-Level Bin-Packing:** Maps pods onto optimal EC2 instance types using bin-packing logic
- **Karpenter Simulation Engine:** Runs a multi-cycle virtual K8s cluster simulation modeling real Karpenter consolidation behavior
- **Spot ML Pool Ranking:** Integrates machine-learning-based spot pool risk/price ranking for instance selection
- **Optimizer Coordinator:** Prevents oscillation between pool optimization and rightsizing through phased execution

### Architecture Diagram (Simplified)

```
┌──────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                       │
│  ClusterDetails.jsx ── RightSizingDashboard.jsx           │
│  RightSizingKarpenterTab.jsx                              │
│         │                    │                            │
│    Settings Toggles     Recommendations Display           │
└────────┬─────────────────────┬────────────────────────────┘
         │ API Calls           │
         ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│                 BACKEND (FastAPI)                          │
│                                                           │
│  karpenter_routes.py ─── pod_metrics_routes.py            │
│  optimizer_coordinator_routes.py ─── ascpai_routes.py     │
│         │                    │                │           │
│         ▼                    ▼                ▼           │
│  KarpenterService    RightSizingService   SimulationEngine│
│         │                    │                │           │
│         ▼                    ▼                ▼           │
│  OptimizerCoordinator ◄──────┴────────────────┘          │
│         │                                                 │
│    ┌────┴────┐                                            │
│    ▼         ▼                                            │
│  PostgreSQL  Redis                                        │
└──────────────────────────────────────────────────────────┘
```

---

## 2. User Actions & UI Walkthrough

### 2.1 Enabling Rightsizing

**Step 1: Navigate to Cluster Details**
- User selects a cluster from `ClusterList.jsx`
- `ClusterDetails.jsx` opens with cluster overview, node list, and settings panel

**Step 2: Enable Auto Right-Sizing Toggle**
- Toggle: `Auto Right-Sizing` (field: `automation_controls.auto_rightsizing_enabled`)
- If Karpenter is NOT installed → "Karpenter Required" modal appears, polls every 5s for status
- If Karpenter IS installed → toggle activates immediately
- Backend syncs setting to `ClusterOptimizationSettings` table and updates Redis

**Step 3: Optional — Enable Synergy Mode**
- When both `Auto Rebalancing` AND `Auto Right-Sizing` are ON → **Synergy Mode** activates
- Optimization target locks to `"spot"` automatically
- UI shows "Locked to Spot — synergy mode active" badge

### 2.2 Viewing Recommendations — Exact UI Layout

#### A. Auto Mode Banner (Top of Dashboard)

Two-column pill layout:

| Column | Icon | Label | Description |
|--------|------|-------|-------------|
| Left | 🔄 (ON) / ⏸ (OFF) | "Auto Rebalancing ON/OFF" | Current rebalancing state |
| Right | ⚡ (ON) / ⏸ (OFF) | "Auto Rightsizing ON/OFF" | Current rightsizing state |

**Footer (when both ON):** "Combined mode: bin-pack first → ML spot pool selection → Karpenter provisions right-sized spot node → agent migrates workloads"

#### B. Cluster Health & Exposure Bar — KPI Cards

**Cluster Overview Row (5 KPI columns):**

| KPI | Font | Color | Example |
|-----|------|-------|---------|
| **Total Nodes** | Large bold number | Default | `12` |
| **Stateless** | Large bold number | Default | `9` |
| **Stateful** | Large bold number | Grey | `2` |
| **Eligible for Resize** | Large number | Indigo background | `6` |
| **In Cooldown** | Large number | Amber background | `1` |

**Exposure Snapshot (3 placeholders):** Spot vs On-Demand Gauge | AZ Distribution | Instance Family

#### C. Guard & Stability Panel — 6 KPI Cards

| Card | Value | Color/Style |
|------|-------|-------------|
| Cluster Safety Score | "—/100" | Grey badge |
| Rollbacks (24h) | "—" | Grey bg `#f9fafb` |
| Guard Triggers | "—" | Amber text |
| Circuit Breaker | "N/A" | Green box |
| Max Concurrent | "—" | Default |
| Currently Running | "—" | Indigo/primary |
| Queue Length | "—" | Default |

#### D. Stateless Nodes Table — Exact Columns

| # | Column Header | Cell Content | Color / Badge Rules |
|---|--------------|-------------|-------------------|
| 1 | **Node** | Node name | Plain text |
| 2 | **Current Type** | e.g. `m5.xlarge` | Plain text |
| 3 | **CPU / Mem** | e.g. `72% / 58%` | **Red** if >80%, otherwise medium grey |
| 4 | **Bin-Packed Size** | e.g. `m5.large` | Plain text (recommended size) |
| 5 | **Optimal Action** | Strategy badge | ⚠ Scale Up / ✦ Resize + Spot / ↓ Resize Only / ⟳ Spot Pool / ✓ No Change |
| 6 | **Best Spot Pool** | `instance_type`, `az`, `risk_score`, `predicted_savings_pct` | **Hidden when Auto mode ON** |
| 7 | **Savings** | `$XX/mo` | **Green** (savings) or **Red** (cost increase) |
| 8 | **EV** | `XX%` | Expected Value percentage |
| 9 | **Status** | Status badge | See badge table below |
| 10 | **Actionable** | Actionable badge | ✓ Actionable (green) / No Better Pool (grey) / — |
| 11 | **Action** | Button or text | "Auto-managed" (greyed) when auto ON; button when OFF (disabled during cooldown) |

**KPI Summary Bars Above Stateless Table:**

| Bar | Border Color | Content |
|-----|-------------|---------|
| Projected Total Savings | Green top border | Total $/month savings across all eligible |
| Safe to Execute | Indigo top border | Count of ready-to-apply nodes |
| Blocked by Policy | Amber top border | Count of cooldown/blocked nodes |

#### E. Stateful Nodes Table — Exact Columns

**KPI Header (above table, 4 columns):**

| KPI | Color | Example |
|-----|-------|---------|
| Total Stateful Nodes | Default | `2` |
| Eligible for Propose | Default | `1` |
| On-Demand Savings Potential | Green | `$85/mo` |
| Max Downscale Allowed | Amber | `25%` |

**Table Columns:**

| # | Column Header | Cell Content | Color Rules |
|---|--------------|-------------|------------|
| 1 | **Node** | Node name | Plain text |
| 2 | **Current Type** | e.g. `r5.xlarge` | Plain text |
| 3 | **CPU / Mem** | e.g. `45% / 62%` | Red if >80% |
| 4 | **Recommended** | e.g. `r5.large` | Plain text |
| 5 | **On-Demand Savings** | `$XX/mo` | Green text |
| 6 | **Policy Status** | Text label | "Blocked by Policy" (amber) / "Approved by Policy" (green) |
| 7 | **Action** | Button | "Request Approval" or "Propose Resize" |

#### F. Pod-Level Right-Sizing Recommendations Table

**Header Badge:** "Active — Auto-Applying" (green) when auto ON, or "Recommendations Only" (amber) when OFF

| # | Column Header | Cell Content | Format |
|---|--------------|-------------|--------|
| 1 | **Workload** | Controller name + `controller_kind` + replica count sub-text | Bold name, grey sub |
| 2 | **Namespace** | K8s namespace | Plain text |
| 3 | **Current CPU** | Millicores | Plain text |
| 4 | **Rec. CPU** | Recommended millicores | **Green** text |
| 5 | **Current Mem** | MB | Plain text |
| 6 | **Rec. Mem** | Recommended MB | **Green** text |
| 7 | **Savings** | `$XX/mo` (with % if available) | Green |
| 8 | **Action** | Action badge | **REDUCE** (green) / **INCREASE** (amber) / **NO_CHANGE** (grey) |

**Footer Bar (green background):**
- "Total Right-Sizing Savings" label
- Summary: "X reduce · X increase · X no change"
- Large total savings amount

#### G. Execution Plan Tab

| # | Column | Content |
|---|--------|---------|
| 1 | **Order** | Sequential number |
| 2 | **Node** | Node name |
| 3 | **Action** | Resize description |
| 4 | **Est Duration** | Estimated time |
| 5 | **Summary** | Brief description |
| 6 | **Monthly Savings** | Dollar amount |
| 7 | **Status** | "Next in line" badge (APPROVED) / "Pending" |
| 8 | **Actions** | Approve button / Reject button (with reason prompt) |

#### H. History Tab

**KPI Row:**
- Resizes this Month (count)
- Net Savings Generated ($ total)
- Success Rate (%)

**Table:**

| # | Column | Content |
|---|--------|---------|
| 1 | **Executed At** | Timestamp |
| 2 | **Node** | Node name |
| 3 | **Before** | Previous instance type |
| 4 | **After** | New instance type |
| 5 | **Time Taken** | Duration |
| 6 | **Savings** | $/month |
| 7 | **Status** | Success (green badge) / Failed (amber badge) |

#### I. Stateless Detail Modal (Drawer)

Opens when clicking a stateless node row. 4 info cards in 2×2 grid:

| Card | Content |
|------|---------|
| Top Candidate Sizes | Alternative instance types ranked |
| Diversification Check | Family/AZ diversity pass/fail |
| Headroom / Volatility | Applied buffer %, market volatility flag |
| Capacity DryRun / Cooldown | Simulation result, cooldown status |

**Buttons:** "Close" | "Apply Now (Manual Override)" (only shown when auto mode OFF)

#### J. Stateful Proposal Modal

Opens when clicking a stateful node row.

- **Header:** "Submit Manual Resize" with "Stateful" grey badge
- **Warning (amber box):** "Spot pools are strictly locked for stateful workloads. This node will be resized using On-Demand instances."
- **Details (4-row key-value):**
  - Current Type → e.g. `r5.xlarge`
  - Proposed Type → indigo color, e.g. `r5.large`
  - Estimated Savings → green, `$XX/mo`
  - Peak Buffer Margin → percentage
- **Buttons:** "Cancel" | "Submit for Approval" (grey) OR "Apply Resize Now" (primary blue)

### 2.3 Applying Recommendations

| Action | UI Element | API Call |
|--------|-----------|----------|
| Apply single stateless resize | "Apply Now" button per node | `POST /api/v1/optimization/apply/{id}` |
| Apply with validation | "Apply" from detailed drawer | `POST /api/v1/optimization/apply/{id}/validated` |
| Bulk apply all eligible | "Apply All Eligible Resizes" button | `POST /api/v1/optimization/rightsizing/batch-apply` |
| Propose stateful resize | "Request Approval" button | Creates `RightsizingProposal` record |
| Approve/Reject proposal | Execution Plan tab buttons | `POST /optimizer/proposals/{id}/approve` |

### 2.4 UI Status Badges

| Badge | Color | Meaning |
|-------|-------|---------|
| **Scale Up** ⚠ | Red | Node is over-utilised, needs more resources |
| **Resize + Spot** ✦ | Green | Both rightsizing and spot pool migration recommended |
| **Resize Only** ↓ | Blue | Size change recommended, same pool |
| **Spot Pool Only** ⟳ | Teal | Pool switch only, no size change |
| **No Change** ✓ | Grey | Already optimal |
| **Cooldown** | Amber | Blocked by 6h resize or 30min pool cooldown |
| **High Volatility** | Red | Spot prices unstable, skipping |
| **Ready** | Green | Safe to execute |

### 2.5 UI Results Displayed

After simulation runs, the user sees:

```
Karpenter Simulation Results
├── Converged: ✓ (3 cycles)
├── Confidence: 92%
├── Final Nodes: 10 (8 spot, 2 on-demand)
├── Peak Pending Pods: 2
├── Fragmentation Headroom: 8%
└── Monthly Cost Estimate: $X,XXX
```

Per-node recommendation cards show:
- **Current** → **Recommended** instance type transition
- Savings per month ($)
- Expected Value (EV %)
- Confidence level (HIGH / MEDIUM)
- Best spot pool for new size

---

## 3. User-Configurable Settings

### 3.1 Cluster-Level Automation Toggles

| Setting | Field | Default | Effect |
|---------|-------|---------|--------|
| **Auto Rebalancing** | `auto_rebalance_enabled` | `false` | Enables ML-ranked spot pool selection |
| **Auto Right-Sizing** | `auto_rightsizing_enabled` | `false` | Enables pod + instance bin-packing |
| **Optimization Target** | `optimization_target` | `"spot"` | Locked to "spot" when both toggles ON |
| **Diversify Pools** | `diversify_pools` | `false` | Enforce family + AZ diversification |
| **Auto Stateful Rightsizing** | `auto_stateful_rightsizing_enabled` | `false` | Allow resize on stateful workloads |
| **Stateful Require Approval** | `stateful_require_approval` | `true` | Stateful proposals need manual approval |
| **Stateful Max Downscale %** | `stateful_max_downscale_pct` | `25` | Max size reduction for stateful (10–75%) |

### 3.2 Karpenter Configuration Panel

| Setting | Field | Default | Range |
|---------|-------|---------|-------|
| **Strategy** | `strategy` | `"balanced"` | `balanced`, `cost-first`, `performance-first` |
| **Instance Families** | `instance_families` | `["m5","m6i","c5","c6i"]` | Selectable tags: m5, m6i, c5, c6i, t3, t4g, c6g, m6g |
| **Architectures** | `architectures` | `["amd64"]` | `amd64`, `arm64` |
| **Spot Target %** | `spot_target_pct` | `75` | 0–100 slider |
| **Safety Buffer %** | `buffer_pct` | `30` | 10–100 number input |
| **On-Demand Fallback** | `on_demand_fallback` | `true` | Toggle |
| **Min vCPU** | `min_vcpu` | `2` | Instance size floor |
| **Max vCPU** | `max_vcpu` | `16` | Instance size ceiling |
| **Min Memory GiB** | `min_memory_gib` | `4` | Memory floor |
| **Max Memory GiB** | `max_memory_gib` | `64` | Memory ceiling |
| **Consolidation Enabled** | `consolidation_enabled` | `true` | Toggle |
| **Consolidation Threshold %** | `consolidation_threshold_pct` | `60` | Utilization threshold for consolidation |
| **Node Max Lifetime** | `node_max_lifetime_days` | `7` | Days before forced rotation |
| **Cost Alert (Monthly)** | `cost_alert_monthly` | `null` | Monthly budget alert threshold |
| **Cost Alert (Hourly)** | `cost_alert_hourly` | `null` | Hourly budget alert threshold |

### 3.3 Simulation Engine Parameters (Hardcoded)

| Parameter | Value | Description |
|-----------|-------|-------------|
| `TICK_SECONDS` | `30` | Each virtual tick = 30s real time |
| `PROVISIONING_TICKS` | `3` | ~90s for node to join cluster |
| `STABILIZATION_TICKS` | `3` | ~90s post-join stabilization |
| `MAX_SIMULATION_TICKS` | `30` | 15-minute simulation cap |
| `MAX_CYCLES` | `10` | Max consolidation cycles |
| `FRAGMENTATION_PCT` | `0.08` | 8% fragmentation correction |
| `SMALL_CLUSTER_THRESHOLD` | `5` | Clusters ≤ this size skip adding a physical fragmentation node; cost is inflated by `FRAGMENTATION_PCT` instead |
| `KUBELET_CPU_M` | `100` | Reserved CPU for kubelet (millicores) |
| `KUBELET_MEM_BYTES` | `256 MiB` | Reserved memory for kubelet |
| `ENGINE_VERSION` | `"v2-convergence"` | Simulation engine version |

---

## 4. Frontend Components — Exact UI Details

### 4.1 ClusterDetails.jsx — Optimization Settings Tab

**File:** `frontend/src/components/clusters/ClusterDetails.jsx`

#### Header Layout
- **Left:** Cluster name + status badge (green/orange pulsing dot) + Provider/Region/K8S Version tags
- **Right buttons:** "Update Agent" | "Refresh" | "Remove"

#### Tab Navigation
`Overview` | `Optimization Settings` | `Node Template` | `Activity Log`

#### Optimization Settings Tab — Full Layout

**Status Banner:**
- Pulsing dot (green when enabled, grey when disabled)
- Status text: **"ENABLED"** or **"DISABLED"**
- Description of current automation state

**Mode Badge (top right of card):** `FULL AUTO` | `REBALANCE ACTIVE` | `DISABLED`

#### Settings Panel — Every Control Listed

| # | Setting | UI Element | Sub-Settings When ON |
|---|---------|-----------|---------------------|
| 1 | **CPU Architecture** | Dropdown | Options: Both (x86 + ARM) / x86 Only / ARM64 Only |
| 2 | **Diversify Spot Pools** | Toggle | → Max Family Diversification Cap % (slider) → Instance Type Diversification % (slider with range labels) |
| 3 | **Auto Rebalance** | Toggle | → Maintain Warm Standby (toggle) → Failure Cooldown (number, minutes) → Post-Rebalance Cooldown (number, minutes) → ASCP Built-in Auto-Scaler (toggle): Min Node Count (number), Scale-Down Threshold (number + %), Scale-Down Stabilization (number + minutes) |
| 4 | **Check Cycle Interval** | Number input | Value in seconds |
| 5 | **Auto Right-Sizing** | Toggle | Enables pod + instance bin-packing + Karpenter consolidation |
| 6 | **Optimization Target** | Dropdown | Options: Spot / On-Demand. Shows **"Locked"** badge with "Locked to Spot — synergy mode active" when both Auto Rebalance + Auto Right-Sizing are ON |
| 7 | **Conservative Mode** | Toggle | Fresh cluster protection (first 24h) |
| 8 | **Manual Approval Required** | Toggle | Routes proposals to Team Lead / Org Admin |
| 9 | **Risk/Savings Tradeoff** | Slider | Range: 0–50% |
| 10 | **Maximum Risk Ceiling** | Slider | Range: 5–50% |

**PDB Controls Section:**
| Setting | UI Element | Description |
|---------|-----------|-------------|
| Respect PodDisruptionBudgets | Toggle | Honors K8s PDB constraints |
| Max Batch Size (%) | Slider with gradient background | Shows "PDB cap" indicator |

**Nested Sub-Settings** have an indigo left border to visually indicate they belong to the parent toggle.

#### State Variables (Internal)
```javascript
karpenterSimulation   // Simulation results from /ascpai/node-recommendations
rightsizing           // Array of pod-level rightsizing recommendations
optSettings           // Cluster optimization settings (automation_controls object)
nodeRecommendations   // Node-level recommendations including simulation data
```

#### Key Behaviors
- `fetchClusterDetails()` — Parallel API fetches for cluster, nodes, recommendations, rightsizing, Karpenter status
- `handleOptConfigChange()` — Guards toggle changes; checks Karpenter installation before enabling auto-rightsizing
- **Polling:** 30s/60s intervals for node state, rebalancing status, node recommendations
- **Karpenter Modal:** When auto-rightsizing toggled ON without Karpenter installed → "Karpenter Required" modal appears, polls every 5s for installation completion

---

### 4.2 RightSizingDashboard.jsx — Complete Screen Layout

**File:** `frontend/src/components/right-sizing/RightSizingDashboard.jsx`

#### Screen Layout (Top to Bottom)

```
┌─────────────────────────────────────────────────────────┐
│  AUTO MODE BANNER (🔄 Rebalancing | ⚡ Rightsizing)      │
│  [Combined mode footer if both ON]                       │
├─────────────────────────────────────────────────────────┤
│  CLUSTER HEALTH KPIs                                     │
│  Total Nodes | Stateless | Stateful | Eligible | Cooling │
├─────────────────────────────────────────────────────────┤
│  GUARD & STABILITY PANEL (6 cards)                       │
├─────────────────────────────────────────────────────────┤
│  STATELESS NODES TABLE (11 columns)                      │
│  [Projected Savings] [Safe to Execute] [Blocked by Policy]│
├─────────────────────────────────────────────────────────┤
│  STATEFUL NODES TABLE (7 columns)                        │
│  [Total] [Eligible] [Savings Potential] [Max Downscale]  │
├─────────────────────────────────────────────────────────┤
│  POD-LEVEL RECOMMENDATIONS TABLE (8 columns)             │
│  [Total Right-Sizing Savings footer]                     │
├─────────────────────────────────────────────────────────┤
│  KARPENTER CONFIGURATION PANEL                           │
│  [Strategy | Families | Policies] [Save]                 │
├─────────────────────────────────────────────────────────┤
│  TABS: Execution Plan | History                          │
└─────────────────────────────────────────────────────────┘
```

#### Karpenter Configuration Panel — Exact Layout

**Left Card:**

| Setting | UI Element | Details |
|---------|-----------|---------|
| Optimization Strategy | 3 radio buttons | `balanced` / `cost-first` / `performance-first` |
| Spot Target % | Slider | 0–100 range |
| Buffer % (Safety Headroom) | Number input | 10–100 range |
| Optimization Target | Dropdown | Spot / On-Demand (locked when synergy ON) |

**Right Card 1 — Instance Families:**

| Setting | UI Element | Details |
|---------|-----------|---------|
| Allowed Instance Families | Clickable tags | m5, m6i, c5, c6i, t3, t4g, c6g, m6g (toggle each) |
| Consolidation | Toggle + threshold slider | Threshold % when consolidation ON |
| Instance-Aware Mode | Toggle | Only recommend if better pool exists |

**Right Card 2 — Stateful Node Policy:**

| Setting | UI Element | Details |
|---------|-----------|---------|
| Max Downscale % | Slider | 10–75% range |
| Auto Stateful Resize | Toggle | Enable auto resize for stateful |
| Require Approval | Toggle | Manual approval gate |
| Spot Migration | Locked badge (red) | "Always Disabled" — stateful stays On-Demand |

**Right Card 3 — Fleet Diversity:**

| Setting | UI Element |
|---------|-----------|
| Diversify Pools | Toggle |

**Save Button** below all cards.

---

### 4.3 RightSizingKarpenterTab.jsx — Karpenter Monitoring Dashboard

**File:** `frontend/src/components/right-sizing/RightSizingKarpenterTab.jsx`

#### Top KPI Cards (4-column grid)

| KPI | Icon | Example |
|-----|------|---------|
| Total Clusters | FiLayers | `3` |
| Active Targets | FiTarget | `8` |
| Monthly Savings | FiDollarSign | `$1,250` |
| Efficiency Score | FiActivity | `—` (placeholder) |

#### Exposure Snapshot Card

| Left Column | Right Column |
|-------------|-------------|
| "Availability Strategy" | "AZ Distribution" |
| Circular placeholder: "Data pending" | 3 progress bars (us-east-1a/b/c with %) |
| | Orange warning: "High concentration in 1a detected..." |

#### Guard & Stability Panel (Same 6 Cards as Dashboard)
Shows actual values when data available (e.g., "0", "2", "HEALTHY")

#### Active Node Migrations Section
- Pulsing green dot with text: "ACTIVE NODE MIGRATIONS (0 migrations)"
- Empty state placeholder with server icon when no active migrations

#### Right Column Cards

| Card | Content |
|------|---------|
| **Next Target** | Server icon + node name badge, Proposed Family, Annual Savings, Risk Assessment, "Apply Recommendations" button |
| **Stabilization Status** | 3 items (Scaling Metrics, Compute Optimizer, Traffic Re-routing) with color dots, Process Health progress bar |
| **Live Updates** | Red background when active, timestamp + event description pairs, pulsing red indicator |

#### Resource Allocation by Instance Family
- Placeholder for chart visualization

#### Stateful Nodes Table
Same columns and KPI header as RightSizingDashboard stateful section.

---

### 4.4 ClusterList.jsx — Per-Cluster Card & Karpenter Status

**File:** `frontend/src/components/clusters/ClusterList.jsx`

#### Cluster Card Layout

```
┌───────────────────────────────────────────┐
│ ● Cluster Name            status pill      │
│ [region] · X nodes · ● Agent / ○ No Agent │
│ CPU  ████████░░  72%                       │
│ MEM  ██████░░░░  58%                       │
│ $XXX/mo                    ● $XX saved     │
├───────────────────────────────────────────┤
│ Karpenter Management                       │
│ Status: [description]      [Badge]         │
│ [Alert box if errors]                      │
│ [Action buttons]                           │
└───────────────────────────────────────────┘
```

#### Karpenter Status Badges Per Cluster

| Status | Badge Color | Icon | Text |
|--------|------------|------|------|
| Installed | Green bg | ✓ | "Installed" |
| Installing | Amber bg | ⟳ (spinning) | "Installing…" |
| Not Installed | Grey bg | — | "Not Installed" |
| Missing | Red bg | ⚠ | "Missing" |
| Unknown | Amber bg | ? | "Unknown" |
| Failed | Red bg | ✕ | "Failed" |
| Checking | Grey bg | ⟳ | "Checking..." |

#### Conditional Alert Boxes

| Condition | Alert Style | Content |
|-----------|------------|---------|
| **Missing** | Amber warning box | Reinstall instructions + `live_status` details |
| **Failed / Unknown** | Red error box | Monospace error message (scrollable) |

#### Action Buttons Per Status

| Status | Buttons |
|--------|---------|
| Not Installed | "⬇ Install Karpenter" (green) |
| Failed | "↺ Retry Install" (red) |
| Missing | "↺ Reinstall Karpenter" (red) + "Uninstall" (outlined grey) |
| Installed | "Uninstall" (outlined grey) |

All buttons show loading states: "Queuing..." / "Installing..." / "Uninstalling..."

### 4.4 Frontend API Calls

**File:** `frontend/src/services/api.js`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `getRightsizing(clusterId)` | `GET /api/v1/pod-metrics/right-sizing/recommendations` | Pod-level recommendations |
| `getEnrichedRightsizing(clusterId)` | `GET /api/v1/pod-metrics/rightsizing/enriched` | Enriched recommendations |
| `applyRecommendation(id)` | `POST /api/v1/optimization/apply/{id}` | Apply single recommendation |
| `applyRightsizingValidated(id, type, az)` | `POST /api/v1/optimization/apply/{id}/validated` | Apply with target validation |
| `batchApplyRecommendations(data)` | `POST /api/v1/optimization/rightsizing/batch-apply` | Batch apply multiple |
| `getNodeRecommendations(clusterId)` | `GET /api/v1/ascpai/node-recommendations` | Node recs + simulation |

---

## 5. Backend API Endpoints

### 5.1 Karpenter Routes (`backend/api/karpenter_routes.py`)

#### GET `/karpenter/status`
Returns Karpenter deployment status.
```json
{
  "is_setup": true,
  "status": "active",
  "mode": "auto",
  "active_clusters": 3,
  "pending_recommendations": 5,
  "savings_estimate": { "monthly": 1250.00 }
}
```

#### GET `/karpenter/config?cluster_id={id}`
Returns per-cluster Karpenter configuration from Redis + DB.

**Sources:** Redis (strategy, families, UI settings) + DB (automation toggles — source of truth)

**Response:**
```json
{
  "cluster_id": "uuid",
  "strategy": "balanced",
  "instance_families": ["m5", "m6i", "c5", "c6i"],
  "architectures": ["amd64"],
  "spot_target_pct": 75,
  "on_demand_fallback": true,
  "buffer_pct": 30,
  "min_vcpu": 2,
  "max_vcpu": 16,
  "min_memory_gib": 4,
  "max_memory_gib": 64,
  "consolidation_enabled": true,
  "consolidation_threshold_pct": 60,
  "auto_rebalancing_enabled": true,
  "auto_rightsizing_enabled": true,
  "optimization_target": "spot",
  "optimization_target_locked": true,
  "diversify_pools": false,
  "auto_stateful_rightsizing_enabled": false,
  "stateful_require_approval": true,
  "stateful_max_downscale_pct": 25
}
```

#### PATCH `/karpenter/config/{cluster_id}`
Updates cluster-level Karpenter settings.

**Side Effects:**
- `auto_rebalancing_enabled` change → syncs `karpenter_mode` (auto/dry_run) in DB
- `auto_rightsizing_enabled` change → patches Karpenter NodePool consolidation policy
- `diversify_pools` enabled → clears cache for immediate pool re-selection
- When `auto_rebalancing=ON` → sets Karpenter `consolidationPolicy="WhenEmpty"` (prevents conflict)

### 5.2 Pod Metrics Routes (`backend/api/pod_metrics_routes.py`)

#### GET `/pod-metrics/right-sizing/recommendations`
Calls `RightSizingService.generate_recommendations(cluster_id)`.
Returns array of `RightSizingRecommendation` objects.

### 5.3 Optimizer Coordinator Routes (`backend/api/optimizer_coordinator_routes.py`)

#### GET `/optimizer/status/{cluster_id}`
Returns current optimization phase and capabilities.

**Phases:** `INITIAL_POOL_OPTIMIZATION` → `STABILIZATION` → `RIGHTSIZING_EVALUATION` → `COMBINED_EXECUTION` → `COOLDOWN`

#### POST `/optimizer/evaluate/{cluster_id}`
Triggers combined optimization — generates proposals + evaluates with combined EV.

#### GET `/optimizer/proposals/{cluster_id}?status=PENDING`
Lists rightsizing proposals by status (`PENDING`, `APPROVED`, `REJECTED`, `EXECUTED`).

#### POST `/optimizer/proposals/{proposal_id}/approve`
Approves and executes a proposal. Activates 6-hour cooldown.

#### GET `/optimizer/trust-phase/{cluster_id}`
Returns progressive trust phase info:

| Phase | Age | Rightsizing | Buffer | Min Samples | Risk Ceiling |
|-------|-----|-------------|--------|-------------|-------------|
| **Phase 0** | 0–30 min | Blocked | 30% | 500 | 0.15 |
| **Phase 1** | 30–120 min | Conservative | 25% | 500 | 0.20 |
| **Phase 2** | >2 hours | Full | 20% | 100 | Profile default |

### 5.4 ASCPAI Routes — Simulation Integration

#### GET `/ascpai/node-recommendations?cluster_id={id}&useRightsized=true`
- When `useRightsized=true`: runs simulation AFTER applying pod rightsizing adjustments
- Returns: `{ recommendations: [...], karpenter_simulation: {...} }`

---

## 6. Core Services & Logic

### 6.1 Karpenter Service (`backend/services/karpenter_service.py`)

**Purpose:** System 3 — NodePool management and ML ranking sync

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `sync_ml_rankings_to_nodepool()` | Extracts instance types + AZs from ML-ranked pools → patches Karpenter NodePool `spec.requirements` via `kubectl patch` |
| `switch_to_ondemand()` | Fallback: patches NodePool to on-demand capacity type with 12h auto-revert TTL in Redis |
| `revert_to_spot()` | Auto-reverts from on-demand back to spot after 12h fallback expires |

**Kubernetes API Integration:**
- Uses `kubernetes` Python client library
- `CustomObjectsApi` for patching `karpenter.sh/v1 NodePool` resources
- Handles both PATCH (update existing) and CREATE (new NodePool) operations

### 6.2 Decision Engine Integration

**Files:** `backend/core/decision_engine.py`, `backend/core/scoring.py`

```
EV = Savings × (1 - Risk)
```

**Combined EV Calculation (used by Optimizer Coordinator):**
```
Option A = EV(current_size + new_pool)    # Pool optimization only
Option B = EV(new_size + best_pool)       # Combined rightsizing + pool
Option C = 0                               # Do nothing (baseline)
```

Recommended option = highest EV, subject to ≥3% improvement threshold.

---

## 7. Simulation Engine — Deep Dive

**File:** `backend/services/simulation_engine.py` (~1350 lines)

### 7.1 Data Structures

#### SimNode
```python
instance_id, instance_type, lifecycle (spot|on-demand), az, architecture (amd64|arm64),
vcpu, memory_gb, price_hourly, workload_class (stateless|stateful|system),
status (READY|CALIBRATING|UNKNOWN), is_standby, node_name
```

#### SimPod
```python
pod_name, namespace, controller_name, controller_kind,
cpu_millicores, memory_bytes, is_stateful, is_daemonset, is_system,
node_name, node_selector (dict), tolerations (list),
has_pod_anti_affinity, has_pod_affinity, topology_spread_constraints,
cpu_limit_millicores, memory_limit_bytes
```

#### VirtualNode (runtime simulation node)
```python
node_id, instance_type, lifecycle, az, architecture, vcpu, memory_gb, price_hourly,
workload_class, status (READY|CORDONED|DRAINING|PROVISIONING|STABILIZING|TERMINATED),
allocatable_cpu_m, allocatable_mem_bytes, used_cpu_m, used_mem_bytes,
provisioning_ticks_remaining, stabilization_ticks_remaining,
is_new_this_cycle, labels (dict), taints (list)
```

#### VirtualPod (runtime simulation pod)
```python
pod_id, pod_name, namespace, controller_name, controller_kind,
cpu_millicores, memory_bytes, is_stateful, is_daemonset, is_system,
node_id, status (RUNNING|PENDING|FAILED),
node_selector, tolerations, has_pod_anti_affinity, has_pod_affinity,
topology_spread_constraints, cpu_limit_millicores, memory_limit_bytes
```

#### SimPool (candidate instance pool)
```python
instance_type, az, architecture, vcpu, memory_gb,
spot_price, od_price, risk_probability, ml_score,
allocatable_cpu_m, allocatable_mem_bytes
```

#### SimClusterSettings
```python
target_spot_exposure_pct (0-100),   # Target spot ratio
diversify_pools (bool),              # Enforce family/AZ diversity
max_family_diversification_cap_pct (default 40),  # Max % per family
architecture_preference (both|amd64|arm64),
min_node_count,
rebalance_batch_percent,
risk_ceiling_percent (default 25),   # Max acceptable risk
risk_savings_tradeoff_pct (default 20)  # Price premium for safety
```

### 7.2 Multi-Cycle Convergence Algorithm

```
run_simulation(snapshot) → SimulationResult

INPUT: SimulationSnapshot containing:
  - Current nodes (type, lifecycle, AZ, resources, price)
  - Current pods (requests, limits, constraints, workload class)
  - Redis constraints (launch_blocked, blacklisted, risky pools)
  - Cluster settings (spot %, diversity, risk ceilings)

ALGORITHM:
  1. Validate snapshot
  2. Filter eligible pools (exclude blocked, blacklisted, wrong arch/AZ)
  
  FOR cycle = 0 to MAX_CYCLES (10):
  
    ┌─────────────────────────────────────────────┐
    │  STEP 1: SELECT CONSOLIDATION CANDIDATES    │
    │  - Stateless on-demand nodes (should be spot)│
    │  - Risky spot nodes (risk > ceiling)         │
    │  - Apply spot exposure cap                   │
    │  - Respect PDB batch sizing                  │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  STEP 2: DRAIN CANDIDATES                   │
    │  - Evict all pods from selected nodes        │
    │  - Pods move to PENDING status               │
    │  - Nodes marked TERMINATED                   │
    │  - Track peak_pending_pods count             │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  STEP 3: KARPENTER PROVISIONING             │
    │  a. Batch pending pods (capacity-aware,      │
    │     based on cheapest pool's pods-per-node)  │
    │  b. FOR each batch:                          │
    │     - Run 5-Pass Pool Selection (Pass 0      │
    │       total-cost + 4 original passes)        │
    │     - Provision new VirtualNode              │
    │     - Node status = PROVISIONING             │
    │     - provisioning_ticks_remaining = 3       │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  STEP 4: TICK PROVISIONING TIMERS           │
    │  PROVISIONING (3 ticks) → STABILIZING       │
    │  STABILIZING (3 ticks) → READY              │
    │  (~90s total real time per node)             │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  STEP 5: GREEDY SCHEDULER PLACEMENT         │
    │  For each PENDING pod:                       │
    │    Find first READY node where:              │
    │    - node_fits_pod() = true (resources)      │
    │    - node_allows_pod() = true (constraints)  │
    │    Place pod → status = RUNNING              │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  STEP 5b: EMPTY NODE CLEANUP (NEW)          │
    │  Remove newly provisioned spot nodes that    │
    │  received zero pods after scheduling. Mirrors│
    │  Karpenter's consolidation controller —      │
    │  prevents inflated node counts.              │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  STEP 6: FRAGMENTATION CORRECTION           │
    │  waste = 1 - (total_used / total_alloc)     │
    │  If waste < 8%:                              │
    │    Small cluster (≤5 nodes): SKIP physical   │
    │      node, apply 8% cost multiplier in       │
    │      output builder instead                  │
    │    Large cluster (>5 nodes): Add one node    │
    │      of most-common type (as before)         │
    └──────────────────┬──────────────────────────┘
                       ▼
    ┌─────────────────────────────────────────────┐
    │  CONVERGENCE CHECK                          │
    │  IF no PENDING pods AND no PROVISIONING     │
    │     nodes → BREAK (converged!)              │
    │  ELSE → next cycle                          │
    └─────────────────────────────────────────────┘

OUTPUT: SimulationResult with:
  - cycles_run, converged, timed_out
  - final_state (nodes + pods placement)
  - history (per-cycle snapshots)
  - confidence_score (0.0 – 1.0)
  - cost breakdown (stateless vs stateful)
```

### 7.3 5-Pass Pool Selection Algorithm

For each batch of pending pods, the simulation selects the best instance pool using a 5-pass algorithm. **Pass 0** is a forward-looking total-cost optimisation added to prevent the cheapest-per-node pool from inflating total node count:

```
PASS 0 — TOTAL-COST OPTIMISATION (Forward-Looking) [NEW]
  Estimate ALL future pending pods:
    future_pods = current_pending + pods on remaining OD stateless nodes
  FOR each eligible pool:
    ✓ pool fits largest individual pod (CPU & memory)
    ✓ pool.risk_probability < risk_ceiling (25%)
    ✓ pool.spot_price < od_price
    ✓ Diversification check passes
    Calculate:
      nodes_cpu  = ⌈total_future_cpu / pool.allocatable_cpu_m⌉
      nodes_mem  = ⌈total_future_mem / pool.allocatable_mem_bytes⌉
      nodes_needed = max(nodes_cpu, nodes_mem)
      total_cost = nodes_needed × pool.spot_price
  → Select: pool with lowest total_cost

  This prevents e.g. 4 × t3a.small ($0.020/hr) beating
  3 × t3a.medium ($0.027/hr) just because small is cheaper per-node.

PASS 1 — VALUE + SAFETY (Preferred)
  ✓ pool.risk_probability < risk_ceiling (25%)
  ✓ pool.spot_price < od_price
  ✓ Diversification check passes (family cap ≤40%)
  → Select: cheapest qualifying pool

PASS 2 — ALLOW COSTLIER IF SAFER
  ✓ pool.price ≤ cheapest_pass1_price + tradeoff_margin (20%)
  ✓ pool.risk_probability < risk_ceiling
  → Select: safest qualifying pool

PASS 3 — RISK OVERRIDE
  ✓ pool is safer than worst current pool in cluster
  → Select: safest available pool (any price)

PASS 4 — ON-DEMAND FALLBACK
  ✓ Any pool cheaper than on-demand equivalent
  → Select: cheapest available (last resort)
```

### 7.4 Constraint Enforcement

#### node_fits_pod() — Resource Check
```python
pod_cpu_effective = pod.cpu_millicores
pod_mem_effective = pod.memory_bytes

# Headroom: if limit > 2× request, apply 1.2× multiplier
if pod.cpu_limit_millicores > 2 * pod.cpu_millicores:
    pod_cpu_effective *= 1.2
if pod.memory_limit_bytes > 2 * pod.memory_bytes:
    pod_mem_effective *= 1.2

return (pod_cpu_effective <= node.remaining_cpu() AND
        pod_mem_effective <= node.remaining_mem())
```

#### node_allows_pod() — Scheduling Constraints
```python
# 1. Node must be READY
if node.status != 'READY': return False

# 2. Workload class matching
#    Stateful pods → stateful/system nodes only
#    Stateless pods → stateless nodes only

# 3. nodeSelector matching
for key, value in pod.node_selector.items():
    if node.labels.get(key) != value: return False

# 4. Taint/Toleration matching (K8s standard)
for taint in node.taints:
    if not any_toleration_matches(pod.tolerations, taint):
        return False

# 5. Pod Anti-Affinity (checked in scheduler)
# 6. Topology Spread Constraints (checked in scheduler)
```

#### Scheduler Constraint Extensions
- **Pod Anti-Affinity:** Checks if same-controller pods already placed on node
- **Topology Spread Constraints:** Enforces `maxSkew` across topology domains
- **HA Constraint:** System pods distributed across AZs

### 7.5 Confidence Scoring

```python
score = 1.0   # Start at 100%

# Provisioning failures
score -= 0.05 × provisioning_failure_count

# Failed pods ratio
score -= 0.20 × (failed_pods / total_pods)

# Slow convergence
if cycles_run > 6:
    score -= 0.10

# Missing metadata detection
if constrained_pods == 0 AND total_pods > 5:
    score -= 0.05   # Likely missing nodeSelector/affinity data

return max(0.0, min(1.0, round(score, 2)))
```

### 7.6 Fragmentation Correction

Real clusters always have some wasted capacity due to binpacking inefficiency. The simulation corrects for this, with **size-aware scaling** to avoid disproportionate node inflation on small clusters:

```python
waste = 1 - (total_used_resources / total_allocatable_resources)

if waste < FRAGMENTATION_PCT (8%):
    if len(stateless_nodes) <= SMALL_CLUSTER_THRESHOLD (5):
        # Small cluster — adding +1 node is disproportionate
        # (e.g., +1 on a 3-node cluster = 33% increase)
        # Skip physical node; apply 8% cost multiplier in output builder
        LOG "Skipping extra node — cost inflated by 8% instead"
        return
    else:
        # Large cluster — +1 node is < 10% of fleet, acceptable
        most_common_type = mode(node.instance_type for node in stateless_nodes)
        add_virtual_node(most_common_type, status=READY)
```

**Rationale:** Real Karpenter does not provision idle nodes "just in case." For small clusters (≤5 nodes), the cost inflation approach (`1 + FRAGMENTATION_PCT = 1.08`) accounts for real-world packing waste without inflating the recommended node count. This is applied in `build_simulation_output()`.

### 7.6b Empty Node Cleanup

After the greedy scheduler completes in each cycle, newly provisioned spot nodes that received zero pods are terminated:

```python
for node in newly_provisioned_spot_nodes:
    if running_pods(node) == 0:
        terminate_node(node)
        # Mirrors Karpenter's consolidation controller
```

This prevents over-provisioning when capacity-aware batching creates more groups than needed.

### 7.6c Capacity-Aware Pod Batching

Instead of a fixed batch size of 4, pending pods are grouped by the estimated pods-per-node capacity of the cheapest eligible pool:

```python
cheapest_pool = eligible_pools[0]  # sorted by spot_price
fit_by_cpu = cheapest_pool.allocatable_cpu_m // max_pod_cpu
fit_by_mem = cheapest_pool.allocatable_mem_bytes // max_pod_mem
pods_per_node = max(1, min(fit_by_cpu, fit_by_mem))

# Group pending pods into batches of `pods_per_node`
# Each batch → one provisioned node
```

This prevents over-provisioning (e.g., creating 3 groups of 4 pods when 2 larger nodes could hold all 12).

### 7.7 Two-Pool Cost Calculation

Returns separate cost breakdowns for stateless (spot) and stateful (on-demand).

**Small-cluster fragmentation cost inflation:** When the fragmentation correction skipped adding a physical node (cluster ≤ `SMALL_CLUSTER_THRESHOLD`), `build_simulation_output()` inflates the stateless cost by `1 + FRAGMENTATION_PCT` (8%) to account for real-world packing waste without inflating node count:

```python
if len(ready_stateless) <= SMALL_CLUSTER_THRESHOLD and waste < FRAGMENTATION_PCT:
    frag_multiplier = 1.0 + FRAGMENTATION_PCT   # 1.08
    stateless_hourly_cost  *= frag_multiplier
    stateless_monthly_cost *= frag_multiplier
    # Totals recomputed from stateful + inflated stateless
```

Example output:
```json
{
  "stateless_node_count": 8,
  "stateless_spot_count": 7,
  "stateless_monthly_cost": 850.00,
  "stateful_node_count": 2,
  "stateful_monthly_cost": 320.00,
  "total_monthly_cost": 1170.00,
  "spot_exposure_pct": 87.5
}
```

---

## 8. RightSizing Service

**File:** `backend/services/rightsizing_service.py` (~700+ lines)

### 8.1 generate_recommendations() — Full Logic

```python
def generate_recommendations(
    cluster_id: str,
    namespace: Optional[str] = None,
    analysis_window_hours: int = 168,  # 7 days
    min_data_points: int = 100
) -> List[RightSizingRecommendation]:
```

**Pipeline:**

```
1. METRIC FRESHNESS CHECK (Enhancement 6)
   │  Reject if latest metric lag > 5 minutes
   ▼
2. COOLDOWN CHECK
   │  Skip if cluster in resize cooldown (6h)
   ▼
3. NODE CLASSIFICATION
   │  Get cached WorkloadInspector classification
   │  (identifies STATELESS_ELIGIBLE nodes)
   ▼
4. GET DISTINCT CONTROLLERS
   │  Query: SELECT DISTINCT (namespace, controller_kind, controller_name)
   │  FROM pod_metrics WHERE cluster_id = ? AND timestamp > (now - window)
   ▼
5. PER-CONTROLLER ANALYSIS  ←── _analyze_controller()
   │  For each controller:
   │    a. Fetch pod metrics from DB
   │    b. Calculate P50/P95/P99/avg/min/max for CPU and memory
   │    c. Apply phase-aware safety buffer (20-30%)
   │    d. Apply volatility-aware buffer (≥35% if volatile)
   │    e. Apply P99 fallback floor (recommended ≥ P99 × 1.3)
   │    f. Estimate cost savings (current vs recommended)
   │    g. Determine confidence (HIGH/MEDIUM/LOW)
   ▼
6. INSTANCE-AWARE FILTERING (if enabled)
   │  Check if better spot pool exists for proposed size
   │  via _check_better_pool_exists()
   ▼
7. RETURN sorted by expected value (descending)
```

### 8.2 _analyze_controller() — Per-Controller Analysis

```python
def _analyze_controller(
    cluster_id, namespace, controller_kind, controller_name,
    analysis_window_hours, min_data_points
) -> Optional[RightSizingRecommendation]:
```

**Calculation:**
1. Query `PodMetric` table for controller in time range
2. Calculate statistics: `{avg, p50, p95, p99, min, max}` for CPU and memory
3. Get current config from latest metric's `cpu_request_millicores`, `memory_request_bytes`
4. **Phase-Aware Safety Buffer:**
   - Phase 0 (0–30 min): 30% buffer
   - Phase 1 (30 min–2h): 25% buffer
   - Phase 2 (>2h): 20% buffer
5. **Volatility-Aware Buffer:** If market volatility detected → buffer ≥ 35%
6. **P99 Fallback Floor:** `recommended ≥ P99 × 1.3` (burst protection)
7. **Cost Estimation:** `monthly_cost = (cpu_cores × cpu_rate + memory_gb × mem_rate) × 730`
8. Return `RightSizingRecommendation` if actionable

### 8.3 Safety Thresholds

| Constant | Value | Purpose |
|----------|-------|---------|
| `SAFETY_BUFFER_PCT` | `20%` | Default headroom above P95 (overridden by phase logic) |
| `OVERSIZED_THRESHOLD_PCT` | `50%` | Flag as oversized if usage < 50% of request |
| `UNDERSIZED_THRESHOLD_PCT` | `95%` | Flag as undersized if P99 > 95% of request |

### 8.4 Confidence Levels

| Level | Criteria |
|-------|----------|
| **HIGH** | ≥ 500 data points AND window coverage ≥ 50% |
| **MEDIUM** | ≥ 100 data points AND window coverage ≥ 20% |
| **LOW** | Below medium thresholds → recommendation is **skipped** |

### 8.5 Instance Family Cost Mappings

| Family | CPU $/core/hour | Memory $/GB/hour |
|--------|----------------|------------------|
| m5 | $0.048 | $0.006 |
| m6i | $0.046 | $0.006 |
| c5 | $0.042 | $0.005 |
| c6i | $0.040 | $0.005 |
| r5 | $0.063 | $0.008 |
| r6i | $0.063 | $0.008 |
| t3 | $0.021 | $0.003 |
| t3a | $0.019 | $0.003 |

**Fallback:** `CPU_COST_PER_CORE_HOUR = $0.04`, `MEMORY_COST_PER_GB_HOUR = $0.005`

### 8.6 _check_better_pool_exists() — Double Gate

```python
# Gate 1: Risk Gate
pool.risk_probability < 0.15   # Max 15% risk

# Gate 2: Price Gate
pool.spot_price < on_demand_equivalent_price

# Selection: highest EV
EV = savings × (1 - risk)
```

---

## 9. Optimizer Coordinator

**File:** `backend/services/optimizer_coordinator.py` (~500+ lines)

### 9.1 Optimization Phases

```
INITIAL_POOL_OPTIMIZATION ──► STABILIZATION ──► RIGHTSIZING_EVALUATION
        (30-60 min)              (≥1 hour)              │
                                                        ▼
        COOLDOWN ◄────────── COMBINED_EXECUTION
      (6h resize /               (evaluate
       30min pool)             Option A/B/C)
```

| Phase | Duration | What Happens |
|-------|----------|-------------|
| **INITIAL_POOL_OPTIMIZATION** | 30–60 min | Spot ML runs first, selects optimal pools |
| **STABILIZATION** | ≥ 1 hour | Waiting period; metrics accumulate |
| **RIGHTSIZING_EVALUATION** | On trigger | RightSizing proposes size changes |
| **COMBINED_EXECUTION** | On trigger | Evaluate Option A vs B vs C, execute best |
| **COOLDOWN** | 6h (resize) / 30min (pool) | Post-execution protection |

### 9.2 can_run_rightsizing_evaluation()

```python
def can_run_rightsizing_evaluation(cluster_id) -> (bool, str):
    # 1. Check trust phase → Phase 0 blocks rightsizing entirely
    # 2. Check STABILIZATION period elapsed (≥1 hour)
    # 3. Check 24-hour interval since last rightsizing check
    # 4. Check resize cooldown (6h active → block)
    # 5. CIRCUIT BREAKER: ≥3 failures in 24h → block
```

### 9.3 evaluate_combined_proposal() — Option A/B/C

```
OPTION A: Current Size + New Pool (Pool Optimization Only)
  cost = current_size_cost × new_pool_price_ratio
  risk = new_pool_risk_probability
  EV_A = savings_A × (1 - risk_A) - migration_cost

OPTION B: New Size + Best Pool for New Size (Combined)
  1. Re-run Spot ML constrained to proposed_instance_type
  2. Find best_pool_for_new_size
  cost = proposed_size_cost × best_pool_price_ratio
  risk = best_pool_risk
  EV_B = savings_B × (1 - risk_B) - migration_cost - volatility_penalty

OPTION C: Do Nothing (Baseline)
  EV_C = 0

DECISION:
  recommended = max(EV_A, EV_B, EV_C)
  IF recommended - EV_C >= MIN_SAVINGS_DELTA_PCT (3%):
      APPROVE recommended option
  ELSE:
      REJECT (insufficient improvement)
```

### 9.4 Timing Thresholds

| Threshold | Value |
|-----------|-------|
| `STABILIZATION_HOURS` | 1 hour |
| `RIGHTSIZING_EVAL_INTERVAL_HOURS` | 24 hours |
| `MIN_SAVINGS_DELTA_PCT` | 3.0% |
| Resize Cooldown | 6 hours |
| Pool Switch Cooldown | 30 minutes |
| Circuit Breaker | 3 failures / 24h |

---

## 10. Database Models

### 10.1 RightsizingProposal

**File:** `backend/models/rightsizing_proposal.py`  
**Table:** `rightsizing_proposals`

| Column | Type | Description |
|--------|------|-------------|
| `id` | `String` (PK) | Format: `rsprop_{YYYYMMDDHHMMSS_microseconds}` |
| `cluster_id` | `String` (FK) | Foreign key to `clusters` table |
| `current_instance_type` | `String` | e.g., `m5.xlarge` |
| `current_vcpu` | `Integer` | Current vCPU count |
| `current_memory_gb` | `Float` | Current memory in GB |
| `current_pool` | `String` | e.g., `m5.large:us-east-1a` |
| `current_hourly_cost` | `Float` | Current $/hour |
| `proposed_instance_type` | `String` | Recommended type |
| `proposed_vcpu` | `Integer` | Proposed vCPU |
| `proposed_memory_gb` | `Float` | Proposed memory GB |
| `proposed_hourly_cost` | `Float` | Proposed $/hour |
| `estimated_hourly_savings` | `Float` | Hourly savings |
| `estimated_monthly_savings` | `Float` | = hourly × 730 |
| `savings_percentage` | `Float` | % savings |
| `avg_cpu_utilization_pct` | `Float` | Average CPU % in window |
| `p95_cpu_utilization_pct` | `Float` | P95 CPU % |
| `avg_memory_utilization_pct` | `Float` | Average memory % |
| `p95_memory_utilization_pct` | `Float` | P95 memory % |
| `metric_sample_count` | `Integer` | Number of data points |
| `metric_window_hours` | `Float` | Analysis window in hours |
| `status` | `Enum` | `PENDING` / `APPROVED` / `REJECTED` / `EXECUTED` / `FAILED` |
| `created_at` | `DateTime` | When proposal was created |
| `evaluated_at` | `DateTime` | When combined EV was calculated |
| `executed_at` | `DateTime` | When resize was actually performed |
| `combined_ev_option_a` | `Float` | EV for pool-only optimization |
| `combined_ev_option_b` | `Float` | EV for combined optimization |
| `combined_ev_option_c` | `Float` | EV for do-nothing (= 0) |
| `selected_option` | `String` | `"A"`, `"B"`, or `"C"` |
| `best_pool_for_new_size` | `String` | e.g., `m5.xlarge:us-east-1b` |
| `best_pool_hourly_cost` | `Float` | Best pool price |
| `best_pool_risk_score` | `Float` | Best pool risk |
| `rejection_reason` | `Text` | Why rejected (if applicable) |
| `evaluation_breakdown` | `JSON` | Full EV calculation details |
| `ev_breakdown` | `JSON` | Stored at creation (Task 2.1) |
| `net_ev` | `Float` | Net expected value from economic model |

**Relationships:**
- `Cluster.rightsizing_proposals` → One-to-many, cascade delete
- `OptimizerState.pending_proposal` → Many-to-one reference

### 10.2 ClusterOptimizationSettings (Relevant Fields)

| Column | Type | Description |
|--------|------|-------------|
| `auto_rebalance_enabled` | `Boolean` | Spot ML pool rebalancing toggle |
| `auto_rightsizing_enabled` | `Boolean` | Rightsizing + bin-packing toggle |
| `optimization_target` | `String` | `"spot"` or `"on_demand"` |
| `instance_aware_rightsizing` | `Boolean` | Only recommend if better pool exists |
| `diversify_pools` | `Boolean` | Family/AZ diversification |

### 10.3 OptimizerState (Relevant Fields)

| Column | Type | Description |
|--------|------|-------------|
| `phase` | `String` | Current optimization phase |
| `pending_rightsizing_proposal_id` | `String` (FK) | Active proposal being evaluated |
| `last_pool_optimization_at` | `DateTime` | Last pool switch timestamp |
| `last_rightsizing_evaluation_at` | `DateTime` | Last rightsizing check |

### 10.4 PodMetric (Source Data)

| Column | Type | Description |
|--------|------|-------------|
| `cluster_id` | `String` | Cluster identifier |
| `namespace` | `String` | K8s namespace |
| `controller_kind` | `String` | Deployment / StatefulSet / DaemonSet |
| `controller_name` | `String` | Controller name |
| `cpu_request_millicores` | `Integer` | CPU request in millicores |
| `memory_request_bytes` | `BigInteger` | Memory request in bytes |
| `cpu_usage_millicores` | `Integer` | Actual CPU usage |
| `memory_usage_bytes` | `BigInteger` | Actual memory usage |
| `timestamp` | `DateTime` | Metric collection time |

---

## 11. Redis Keys & Caching

### 11.1 Cooldown & Control Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `spot:resize_cooldown:{cluster_id}` | 6 hours | Active resize cooldown |
| `spot:pool_switch_cooldown:{cluster_id}` | 30 min | Pool switch cooldown |
| `spot:ondemand_fallback:{cluster_id}` | 12 hours | On-demand fallback state |
| `spot:karpenter:nodepool_updated:{cluster_id}` | Variable | Prevents frequent NodePool patches |
| `resize:failure_count_24h:{cluster_id}` | 24 hours | Circuit breaker failure counter |

### 11.2 Constraint & Ranking Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `{cluster_id}:{instance_type}:{az}:launch_blocked` | — | Blocked pool (from constraint replay) |
| `global_pool_rankings:{region}` | 65 min | Cached ML-ranked pools |
| `ascpai:pool_rankings` | Request-scoped | Legacy per-request ranking cache |

### 11.3 Pricing Cache Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `od_price:{region}:{instance_type}` | — | On-demand hourly rate |
| `ondemand_price:{region}:{instance_type}` | — | Alternative OD key format |
| `pricing:ec2:{family}:cpu_per_core_hour` | — | CPU pricing per family |
| `pricing:ec2:{family}:mem_per_gb_hour` | — | Memory pricing per family |

### 11.4 Configuration Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `karpenter_config:{cluster_id}` | 24 hours | Persisted UI settings (JSON) |
| `karpenter:live_status:{cluster_id}` | 60 sec | Agent heartbeat Karpenter status |

### 11.5 Workload & Volatility Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `volatility:{cluster_id}:{node_id}` | — | `"true"` / `"active"` = volatile market |

---

## 12. Pydantic Schemas

### 12.1 RightSizingRecommendation

**File:** `backend/schemas/pod_metric_schemas.py`

```python
class RightSizingRecommendation(BaseModel):
    # Identity
    pod_name: str
    namespace: str
    controller_kind: str
    controller_name: str
    
    # Current Configuration
    current_cpu_request_millicores: int
    current_memory_request_mb: int
    current_replica_count: int
    
    # Recommendation
    recommended_cpu_request_millicores: int
    recommended_memory_request_mb: int
    recommended_safety_buffer_pct: int       # 20% default
    
    # Metrics
    metric_sample_count: int
    analysis_window_hours: float
    p95_cpu_usage_millicores: int
    p95_memory_usage_mb: int
    avg_cpu_usage_millicores: int
    avg_memory_usage_mb: int
    
    # Economics
    estimated_hourly_savings: float
    estimated_monthly_savings: float
    savings_percentage: float
    confidence: str                           # HIGH / MEDIUM / LOW
    
    # Instance-Aware Fields
    is_actionable: bool                       # False if no better pool exists
    best_pool: Optional[Dict[str, Any]]       # Best spot pool for new size
    risk_prob: Optional[float]                # Pool risk probability
    capacity_status: Optional[str]            # Pool capacity status
```

### 12.2 ClusterKarpenterConfig

**File:** `backend/api/karpenter_routes.py`

```python
class ClusterKarpenterConfig(BaseModel):
    cluster_id: str
    strategy: str = "balanced"
    instance_families: List[str] = ["m5", "m6i", "c5", "c6i"]
    architectures: List[str] = ["amd64"]
    spot_target_pct: int = 75
    on_demand_fallback: bool = True
    min_vcpu: int = 2
    max_vcpu: int = 16
    min_memory_gib: int = 4
    max_memory_gib: int = 64
    consolidation_enabled: bool = True
    consolidation_threshold_pct: int = 60
    node_max_lifetime_days: int = 7
    cost_alert_monthly: Optional[float] = None
    cost_alert_hourly: Optional[float] = None
    daily_budget: Optional[float] = None
```

### 12.3 KarpenterApplyRequest

```python
class KarpenterApplyRequest(BaseModel):
    recommended_type: str
    reason: Optional[str] = None
    is_stateful: bool = False
    instance_id: Optional[str] = None
    spot_pool: Optional[Dict[str, Any]] = None
```

---

## 13. End-to-End Request Flow

### 13.1 Fetching Recommendations (User Opens Dashboard)

```
Browser                          Backend                          DB/Redis
  │                                │                                │
  │ GET /pod-metrics/right-sizing/ │                                │
  │  recommendations?cluster_id=X  │                                │
  │──────────────────────────────►│                                │
  │                                │ 1. Check metric freshness      │
  │                                │──────────────────────────────►│
  │                                │◄──────────────────────────────│
  │                                │ 2. Check cooldown (Redis)      │
  │                                │──────────────────────────────►│
  │                                │◄──────────────────────────────│
  │                                │ 3. Get trust phase             │
  │                                │ 4. Query PodMetric table       │
  │                                │──────────────────────────────►│
  │                                │◄──────────────────────────────│
  │                                │ 5. Per-controller analysis     │
  │                                │    (P95, buffer, cost calc)    │
  │                                │ 6. Instance-aware filtering    │
  │                                │──────────────────────────────►│
  │                                │◄──────────────────────────────│
  │◄──────────────────────────────│ 7. Return recommendations      │
  │                                │                                │
  │ GET /ascpai/node-             │                                │
  │  recommendations?useRightsized │                                │
  │──────────────────────────────►│                                │
  │                                │ 8. Build SimulationSnapshot    │
  │                                │ 9. Run multi-cycle simulation  │
  │                                │ 10. Calculate costs/confidence │
  │◄──────────────────────────────│ 11. Return sim results         │
```

### 13.2 Applying a Recommendation (User Clicks "Apply")

```
Browser                          Backend                    Karpenter/K8s
  │                                │                            │
  │ POST /optimization/apply/{id}  │                            │
  │──────────────────────────────►│                            │
  │                                │ 1. Look up recommendation  │
  │                                │ 2. Check cooldown          │
  │                                │ 3. Check trust phase       │
  │                                │                            │
  │                                │ [Stateless]                │
  │                                │ 4. Patch NodePool          │
  │                                │──────────────────────────►│
  │                                │◄──────────────────────────│
  │                                │ 5. Activate cooldown (6h)  │
  │                                │ 6. Record to DB            │
  │                                │                            │
  │                                │ [Stateful]                 │
  │                                │ 4. Create RightsizingProposal
  │                                │    (status=PENDING)        │
  │                                │ 5. Wait for approval       │
  │                                │                            │
  │◄──────────────────────────────│ Return result              │
```

### 13.3 Combined Evaluation Flow (Optimizer Coordinator)

```
Trigger (scheduled/manual)
  │
  ▼
can_run_rightsizing_evaluation(cluster_id)
  │ ✓ Trust Phase ≥ 1
  │ ✓ Stabilization elapsed (≥1h)
  │ ✓ 24h since last evaluation
  │ ✓ No resize cooldown
  │ ✓ Circuit breaker < 3 failures
  ▼
generate_recommendations(cluster_id)
  │ → Per-controller P95 analysis
  │ → Phase-aware safety buffers
  │ → Instance-aware pool check
  ▼
Create RightsizingProposal (status=PENDING)
  │ Store ev_breakdown, net_ev
  ▼
evaluate_combined_proposal(proposal_id)
  │
  ├─► Option A: Current size + new pool ──► EV_A
  ├─► Option B: New size + best pool    ──► EV_B (re-run ML ranking)
  ├─► Option C: Do nothing              ──► EV_C = 0
  │
  ▼
Decision: max(EV_A, EV_B, EV_C)
  │
  ├─► ΔEV ≥ 3% → APPROVE → execute → COOLDOWN (6h)
  └─► ΔEV < 3% → REJECT → back to STABILIZATION
```

---

## 14. Safety & Guard Rails

### 14.1 Progressive Trust Phases

| Phase | Cluster Age | Rightsizing | Buffer | Min Samples | Risk Ceiling |
|-------|-------------|-------------|--------|-------------|-------------|
| **0** | 0–30 min | **Blocked** | 30% | 500 | 0.15 (15%) |
| **1** | 30 min–2h | Conservative | 25% | 500 | 0.20 (20%) |
| **2** | >2 hours | Full | 20% | 100 | Profile default |

### 14.2 Cooldown Protection

| Cooldown | Duration | Trigger |
|----------|----------|---------|
| Resize Cooldown | **6 hours** | After any resize execution |
| Pool Switch Cooldown | **30 minutes** | After any pool switch |
| On-Demand Fallback | **12 hours** | After emergency OD switch (auto-reverts) |

### 14.3 Circuit Breaker

- **Threshold:** 3 resize failures within 24 hours
- **Redis key:** `resize:failure_count_24h:{cluster_id}` (24h TTL)
- **Effect:** Blocks all further rightsizing until counter expires

### 14.4 Oscillation Prevention

- **Pending Proposal Freeze:** While a `RightsizingProposal` is `PENDING`, pool optimization is blocked
- **24-Hour Interval:** Rightsizing evaluation runs at most once per 24 hours
- **Phase Sequencing:** Pool optimization must complete and stabilize before rightsizing is allowed
- **Combined EV Gate:** Only execute if ΔEV ≥ 3% improvement over doing nothing

### 14.5 Workload-Specific Guards

| Guard | Rule |
|-------|------|
| **Stateful Protection** | Stateful nodes are On-Demand only, no spot migration |
| **Stateful Max Downscale** | Configurable cap (default 25%, range 10–75%) |
| **Stateful Approval** | `require_approval=true` by default — needs manual approval |
| **DaemonSet Exclusion** | DaemonSet pods excluded from rightsizing recommendations |
| **System Pod HA** | System pods distributed across AZs in simulation |
| **PDB Respect** | Batch sizing respects PodDisruptionBudgets |

### 14.6 Metric Quality Guards

| Guard | Rule |
|-------|------|
| **Freshness** | Reject if latest metric > 5 minutes old |
| **Sample Count** | Phase 0–1: min 500 samples. Phase 2: min 100 |
| **Coverage** | HIGH confidence requires ≥50% window coverage |
| **Volatility** | Skip if P50 < 5% of P99 (extreme spike workload) |
| **P99 Floor** | Recommended always ≥ P99 × 1.3 (burst safety) |

---

## Source File Index

| File | Purpose |
|------|---------|
| `backend/services/simulation_engine.py` | Multi-cycle Karpenter simulation engine |
| `backend/services/rightsizing_service.py` | Pod-level P95 analysis and recommendation generation |
| `backend/services/optimizer_coordinator.py` | Phase-based coordinator preventing oscillation |
| `backend/services/karpenter_service.py` | K8s NodePool management and ML ranking sync |
| `backend/api/karpenter_routes.py` | Karpenter config and status API endpoints |
| `backend/api/pod_metrics_routes.py` | Rightsizing recommendation API endpoint |
| `backend/api/optimizer_coordinator_routes.py` | Optimizer phase and proposal API endpoints |
| `backend/models/rightsizing_proposal.py` | RightsizingProposal SQLAlchemy model |
| `backend/schemas/pod_metric_schemas.py` | RightSizingRecommendation Pydantic schema |
| `backend/core/decision_engine.py` | EV calculation functions |
| `backend/core/scoring.py` | Risk scoring functions |
| `backend/redis_keys.py` | Redis key pattern definitions |
| `frontend/src/components/clusters/ClusterDetails.jsx` | Cluster settings + automation toggles |
| `frontend/src/components/right-sizing/RightSizingDashboard.jsx` | Full rightsizing dashboard UI |
| `frontend/src/components/right-sizing/RightSizingKarpenterTab.jsx` | Karpenter monitoring tab |
| `frontend/src/services/api.js` | Frontend API service calls |
