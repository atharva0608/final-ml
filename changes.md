Here's the complete unified implementation plan combining everything.

---

## Pre-Implementation Audit (Do Before Writing Any Code)

```
Check these specific things in the codebase:

1. Where is savings currently calculated?
   Search: savings_hourly, monthly_savings, savings_est
   Note: is it estimated or realized? Is it using source OD or pool OD?

2. Where is scoring happening?
   Search: final_score, pool_score, rank_pools
   Note: is it using min-max batch normalization or absolute?

3. Where is the pool cap?
   Search: [:10], [:6], top_n, max_candidates, limit=
   Note every location

4. What does category_mapping.json contain?
   Count how many families are mapped
   Identify which current-gen families are missing

5. What is the ONNX model output range?
   Run model on 20 sample pools
   Note min and max output values

6. Does ClusterBaseline model exist?
   Search: ClusterBaseline, baseline_od_price, original_od_price
   If not → needs to be created

7. Is WorkloadInspector running BEFORE ML pipeline?
   Trace the call order in auto_rebalancer.py scan loop
```

---

## Phase 1 — Data Foundation

**Must be done first. All other phases depend on this.**

---

### Task 1.1 — Fix Spot Advisor Scraper

**File:** `backend/scrapers/spot_advisor_scraper.py`

```
Changes:
  1. Download full JSON — not filtered by existing DB records
  2. Hardcode OS = Linux — never loop over OS types
  3. Per-region hash — not global blob hash
     key: spot:advisor:hash:{region}
     skip region writes only if THIS region's hash unchanged
  4. Always write timestamp regardless of hash:
     spot:advisor:last_scraped:{region} = utcnow()
  5. Fix interruption index map:
     {0: 5, 1: 10, 2: 15, 3: 20, 4: 25, missing: None}
  6. Fix KeyError default:
     Missing instance type → store None, never 5
  7. Upsert ALL records to spot_advisor_rates table

Verification:
  spot_advisor_rates row count: was ~20, should be 400+
  t4g.micro ap-south-1 rate: should be 25 (>20%) not 5
  last_scraped key exists for each region
```

---

### Task 1.2 — Fix Pricing Service

**File:** `backend/services/aws_pricing_service.py`

```
Changes:
  1. Remove hardcoded InstanceTypes filter from
     describe_spot_price_history call
  2. Use Boto3 paginator — returns thousands of records
  3. Filter by:
     ProductDescription: Linux/UNIX
     StartTime: last 2 hours
     All AZs in region
  4. Cache per pool_key:
     spot_price:{region}:{az}:{instance_type} TTL=3600s
  5. Fetch OD pricing for all types:
     od_price:{region}:{instance_type} TTL=86400s

Verification:
  Redis key count for spot_price:ap-south-1:* 
  Should be 400+ × 3 AZs = 1200+ keys
```

---

### Task 1.3 — Fix Instance Catalog

**File:** `backend/models/instance_catalog.py`

```
Changes:
  1. Call describe_instance_types with no filters
  2. Paginate response — 500+ instance types
  3. Store per type:
     vcpu, memory_mib→GB, architecture,
     supported_usage_classes (must include 'spot'),
     gpu_info, instance_storage
  4. DB upsert on instance_type key
  5. Redis cache:
     instance_spec:{instance_type} TTL=86400s
  6. Run on startup + daily Celery beat refresh

Verification:
  instance_catalog table row count: should be 400+
  m7i.large present: yes
  t4g.micro memory_gb: 1 (not 4)
```

---

### Task 1.4 — Fix Cache Builder

**File:** `backend/workers/tasks/cache_builder.py`

```
Changes:
  1. Load ALL instance types from instance_catalog table
  2. Load ALL AZs: describe_availability_zones()
  3. Cross-product every type × every AZ
  4. For each pool_key:
     spot_price = Redis spot_price:{region}:{az}:{type}
     od_price   = Redis od_price:{region}:{type}
     vcpu, memory, arch = Redis instance_spec:{type}
     interruption_rate = spot_advisor_rates table
     savings_pct = (od_price - spot_price) / od_price × 100
  5. Skip if: no spot_price OR savings_pct <= 0
  6. Store all valid pools:
     global_pool_cache:{region} TTL=3600s
  7. Log build summary:
     raw_cross_product, no_spot_price_skipped,
     negative_savings_skipped, final_pool_count

Verification:
  global_pool_cache:ap-south-1 entry count: should be 800+
  Log shows: raw=1170, final=~850
```

---

## Phase 2 — ML Pipeline Fixes

---

### Task 2.1 — Update category_mapping.json

**File:** `ml_model/model/category_mapping.json`

```
Add all missing current-gen families with tier assignment:

Tier 1 (model trained on — verify these exist):
  m5, m6i, m6g, c5, c6i, c6g, r5, r6i, r6g, t3, t3a

Tier 2 (proxy mapping — add these):
  m7i → proxy: m6i, penalty: 0.90
  m7g → proxy: m6g, penalty: 0.90
  m7a → proxy: m6a, penalty: 0.90
  c7i → proxy: c6i, penalty: 0.90
  c7g → proxy: c6g, penalty: 0.90
  c7a → proxy: c6a, penalty: 0.90
  r7i → proxy: r6i, penalty: 0.90
  r7g → proxy: r6g, penalty: 0.90
  r7a → proxy: r6a, penalty: 0.90
  m6a → proxy: m6i, penalty: 0.90
  c6a → proxy: c6i, penalty: 0.90
  r6a → proxy: r6i, penalty: 0.90
  i4i → proxy: i3,  penalty: 0.90
  i4g → proxy: i3,  penalty: 0.90

Tier 3 (size-class average — for anything else):
  All other families not in Tier 1 or 2
  penalty: 0.75

Format:
{
  "tier1": ["m5", "m6i", "m6g", "c5", "c6i", ...],
  "tier2": {
    "m7i": {"proxy": "m6i", "penalty": 0.90},
    "m7g": {"proxy": "m6g", "penalty": 0.90},
    ...
  },
  "tier3_penalty": 0.75
}

Verification:
  No pool dropped with reason unknown_category after this change
```

---

### Task 2.2 — Fix Capacity Validator

**File:** `ml_model/decision_engine/06_capacity_validator.py`

```
Changes:
  1. Load per-node resource profile from Redis:
     node_resource_profile:{node_id}
     {vcpu_requested: 1.2, memory_gb_requested: 3.2}
     
  2. If profile exists:
     headroom = cluster_config.replacement_headroom_pct (default 10)
     min_vcpu   = pod_vcpu_requested × (1 + headroom/100)
     min_memory = pod_memory_gb_requested × (1 + headroom/100)
     round up to nearest whole numbers
     
  3. If profile missing (metrics unavailable):
     fallback to node.vcpu_total, node.memory_gb_total
     log warning: "No pod request data, using node total as floor"
     
  4. Gate:
     pool.vcpu < min_vcpu   → reject: too_small_vcpu
     pool.memory < min_memory → reject: too_small_memory
     
  5. Track counts per rejection reason

Verification:
  Node at 40% utilization: min_vcpu should be ~1.1 not 2.0
  Opens smaller replacement options for underutilized nodes
```

---

### Task 2.3 — Fix Architecture Filter

**File:** `ml_model/decision_engine/08_template_filter.py`

```
Changes:
  1. Load per-node arch compatibility from Redis:
     node_arch_compat:{node_id}: {arm64: true/false}
     Computed by WorkloadInspector (Task 2.4)
     
  2. If arm64_eligible = True:
     Allow all architecture families
     Graviton pools (t4g, m6g, m7g, c6g, c7g, r6g, r7g) included
     
  3. If arm64_eligible = False:
     Drop all arm64 pools
     rejection: architecture_incompatible_arm64
     
  4. Always drop regardless of arch setting:
     GPU instances: p*, g* (unless node has GPU pods)
     Inferentia: inf*
     Trainium: trn*
     Mac: mac*
     Bare metal: *.metal

  5. Track counts per rejection reason

Verification:
  Cluster with multi-arch images: arm64 pools appear in ranking
  Cluster with amd64-only images: arm64 pools absent
```

---

### Task 2.4 — Extend WorkloadInspector

**File:** `backend/services/workload_inspector.py`

```
Add method: compute_node_resource_profile(node_id)
  1. Query Kubernetes API for all pods on node
  2. Sum CPU requests: convert millicores to cores (500m = 0.5)
  3. Sum memory requests: convert to GB (512Mi = 0.5)
  4. Cache:
     node_resource_profile:{node_id} TTL=300s
     {vcpu_requested, memory_gb_requested, pod_count, computed_at}

Add method: compute_node_arch_compatibility(node_id)
  1. Get all pods on node
  2. For each container image:
     Method A: check container registry manifest for arm64 support
     Method B: check pod nodeSelector/nodeAffinity for arch requirement
     Method C: check known amd64-only base image patterns
  3. arm64_eligible = True only if ALL containers support arm64
  4. Cache:
     node_arch_compat:{node_id} TTL=3600s
     {arm64: true/false, computed_at, reason}

Verify call order in auto_rebalancer.py:
  classification = workload_inspector.classify(node)
  if classification != STATELESS_ELIGIBLE: skip  ← MUST be first
  then → ML pipeline
```

---

### Task 2.5 — Fix ML Scoring Tiers

**File:** `backend/core/decision_engine.py`

```
Add function: get_ml_score(pool, category_mapping)

  family = extract_family(pool.instance_type)
  # m7i.large → m7i

  if family in category_mapping['tier1']:
    score = onnx_model.predict(build_features(pool))
    tier = 1
    confidence = 1.0

  elif family in category_mapping['tier2']:
    proxy = category_mapping['tier2'][family]['proxy']
    penalty = category_mapping['tier2'][family]['penalty']
    proxy_features = build_proxy_features(pool, proxy)
    score = onnx_model.predict(proxy_features)
    tier = 2
    confidence = penalty  # 0.90

  else:
    size_class = extract_size_class(pool.instance_type)
    score = get_size_class_average(size_class)
    tier = 3
    confidence = 0.75

  # Verify ONNX output range
  # If model outputs compressed range (e.g., 0.4-0.8):
  # ml_score_normalized = (score - MODEL_MIN) / (MODEL_MAX - MODEL_MIN)
  # where MODEL_MIN/MAX from empirical validation data
  
  return score × confidence, tier

Never raise exception for unknown family.
Never drop pool for being unknown.
Log tier assignment counts.
```

---

### Task 2.6 — Add AZ Interruption Estimation

**File:** `backend/services/pool_ranking_service.py`

```
Add function: estimate_az_interruption(instance_type, az, region)

  # Layer 1: AWS region rate (base)
  region_rate = get_spot_advisor_rate(region, instance_type)
  if region_rate is None: return None  → pool eliminated by Gate 4

  # Layer 2: AZ price adjustment
  az_price     = get_spot_price(region, az, instance_type)
  region_avg   = average spot price across all AZs for this type
  price_ratio  = az_price / region_avg if region_avg > 0 else 1.0
  
  az_adjustment = 0
  if price_ratio > 1.20: az_adjustment = 1    # +1 tier
  elif price_ratio > 1.10: az_adjustment = 0.5  # +0.5 tier

  # Layer 3: Own historical interruption data
  history = redis_client.get(f"interruption_history:{region}:{az}:{instance_type}")
  if history:
    own_rate = history['rate']
    event_count = history['count']
    history_weight = min(event_count / 100, 0.5)
  else:
    own_rate = region_rate
    history_weight = 0

  aws_weight = 1 - history_weight
  combined = (region_rate + az_adjustment) × aws_weight + own_rate × history_weight
  return min(combined, 25)

Add function: record_interruption_event(region, az, instance_type)
  Called by termination_monitor on each spot interruption
  Updates exponential moving average in Redis
  key: interruption_history:{region}:{az}:{instance_type} TTL=7days
```

---

### Task 2.7 — Add Rejection Audit Logging

**File:** `ml_model/decision_engine/pipeline.py`

```
Add rejection_reasons dict at start of filter_pools():
  {
    no_spot_price_in_az: 0,
    too_small_vcpu: 0,
    too_small_memory: 0,
    architecture_incompatible: 0,
    interruption_above_ceiling: 0,
    blacklisted: 0,
    dry_run_fail: 0,
    spot_costs_more_than_od: 0,
  }

Increment at each gate rejection.

At end of function:
  1. Log full audit at INFO level
  2. Store in Redis:
     pool_audit:{cluster_id}:{node_id} TTL=300s
     {raw_count, eligible_count, rejection_reasons, ml_tier_stats, computed_at}

Expose via API:
  GET /clusters/{id}/nodes/{node_id}/pool-audit
```

---

## Phase 3 — Scoring Formula

---

### Task 3.1 — Implement Correct Weighted Scoring

**File:** `backend/core/decision_engine.py`

```
Profile weight table:
  COST_FIRST:   {W_savings: 0.60, W_risk: 0.20, W_ml: 0.20}
  BALANCED:     {W_savings: 0.40, W_risk: 0.40, W_ml: 0.20}
  NO_DOWNTIME:  {W_savings: 0.20, W_risk: 0.60, W_ml: 0.20}

Step 1: Absolute normalization (NOT batch min/max)

  savings_score = max(0.0, min(pool.intrinsic_savings_pct / 0.70, 1.0))
  # intrinsic = (pool.od_price - pool.spot_price) / pool.od_price
  # 0.70 cap: anything above 70% intrinsic savings = max score

  safety_score = max(0.0, 1.0 - (pool.az_interruption_rate / 25.0))
  # 25 = max tier value (>20% maps to 25)
  # <5% → 0.80, 10% → 0.60, 20% → 0.20, >20% → 0.00

  ml_score = ml_raw_score × confidence_penalty
  # tier1: ×1.00, tier2: ×0.90, tier3: ×0.75
  # If ONNX output is compressed: rescale to 0-1 first

Step 2: Soft signal penalty
  soft_penalty = 0.85 if recent_failure_count(pool.pool_key) > 0 else 1.0
  # recent_failure_count = Redis key set after blacklist TTL expires
  # Resets after 24h clean operation

Step 3: Weighted sum (all positive, weights sum to 1.0)
  raw_score = (W_savings × savings_score)
            + (W_risk    × safety_score)
            + (W_ml      × ml_score)

  final_score = raw_score × soft_penalty

Step 4: Sort descending
  ranked_pools = sorted(eligible_pools, key=lambda p: p.final_score, reverse=True)

Step 5: Log score distribution per cycle
  score_stats:{cluster_id}: {min, max, mean, p25, p50, p75, p90}
  If max - min < 0.2: scoring is compressed, investigate
```

---

### Task 3.2 — Separate Savings Figures

**File:** `backend/core/decision_engine.py` + `backend/workers/tasks/savings_calculator.py`

```
Per pool, compute and store TWO savings figures:

pool.intrinsic_savings_pct:
  = (pool.od_price - pool.spot_price) / pool.od_price
  Used for: savings_score in ranking formula
  Answers: how good is this pool in the spot market?

pool.customer_savings_pct:
  = (source_od_price - pool.spot_price) / source_od_price
  Used for: UI display in Market View savings column
  Answers: what does the customer actually save vs what they pay now?

Both returned in API response.
UI shows customer_savings_pct in the savings column.
Ranking uses intrinsic_savings_pct.
```

---

### Task 3.3 — Remove All Pool Caps

**Files:** `substitute_manager.py`, `decision_engine.py`, any file with pool slicing

```
Search and remove:
  [:10], [:6], top_n=10, max_candidates=10, limit=10
  ranked[:MAX_POOLS], pools[:self.max_pools]

Replace with:
  Full list — no slice
  Pagination only at API response layer

Keep (do NOT remove):
  max_instance_type_attempts in auto_rebalancer
  This limits LAUNCH ATTEMPTS not pool universe
  Default 6 is correct — universe can be 400+ but we try 6 before giving up
```

---

## Phase 4 — Savings Data Model

---

### Task 4.1 — Create ClusterBaseline Model

**File:** `backend/models/cluster_baseline.py` (new) + Alembic migration

```
Model fields:
  cluster_id              (FK to clusters)
  original_instance_type  = t3.medium
  original_od_price_hr    = 0.0464
  original_node_count     = 5
  original_monthly_cost   = 169.35
  original_architecture   = amd64
  original_region         = ap-south-1
  recorded_at             = timestamp (immutable — never update this row)
  recorded_by             = onboarding / manual / auto-detected

Rules:
  Insert once at cluster onboarding
  Never UPDATE — append new row if cluster is re-onboarded
  Keep all historical baselines for audit trail
  Active baseline = latest recorded_at for cluster_id
```

---

### Task 4.2 — Update RebalancingAction Model

**File:** `backend/models/rebalancing_action.py` + Alembic migration

```
Add columns:
  source_od_price_hr      FLOAT   (OD price at decision time)
  target_spot_price_hr    FLOAT   (intended pool spot price at decision time)
  estimated_savings_hr    FLOAT
  estimated_savings_mo    FLOAT

  actual_instance_type    VARCHAR (what actually launched — may differ from intended)
  actual_az               VARCHAR
  actual_spot_price_hr    FLOAT   (spot price at launch time)
  realized_savings_hr     FLOAT
  realized_savings_mo     FLOAT
  realized_savings_pct    FLOAT
  savings_gap_hr          FLOAT   (estimated - realized, 0 if no fallback)

Write at action creation:
  source_od_price_hr, target_spot_price_hr,
  estimated_savings_hr, estimated_savings_mo

Write at action completion:
  actual_instance_type, actual_az, actual_spot_price_hr,
  realized_savings_hr, realized_savings_mo,
  realized_savings_pct, savings_gap_hr
```

---

### Task 4.3 — Fix Savings Calculator

**File:** `backend/workers/tasks/savings_calculator.py`

```
Hourly Celery task:

For each cluster:
  1. Load ClusterBaseline (immutable anchor)
     baseline_monthly_cost = original_od_price_hr × original_node_count × 730

  2. For each active spot node launched by platform:
     current_spot_price = latest from Redis spot_price:{region}:{az}:{type}
     source_od_price    = from rebalancing_action.source_od_price_hr
                          (the OD price of the node that was replaced)
     
     live_savings_hr    = source_od_price - current_spot_price
     live_savings_mo    = live_savings_hr × 730

  3. Cluster totals:
     current_monthly_cost     = sum(current_spot_price × 730) for all platform nodes
     total_live_savings_mo    = baseline_monthly_cost - current_monthly_cost
     total_live_savings_pct   = total_live_savings_mo / baseline_monthly_cost × 100
     total_live_savings_annual = total_live_savings_mo × 12

  4. Estimated vs realized gap:
     total_gap_mo = sum(action.savings_gap_hr × 730) for all completed actions

  5. Write SavingsSnapshot:
     {cluster_id, snapshot_at, baseline_monthly_cost,
      current_monthly_cost, realized_savings_mo,
      realized_savings_pct, realized_savings_annual,
      estimated_vs_realized_gap, data_freshness}

NEVER use estimated_savings as realized_savings.
NEVER recalculate from original target pool if fallback occurred.
ALWAYS use actual_spot_price_hr from rebalancing_action record.
```

---

## Phase 5 — API and Frontend

---

### Task 5.1 — Market View API

```
GET /clusters/{cluster_id}/market-view
  ?page=1&page_size=20&sort_by=final_score&sort_order=desc

Response:
{
  "source_node": {
    "instance_type": "t3.medium",
    "vcpu": 2,
    "memory_gb": 4,
    "od_price_hr": 0.0464,
    "baseline_monthly_cost": 169.35,
    "node_count": 5
  },
  "profile": "BALANCED",
  "weights": {"savings": 0.40, "risk": 0.40, "ml": 0.20},
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_valid_pools": 124,
    "total_pages": 7,
    "total_evaluated": 1170,
    "gates_eliminated": 1046
  },
  "pools": [
    {
      "rank": 1,
      "instance_type": "t3a.medium",
      "az": "ap-south-1a",
      "vcpu": 2,
      "memory_gb": 4,
      "architecture": "amd64",
      "spot_price_hr": 0.0139,
      "od_price_hr": 0.0464,
      "intrinsic_savings_pct": 70.0,
      "customer_savings_pct": 70.0,
      "customer_savings_monthly_per_node": 23.72,
      "customer_savings_monthly_total": 118.60,
      "interruption_rate": 5,
      "interruption_label": "<5%",
      "safety_score": 0.80,
      "savings_score": 1.00,
      "ml_score": 0.82,
      "ml_tier": 1,
      "final_score": 0.884,
      "health": "Healthy",
      "blacklisted": false,
      "soft_penalty_applied": false,
      "data_age_minutes": 14
    }
  ]
}
```

---

### Task 5.2 — Savings API

```
GET /clusters/{cluster_id}/savings

Response:
{
  "baseline": {
    "instance_type": "t3.medium",
    "node_count": 5,
    "monthly_cost": 169.35,
    "recorded_at": "2026-01-15T10:00:00Z"
  },
  "current": {
    "instance_type": "t3a.medium",
    "node_count": 5,
    "monthly_cost": 50.75,
    "spot_price_hr": 0.0139
  },
  "realized_savings": {
    "monthly": 118.60,
    "pct": 70.0,
    "annual": 1423.20
  },
  "estimated_vs_realized_gap": {
    "monthly": 5.92,
    "explanation": "Fallback launched c5.large instead of t3a.medium in 1 action"
  },
  "data_freshness": "2026-03-20T10:46:00Z",
  "recalculated": "hourly"
}
```

---

### Task 5.3 — Pool Audit API

```
GET /clusters/{cluster_id}/nodes/{node_id}/pool-audit

Response:
{
  "node_id": "i-abc123",
  "instance_type": "t3.medium",
  "resource_profile": {
    "vcpu_requested": 1.2,
    "memory_gb_requested": 3.2,
    "min_vcpu_required": 1.4,
    "min_memory_required": 3.6,
    "headroom_pct": 10,
    "source": "kubernetes_pod_requests"
  },
  "funnel": {
    "raw_pool_universe": 1170,
    "after_no_spot_price": 900,
    "after_capacity_floor": 520,
    "after_architecture": 420,
    "after_interruption_ceiling": 390,
    "after_blacklist": 385,
    "after_savings_gate": 310,
    "final_eligible": 310
  },
  "rejection_reasons": {
    "no_spot_price_in_az": 270,
    "too_small_vcpu": 180,
    "too_small_memory": 200,
    "architecture_incompatible": 100,
    "interruption_above_ceiling": 30,
    "blacklisted": 5,
    "spot_costs_more_than_od": 75
  },
  "ml_tier_stats": {
    "tier1_known": 220,
    "tier2_proxy": 70,
    "tier3_unknown": 20
  },
  "computed_at": "2026-03-20T10:44:00Z"
}
```

---

### Task 5.4 — Frontend Updates

```
Market View:
  Add pagination controls: [←] [1][2]...[7] [→]
  Add sortable column headers
  Show TWO savings columns:
    "Pool Saving" = intrinsic_savings_pct (how good is this pool)
    "Your Saving" = customer_savings_pct (what you actually save)
  Show ml_tier badge: T1 / T2 / T3
  Show soft_penalty_applied indicator
  Live update indicator: ● Live / ⚠ Stale

Savings Panel (new or replace existing):
  Baseline vs current comparison
  Realized savings (not estimated)
  Estimated vs realized gap with explanation
  Last recalculated timestamp

Cluster Impact View:
  Per-node funnel breakdown
  Coverage status: COVERED / AT_RISK / STRANDED
  Expandable rows showing per-node alternatives

Pool Audit Panel:
  Visual funnel: 1170 → 900 → 520 → ... → 310
  Shows exactly where pools were eliminated
  "Why didn't it recommend X?" answered here
```

---

## Implementation Order and Verification

```
Week 1 — Data (Phase 1):
  Day 1-2: Task 1.1 scraper fix
           ✓ spot_advisor_rates: 400+ rows
           ✓ t4g.micro rate = 25 not 5
  Day 2-3: Task 1.2 pricing service
           ✓ spot price keys: 1200+ in Redis
  Day 3-4: Task 1.3 instance catalog
           ✓ catalog: 400+ types
           ✓ m7i.large present
  Day 4-5: Task 1.4 cache builder
           ✓ global_pool_cache: 800+ entries

Week 2 — ML Pipeline (Phase 2):
  Day 1:   Task 2.1 category_mapping.json
           ✓ m7i, m7g, c7i, c7g present
           ✓ zero pools dropped for unknown_category
  Day 2:   Task 2.2 capacity validator
           ✓ uses pod requests not node total
  Day 3:   Task 2.3 architecture filter
           ✓ arm64 pools appear for multi-arch workloads
  Day 4:   Task 2.4 WorkloadInspector extensions
           ✓ node_resource_profile cached per node
           ✓ node_arch_compat cached per node
  Day 5:   Task 2.5 ML scoring tiers
           ✓ tier2 and tier3 pools get scores not exceptions
  Day 5:   Task 2.6 AZ interruption estimation
           ✓ each pool has az-specific rate
  Day 6:   Task 2.7 rejection audit logging
           ✓ logs show full funnel per node

Week 3 — Scoring + Savings (Phases 3 + 4):
  Day 1:   Task 3.1 weighted scoring formula
           ✓ Pool A (<5% risk) scores higher than Pool B (>15% risk)
           ✓ Score range > 0.3 (not compressed)
  Day 2:   Task 3.2 separate savings figures
           ✓ intrinsic and customer savings both present in response
  Day 3:   Task 3.3 remove pool caps
           ✓ no [:10] or similar in codebase
  Day 4:   Task 4.1 ClusterBaseline model
           ✓ baseline stored at onboarding
           ✓ never overwritten
  Day 5:   Task 4.2 RebalancingAction new columns
           ✓ estimated vs realized both stored
           ✓ savings_gap_hr populated after fallback actions
  Day 6:   Task 4.3 savings calculator fix
           ✓ uses actual_spot_price_hr not estimated
           ✓ computes vs baseline not floating OD

Week 4 — API + Frontend (Phase 5):
  Day 1-2: Tasks 5.1-5.3 API endpoints
           ✓ market-view returns 100+ pools paginated
           ✓ savings API shows realized not estimated
           ✓ pool-audit API shows funnel breakdown
  Day 3-4: Task 5.4 frontend
           ✓ pagination works
           ✓ two savings columns visible
           ✓ funnel visualization renders
  Day 5:   Full integration test
           ✓ pool count: 7 → 100+
           ✓ t4g.micro ranked low (>20% risk)
           ✓ r5.xlarge eliminated (costs more than source OD)
           ✓ realized savings != estimated when fallback occurred
           ✓ ML tier2/tier3 pools appear in rankings
```Here's the complete instruction set for Claude Code to execute.

---

## Pre-Execution: Read These Files First

```
Read every file before touching anything:

backend/scrapers/spot_advisor_scraper.py
backend/scrapers/spot_advisor_enhanced.py
backend/services/aws_pricing_service.py
backend/services/pool_ranking_service.py
backend/services/substitute_manager.py
backend/services/workload_inspector.py
backend/core/decision_engine.py
backend/workers/tasks/cache_builder.py
backend/workers/tasks/savings_calculator.py
backend/workers/tasks/auto_rebalancer.py
backend/models/instance_catalog.py
backend/models/cluster.py
backend/models/rebalancing_action.py
ml_model/decision_engine/pipeline.py
ml_model/decision_engine/06_capacity_validator.py
ml_model/decision_engine/08_template_filter.py
ml_model/model/category_mapping.json
frontend/src/components/dashboard/Dashboard.jsx
frontend/src/components/clusters/ClusterDetails.jsx

After reading, answer these before writing any code:
  1. What is current pool count in global_pool_cache?
  2. How many rows in spot_advisor_rates table?
  3. How many families in category_mapping.json?
  4. Where exactly is [:10] or similar cap?
  5. Does ClusterBaseline model exist?
  6. Is WorkloadInspector called BEFORE ML pipeline?
  7. What is ONNX model output range?
  8. Where is savings currently computed?
  9. What does describe_spot_price_history call look like?
  10. What does the current scoring formula look like?
```

---

## Block 1 — Fix Spot Advisor Scraper

**File:** `backend/scrapers/spot_advisor_scraper.py`

```
Instructions:

1. Find the function that downloads Spot Advisor data.

2. Change the download to fetch the complete JSON:
   URL: https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json
   Do not filter by existing DB records before downloading.

3. Fix OS handling:
   Hardcode OS = "Linux" everywhere.
   Remove any loop that iterates over multiple OS types.
   Never process Windows, SUSE, or other OS types.

4. Fix the interruption index translation:
   Replace whatever mapping exists with exactly this:
   {0: 5, 1: 10, 2: 15, 3: 20, 4: 25}
   If r value is missing or not in map: store None, NOT 0, NOT 5.

5. Fix KeyError handling:
   If instance type is missing from region data: store None.
   Never default to 5 or 0 on any exception.

6. Change hash logic to per-region:
   Remove any global blob hash.
   For each region:
     Compute hash of that region's data only.
     Key: spot:advisor:hash:{region}
     Skip DB writes for that region if hash unchanged.
     BUT always write timestamp regardless of hash match.

7. Always write after every successful scrape per region:
   redis_client.set(f"spot:advisor:last_scraped:{region}", utcnow().isoformat())

8. Change iteration to process ALL instance types from JSON:
   For region in json_data['spot_advisor']:
     For instance_type in json_data['spot_advisor'][region]['Linux']:
       Extract r value, translate to interruption_rate using map above.
       Extract s value (savings vs OD percentage).
       Upsert to spot_advisor_rates table.

9. After changes, run scraper manually and verify:
   SELECT COUNT(*) FROM spot_advisor_rates WHERE region = 'ap-south-1';
   Result must be 300+ not ~20.
   
   SELECT interruption_rate FROM spot_advisor_rates 
   WHERE instance_type = 't4g.micro' AND region = 'ap-south-1';
   Result must be 25, not 5.
```

---

## Block 2 — Fix AWS Pricing Service

**File:** `backend/services/aws_pricing_service.py`

```
Instructions:

1. Find the describe_spot_price_history call.

2. Remove the InstanceTypes filter parameter entirely.
   Do not pass any instance type list to this call.
   Let AWS return all available spot types.

3. Add Boto3 paginator:
   paginator = ec2_client.get_paginator('describe_spot_price_history')
   Use paginator.paginate() not direct ec2_client.describe_spot_price_history()
   Process every page of results.

4. Add these filters to the paginator call:
   Filters: ProductDescription = Linux/UNIX
   StartTime: datetime.utcnow() - timedelta(hours=2)
   Do NOT filter by AvailabilityZone — let it return all AZs.

5. For each record returned:
   pool_key = f"{region}:{record['AvailabilityZone']}:{record['InstanceType']}"
   Store in Redis:
     Key: spot_price:{region}:{az}:{instance_type}
     Value: float(record['SpotPrice'])
     TTL: 3600 seconds

6. Also fetch OD pricing:
   Find where OD prices are fetched.
   Remove any instance type filter there too.
   Cache: od_price:{region}:{instance_type} TTL=86400s

7. After changes verify:
   redis-cli KEYS "spot_price:ap-south-1:*" | wc -l
   Result must be 1000+ not ~60.
```

---

## Block 3 — Fix Instance Catalog

**File:** `backend/models/instance_catalog.py` or wherever describe_instance_types is called

```
Instructions:

1. Find where instance type specs (vcpu, memory) are stored.

2. If it is a hardcoded dict: replace with dynamic fetch.
   If it calls describe_instance_types with filters: remove filters.

3. Call describe_instance_types with no InstanceTypes filter:
   Use Boto3 paginator.
   Process every page.

4. For each instance type extract and store:
   instance_type: string key
   vcpu: VCpuInfo.DefaultVCpus
   memory_gb: MemoryInfo.SizeInMiB / 1024
   architecture: ProcessorInfo.SupportedArchitectures (list)
   supported_usage_classes: must contain 'spot' to be eligible
   has_gpu: True if GpuInfo exists
   has_local_storage: True if InstanceStorageSupported

5. Upsert to instance_catalog table.
   Cache each in Redis:
   instance_spec:{instance_type} = {vcpu, memory_gb, architecture, has_gpu}
   TTL: 86400s

6. Run this on application startup and register as daily Celery beat task.

7. Verify:
   SELECT COUNT(*) FROM instance_catalog;
   Result must be 400+.
   
   SELECT vcpu, memory_gb FROM instance_catalog WHERE instance_type = 't4g.micro';
   Must return: vcpu=2, memory_gb=1 (NOT 4).
```

---

## Block 4 — Fix Cache Builder

**File:** `backend/workers/tasks/cache_builder.py`

```
Instructions:

1. Find the function that builds the global pool cache.

2. Remove any hardcoded instance type list.

3. Load ALL instance types from instance_catalog table:
   types = db.query(InstanceCatalog).filter(
     InstanceCatalog.supported_usage_classes.contains('spot')
   ).all()

4. Load ALL AZs for the region:
   response = ec2_client.describe_availability_zones(
     Filters=[{'Name': 'state', 'Values': ['available']}]
   )
   azs = [az['ZoneName'] for az in response['AvailabilityZones']]

5. Build cross-product and for each combination:
   pool_key = f"{region}:{az}:{instance_type}"
   
   spot_price = redis_client.get(f"spot_price:{region}:{az}:{instance_type}")
   if not spot_price: continue  (not available as spot in this AZ)
   
   od_price = redis_client.get(f"od_price:{region}:{instance_type}")
   if not od_price: continue
   
   savings_pct = (od_price - spot_price) / od_price * 100
   if savings_pct <= 0: continue  (spot costs more than OD)
   
   interruption_rate = query spot_advisor_rates for this region+instance_type
   vcpu, memory_gb, architecture = from instance_catalog

6. Store all valid pools:
   global_pool_cache:{region} = json of all pool dicts
   TTL: 3600s

7. Log build summary at completion:
   logger.info(f"Cache built: raw={total_cross_product}, 
               no_spot={no_spot_count}, neg_savings={neg_savings_count},
               final={len(valid_pools)}")

8. Verify after running:
   Check Redis key global_pool_cache:ap-south-1
   Parse JSON and count entries: must be 700+.
   Check log for build summary numbers.
```

---

## Block 5 — Update category_mapping.json

**File:** `ml_model/model/category_mapping.json`

```
Instructions:

1. Read the current file completely first.

2. Identify which families are in Tier 1 (model trained on these).
   These should include at minimum: m5, m6i, m6g, c5, c6i, c6g, r5, r6i, r6g, t3, t3a.
   Verify by checking what the ONNX model was actually trained on.

3. Add ALL of these to Tier 2 if not already present:
   m7i  → proxy: m6i, penalty: 0.90
   m7g  → proxy: m6g, penalty: 0.90
   m7a  → proxy: m6a, penalty: 0.90
   c7i  → proxy: c6i, penalty: 0.90
   c7g  → proxy: c6g, penalty: 0.90
   c7a  → proxy: c6a, penalty: 0.90
   r7i  → proxy: r6i, penalty: 0.90
   r7g  → proxy: r6g, penalty: 0.90
   r7a  → proxy: r6a, penalty: 0.90
   m6a  → proxy: m6i, penalty: 0.90
   c6a  → proxy: c6i, penalty: 0.90
   r6a  → proxy: r6i, penalty: 0.90
   i4i  → proxy: i3,  penalty: 0.90
   i4g  → proxy: i3,  penalty: 0.90
   x2idn → proxy: x1e, penalty: 0.85
   x2iedn → proxy: x1e, penalty: 0.85

4. Set Tier 3 penalty = 0.75 for everything not in Tier 1 or 2.

5. Restructure file to this exact format:
{
  "tier1": ["m5", "m6i", "m6g", "c5", "c6i", "c6g", "r5", "r6i", "r6g", "t3", "t3a"],
  "tier2": {
    "m7i": {"proxy": "m6i", "penalty": 0.90},
    "m7g": {"proxy": "m6g", "penalty": 0.90},
    ... (all entries above)
  },
  "tier3_penalty": 0.75
}

6. Verify: every instance type in the global_pool_cache
   maps to tier1, tier2, or will use tier3.
   No pool should ever be dropped for unknown family after this.
```

---

## Block 6 — Fix Capacity Validator

**File:** `ml_model/decision_engine/06_capacity_validator.py`

```
Instructions:

1. Find where min_vcpu and min_memory are set for filtering.

2. Replace the current logic with this:
   
   # Try to load actual pod requests from Redis
   profile_key = f"node_resource_profile:{node.node_id}"
   profile = redis_client.get(profile_key)
   
   if profile:
     data = json.loads(profile)
     pod_vcpu = data['vcpu_requested']
     pod_memory = data['memory_gb_requested']
     headroom = cluster_config.get('replacement_headroom_pct', 10)
     min_vcpu   = math.ceil(pod_vcpu * (1 + headroom/100))
     min_memory = math.ceil(pod_memory * (1 + headroom/100))
   else:
     # Fallback to node total if no pod data available
     logger.warning(f"No pod request profile for {node.node_id}, using node total")
     min_vcpu   = node.vcpu_total
     min_memory = node.memory_gb_total

3. Use min_vcpu and min_memory as the filter floor.

4. Track rejection counts:
   if pool.vcpu < min_vcpu: rejection_reasons['too_small_vcpu'] += 1; continue
   if pool.memory_gb < min_memory: rejection_reasons['too_small_memory'] += 1; continue
```

---

## Block 7 — Fix Architecture Filter

**File:** `ml_model/decision_engine/08_template_filter.py`

```
Instructions:

1. Find where architecture filtering happens.

2. Replace hardcoded amd64-only logic with:
   
   compat_key = f"node_arch_compat:{node.node_id}"
   compat = redis_client.get(compat_key)
   arm64_eligible = json.loads(compat)['arm64'] if compat else False

3. Filter logic:
   if not arm64_eligible:
     if pool.architecture == 'arm64':
       rejection_reasons['architecture_incompatible'] += 1
       continue
   
   # Always filter these regardless of arm64_eligible:
   gpu_families = ['p2', 'p3', 'p4', 'g3', 'g4', 'g5']
   special_families = ['inf', 'trn', 'mac', 'f1', 'vt1']
   
   family = extract_family(pool.instance_type)
   
   if any(pool.instance_type.startswith(f) for f in gpu_families):
     if not node.has_gpu_pods:
       rejection_reasons['gpu_not_needed'] += 1
       continue
   
   if any(pool.instance_type.startswith(f) for f in special_families):
     rejection_reasons['special_hardware'] += 1
     continue
   
   if pool.instance_type.endswith('.metal'):
     rejection_reasons['bare_metal'] += 1
     continue
```

---

## Block 8 — Extend WorkloadInspector

**File:** `backend/services/workload_inspector.py`

```
Instructions:

1. Add this method to the WorkloadInspector class:

   def compute_node_resource_profile(self, node_id: str, node_name: str) -> dict:
     
     # Get all pods on this node from Kubernetes
     pods = k8s_client.list_pod_for_all_namespaces(
       field_selector=f"spec.nodeName={node_name}"
     ).items
     
     total_cpu_millicores = 0
     total_memory_mib = 0
     
     for pod in pods:
       if pod.status.phase not in ('Running', 'Pending'):
         continue
       for container in pod.spec.containers:
         if container.resources and container.resources.requests:
           cpu_str = container.resources.requests.get('cpu', '0')
           mem_str = container.resources.requests.get('memory', '0')
           total_cpu_millicores += parse_cpu_to_millicores(cpu_str)
           total_memory_mib += parse_memory_to_mib(mem_str)
     
     profile = {
       'vcpu_requested': round(total_cpu_millicores / 1000, 2),
       'memory_gb_requested': round(total_memory_mib / 1024, 2),
       'pod_count': len(pods),
       'computed_at': datetime.utcnow().isoformat()
     }
     
     redis_client.setex(
       f"node_resource_profile:{node_id}",
       300,  # 5 min TTL
       json.dumps(profile)
     )
     return profile

2. Add helper functions if not present:
   parse_cpu_to_millicores: converts '500m' → 500, '2' → 2000, '0.5' → 500
   parse_memory_to_mib: converts '512Mi' → 512, '1Gi' → 1024, '2G' → 1907

3. Add this method:

   def compute_node_arch_compatibility(self, node_id: str, node_name: str) -> dict:
     
     pods = k8s_client.list_pod_for_all_namespaces(
       field_selector=f"spec.nodeName={node_name}"
     ).items
     
     arm64_eligible = True
     reason = "all_containers_multi_arch"
     
     for pod in pods:
       # Check nodeSelector
       if pod.spec.node_selector:
         arch = pod.spec.node_selector.get('kubernetes.io/arch', '')
         if arch == 'amd64':
           arm64_eligible = False
           reason = f"pod_{pod.metadata.name}_requires_amd64_via_nodeselector"
           break
       
       # Check nodeAffinity
       if pod.spec.affinity and pod.spec.affinity.node_affinity:
         affinity = pod.spec.affinity.node_affinity
         # Parse required rules for arch requirements
         # If arch=amd64 required → not arm64 eligible
       
       # Check image name patterns as last resort
       for container in pod.spec.containers:
         image = container.image.lower()
         if any(pattern in image for pattern in ['windows', 'nanoserver', 'amd64']):
           arm64_eligible = False
           reason = f"image_{image}_is_amd64_only"
           break
     
     result = {
       'arm64': arm64_eligible,
       'reason': reason,
       'computed_at': datetime.utcnow().isoformat()
     }
     
     redis_client.setex(
       f"node_arch_compat:{node_id}",
       3600,  # 1 hour TTL
       json.dumps(result)
     )
     return result

4. Call both methods in the scan loop in auto_rebalancer.py:
   BEFORE the ML pipeline runs, after STATELESS_ELIGIBLE classification:
   
   workload_inspector.compute_node_resource_profile(node.instance_id, node.node_name)
   workload_inspector.compute_node_arch_compatibility(node.instance_id, node.node_name)
   
   These populate the Redis cache that capacity_validator and template_filter read.
```

---

## Block 9 — Fix ML Scoring Tiers

**File:** `backend/core/decision_engine.py`

```
Instructions:

1. Find where the ML model score is computed for each pool.

2. Replace with this tiered function:

   def get_ml_score(pool_instance_type, category_mapping, onnx_model):
     
     family = extract_instance_family(pool_instance_type)
     # Extract family: 'm7i.large' → 'm7i', 't3a.medium' → 't3a'
     # Logic: split on '.', take first part, strip trailing digits
     
     if family in category_mapping['tier1']:
       features = build_full_features(pool_instance_type)
       raw_score = onnx_model.predict(features)[0]
       confidence = 1.0
       tier = 1
     
     elif family in category_mapping['tier2']:
       proxy_family = category_mapping['tier2'][family]['proxy']
       confidence = category_mapping['tier2'][family]['penalty']
       proxy_instance = pool_instance_type.replace(family, proxy_family)
       features = build_full_features(proxy_instance)
       raw_score = onnx_model.predict(features)[0]
       tier = 2
     
     else:
       size_class = extract_size_class(pool_instance_type)
       raw_score = get_size_class_average_score(size_class)
       confidence = category_mapping['tier3_penalty']
       tier = 3
     
     # Check and correct for ONNX output range compression
     # Run this once on startup to determine model range:
     # MODEL_OUTPUT_MIN, MODEL_OUTPUT_MAX from validation set
     if MODEL_OUTPUT_MAX - MODEL_OUTPUT_MIN < 0.5:
       raw_score = (raw_score - MODEL_OUTPUT_MIN) / (MODEL_OUTPUT_MAX - MODEL_OUTPUT_MIN)
     
     final_ml_score = raw_score * confidence
     return final_ml_score, tier

3. This function must NEVER raise an exception.
   NEVER return None.
   ALWAYS return a float score and tier integer.

4. Add size_class_average computation:
   Compute average Tier 1 score for each size class (large, xlarge, 2xlarge etc.)
   Store in Redis on startup: size_class_avg:{size_class}
   Use as fallback for Tier 3 pools.
```

---

## Block 10 — Add AZ Interruption Estimation

**File:** `backend/services/pool_ranking_service.py`

```
Instructions:

1. Add this function:

   def estimate_az_interruption(instance_type, az, region):
     
     # Layer 1: AWS region rate
     rate_record = db.query(SpotAdvisorRate).filter_by(
       instance_type=instance_type, region=region
     ).first()
     
     if not rate_record or rate_record.interruption_rate is None:
       return None  # Unknown → will be eliminated by interruption gate
     
     region_rate = rate_record.interruption_rate
     
     # Layer 2: AZ price adjustment
     az_price = float(redis_client.get(f"spot_price:{region}:{az}:{instance_type}") or 0)
     
     # Get average across all AZs for this type
     az_prices = []
     for az_key in redis_client.scan_iter(f"spot_price:{region}:*:{instance_type}"):
       val = redis_client.get(az_key)
       if val: az_prices.append(float(val))
     
     if az_prices and az_price > 0:
       region_avg = sum(az_prices) / len(az_prices)
       price_ratio = az_price / region_avg if region_avg > 0 else 1.0
       if price_ratio > 1.20:
         az_adjustment = 1
       elif price_ratio > 1.10:
         az_adjustment = 0.5
       else:
         az_adjustment = 0
     else:
       az_adjustment = 0
     
     # Layer 3: Own historical data
     history_key = f"interruption_history:{region}:{az}:{instance_type}"
     history_data = redis_client.get(history_key)
     
     if history_data:
       history = json.loads(history_data)
       own_rate = history['rate']
       history_weight = min(history['count'] / 100, 0.5)
     else:
       own_rate = region_rate
       history_weight = 0
     
     aws_weight = 1 - history_weight
     combined = (region_rate + az_adjustment) * aws_weight + own_rate * history_weight
     return min(round(combined, 1), 25)

2. Add this function to termination_monitor.py:

   def record_interruption_event(region, az, instance_type):
     key = f"interruption_history:{region}:{az}:{instance_type}"
     existing = redis_client.get(key)
     history = json.loads(existing) if existing else {'rate': 0, 'count': 0}
     history['count'] += 1
     history['rate'] = history['rate'] * 0.9 + 25 * 0.1
     redis_client.setex(key, 86400 * 7, json.dumps(history))

   Call record_interruption_event() inside detect_termination_notice()
   after the instance type and AZ are extracted from the event.

3. Replace all places that use region-level interruption rate
   for a specific pool with estimate_az_interruption() instead.
```

---

## Block 11 — Add Rejection Audit Logging

**File:** `ml_model/decision_engine/pipeline.py`

```
Instructions:

1. At the start of the main filter function, add:

   rejection_reasons = {
     'no_spot_price_in_az': 0,
     'too_small_vcpu': 0,
     'too_small_memory': 0,
     'architecture_incompatible': 0,
     'gpu_not_needed': 0,
     'special_hardware': 0,
     'bare_metal': 0,
     'interruption_above_ceiling': 0,
     'blacklisted': 0,
     'dry_run_fail': 0,
     'spot_costs_more_than_od': 0,
   }
   
   ml_tier_stats = {'tier1': 0, 'tier2': 0, 'tier3': 0}
   raw_count = len(all_pools)

2. At each gate rejection, increment the relevant counter.

3. At ML scoring, increment ml_tier_stats[f'tier{tier}'].

4. At the end of the function:

   audit = {
     'node_id': node.node_id,
     'cluster_id': cluster_id,
     'raw_pool_count': raw_count,
     'eligible_count': len(eligible_pools),
     'rejection_reasons': rejection_reasons,
     'ml_tier_stats': ml_tier_stats,
     'computed_at': datetime.utcnow().isoformat()
   }
   
   logger.info(f"Pool audit: {json.dumps(audit)}")
   
   redis_client.setex(
     f"pool_audit:{cluster_id}:{node.node_id}",
     300,
     json.dumps(audit)
   )

5. Add API endpoint:
   GET /clusters/{cluster_id}/nodes/{node_id}/pool-audit
   Returns the Redis value for pool_audit:{cluster_id}:{node_id}
```

---

## Block 12 — Fix Scoring Formula

**File:** `backend/core/decision_engine.py`

```
Instructions:

1. Find the current final_score computation. Read it carefully.
   Note if it uses min-max batch normalization.
   Note if risk is added (wrong) or inverted (correct).

2. Replace entirely with:

   PROFILE_WEIGHTS = {
     'COST_FIRST':   {'savings': 0.60, 'risk': 0.20, 'ml': 0.20},
     'BALANCED':     {'savings': 0.40, 'risk': 0.40, 'ml': 0.20},
     'NO_DOWNTIME':  {'savings': 0.20, 'risk': 0.60, 'ml': 0.20},
   }

   def compute_final_score(pool, source_od_price, profile, category_mapping, onnx_model):
     
     weights = PROFILE_WEIGHTS[profile]
     
     # Savings score — absolute normalization, NOT batch min/max
     intrinsic_savings = (pool.od_price - pool.spot_price) / pool.od_price
     savings_score = max(0.0, min(intrinsic_savings / 0.70, 1.0))
     # 0.70 cap: anything above 70% intrinsic gets max savings_score of 1.0
     
     # Safety score — absolute normalization
     az_rate = estimate_az_interruption(pool.instance_type, pool.az, pool.region)
     if az_rate is None:
       return None  # Unknown interruption rate → skip this pool
     safety_score = max(0.0, 1.0 - (az_rate / 25.0))
     # <5% → 0.80, 10% → 0.60, 20% → 0.20, >20% → 0.00
     
     # ML score — tiered with confidence penalty
     ml_raw, tier = get_ml_score(pool.instance_type, category_mapping, onnx_model)
     ml_score = ml_raw  # already multiplied by confidence in get_ml_score
     
     # Soft penalty for recently-recovered pools
     failure_count = int(redis_client.get(f"recent_failure_count:{pool.pool_key}") or 0)
     soft_penalty = 0.85 if failure_count > 0 else 1.0
     
     # Weighted sum — all components positive, weights sum to 1.0
     raw_score = (
       weights['savings'] * savings_score +
       weights['risk']    * safety_score +
       weights['ml']      * ml_score
     )
     
     final_score = raw_score * soft_penalty
     
     # Store component scores for UI display and debugging
     pool.savings_score = savings_score
     pool.safety_score = safety_score
     pool.ml_score = ml_score
     pool.ml_tier = tier
     pool.soft_penalty = soft_penalty
     pool.final_score = final_score
     
     # Customer savings for UI display (different from intrinsic)
     pool.customer_savings_pct = (source_od_price - pool.spot_price) / source_od_price * 100
     pool.customer_savings_monthly = (source_od_price - pool.spot_price) * 730
     
     return final_score

3. Remove all pool caps after scoring:
   Search for: [:10], [:6], top_n, max_candidates, limit=
   Remove every instance.
   Return the full sorted list.
   Pagination happens only at the API layer.
```

---

## Block 13 — Create ClusterBaseline Model

**Files:** `backend/models/cluster_baseline.py` (create new) + Alembic migration

```
Instructions:

1. Create new file backend/models/cluster_baseline.py:

   class ClusterBaseline(Base):
     __tablename__ = 'cluster_baselines'
     
     id                    = Column(Integer, primary_key=True)
     cluster_id            = Column(String, ForeignKey('clusters.id'), nullable=False)
     original_instance_type = Column(String, nullable=False)
     original_od_price_hr  = Column(Float, nullable=False)
     original_node_count   = Column(Integer, nullable=False)
     original_monthly_cost = Column(Float, nullable=False)  # = od_price × count × 730
     original_architecture = Column(String)
     original_region       = Column(String)
     recorded_at           = Column(DateTime, default=datetime.utcnow, nullable=False)
     recorded_by           = Column(String, default='auto')
     # Never add an update method — this model is append-only

2. Create Alembic migration for this table.

3. Find where clusters are onboarded or first connected.
   After cluster registers, insert a ClusterBaseline record:
   
   baseline = ClusterBaseline(
     cluster_id=cluster.id,
     original_instance_type=detected_primary_instance_type,
     original_od_price_hr=get_od_price(instance_type, region),
     original_node_count=current_node_count,
     original_monthly_cost=od_price × node_count × 730,
     original_region=cluster.region
   )
   db.add(baseline)
   db.commit()
   
   NEVER call db.query(ClusterBaseline).filter_by(...).update(...)
   Only ever INSERT, never UPDATE.

4. Add helper: get_active_baseline(cluster_id)
   Returns: db.query(ClusterBaseline).filter_by(cluster_id=cluster_id)
            .order_by(ClusterBaseline.recorded_at.desc()).first()
```

---

## Block 14 — Update RebalancingAction Model

**File:** `backend/models/rebalancing_action.py` + Alembic migration

```
Instructions:

1. Add these columns if not already present:
   source_od_price_hr      Float    nullable=True
   target_spot_price_hr    Float    nullable=True
   estimated_savings_hr    Float    nullable=True
   estimated_savings_mo    Float    nullable=True
   actual_instance_type    String   nullable=True
   actual_az               String   nullable=True
   actual_spot_price_hr    Float    nullable=True
   realized_savings_hr     Float    nullable=True
   realized_savings_mo     Float    nullable=True
   realized_savings_pct    Float    nullable=True
   savings_gap_hr          Float    nullable=True

2. Create Alembic migration.

3. In auto_rebalancer.py at action creation time, populate:
   action.source_od_price_hr = get_od_price(source_instance_type, region)
   action.target_spot_price_hr = chosen_pool.spot_price
   action.estimated_savings_hr = source_od_price - target_spot_price
   action.estimated_savings_mo = estimated_savings_hr × 730

4. In auto_rebalancer.py at action completion (after successful launch):
   action.actual_instance_type = actually_launched_instance_type
   action.actual_az = actually_launched_az
   action.actual_spot_price_hr = get_current_spot_price(actual_instance_type, actual_az, region)
   action.realized_savings_hr = action.source_od_price_hr - action.actual_spot_price_hr
   action.realized_savings_mo = action.realized_savings_hr × 730
   action.realized_savings_pct = action.realized_savings_hr / action.source_od_price_hr × 100
   action.savings_gap_hr = action.estimated_savings_hr - action.realized_savings_hr
   db.commit()
```

---

## Block 15 — Fix Savings Calculator

**File:** `backend/workers/tasks/savings_calculator.py`

```
Instructions:

1. Find the current savings computation. Read it fully.
   Note if it uses estimated or realized.
   Note what it uses as the source price.

2. Replace the computation with:

   For each cluster:
   
   a. Load baseline:
      baseline = get_active_baseline(cluster_id)
      baseline_monthly = baseline.original_od_price_hr × baseline.original_node_count × 730
   
   b. For each active spot node launched by platform:
      Get rebalancing_action for this node.
      source_od_price = action.source_od_price_hr
      
      current_spot_price = float(redis_client.get(
        f"spot_price:{region}:{node.az}:{node.instance_type}"
      ) or action.actual_spot_price_hr)
      
      live_savings_hr = source_od_price - current_spot_price
      live_savings_mo = live_savings_hr × 730
   
   c. Cluster totals:
      total_current_cost_mo = sum(current_spot_price × 730 for all platform nodes)
      total_realized_savings_mo = baseline_monthly - total_current_cost_mo
      total_realized_savings_pct = total_realized_savings_mo / baseline_monthly × 100
      total_gap_mo = sum(action.savings_gap_hr × 730 for all completed actions)
   
   d. Write SavingsSnapshot:
      {
        cluster_id, snapshot_at,
        baseline_monthly_cost: baseline_monthly,
        current_monthly_cost: total_current_cost_mo,
        realized_savings_mo: total_realized_savings_mo,
        realized_savings_pct: total_realized_savings_pct,
        realized_savings_annual: total_realized_savings_mo × 12,
        estimated_vs_realized_gap_mo: total_gap_mo,
        data_freshness: utcnow()
      }

3. NEVER use estimated_savings_mo as the displayed savings figure.
   NEVER use action.target_spot_price_hr if actual_spot_price_hr is available.
   ALWAYS prefer actual_spot_price_hr over target_spot_price_hr.
   ALWAYS use ClusterBaseline as the anchor, not a floating OD price.
```

---

## Block 16 — Add API Endpoints

**File:** Wherever cluster API routes are defined

```
Instructions:

1. Add Market View endpoint:
   GET /clusters/{cluster_id}/market-view
   
   Params: page (int, default 1), page_size (int, default 20, max 100),
           sort_by (str, default 'final_score'),
           sort_order (str, default 'desc')
   
   Logic:
     Load ClusterBaseline for source node context.
     Load node_resource_profile for primary OD node.
     Run full eligibility pipeline with per-node gates.
     Sort by requested sort field.
     Return paginated slice.
   
   Response includes:
     source_node: {instance_type, vcpu, memory_gb, od_price_hr, baseline_monthly_cost}
     profile: current cluster profile
     weights: {savings, risk, ml}
     pagination: {page, page_size, total_valid_pools, total_pages, total_evaluated}
     pools: array of pool objects with all score components

2. Add Node Alternatives endpoint:
   GET /clusters/{cluster_id}/nodes/{node_id}/alternatives
   Params: page, page_size
   
   Logic:
     Load specific node resource profile from Redis.
     Run pipeline specifically for that node's requirements.
     Return paginated results with node context.

3. Add Pool Audit endpoint:
   GET /clusters/{cluster_id}/nodes/{node_id}/pool-audit
   
   Logic:
     Return Redis value: pool_audit:{cluster_id}:{node_id}
     If missing: return 404 with message "Run a rebalancing cycle first"

4. Add Savings endpoint:
   GET /clusters/{cluster_id}/savings
   
   Logic:
     Load latest SavingsSnapshot.
     Load ClusterBaseline.
     Return combined response with baseline, current, realized, gap.
```

---

## Block 17 — Frontend Updates

**File:** `frontend/src/components/dashboard/Dashboard.jsx` and cluster detail components

```
Instructions:

1. Market View tab:
   
   Add pagination state: page, totalPages, totalPools.
   
   Add pagination controls below the table:
     Previous button: disabled when page = 1
     Page numbers: show current ± 2 pages
     Next button: disabled when page = totalPages
     Total count: "Showing {start}-{end} of {totalPools} pools"
   
   Add sortable column headers:
     Click header → toggle sort direction → re-fetch with new sort params
     Show sort indicator arrow on active column
   
   Add two savings columns:
     "Pool Saving" header → shows pool.intrinsic_savings_pct
     "Your Saving" header → shows pool.customer_savings_pct
     Label each clearly so user understands the difference
   
   Add ML tier badge on each row:
     T1 = green badge (full model)
     T2 = yellow badge (proxy)
     T3 = gray badge (estimate)
   
   Add live indicator in table header:
     ● Live (green) when last fetch < 60s ago
     ⚠ Stale (yellow) when last fetch > 5 min ago

2. Savings panel:
   
   Replace any estimated savings display with realized savings.
   
   Show three sections:
     Baseline: "{instance_type} × {node_count} On-Demand = ${baseline_monthly}/mo"
     Current:  "{instance_type} × {node_count} Spot = ${current_monthly}/mo"
     Realized: "${realized_savings_mo}/mo saved ({realized_savings_pct}%)"
   
   If estimated_vs_realized_gap > 0, show:
     "Note: ${gap}/mo less than estimated due to fallback launches"
   
   Show data freshness timestamp.

3. Pool Audit panel (add to Cluster Impact View):
   
   Show funnel visualization:
     Raw universe: 1,170
     After no spot price: -270 = 900
     After capacity floor: -380 = 520
     ... (each stage)
     Final eligible: 124
   
   Use horizontal bar chart or step-down visual.
   Each stage shows: stage name, pools eliminated, pools remaining.
   
   Show ML tier breakdown:
     Tier 1 (full model): X pools
     Tier 2 (proxy): Y pools
     Tier 3 (estimate): Z pools
```

---

## Block 18 — Remove All Pool Caps

```
Instructions:

Search the entire codebase for these patterns:
  [:10]
  [:6]
  top_n
  max_candidates
  limit=10
  ranked[:
  pools[:
  candidates[:
  MAX_POOLS
  
For each match:
  Read the context.
  If it is limiting the pool universe before ranking: REMOVE it.
  If it is limiting launch attempts (max_instance_type_attempts): KEEP it.
  
The rule:
  Pool universe = no cap (remove all these)
  Launch attempt limit = keep (this is separate, default 6)

After removing caps:
  Add pagination at API response layer only.
  The API endpoint slices the full list for the requested page.
  The execution engine always sees the full ranked list.
```

---

## Block 19 — Verification Steps

```
Run these checks after all blocks are complete:

Data verification:
  1. SELECT COUNT(*) FROM spot_advisor_rates WHERE region = 'ap-south-1';
     Expected: 300+, not ~20
  
  2. SELECT interruption_rate FROM spot_advisor_rates 
     WHERE instance_type = 't4g.micro' AND region = 'ap-south-1';
     Expected: 25, not 5
  
  3. redis-cli KEYS "spot_price:ap-south-1:*" | wc -l
     Expected: 1000+, not ~60
  
  4. SELECT COUNT(*) FROM instance_catalog;
     Expected: 400+
  
  5. Parse global_pool_cache:ap-south-1 from Redis and count entries.
     Expected: 700+

ML pipeline verification:
  6. Check logs after one rebalancing cycle for:
     "Pool audit:" line showing raw_pool_count and eligible_count.
     raw must be 1000+, eligible must be 100+.
  
  7. Check logs for any "unknown_category" drops.
     Expected: zero after category_mapping.json update.
  
  8. Check ml_tier_stats in pool audit.
     tier2 and tier3 must both be > 0 (proving new families are scored).

Scoring verification:
  9. Compare score of pool with <5% interruption vs >15% interruption.
     With BALANCED profile, difference must be > 0.2.
     If difference < 0.05, normalization is still broken.
  
  10. Check that r5.xlarge is eliminated for t3.medium source.
      r5.xlarge spot ($0.0756) > t3.medium OD ($0.0464) → must not appear.

Savings verification:
  11. After one completed rebalancing action:
      SELECT estimated_savings_mo, realized_savings_mo, savings_gap_hr
      FROM rebalancing_actions ORDER BY completed_at DESC LIMIT 1;
      Both columns must be populated.
      If fallback occurred: realized != estimated, savings_gap > 0.
  
  12. GET /clusters/{id}/savings
      Response must show realized_savings_mo not estimated.
      baseline_monthly_cost must match ClusterBaseline record.

Frontend verification:
  13. Open Market View.
      Must show pagination controls.
      Total pool count must be 100+.
      r5.xlarge must not appear in list.
      t4g.micro must show >20% interruption if present.
  
  14. Both savings columns must be visible:
      "Pool Saving" and "Your Saving" as separate columns.
  
  15. Pool audit panel must show funnel breakdown
      with raw count near 1170 and eligible near 100+.
```

---

## Execution Order for Claude Code

```
Execute blocks in this exact order:

1  → Block 1  (scraper fix — data foundation)
2  → Block 2  (pricing service — data foundation)
3  → Block 3  (instance catalog — data foundation)
4  → Block 4  (cache builder — depends on 1, 2, 3)
5  → Block 5  (category_mapping.json — ML foundation)
6  → Block 13 (ClusterBaseline model — savings foundation)
7  → Block 14 (RebalancingAction columns — savings foundation)
8  → Block 8  (WorkloadInspector extensions — pipeline dependency)
9  → Block 6  (capacity validator — depends on 8)
10 → Block 7  (architecture filter — depends on 8)
11 → Block 10 (AZ interruption estimation — depends on 1, 2)
12 → Block 9  (ML scoring tiers — depends on 5)
13 → Block 11 (rejection audit logging — depends on 6, 7, 9, 10, 11, 12)
14 → Block 12 (scoring formula — depends on all pipeline blocks)
15 → Block 18 (remove pool caps — depends on 12)
16 → Block 15 (savings calculator — depends on 13, 14)
17 → Block 16 (API endpoints — depends on all backend blocks)
18 → Block 17 (frontend — depends on 17)
19 → Block 19 (verification — run last)

After each block:
  Run py_compile or equivalent syntax check.
  Check for import errors.
  Do not proceed to next block if current block has errors.
```