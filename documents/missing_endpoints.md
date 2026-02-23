# Missing API Endpoints / Fields for Right-Sizing Dashboard

While integrating the new RightSizingDashboard, several fields used in the UI mock data (from `changelogic.md`) were identified as either missing or requiring better backend support. The frontend currently uses approximations or hardcoded fallbacks for these fields.

## 1. Karpenter Node Recommendations (`/api/v1/karpenter/recommendations`)
The new UI requires more granular node-level metrics:
- `curCpu` & `curMem`: Currently not provided directly for the *node*, only for the pods via `details`.
- `cpuPeak` & `memPeak`: Not returned by the API; frontend estimates these as `avg + 20%`.
- `pods`: The UI can render a "Bin Packing" visualization of workloads running on the node (`[{ name, cpu, mem }]`). The backend currently only returns `affected_pods: int`. We need the actual pod distribution to draw the bin blocks truthfully.
- `conf` / `pool`: The backend provides `confidence` and `risk_level`, but not the exact string equivalents ("High", "Low", "Healthy", "Risky") the UI originally used.

## 2. Global Clusters (`/api/v1/clusters`)
- The UI expects Karpenter-specific configuration states per cluster like `score`.
- `agentVersion` and `status` mappings are needed inside the cluster payload.

## 3. History & Activity (`/api/v1/karpenter/activity`)
- Similar to recommendations, `binBefore` and `binAfter` arrays are required to show how pods were reorganized across nodes after an optimization.

## 4. Savings Tracker (`/api/v1/karpenter/stats`)
- The UI filters by `1m`, `3m`, `6m`, but the backend only natively supports `week` | `month` | `all`.
- It expects an array like `[ { m: "Sep", real: 1240, pot: 5800 } ]` representing historical trends per month. The backend currently provides `cost_trend` with "Week 1", "Week 2", etc.
