Here's the complete implementation plan.

---

## Pre-Implementation: Understand Current State

Before writing a single line, audit these files and answer these questions:

```
Files to read first:
  ml_model/decision_engine/pipeline.py
  ml_model/decision_engine/06_capacity_validator.py
  ml_model/decision_engine/08_template_filter.py
  ml_model/model/category_mapping.json
  backend/core/decision_engine.py
  backend/services/workload_inspector.py
  backend/services/substitute_manager.py
  backend/scrapers/spot_advisor_scraper.py
  backend/services/aws_pricing_service.py
  backend/workers/tasks/cache_builder.py

Questions to answer before starting:
  1. What is the current pool count in Redis global_pool_cache?
  2. How many instance types are in category_mapping.json right now?
  3. How many rows in spot_advisor_rates table?
  4. Is WorkloadInspector classification running BEFORE ML pipeline?
  5. Where exactly is the [:10] or similar cap in the code?
  6. What does describe_spot_price_history call look like currently?
```

---

## Phase 1 — Fix the Data Ingestion (The Root Cause)

**Priority: Do this first. Everything else depends on having correct data.**

---

### Task 1.1 — Fix Spot Advisor Scraper

**File:** `backend/scrapers/spot_advisor_scraper.py`

**What to change:**

```
Current behavior:
  - Iterates only over instance types already in DB
  - Uses ttl_hours=12 (already fixed to 0.25 in session 1)
  - Hashes entire blob — skips writes if hash matches
  - OS type may be overwriting Linux with Windows rates
  - KeyError defaults to 5 not None

New behavior:
  1. Download full JSON from:
     spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json

  2. For each region in the JSON:
     For each instance_type under Linux key:
       Extract r value (interruption index)
       Extract s value (savings vs OD)
       
       interruption_map = {
         0: 5,    # <5%
         1: 10,   # 5-10%
         2: 15,   # 10-15%
         3: 20,   # 15-20%
         4: 25,   # >20%
       }
       
       If r not in map: store None (not 5, not 0)
       If instance_type missing: store None

  3. Write per-region hash:
     spot:advisor:hash:{region} — skip region if unchanged
     Not a global hash — per-region so one region update
     doesn't get blocked by unchanged other regions

  4. Always write timestamp regardless of hash:
     spot:advisor:last_scraped:{region} = utcnow()

  5. Upsert ALL records to spot_advisor_rates table
     Do not filter by existing DB records

  6. OS must be hardcoded to Linux — never loop over OS types

Expected result:
  spot_advisor_rates table goes from ~20 rows to 400+ rows per region
```

---

### Task 1.2 — Fix AWS Pricing Service

**File:** `backend/services/aws_pricing_service.py`

**What to change:**

```
Current behavior:
  describe_spot_price_history called with hardcoded InstanceTypes list
  Only fetches pricing for ~20 known types
  May only query one AZ

New behavior:
  1. Call describe_spot_price_history with NO InstanceTypes filter
     Let AWS return all available spot types
     Use Boto3 paginator — response can be thousands of records

  2. Filter by:
     AvailabilityZone: all AZs in the region
     ProductDescription: Linux/UNIX only
     StartTime: last 2 hours (get recent prices)

  3. For each record returned:
     pool_key = region:az:instance_type
     Store: spot_price, az, instance_type, timestamp

  4. Cache in Redis:
     spot_price:{region}:{az}:{instance_type} TTL=3600s

  5. Also fetch OD pricing for all types from AWS Pricing API
     Cache: od_price:{region}:{instance_type} TTL=86400s

Expected result:
  Pricing data for 400+ instance types across all AZs
  Not just the 20 currently hardcoded
```

---

### Task 1.3 — Fix Instance Catalog

**File:** `backend/models/instance_catalog.py` or wherever instance specs are stored

**What to change:**

```
Current behavior:
  Hardcoded dict of ~20-30 instance types with vcpu/memory

New behavior:
  1. Call describe_instance_types API with no filters
     Returns full AWS catalog — 500+ instance types
     Paginate the response

  2. For each instance type extract:
     vcpu count
     memory_mib → convert to GB
     architecture (x86_64, arm64)
     supported_usage_classes (spot, on-demand)
     instance_storage (for local NVMe detection)
     gpu_info (if any)
     
  3. Store in DB: instance_catalog table
     upsert on instance_type key

  4. Cache in Redis:
     instance_spec:{instance_type} TTL=86400s

  5. Run this on startup and refresh daily via Celery beat

Expected result:
  Full instance catalog covering all current AWS types
  including m7i, m7g, c7i, c7g, r7i, r7g, m6a, c6a, r6a etc.
```

---

### Task 1.4 — Fix Cache Builder Pool Universe

**File:** `backend/workers/tasks/cache_builder.py`

**What to change:**

```
Current behavior:
  Builds pool cache from small hardcoded instance type list
  Likely no AZ expansion step

New behavior:
  1. Load ALL instance types from instance_catalog table
     (now 400+ after Task 1.3)

  2. Load ALL AZs for the region:
     describe_availability_zones() → [ap-south-1a, 1b, 1c]

  3. Cross-product:
     for instance_type in all_types:
       for az in all_azs:
         pool_key = f"{region}:{az}:{instance_type}"

  4. For each pool_key:
     spot_price = get from Redis spot_price:{region}:{az}:{instance_type}
     If no spot price → instance not available as spot in that AZ → skip
     od_price = get from Redis od_price:{region}:{instance_type}
     interruption_rate = get from spot_advisor_rates table
     vcpu, memory = get from instance_catalog
     architecture = get from instance_catalog
     savings_pct = (od_price - spot_price) / od_price × 100

  5. If savings_pct <= 0: skip (spot costs more than OD)

  6. Store all valid pools in Redis:
     global_pool_cache:{region} = serialized list of all pools
     TTL = 3600s (rebuilt hourly)

  7. Log summary:
     "Built pool cache for ap-south-1:
      raw_cross_product: 1170
      no_spot_price: 270 (not available as spot)
      negative_savings: 50
      final_pool_count: 850"

Expected result:
  global_pool_cache goes from 7 entries to 800+ entries
```

---

## Phase 2 — Fix the ML Pipeline

**Do after Phase 1. ML fixes are useless if the data isn't there.**

---

### Task 2.1 — Fix category_mapping.json

**File:** `ml_model/model/category_mapping.json`

**What to add:**

```
Current gen families likely missing:
  m7i, m7g, m7a     → proxy: m6i, m6g, m6a
  c7i, c7g, c7a     → proxy: c6i, c6g, c6a
  r7i, r7g, r7a     → proxy: r6i, r6g, r6a
  m6a               → proxy: m6i
  c6a               → proxy: c6i
  r6a               → proxy: r6i
  i4i, i4g          → proxy: i3, i3en
  hpc7g, hpc6id     → proxy: c6g, c6i
  
Format for each entry:
  {
    "family": "m7i",
    "tier": 2,
    "proxy_family": "m6i",
    "confidence_penalty": 0.90,
    "architecture": "amd64",
    "generation": 7
  }

Add ALL families with tier assignment:
  Tier 1: families the model was trained on
  Tier 2: new gen with known proxy
  Tier 3: completely novel families (use size-class average)
```

---

### Task 2.2 — Fix Capacity Validator

**File:** `ml_model/decision_engine/06_capacity_validator.py`

**What to change:**

```
Current behavior:
  min_vcpu   = source_node.vcpu_total
  min_memory = source_node.memory_gb_total

New behavior:
  1. Load per-node pod resource profile:
     pod_vcpu_requested   = sum of CPU requests for all pods on node
     pod_memory_requested = sum of memory requests for all pods on node
     
     Source: Kubernetes metrics API or node resource profile cache
     Cache key: node_resource_profile:{node_id} TTL=300s

  2. Apply configurable headroom:
     headroom_pct = cluster_config.get('replacement_headroom_pct', 10)
     
     min_vcpu_required   = pod_vcpu_requested × (1 + headroom_pct/100)
     min_memory_required = pod_memory_requested × (1 + headroom_pct/100)

  3. Round up to next standard increment:
     vcpu: round up to nearest whole number
     memory: round up to nearest standard tier (2, 4, 8, 16, 32...)

  4. Gate:
     if pool.vcpu < min_vcpu_required: REJECT, reason="too_small_vcpu"
     if pool.memory < min_memory_required: REJECT, reason="too_small_memory"

  5. Log rejection reason with counts

  6. Fallback: if pod_vcpu_requested is None or 0
     (metrics not available) → fall back to source_node.vcpu_total
     Log warning: "No pod request data, using node total as floor"

Expected result:
  A node at 40% utilization opens up smaller, cheaper replacement options
  Stage 1 drops from 600 pools rejected to ~400 pools rejected
  ~200 additional pools become eligible
```

---

### Task 2.3 — Fix Architecture Filter

**File:** `ml_model/decision_engine/08_template_filter.py`

**What to change:**

```
Current behavior:
  Hardcoded: only amd64 allowed

New behavior:
  1. Check per-node arch compatibility flag:
     arm64_eligible = node_arch_compatibility:{node_id}
     
     This is computed by WorkloadInspector (Task 2.4)
     Cache key: node_arch_compat:{node_id} TTL=3600s

  2. If arm64_eligible = True:
     Allow pools from all architecture families
     Include: t4g, m6g, m7g, c6g, c7g, r6g, r7g families

  3. If arm64_eligible = False:
     Drop all arm64 pools
     Reject reason: "architecture_incompatible_arm64"

  4. Always drop regardless of arm64:
     GPU instances (p*, g*) unless node has GPU pods
     Inferentia (inf*) unless node has inf workloads
     Trainium (trn*) unless node has trn workloads
     Mac instances (mac*) always
     Bare metal (*.metal) unless explicitly enabled
     
  5. Log each rejection with reason
```

---

### Task 2.4 — Extend WorkloadInspector

**File:** `backend/services/workload_inspector.py`

**What to add:**

```
New method: compute_node_arch_compatibility(node_id)

Logic:
  1. Get all pods running on the node
  
  2. For each pod, for each container:
     Check image manifest for supported architectures
     
     Method A (preferred): 
       Call container registry API to get manifest
       Check manifest.platforms for linux/arm64 entry
     
     Method B (fallback):
       Check pod spec nodeSelector for kubernetes.io/arch
       Check pod spec nodeAffinity for architecture requirement
       If explicitly requires amd64 → not arm64 eligible
     
     Method C (last resort):
       Check image name patterns
       Known amd64-only bases: windowsservercore, nanoserver
       Known multi-arch: alpine, ubuntu, debian, distroless

  3. arm64_eligible = True only if ALL containers support arm64
     One amd64-only container makes the whole node amd64-only

  4. Cache result:
     node_arch_compat:{node_id} = {arm64: true/false}
     TTL = 3600s

New method: compute_node_resource_profile(node_id)

Logic:
  1. Query Kubernetes for all pods on the node
  
  2. Sum resource requests:
     total_cpu_requested = sum(pod.spec.containers[*].resources.requests.cpu)
     total_mem_requested = sum(pod.spec.containers[*].resources.requests.memory)
  
  3. Convert to standard units:
     cpu → float (millicores to cores: 500m = 0.5)
     memory → GB (Mi to GB: 512Mi = 0.5GB)
  
  4. Cache result:
     node_resource_profile:{node_id} = {
       vcpu_requested: 1.2,
       memory_gb_requested: 3.2,
       pod_count: 8,
       computed_at: timestamp
     }
     TTL = 300s (5 min — refresh as pods change)

Verify STATELESS_ELIGIBLE check runs BEFORE ML pipeline:
  In auto_rebalancer.py scan loop:
    classification = workload_inspector.classify(node)
    if classification != STATELESS_ELIGIBLE: skip
    Then → ML pipeline
  
  If this order is wrong, fix it first before anything else
```

---

### Task 2.5 — Fix ML Scoring Tiers

**File:** `backend/core/decision_engine.py`

**What to change:**

```
Current behavior:
  Unknown instance family → exception → pool dropped

New behavior:
  def get_ml_score(pool, category_mapping):
    family = extract_family(pool.instance_type)
    # e.g., m7i.large → family = m7i
    
    if family in category_mapping['tier1']:
      # Full ONNX prediction
      score = onnx_model.predict(pool_features)
      tier = 1
      confidence = 1.0
      
    elif family in category_mapping['tier2']:
      # Proxy family prediction
      proxy_family = category_mapping['tier2'][family]['proxy']
      proxy_features = build_proxy_features(pool, proxy_family)
      score = onnx_model.predict(proxy_features)
      tier = 2
      confidence = 0.90
      
    else:
      # Size-class average
      size_class = extract_size_class(pool.instance_type)
      # e.g., m7i.2xlarge → size_class = 2xlarge
      score = get_size_class_average(size_class, category_mapping)
      tier = 3
      confidence = 0.75
    
    return score × confidence, tier

  Never raise exception for unknown family.
  Never return None for unknown family.
  Always return a score with appropriate confidence penalty.
  
  Log tier assignment:
    ml_tier_stats:{cluster_id}:
      tier1_count: X
      tier2_count: Y  
      tier3_count: Z
```

---

### Task 2.6 — Add Rejection Audit Logging

**File:** `ml_model/decision_engine/pipeline.py`

**What to add:**

```
def filter_pools(raw_pools, node_profile):
  rejection_reasons = {
    "no_spot_price_in_az":         0,
    "too_small_vcpu":              0,
    "too_small_memory":            0,
    "architecture_incompatible":   0,
    "interruption_above_ceiling":  0,
    "blacklisted":                 0,
    "dry_run_fail":                0,
    "spot_costs_more_than_od":     0,
  }
  
  ml_tier_stats = {
    "tier1_known":   0,
    "tier2_proxy":   0,
    "tier3_unknown": 0,
  }
  
  eligible = []
  
  for pool in raw_pools:
    # Gate 1
    if pool.spot_price is None:
      rejection_reasons["no_spot_price_in_az"] += 1
      continue
    
    # Gate 2
    if pool.vcpu < node_profile.min_vcpu_required:
      rejection_reasons["too_small_vcpu"] += 1
      continue
    
    # Gate 3  
    if pool.memory_gb < node_profile.min_memory_required:
      rejection_reasons["too_small_memory"] += 1
      continue
    
    # Gate 4
    if not arch_compatible(pool, node_profile):
      rejection_reasons["architecture_incompatible"] += 1
      continue
    
    # Gate 5
    if pool.interruption_rate > node_profile.risk_ceiling:
      rejection_reasons["interruption_above_ceiling"] += 1
      continue
    
    # Gate 6
    if is_blacklisted(pool.pool_key):
      rejection_reasons["blacklisted"] += 1
      continue
    
    # Gate 7
    if dry_run_failed(pool.pool_key):
      rejection_reasons["dry_run_fail"] += 1
      continue
    
    # Gate 8
    if pool.spot_price >= node_profile.source_od_price:
      rejection_reasons["spot_costs_more_than_od"] += 1
      continue
    
    # ML Scoring — no drops here
    score, tier = get_ml_score(pool, category_mapping)
    ml_tier_stats[f"tier{tier}_{'known' if tier==1 else 'proxy' if tier==2 else 'unknown'}"] += 1
    pool.ml_score = score
    pool.ml_tier = tier
    eligible.append(pool)
  
  # Log full audit
  logger.info(
    f"Pool eligibility audit | node={node_profile.node_id} | "
    f"raw={len(raw_pools)} | eligible={len(eligible)} | "
    f"rejected={rejection_reasons} | ml_tiers={ml_tier_stats}"
  )
  
  # Store in Redis for API/UI consumption
  redis_client.setex(
    f"pool_audit:{node_profile.cluster_id}:{node_profile.node_id}",
    300,
    json.dumps({
      "raw_pool_count": len(raw_pools),
      "eligible_count": len(eligible),
      "rejection_reasons": rejection_reasons,
      "ml_tier_stats": ml_tier_stats,
      "computed_at": datetime.utcnow().isoformat()
    })
  )
  
  return eligible
```

---

### Task 2.7 — Add AZ Interruption Estimation

**File:** `backend/services/pool_ranking_service.py`

**What to add:**

```
def estimate_az_interruption(instance_type, az, region):
  
  # Layer 1: AWS region-level rate (base)
  region_rate = get_spot_advisor_rate(region, instance_type)
  if region_rate is None:
    return None  # unknown → eliminated by Gate 5
  
  # Layer 2: AZ price adjustment
  az_spot_price    = get_spot_price(region, az, instance_type)
  region_avg_price = get_region_avg_spot_price(region, instance_type)
  
  if az_spot_price and region_avg_price and region_avg_price > 0:
    price_ratio = az_spot_price / region_avg_price
    
    if price_ratio > 1.20:
      az_adjustment = 1    # +1 tier (tighter capacity)
    elif price_ratio > 1.10:
      az_adjustment = 0.5  # +0.5 tier
    else:
      az_adjustment = 0    # no adjustment
  else:
    az_adjustment = 0
  
  # Layer 3: Own historical data
  history_key = f"interruption_history:{region}:{az}:{instance_type}"
  history_data = redis_client.get(history_key)
  
  if history_data:
    history = json.loads(history_data)
    own_rate = history['rate']
    event_count = history['count']
    history_weight = min(event_count / 100, 0.5)
  else:
    own_rate = region_rate
    history_weight = 0
  
  # Combine all three layers
  aws_weight = 1 - history_weight
  combined_rate = (
    (region_rate + az_adjustment) × aws_weight +
    own_rate × history_weight
  )
  
  return min(combined_rate, 25)  # cap at >20% tier value

def record_interruption_event(region, az, instance_type):
  # Called by termination_monitor when a spot interruption occurs
  history_key = f"interruption_history:{region}:{az}:{instance_type}"
  history = json.loads(redis_client.get(history_key) or '{"rate": 0, "count": 0}')
  
  history['count'] += 1
  # Exponential moving average
  history['rate'] = (history['rate'] × 0.9) + (25 × 0.1)
  # 25 = max interruption tier value, weighted in on each event
  
  redis_client.setex(history_key, 86400 × 7, json.dumps(history))
  # Keep 7 days of history
```

---

## Phase 3 — Fix the Scoring and Ranking

---

### Task 3.1 — Implement Weighted Scoring Formula

**File:** `backend/core/decision_engine.py`

**What to change:**

```
Profile weight table:
  COST_FIRST:   {savings: 0.60, risk: 0.20, ml: 0.20}
  BALANCED:     {savings: 0.40, risk: 0.40, ml: 0.20}
  NO_DOWNTIME:  {savings: 0.20, risk: 0.60, ml: 0.20}

Scoring:
  savings_score = (source_od_price - spot_price) / source_od_price
  
  safety_score  = 1 - (az_interruption_rate / 25)
                  # normalize to 0-1 where 25 = max rate
  
  final_score   = (W_savings × savings_score)
                + (W_risk    × safety_score)
                + (W_ml      × ml_score)

Sort all eligible pools by final_score DESC.
No cap on number of pools returned.
```

---

### Task 3.2 — Remove All Pool Caps

**Files:** `backend/services/substitute_manager.py`, `backend/core/decision_engine.py`

**What to change:**

```
Search for any of these patterns and remove:
  [:10]
  [:6]
  limit=10
  top_n=10
  max_candidates=10
  ranked[:MAX_POOLS]

Replace with:
  Full list — no slice
  Pagination applied only at API response layer
  Execution engine gets full list

Keep:
  max_instance_type_attempts in auto_rebalancer
  (this limits LAUNCH ATTEMPTS not pool universe)
  Default 6 attempts is fine
  Pool universe can be 400+ but we only try 6 before giving up
```

---

## Phase 4 — Fix the API and Frontend

---

### Task 4.1 — Market View API

**File:** Wherever market view endpoint lives

```
GET /clusters/{cluster_id}/market-view
  ?page=1
  &page_size=20
  &sort_by=final_score
  &sort_order=desc

Logic:
  1. Load ClusterBaseline for source node context
  2. Load node_resource_profile for primary OD node
  3. Run full pipeline (Phase 2 funnel)
  4. Return paginated slice of full ranked list
  5. Include pagination metadata and rejection audit

Response includes:
  source_node context
  pagination: {page, page_size, total, total_pages}
  gates_eliminated: rejection_reasons counts
  pools: paginated slice
```

---

### Task 4.2 — Node Alternatives API

```
GET /clusters/{cluster_id}/nodes/{node_id}/alternatives
  ?page=1&page_size=20

Logic:
  1. Load specific node's resource profile
  2. Run pipeline for that specific node
  3. Return paginated alternatives specific to that node's needs

Response includes:
  node resource profile (vcpu_requested, memory_requested)
  coverage_status: COVERED/AT_RISK/STRANDED
  alternative_count
  paginated pool list
```

---

### Task 4.3 — Pool Audit API

```
GET /clusters/{cluster_id}/nodes/{node_id}/pool-audit

Returns:
  raw_pool_count: 1170
  eligible_count: 124
  rejection_reasons: {
    no_spot_price_in_az: 270,
    too_small_vcpu: 350,
    too_small_memory: 80,
    architecture_incompatible: 200,
    interruption_above_ceiling: 30,
    blacklisted: 5,
    spot_costs_more_than_od: 111,
  }
  ml_tier_stats: {
    tier1_known: 89,
    tier2_proxy: 30,
    tier3_unknown: 5
  }
  computed_at: timestamp
```

---

### Task 4.4 — Frontend Cluster Impact View

```
Add funnel visualization panel:

POOL ELIGIBILITY FUNNEL — Node i-abc123 (t3.medium)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Raw AWS Universe:        1,170 pools
  ↓ No spot price in AZ:  -270  (not offered as spot)
  ↓ Too small for pods:   -430  (below pod request floor)
  ↓ Architecture:         -200  (amd64 only workload)
  ↓ Interruption ceiling: - 30  (above BALANCED 20% ceiling)
  ↓ Blacklisted:          -  5  (recently failed)
  ↓ Spot costs more OD:   -111  (no savings)
                         ─────
Final eligible:            124 pools  ✅

ML Scoring:
  Tier 1 (full model):    89 pools
  Tier 2 (proxy):         30 pools
  Tier 3 (size average):   5 pools

Top 3 alternatives:
  1. t3a.medium  <5%  70% saving  score 0.824
  2. c5.large    <5%  52% saving  score 0.748
  3. m5.large    <5%  44% saving  score 0.708
```

---

## Implementation Order and Timeline

```
Week 1 — Data Foundation (Phase 1)
  Day 1-2: Task 1.1 — Fix spot advisor scraper
           Verify: spot_advisor_rates goes from 20 to 400+ rows
  Day 2-3: Task 1.2 — Fix pricing service  
           Verify: spot price data for all types in all AZs
  Day 3-4: Task 1.3 — Fix instance catalog
           Verify: instance_catalog has 400+ types with specs
  Day 4-5: Task 1.4 — Fix cache builder
           Verify: global_pool_cache has 800+ entries

Week 2 — ML Pipeline (Phase 2)
  Day 1:   Task 2.1 — Update category_mapping.json
           Verify: all current gen families have tier assignment
  Day 2:   Task 2.2 — Fix capacity validator
           Verify: uses pod requests not node total
  Day 3:   Task 2.3 — Fix architecture filter
           Verify: arm64 pools appear when workload supports it
  Day 4:   Task 2.4 — Extend WorkloadInspector
           Verify: node_arch_compat and node_resource_profile cached correctly
  Day 5:   Task 2.5 — Fix ML scoring tiers
           Verify: no pools dropped for unknown family
           Verify: tier2 and tier3 pools get scores not exceptions
  Day 5:   Task 2.6 — Add rejection audit logging
           Verify: logs show full funnel breakdown
  Day 6:   Task 2.7 — AZ interruption estimation
           Verify: each pool_key has az-specific rate not just region rate

Week 3 — Scoring, API, Frontend (Phases 3 + 4)
  Day 1:   Task 3.1 — Weighted scoring formula
           Verify: scores change correctly when profile changes
  Day 2:   Task 3.2 — Remove all pool caps
           Verify: no [:10] or similar slices remain
  Day 3:   Task 4.1 + 4.2 — Market View and Node Alternatives APIs
           Verify: pagination works, returns correct pool counts
  Day 4:   Task 4.3 — Pool Audit API
           Verify: funnel breakdown accessible via API
  Day 5:   Task 4.4 — Frontend Cluster Impact View
           Verify: funnel visualization renders correctly

Week 4 — Verification
  Day 1-2: Run integration tests
           Verify pool count goes from 7 to 100+
           Verify t4g.micro no longer appears with wrong interruption rate
           Verify Market View shows correct savings vs source OD
  Day 3-4: Load test
           Verify pipeline handles 1170 pools without performance issues
  Day 5:   Deploy to staging
           Monitor logs for rejection audit output
           Confirm pool counts match expectations
```

---

## Verification Checklist

After all tasks complete, verify these specific things:

```
Data layer:
  □ spot_advisor_rates table has 400+ rows for ap-south-1
  □ global_pool_cache:{region} has 800+ entries
  □ spot_price:{region}:{az}:{type} exists for all combinations
  □ instance_catalog has 400+ types

ML pipeline:
  □ category_mapping.json includes m7i, m7g, c7i, c7g, r7i, r7g
  □ No pool dropped with reason "unknown_category"
  □ Tier 2 and Tier 3 pools appear in eligible list
  □ Capacity floor uses pod requests not node total

Funnel output:
  □ Pool audit log shows 1170 raw → 100+ eligible
  □ t4g.micro shows >20% interruption not <5%
  □ r5.xlarge eliminated by savings gate (costs more than t3.medium OD)
  □ Eligible pools include both amd64 and arm64 if workload supports it

API and frontend:
  □ Market View shows 100+ pools paginated
  □ Node-Specific View shows per-node alternatives
  □ Cluster Impact View shows funnel breakdown
  □ Source node context shown: t3.medium $0.0464/hr baseline
  □ Savings shown vs baseline not floating OD estimate
```