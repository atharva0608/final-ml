# Comprehensive Codebase Audit Report

**Original Date:** June 2025  
**Last Verified:** 30 March 2026  
**Scope:** Full audit of all known problems (Z1–Z14, N1–N12) from `documents/problems.md`, plus additional edge cases (BUG-1 to BUG-9) discovered during codebase analysis.  
**Live Verification:** `documents/source-validation.md` — Docker container inspection + live Redis/DB queries run 2026-03-28 against `spot-optimizer-backend`.  
**Current Status:** 26 of 42 items resolved. 9 open (including 7 newly discovered). 7 not-a-bug/deferred.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Resolved Items (Verified Fixed)](#2-resolved-items-verified-fixed)
3. [Open Items (Still Unfixed)](#3-open-items-still-unfixed)
3b. [Live Environment Verification Summary](#3b-live-environment-verification-summary)
4. [Not-a-Bug / Deferred by Design](#4-not-a-bug--deferred-by-design)
5. [Dependency Chains (Resolved)](#5-dependency-chains-resolved)
6. [Full Summary Table](#6-full-summary-table)

---

## 1. Executive Summary

### Audit Methodology
- Read `documents/problems.md` (400 lines, Z1–Z14 + N1–N12)
- Verified each item against the actual codebase with exact line-number evidence
- Searched for additional unhandled edge cases across 6 primary code files
- Verified Celery beat schedule in `backend/workers/app.py`
- **Re-verified all items on 2026-03-30 against current codebase**
- **Live environment validated on 2026-03-28** via `source-validation.md` (Docker exec into `spot-optimizer-backend`)

### Current State

| Category | Total | Fixed | Open | Not-a-Bug / Deferred |
|----------|-------|-------|------|----------------------|
| Z-Items (Z1–Z14) | 14 | 11 | 0 | 3 |
| N-Items (N1–N12) | 12 | 7 | 1 | 4 |
| Original (BUG-1–9) | 9 | 8 | 1 | 0 |
| **New (BUG-10–16)** | **7** | **0** | **7** | **0** |
| **Total** | **42** | **26** | **9** | **7** |

### Open Issues: 9

| ID | Issue | Severity |
|----|-------|----------|
| BUG-10 | Agent endpoints have no authentication | CRITICAL |
| BUG-11 | Missing `Dict` import in agent/main.py — runtime crash | HIGH |
| BUG-12 | `flush_buffer()` silently drops critical messages on error | HIGH |
| BUG-13 | Spot interruption fallback handler is a no-op | MEDIUM |
| BUG-14 | Thread-unsafe `component_health` dict in heartbeat.py | MEDIUM |
| BUG-15 | `recovery_monitor` subtask failures crash umbrella task | MEDIUM |
| BUG-16 | Unvalidated user input in `/fallback` endpoint (log injection) | MEDIUM |
| N8 | `dry_run` cache key is global across clusters | MEDIUM |
| BUG-3 | Non-atomic Redis get→check→set in some locations | MEDIUM |

---

## 2. Resolved Items (Verified Fixed)

All items below have been verified against the codebase on 2026-03-30 with exact code evidence.

### Z-Items (Zombie Node Remediation)

| ID | Issue | Fix Evidence |
|----|-------|-------------|
| **Z1** | Zombie OD cleanup task not in beat schedule | `app.py:57–61` — `'zombie-od-cleanup-hourly'` entry runs `cleanup_zombie_od_instances` every 3600s |
| **Z2** | Stuck cordon recovery | `recovery_monitor.py:518–615` — `recover_stuck_cordoned_nodes` dispatches `UNCORDON_NODE` for stuck/failed cordons. Integrated into recovery_monitor umbrella (60s interval) |
| **Z3** | `force_delete_node()` no self-guard | `actuator.py:279–286` — Self-guard: checks `os.getenv('NODE_NAME')`, returns `SELF_DELETE_ATTEMPT`. All three destructive functions (cordon, drain, force_delete) now guarded |
| **Z4** | Zombie EC2 on CORDON NOT_FOUND | `auto_rebalancer.py:2955–3020` — Detects 404, terminates EC2, cleans Redis keys, marks `ZOMBIE_EC2_TERMINATED` |
| **Z5** | `cluster_pools` sync not in beat | `app.py:63–67` — `'sync-cluster-pools-every-30-mins'` entry runs `sync_cluster_pools` every 1800s. Also `srem` on launch failure at `auto_rebalancer.py:1544` |
| **Z6** | `node_active_action` stale expiry | `auto_rebalancer.py:2345–2355` — Key deleted on failure; `setex(..., 86400)` as 24h safety-net TTL |
| **Z8** | `asserted_spot` TTL | All `setex` calls use 600s (10 min) consistently |
| **Z10** | `lock:node_action` TTL | `auto_rebalancer.py:980` — `ex=1200` (20 min) |
| **Z12** | Rollback `node_joined` guard | `auto_rebalancer.py:2148–2161` — Skips rollback drain if replacement node < 180s old |
| **Z13** | Emergency lock TTL | `termination_monitor.py:154` — `ex=120` (2 min, was 600s) |
| **Z14** | Reconciliation per-instance skip | `reconciliation_worker.py:227–282` — Builds protected instance set from active actions, skips only those instances |

### N-Items (New Issues)

| ID | Issue | Fix Evidence |
|----|-------|-------------|
| **N1** | `respect_pdb_enabled` stored but never enforced | `auto_rebalancer.py:2802–2810` — Loads `respect_pdb_enabled` from `StatelessRuntimeRules`; sets `_n1_force_drain = not respect_pdb_enabled`; passes `"force": _n1_force_drain` in DRAIN_NODE payload. Also at line 5966 for stateful resize |
| **N2** | `min_savings_percent` stored but never enforced | `pool_ranking_service.py:2223–2224` — Loads from `OptimizationStrategy`; `2428–2433` — `if savings_pct < (_min_savings_setting / 100.0): continue` drops pools below threshold |
| **N3** | No agent version handshake | `agents.py:21` — `EXPECTED_AGENT_VERSION = "1.0.0"`; lines 38–47 — logs warning on mismatch during registration (non-blocking) |
| **N4** | Image tag `latest` causes agent divergence | `values.yaml:3–4` — `tag: "{{ .Chart.AppVersion }}"`, `pullPolicy: IfNotPresent` (was `latest`/`Always`) |
| **N5** | `action_heartbeat` refreshed by backend only | `actuator.py:1514–1525` — `_action_heartbeat_loop()` POSTs to `/api/v1/agents/actions/{action_id}/heartbeat` every 30s during execution. Dual-writer: backend Celery (~15s) + agent (30s) |
| **N7** | `launch_blocked` TTL (5 min) mismatches join timeout | `auto_rebalancer.py:2976–2980` — TTL now dynamic: `_block_ttl = _SPOT_WAIT_TIMEOUT_S if _SPOT_WAIT_TIMEOUT_S > 0 else 1800` (was hardcoded 300s) |
| **N9** | Unknown instance type fallback allows undersized replacement | `pool_ranking_service.py:2281–2290` — When `min_vcpu <= 0`, returns `[]` (aborts ranking). Logged as CRITICAL. Live verification (`source-validation.md` §5): `cache_builder.py` fallback confirmed as `(1, 1.0, 'amd64')` — 136-entry `_FALLBACK_SPECS` dict covers all production types; derivation heuristic handles unknown families |

### BUG Items (Additional Edge Cases)

| ID | Issue | Fix Evidence |
|----|-------|-------------|
| **BUG-1** | Action result lost on WebSocket disconnect | `websocket_client.py:354–372` — HTTP POST fallback to `/api/v1/agents/actions/{action_id}/result` when WebSocket send fails |
| **BUG-2** | Drain disconnect without coordinated rollback | `websocket_client.py:76–78` — `_current_action_id` tracking; on reconnect `flush_buffer()` sends `action_still_running` message |
| **BUG-4/N6** | WebSocket buffer drops action results (no priority) | `websocket_client.py:60–75` — Two-tier queue: `critical_queue = queue.Queue()` (unbounded, action_result/heartbeat) + `metrics_buffer = deque(maxlen=200)` (ring buffer). Critical flushed first |
| **BUG-5** | Cluster deletion does not clear Redis keys | `cluster_routes.py:246–260` — Explicit cleanup loop deletes 7 cluster-scoped Redis keys |
| **BUG-6** | `.set()` without TTL in karpenter_routes | `karpenter_routes.py:491` — All `.set()` calls now include `ex=86400` (24h TTL) |
| **BUG-7** | `max_concurrent_actions` exceeded by concurrent workers | `auto_rebalancer.py:5371–5388` — Atomic Redis INCR/DECR semaphore replaces non-atomic read-check pattern |
| **BUG-8** | State transition fails silently without retry | `auto_rebalancer.py:45–75` — `_sm_transition()` retries up to 2× with 100ms/200ms backoff; re-reads current state |
| **BUG-9** | Stale agent reset does not cancel pending actions | `health.py:111–142` — Cancels `PENDING`/`PICKED_UP` `AgentAction`s, fails `in_progress` `RebalancingAction`s with `AGENT_WENT_OFFLINE`, deletes `action_heartbeat` keys |

---

## 3. Open Items (Still Unfixed)

### N8 — `dry_run` Cache is Global Across Clusters
**Status:** 🔴 STILL OPEN  
**Severity:** MEDIUM

**Evidence (verified 2026-03-30 + live 2026-03-28):**
- `auto_rebalancer.py:1487` — `_dr_key = f"dry_run:{_lt}:{target_az}"`
- No `cluster_id` in the key — capacity check result is shared across ALL clusters in same region
- **Live confirmation** (`source-validation.md` §6): Key format observed in Redis is `dry_run:{instance_type}:{az}` (e.g. `dry_run:c6i.xlarge:ap-south-1a`). TTLs confirmed as `PASS=900s`, `FAIL=300s`. 7 live keys present: 5 `pass`, 0 `fail`.

**Impact:** One cluster's transient capacity failure blocks the pool region-wide for 5 minutes (fail TTL = 300s). Multiple clusters in the same region experience unnecessary pool starvation.

**Existing Mitigation:** Fail TTL is only 300s (5 min), so the block self-heals quickly.

**Fix Options:**
1. Add `cluster_id` to key: `dry_run:{cluster_id}:{type}:{az}` — scopes capacity failures to the originating cluster
2. Reduce fail TTL from 300s to 60s — shorter global block window

---

### BUG-3 — Non-Atomic Redis get→check→setex Race Condition
**Status:** 🟡 PARTIALLY FIXED  
**Severity:** MEDIUM

**Evidence (verified 2026-03-30):**
- **Fixed locations** using atomic NX:
  - `auto_rebalancer.py:899` — `_redis.set(_lock_key, ..., nx=True, ex=2400)` ✅
  - `auto_rebalancer.py:3757` — `_redis.set(..., nx=True, ex=...)` — BUG-3 fix comment ✅
- **Still non-atomic:**
  - `auto_rebalancer.py:3640` — `if not _redis.get(_rlf_debounce_key): _redis.setex(...)` — debounce for ranking refresh still uses get→check→set pattern

**Impact:** The remaining non-atomic pattern is for cache-rebuild debouncing, which is low-severity — worst case is two redundant cache rebuilds within a 60s window. The critical paths (locks, state transitions) have been fixed.

**Fix:** Convert line 3640 to `_redis.set(_rlf_debounce_key, '1', nx=True, ex=60)`.

---

### BUG-10 — Agent Endpoints Have No Authentication
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** CRITICAL

**Evidence (verified 2026-03-30):**
- `backend/routers/agents.py` — All 5 agent endpoints accept `authorization: Optional[str] = Header(None)` but **never validate it**
- Affected endpoints:
  - `POST /api/v1/agents/register` (line 27)
  - `POST /api/v1/agents/actions/{action_id}/heartbeat` (line 137)
  - `POST /api/v1/agents/actions/{action_id}/result` (line 152)
  - `POST /api/v1/agents/deregister` (line 183)
  - `POST /api/v1/agents/heartbeat` (line 231)
- No `Depends(verify_token)` or middleware auth check on any of these routes

**Impact:** Any unauthenticated request can register fake agents, submit spoofed action results, send false heartbeats, or deregister legitimate agents. Complete agent impersonation possible.

**Fix:** Add token validation via `Depends(verify_agent_token)` or shared-secret verification on all agent endpoints.

---

### BUG-11 — Missing `Dict` Import in agent/main.py (Runtime Crash)
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** HIGH

**Evidence (verified 2026-03-30):**
- `agent/main.py:16` — `from typing import Optional` (only `Optional` imported)
- `agent/main.py:90–91` — `self._restart_counts: Dict[str, int] = {}` and `self._restart_backoffs: Dict[str, float] = {}`
- `Dict` is not imported → **NameError at runtime** when `Agent.__init__()` executes
- No `from __future__ import annotations` at top of file

**Impact:** Agent crashes immediately on startup. This is a blocking bug.

**Fix:** Change line 16 to `from typing import Optional, Dict`.

---

### BUG-12 — `flush_buffer()` Silently Drops Critical Messages on Error
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** HIGH

**Evidence (verified 2026-03-30):**
- `agent/websocket_client.py:245–248`:
  ```python
  while not self.critical_queue.empty():
      try:
          msg = self.critical_queue.get_nowait()
          await self.send_message(msg)
      except Exception:
          break  # ← silently drops msg + all remaining messages
  ```
- No logging of the error
- Failed message is dequeued but never re-queued → **permanently lost**
- All subsequent critical messages in the queue are also abandoned

**Impact:** If `send_message()` fails on the first flush attempt (e.g. WebSocket not yet fully connected), ALL buffered action results and heartbeats are silently discarded. Contradicts the two-tier queue design (BUG-4 fix) which guarantees critical messages are never lost.

**Fix:** Log the exception, re-queue the failed message with `self.critical_queue.put(msg)`, then break.

---

### BUG-13 — Spot Interruption Fallback Handler is a No-Op
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** MEDIUM

**Evidence (verified 2026-03-30):**
- `agent/poller.py:170–184` — `handle_termination()` checks `hasattr(self.actuator, 'handle_spot_interruption')`
- If the method is missing, only a warning is logged: `"Actuator missing 'handle_spot_interruption' method. Implementing basic fallback."`
- **No actual fallback logic is implemented** — the method returns without cordoning or draining
- Spot interruption is silently ignored; pods have 2 min before hard termination

**Impact:** If `handle_spot_interruption` is removed or renamed during refactoring, spot termination handling degrades silently to a no-op.

**Fix:** Implement actual fallback: cordon the node and initiate drain in the `else` branch.

---

### BUG-14 — Thread-Unsafe `component_health` Dict in heartbeat.py
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** MEDIUM

**Evidence (verified 2026-03-30):**
- `agent/heartbeat.py:205` — `set_component_health()` writes to `self.component_health` from the main thread
- `agent/heartbeat.py:277` — `send_heartbeat()` reads `self.component_health` from the heartbeat thread
- `agent/heartbeat.py:309` — `collect_agent_metrics()` reads `self.component_health` from the metrics server thread
- **No threading lock** protects concurrent access

**Impact:** Dict mutation during iteration can crash the heartbeat thread with `RuntimeError: dictionary changed size during iteration`. Stale component health in metrics payloads.

**Fix:** Add `threading.Lock()` around all reads/writes to `component_health`.

---

### BUG-15 — `recovery_monitor` Subtask Failures Crash Umbrella Task
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** MEDIUM

**Evidence (verified 2026-03-30):**
- `backend/workers/tasks/recovery_monitor.py:505–513`:
  ```python
  r1 = sync_instance_states.apply()
  r2 = scan_orphans.apply()
  r3 = detect_karpenter_stalls.apply()
  r4 = recover_stuck_cordoned_nodes.apply()
  return {
      "sync": r1.result,     # ← re-raises exception if task failed
      "scan": r2.result,
      ...
  }
  ```
- Accessing `.result` on a failed `AsyncResult` re-raises the exception
- If ANY subtask fails, the entire `recovery_monitor` umbrella task fails
- Healthy subtasks' results are lost; Celery retries the full umbrella (max_retries=1)

**Impact:** A single subtask failure (e.g. `sync_instance_states` DB timeout) takes down all 4 recovery subtasks for the entire retry cycle.

**Fix:** Wrap each `.result` access in try/except, log failures, and return partial results.

---

### BUG-16 — Unvalidated User Input in `/fallback` Endpoint (Log Injection)
**Status:** 🔴 NEW — UNHANDLED  
**Severity:** MEDIUM

**Evidence (verified 2026-03-30):**
- `backend/api/cluster_routes.py:445–461` — `request_fallback_node()` accepts `payload: dict`
- User-supplied fields (`node_name`, `reason`, `instance_type`, `az`) are extracted without validation
- Fields are directly interpolated into `logger.critical()` f-string
- No length limits, no character sanitization

**Impact:** Log injection via newline characters in payload fields. Attacker can forge log entries or flood logs with arbitrarily large strings.

**Fix:** Validate and sanitize all user-supplied fields before logging. Use structured logging (JSON) or strip control characters.

---

## 3b. Live Environment Verification Summary

The following data sources were verified against a running `spot-optimizer-backend` Docker container on **2026-03-28** (see `documents/source-validation.md` for full evidence).

| Data Source | Keys / Records | Status | Notes |
|---|---|---|---|
| Spot prices | 9,657 Redis keys | ✅ PASS | `spot_price:{region}:{az}:{type}`, 600s TTL, refreshed every 5 min via scheduler |
| On-demand prices | 2,640 Redis keys | ✅ PASS | `ondemand_price:{region}:{type}`, nightly refresh from AWS Pricing API; `_estimate_od_price()` fallback active |
| Spot Advisor data | 19,353 Redis keys, 31,270 DB rows | ✅ PASS | `spot_advisor:{region}:{type}:Linux`, 90,000s TTL (25h); default fallback = 15% if missing |
| ML models | classifier_6.onnx + regressor_6.onnx | ✅ PASS | Both ~1 MB; accept exactly 45 features (`[null, 45]`); `optimal_threshold = 0.35`; circuit breaker inactive |
| Instance specs | 136 fallback entries + derivation | ✅ PASS | Final fallback is `(1, 1.0, 'amd64')` — not `(0, 0.0)` as previously noted |
| Dry-run cache | 7 live keys (5 pass, 0 fail) | ✅ PASS | Key format `dry_run:{type}:{az}` — **confirms N8 is still open** (no cluster_id) |
| Spot launch | sha256 ClientToken, `one-time` SpotOptions | ✅ PASS | ClientToken = 64 hex chars (deterministic, idempotent) |
| ASG terminate | Single atomic API call, 3 retries | ✅ PASS | `terminate_instance_in_auto_scaling_group` with `ShouldDecrementDesiredCapacity=True` |
| User-data retrieval | 3-tier cascade | ✅ PASS | Aborts with `MISSING_USERDATA` if all 3 tiers empty — no blind launches |
| ML features | 45-feature vector | ✅ PASS | Spot price lag (1h/4h/24h), temporal encodings, family stress, price pressure all computed from live data |
| Global pool rankings | 1,954 cached pools | ✅ PASS | `global_pool_rankings:{region}`, 3,900s TTL; ML circuit breaker inactive |

**Observations from live data:**
- `c5a.large:ap-south-1a` EMA rate = 0.0 (0 interruptions observed) — consistent with Action #187 completing successfully on this pool.
- All monitoring tables exist in DB: `circuit_breaker_state`, `pool_risk_scores`, `termination_events`, `global_pool_ema`.
- No degraded regions, no risky pools blacklisted at time of verification.

---

## 4. Not-a-Bug / Deferred by Design

| ID | Issue | Reason |
|----|-------|--------|
| **Z7** | Late drain after timeout | ⚪ DEFERRED — Rollback functions (uncordon, etc.) are idempotent. 45-min stale-action timeout handles this. Accepted risk. |
| **Z9** | Orphaned PICKED_UP actions | ⚪ DEFERRED — `auto_rebalancer.py:4006–4024` expires stale PENDING/PICKED_UP actions after 15 min. BUG-9 fix also cancels on agent offline. |
| **Z11** | `max_concurrent` dead config | ⚪ NOT DEAD — `auto_rebalancer.py:5323–5342` actively reads and enforces this setting. `problems.md` description was incorrect. |
| **N10** | Stale `pool_audit` key on node name reuse | ⚪ NOT A BUG — Read-only diagnostic cache, 300s TTL, not used in rebalancing decisions. |
| **N11** | `rebalance_failures` counter resets on TTL expiry | ⚪ CORRECT BEHAVIOR — 24h sliding window is intentional. Counter persists to track failure patterns, auto-resets after 24h without failures. |
| **N12** | OD prices have no TTL | ⚪ ALREADY FIXED (pre-audit) — `aws_pricing_service.py:44` — `OD_PRICING_TTL_SECONDS = 86400` (24h). |
| **N6** | WebSocket buffer no priority | ⚪ FIXED as BUG-4/N6 — Merged with BUG-4 fix (two-tier queue). |

---

## 5. Dependency Chains (Resolved)

These dependency chains from the original audit have been **fully resolved** by the implemented fixes:

### 5.1 Action Heartbeat Chain (N5 → BUG-1 → BUG-2 → BUG-9) — ✅ RESOLVED

| Link | Fix |
|------|-----|
| N5: Backend-only heartbeat → single point of failure | Agent now also writes heartbeat every 30s (dual-writer) |
| BUG-1: No acknowledgement for action results → lost on disconnect | HTTP POST fallback to `/actions/{id}/result` |
| BUG-2: No action context recovery on reconnect → abandoned drains | `_current_action_id` tracking + `action_still_running` on reconnect |
| BUG-9: Stale agent reset doesn't cancel actions → 45-min lock | Reset now cancels AgentActions + fails RebalancingActions immediately |

**Combined result:** A Celery worker restart or network partition no longer locks clusters for 45 minutes. Agent heartbeat provides redundancy; HTTP fallback ensures results are delivered; stale-agent cleanup frees the cluster within 5 minutes.

### 5.2 Buffer + Priority Chain (N6 → BUG-4) — ✅ RESOLVED

Two-tier queue: `critical_queue` (unbounded, never drops action results) + `metrics_buffer` (deque maxlen=200, drops oldest metrics). Critical queue flushed first on reconnect.

### 5.3 Instance Type Lookup Chain (N9) — ✅ RESOLVED

The `cache_builder.py` final fallback is `(1, 1.0, 'amd64')` (confirmed live in `source-validation.md` §5; earlier audit incorrectly noted `(0, 0.0)`). `rank_pools_for_node()` now **aborts** (returns `[]`) when `min_vcpu <= 0` — protecting against any future regression where the fallback reverts to zero values. 136-entry `_FALLBACK_SPECS` dict covers all production types; derivation heuristic handles unknowns.

### 5.4 TTL Mismatch Chain (N7) — ✅ RESOLVED

`launch_blocked` TTL now matches `_SPOT_WAIT_TIMEOUT_S` (dynamic, defaults to 30 min) instead of hardcoded 300s.

### 5.5 Concurrent Worker Safety (BUG-3 → BUG-7 → BUG-8) — ✅ MOSTLY RESOLVED

| Link | Status |
|------|--------|
| BUG-7: `max_concurrent` race | ✅ Atomic INCR/DECR semaphore |
| BUG-8: State transition silent failure | ✅ Retry with backoff (2× max) |
| BUG-3: Non-atomic Redis patterns | 🟡 Critical paths fixed (NX); one low-severity debounce pattern remains |

---

## 6. Full Summary Table

| ID | Issue | Status | Severity | Fix Location |
|----|-------|--------|----------|--------------|
| **Z1** | Zombie OD cleanup not in beat | ✅ FIXED | — | `app.py:57–61` |
| **Z2** | Stuck cordon recovery | ✅ FIXED | — | `recovery_monitor.py:518–615` |
| **Z3** | `force_delete_node` no self-guard | ✅ FIXED | — | `actuator.py:279–286` |
| **Z4** | CORDON NOT_FOUND → zombie EC2 | ✅ FIXED | — | `auto_rebalancer.py:2955–3020` |
| **Z5** | `cluster_pools` sync not in beat | ✅ FIXED | — | `app.py:63–67` |
| **Z6** | `node_active_action` stale | ✅ FIXED | — | `auto_rebalancer.py:2345–2355` |
| **Z7** | Late drain after timeout | ⚪ DEFERRED | LOW | Rollback idempotent |
| **Z8** | `asserted_spot` TTL | ✅ FIXED | — | All setex 600s |
| **Z9** | Orphaned PICKED_UP | ⚪ DEFERRED | LOW | 15-min expiry + BUG-9 |
| **Z10** | `lock:node_action` TTL | ✅ FIXED | — | `auto_rebalancer.py:980` |
| **Z11** | `max_concurrent` config | ⚪ NOT DEAD | — | Working correctly |
| **Z12** | Rollback `node_joined` guard | ✅ FIXED | — | `auto_rebalancer.py:2148–2161` |
| **Z13** | Emergency lock TTL | ✅ FIXED | — | `termination_monitor.py:154` |
| **Z14** | Reconciliation per-instance skip | ✅ FIXED | — | `reconciliation_worker.py:227–282` |
| **N1** | `respect_pdb_enabled` ignored | ✅ FIXED | — | `auto_rebalancer.py:2802–2810` |
| **N2** | `min_savings_percent` ignored | ✅ FIXED | — | `pool_ranking_service.py:2223,2428` |
| **N3** | No agent version check | ✅ FIXED | — | `agents.py:21–47` |
| **N4** | Image tag: `latest` | ✅ FIXED | — | `values.yaml:3–4` |
| **N5** | Heartbeat backend-only | ✅ FIXED | — | `actuator.py:1514–1525` |
| **N6** | WebSocket buffer no priority | ✅ FIXED | — | Merged with BUG-4 |
| **N7** | `launch_blocked` TTL mismatch | ✅ FIXED | — | `auto_rebalancer.py:2976–2980` |
| **N8** | `dry_run` cache global | 🔴 OPEN | MEDIUM | `auto_rebalancer.py:1487` |
| **N9** | Instance spec fallback (0,0) | ✅ FIXED | — | `pool_ranking_service.py:2281–2290` |
| **N10** | `pool_audit` stale | ⚪ NOT A BUG | — | 300s TTL, diagnostic only |
| **N11** | `rebalance_failures` reset | ⚪ CORRECT | — | 24h sliding window |
| **N12** | OD prices no TTL | ⚪ ALREADY FIXED | — | `aws_pricing_service.py:44` |
| **BUG-1** | Action result lost on disconnect | ✅ FIXED | — | `websocket_client.py:354–372` |
| **BUG-2** | Drain disconnect no rollback | ✅ FIXED | — | `websocket_client.py:76–78,218–227` |
| **BUG-3** | Non-atomic Redis race | 🟡 PARTIAL | MEDIUM | Critical paths fixed; line 3640 remains |
| **BUG-4** | Buffer overflow loses results | ✅ FIXED | — | `websocket_client.py:60–75,192–242` |
| **BUG-5** | Cluster delete no Redis cleanup | ✅ FIXED | — | `cluster_routes.py:246–260` |
| **BUG-6** | `.set()` without TTL | ✅ FIXED | — | `karpenter_routes.py:491` |
| **BUG-7** | `max_concurrent` race | ✅ FIXED | — | `auto_rebalancer.py:5371–5388` |
| **BUG-8** | State transition silent fail | ✅ FIXED | — | `auto_rebalancer.py:45–75` |
| **BUG-9** | Stale agent no action cancel | ✅ FIXED | — | `health.py:111–142` |
| **BUG-10** | Agent endpoints no auth | 🔴 NEW | CRITICAL | `agents.py:27,137,152,183,231` |
| **BUG-11** | Missing `Dict` import → crash | 🔴 NEW | HIGH | `agent/main.py:16,90–91` |
| **BUG-12** | `flush_buffer` drops critical msgs | 🔴 NEW | HIGH | `websocket_client.py:245–248` |
| **BUG-13** | Spot interrupt fallback is no-op | 🔴 NEW | MEDIUM | `agent/poller.py:170–184` |
| **BUG-14** | Thread-unsafe `component_health` | 🔴 NEW | MEDIUM | `agent/heartbeat.py:205,277,309` |
| **BUG-15** | `recovery_monitor` cascade failure | 🔴 NEW | MEDIUM | `recovery_monitor.py:505–513` |
| **BUG-16** | Log injection in `/fallback` | 🔴 NEW | MEDIUM | `cluster_routes.py:445–461` |

---

*End of audit report. Last verified against codebase: 2026-03-30.*
