================================================================================
SPOT OPTIMIZER PLATFORM — COMPLETE PRODUCTION HARDENING INSTRUCTIONS
================================================================================
Source: Full architecture review, logic.md, all-components.md, and all prior
        technical discussion consolidated into a single instruction set.

Scope: Three fully working sections — AtharvaAI, Right-Sizing, Hibernation —
       plus all supporting settings, billing, admin, and UI wiring.

Format: Each instruction is self-contained. No "days" — just ordered tasks.
        Complete the tasks in each Phase in order. Phases within a section
        can be parallelised across teams. Cross-section dependencies are noted.

================================================================================
PART 1 — SAFETY GATES (DO THESE FIRST, BEFORE ANY OTHER CHANGE)
================================================================================

These are the two safest, highest-impact changes. They have no dependencies,
touch only one location each, and prevent live system conflicts that can cause
data loss or infinite control-plane loops.

--------------------------------------------------------------------------------
TASK 1.1 — Add Hibernation Early Gate to Control Plane Loop
--------------------------------------------------------------------------------
File: backend/workers/tasks/control_plane_loop.py
Function: run_decision_cycle(cluster_id)

Instruction:
  Add the following check as the very first two lines of run_decision_cycle(),
  before any Redis reads, pricing fetches, DryRun calls, or risk calculations.

  cluster = get_cluster(cluster_id)
  if cluster.is_hibernating:
      logger.info(f"Cluster {cluster_id} is hibernating — skipping cycle")
      return {"status": "SKIPPED", "reason": "HIBERNATING"}

Why: The control plane loop runs every 5 minutes per active cluster. If a
cluster is hibernating (NUCLEAR or SNAPSHOT_RESTORE strategy means its nodes
are stopped or terminated), the loop currently still runs — burning DryRun
budget, calling the risk engine, reading pricing data, and potentially
conflicting with the hibernation worker that owns those nodes. This check
costs one DB lookup and prevents the entire blast radius.

Do NOT place this check after any Redis reads. It must be the first operation.

--------------------------------------------------------------------------------
TASK 1.2 — Add Substitute vs Pool Rotation Mutual Exclusion
--------------------------------------------------------------------------------
File A: backend/services/pool_rotation_service.py
Function: The top of the rotation trigger function (whichever function
          initiates a rotation — search for where rotation begins)

Instruction:
  Add at the very top of the rotation trigger, before any rotation logic:

  substitute_state = redis.get(f"spot:substitute:state:{cluster_id}")
  substitute_state = substitute_state.decode() if substitute_state else "IDLE"
  if substitute_state not in ("IDLE", "FAILED", "COMPLETED"):
      logger.info(
          f"Deferring rotation for {cluster_id}: substitute in {substitute_state}"
      )
      return {"status": "DEFERRED", "reason": "SUBSTITUTE_ACTIVE"}

File B: backend/workers/tasks/hibernation_worker.py
Function: execute_hibernation task, before acquiring the distributed lock

Instruction:
  Add before the lock acquisition line:

  substitute_state = redis.get(f"spot:substitute:state:{cluster_id}")
  substitute_state = substitute_state.decode() if substitute_state else "IDLE"
  if substitute_state not in ("IDLE", "FAILED", "COMPLETED"):
      logger.warning(
          f"Deferring hibernation for {cluster_id}: substitute in {substitute_state}"
      )
      execute_hibernation.apply_async(args=[schedule_id], countdown=300)
      return

Why: The SubstituteManager has a 5-state machine (IDLE → PREWARMING → READY
→ ACTIVE → RELEASING). Pool rotation modifies AZ assignments and clears pool
ranking cache. Hibernation terminates or stops nodes. If any of these run
while a substitute is in PREWARMING, READY, or ACTIVE state, two systems are
simultaneously trying to modify the same node's lifecycle. The result is
undefined — the node can be left cordoned but not terminated, or terminated
while still flagged as a substitute target. These two checks close that window.

The substitute state key is: spot:substitute:state:{cluster_id}
States that block concurrent operations: PREWARMING, READY, ACTIVE, RELEASING
States that allow concurrent operations: IDLE, FAILED, COMPLETED

================================================================================
PART 2 — DATABASE MIGRATION (RUN BEFORE ANY EV CODE CHANGES)
================================================================================

--------------------------------------------------------------------------------
TASK 2.1 — Add EV Breakdown Fields to RightsizingProposal Model
--------------------------------------------------------------------------------
File: backend/models/rightsizing.py (or wherever RightsizingProposal is defined)

Instruction:
  Add two nullable fields to the RightsizingProposal model:

  ev_breakdown = models.JSONField(null=True, blank=True)
  net_ev = models.FloatField(null=True, blank=True)

  Then generate and run the migration:
  python manage.py makemigrations
  python manage.py migrate

  The fields must be nullable because existing in-flight proposals in the
  database were created before this migration and will not have ev_breakdown.
  The backend and frontend must both handle the null case gracefully.

Why: Once EV unification is deployed (Part 3), every new proposal will have
ev_breakdown populated. Existing proposals in PENDING state will not. The
nullable fields allow the optimizer coordinator to fall back to the old
compute_combined_expected_value() for pre-migration proposals, then switch
to ev_breakdown for all new ones.

================================================================================
PART 3 — EV UNIFICATION (CORE LOGIC — ATHARVAAI + RIGHT-SIZING)
================================================================================

This is the most important change. Currently there are four different EV
formulas running simultaneously on the same cluster in the same 5-minute
window:
  - decision_engine.py Step 9: savings × (1 - risk)
  - control_plane_loop.py Step 6: full ev_model.evaluate_candidate_ev()
  - rightsizing_service.py: savings × (1 - risk)
  - optimizer_coordinator.py: compute_combined_expected_value() (3-option simple)
  - RightSizingDashboard.jsx: savings × (1 - risk) in the browser

After these changes there will be one formula: evaluate_candidate_ev() from
ev_model.py for all execution decisions. The simple formula stays only for
pool ranking cache sorting (Tier 1 cache — not a gating decision).

--------------------------------------------------------------------------------
TASK 3.1 — Compute Dynamic Capacity Failure Probability (Helper)
--------------------------------------------------------------------------------
File: backend/core/ev_model.py  (or a new helper imported by both callers)

Instruction:
  Add this helper function. It will be called by both decision_engine.py and
  rightsizing_service.py:

  def get_dynamic_capacity_failure_probability(redis_client, pool_id, region):
      """
      Compute real observed DryRun failure rate for a pool.
      Falls back to 0.05 if no data yet.
      """
      failures_key = f"spot:dryrun_failures_24h:{pool_id}"
      count_key = f"spot:dryrun_count:{region}"

      failures = redis_client.get(failures_key)
      attempts = redis_client.get(count_key)

      failures = int(failures) if failures else 0
      attempts = int(attempts) if attempts else 1  # avoid division by zero

      probability = failures / attempts
      return min(probability, 0.50)  # cap at 50% — never assume total failure

Why: ev_model.py currently uses a hardcoded capacity_failure_probability of
0.05. Your Redis already tracks spot:dryrun_failures_24h:{pool} and
spot:dryrun_count:{region} from the DryRun capacity checks in pool ranking.
This replaces a static guess with a live signal that reflects actual AWS
capacity availability for each pool. This materially improves EV realism —
a pool with 3 DryRun failures in 24 hours genuinely has higher failure risk
than a pool with zero failures.

--------------------------------------------------------------------------------
TASK 3.2 — Replace Simple EV in Decision Engine Step 9
--------------------------------------------------------------------------------
File: backend/core/decision_engine.py
Location: Step 9 of evaluate_action_plan() — search for compute_expected_value

Instruction:
  Find the line(s) that call compute_expected_value() or that compute
  EV as savings * (1 - risk). Replace the entire block with:

  from backend.core.ev_model import evaluate_candidate_ev
  # (add this import at top of file if not already present)

  cap_fail_prob = get_dynamic_capacity_failure_probability(
      redis_client, pool_id, cluster.region
  )

  ev_breakdown = evaluate_candidate_ev(
      savings=savings,
      final_risk=final_risk,
      normalized_volatility=normalized_volatility,
      capacity_failure_probability=cap_fail_prob,
      downtime_cost_per_hour=100.0,
      risk_horizon_hours=2.0,
      recovery_time_hours=0.5,
  )

  if not ev_breakdown["is_eligible"]:
      increment_rejection_counter(cluster_id, "ev_not_eligible")
      continue

  ev = ev_breakdown["ev"]

  Do NOT remove compute_expected_value() from scoring.py yet. Mark it
  deprecated with a comment but leave it in place until all callers are
  confirmed migrated. The pool ranking Tier 1 cache (pool_ranking_service.py
  Step 7) intentionally keeps using simple EV for ranking sort order — that
  is a performance decision for cache sorting, not an execution gate.

Why: The control plane loop Step 6 already uses evaluate_candidate_ev() for
its economic assessment. The decision engine Step 9 then re-scores the same
pools using the simple formula and reaches a different conclusion. These two
evaluations run in the same 5-minute cycle on the same cluster. The result
is that the control plane approves a pool as economically viable but the
decision engine may score it differently, causing plan disagreement. After
this change both evaluations use the same formula.

--------------------------------------------------------------------------------
TASK 3.3 — Inject EV Breakdown into Rightsizing Proposals
--------------------------------------------------------------------------------
File: backend/services/rightsizing_service.py
Function: create_rightsizing_proposals()
Location: After the template filter passes, before creating the DB record

Instruction:
  Find the section of create_rightsizing_proposals() where each proposal is
  built and saved to the database. Add the following block before the
  proposal save:

  from backend.core.ev_model import evaluate_candidate_ev

  cap_fail_prob = get_dynamic_capacity_failure_probability(
      redis_client, pool_id, cluster.region
  )

  ev_breakdown = evaluate_candidate_ev(
      savings=proposal_savings,
      final_risk=risk_score,
      normalized_volatility=current_volatility,
      capacity_failure_probability=cap_fail_prob,
      downtime_cost_per_hour=100.0,
      risk_horizon_hours=2.0,
      recovery_time_hours=0.5,
  )

  proposal.ev_breakdown = ev_breakdown      # JSONField — stores full dict
  proposal.net_ev = ev_breakdown["ev"]      # FloatField — for quick sorting

  The proposal.ev_breakdown dict will contain:
    ev, savings, interruption_cost, migration_penalty,
    capacity_failure_risk, volatility_cost, is_eligible

  This stored ev_breakdown travels with the proposal through the entire
  pipeline — coordinator evaluation, operator approval UI, audit log.

Why: Currently rightsizing proposals are created with a simple EV estimate.
The optimizer coordinator then independently re-computes EV to decide whether
to approve the proposal, using yet another formula. Storing the economic EV
breakdown at proposal creation time means the coordinator reads the same
number that was used to generate the proposal — no recomputation divergence.

--------------------------------------------------------------------------------
TASK 3.4 — Update Optimizer Coordinator COMBINED_EVALUATION Phase
--------------------------------------------------------------------------------
File: backend/services/optimizer_coordinator.py
Function: The method that handles the COMBINED_EVALUATION → EXECUTION or
          COMBINED_EVALUATION → STABILIZATION transition. Search for
          compute_combined_expected_value to find the right location.

Instruction:
  Replace the call to compute_combined_expected_value() with logic that
  reads the stored ev_breakdown from the proposal:

  # Load the proposal from DB
  proposal = RightsizingProposal.objects.get(id=proposal_id)

  if proposal.ev_breakdown is not None:
      # New path: use economic EV stored at proposal creation time
      pool_ev = proposal.ev_breakdown.get("ev", 0.0)
      rightsizing_ev = proposal.net_ev or 0.0
  else:
      # Fallback for proposals created before the EV migration
      # Use old compute_combined_expected_value() so nothing breaks
      result = compute_combined_expected_value(...)
      pool_ev = result.option_a_ev
      rightsizing_ev = result.option_b_ev

  baseline_ev = 0.0  # Option C: do nothing

  # Decision threshold: 10% improvement over baseline (unchanged)
  best_ev = max(pool_ev, rightsizing_ev)
  if best_ev > 0 and (best_ev - baseline_ev) / max(abs(baseline_ev), 1) >= 0.10:
      self.transition_to(EXECUTION)
  else:
      self.transition_to(STABILIZATION)

  Also add to the GET /api/v1/optimizer/ev-comparison/{proposal_id} endpoint:
  Instead of computing EV in the route, load proposal.ev_breakdown and
  return it directly. The three options should be:
    Option A: Pool optimization EV from proposal.ev_breakdown
    Option B: Rightsizing EV from proposal.net_ev
    Option C: Baseline EV = 0.0
  Include all breakdown fields (interruption_cost, migration_penalty, etc.)
  so the frontend can display the full decomposition.

Why: The current COMBINED_EVALUATION uses compute_combined_expected_value()
which is the simplified 3-option model (savings × (1 - risk) with
volatility_penalty). This produces a different number than evaluate_candidate_ev().
Operators looking at the EV Comparison Panel in the UI were approving or
rejecting proposals based on a number that did not match what the backend
used to generate the proposal. This fix ensures the number the operator sees
is the number that drove the decision.

The fallback for null ev_breakdown is critical — at deploy time there will be
in-flight proposals in PENDING state that were created before this migration.
Without the fallback, the coordinator crashes when it encounters them.

================================================================================
PART 4 — DETERMINISTIC STATE MANAGEMENT
================================================================================

--------------------------------------------------------------------------------
TASK 4.1 — Add Stabilization Lock to Cooldown Controller
--------------------------------------------------------------------------------
File: backend/services/cooldown_controller.py

Instruction:
  Add two new methods to CooldownController (or as standalone functions if
  the controller is not a class):

  STABILIZATION_TTL_SECONDS = 900  # 15 minutes

  def set_stabilization_lock(self, cluster_id):
      """
      Set a stabilization lock after any significant cluster action.
      Prevents any new optimization decision for 15 minutes.
      Different from cooldown: cooldown prevents re-triggering the SAME action.
      Stabilization prevents ANY action during the turbulent post-change window.
      """
      redis.setex(
          f"spot:stabilization_lock:{cluster_id}",
          STABILIZATION_TTL_SECONDS,
          "1"
      )

  def is_stabilizing(self, cluster_id):
      return bool(redis.exists(f"spot:stabilization_lock:{cluster_id}"))

  Then add the stabilization check to control_plane_loop.py immediately after
  the hibernation check (Task 1.1):

  if cooldown_controller.is_stabilizing(cluster_id):
      logger.info(f"Cluster {cluster_id} is stabilizing — skipping cycle")
      return {"status": "SKIPPED", "reason": "STABILIZING"}

  Then add set_stabilization_lock() calls in each of these locations:

  In substitute_manager.py — after the PROMOTING state transition completes
  and substitute becomes the primary node. Call:
    cooldown_controller.set_stabilization_lock(cluster_id)

  In karpenter_service.py — after circuit breaker auto-recovery (when the
  breaker transitions from OPEN back to CLOSED). Call:
    cooldown_controller.set_stabilization_lock(cluster_id)

  In pool_rotation_service.py — after rotation completes and new AZ is
  recorded as primary. Call:
    cooldown_controller.set_stabilization_lock(cluster_id)

  In action_executor.py — after on-demand fallback is activated (when
  switch_to_ondemand() succeeds). Call:
    cooldown_controller.set_stabilization_lock(cluster_id)

Why: Cooldowns prevent re-triggering the same action type. They do not
prevent a different action from running immediately after a turbulent event.
A substitute promotion followed within seconds by a pool rotation, or a
circuit breaker recovery immediately followed by a full optimization cycle,
are real conflict scenarios at 100+ clusters running 5-minute cycles.
Stabilization lock is the gap-filler — it freezes ALL decisions for 15
minutes after any significant state change, giving the cluster time to settle.

--------------------------------------------------------------------------------
TASK 4.2 — Persist Cluster State Machine to Redis
--------------------------------------------------------------------------------
File: backend/core/risk_engine.py
Function: get_cluster_instability_boost(cluster_id) — or wherever the
          CONSERVATIVE/HALT mode time-decay is computed

Instruction:
  Replace the in-memory or ephemeral state lookup with a Redis hash read.
  The full replacement:

  def get_cluster_instability_boost(cluster_id, redis_client):
      import math, time

      state_key = f"spot:cluster_state:{cluster_id}"
      state = redis_client.hgetall(state_key)

      if not state:
          # First time this cluster has been seen — initialize
          redis_client.hset(state_key, mapping={
              "state": "NORMAL",
              "entered_at": str(time.time()),
              "rollback_count": "0",
              "instability_score": "0.0",
              "last_transition_reason": "initialized",
          })
          return 0.0

      current_state = state.get(b"state", b"NORMAL").decode()

      if current_state == "CONSERVATIVE":
          entered_at = float(state.get(b"entered_at", b"0").decode())
          t = time.time() - entered_at
          tau = 7200  # 120 minutes in seconds
          return 1.3 * math.exp(-t / tau)

      elif current_state == "HALT":
          return 1.0

      else:  # NORMAL
          return 0.0

  Also update all state transition points (wherever the cluster transitions
  between NORMAL, CONSERVATIVE, and HALT) to write the new state to Redis:

  def transition_cluster_state(cluster_id, new_state, reason, redis_client):
      import time
      state_key = f"spot:cluster_state:{cluster_id}"
      redis_client.hset(state_key, mapping={
          "state": new_state,
          "entered_at": str(time.time()),
          "last_transition_reason": reason,
      })
      # Increment rollback_count if transitioning to CONSERVATIVE or HALT
      if new_state in ("CONSERVATIVE", "HALT"):
          redis_client.hincrby(state_key, "rollback_count", 1)

  Do NOT set a TTL on this key. It must be permanent for the cluster's
  lifetime. Delete the key only when the cluster is deleted.

Why: The instability boost formula for CONSERVATIVE mode is:
  boost = 1.3 × exp(-t / τ)  where τ = 120 min
This requires knowing when the CONSERVATIVE state was entered (entered_at).
If this is stored in-memory on a Celery worker, any worker restart — whether
due to deployment, crash, or autoscaling — resets t to zero. The decay
formula then starts over from the full 1.3 boost instead of continuing from
where it left off. This makes risk assessment non-deterministic across
restarts. With persistent Redis state, the decay is always computed from the
real entered_at timestamp regardless of which worker processes the cluster.

--------------------------------------------------------------------------------
TASK 4.3 — Add Ranking Version Optimistic Lock
--------------------------------------------------------------------------------
New Redis Key: spot:rankings_version:{region}
Type: String (integer counter)
TTL: None (permanent counter — never expires)

Instruction — Part A: Increment on every cache invalidation
  Add the following helper to a shared utility or directly to each file:

  def increment_rankings_version(redis_client, region):
      key = f"spot:rankings_version:{region}"
      if not redis_client.exists(key):
          redis_client.set(key, "1")
      else:
          redis_client.incr(key)

  Call increment_rankings_version() at these four locations:

  In blacklist_service.py — inside update_global_cache_on_blacklist(),
  after the cache update completes. Call increment_rankings_version() for
  the affected region.

  In pool_rotation_service.py — after rotation commits and new AZ is set
  as primary. Call increment_rankings_version() for the cluster's region.

  In global_pool_cache_service.py — after manual refresh completes and
  the new cache is written. Call increment_rankings_version().

  In event_monitor.py — after a volatility regime change is written to
  Redis (when regime flips from normal to volatile or back). Call
  increment_rankings_version() for the affected region.

Instruction — Part B: Read and re-check in control_plane_loop.py

  At the START of run_decision_cycle(), after the safety checks (hibernation
  and stabilization), read the version:

  start_version = redis.get(
      f"spot:rankings_version:{cluster.region}"
  )
  start_version = start_version.decode() if start_version else "0"

  Then, BEFORE the Step 8 execution queue finalization (before any nodes are
  actually moved or pools actually switched), re-check:

  current_version = redis.get(
      f"spot:rankings_version:{cluster.region}"
  )
  current_version = current_version.decode() if current_version else "0"

  if current_version != start_version:
      logger.warning(
          f"Rankings changed during cycle for cluster {cluster_id} "
          f"(version {start_version} → {current_version}) — aborting"
      )
      return {"status": "ABORTED", "reason": "RANKING_STALE"}

Why: The control plane loop reads global rankings at Step 1 (market signal
collection), then runs 7 more steps before reaching execution at Step 8.
With 100+ clusters on staggered 5-minute cycles, a blacklist event can fire
during those intermediate steps — the blacklisted pool is removed from the
global cache but the current cluster's cycle already has it selected. The
version stamp detects this: if the cache was invalidated between Step 1 and
Step 8, the cycle aborts cleanly and the next 5-minute cycle will start with
fresh rankings.

--------------------------------------------------------------------------------
TASK 4.4 — Add Execution Plan Hash Verification
--------------------------------------------------------------------------------
New Redis Key: spot:execution_plan:{cluster_id}
Type: String (SHA256 hash)
TTL: 3600 seconds (1 hour)

Instruction — Part A: Store hash after Step 8 in control_plane_loop.py

  After the execution plan is fully built (after Step 8, before dispatching
  any actions), compute and store a hash of the plan:

  import hashlib, json

  hashable = {
      "pools": sorted([
          f"{candidate.instance_type}:{candidate.az}"
          for candidate in plan.candidates
      ]),
      "version": start_version,
      "cluster_id": cluster_id,
  }
  plan_hash = hashlib.sha256(
      json.dumps(hashable, sort_keys=True).encode()
  ).hexdigest()

  redis.setex(f"spot:execution_plan:{cluster_id}", 3600, plan_hash)

  The sorted() call is essential. Pool ordering can differ between equivalent
  plan objects depending on dict iteration order. Sorting the pool identifiers
  before hashing ensures the same plan always produces the same hash.

Instruction — Part B: Verify hash in execution_controller.py

  In execute_pool_switch() (or the equivalent function that performs the
  actual node operations), add at the beginning:

  stored_hash = redis.get(f"spot:execution_plan:{cluster_id}")

  if stored_hash:
      hashable = {
          "pools": sorted([
              f"{c.instance_type}:{c.az}"
              for c in original_plan.candidates
          ]),
          "version": original_plan.rankings_version,
          "cluster_id": cluster_id,
      }
      expected_hash = hashlib.sha256(
          json.dumps(hashable, sort_keys=True).encode()
      ).hexdigest()

      if stored_hash.decode() != expected_hash:
          raise StalePlanError(
              f"Execution plan for cluster {cluster_id} was invalidated "
              f"between planning and execution — aborting"
          )

Why: The ranking version check (Task 4.3) guards the gap between cycle start
and Step 8. The execution plan hash guards the gap between Step 8 (plan built)
and actual execution. These are different windows. A blacklist event that fires
after Step 8 but before execution_controller.py runs would not be caught by
the version check but IS caught by the hash check. Both guards are needed
for full coverage. The hash includes the rankings version as part of its
input, so any version change automatically invalidates the hash.

================================================================================
PART 5 — THREE-LAYER RISK CEILING (ATHARVAAI — DECISION ENGINE)
================================================================================

--------------------------------------------------------------------------------
TASK 5.1 — Refactor Risk Ceiling in Decision Engine Step 6
--------------------------------------------------------------------------------
File: backend/core/decision_engine.py
Location: Step 6 of evaluate_action_plan() — the risk ceiling filter

Instruction:
  Find the current hard-reject at the profile ceiling. Replace the single
  hard-reject with the three-layer structure:

  # LAYER 1: Catastrophic ceiling — absolute hard reject regardless of profile
  # This is SEPARATE from the ML threshold (0.35) in risk_threshold.json
  # Do not modify optimal_threshold. This is a new upper bound above it.
  CATASTROPHIC_RISK_CEILING = 0.85

  if final_risk >= CATASTROPHIC_RISK_CEILING:
      increment_rejection_counter(cluster_id, "catastrophic_risk")
      continue  # skip to next candidate

  # LAYER 2: Profile ceiling — apply savings penalty instead of hard rejection
  # Profiles: COST_FIRST=0.25, BALANCED=0.20, NO_DOWNTIME_FIRST=0.10
  if final_risk > profile.risk_ceiling:
      # Penalty scales from 0 (at ceiling) to 1 (at catastrophic ceiling)
      penalty = (final_risk - profile.risk_ceiling) / (
          CATASTROPHIC_RISK_CEILING - profile.risk_ceiling
      )
      savings = savings * (1 - penalty)
      # Candidate stays in the pipeline with reduced savings
      # Economic EV (Layer 3) will reject it if savings no longer justify risk

  # LAYER 3: Economic EV gate — handled in Step 9 (Task 3.2)
  # If adjusted savings are too low, evaluate_candidate_ev() returns
  # is_eligible=False and the candidate is rejected there

  Note: The ML model's optimal_threshold (0.35) in risk_threshold.json is
  unchanged. That is the SageMaker-tuned pool ranking filter in
  pool_ranking_service.py Step 7. The 0.85 catastrophic ceiling here is in
  the decision engine and operates on final_risk (the composite Bayesian risk
  after all adjustments), not on ML probability scores. They are independent.

Why: The current structure hard-rejects any pool whose final_risk exceeds
the profile ceiling (0.10, 0.20, or 0.25 depending on mode). This is too
blunt for new regions where baseline ML risk scores are legitimately higher
due to less historical data. It forces unnecessary on-demand fallbacks even
when a pool has high savings that would economically justify moderate risk.
The three-layer model allows the economic model to approve justified
high-risk pools while still blocking catastrophic-risk pools unconditionally.

================================================================================
PART 6 — FINANCIAL GUARDRAILS
================================================================================

--------------------------------------------------------------------------------
TASK 6.1 — Add Org-Level Spend Velocity Guard
--------------------------------------------------------------------------------
New Redis Key: spot:config:org_velocity_threshold
Type: String (float, default "20.0" representing 20% above 24h rolling average)

New Redis Key: spot:org_spend_state:{org_id}
Type: Hash with fields: current_hourly, rolling_avg_24h, last_updated

Instruction:
  In backend/services/billing_service.py, add:

  def get_org_spend_velocity(org_id, redis_client):
      state = redis_client.hgetall(f"spot:org_spend_state:{org_id}")
      if not state:
          return {"current_hourly": 0.0, "rolling_avg_24h": 0.0, "blocked": False}

      current = float(state.get(b"current_hourly", b"0").decode())
      avg_24h = float(state.get(b"rolling_avg_24h", b"0").decode())

      if avg_24h == 0:
          return {"current_hourly": current, "rolling_avg_24h": 0, "blocked": False}

      velocity_pct = ((current / avg_24h) - 1) * 100
      threshold = float(redis_client.get("spot:config:org_velocity_threshold") or 20)
      return {
          "current_hourly": current,
          "rolling_avg_24h": avg_24h,
          "velocity_pct": velocity_pct,
          "blocked": velocity_pct > threshold,
      }

  In action_executor.py, add a check before execution of upward resizes
  and on-demand fallback activations:

  spend = billing_service.get_org_spend_velocity(org_id, redis_client)
  if spend["blocked"]:
      action_types_blocked = ("UPSIZE", "ONDEMAND_FALLBACK", "SCALE_UP")
      if action.action_type in action_types_blocked:
          logger.warning(
              f"Org {org_id} spend velocity blocked — skipping {action.action_type}"
          )
          return {"status": "BLOCKED", "reason": "SPEND_VELOCITY"}
      # Risk-reduction actions (DOWNSIZE, POOL_SWITCH to cheaper pool) pass through
      # Substitute promotions for already-interrupted nodes pass through

  Store the threshold in Redis (not hardcoded) so it can be tuned without
  a deploy:
  redis.set("spot:config:org_velocity_threshold", "20.0")
  Use this as the initial value. Adjust after observing real traffic patterns.

Why: Individual cluster guards miss org-level risk. If 30 clusters each pass
their individual spend guards and simultaneously trigger on-demand fallback
(which costs significantly more than spot), the org's hourly bill spikes
by the combined cost increase of all 30 clusters. No individual guard would
have caught this. The org-level velocity guard compares current hourly spend
to the 24-hour rolling average and blocks further cost-increasing actions if
the acceleration exceeds the threshold. Downsizes and risk-reduction pool
switches are always allowed — only actions that increase cost are blocked.

================================================================================
PART 7 — ATHARVAAI SECTION — COMPLETE WORKING STATE
================================================================================

This section covers every backend and frontend change needed to make the
AtharvaAI section fully operational with all settings working.

--------------------------------------------------------------------------------
TASK 7.1 — Add Decision Rejection Counters to Decision Engine
--------------------------------------------------------------------------------
File: backend/core/decision_engine.py

Instruction:
  Add a helper function that increments a per-cluster, per-reason Redis counter
  whenever a pool or decision is rejected. Call it at every rejection point
  in the 15-step pipeline:

  def increment_rejection_counter(cluster_id, reason, redis_client):
      key = f"spot:rejection_counter:{cluster_id}:{reason}"
      redis_client.incr(key)
      redis_client.expire(key, 86400)  # 24-hour window

  Call increment_rejection_counter() at each of these rejection points:
    Step 1:  reason = "cluster_cooldown"
    Step 1b: reason = "pricing_stale"
    Step 2:  reason = "all_pools_on_cooldown"
    Step 2b: reason = "no_node_classification"
    Step 2c: reason = "no_stateless_eligible_nodes"
    Step 5:  reason = "no_global_rankings"
    Step 6:  reason = "catastrophic_risk" (new from Task 5.1)
    Step 6:  reason = "all_exceed_risk_ceiling" (existing check)
    Step 11: reason = "template_filter_reject"
    Step 12: reason = "diversity_deadlock" or "diversity_unsafe"
    Step 13: reason = "below_delta_threshold"
    EV gate: reason = "ev_not_eligible"

  Add a backend route to expose these counters:

  File: backend/routes/atharvaai_routes.py (or metrics_routes.py)

  @router.get("/metrics/rejections/{cluster_id}")
  async def get_rejection_counters(cluster_id: str):
      pattern = f"spot:rejection_counter:{cluster_id}:*"
      keys = redis.keys(pattern)
      result = {}
      for key in keys:
          reason = key.decode().split(":")[-1]
          result[reason] = int(redis.get(key) or 0)
      return result

Why: Currently when the decision engine skips a cluster, nothing is recorded
about why. Operators see the optimizer "not doing anything" with no explanation.
These counters let operators see that the system is correctly enforcing
cluster_cooldown 47 times, diversity_deadlock 3 times, etc. — the system
working correctly looks different from the system being broken.

--------------------------------------------------------------------------------
TASK 7.2 — Add Unified Cluster Summary Endpoint
--------------------------------------------------------------------------------
File: backend/routes/cluster_routes.py (or a new control_plane_routes.py)

New Endpoint: GET /api/v1/control-plane/cluster-summary/{cluster_id}

Instruction:
  Implement this endpoint using a single Redis pipeline call (one round-trip):

  @router.get("/control-plane/cluster-summary/{cluster_id}")
  async def get_cluster_summary(cluster_id: str, current_user=Depends(auth)):
      cluster = await get_cluster(cluster_id)
      region = cluster.region
      org_id = cluster.org_id

      pipe = redis.pipeline()
      pipe.hgetall(f"spot:cluster_state:{cluster_id}")          # state machine
      pipe.ttl(f"spot:cooldown:cluster:{cluster_id}")           # cooldown remaining
      pipe.get(f"spot:execution_failures:{cluster_id}")         # circuit breaker count
      pipe.get(f"spot:substitute:state:{cluster_id}")           # substitute state
      pipe.get(f"spot:volatility_regime:{region}")              # volatility flag
      pipe.get(f"spot:rankings_version:{region}")               # ranking version
      pipe.ttl(f"spot:stabilization_lock:{cluster_id}")         # stabilization remaining
      pipe.get(f"spot:dryrun_count:{region}")                   # DryRun budget used
      pipe.hgetall(f"spot:org_spend_state:{org_id}")            # org spend velocity
      results = pipe.execute()

      state_data, cooldown_ttl, cb_failures, sub_state, \
      vol_regime, rank_version, stab_ttl, dryrun_count, \
      org_spend = results

      return {
          "cluster_id": cluster_id,
          "cluster_state": state_data.get(b"state", b"NORMAL").decode()
              if state_data else "NORMAL",
          "entered_state_at": float(state_data.get(b"entered_at", b"0"))
              if state_data else None,
          "cooldown_active": cooldown_ttl > 0,
          "cooldown_seconds_remaining": max(cooldown_ttl, 0),
          "stabilization_active": stab_ttl > 0,
          "stabilization_seconds_remaining": max(stab_ttl, 0),
          "circuit_breaker_failures": int(cb_failures or 0),
          "substitute_state": sub_state.decode() if sub_state else "IDLE",
          "volatility_regime": vol_regime.decode() if vol_regime else "normal",
          "rankings_version": rank_version.decode() if rank_version else "0",
          "dryrun_budget_used": int(dryrun_count or 0),
          "org_spend_velocity_blocked":
              get_org_spend_velocity(org_id, redis).get("blocked", False),
      }

Why: Currently the frontend assembles cluster state from 7+ separate async
endpoint calls made in parallel from the browser. Each call hits a different
Redis key at a slightly different timestamp. This produces impossible state
combinations — the circuit breaker shows OPEN while cooldown shows READY,
because they were read 300ms apart during a state transition. One atomic
Redis pipeline reads all keys at the same logical instant.

--------------------------------------------------------------------------------
TASK 7.3 — Wire Pool Rotation Status to Frontend
--------------------------------------------------------------------------------
Backend file: backend/routes/pool_rotation_routes.py
Route: GET /api/v1/pool-rotation/status/{cluster_id}  (route already exists)

Frontend file: atharvaai/DecisionEngineV3Dashboard.jsx

Instruction:
  The backend route exists but the frontend never calls it. Add a fetch of
  this endpoint in DecisionEngineV3Dashboard.jsx alongside the other data
  fetches. Display the result in the Effective Configuration Panel as a new
  "Pool Rotation" status row, showing:
    - Current primary AZ
    - Last rotation timestamp
    - Rotation trigger reason (if available)
    - Next eligible rotation time (if in rotation cooldown)

  Also wire: POST /api/v1/pool-rotation/force/{cluster_id}
  Add a "Force Rotation" button visible only to SUPER_ADMIN role users
  in the Decision Engine V3 panel, protected by the PermissionGate component.

--------------------------------------------------------------------------------
TASK 7.4 — Wire AtharvaAI Health Endpoint to Dashboard
--------------------------------------------------------------------------------
Backend route: GET /api/v1/atharvaai/health  (route exists, not called by frontend)

Frontend file: atharvaai/DecisionEngineV3Dashboard.jsx or
               atharvaai/GlobalIntelligencePanel.jsx

Instruction:
  Add a health status indicator to the AtharvaAI Dashboard sub-tab that
  displays the result of GET /api/v1/atharvaai/health. Show:
    - ML model status (active / degraded / fallback_scoring mode)
    - atharvaai:ml_fail_count from the circuit breaker
    - atharvaai:ml_degraded flag status
    - ONNX model version currently loaded (classifier_6 / regressor_6)

  Use the existing shared Badge component with:
    green = ML active and healthy
    yellow = degraded, using fallback scoring
    red = circuit breaker open (>5 failures in 10 min window)

--------------------------------------------------------------------------------
TASK 7.5 — Fix Volatility Banner in MainLayout
--------------------------------------------------------------------------------
File: layout/MainLayout.jsx
Current state: Volatility banner logic is inline — an API call to
  GET /api/v1/atharvaai/volatility/{id} is made directly inside the layout
  component, which means it re-executes on every route change.

Existing file: atharvaai/VolatilityMonitor.jsx (already exists, not used here)

Instruction:
  Remove the inline volatility API call and banner rendering from
  MainLayout.jsx entirely.

  Import VolatilityMonitor from atharvaai/VolatilityMonitor.jsx and render
  it as a standalone component at the top of the content area in MainLayout,
  outside the sidebar and outside the route-switching logic:

  // In MainLayout.jsx — replace inline logic with:
  import VolatilityMonitor from '../atharvaai/VolatilityMonitor';

  // In the JSX, at the top of the content wrapper:
  <div className="content-wrapper">
    <VolatilityMonitor />  {/* Self-contained — manages own fetch and state */}
    {children}
  </div>

  VolatilityMonitor should manage its own polling interval (match the existing
  2-hour TTL on the volatility_regime Redis key — poll every 10 minutes is
  sufficient, not on every route change).

Why: MainLayout.jsx is the root shell wrapper. Every route change triggers
a re-render of MainLayout. If the volatility endpoint is slow, returns a 500,
or times out, the entire shell render is delayed. The notification bell,
sidebar, and content area all wait. Moving the banner to a standalone
component means a slow volatility endpoint only delays the banner — the rest
of the UI renders immediately.

--------------------------------------------------------------------------------
TASK 7.6 — Wire Rejection Counters to Decision Engine Dashboard
--------------------------------------------------------------------------------
File: atharvaai/DecisionEngineV3Dashboard.jsx

Instruction:
  Add a new "Rejection Breakdown" panel to the Decision Engine V3 dashboard
  that fetches GET /api/v1/metrics/rejections/{cluster_id} and displays the
  results as a list of reason → count pairs. Refresh this data every 30
  seconds alongside the existing auto-refresh.

  Display format:
    cluster_cooldown:       47  (show as gray — system working correctly)
    pricing_stale:           3  (show as yellow — potential issue)
    no_stateless_eligible:  12  (show as gray — workload is stateful)
    ev_not_eligible:         8  (show as blue — economic model filtering)
    catastrophic_risk:       0  (show as green when zero, red when > 0)
    template_filter_reject:  2  (show as gray — template constraints working)
    diversity_deadlock:      1  (show as yellow — may indicate pool shortage)

  Add a 24h reset indicator showing when counters will be cleared.

--------------------------------------------------------------------------------
TASK 7.7 — Add Decision Engine Rejection Counters to Unified Summary
--------------------------------------------------------------------------------
File: backend/routes/cluster_routes.py
(The cluster summary endpoint from Task 7.2)

Instruction:
  After the pipeline execute() call, add a second Redis call to fetch
  rejection counters and include them in the summary response:

  rejection_pattern = f"spot:rejection_counter:{cluster_id}:*"
  rejection_keys = redis.keys(rejection_pattern)
  rejections = {}
  if rejection_keys:
      values = redis.mget(rejection_keys)
      for key, val in zip(rejection_keys, values):
          reason = key.decode().split(":")[-1]
          rejections[reason] = int(val or 0)

  Add "rejection_counts_24h": rejections to the response dict.

================================================================================
PART 8 — RIGHT-SIZING SECTION — COMPLETE WORKING STATE
================================================================================

--------------------------------------------------------------------------------
TASK 8.1 — Update RightsizingProposal Schema for API Response
--------------------------------------------------------------------------------
File: backend/schemas/rightsizing.py (or wherever RightsizingProposal
      response schema is defined)

Instruction:
  Add ev_breakdown and net_ev to the response schema:

  from typing import Optional
  from pydantic import BaseModel

  class EVBreakdown(BaseModel):
      ev: float
      savings: float
      interruption_cost: float
      migration_penalty: float
      capacity_failure_risk: float
      volatility_cost: float
      effective_exposure_hours: float
      is_eligible: bool

  class RightsizingProposalResponse(BaseModel):
      # ... existing fields ...
      ev_breakdown: Optional[EVBreakdown] = None
      net_ev: Optional[float] = None

  Ensure the GET /api/v1/optimizer/proposals/{cluster_id} endpoint serializes
  ev_breakdown from the DB JSONField into this schema for each proposal.

--------------------------------------------------------------------------------
TASK 8.2 — Remove Client-Side EV Computation from RightSizingDashboard
--------------------------------------------------------------------------------
File: frontend/src/RightSizingDashboard.jsx (or the path to this file)
Location: The EV Delta & Risk Columns area (around line 146 per component map)

Instruction:
  Find the line that computes EV client-side. It will look like:
    const ev = savings * (1 - risk);
  or:
    EV = recommendation.savings * (1 - recommendation.risk)

  Remove this computation entirely.

  Replace the EV column rendering with:

  {recommendation.ev_breakdown ? (
    <td>
      <span title={
        `Savings: $${recommendation.ev_breakdown.savings.toFixed(2)}/hr\n` +
        `Interruption cost: $${recommendation.ev_breakdown.interruption_cost.toFixed(2)}/hr\n` +
        `Migration penalty: $${recommendation.ev_breakdown.migration_penalty.toFixed(2)}\n` +
        `Volatility cost: $${recommendation.ev_breakdown.volatility_cost.toFixed(2)}/hr`
      }>
        ${recommendation.ev_breakdown.ev.toFixed(2)}/hr
      </span>
    </td>
  ) : (
    <td><span className="text-gray-400">—</span></td>
  )}

  The tooltip shows the breakdown components on hover. The dash fallback
  handles pre-migration proposals that don't have ev_breakdown yet.

  Also update the Risk column to use recommendation.ev_breakdown.is_eligible
  as a quality indicator alongside the risk percentage.

Why: Operators looking at the EV column in RightSizingDashboard were seeing
a number computed in their browser using savings × (1 - risk). The backend
uses a more complex formula that includes interruption cost, migration penalty,
capacity failure risk, and volatility cost. The displayed number was different
from the number that drove the backend decision. After this change, the
displayed number IS the number that drove the decision.

--------------------------------------------------------------------------------
TASK 8.3 — Update EV Comparison Panel in OptimizerCoordinator Dashboard
--------------------------------------------------------------------------------
File: frontend/src/optimizer/OptimizerCoordinatorDashboard.jsx
Location: EV Comparison Panel section (around line 533 per component map)

Instruction:
  The EV Comparison Panel currently calls:
    GET /api/v1/optimizer/ev-comparison/{proposal_id}
  and the backend computes compute_combined_expected_value() to respond.

  The backend for this endpoint was updated in Task 3.4 to return stored
  ev_breakdown data instead of computing it live. On the frontend:

  Update the EV Comparison Panel to display the full breakdown fields
  returned by the updated endpoint. For each of the three options:
    Option A (Pool optimization): Show ev, savings, interruption_cost,
      migration_penalty, volatility_cost from the response
    Option B (Rightsizing): Show the same fields for the resize option
    Option C (Baseline): Show ev = 0.0, all costs = 0.0

  Add a tooltip or expandable row for each option that shows the component
  breakdown so operators can understand WHY Option A has a higher EV than
  Option B (e.g. lower migration_penalty, lower interruption_cost).

  Remove any local EV computation in the component. The panel must render
  only what the backend returns.

--------------------------------------------------------------------------------
TASK 8.4 — Wire Manual Fallback Trigger to Cluster UI
--------------------------------------------------------------------------------
Backend route: POST /api/v1/clusters/{id}/fallback  (exists, not wired to UI)

Frontend file: clusters/ClusterDetails.jsx

Instruction:
  Add a "Manual Fallback" button to the Decision Engine State Panel in
  ClusterDetails.jsx. This button should:
    - Only be visible when circuit_breaker is OPEN or substitute_state is
      PREWARMING or READY
    - Be protected by the PermissionGate component (require 'manage_clusters'
      permission or equivalent RBAC permission)
    - On click: show a confirmation modal explaining that this will switch
      the cluster to on-demand instances for 12 hours
    - On confirm: call POST /api/v1/clusters/{id}/fallback
    - On success: show a toast notification and refresh the cluster summary

  The on-demand fallback TTL is 12 hours (FALLBACK_TTL_SECONDS = 43200 in
  karpenter_service.py). Include this information in the confirmation modal.

--------------------------------------------------------------------------------
TASK 8.5 — Wire Right-Sizing Feature Card on Dashboard
--------------------------------------------------------------------------------
File: pages/Dashboard.jsx (or wherever the Cost Intelligence tab is rendered)
Location: The Right-Sizing Feature Card in the Cost Intelligence tab

Instruction:
  The Right-Sizing feature card in the Cost Intelligence tab currently shows
  hardcoded zeros or empty state for its KPI stats.

  Add a data fetch to GET /api/v1/karpenter/recommendations and use the
  response to populate:
    - Recommendations count (total active recommendations)
    - Top savings estimate (highest single recommendation savings)
    - Clusters with recommendations (count of unique cluster_ids)
    - Last recommendation time

  The card already has the navigation button ("View Right-Sizing →") — ensure
  it routes to /right-sizing correctly.

--------------------------------------------------------------------------------
TASK 8.6 — Wire AtharvaAI Feature Card on Dashboard
--------------------------------------------------------------------------------
File: pages/Dashboard.jsx
Location: The AtharvaAI Feature Card in the Cost Intelligence tab

Instruction:
  Add a data fetch to GET /api/v1/atharvaai/rankings/global and use the
  response to populate:
    - Pools analyzed count
    - Top ML score in current rankings
    - Regions covered
    - Last pipeline run timestamp

  Also fetch GET /api/v1/atharvaai/health and use the ml_degraded flag to
  show a small status indicator on the card (green dot for healthy, yellow
  for degraded/fallback mode).

================================================================================
PART 9 — HIBERNATION SECTION — COMPLETE WORKING STATE
================================================================================

--------------------------------------------------------------------------------
TASK 9.1 — Fix Conflict Detection for All Schedule Types
--------------------------------------------------------------------------------
File: backend/services/hibernation_service.py
Function: check_conflicts() (or wherever overlap detection occurs)

Current state: Only checks WEEKLY vs WEEKLY schedules. DAILY and MONTHLY
schedules can overlap with WEEKLY schedules silently.

Instruction:
  Add a normalization function that converts any schedule type to a 744-slot
  monthly representation (31 days × 24 hours):

  def expand_to_744(schedule):
      """
      Normalize any schedule type to 744 slots (31 days × 24 hours).
      This allows cross-type overlap comparison.
      """
      matrix = schedule.schedule_matrix
      stype = schedule.schedule_type

      if stype == "WEEKLY":
          # 168 chars (7 × 24). Repeat to fill 744.
          # 744 / 168 = 4.43 — multiply and trim
          repeated = (matrix * 5)[:744]
          return repeated

      elif stype == "DAILY":
          # 31 chars — one per day. Expand each day to 24 hours.
          expanded = ""
          for day_char in matrix[:31]:
              expanded += day_char * 24
          return expanded[:744]

      elif stype == "MONTHLY":
          # Already 744 chars
          return matrix[:744]

      else:
          # Unknown type — treat as all awake (no conflict)
          return "0" * 744

  Replace the existing check_conflicts() body with:

  def check_conflicts(new_schedule, cluster_ids):
      existing_schedules = HibernationSchedule.objects.filter(
          clusters__id__in=cluster_ids,
          is_active=True,
      ).exclude(id=new_schedule.id)

      new_expanded = expand_to_744(new_schedule)

      for existing in existing_schedules:
          existing_expanded = expand_to_744(existing)
          overlap_hours = sum(
              1 for i in range(744)
              if new_expanded[i] == "1" and existing_expanded[i] == "1"
          )
          if overlap_hours > 0:
              raise ConflictError(
                  f"Schedule '{new_schedule.name}' ({new_schedule.schedule_type}) "
                  f"overlaps {overlap_hours} hour(s) with "
                  f"'{existing.name}' ({existing.schedule_type}) "
                  f"on clusters {list(cluster_ids)}"
              )

Why: A DAILY schedule with '1' entries on Monday, Wednesday, Friday combined
with a WEEKLY schedule that covers overnight hours on those same days would
silently trigger simultaneous hibernate and wake events — the hibernation
worker dispatches a sleep task while a wake task is also dispatched, because
they were never compared. The 744-slot normalization puts all schedule types
in the same coordinate space so overlap is a simple per-slot comparison.

--------------------------------------------------------------------------------
TASK 9.2 — Fix Wake Staleness Check to Be Strategy-Aware
--------------------------------------------------------------------------------
File: backend/workers/tasks/hibernation_worker.py
Function: execute_wake task — wherever is_wake_stale check occurs, or
          wherever hibernation_state timestamp is compared to a threshold

Instruction:
  Replace the single hardcoded 4-hour staleness threshold with a per-strategy
  threshold dict:

  WAKE_STALENESS_THRESHOLDS_MINUTES = {
      "NAMESPACE_SLEEP":    240,  # 4 hours — replicas scaled to 0, safe to wait
      "NUCLEAR":             30,  # 30 min — nodes were terminated, state is volatile
      "SNAPSHOT_RESTORE":    60,  # 60 min — cluster was stopped, needs fresh check
  }

  def is_wake_stale(cluster, strategy):
      if not cluster.hibernation_state:
          return True  # No state recorded — treat as stale, re-validate

      timestamp = cluster.hibernation_state.get("timestamp")
      if not timestamp:
          return True

      age_minutes = (time.time() - float(timestamp)) / 60
      threshold = WAKE_STALENESS_THRESHOLDS_MINUTES.get(strategy, 240)
      return age_minutes > threshold

  Replace all calls to the old staleness check with is_wake_stale(cluster, strategy).

Why: For NUCLEAR strategy, worker nodes were terminated. A 4-hour stale
threshold means the wake worker could try to restore cluster state based on
4-hour-old information about which nodes existed. After 4 hours, those node
IDs no longer exist in AWS. The restore will fail and may leave the cluster
in a partial state. 30 minutes is the right threshold for NUCLEAR — if the
wake task has been queued for more than 30 minutes, re-validate cluster state
before proceeding. For NAMESPACE_SLEEP, 4 hours is fine because no AWS
resources were terminated — only Kubernetes replica counts were modified.

--------------------------------------------------------------------------------
TASK 9.3 — Route HibernationWizard as First-Time Setup Entry Point
--------------------------------------------------------------------------------
File: hibernation/HibernationWizard.jsx (411 lines, currently orphaned)
File: HibernationDashboardNew.jsx

Instruction:
  HibernationWizard.jsx calls POST /api/v1/hibernation/setup — a real,
  existing backend endpoint. The wizard is not routed anywhere, so users
  who have never created a hibernation schedule have no guided path to do so.

  In HibernationDashboardNew.jsx, in the Schedules tab rendering:
  Check if the schedule list returned by GET /api/v1/hibernation/schedules
  is empty. If it is empty AND the user has not previously dismissed the wizard:

  {schedules.length === 0 && !wizardDismissed && (
    <HibernationWizard
      onComplete={() => {
        setWizardDismissed(true);
        fetchSchedules(); // refresh list after wizard completes
      }}
      onDismiss={() => setWizardDismissed(true)}
    />
  )}

  Store wizardDismissed in local component state (reset on page load — the
  wizard should show again if the user navigates away and back and still
  has no schedules, unless they created one).

  The wizard's 3 steps are:
    Step 1: Select clusters to hibernate
    Step 2: Choose strategy (NAMESPACE_SLEEP / NUCLEAR / SNAPSHOT_RESTORE)
    Step 3: Set schedule matrix and timezone

  Wire the wizard's final submit to call POST /api/v1/hibernation/setup
  which the backend already handles.

--------------------------------------------------------------------------------
TASK 9.4 — Wire AdvancedConfiguration Component
--------------------------------------------------------------------------------
File: hibernation/AdvancedConfiguration.jsx (currently orphaned)
File: HibernationDashboardNew.jsx

Instruction:
  AdvancedConfiguration.jsx exists but is not rendered anywhere. Add it to
  the Schedule Form (the create/edit modal in HibernationDashboardNew.jsx,
  lines 433–616) as a collapsible "Advanced Settings" section at the bottom
  of the form, above the Save button.

  The advanced configuration should expose:
    - pre_warm_minutes (number input, default 30)
    - date_overrides (key-value editor for specific date overrides)
    - Schedule type selection: WEEKLY / DAILY / MONTHLY (currently only
      WEEKLY is accessible through the UI — the schedule_type field exists
      in the backend model but has no UI control)

  Wire each field to the existing POST/PUT /api/v1/hibernation/schedules
  request body, which already accepts these fields per the backend spec.

--------------------------------------------------------------------------------
TASK 9.5 — Wire MultiTimezone Component
--------------------------------------------------------------------------------
File: hibernation/MultiTimezone.jsx (currently orphaned)
File: HibernationDashboardNew.jsx

Instruction:
  MultiTimezone.jsx exists but is not connected to any parent. The schedule
  form has a timezone field but it appears to be a basic text input or simple
  select. Replace it with the MultiTimezone component, which presumably
  provides timezone search, current-time-in-timezone preview, and DST awareness.

  Pass the currently selected timezone to MultiTimezone and handle its
  onChange to update the schedule form's timezone field.

--------------------------------------------------------------------------------
TASK 9.6 — Wire NotificationSettings Component
--------------------------------------------------------------------------------
File: hibernation/NotificationSettings.jsx
API: GET/PUT /api/v1/hibernation/notifications

Instruction:
  NotificationSettings.jsx calls real API endpoints but is not surfaced in
  the main HibernationDashboardNew.jsx UI. Add a "Notifications" section
  to either:
    a) The bottom of the Schedules tab (as a collapsible settings section), or
    b) A new "Settings" sub-tab within the Hibernation section

  The component allows users to configure:
    - Email notifications on hibernate/wake events
    - Slack webhook for hibernation alerts
    - Notify on: schedule start, schedule end, execution failure

  This is already fully implemented — it just needs to be placed in the UI.

--------------------------------------------------------------------------------
TASK 9.7 — Wire Hibernation Feature Card on Dashboard
--------------------------------------------------------------------------------
File: pages/Dashboard.jsx
Location: The Hibernation Feature Card in the Cost Intelligence tab

Instruction:
  Add a data fetch to GET /api/v1/hibernation/savings/history and use the
  response to populate:
    - Total hours slept (aggregate sleep_hours across all schedules/months)
    - Total estimated savings from hibernation
    - Active schedules count
    - Clusters on schedule count

  Wire GET /api/v1/hibernation/schedules to get active_schedules count.
  Wire GET /api/v1/hibernation/status/active to show a "Hibernating Now"
  badge on the feature card when clusters are currently being hibernated.

--------------------------------------------------------------------------------
TASK 9.8 — Display Strategy-Aware Information in Strategies Tab
--------------------------------------------------------------------------------
File: HibernationDashboardNew.jsx
Location: Strategies sub-tab (lines 393–431 and 828–864)

Current state: The strategy cards and comparison table use a hardcoded
STRATEGIES[] array with static data.

Instruction:
  The static strategy data is acceptable for the description and comparison
  table (strategy types do not change). However, add real data for each
  strategy card showing actual usage:
    - Number of clusters currently using this strategy
    - Total savings generated by this strategy in the last 30 days
    - Last execution timestamp for this strategy

  Fetch this data from GET /api/v1/hibernation/savings/history — the response
  already groups by strategy per the hibernation_service.py spec. Enrich each
  strategy card with this live data alongside the static description.

================================================================================
PART 10 — BILLING AND ADMIN ROUTES (USER-VISIBLE BREAKAGE)
================================================================================

--------------------------------------------------------------------------------
TASK 10.1 — Create Billing Backend Routes
--------------------------------------------------------------------------------
File: Create backend/routes/billing_routes.py

Instruction:
  Create this file with three routes. All routes must use real service calls —
  no hardcoded data:

  from fastapi import APIRouter, Depends
  router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

  @router.get("/status")
  async def get_billing_status(
      current_user: User = Depends(get_current_user)
  ):
      """
      Return billing plan, status, and period for the user's organization.
      Must query Organization model or Stripe — not hardcoded.
      """
      return await billing_service.get_status(current_user.org_id)

  @router.get("/costs/summary")
  async def get_costs_summary(
      current_user: User = Depends(get_current_user)
  ):
      """
      Return usage summary: cluster count, member count, scans count.
      Must query real DB counts — not hardcoded.
      """
      return await billing_service.get_cost_summary(current_user.org_id)

  @router.post("/create-portal-session")
  async def create_portal_session(
      current_user: User = Depends(get_current_user)
  ):
      """
      Create Stripe customer portal session.
      Returns: {"url": "https://billing.stripe.com/..."}
      """
      return await billing_service.create_portal_session(current_user.org_id)

  In billing_service.py, implement:
    get_status(org_id): Query Organization model for plan_type, billing_status,
      current_period_start, current_period_end. If using Stripe, call
      stripe.Subscription.retrieve with the org's subscription_id.

    get_cost_summary(org_id): Count Cluster.objects.filter(org_id=org_id),
      count OrganizationMember.objects.filter(org_id=org_id),
      count audit events for scans in current billing period.

    create_portal_session(org_id): Call stripe.billing_portal.Session.create
      with the org's stripe_customer_id. Return the session URL.

  Register billing_routes in the main app router.

  The frontend calls these in Settings.jsx lines 76 and 116:
    GET /api/v1/billing/status → BillingStatus card
    GET /api/v1/billing/costs/summary → UsageSummary card
    POST /api/v1/billing/create-portal-session → "Manage Billing" button

--------------------------------------------------------------------------------
TASK 10.2 — Create Admin Backend Routes
--------------------------------------------------------------------------------
File: Create backend/routes/admin_routes.py (if not already exists)

Instruction:
  Add the three missing endpoints. All must require SUPER_ADMIN RBAC check:

  @router.get("/admin/dashboard")
  async def get_admin_dashboard(current_user=Depends(require_super_admin)):
      """
      Return aggregate platform KPIs:
        active_clusters: count
        healthy_agents: count
        api_latency_ms: average from recent health checks
        error_rate_pct: error percentage in last hour
        total_organizations: count
        total_users: count
      """
      return await admin_service.get_dashboard_summary()

  @router.get("/admin/stats")
  async def get_admin_stats(current_user=Depends(require_super_admin)):
      """
      Return system resource stats:
        cpu_usage_pct: current CPU usage
        memory_usage_pct: current memory usage
        db_connections: current DB connection pool size
        redis_memory_mb: Redis memory usage
        celery_queue_depth: pending task count
      """
      return await admin_service.get_system_stats()

  @router.get("/admin/agent-fleet")
  async def get_agent_fleet(current_user=Depends(require_super_admin)):
      """
      Return agent fleet status:
        agents: list of {
          cluster_id, agent_version, last_heartbeat,
          status (healthy/stale/disconnected), region
        }
      """
      return await admin_service.get_agent_fleet()

  In admin_service.py, implement these methods querying real data from
  Cluster, Organization, User models and Redis system metrics.

  Register admin_routes in the main app router.

  AdminDashboard.jsx calls GET /api/v1/admin/dashboard and /admin/stats.
  AdminHealth.jsx relies on /admin/health (already exists).
  The agent-fleet endpoint feeds AdminDashboard.jsx fleet visibility.

================================================================================
PART 11 — CLEANUP (AFTER ALL ABOVE IS COMPLETE)
================================================================================

--------------------------------------------------------------------------------
TASK 11.1 — Delete Three Confirmed Duplicate Files
--------------------------------------------------------------------------------
Files to delete:
  settings/TeamManagement.jsx (48KB)
    — Superseded entirely by teams/MembersTab.jsx and teams/TeamsTab.jsx.
      Verify no imports remain before deleting.

  settings/GovernanceManager.jsx (~480 lines)
    — Overlaps with settings/GovernanceSettings.jsx which is the active file.
      Verify no imports remain before deleting.

  approvals/ActiveWindowBanner.jsx (~120 lines)
    — Duplicate of governance/ActiveJITBanner.jsx which is the active file.
      Verify no imports remain before deleting.

Instruction:
  Before deleting each file, search the entire frontend codebase for imports
  of that file. If any import is found, redirect it to the replacement file
  first, then delete.

--------------------------------------------------------------------------------
TASK 11.2 — Mark compute_expected_value as Deprecated
--------------------------------------------------------------------------------
File: backend/core/scoring.py

Instruction:
  Add a deprecation warning to compute_expected_value():

  import warnings

  def compute_expected_value(savings, risk):
      warnings.warn(
          "compute_expected_value() is deprecated. "
          "Use ev_model.evaluate_candidate_ev() for execution decisions. "
          "This function is kept only for pool ranking cache sort order.",
          DeprecationWarning,
          stacklevel=2
      )
      return savings * (1.0 - risk)

  Do NOT delete the function yet. The pool ranking Tier 1 cache (Step 7 in
  pool_ranking_service.py) legitimately uses it for sorting. It is only
  deprecated for use in execution decisions. Once all execution paths are
  confirmed migrated, delete it in a follow-up.

  Also add a comment at the top of scoring.py:
    # compute_expected_value: DEPRECATED for execution paths.
    # Kept for pool ranking sort order only (Tier 1 cache, non-gating).
    # compute_combined_expected_value: DEPRECATED.
    # Kept as fallback for pre-migration proposals in optimizer_coordinator.py.
    # Delete both after migration is confirmed complete.

--------------------------------------------------------------------------------
TASK 11.3 — Redis Key Inventory Comment Block
--------------------------------------------------------------------------------
File: Create backend/redis_keys.py (or add to an existing constants file)

Instruction:
  Add a single source-of-truth comment block listing every Redis key pattern
  used by the system, including the new keys added by this hardening effort.
  This prevents future developers from accidentally reusing key names or
  missing TTL requirements:

  """
  REDIS KEY REGISTRY — Spot Optimizer Platform
  =============================================

  EXISTING KEYS (pre-hardening):
  spot:cooldown:cluster:{id}          TTL: 60min    CooldownController
  spot:cooldown:pool:{pool_id}        TTL: 120min   CooldownController
  spot:cooldown:resize:{id}           TTL: 360min   CooldownController
  spot:cooldown:pool_switch:{id}      TTL: 30min    CooldownController
  spot:cooldown:substitute:{id}       TTL: 120min   CooldownController
  spot:node_classification:{id}       TTL: 10min    WorkloadInspector
  spot:cluster_mode:{id}              TTL: 300s     DecisionEngine
  spot:global_rankings:{region}       TTL: 65min    GlobalPoolCacheService
  spot:volatility_regime:{region}     TTL: 2h       EventMonitor
  spot:substitute:state:{id}          TTL: Variable SubstituteManager
  spot:dryrun_count:{region}          TTL: 1h       PoolRankingService
  spot:dryrun_failures_24h:{pool}     TTL: 24h      PoolRankingService
  hibernation:lock:{sched}:{cluster}  TTL: 180s     HibernationWorker
  atharvaai:ml_fail_count             TTL: 10min    PoolRankingService
  atharvaai:ml_degraded               TTL: 10min    PoolRankingService

  NEW KEYS (added by hardening):
  spot:cluster_state:{cluster_id}     TTL: NONE     risk_engine.py
  spot:rankings_version:{region}      TTL: NONE     multiple invalidators
  spot:stabilization_lock:{cluster_id} TTL: 15min   cooldown_controller.py
  spot:execution_plan:{cluster_id}    TTL: 1h       control_plane_loop.py
  spot:org_spend_state:{org_id}       TTL: 1h       billing_service.py
  spot:rejection_counter:{id}:{reason} TTL: 24h     decision_engine.py
  spot:config:org_velocity_threshold  TTL: NONE     config (manually set)
  """

================================================================================
PART 12 — INTEGRATION TESTS (DO NOT DEPLOY WITHOUT THESE)
================================================================================

These tests must pass before deploying to production. They verify the six
critical behavioral guarantees of the hardened system.

--------------------------------------------------------------------------------
TASK 12.1 — Write Integration Tests for Critical Scenarios
--------------------------------------------------------------------------------
File: Create backend/tests/test_integration_hardening.py

Write tests for the following six scenarios:

TEST 1: Blacklist mid-cycle aborts execution
  Setup: Start a decision cycle for a cluster in a test region.
  During: After Step 1 (rankings version read), fire a blacklist event that
          increments spot:rankings_version:{region}.
  Verify: The cycle returns ABORTED with reason RANKING_STALE.
          No execution actions were dispatched.

TEST 2: Worker restart preserves instability decay
  Setup: Put a cluster into CONSERVATIVE state by writing to
         spot:cluster_state:{cluster_id} with entered_at = 60 minutes ago.
  Simulate: A worker restart (clear any in-memory state).
  Call: get_cluster_instability_boost(cluster_id)
  Verify: The returned boost is approximately 1.3 × exp(-3600/7200) ≈ 0.919.
          NOT 1.3 (which would be the result if decay reset to t=0).

TEST 3: Org spend spike blocks upward resize
  Setup: Write spot:org_spend_state:{org_id} with current_hourly = 120,
         rolling_avg_24h = 100 (20% above average — at the threshold).
         Set spot:config:org_velocity_threshold to "20".
  Call: action_executor with action_type = UPSIZE for that org.
  Verify: Action returns BLOCKED with reason SPEND_VELOCITY.
  Also verify: action_type = DOWNSIZE passes through (not blocked).

TEST 4: Stale execution plan hash aborts execution
  Setup: Build a plan for a cluster and store its hash in Redis.
         Modify the plan's candidate pool list (simulate a pool being removed).
  Call: execution_controller.execute_step() with the modified plan.
  Verify: StalePlanError is raised. Execution did not proceed.

TEST 5: Stabilization lock blocks second action
  Setup: Set spot:stabilization_lock:{cluster_id} (simulate post-rotation lock).
  Call: run_decision_cycle(cluster_id)
  Verify: Returns SKIPPED with reason STABILIZING.
          No Redis reads beyond the lock check occurred.

TEST 6: Hibernation blocks entire cycle
  Setup: Set cluster.is_hibernating = True in the DB.
  Call: run_decision_cycle(cluster_id)
  Verify: Returns SKIPPED with reason HIBERNATING.
          No Redis reads, no DryRun API calls, no risk engine calls occurred.
          Verify by checking that no DryRun-related Redis keys were written.

TEST 7: EV divergence is eliminated
  Setup: Create a rightsizing proposal through create_rightsizing_proposals().
  Verify: proposal.ev_breakdown is not None.
  Call: The optimizer coordinator COMBINED_EVALUATION for this proposal.
  Verify: The EV used for the EXECUTION/STABILIZATION decision matches
          proposal.ev_breakdown["ev"] exactly (not a recomputed value).

TEST 8: Hibernation conflict detection catches cross-type overlaps
  Setup: Create a WEEKLY schedule with '1' entries overnight Monday-Friday.
  Attempt: Create a DAILY schedule with '1' on every day (all ones).
  Verify: ConflictError is raised with overlap_hours > 0.
  Also verify: Two WEEKLY schedules with no overlapping slots succeed.

================================================================================
SUMMARY OF ALL CHANGES BY FILE
================================================================================

BACKEND FILES MODIFIED:
  backend/workers/tasks/control_plane_loop.py
    — Hibernation early gate (Task 1.1)
    — Stabilization lock check (Task 4.1)
    — Rankings version read at start + recheck before Step 8 (Task 4.3)
    — Execution plan hash storage (Task 4.4)

  backend/services/pool_rotation_service.py
    — Substitute state check before rotation (Task 1.2)
    — Call set_stabilization_lock after rotation (Task 4.1)
    — Call increment_rankings_version after rotation (Task 4.3)

  backend/workers/tasks/hibernation_worker.py
    — Substitute state check before lock acquisition (Task 1.2)
    — Strategy-aware wake staleness thresholds (Task 9.2)

  backend/core/risk_engine.py
    — Persistent cluster state machine via Redis hash (Task 4.2)

  backend/core/decision_engine.py
    — Replace Step 9 simple EV with evaluate_candidate_ev() (Task 3.2)
    — Three-layer risk ceiling in Step 6 (Task 5.1)
    — Add rejection counters at every rejection point (Task 7.1)

  backend/core/ev_model.py
    — Add get_dynamic_capacity_failure_probability() helper (Task 3.1)

  backend/services/cooldown_controller.py
    — Add set_stabilization_lock() and is_stabilizing() methods (Task 4.1)

  backend/services/rightsizing_service.py
    — Inject ev_breakdown into proposals at creation time (Task 3.3)

  backend/services/optimizer_coordinator.py
    — Update COMBINED_EVALUATION to use stored ev_breakdown (Task 3.4)
    — Add fallback for pre-migration proposals (Task 3.4)

  backend/services/hibernation_service.py
    — Fix check_conflicts() to support all schedule types (Task 9.1)
    — Add expand_to_744() normalization function (Task 9.1)

  backend/services/billing_service.py
    — Implement get_status(), get_cost_summary(), create_portal_session() (Task 10.1)
    — Add get_org_spend_velocity() (Task 6.1)

  backend/core/action_executor.py
    — Add org spend velocity check before upward resizes (Task 6.1)
    — Call set_stabilization_lock after on-demand fallback (Task 4.1)

  backend/services/substitute_manager.py
    — Call set_stabilization_lock after substitute promotion (Task 4.1)

  backend/services/karpenter_service.py
    — Call set_stabilization_lock after circuit breaker recovery (Task 4.1)

  backend/services/blacklist_service.py
    — Call increment_rankings_version on cache invalidation (Task 4.3)

  backend/services/global_pool_cache_service.py
    — Call increment_rankings_version on manual refresh (Task 4.3)

  backend/services/event_monitor.py
    — Call increment_rankings_version on volatility regime change (Task 4.3)

  backend/core/scoring.py
    — Add deprecation warning to compute_expected_value() (Task 11.2)

  backend/core/execution_controller.py
    — Add execution plan hash verification (Task 4.4)

BACKEND FILES CREATED:
  backend/routes/billing_routes.py     — Three billing endpoints (Task 10.1)
  backend/routes/admin_routes.py       — Three admin endpoints (Task 10.2)
  backend/redis_keys.py                — Redis key registry comment (Task 11.3)
  backend/tests/test_integration_hardening.py — 8 integration tests (Task 12.1)

BACKEND FILES — DB MIGRATION:
  backend/models/rightsizing.py        — Add ev_breakdown, net_ev fields (Task 2.1)
  backend/schemas/rightsizing.py       — Add EVBreakdown to response schema (Task 8.1)

FRONTEND FILES MODIFIED:
  layout/MainLayout.jsx
    — Remove inline volatility API call and banner (Task 7.5)
    — Import and render VolatilityMonitor as standalone component (Task 7.5)

  RightSizingDashboard.jsx
    — Remove client-side EV computation (Task 8.2)
    — Render ev_breakdown from API response with tooltip breakdown (Task 8.2)
    — Wire Right-Sizing feature card KPIs from API (Task 8.5)

  optimizer/OptimizerCoordinatorDashboard.jsx
    — Update EV Comparison Panel to render stored ev_breakdown (Task 8.3)
    — Remove local EV computation from panel (Task 8.3)

  pages/Dashboard.jsx
    — Wire Right-Sizing feature card to real API (Task 8.5)
    — Wire AtharvaAI feature card to real API (Task 8.6)
    — Wire Hibernation feature card to real API (Task 9.7)

  atharvaai/DecisionEngineV3Dashboard.jsx
    — Add pool rotation status section (Task 7.3)
    — Add AtharvaAI health status indicator (Task 7.4)
    — Add Rejection Breakdown panel with 30s auto-refresh (Task 7.6)

  clusters/ClusterDetails.jsx
    — Add Manual Fallback button with confirmation modal (Task 8.4)

  HibernationDashboardNew.jsx
    — Route HibernationWizard for first-time setup (Task 9.3)
    — Add AdvancedConfiguration to schedule form (Task 9.4)
    — Replace timezone input with MultiTimezone component (Task 9.5)
    — Surface NotificationSettings in UI (Task 9.6)
    — Enrich strategy cards with live usage data (Task 9.8)

FRONTEND FILES WIRED UP (existed as orphans):
  hibernation/HibernationWizard.jsx    — Wired in Task 9.3
  hibernation/AdvancedConfiguration.jsx — Wired in Task 9.4
  hibernation/MultiTimezone.jsx        — Wired in Task 9.5
  hibernation/NotificationSettings.jsx — Wired in Task 9.6
  atharvaai/VolatilityMonitor.jsx      — Wired in Task 7.5

FRONTEND FILES DELETED:
  settings/TeamManagement.jsx          — Deleted in Task 11.1
  settings/GovernanceManager.jsx       — Deleted in Task 11.1
  approvals/ActiveWindowBanner.jsx     — Deleted in Task 11.1

================================================================================
EXECUTION ORDER — STRICT DEPENDENCY SEQUENCE
================================================================================

Complete in this order. Dependencies are noted in brackets.

1.  Task 1.1 — Hibernation early gate                [no dependencies]
2.  Task 1.2 — Substitute/rotation/hibernation mutex [no dependencies]
3.  Task 2.1 — Database migration (run migrate)      [no dependencies]
4.  Task 4.2 — Persistent cluster state machine      [no dependencies]
5.  Task 3.1 — Dynamic capacity failure probability  [no dependencies]
6.  Task 3.2 — Replace EV in decision engine Step 9  [depends on 3.1, 4.2]
7.  Task 3.3 — Inject EV breakdown into proposals    [depends on 2.1, 3.1]
8.  Task 3.4 — Update optimizer coordinator EV       [depends on 2.1, 3.3]
9.  Task 4.3 — Ranking version optimistic lock       [no dependencies]
10. Task 4.4 — Execution plan hash verification      [depends on 4.3]
11. Task 4.1 — Stabilization lock                    [depends on 1.1]
12. Task 5.1 — Three-layer risk ceiling              [depends on 3.2]
13. Task 6.1 — Org-level spend velocity guard        [depends on 3.2, 3.3]
14. Task 7.1 — Decision rejection counters           [depends on 3.2, 5.1]
15. Task 7.2 — Unified cluster summary endpoint      [depends on 4.1, 4.2, 4.3]
16. Task 9.1 — Hibernation conflict detection fix    [no dependencies]
17. Task 9.2 — Strategy-aware wake staleness         [no dependencies]
18. Task 10.1 — Billing backend routes               [no dependencies]
19. Task 10.2 — Admin backend routes                 [no dependencies]
20. Task 8.1 — Rightsizing schema update             [depends on 2.1, 3.3]
21. Task 7.5 — Fix Volatility Banner in MainLayout   [no dependencies]
22. Task 8.2 — Remove client-side EV in RightSizing  [depends on 8.1]
23. Task 8.3 — Update EV Comparison Panel            [depends on 3.4, 8.1]
24. Task 9.3 — Route HibernationWizard               [no dependencies]
25. Task 9.4 — Wire AdvancedConfiguration            [no dependencies]
26. Task 9.5 — Wire MultiTimezone                    [no dependencies]
27. Task 9.6 — Wire NotificationSettings             [no dependencies]
28. Task 7.3 — Wire pool rotation status             [depends on 7.2]
29. Task 7.4 — Wire AtharvaAI health endpoint        [no dependencies]
30. Task 7.6 — Wire rejection counters to UI         [depends on 7.1]
31. Task 8.4 — Manual fallback button                [no dependencies]
32. Task 8.5 — Wire RightSizing Dashboard feature card [no dependencies]
33. Task 8.6 — Wire AtharvaAI feature card           [no dependencies]
34. Task 9.7 — Wire Hibernation feature card         [no dependencies]
35. Task 9.8 — Enrich strategy cards with live data  [no dependencies]
36. Task 12.1 — Write and run integration tests      [depends on 1-19]
37. Task 11.1 — Delete duplicate files               [depends on all above]
38. Task 11.2 — Mark compute_expected_value deprecated [depends on 6, 7, 8]
39. Task 11.3 — Redis key registry                   [depends on all above]

================================================================================
END OF INSTRUCTION SET
================================================================================
Total backend files modified: 18
Total backend files created: 4
Total frontend files modified: 9
Total frontend files newly wired: 5
Total frontend files deleted: 3
Total Redis keys added: 7
Total integration tests: 8
================================================================================