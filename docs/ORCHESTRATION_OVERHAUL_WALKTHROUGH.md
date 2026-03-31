# Orchestration Overhaul — Walkthrough

## Changes Made

### Backend: `auto_rebalancer.py`

**2-Phase Provision-and-Wait** — The old 4-action-at-once queue (`PATCH_NODEPOOL → CORDON → DRAIN → TERMINATE`) is now split into 2 phases:
- **Phase 1**: Only `PATCH_KARPENTER_NODEPOOL` is queued. This tells Karpenter to provision a spot node.
- **Wait**: Action resolution polls for a running spot node (30-min timeout).
- **Phase 2**: Once spot is Ready (or timeout), `CORDON → DRAIN → TERMINATE` actions are created.

This prevents the blast-radius problem where nodes are drained before a replacement exists.

**EC2 Terminate Failure** — Previously, if EC2 terminate failed silently, the action was still marked `COMPLETED`. Now:
- If terminate fails → action status = `failed`, `error_message` set
- Logged as `CRITICAL` (not warning)

**Allocatable Check** — Before accepting a replacement type, verifies it has ≥ CPU/RAM as the current node. If replacement is smaller AND rightsizing is OFF → falls back to same-size replacement.

**10-min Strict Cooldown** — Reduced from 20 min. Since spot provisioning now happens in Phase 1 (before drain), no need for the long Karpenter wait.

---

### Backend: `karpenter_routes.py`

- GET `/karpenter/config/{cluster_id}` now returns `optimization_target` and `optimization_target_locked`
- PATCH accepts `optimization_target` ("spot" | "on_demand")
- **Synergy Lock**: When both toggles ON → forces target to "spot"
- **Consolidation Disable**: When ML rebalancing is turned ON, queues a `PATCH_KARPENTER_NODEPOOL` action to set `consolidationPolicy: WhenEmpty` (prevents Karpenter from independently consolidating)

---

### Data Model: `cluster.py` + Migration

- Added `optimization_target` column (String(20), default="spot") to `ClusterOptimizationSettings`
- Migration: `20260305_add_optimization_target.py`

---

### Frontend: `ClusterList.jsx`

- Added "Optimization Target" dropdown (Spot / On-Demand) in cluster settings
- When both toggles ON → dropdown disabled, shows "Locked to Spot — Synergy Mode"

---

## Validation

| Step | Result |
|---|---|
| `docker compose build frontend backend` | ✅ Both images built |
| `docker compose up -d frontend backend celery-worker` | ✅ All containers running |
| DB migration (`ALTER TABLE ... ADD COLUMN optimization_target`) | ✅ Column added |
