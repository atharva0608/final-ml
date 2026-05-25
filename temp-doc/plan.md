# MVP Demo — Coding Agent Execution Plan
**Target: Tomorrow's Demo | Written for: Autonomous Coding Agent**
**Principle: Real data only. No seeding. No mocking numbers. If real data is not available, the feature showes n/a.**

---

## GROUND TRUTH — What We Know For Certain

| Component | State | What This Means |
|---|---|---|
| `pod_metrics` table | 102k rows, 3 days stale | Agent stopped posting — must restart agent first |
| WIE classifications | 21 workloads, 5 CONFIRMED | Works immediately, no metrics needed |
| `rightsizing_proposals` | ZERO rows | Proposal pipeline never completed — fix in Phase 2 |
| `agent_actions` | Only 2 Karpenter installs | No optimization actions ever executed |
| Resize guard Redis keys | All empty | Dead code — ignore entirely |
| Frontend Overview.jsx | 100% hardcoded mock | Wire to real APIs |
| Frontend Rightsizing view | Real API + graceful fallback | Mostly working |
| Backend containers | Currently stopped | Start before everything |

---

## UI FILE AUDIT — What Each File Actually Shows vs What Is Missing

This section was added after reading all 6 frontend files. The agent must
read this before touching any frontend file in Phase 4.

### WorkloadProfiling.jsx — STATUS: GOOD, minor gaps

**What it already shows correctly:**
- WIE tier, confidence_state, spot_score, criticality_score with progress bars ✅
- OD/Spot distribution bar (WIE constraint vs Policy target) ✅
- Spot eligibility badge (FULLY SPOT / PARTIALLY SPOT / OD ONLY) ✅
- CPU timeseries sparkline (14-day daily avg) ✅
- Coefficient of variation (CV) with stable/skew label ✅
- Advisor actionability gates (7 checks, pass/fail) ✅
- Signals fired list ✅
- DB/stateful workload detection (Always OD badge) ✅

**What is MISSING and must be added in Phase 4:**
- No `burst_ratio` display — add to identity section alongside CV
- No `throttle_risk` badge — add to spot eligibility badge area
- No `workload_hint` (JVM) badge — add next to tier badge in list and detail
- No `currently_spiking` indicator — add ⚡ Active Spike badge
- No per-pod resource utilization breakdown (CPU requested vs P95 actual bar)
  — the sparkline shows daily CPU avg trend, but there is no
  "requested: 1000m / P95 actual: 220m / waste: 78%" visual for the demo
- `savings` field shown as plain `$X` with no context — add "per month" label
  and only show when `throttle_risk = False`

**Widget to add — Resource Utilization Card (new, inside right panel):**
Show only when a proposal exists for this workload (`proposal` field in detail API).
```
┌─ Resource Utilization ──────────────────────────────────────────┐
│ CPU                                                              │
│  Requested:  1000m  ████████████████████████████████████ 100%  │
│  P95 Actual:  220m  ██████                              22%     │
│  Waste:       780m  ←——————————————————————————————— 78%       │
│                                                                  │
│ Memory                                                           │
│  Requested:  2048Mi ████████████████████████████████████ 100%  │
│  P95 Actual: 1100Mi ██████████████████████           54%        │
│  Waste:       948Mi ←—————————————————————————— 46%            │
│                                                                  │
│ Burst Ratio: 6.2×  ⚠ Throttle Risk — OBSERVE only             │
└──────────────────────────────────────────────────────────────────┘
```
Data source: `proposal.current_cpu_request_millicores`,
`proposal.p95_cpu_millicores`, `proposal.burst_ratio`,
`proposal.throttle_risk` from the rightsizing API.
If no proposal exists for the workload → hide this card entirely (do not show zeros).

---

### WorkloadPlacement.jsx — STATUS: GOOD, no critical gaps

**What it already shows correctly:**
- Real EE state machine progression (PROVISIONING → EXECUTING → DRAINING → VERIFYING) ✅
- Execution plan: nodes to provision, nodes to drain, pod movements table ✅
- OD/Spot distribution bar per workload ✅
- CPU/memory totals in the execution plan ✅
- Capacity plan (total CPU/memory for OD and Spot separately) ✅
- Future node list with cpu utilization bar after packing ✅
- Per-node schedule progress steps ✅

**What is MISSING:**
- No `throttle_risk` guard on the migration trigger — if a workload has
  `throttle_risk = True`, the migration button must be disabled with tooltip
  "Throttle risk — resolve sizing issue before migrating to spot"
- No `currently_spiking` guard — if spike is active, disable migration
  with tooltip "Active CPU spike — migration paused"

These are safety guards, not display changes. Add them to the workload
selection logic that determines whether a migration can be triggered.

---

### WorkloadMigration.jsx — STATUS: GOOD

**What it already shows correctly:**
- Full EE state machine visualization with animated steps ✅
- Execution plan section (provision + drain nodes, pod movement table) ✅
- Migration history list ✅
- Decision engine blacklist status ✅
- Cooldown timer ✅
- Manifest status with TTL ✅

**What is MISSING:** Nothing critical for the demo. This file is complete.

---

### WorkloadScaling.jsx — STATUS: GOOD, one gap

**What it already shows correctly:**
- HPA config table (min, max, target CPU, recommended values) ✅
- Scale event timeline bar chart (120m snapshots) ✅
- Replica efficiency breakdown (serving/idle/draining) with color bar ✅
- Cooldown audit table ✅
- KEDA badge ✅
- Replica utilization bar: current/max replicas shown as progress bar ✅

**What is MISSING:**
- `Avg Scale Latency`, `Idle Replica Waste`, `VPA Recommendations` in the
  summary strip are hardcoded `'—'` — these will never show values because
  the backend does not compute them. That is fine. Just make sure they are
  NOT shown to the audience as "coming soon" — either hide those 3 summary
  cards or label them "Post-MVP" in a comment. Do not try to compute them tonight.

---

### NodeBinPacking.jsx — STATUS: GOOD

**What it already shows correctly:**
- CPU and memory utilization bars per node ✅
- Consolidation candidate detection (< 60% CPU = drain candidate) ✅
- Packing simulation with headroom visualization ✅
- Pod list with CPU/memory requests ✅
- Summary strip: avg CPU util, consolidation candidates, est savings ✅

**What is MISSING:** Nothing critical for the demo.

---

### NodeSelector.jsx — STATUS: GOOD, one gap

**What it already shows correctly:**
- Node plan (provision/drain/keep actions) ✅
- Pod movement plan ✅
- Per-node resource bars (cpu_actual_pct, cpu_requested_pct) ✅
- Plan summary (estimated savings, AZ breakdown) ✅
- Future node capacity (CPU/memory total requested) ✅

**What is MISSING:**
- The `cpu_actual_pct` bar shows actual utilization, but there is no
  "requested vs actual" split bar for the demo's "overprovisioned" story.
  The NodeBinPacking file has a better version of this. The NodeSelector
  bar is sufficient — do not rebuild it.

---

## REALITY CHECK — What Is Real AWS/K8s Code vs What Is Not

The agent must understand this before deciding what to demo.
Everything in the REAL column works on a live EKS cluster with real AWS APIs.

### CONFIRMED REAL — Will Work On A Live AWS Account ✅

| Area | What Is Real |
|---|---|
| **Workload Identification** | Reads live pod specs, detects Deployment/StatefulSet, checks replicas, PDBs, affinity, tolerations — real K8s API calls |
| **Spot Classification** | `spot_friendly`, replica check, PDB check, stateless detection, risk scoring — real backend logic, not fake AI scoring |
| **K8s Migration Operations** | Cordon, drain, pod eviction, node patching — all real K8s API calls via `auto_rebalancer.py` |
| **Karpenter Integration** | Patches NodePool CRDs live, changes capacity type, manages spot/OD transitions — real CRD interaction |
| **Rightsizing Math** | P95, P99, percentile calc, oversized detection, savings calc — real math on real metrics |
| **AWS Integration** | boto3, STS assume-role, ASG, EC2, EKS APIs — real cloud integration, not stubs |

### NOT FULLY REAL — Do Not Demo As Autonomous ⚠️

| Area | What Is Missing | Demo Rule |
|---|---|---|
| **Rollback Automation** | Redis rollback keys never written, guard metrics dead | Do NOT claim self-healing or autonomous rollback |
| **Auto Rightsizing Execution** | No throttle metrics, no working_set validation, rollback incomplete | Show recommendations only — do NOT auto-apply resize |
| **ML / AI Claims** | System is percentile heuristics + rule-based scoring | Never say "AI-driven" or "ML-powered" in the demo |
| **Scheduler Simulation** | Not kube-scheduler parity, hardcoded kube_reserved, no preemption | Do not claim precise placement accuracy |
| **Cost Engine** | Compute-only, no RI/SP/network/storage/CUR | Present as "compute savings estimate" only |

### CORRECT DEMO POSITIONING

Do NOT say: "Fully autonomous AI optimization platform"
DO say: "Intelligent Kubernetes cost optimization — platform recommends, operator approves"

Enterprise buyers trust manual approval MORE at MVP stage.
One successful controlled migration is worth more than claiming full autonomy
with an incomplete rollback path.

---

## TWO INDEPENDENT DATA TRACKS — Understand This Before Touching Anything

**Track A — WIE Classification (available immediately, no metrics needed):**
```
Cluster registered → WIE reads K8s API (pod specs, owner refs,
replicas, PDB, tolerations, affinity, restart count) →
tier + spot_friendly + confidence_state → ready in minutes
```
The 21 classified workloads in DB are usable RIGHT NOW. The workload list,
tier badges, spot-friendly flags — show these immediately without waiting
for metrics. Do NOT block this view on monitoring data.

**Track B — Rightsizing / Waste Detection (needs monitoring data):**
```
Agent running → pod_metrics flowing every 5 min →
P95/P99 computed → waste % calculated → recommendation generated
```
This is gated on the agent being alive and posting. Without real metrics,
waste percentages and savings numbers cannot be shown. Do not fabricate them.

**Demo implication:** If the agent cannot be restarted tonight, the demo
shows Track A (workload identification, tier, spot classification) strongly,
and acknowledges Track B as "recommendations generate after 24h of monitoring."
That is a credible and honest MVP position.

---

## ABSOLUTE RULES FOR TONIGHT

**DO NOT touch these — working and fragile:**
- `workload_identification_engine.py` — classification logic
- `rightsizing_service.py` — `_calculate_statistics()` percentile math
- `eviction_safety.py` — PDB checks
- `distribution_engine.py` — wave execution
- `auto_rebalancer.py` — cordon/drain inline K8s calls
- Any existing `agent_actions` polling loop in the frontend

**DO NOT attempt to fix tonight — out of scope:**
- Resize guard Redis key writes (`metrics:cpu_avg_10m` etc.) — confirmed dead code
- Rollback consumer original-resources lookup
- RI / Savings Plans cost modelling
- Cross-cluster aggregation
- `PlacementRolloutService` — confirmed stub
- GPU optimization
- WIE enforcement mode — observation-only by design
- BestEffort QoS rightsizing — no request baseline, exclude not fix
- Batch/CronJob optimization — correctly skipped by backend, hide in UI not build logic
- CFS throttle metric collection — post-demo work, handled by heuristic tonight (Phase 2B)

**DO NOT demo tomorrow:**
- Automatic rightsizing execution (PATCH_CONTAINER_RESOURCES)
- Rollback flow or self-healing claims
- Emergency fallback
- ML / AI / predictive language of any kind
- Any number not backed by a real DB row
- Any claim of production-readiness or full autonomy

**5 HARD DEMO RULES — agent must enforce these in every decision:**

Rule 1 — SAFE WORKLOADS ONLY for migration:
Only Deployments, replicas ≥ 2, no StatefulSets, no singleton pods,
no local storage, no GPU workloads. Any other workload type → do not migrate.

Rule 2 — NO LIVE AUTO-RESIZING:
Generate and display recommendations. Do NOT automatically patch container
resources. This is the highest-risk action given incomplete rollback.

Rule 3 — REAL METRICS ONLY:
If metrics are stale or missing → show workload classification only.
Do not fabricate savings numbers. Do not show $0 or placeholder values.

Rule 4 — MANUAL APPROVAL IS THE FEATURE, NOT A LIMITATION:
The demo story is "platform recommends, operator approves."
This is intentional product positioning. Enterprise buyers prefer this.

Rule 5 — ONE CLEAN MIGRATION BEATS TWENTY UNSTABLE ONES:
Prepare and test exactly one migration target tonight.
If it works cleanly, that is the demo. Do not add more targets.

---

## BIGGEST REAL RISKS FOR TOMORROW — Agent Must Pre-Empt These Tonight

These are the most likely failure points during the demo.
The agent must verify and mitigate each one before stopping work tonight.

**Risk 1 — Metrics Agent Dead (Highest Priority)**
If agent is not posting, there are no waste numbers, no P95/P99, no savings.
The entire Track B demo collapses. This is why Phase 1 is the first thing done.
Mitigation: restart agent tonight, verify rows appear in pod_metrics.
If agent cannot be restarted: pivot to Track A only demo (classification + migration).

**Risk 2 — Drain Hanging During Demo**
A pod stuck in Terminating (finalizer deadlock, webhook, PVC) will freeze
the migration flow in front of the audience.
Mitigation: the 120s hard timeout in Phase 5 must be implemented.
Pre-test the drain on the target workload tonight before demo.
Verify no stuck pods, no webhook interceptors on the target namespace.

**Risk 3 — Spot Node Not Joining After Migration**
Possible causes: Karpenter misconfiguration, IAM permission missing on
the node role, subnet capacity in the target AZ, EC2 spot capacity unavailable.
Mitigation: pre-test spot node provisioning tonight by cordoning a node
and watching Karpenter provision a replacement. If Karpenter fails,
switch to dry_run simulation mode for the demo migration.

**Risk 4 — Recommendations Returning Empty**
Very likely if coordinator never ran, metrics are stale, or DB flags disabled.
Mitigation: Phase 2A investigates and fixes this. Do not skip Phase 2A.
If coordinator cannot be fixed, use the bypass script path.

**Risk 5 — Frontend Showing Hardcoded Numbers**
Even one fake chart or hardcoded dollar value visible during demo destroys
trust immediately. Audiences notice when numbers never change.
Mitigation: Phase 4 removes all mock constants from Overview.jsx.
Phase 7 Check 4 verifies no zero or null savings values in API response.

---

## PHASE 0 — Start the System (~15 min)

Start postgres, redis, and the FastAPI backend. Verify:
- Backend responds to HTTP health endpoint
- `redis-cli ping` returns PONG
- Postgres tables exist and are queryable

Do NOT start Celery workers yet — start them only after Phase 1 agent
restart is confirmed working.

---

## PHASE 1 — Restart the Metrics Agent (Critical Path, ~45 min)

### Problem
pod_metrics are 3 days stale. The in-cluster agent on `spot-demo-1` stopped
posting. Everything in Track B depends on this agent being alive.

### Step 1.1 — Determine cluster status

Check whether `spot-demo-1` EKS cluster still exists:
```bash
aws eks list-clusters
aws eks describe-cluster --name spot-demo-1
```

**If cluster exists → go to Step 1.2**
**If cluster is torn down → go to Step 1.3**

### Step 1.2 — Restart the agent pod (cluster alive)

1. Find the agent pod in the cluster:
   ```bash
   kubectl get pods -A | grep spot
   ```

2. Check agent logs for why it stopped:
   ```bash
   kubectl logs <agent-pod> --tail=50
   ```
   Common reasons: backend URL unreachable, auth token expired, OOMKilled.

3. Fix the root cause (update backend URL env var, rotate token, adjust
   memory limit).

4. Restart the agent pod:
   ```bash
   kubectl rollout restart deployment/<agent-deployment> -n <namespace>
   ```

5. Verify it posts metrics. Watch backend logs for incoming
   `POST /api/v1/pod-metrics/batch`. Wait 10 minutes, then check:
   ```sql
   SELECT COUNT(*), MAX(created_at) FROM pod_metrics
   WHERE created_at > NOW() - INTERVAL '15 minutes';
   ```
   If rows appear → Phase 1 complete. The existing 102k historical rows
   spanning April–May are within the 168h analysis window — do not wait
   8 hours for new data. Trigger Phase 2 as soon as fresh rows appear.

### Step 1.3 — If Cluster Is Torn Down

**Do not seed data. Make a decision between two options:**

**Option A — Spin up a minimal EKS cluster tonight:**
- 2 nodes, t3.medium
- Deploy real workloads (nginx with high requests, a Spring Boot app if
  available, a StatefulSet like Redis or Postgres)
- Install the agent and let it run
- Real metrics appear within 1–2 hours
- This is the preferred option if time permits

**Option B — Demo Track A only (workload identification):**
- The 21 classified workloads in DB are real and usable now
- Show WIE classification, tier, spot-friendly scoring, PDB detection
- The demo story becomes: "Watch us classify your workloads in real-time.
  Rightsizing recommendations appear after 24 hours of monitoring"
- This is honest and still a credible MVP

Option C does not exist. Seeded fake metrics are not an option.

### Verify Phase 1 Complete
```sql
SELECT COUNT(*), MAX(created_at)
FROM pod_metrics
WHERE created_at > NOW() - INTERVAL '3 hours';
```
Must return COUNT > 0 and MAX within last 15 minutes.

---

## PHASE 2A — Make Rightsizing Proposals Generate (~1.5 hrs)

### Problem
`rightsizing_proposals` has zero rows. The `optimizer_coordinator` never
completed a run. This must be fixed before the recommendations view has
anything to show. This phase only runs if Phase 1 succeeded (fresh metrics exist).

### Step 2A.1 — Investigate why coordinator never ran

Search codebase in this order:

1. Find where `OptimizerCoordinator` is instantiated and its main method
   called. Look for `evaluate()`, `run_cycle()`, or `run()`.

2. Find what triggers it — Celery beat schedule, API endpoint, or manual call.

3. Check cluster DB settings: `auto_rightsizing_enabled`, `optimization_strategy`,
   any `trust_phase` or `phase` field that gates the coordinator.

4. WIE engine age is 41h — any gate requiring >24h is already satisfied.

### Step 2A.2 — Fix paths (apply after investigation)

**Path A — Coordinator callable but never triggered:**
Trigger it manually for `spot-demo-1`'s cluster_id. Watch logs.
If proposals appear in DB → done.

**Path B — Coordinator blocked by cluster settings:**
Update the cluster record in DB to enable rightsizing. Then trigger (Path A).

**Path C — Coordinator crashes on run:**
Do NOT fix the coordinator tonight. Write a standalone bypass script:
- Import `rightsizing_service.py` directly
- Call `generate_recommendations(cluster_id)` for each CONFIRMED workload
- The return schema is known and verified (RightSizingRecommendation dataclass)
- Write each result row directly into `rightsizing_proposals` table
- Map every field from the dataclass to table columns
- Apply Phase 2B burst protection rules BEFORE writing (see below)

Path C output is backed by real P95/P99 computed from real pod_metrics rows.
The only thing bypassed is the EV scoring layer — the numbers are real.

### Step 2A.3 — Apply burst protection before writing any proposal

Before any proposal with `recommendation_action = REDUCE` is written to DB,
the burst ratio check from Phase 2B must run. If burst_ratio > 5.0, override
to `recommendation_action = OBSERVE` and set `throttle_risk = True`.
Details in Phase 2B.

### Verify Phase 2A Complete
```sql
SELECT controller_name, namespace, recommendation_action,
       savings_monthly, savings_pct, confidence
FROM rightsizing_proposals
WHERE cluster_id = '<demo_cluster_id>'
ORDER BY savings_monthly DESC;
```
Must return rows with real numbers. `savings_pct` between 10–95.
If savings_monthly is 0 or null — debug the metrics data or cost formula,
do not override the numbers.

---

## PHASE 2B — Spike Detection and JVM / CPU Throttle Protection

This is new logic added to every recommendation before it is stored or
returned from any API. It has two parts: a historical burst-ratio check
and a real-time active spike check.

---

### THE CORE PROBLEM — Why This Matters For JVM Microservices

Java microservices run garbage collection cycles. GC pattern in metrics:
- P50 CPU: 60m (idle between GC cycles)
- P95 CPU: 180m (minor GC)
- P99 CPU: 600m+ (major/full GC pause)
- Burst ratio (P99 / avg): 6–10×

If the platform recommends REDUCE from 1000m to 228m (P95 × 1.2),
and the container's CPU limit is set near that value, then during the
next major GC the container hits its CFS quota. The kernel throttles it.
GC cannot complete at full speed. GC takes 3–5× longer. Application
latency spikes. The JVM is degraded even though the container "appears running."

The platform currently collects ZERO CFS throttle metrics
(`container_cpu_cfs_throttled_seconds_total` does not exist anywhere in
the codebase). The burst ratio is the only proxy available tonight.
Post-demo, real CFS metrics must be collected (see Phase 6).

---

### PART 1 — Historical Burst Ratio (applies to stored proposals)

**After computing P50, P95, P99, avg for CPU — add this calculation:**

```
burst_ratio = p99_cpu_millicores / max(avg_cpu_millicores, 1)
```

**Thresholds and actions:**

| burst_ratio | Classification | Action |
|---|---|---|
| < 3.0 | Normal | Safe to REDUCE if oversized |
| 3.0 – 5.0 | Elevated burst | Apply P99 × 1.5 floor instead of P99 × 1.3 |
| > 5.0 | High burst | Override to OBSERVE, set throttle_risk = True |

The `burst_ratio` value and `throttle_risk` boolean must be stored on
the proposal record and returned in every API response.

**JVM pattern heuristic — apply stricter thresholds if ANY of these are true:**

Check 1 — Memory-to-CPU ratio:
```
memory_to_cpu_ratio = memory_request_mb / (cpu_request_millicores / 1000)
```
If ratio > 4 (e.g., 2GB RAM with 500m CPU) → likely JVM.

Check 2 — Image name (only if agent collects container image names):
Scan for: `java`, `spring`, `jvm`, `tomcat`, `quarkus`, `micronaut`,
`openjdk`, `amazoncorretto`, `adoptopenjdk`

Check 3 — Memory growth pattern:
If `memory_p99 / memory_avg > 1.8` → heap growth pattern.

If ANY check is true, set `workload_hint = JVM` and:
- Lower the high-burst threshold from 5.0 to 3.0
  (i.e., JVM workloads get OBSERVE at burst_ratio > 3.0 instead of > 5.0)
- Apply P99 × 1.6 as CPU floor instead of P99 × 1.3
- Never recommend REDUCE if burst_ratio > 3.0

**Where to implement:**

Find the right insertion point — pick whichever requires least change
to existing working code:

Option A: Inside `generate_recommendations()` in `rightsizing_service.py`,
after `_calculate_statistics()` returns but before the final recommendation
dict is assembled.

Option B: In the route handler or service method that prepares the API response,
as a post-filter that overrides `recommendation_action` before returning.

Option C: In the Phase 2A bypass script, when mapping dataclass output to
DB row before writing.

The burst_ratio math is pure arithmetic on already-computed fields.
No new DB queries, no new metrics collection required tonight.

---

### PART 2 — Real-Time Active Spike Detection

This detects a CPU spike happening RIGHT NOW on a running workload.

**In the agent's metric submission handler** (the endpoint that receives
`POST /api/v1/pod-metrics/batch`), add this check after ingesting each batch:

For each workload in the batch:
1. Get the 3 most recent CPU readings just ingested (last 15 minutes)
2. Get the 60-minute rolling average from the existing pod_metrics rows
3. Compute: `spike_ratio = latest_cpu / rolling_avg_60min`
4. If `spike_ratio > 3.0`:
   - Write Redis key: `spike:active:{cluster_id}:{namespace}/{workload_name}`
   - TTL: 900 seconds (15 minutes)
   - If spike persists, the next batch submission will renew the key
   - Key auto-expires when spike subsides

**In the recommendations API response:**

For each recommendation, check if this Redis key exists.
If it does → set `currently_spiking = True` in the response.
If not → `currently_spiking = False`.

**Rule: if `currently_spiking = True`, the REDUCE action button is disabled
in the UI.** The recommendation is still shown (so it can be acted on when
the spike subsides) but the action is suppressed with tooltip:
"Active spike detected — recommendation paused until workload stabilizes."

---

### WHAT TO SHOW IN THE UI FOR THROTTLE-RISK WORKLOADS

These workloads must NOT show a savings estimate or a REDUCE action button.
Show instead:

```
Workload: payment-api
CPU Request: 1000m  |  P95 Usage: 220m  |  Burst Ratio: 6.2×
Status: ⚠ Throttle Risk Detected
Hint: JVM Detected — Conservative Sizing Applied
Reason: High CPU burst pattern. Reducing requests may cause CFS
        throttling during GC cycles. Platform is monitoring.
Action: OBSERVE — No resize recommended until burst stabilizes
```

This is more intelligent than a naive REDUCE recommendation and is
completely honest about platform limitations.

---

## PHASE 3 — Fix the Recommendations API Endpoint (~30 min)

### Step 3.1 — Confirm correct route

Confirmed routes:
- `GET /api/v1/pod-metrics/right-sizing/recommendations?cluster_id=<id>`
- `GET /api/v1/pod-metrics/rightsizing/enriched?cluster_id=<id>`

Find which one `useRightsizing.js` calls. If wrong path, update the hook's
URL constant. Do not add a new route.

### Step 3.2 — Check response schema vs frontend expectations

Backend returns snake_case (Pydantic). Frontend may expect camelCase.
If mismatch, fix on ONE side only — prefer the backend.

### Step 3.3 — Extend response schema with new fields

Every recommendation response must include:
- `burst_ratio: float`
- `throttle_risk: bool`
- `workload_hint: str` (values: "JVM", "BATCH", "NORMAL")
- `currently_spiking: bool`
- `current_cpu_request_millicores: int` — needed by the utilization bar
- `p95_cpu_millicores: int` — needed by the utilization bar
- `current_memory_request_bytes: int` — needed by the memory utilization bar
- `p95_memory_bytes: int` — needed by the memory utilization bar

These must be present (even if False/NORMAL/0) on every record so the
frontend can render badges and bars without null checks.

### Step 3.4 — Filter zero-request workloads at response layer

After recommendations are computed, before returning:
- Remove any result where `current_cpu_request = 0` AND
  `current_memory_request = 0`
- These are BestEffort pods — no savings baseline exists
- Do not try to fix the math — exclude them
- They still appear in the workload classification view with
  `No Requests Set` badge

### Step 3.5 — Performance check

Endpoint must respond in < 2 seconds × 3 consecutive calls.
If slow, find the N+1 query (likely per-workload stats recomputed from
raw pod_metrics on every request). Add `LIMIT 100` to inner query as
stopgap. No new indexes tonight unless response > 10 seconds.

### Verify
`curl` the endpoint. Real JSON array. No `savings_pct = 0`.
No `savings_monthly = null`. No `burst_ratio` field missing.
No `current_cpu_request_millicores` field missing.

---

## PHASE 4 — Fix the Frontend for Demo (~1.5 hrs)

### Rule: Only the demo pages. Do not touch WorkloadMigration, WorkloadScaling,
### NodeBinPacking, or NodeSelector — they are already correct.

Demo pages: Cluster Overview, WorkloadProfiling (workload list + detail),
and the Recommendations view.

### Step 4.1 — Fix Overview.jsx (currently 100% mock)

Wire to real API endpoints. Replace mock constants with real API calls.
If no single endpoint returns all needed values, compute client-side from
rightsizing API response. Do not add new mock constants.

Must show:
- Total workloads analyzed (real count from WIE)
- Overprovisioned workload count (`is_oversized = True` from proposals)
- Total monthly waste (sum of `savings_monthly` across proposals)
- Spot vs On-Demand node split (real, if available)
- One bold hero savings number in dollars

### Step 4.2 — WorkloadProfiling.jsx — add 4 missing elements

The file already has all the core classification UI working correctly.
Add only these 4 things, nothing else:

**4.2.1 — Resource Utilization Card** (add to right panel, after WIE scores)

Render this card only when `detail?.proposal` is non-null (meaning a
rightsizing proposal exists for this workload AND metrics are available).
If no proposal → the card does not render. No zeros, no placeholders.

The card shows two progress bar rows, one for CPU, one for memory:

CPU row:
- `Requested` bar: width = 100%, color = gray-300, label = `{current_cpu_request_millicores}m`
- `P95 Actual` bar: width = `(p95_cpu_millicores / current_cpu_request_millicores) * 100`%,
  color = indigo-500 if waste < 50%, amber-500 if waste 50-80%, red-500 if waste > 80%
- `Waste` label: `{Math.round((1 - p95/request) * 100)}%` shown in red if > 50%

Memory row: same structure using `current_memory_request_bytes` and `p95_memory_bytes`.

Below the bars, show burst ratio and throttle risk:
- If `throttle_risk = True`: show `⚠ Burst Ratio: {burst_ratio.toFixed(1)}× — OBSERVE only` in amber
- If `workload_hint = 'JVM'`: show `☕ JVM Detected — conservative floor applied` in blue
- If `currently_spiking = True`: show `⚡ Active Spike` in red
- Otherwise if `burst_ratio >= 3`: show `Burst Ratio: {burst_ratio.toFixed(1)}×` in gray

Data comes from `detail.proposal` which must be populated by the API
call in `optimizeAPI.getWorkloadProfilingDetail()`.

**4.2.2 — throttle_risk badge** (add to the workload list rows and detail header)

In the list row (left panel), alongside the spot eligibility badge:
- If `row.throttleRisk = True`: render `⚠ Throttle Risk` in amber, same
  style as existing `Dist pending` badge
- If `row.workloadHint = 'JVM'`: render `☕ JVM` badge in blue next to tier

In the detail header (right panel), alongside existing spot eligibility badges:
- If `w.throttleRisk`: render `⚠ Throttle Risk` badge before the spot badge
- If `w.currentlySpiking`: render `⚡ Active Spike` badge in red

Map these fields in `mapListItem()`:
```js
throttleRisk:      w.throttle_risk || false,
workloadHint:      w.workload_hint || 'NORMAL',
currentlySpiking:  w.currently_spiking || false,
```
These fields come from the workload classification API enriched with
proposal data, OR from a joined endpoint. If the workload classification
API does not return them, add a second fetch in the `useEffect` that
loads proposals and merges `throttle_risk`, `workload_hint`,
`currently_spiking` into the workload list by matching on
`controller_name + namespace`.

**4.2.3 — savings label fix** (one-line change)

Current: `${row.savings}` — shows raw number with no context.
Fix: `${row.savings > 0 && !row.throttleRisk ? `$${Math.round(row.savings)}/mo saved` : ''}`
Do not show savings estimate for throttle-risk workloads — it is misleading
(the savings would only be real if the platform actually recommended REDUCE,
which it does not for throttle-risk workloads).

**4.2.4 — default filter update**

The current list shows all workloads sorted by spotFriendly then spotScore.
Add a filter toggle that defaults to "Optimization Candidates":

- `Optimization Candidates` (default ON):
  Include only: `confLabel` IN ('CONFIRMED', 'PROVISIONAL')
  AND `controllerKind` IN ('Deployment', 'ReplicaSet')
  AND `currentCpuRequest > 0` (exclude BestEffort — no requests set)
  AND `role !== 'SYSTEM'` AND `controllerKind !== 'DaemonSet'`

- `All Workloads`: show everything WIE observed

Filter is client-side. No new API call needed.
The toggle button goes in the filter bar alongside the existing Confidence
dropdown. Style it the same as the confidence buttons.

### Step 4.3 — Recommendations View

The recommendations view (`rightsizing` or similar page, not WorkloadProfiling)
must show each recommendation card with:
- Current monthly cost
- Optimized monthly cost
- Savings amount and percentage (only if `throttle_risk = False`)
- Recommended action badge: REDUCE (green), OBSERVE (amber), INCREASE (red)
- Confidence level badge
- `⚠ Throttle Risk` badge (amber) if `throttle_risk = True`
- `☕ JVM Detected` badge (blue) if `workload_hint = 'JVM'`
- `⚡ Active Spike` badge (red) if `currently_spiking = True`

**Resource utilization mini-bar** on each recommendation card:
Show a single-line CPU bar: `Requested: Xm [████░░░░░░░░] P95: Ym (Z% waste)`
Same logic as Step 4.2.1. This is the demo's most important visual —
it shows at a glance that the platform has real data, not fake numbers.
Width of the filled portion = `p95_cpu_millicores / current_cpu_request_millicores`.

For OBSERVE-action workloads:
- Hide the "Review Recommendation" button entirely
- Show "Monitoring — No Action Recommended" in gray italic text
- Show the throttle risk / JVM / burst ratio explanation

For REDUCE-action workloads with `currently_spiking = True`:
- Show the recommendation card with all data
- Disable the "Review Recommendation" button with tooltip
  "Active CPU spike detected — action paused until workload stabilizes"
  This is achieved by adding `disabled={item.currently_spiking}` to the button

Review Recommendation button must NOT auto-execute. Show confirmation
modal only. Do not wire to live execution tonight.

### Step 4.4 — Hide broken pages from navigation

Conditionally hide mock-only pages from sidebar nav.
Do not delete files. Add `// Hidden for MVP demo` comment on nav entry.

---

## PHASE 5 — Migration Flow Demo (~45 min)

### Demo Story
"Platform identified a workload as overprovisioned and spot-safe.
Watch it cordon the node, migrate the workload, replace with spot capacity
— PDB respected throughout."

### Step 5.1 — Verify cluster connectivity

Check how `KubernetesClientService` loads credentials (DB, file, env var).
If credentials exist and cluster alive → live migration possible.

### Pre-migration safety check (add before triggering any migration)

Before showing the migration button as enabled, verify all of these:
- `throttle_risk = False` — do not migrate workloads with CPU throttle risk
- `currently_spiking = False` — do not migrate during active spike
- `confidence_state = CONFIRMED` — only CONFIRMED workloads
- `controller_kind` IN ('Deployment', 'ReplicaSet') — no StatefulSets
- `min_replicas >= 2` — never single-replica

If any check fails → show the migration button as disabled with the specific
reason as a tooltip. Do not hide the button — show it grayed out so the
audience can see why the platform protects the workload.

### If Live Migration Is Possible

Single controlled migration only:
- Target: CONFIRMED, Deployment, replicas ≥ 2, no PDB violations, spot-safe
- Verify before demo: no active spike (`currently_spiking = False`),
  no throttle_risk flag
- Add a manual trigger endpoint if none exists:
  `POST /api/v1/debug/trigger-migration?cluster_id=<id>&workload=<name>&namespace=<ns>`
- Endpoint must: check PDB first (return 400 if violated), cordon
  least-loaded node, drain only target pods, return a pollable job ID
- Hard timeout: 120 seconds. If drain fails, reverse cordon, return error.

### If Cluster Is Down

Use `dry_run=True` simulation mode:
- API endpoint triggers full state machine with dry_run flag
- Each step writes to `agent_actions` with `status = SIMULATED`
- `EventTimeline.jsx` (confirmed real API) polls and shows steps in real time

Steps to write into agent_actions with 3-second gaps between timestamps:
```
1. CLASSIFY_WORKLOAD   SIMULATED  "Workload classified spot-safe, CONFIRMED"
2. VALIDATE_PDB        SIMULATED  "PDB validated — N replicas, safe to drain"
3. CORDON_NODE         SIMULATED  "Node cordoned — no new pods scheduled"
4. DRAIN_WORKLOAD      SIMULATED  "Workload drained and rescheduled"
5. LAUNCH_SPOT         SIMULATED  "Spot node launched in <AZ>"
6. COST_APPLIED        SIMULATED  "Saving $X/month applied"
```

---

## PHASE 6 — Post-Demo Monitoring Pipeline Roadmap
**(Reference only — not tonight's work)**

Once demo is done, correct build sequence:

**Step 1 — Robust monitoring pipeline**
Agent submits every 5 minutes reliably. Add health alert if pod_metrics
has no rows in last 10 minutes for an active cluster. No more 3-day stale.

**Step 2 — Per-workload monitoring view (new feature)**
Time-series view per workload: CPU and memory over 24h/7d.
Customers must be able to verify the platform sees what they see in Prometheus
before they trust recommendations. This view is the trust-building layer.
This is the "pod-level metrics" view called out in the product direction —
show actual CPU and memory usage over time per workload, with P50/P95/P99
overlaid as horizontal reference lines on the timeseries chart.

**Step 3 — Replace burst heuristic with real CFS throttle data**
Agent must collect `container_cpu_cfs_throttled_seconds_total` from
cAdvisor/K8s metrics API alongside existing cpu_usage_millicores.
Store as `cpu_throttled_pct` in `pod_metrics`.
A workload with `cpu_throttled_pct > 10%` must NEVER receive a REDUCE
recommendation regardless of average usage. This replaces the burst_ratio
heuristic from Phase 2B with actual throttle measurement.

**Step 4 — Spot-friendly enrichment using usage patterns**
Currently WIE uses structural signals only for spot scoring.
Enhancement: feed actual usage patterns into spot scoring.
Low CPU + low memory + low burst_ratio = stronger spot candidate.
High burst workloads get lower spot score even if stateless and multi-replica
— they are harder to migrate safely during interruptions.

---

## PHASE 7 — Sanity Checks Before Demo (~20 min)

**Check 1 — Fresh metrics exist**
```sql
SELECT COUNT(*), MAX(created_at) FROM pod_metrics
WHERE created_at > NOW() - INTERVAL '1 hour';
```
Must return COUNT > 0. Zero means agent is not running.

**Check 2 — Proposals exist with real numbers**
```sql
SELECT controller_name, recommendation_action, savings_monthly,
       savings_pct, confidence
FROM rightsizing_proposals
WHERE cluster_id = '<demo_cluster_id>'
ORDER BY savings_monthly DESC;
```
Must return rows. `savings_pct` must be between 10 and 95.
If any row has savings_pct > 95 — the CPU request or price is wrong, debug it.

**Check 3 — Burst ratio applied correctly**
```sql
SELECT controller_name, recommendation_action, throttle_risk
FROM rightsizing_proposals
WHERE cluster_id = '<demo_cluster_id>'
AND throttle_risk = True;
```
If any throttle_risk row has `recommendation_action = REDUCE` →
Phase 2B logic was not applied. Fix before demo.
These are dangerous recommendations that must not be shown.

**Check 4 — No broken waste percentages**
Hit the recommendations API. Scan the response JSON.
No result should have `savings_pct = 0`, `savings_pct = null`,
or `current_cost_monthly = 0`. If any do → BestEffort pods slipped
through the Phase 3 filter. Fix the filter, not the numbers.

**Check 5 — Workload list default view is clean**
Load workload list with default "Optimization Candidates" filter.
Only Deployment/ReplicaSet with CONFIRMED/PROVISIONAL state should appear.
No CronJobs, DaemonSets, or DRAFT workloads in default view.

**Check 6 — Spot-safe candidate exists**
At least one CONFIRMED workload must show `spot_friendly = True`,
no `throttle_risk`, no active spike. This is the migration demo target.

**Check 7 — Protected workload exists**
At least one workload must show as NOT recommended for migration
(StatefulSet, Platinum/Gold tier, or `throttle_risk = True`).
This shows the platform distinguishes safe from unsafe actions.

**Check 8 — API response time**
Hit recommendations endpoint 3 times. Each must respond < 2 seconds.

**Check 9 — Resource utilization bars render correctly** (NEW)
In WorkloadProfiling, select a workload that has a proposal.
The Resource Utilization card must appear and show non-zero values.
CPU requested bar must be wider than P95 actual bar for any REDUCE
recommendation — if they are equal or P95 is wider, the workload
is being recommended for REDUCE incorrectly.

**Check 10 — throttle_risk workload shows OBSERVE, not REDUCE** (NEW)
Select a workload with `throttle_risk = True` in the UI.
Confirm it shows the amber ⚠ badge, no savings number, no REDUCE button.
If it shows a savings number or REDUCE button → Phase 4.2.3 was not applied.

---

## DEMO NARRATIVE — Every Number Must Be a Real DB Row

```
"This EKS cluster has several massively overprovisioned workloads.

 Our platform analyzed [real N] workloads over 72 hours.
 [real N] are overprovisioned. The worst case is requesting
 [real cpu_request]m but only using [real p95]m at P95 —
 that is [real savings_pct]% waste, [real savings_monthly]/month
 on that single workload.

 The platform classified it as stateless, [real replica count] replicas,
 spot-safe, CONFIRMED. PDB validated.

 Now look at this Java microservice. We detected a 6× burst ratio —
 that is a GC spike pattern. We do NOT recommend downsizing it.
 Reducing CPU here would cause CFS throttling during garbage collection.
 The platform knows the difference between real waste and burst headroom.

 For the safe workload: watch the migration —
 cordon → drain → reschedule → spot node → done.
 Zero downtime. PDB respected throughout.

 Total identified savings: [real sum]/month = [real pct]% reduction."
```

Every bracketed value must exist as a real number in the DB.
If the number is not in the DB, do not say it in the demo.

---

## PRIORITY ORDER IF TIME RUNS OUT

1. **Must have:** Agent running + fresh metrics in DB
2. **Must have:** Real proposals in DB (Phase 2A) with burst_ratio
   protection applied (2B)
3. **Must have:** Recommendations API returning real data with throttle
   risk fields AND `current_cpu_request_millicores` + `p95_cpu_millicores`
4. **Must have:** Recommendations view showing real numbers + throttle
   risk badges + resource utilization mini-bar
5. **Should have:** WorkloadProfiling Resource Utilization card (Step 4.2.1)
6. **Should have:** Overview.jsx wired to real APIs
7. **Should have:** Workload list with filter toggle and throttle_risk / JVM badges
8. **Nice to have:** Migration flow (live or simulated)
9. **Skip:** Any UI polish, animations, new pages

A demo showing real overprovisioned workloads with real waste percentages,
one JVM workload correctly identified as throttle-risk and protected from
downsizing (with the burst ratio number visible), and the migration story
— is a genuinely strong MVP.
Do not sacrifice data correctness for feature count.