# Pool Data Architecture — Complete Reference

> Generated: 9 April 2026  
> Updated: 10 April 2026 (Gap 1–4 fixes applied)  
> Covers: Where pool data comes from, the global ranking pipeline, safe-zone counts before cluster-specific filters, and how pool data flows to the UI

---

## 1. Pool Data — End-to-End Overview

```mermaid
flowchart TB
    subgraph AWS["AWS Data Sources"]
        API1["describe_spot_price_history()<br/>boto3 EC2 client<br/>Every 10 min, 6h lookback window"]
        API1B["DescribeInstanceTypeOfferings<br/>(LocationType=availability-zone)<br/>Authoritative universe discovery<br/>Runs after each price fetch"]
        API2["Spot Advisor S3 JSON<br/>spot-bid-advisor.s3.amazonaws.com<br/>Daily 2:00 AM UTC"]
        API3["DescribeInstanceTypeOfferings<br/>(Step 9 capacity check)<br/>On-demand (30-min cache)"]
        API4["EC2 DryRun (RunInstances)<br/>Actual capacity validation<br/>Budget: min(200, clusters×2)/hr"]
    end

    subgraph Storage["Storage Layer"]
        DB1["SpotPriceHistory table<br/>24h rolling retention"]
        DB2["SpotAdvisorData table<br/>Permanent"]
        DB3["OnDemandPricing table<br/>Daily refresh"]
        R1["Redis: spot_price:{region}:{az}:{type}<br/>TTL 10 min (real) / 1h (estimated)<br/>⚡ Estimated keys marked is_estimated=true"]
        R2["Redis: spot_advisor:{region}:{type}:Linux<br/>TTL 25h"]
        R3["Redis: global_pool_rankings:{region}<br/>TTL 65 min — Top 1500 pools (all AZ variants)"]
        R4["Redis: risky_pools:{region}<br/>Global blacklist set"]
        R5["Redis: blacklist_failures:{pool_key}<br/>TTL 24h — repeat-offender counter"]
        R6["Redis: capacity:{type}:{az}<br/>TTL 15 min — DescribeOfferings cache"]
        R7["Redis: instance_type_offerings:{region}:count<br/>TTL 25h — offerings universe telemetry"]
    end

    subgraph Pipeline["Global Ranking Pipeline (pool_ranking_service.py)"]
        P1["Step 3: SA Annotation (Gap 3)<br/>Attaches SA rank as ONNX feature<br/>ALL pools pass through (no gate)"]
        P2["Step 4: Blacklist Check<br/>Global risky_pools:{region}"]
        P3["Step 6: Price Fetch<br/>Spot + OD prices per pool"]
        P4["Step 7: ML Scoring<br/>ONNX + 4-signal blend"]
        P5["Hard Gate 0.35 REJECT<br/>Safety Net 0.50 REJECT"]
        P6["Cache Top 1500 (all AZ variants)<br/>global_pool_rankings:{region}<br/>(Gap 4: no instance-type dedup)"]
    end

    subgraph ClusterFilter["Cluster-Specific Tier 2 Filters (_apply_client_filters)"]
        F1["Architecture (amd64/arm64)"]
        F2["vCPU + Memory range"]
        F3["Allowed families & sizes"]
        F4["Allowed AZs"]
        F5["Excluded instance types"]
        F6["Per-cluster blacklist (failure_count ≥ 3)"]
        F7["Price gate (spot < OD)"]
        F8["Pod-request floor (10% headroom)"]
        P7["Step 9: DryRun capacity validation<br/>on top 10 results"]
    end

    subgraph Consumers["Consumers"]
        C1["Auto-Rebalancer (S2S target selection)"]
        C2["Node Recommendations API"]
        C3["Karpenter NodePool sync (top 10 types)"]
        C4["Substitute Manager (ITN replacement)"]
        C5["Decision Engine V3 (05_risk_filter.py)"]
        C6["Frontend: Pool Rankings UI"]
    end

    API1 --> DB1 --> P3
    API1 --> R1 --> P3
    API1B --> R1
    API2 --> DB2 --> P1
    API2 --> R2 --> P1
    API3 --> R6 --> P2
    DB3 --> P3
    R4 --> P2
    R5 --> F6

    P1 --> P2 --> P3 --> P4 --> P5 --> P6
    P6 --> ClusterFilter
    ClusterFilter --> P7
    P7 --> Consumers
```

---

## 2. AWS Data Sources — Detailed

```mermaid
flowchart LR
    subgraph PriceCollection["Spot Price Collection (pricing_collector.py)"]
        direction TB
        T1["Celery Beat: every 10 min"]
        Code1["ec2_client.describe_spot_price_history(<br/>  StartTime = now - 6h,  (Gap 2 fix: was 1h)<br/>  ProductDescriptions=['Linux/UNIX'],<br/>  MaxResults = 1000,<br/>  NextToken = ...   ← paginated<br/>)<br/><br/>Followed by DescribeInstanceTypeOfferings<br/>(Gap 1: authoritative universe backfill)<br/>Writes estimated spot_price keys for types<br/>missing from price history (OD × 0.35, is_estimated=true)<br/><br/>Family-based OD estimator fallback:<br/>New types get price estimates via<br/>_estimate_od_price() when no cached OD price"]
        Store1["→ SpotPriceHistory table (24h retention)<br/>→ Redis spot_price:{region}:{az}:{type} (TTL=600s)"]
        T1 --> Code1 --> Store1
    end

    subgraph SACollection["Spot Advisor Collection (spot_advisor_scraper.py)"]
        direction TB
        T2["Celery Beat: Daily 2:00 AM UTC"]
        Code2["GET https://spot-bid-advisor.s3.amazonaws.com/<br/>spot-advisor-data.json<br/><br/>Parses interruption_index (0–4):<br/>0 = <5%, 1 = 5–10%, 2 = 10–15%,<br/>3 = 15–20%, 4 = >20%<br/>Missing 'r' → defaults to 4 (worst)"]
        Store2["→ SpotAdvisorData table (permanent)<br/>→ SpotAdvisorRate table (audit trail)<br/>→ Redis spot_advisor:{region}:{type}:Linux (TTL=90000s=25h)<br/>→ Redis spot:advisor:hash:{region} (SHA256 dedup)<br/>→ Redis spot:advisor:last_scraped (staleness tracking)"]
        T2 --> Code2 --> Store2
        Stale["Staleness checks:<br/>> 6h WARNING<br/>> 24h auto-retrigger"]
        Store2 --> Stale
    end

    subgraph ODCollection["On-Demand Price Collection"]
        direction TB
        T3["Daily 1:00 AM UTC"]
        Code3["AWS Price List API<br/>or pricing scraper fallback dict"]
        Store3["→ OnDemandPricing table<br/>→ Redis od_price:{region}:{type}"]
        T3 --> Code3 --> Store3
    end
```

---

## 3. Total Pool Universe — Before Any Filter

```mermaid
flowchart TD
    subgraph Universe["Pool Universe (ap-south-1 example)"]
        Total["~600+ total pools<br/>≈ 200+ instance types × 3 AZs<br/>(ap-south-1a, ap-south-1b, ap-south-1c)<br/><br/>Gap 1 fix: DescribeInstanceTypeOfferings<br/>discovers ALL spot-eligible types per AZ,<br/>not just those with recent price history"]
        
        Examples["Example pools:<br/>• t3.nano:ap-south-1a<br/>• t3.nano:ap-south-1b<br/>• t3.nano:ap-south-1c<br/>• m5.large:ap-south-1a<br/>• m5.large:ap-south-1b<br/>• c5.xlarge:ap-south-1a<br/>• ... 594+ more"]
    end

    Total --> Examples

    note1["Each 'pool' = one unique combination of<br/>(instance_type, availability_zone, region)<br/><br/>Universe now includes types with estimated<br/>spot prices (OD × 0.35) from offerings backfill"]
```

---

## 4. Global Pipeline — Step by Step With Pool Counts

```mermaid
flowchart TD
    Start["ALL POOLS IN REGION<br/>~600+ pools<br/>(200+ types × 3 AZs)<br/>(Gap 1: offerings backfill expands universe)"]

    subgraph Step3["Step 3: Spot Advisor Annotation (Gap 3 fix)"]
        direction TB
        SA0["Single pass — max_rank=4<br/>ALL pools pass through<br/>SA rank attached as ONNX feature<br/>(no longer a hard gate)<br/><br/>Result: all ~600+ pools continue"]
    end

    Start --> Step3

    subgraph Step4["Step 4: Global Blacklist Check"]
        BL["Reject pools in risky_pools:{region}<br/>Failed DryRun OR failure_count ≥ 3<br/><br/>Typical removal: 5–30 pools"]
    end

    Step3 --> Step4

    subgraph Step6["Step 6: Price Fetch"]
        PF["Load spot price + OD price for each pool<br/>Source priority:<br/>1. Redis spot_price:{region}:{az}:{type}<br/>2. SpotPriceHistory DB (latest)<br/>3. Fallback hardcoded dict<br/><br/>Pool dropped if no valid price found"]
    end

    Step4 --> Step6

    subgraph Step7["Step 7: ML Scoring (ONNX + 4-Signal Blend)"]
        ML1["Build 45 features per pool<br/>(ml_feature_service.py)"]
        ML2["Run classifier_6.onnx<br/>Output: risk_probability 0.0–1.0"]
        ML3["4-Signal blend:<br/>0.40 × ONNX + 0.35 × PricePressure<br/>+ 0.25 × SpotAdvisor<br/>+ EMA injection (max 40%)"]
        ML4["HARD GATE → REJECT if blended risk > 0.35<br/>(optimal_threshold from risk_threshold.json)"]
        ML5["SAFETY NET → REJECT if risk > 0.50<br/>(absolute hard cutoff)"]
        CB["⚡ Circuit Breaker:<br/>If ONNX fails > 5 times in 10 min<br/>ascpai:ml_fail_count > 5<br/>ALL pools get risk = 0.20 (fallback)"]
        ML1 --> ML2 --> ML3 --> ML4 --> ML5
        CB -.->|"OPEN"| ML3
    end

    Step6 --> Step7

    subgraph Counts["Typical Pool Counts After ML Gates"]
        C1["After ONNX hard gate (≤0.35)<br/>Typical: 50–200 pools (varies with market)"]
        C2["After safety net gate (≤0.50)<br/>Typical: 35–150 pools<br/>(fallback mode: all pools pass — risk=0.20 always ≤0.50)"]
        C3["Fallback trigger activated if<br/>< 10 pools survive ONNX gate<br/>→ heuristic scoring replaces ML"]
    end

    Step7 --> Counts

    subgraph Step8["Step 8: Final Ranking & Cache (Gap 4 fix)"]
        R1["Sort by unified ML score (descending)"]
        R2["Retain ALL AZ variants per type<br/>(Gap 4: no instance-type dedup)<br/>m5.large:us-east-1a AND m5.large:us-east-1b both kept"]
        R3["Assign ranks 1, 2, 3..."]
        R4["Cache TOP 1500 to Redis<br/>Key: global_pool_rankings:{region}<br/>TTL: 65 min (3900s)"]
        R1 --> R2 --> R3 --> R4
    end

    Counts --> Step8

    style SA0 fill:#c8e6c9
    style ML4 fill:#ffcdd2
    style ML5 fill:#ffcdd2
    style CB fill:#ffe0b2
```

---

## 5. "Safe Zone" — Exact Numbers Before Cluster Filters

```mermaid
flowchart LR
    subgraph SafeZoneTable["Safe Zone Summary (per region, normal market)"]
        direction TB
        
        Row0["✅ STAGE 0 — Raw pools in universe<br/>~600+ pools (200+ types × 3 AZs)<br/>(Gap 1: offerings backfill expands from ~80 types)"]
        Row1["✅ STAGE 1 — After SA Annotation (Gap 3)<br/>ALL pools pass through (SA is feature, not gate)<br/>~600+ pools unchanged"]
        Row4["✅ STAGE 2 — After Global Blacklist<br/>−5 to −30 pools (failures removed)"]
        Row5["✅ STAGE 3 — After ONNX Hard Gate (≤ 0.35)<br/>~50–200 pools (market-dependent)<br/>⚠️ Fallback if < 10 survive"]
        Row6["✅ STAGE 4 — After Safety Net (≤ 0.50)<br/>~35–150 pools — these are IN THE SAFE ZONE"]
        Row7["📦 GLOBAL CACHE<br/>Top 1500 stored in Redis<br/>(all AZ variants retained — Gap 4)"]

        Row0 --> Row1 --> Row4 --> Row5 --> Row6 --> Row7
    end

    style Row6 fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style Row7 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style Row5 fill:#fff9c4
```

### Safe Zone in Numbers

| Stage | Filter | Pools Remaining | Note |
|-------|--------|----------------|------|
| Raw universe | None (+ offerings backfill) | ~600+ | 200+ types × 3 AZs (Gap 1) |
| After SA Annotation | SA rank attached (Gap 3: no gate) | ~600+ | All pools pass through |
| After Global Blacklist | failure_count ≥ 3 removed | ~580–600 | −5 to −30 |
| After Price Fetch | no-price pools dropped | ~560–590 | Small drop |
| **After ONNX Hard Gate (≤ 0.35)** | **risk > 0.35 rejected** | **~50–200** | **Market-dependent** |
| **After Safety Net (≤ 0.50)** | **risk > 0.50 rejected** | **~35–150** | **IN THE SAFE ZONE** |
| **Final Global Cache** | **Top 1500 cached (all AZ variants)** | **35–150 (or up to 1500)** | **Redis TTL 65 min (Gap 4: no dedup)** |

> **The "safe zone" before any cluster-specific filter = pools with blended risk_probability ≤ 0.35 (or ≤ 0.50 via safety net), not blacklisted, with valid price data. Typically 35–150 pools under normal market conditions.**

---

## 6. Cluster-Specific Filters (Tier 2) — Applied On Top Of Safe Zone

```mermaid
flowchart TD
    GlobalCache["Global Cache<br/>up to 1500 pools (all safe-zone pools)<br/>global_pool_rankings:{region}"]
    
    GlobalCache --> F1

    subgraph ClientFilters["_apply_client_filters() — In-Memory on each API call"]
        direction TB
        
        F1["Filter 1: Architecture<br/>x86_64 ↔ amd64 normalized<br/>arm64 ARM family check"]
        
        F2["Filter 2: vCPU Range<br/>template.vcpu_range (min, max)<br/>+ pod-request floor: max(template_min, pod_vcpu×1.10)"]
        
        F3["Filter 3: Memory Range<br/>template.memory_range (min_gb, max_gb)<br/>+ pod-request floor: ceil(pod_mem_gb × 1.10)"]
        
        F4["Filter 4: Allowed Families<br/>e.g. [m5, c5, r5, m6i, c6i, r6i, m6g, c6g]<br/>None = all families pass"]
        
        F5["Filter 5: Allowed Sizes<br/>e.g. [medium, large, xlarge, 2xlarge, 4xlarge]<br/>None = all sizes pass"]
        
        F6["Filter 6: Allowed AZs<br/>User's geography preference<br/>None = all AZs pass"]
        
        F7["Filter 7: Excluded Instance Types<br/>User blacklist (e.g. m5.metal, c5.24xlarge)<br/>None = nothing excluded"]
        
        F8["Filter 8: Per-Cluster Blacklist<br/>Redis: blacklist_failures:{pool_key} ≥ 3<br/>TTL: 24h — cluster saw 3+ consecutive failures"]
        
        F9["Filter 9: Price Gate<br/>spot_price < od_price required<br/>Pools with no savings dropped"]

        F1 --> F2 --> F3 --> F4 --> F5 --> F6 --> F7 --> F8 --> F9
    end

    subgraph PodFloor["Pod-Request Floor Detail (node_resource_profile:{node_id})"]
        direction LR
        PF1["Redis key: node_resource_profile:{node_id}"]
        PF2["Fields: vcpu_requested, memory_gb_requested,<br/>replacement_headroom_pct (default 10%)"]
        PF3["effective_vcpu_min = max(1, ceil(vcpu_req × 1.10))<br/>effective_mem_min = ceil(mem_gb × 1.10)"]
        PF4["Effect: allows SMALLER replacement<br/>than original node IF pods don't need full size<br/>e.g. t3.large (8GB) → t3.small (2GB)<br/>if pods only request 1.5 GB"]
        PF1 --> PF2 --> PF3 --> PF4
    end

    F2 -.->|"informed by"| PodFloor

    subgraph Step9["Step 9: DryRun Capacity Validation (top 10)"]
        S9A["For top 10 pools that survive cluster filters:<br/>EC2 RunInstances(DryRun=True)<br/>Confirms actual spot capacity available"]
        S9B["Budget: min(200, active_clusters×2) DryRuns per region per hour<br/>Per-cluster cap: 5 DryRuns per call"]
        S9C["Cache: spot:validated:{region}:{type}:{az} TTL=30min<br/>(Gap fix: was 1h, reduced to reduce stale capacity illusion)<br/>Starvation retry: if < 5 validated, re-triggers"]
        S9A --> S9B --> S9C
    end

    F9 --> Step9

    Result["Final Result for this cluster<br/>Typically 5–30 pools<br/>Returned to caller (API, rebalancer, Karpenter)"]
    Step9 --> Result

    style GlobalCache fill:#e3f2fd
    style Result fill:#c8e6c9
```

---

## 7. NodeTemplate — What Controls Cluster-Level Filters

```mermaid
flowchart LR
    subgraph NodeTemplate["NodeTemplate Dataclass (pool_ranking_service.py:44)"]
        direction TB
        NT1["vcpu_range: Tuple[int, int]<br/>e.g. (2, 16)"]
        NT2["memory_range: Tuple[int, int] GB<br/>e.g. (4, 64)"]
        NT3["allowed_families: Optional[List[str]]<br/>e.g. ['m5', 'c5', 'r5', 'm6i']"]
        NT4["allowed_sizes: Optional[List[str]]<br/>e.g. ['large', 'xlarge', '2xlarge']"]
        NT5["excluded_instance_types: Optional[List[str]]<br/>e.g. ['m5.metal']"]
        NT6["architectures: Optional[List[str]]<br/>e.g. ['amd64', 'arm64']"]
        NT7["allowed_azs: Optional[List[str]]<br/>e.g. ['ap-south-1a', 'ap-south-1b']"]
    end

    subgraph Sources["Where NodeTemplate Comes From"]
        S1["Default Template<br/>(execute_pool_ranking_pipeline)<br/>All families, wide ranges<br/>Used for global cache computation"]
        S2["API Request Body<br/>(POST /ascpai/pools/rankings)<br/>User or program-defined"]
        S3["Cluster DB Settings<br/>(cluster_optimization_settings)<br/>Per-cluster preferences"]
        S4["Auto-Rebalancer<br/>Builds template from node's<br/>current instance type + constraints"]
    end

    Sources --> NodeTemplate
```

---

## 8. Pool Ranking Pipeline — Celery Schedule

```mermaid
flowchart TD
    subgraph CeleryBeat["Celery Beat Schedule"]
        direction TB
        
        T1["execute_pool_ranking_pipeline<br/>⏰ Every 1 hour<br/>ascpai_worker.py<br/>→ Runs full global pipeline<br/>→ Caches top 1500 to Redis<br/>→ No cluster-specific filtering"]
        
        T2["ingest_spot_prices (pricing_worker.py)<br/>⏰ Every 10 min<br/>→ Calls describe_spot_price_history<br/>→ Updates SpotPriceHistory + Redis"]
        
        T3["refresh_regional_pricing<br/>⏰ Every 10 min per region<br/>→ Updates spot price Redis cache"]
        
        T4["spot_advisor_scraper (daily)<br/>⏰ 2:00 AM UTC<br/>→ Pulls S3 JSON<br/>→ Updates SpotAdvisorData table<br/>→ SHA256 dedup check"]
        
        T5["on_demand_pricing_scraper (daily)<br/>⏰ 1:00 AM UTC<br/>→ Updates OnDemandPricing table"]
    end

    subgraph Staleness["Cache Staleness Behavior"]
        direction TB
        ST1["global_pool_rankings:{region}<br/>If stale (expired TTL):<br/>First call recomputes (blocks ~2–5s)<br/>Subsequent calls use fresh cache"]
        ST2["spot_advisor:<br/>> 6h → WARNING log<br/>> 24h → auto-retrigger scrape"]
        ST3["spot_price (Redis TTL=10min):<br/>Falls back to DB query<br/>Falls back to hardcoded dict"]
    end
```

---

## 9. Data Flow to Frontend — Pool Rankings UI

```mermaid
sequenceDiagram
    participant Beat as Celery Beat (hourly)
    participant PRS as pool_ranking_service.py
    participant Redis as Redis
    participant Route as ascpai_routes.py
    participant FE as Frontend (PoolRankings.jsx)

    Note over Beat: Every 1 hour
    Beat->>PRS: execute_pool_ranking_pipeline()
    PRS->>PRS: Steps 3–8: SA filter → blacklist → price → ONNX → gates → rank
    PRS->>Redis: SET global_pool_rankings:{region}<br/>[{instance_type, risk, savings, ev, ...}]<br/>TTL=3900s (65min)

    Note over FE: User opens Pool Rankings tab
    FE->>Route: POST /api/v1/ascpai/pools/rankings<br/>{region, limit, template?, node_id?}
    Route->>Redis: GET global_pool_rankings:{region}
    Redis-->>Route: Up to 1500 pool objects
    Route->>Route: _apply_client_filters()<br/>9 cluster-specific filters in-memory
    Route->>Route: Step 9: DryRun validate top 10
    Route-->>FE: [{instance_type, az, risk_probability,<br/>predicted_savings, expected_value, ml_score, rank, ...}]

    Note over FE: Render pool cards
    FE->>FE: Sort by ml_score (already ranked)
    FE->>FE: Show risk bar, savings %, EV score
    FE->>FE: Color-code by risk tier (green/amber/red)
```

---

## 10. ScoredPool Object — What's Inside Each Pool Entry

```mermaid
flowchart LR
    subgraph ScoredPool["ScoredPool (per pool in global cache)"]
        direction TB
        F1["instance_type: str<br/>e.g. 'm5.large'"]
        F2["az: str<br/>e.g. 'ap-south-1a'"]
        F3["vcpu: int<br/>e.g. 2"]
        F4["memory_gb: float<br/>e.g. 8.0"]
        F5["spot_price: float<br/>e.g. 0.0285 ($/hr)"]
        F6["ondemand_price: float<br/>e.g. 0.096 ($/hr)"]
        F7["predicted_savings: float<br/>0.0–1.0 (regressor output)<br/>e.g. 0.70"]
        F8["risk_probability: float<br/>0.0–1.0 (4-signal blend)<br/>e.g. 0.12"]
        F9["expected_value: float<br/>savings × (1 - risk)<br/>e.g. 0.616"]
        F10["ml_score: float<br/>(savings×0.8) × (1-risk) × rep × cap<br/>e.g. 0.493"]
        F11["rank: int<br/>1 = best in region"]
        F12["is_flagged: bool<br/>True if in risky_pools global blacklist"]
        F13["spot_advisor_rank: int<br/>0–5 (5 = missing/default worst)"]
        F14["timestamp: str<br/>ISO format — when price was fetched"]
    end

    subgraph APIResponse["Additional fields added by ascpai_routes.py"]
        direction TB
        A1["s2s_candidate: bool<br/>True if node's risk > cluster ceiling"]
        A2["s2s_trigger: str<br/>Reason: 'risk_threshold', 'pool_diversify', etc."]
        A3["target_instance_type: str<br/>Best replacement pool"]
        A4["current_cost: float<br/>$/hr for current node"]
    end
```

---

## 11. Global Blacklist vs Per-Cluster Blacklist

```mermaid
flowchart TD
    subgraph GlobalBL["Global Blacklist — risky_pools:{region}"]
        direction TB
        G1["Redis SET: risky_pools:{region}<br/>Contains pool_keys that failed system-wide"]
        G2["Added by:<br/>• DryRun failures (RunInstances returned InsufficientCapacity)<br/>• ITN events recorded (record_interruption_event())<br/>• System-B blacklist updates"]
        G3["Applied at: Step 4 — before ML scoring<br/>Scope: ALL clusters in region"]
        G4["Reset by: pool_ranking_service or<br/>manual Redis delete"]
        G1 --> G2 --> G3 --> G4
    end

    subgraph PerClusterBL["Per-Cluster Blacklist — blacklist_failures:{pool_key}"]
        direction TB
        C1["Redis KEY: blacklist_failures:{pool_key}<br/>Value: int (0, 1, 2, or 3)<br/>TTL: 86400s (24h)"]
        C2["Added by:<br/>• auto_rebalancer.py: migration failed<br/>  (spot didn't provision, node not joining)<br/>• S2S action failed for this pool + cluster combo"]
        C3["Applied at: _apply_client_filters() Filter 8<br/>Scope: Only this cluster's filter pass"]
        C4["Auto-expires after 24h<br/>Pool gets a clean slate next day"]
        C1 --> C2 --> C3 --> C4
    end

    GlobalBL -->|"Feeds into"| PerClusterBL
    note["Key difference: Global blacklist = AWS can't provision this pool ANYWHERE.<br/>Per-cluster blacklist = THIS specific cluster had 3+ failures with this pool<br/>(possibly pod scheduling mismatch or node label issue)"]
```

---

## 12. ONNX Circuit Breaker — Fallback Behavior

```mermaid
flowchart TD
    subgraph CircuitBreaker["ML Circuit Breaker (ascpai:ml_fail_count)"]
        Check{"ascpai:ml_fail_count > 5?<br/>(Redis key, TTL=10min)"}
        
        Normal["NORMAL PATH<br/>Run classifier_6.onnx per pool<br/>On failure: incr ml_fail_count<br/>+ expire(600s)"]
        
        Fallback["FALLBACK PATH (circuit OPEN)<br/>Skip ONNX entirely<br/>All pools assigned risk = 0.20<br/>Savings estimated from spot/OD prices<br/>EV = savings × (1 - 0.20)"]
        
        Effect["Effect on Safe Zone:<br/>ALL pools with valid prices pass<br/>0.20 risk < 0.35 hard gate<br/>0.20 risk < 0.50 safety net<br/>→ Typically 400–800 pools in safe zone (inflated)"]
        
        Recovery["Recovery:<br/>ml_fail_count auto-expires in 10 min<br/>Next ONNX success resets counter<br/>Circuit 'closes' automatically"]
        
        Check -->|"No (closed)"| Normal
        Check -->|"Yes (open)"| Fallback
        Fallback --> Effect
        Effect --> Recovery
    end

    style Fallback fill:#ffe0b2
    style Effect fill:#fff9c4
```

---

## 13. Key Constants & Redis Keys Quick Reference

### Constants (pool_ranking_service.py)

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| `GLOBAL_CACHE_LIMIT` | 1500 | Line 37 | Max pools stored per region in global cache |
| `GLOBAL_CACHE_TTL` | 3900s (65 min) | Line 36 | How long global rankings stay cached |
| `optimal_threshold` | 0.35 | Line 135 | ONNX risk hard gate (from `ml_model/risk_threshold.json`) |
| `safety_net_gate` | 0.50 | Line 557–867 | Absolute max risk — hardcoded |
| `fallback_trigger` | < 10 pools | Line 545 | When ONNX gate leaves fewer than 10 pools → activate fallback |
| `circuit_breaker_limit` | > 5 failures | Line 1150 | Opens circuit breaker → fallback scoring |
| `circuit_breaker_window` | 600s (10 min) | Line 1158 | Redis TTL for ml_fail_count |
| `blacklist_failure_threshold` | ≥ 3 | Line 741 | Per-cluster pool rejection |
| `blacklist_ttl` | 86400s (24h) | — | Auto-expiry for per-cluster failure counter |
| `capacity_cache_ttl` | 900s (15 min) | — | DescribeInstanceTypeOfferings cache |
| `validated_pool_ttl` | 1800s (30 min) | — | DryRun validation cache (was 3600s/1h, reduced to 30 min) |
| `dryrun_budget_per_hour` | min(200, clusters×2) | — | EC2 DryRun budget per region |
| `dryrun_per_cluster_cap` | 5 | — | DryRuns per single cluster call |
| `target_validated_pools` | 10 | — | Min pools to DryRun-validate before returning |
| `pod_headroom_pct` | 10% | Line ~677 | Buffer added to pod-request floor |

### Redis Keys Reference

| Key Pattern | Stored Value | TTL | Written By | Read By |
|-------------|-------------|-----|-----------|--------|
| `global_pool_rankings:{region}` | JSON array of ScoredPool | 3900s | pool_ranking_service | ascpai_routes, auto_rebalancer, karpenter_service |
| `spot_price:{region}:{az}:{type}` | `{"price": float, "timestamp": ISO, "is_estimated": bool}` | 600s (real) / 3600s (estimated) | pricing_collector + offerings backfill | pool_ranking_service Step 6 |
| `od_price:{region}:{type}` | float | varies | pricing scraper | pool_ranking_service Step 6 |
| `spot_advisor:{region}:{type}:Linux` | `{"interruption_index": int, "savings": float}` | 90000s (25h) | spot_advisor_scraper | pool_ranking_service Step 3 |
| `spot:advisor:hash:{region}` | SHA256 string | none | spot_advisor_scraper | dedup check |
| `spot:advisor:last_scraped` | ISO timestamp | none | spot_advisor_scraper | staleness check |
| `risky_pools:{region}` | Redis SET of pool_keys | varies | pool_ranking_service, auto_rebalancer | Step 4, _apply_client_filters |
| `blacklist_failures:{pool_key}` | int (0–3) | 86400s (24h) | auto_rebalancer | _apply_client_filters Filter 8 |
| `capacity:{type}:{az}` | "1" or "0" | 900s (15 min) | Step 5 (DescribeOfferings) | Step 5 cache check |
| `spot:validated:{region}:{type}:{az}` | ISO timestamp | 1800s (30 min) | Step 9 (DryRun) | Step 9 cache check |
| `spot:dryrun_count:{region}` | int | 3600s (1h) | Step 9 | budget enforcement |
| `ascpai:ml_fail_count` | int | 600s (10 min) | Step 7 (on ONNX exception) | circuit breaker check |
| `node_resource_profile:{node_id}` | `{"vcpu_requested": float, "memory_gb_requested": float, "replacement_headroom_pct": int}` | varies | pod metrics collector | _apply_client_filters (pod-request floor) |
| `market_factor:{region}` | float (0.80–1.20) | varies | volatility detector | auto_rebalancer (S2S ceiling) |
| `volatility_regime:{region}` | "NORMAL" / "HIGH" / "CRITICAL" | varies | volatility detector | auto_rebalancer, decision engine |
| `instance_type_offerings:{region}:count` | int (number of types discovered) | 90000s (25h) | pricing_collector + aws_pricing_service | telemetry / debugging |

---

## 14. Pool Count Funnel — Visual Summary

```mermaid
flowchart TD
    A["🌍 ALL POOLS IN REGION<br/>~600+ pools (200+ types × 3 AZs)<br/>(Gap 1: offerings backfill)"]
    B["🔶 After SA Annotation (Gap 3)<br/>All pools pass through<br/>(SA rank attached as feature, not a gate)<br/>~600+ pools"]
    C["🔶 After Global Blacklist<br/>~580–600 pools<br/>(−5 to −30 failures removed)"]
    D["🔶 After Price Fetch<br/>~560–590 pools<br/>(no-price pools dropped)"]
    E["🔴 After ONNX Hard Gate (risk ≤ 0.35)<br/>~50–200 pools<br/>⚡ If < 10 survive → fallback mode"]
    F["🟢 SAFE ZONE — After Safety Net (risk ≤ 0.50)<br/>~35–150 pools<br/>(Normal market / ONNX healthy)"]
    G["📦 Global Cache Written<br/>Top 1500 in Redis (all AZ variants, Gap 4)<br/>global_pool_rankings:{region}<br/>TTL: 65 min"]
    H["🏢 Per-Cluster Filter<br/>_apply_client_filters(9 filters)<br/>Typically 5–30 pools survive"]
    I["✅ DryRun Validated (TTL=30min)<br/>Top 10 confirmed with real EC2 capacity<br/>→ Returned to caller"]

    A -->|"~600+"| B
    B -->|"~600+"| C
    C -->|"~580–600"| D
    D -->|"~560–590"| E
    E -->|"~50–200"| F
    F --> G
    G -->|"up to 1500"| H
    H -->|"5–30"| I

    style F fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
    style G fill:#e3f2fd
    style I fill:#c8e6c9
```

---

## 15. Database Tables — Schema Overview

```mermaid
erDiagram
    SpotPriceHistory {
        int id PK
        string instance_type
        string az
        string region
        float price "$/hr spot"
        datetime timestamp
    }

    SpotAdvisorData {
        int id PK
        string instance_type
        string region
        string os_type "Linux/UNIX"
        int interruption_index "0=<5%, 1=5-10%, 2=10-15%, 3=15-20%, 4=>20%"
        float savings_percentage "0-100"
    }

    SpotAdvisorRate {
        int id PK
        string region
        string instance_type
        float interruption_rate_pct
        datetime valid_from "daily audit trail"
    }

    OnDemandPricing {
        int id PK
        string instance_type
        string region
        float price "$/hr on-demand"
        datetime last_updated
    }

    SpotPriceHistory ||--o{ SpotAdvisorData : "same instance_type"
    SpotAdvisorData ||--o{ SpotAdvisorRate : "audit trail"
    OnDemandPricing ||--o{ SpotPriceHistory : "same instance_type"
```
