# Client Dashboard Specification

Based on the comprehensive architecture of **Spot Optimizer** and referencing `feature_mapping.md` / `CAST_AI_IMPLEMENTATION_PLAN.md`.

## 1. 🚀 Dashboard (The Executive View)
**Purpose**: Instant visibility into value delivery (Savings) and System Health.

### KPI Cards
- **Net Savings ($)**: Total money saved this month vs. On-Demand baseline.
- **Current Spend Rate ($)**: Projected end-of-month bill.
- **Efficiency Score (%)**: (Resource Usage / Resource Requests).
- **Spot Coverage (%)**: Percentage of workloads running on Spot instances vs. On-Demand.

### Visuals
- **Savings Graph**: Bar/line chart showing daily spend vs. On-Demand cost.
- **Cluster Map**: High-level status of all connected clusters (Green/Red based on Heartbeat).

## 2. 🖥️ Cluster Management (Inventory)
**Purpose**: Manage the connection between the Platform and Kubernetes.

- **Cluster Registry**: List of all K8s clusters.
- **Connection Wizard**:
  - "Add Cluster" Button with helm install command generation (unique API Key).
  - Connection Status: "Heartbeat" indicator.
- **Cluster Detail View**:
  - Node List: EC2 instances (Type, Lifecycle, % CPU Util).
  - Instant Rebalance: "Optimize Now" button to trigger Bin Packer.

## 3. ⚙️ Automation Policies (The Control Plane)
**Purpose**: Configure rules of engagement (Savings vs. Uptime).

### A. Provisioning Strategy
- **Lifecycle Mix**: Spot/On-Demand Ratio slider (e.g., 20/80).
  - Base Capacity: "Always keep first [X] nodes On-Demand".
- **Spot Selection**:
  - Lowest Price
  - Capacity Optimized
  - AI Balanced (MOD-AI score)
- **Fallback & Recovery**:
  - On-Demand Fallback toggle.
  - Spot Reversion: Retry after [X] minutes.

### B. Scheduling & Maintenance Windows
- **Optimization Schedule**:
  - "Always On" vs "Maintenance Windows Only".
- **Blackout Periods**: Calendar integration (e.g., Black Friday).

### C. Workload Constraints
- **Exclusion Rules**: By Namespace, Label, Annotation.
- **Headroom (Buffer)**: "Maintain [X%] extra CPU and [X GB] extra RAM".
  - Dynamic Buffer option.

### D. Node Specifications
- **Instance Constraints**: Allowed Families (c5, m5, etc.), Architectures (x86/ARM), Generation.
- **Storage**: Default EBS Size/Type.

### E. Aggressiveness Settings
- **Bin Packing Intensity**: Passive, Balanced (Default), Aggressive.
- **Node Lifetime**: "Do not terminate nodes running for less than [X] minutes".

## 4. 📝 Node Templates (Infrastructure Specs)
**Purpose**: Define compute "shapes" (Karpenter Provisioners).

- **Template Builder**:
  - Instance Families, Architectures, Storage Config.
  - Security Groups/Subnets (from AWS Discovery).

## 5. 📉 Workload Rightsizing (Efficiency)
**Purpose**: Move beyond simple "Current vs. Request".

### A. Deep-Dive Visualization
- **Historical Usage vs. Proposal**: Time-series graph (Usage vs Request vs Proposed).
- **Throttling Events Tracker**: Visual markers for CPU throttling.
- **Waste Heatmap**: Treemap (Size=Cost, Color=Severity).

### B. Automation Workflows
- **GitOps Integration**: PRs to client Git repo.
- **Live Autoscaling (VPA Mode)**: In-Place Updates toggle.

### C. Advanced Granularity
- **Sidecar Tuning**: Specific settings for auxiliary containers.
- **Burst Configuration**: Ratio between Request and Limit.

### D. Intelligence & Safety
- **Confidence Score**: AI Confidence badge.
- **Gold Standard Profiles**: Critical vs Batch profiles.
- **Ignore Rules**: For new workloads.

## 6. 💤 Hibernation (Cost Schedules)
**Purpose**: Turn off infrastructure when not in use.

- **Visual Scheduler**: Google Calendar-style grid (24x7).
- **Drag-and-Draw**: Green (Uptime) / Gray (Downtime).
- **Overrides**: "Wake Up for 2 Hours" button.

## 7. 🧾 Settings & Integrations
**Purpose**: Account administration.

- **Cloud Integrations**: AWS Cross-Account Role setup/validation.
- **Billing Portal**: Plan, Credit Card, Invoices.
- **Team Management**: Invite users, roles (Admin/Read-Only).

## 8. 🛡️ Audit Log (Trust & Safety)
**Purpose**: Transparency.

- **Event Feed**: Termination, Launch, Hibernation events.
- **Diff View**: JSON diff of cluster state changes.

## 🗺️ Navigation Structure (Sidebar)
Refrain from other structures. Strict flow:
1. Dashboard
2. Clusters
3. Policies
4. Templates
5. Right-Sizing
6. Hibernation
7. Audit Logs
8. Settings
