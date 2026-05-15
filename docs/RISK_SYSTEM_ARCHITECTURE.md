# Risk System Architecture — Complete Reference

> Generated: 9 April 2026  
> Updated: 10 April 2026 (Gap 1–4 fixes applied)  
> Covers: Risk scoring pipeline, S2S risk thresholds, Node Fleet UI, risk-based decisions

---

## 1. Risk System Overview

```mermaid
flowchart TB
    subgraph DataSources["Data Sources"]
        SpotPrices["AWS Spot Price History<br/>(describe_spot_price_history, 6h window)"]
        SpotOfferings["DescribeInstanceTypeOfferings<br/>(Gap 1: authoritative universe discovery)<br/>Backfills estimated prices for 200+ types"]
        SpotAdvisor["AWS Spot Advisor<br/>(Interruption Frequency Rank 1-5)<br/>(Gap 3: annotation-only, not a gate)"]
        HistEvents["Historical Interruption Events<br/>(EMA smoothed)"]
        Temporal["Temporal Features<br/>(hour, day, cyclical encodings)"]
    end

    subgraph MLPipeline["ML Scoring Pipeline (pool_ranking_service.py)"]
        Features["45-Feature Vector<br/>(ml_feature_service.py)"]
        ONNX["classifier_6.onnx<br/>Binary Classifier<br/>Output: risk_probability 0.0–1.0"]
        Blender["4-Signal Blended Risk<br/>ONNX 40% + Price 35% + SA 25% + EMA"]
        HardGate["Hard Risk Gate<br/>optimal_threshold = 0.35<br/>REJECT pools above this"]
        UnifiedScore["Unified Score<br/>savings × 0.8 × (1 - risk)<br/>× reputation × capacity"]
    end

    subgraph Consumers["Risk Consumers"]
        Rebalancer["auto_rebalancer.py<br/>S2S Risk Threshold Check"]
        NodeRecs["ascpai_routes.py<br/>Node Recommendations API"]
        SubMgr["substitute_manager.py<br/>Warm Standby Selection"]
        DecEngine["Decision Engine V3<br/>05_risk_filter.py"]
        CtrlPlane["control_plane_loop.py<br/>Step 7 Diversification"]
    end

    subgraph FrontendUI["Frontend Risk UI"]
        FleetTable["Node Fleet Table<br/>Risk bar per node"]
        RiskSliders["Risk Ceiling + Tradeoff<br/>Sliders"]
        AtRiskBadge["At-Risk Count Badge"]
        PoolCards["Pool Ranking Cards<br/>Risk % display"]
        GlobalRank["Global Rankings<br/>Risk column"]
    end

    SpotPrices --> Features
    SpotOfferings --> Features
    SpotAdvisor --> Features
    HistEvents --> Features
    Temporal --> Features
    Features --> ONNX
    ONNX --> Blender
    Blender --> HardGate
    HardGate --> UnifiedScore

    UnifiedScore --> Rebalancer
    UnifiedScore --> NodeRecs
    UnifiedScore --> SubMgr
    UnifiedScore --> DecEngine
    UnifiedScore --> CtrlPlane

    NodeRecs --> FleetTable
    NodeRecs --> AtRiskBadge
    NodeRecs --> PoolCards
    NodeRecs --> GlobalRank
    Rebalancer --> FleetTable
```

---

## 2. Risk Score Calculation — The 4-Signal Blend

```mermaid
flowchart LR
    subgraph Inputs["Input Signals"]
        direction TB
        S1["Signal 1: ONNX Classifier<br/>classifier_6.onnx<br/>45 features → probability 0.0–1.0<br/><b>Weight: 0.40</b>"]
        S2["Signal 2: Price Pressure<br/>headroom = (OD - Spot) / OD<br/>pressure = max(0, 1 - headroom/0.40)<br/><b>Weight: 0.35</b>"]
        S3["Signal 3: Spot Advisor<br/>AWS rank 1–5 → sa_risk = rank/5.0<br/>Capped at 0.80<br/><b>Weight: 0.25</b>"]
        S4["Signal 4: EMA Smoothing<br/>Historical event exponential average<br/><b>Max injection: 40%</b>"]
    end

    subgraph Calculation["Blending Formula"]
        Blend["weighted_sum =<br/>0.40 × ONNX +<br/>0.35 × Price_Pressure +<br/>0.25 × SA_Risk"]
        EMA["final_risk =<br/>(1 - ema_wt) × base +<br/>ema_wt × ema_risk"]
    end

    subgraph Overrides["Hard Overrides"]
        BL["Blacklisted Pool<br/>(ITN in last 24h)<br/>→ max(0.75, risk)"]
        DR["Dry-Run Failed<br/>(no capacity)<br/>→ max(0.65, risk)"]
    end

    subgraph Output["Final Output"]
        Risk["risk_probability<br/>0.0 (safest) → 1.0 (riskiest)"]
    end

    S1 --> Blend
    S2 --> Blend
    S3 --> Blend
    Blend --> EMA
    S4 --> EMA
    EMA --> BL
    BL --> DR
    DR --> Risk
```

### 45 ML Features Breakdown

```mermaid
pie title ML Feature Distribution (45 total)
    "Temporal (hour, day, cyclical)" : 10
    "Lag Features (1h, 4h, 24h)" : 3
    "Rolling Stats (4h + 24h windows)" : 8
    "Price Dynamics (velocity, volatility, headroom)" : 5
    "Family-Time Patterns" : 6
    "Family Stress (cross-instance contagion)" : 3
    "Event Features (holidays, stress)" : 3
    "Pool Risk (historical failure rate)" : 1
    "Categorical Encodings (family, size, AZ)" : 6
```

---

## 3. Risk Gates — Multi-Layer Filtering

```mermaid
flowchart TD
    AllPools["All Spot Pools in Region<br/>(~600+ pools, Gap 1: offerings backfill)"]
    
    Gate1{"Gate 1: ONNX Hard Gate<br/>risk_probability ≤ 0.35?<br/>(ml_model/risk_threshold.json)<br/><br/>Note: SA rank is annotation-only (Gap 3)<br/>feeds into ONNX as a feature,<br/>no separate SA gate exists"}
    AllPools --> Gate1
    Gate1 -->|"Pass"| Gate2
    Gate1 -->|"Fail"| Rejected1["❌ Rejected<br/>(too risky per ML model)"]
    
    Gate2{"Gate 2: Risk Ceiling<br/>risk ≤ risk_ceiling_percent × market_factor?<br/>(default: 25% × 0.8–1.2)"}
    Gate2 -->|"Pass"| Gate3
    Gate2 -->|"Fail"| Rejected2["❌ Rejected<br/>(exceeds user ceiling)"]
    
    Gate3{"Gate 3: Safety Net<br/>risk ≤ 0.50?<br/>(fallback scoring only)"}
    Gate3 -->|"Pass"| Score["✅ Scored & Ranked<br/>EV = savings × (1 - risk)"]
    Gate3 -->|"Fail"| Rejected3["❌ Rejected<br/>(safety net catch-all)"]

    subgraph FallbackPath["If ONNX circuit breaker open (>5 failures in 10min)"]
        FB["All pools get risk = 0.20<br/>(conservative default)"]
    end

    subgraph GapNotes["Gap Fix Summary"]
        GN1["Gap 1: Universe expanded to 200+ types via DescribeInstanceTypeOfferings"]
        GN2["Gap 2: Price history lookback extended to 6h (was 1-2h)"]
        GN3["Gap 3: SA rank is annotation-only (ONNX feature), not a hard gate"]
        GN4["Gap 4: All AZ variants retained in global cache (no dedup)"]
        GN5["DryRun validation TTL reduced to 30min (was 1h)"]
    end
    
    style Rejected1 fill:#ffcdd2
    style Rejected2 fill:#ffcdd2
    style Rejected3 fill:#ffcdd2
    style Score fill:#c8e6c9
```

---

## 4. Unified Scoring Formula

```mermaid
flowchart LR
    subgraph Formula["Unified Score = (savings × 0.8) × (1 - risk) × reputation × capacity"]
        Savings["savings_pct<br/>(OD - Spot) / OD<br/>Weight: 0.8"]
        Risk["(1 - risk_probability)<br/>Safety multiplier"]
        Rep["reputation_mult<br/>Based on historical success<br/>Default: 1.0"]
        Cap["capacity_mult<br/>Based on availability<br/>Default: 1.0"]
        EV["expected_value =<br/>savings × (1 - risk)"]
    end

    Savings --> EV
    Risk --> EV

    subgraph Example["Example Calculation"]
        E1["Pool: t3a.medium:ap-south-1c<br/>Savings: 72% (OD=$0.0416 → Spot=$0.0117)"]
        E2["ONNX risk: 0.12<br/>Price pressure: 0.08<br/>SA rank: 2 → sa_risk=0.40"]
        E3["Blended risk =<br/>0.40×0.12 + 0.35×0.08 + 0.25×0.40<br/>= 0.048 + 0.028 + 0.100 = 0.176"]
        E4["EV = 0.72 × (1 - 0.176) = 0.593<br/>Unified = 0.72×0.8 × 0.824 × 1.0 × 1.0 = 0.475"]
    end
    E1 --> E2 --> E3 --> E4
```

---

## 5. S2S Risk-Based Rebalancing — Complete Flow

```mermaid
flowchart TD
    Start["Celery Beat tick (every 15s)<br/>auto_rebalancer.py"]
    
    CheckOD{"Any ON_DEMAND<br/>nodes left?"}
    Start --> CheckOD
    
    CheckOD -->|"Yes"| ODPath["OD→Spot migration path<br/>(not S2S)"]
    CheckOD -->|"No (all spot)"| LoadSettings
    
    LoadSettings["Load S2S Settings:<br/>• risk_ceiling_percent (default 25%)<br/>• risk_savings_tradeoff_pct (default 20%)<br/>• diversify_pools (bool)<br/>• market_factor (Redis)"]

    ApplyMF["Apply Market Factor:<br/>effective_ceiling = 25% × market_factor<br/>Range: 20%–30%"]
    LoadSettings --> ApplyMF
    
    IterateSpot["For each SPOT node<br/>in cluster..."]
    ApplyMF --> IterateSpot

    subgraph Checks["S2S Trigger Checks (sequential)"]
        direction TB
        
        Check0["<b>Check 0: Opportunistic</b><br/>Find pool with BOTH:<br/>• Δrisk ≥ 5pp lower<br/>• Δsavings ≥ 1pp higher<br/><i>(Dynamic: +2pp in HIGH vol, +4pp in CRITICAL)</i>"]
        
        Check1["<b>Check 1: Pool Diversify</b><br/>Same (type, az) has >1 node?<br/>→ Duplicate pool violation"]
        
        Check15["<b>Check 1.5: Family Cap</b><br/>Family X count > ceil(40% × total)?<br/>→ Family concentration violation"]
        
        Check2["<b>Check 2: Risk Threshold</b><br/>current_risk > risk_ceiling?<br/>→ Node is TOO RISKY"]

        Check0 -->|"No trigger"| Check1
        Check1 -->|"No trigger"| Check15
        Check15 -->|"No trigger"| Check2
    end

    IterateSpot --> Check0
    
    Check0 -->|"Trigger!"| TargetSelect
    Check1 -->|"Trigger!"| TargetSelect
    Check15 -->|"Trigger!"| TargetSelect
    Check2 -->|"Trigger!"| TargetSelect
    Check2 -->|"No trigger"| NextNode["Next spot node..."]

    subgraph TargetSelect["Target Pool Selection (3 Passes)"]
        direction TB
        P1["<b>Pass 1: Strict</b><br/>Better risk AND ≥ savings<br/>+ pool uniqueness + family cap"]
        P2["<b>Pass 2: Tradeoff</b><br/>Better risk AND savings ≥ current × (1-20%)<br/><i>Only for risk_threshold trigger</i>"]
        P3["<b>Pass 3: Diversify Any</b><br/>Any unoccupied pool from different family<br/><i>Only for diversify triggers</i>"]
        OD["<b>OD Fallback</b><br/>Replace spot with on-demand same-type<br/><i>Only for risk_threshold trigger</i>"]
        
        P1 -->|"No match"| P2
        P2 -->|"No match"| P3
        P3 -->|"No match"| OD
    end

    TargetSelect --> CreateAction["Create S2S RebalancingAction<br/>→ Phase 1 (provision) → Phase 2 (drain+terminate)"]
    
    style Check0 fill:#e0f7fa
    style Check1 fill:#e8f5e9
    style Check15 fill:#e8f5e9
    style Check2 fill:#fff3e0
    style P1 fill:#e8f5e9
    style P2 fill:#fff9c4
    style P3 fill:#e0f7fa
    style OD fill:#ffcdd2
```

---

## 6. Risk Ceiling — Dynamic Adjustment

```mermaid
flowchart TD
    subgraph UserConfig["User Configuration (DB: optimization_strategy)"]
        RC["risk_ceiling_percent<br/>Default: 25%<br/>Range: 5%–80% (UI slider)"]
        TP["risk_savings_tradeoff_pct<br/>Default: 20%<br/>Range: 0%–50% (UI slider)"]
    end

    subgraph MarketFactor["Market Factor Adjustment"]
        MF["Redis: market_factor:{region}<br/>Range: 0.80–1.20"]
        Calc["effective_ceiling =<br/>risk_ceiling × market_factor"]
    end

    RC --> Calc
    MF --> Calc

    subgraph Examples["Effective Ceiling Examples"]
        EX1["Normal market (factor=1.0):<br/>25% × 1.0 = <b>25%</b>"]
        EX2["Volatile market (factor=0.85):<br/>25% × 0.85 = <b>21.25%</b> (stricter)"]
        EX3["Calm market (factor=1.15):<br/>25% × 1.15 = <b>28.75%</b> (relaxed)"]
    end

    Calc --> EX1
    Calc --> EX2
    Calc --> EX3

    subgraph DecisionEngineOverrides["Decision Engine V3 — Extra Layers"]
        direction TB
        L1["Layer 1: Strategy Profile<br/>COST_FIRST → 25%<br/>BALANCED → 20%<br/>NO_DOWNTIME_FIRST → 10%"]
        L2["Layer 2: Volatility Regime<br/>volatile=true → subtract 5%"]
        L3["Layer 3: Trust Phase<br/>Phase 0 (0-30 min) → force 15%<br/>Phase 1 (30min-2h) → force 20%<br/>Phase 2 (>2h) → no override"]
        Final["Effective = min(L1, L2_adjusted, L3_override)<br/><i>Strictest always wins</i>"]
        L1 --> Final
        L2 --> Final
        L3 --> Final
    end
```

---

## 7. Volatility Regime — Effects on Risk Decisions

```mermaid
flowchart TD
    subgraph Detection["Volatility Detection"]
        Redis1["Redis: volatility_regime:{region}<br/>'NORMAL' | 'HIGH' | 'CRITICAL'"]
        Redis2["Redis: market_factor:{region}<br/>0.80 — 1.20"]
    end

    subgraph Effects["Effects on System Behavior"]
        direction TB
        
        subgraph Normal["NORMAL Volatility"]
            N1["Risk ceiling: base × 1.0"]
            N2["S2S opportunistic: Δrisk ≥ 5pp, Δsavings ≥ 1pp"]
            N3["Standard behavior"]
        end

        subgraph High["HIGH Volatility"]
            H1["Risk ceiling: base × ~0.90 (tighter)"]
            H2["S2S opportunistic: Δrisk ≥ 7pp, Δsavings ≥ 1.5pp<br/>(wider thresholds = harder to trigger)"]
            H3["Decision Engine: -5% ceiling adjustment"]
        end

        subgraph Critical["CRITICAL Volatility"]
            CR1["Risk ceiling: base × ~0.80 (strictest)"]
            CR2["S2S opportunistic: Δrisk ≥ 9pp, Δsavings ≥ 2pp<br/>(much wider = only obvious improvements)"]
            CR3["Decision Engine: -5% + trust phase locks"]
        end
    end

    Redis1 --> Normal
    Redis1 --> High
    Redis1 --> Critical

    style Normal fill:#e8f5e9
    style High fill:#fff9c4
    style Critical fill:#ffcdd2
```

---

## 8. Node Fleet UI — Risk Display Components

```mermaid
flowchart TB
    subgraph API["API: GET /ascpai/clusters/{id}/node-recommendations"]
        Response["Per-node response fields:<br/>• risk_score (0.0–1.0)<br/>• s2s_candidate (bool)<br/>• s2s_trigger (string)<br/>• current_cost ($/hr)<br/>• target_instance_type<br/>• target_spot_price<br/>• lifecycle (spot/on_demand)"]
    end

    subgraph FleetTable["Node Fleet Table (PoolRankings.jsx)"]
        direction TB

        SummaryCards["Summary Cards Row"]
        NodeRow["Per-Node Row"]
        
        subgraph Cards["4 Summary Cards"]
            C1["Total Nodes<br/>(nodeRecommendations.length)"]
            C2["At-Risk Nodes<br/>risk_score > 0.60<br/>🔴 Red count badge"]
            C3["Spot Nodes<br/>Already optimized count"]
            C4["S2S Candidates<br/>Nodes needing migration"]
        end

        subgraph RowDetail["Per-Node Status Column"]
            StatusBadge["Status Badge:<br/>• 🟢 Optimized (spot, risk OK)<br/>• 🟡 REBALANCE:RISK_HIGH (risk%)<br/>• 🔵 REBALANCE:BETTER_POOL<br/>• ⚪ STABLE (risk%)<br/>• 🟠 Orphaned"]
            
            RiskBar["Risk Progress Bar:<br/>(only for Optimized spot nodes)"]
        end

        SummaryCards --> Cards
        NodeRow --> RowDetail
    end

    API --> FleetTable

    subgraph RiskBarDetail["Risk Bar Anatomy"]
        direction TB
        Calc2["riskVal = rec.risk_score<br/>ceil = dynamicRiskCeiling (default 0.25)<br/>pct = min(100, round(riskVal/ceil × 100))"]
        
        Colors["Bar Colors:<br/>🟢 Green (pct < 75% of ceiling)<br/>🟡 Amber (75%–100% of ceiling, 'Approaching')<br/>🔴 Red + glow + pulse (> ceiling, '⚠ S2S next cycle')"]
        
        Display["Display: '12% / 25%'<br/>= current risk / ceiling<br/>with animated progress bar"]
        
        Calc2 --> Colors --> Display
    end
```

### Risk Bar Visual States

```mermaid
flowchart LR
    subgraph Safe["🟢 SAFE (risk 8% / ceiling 25%)"]
        S["████░░░░░░░░░░<br/>Green bar, 32% filled<br/>No label"]
    end
    
    subgraph Warning["🟡 WARNING (risk 20% / ceiling 25%)"]
        W["████████████░░<br/>Amber bar, 80% filled<br/>'Approaching' label"]
    end
    
    subgraph Breach["🔴 BREACHING (risk 32% / ceiling 25%)"]
        B["██████████████<br/>Red bar + red glow, 100% filled<br/>'⚠ S2S next cycle' pulse"]
    end
```

---

## 9. Risk Threshold UI Controls

```mermaid
flowchart TD
    subgraph SettingsPanel["ClusterDetails.jsx — Optimization Strategy Panel"]
        direction TB
        
        subgraph StrategySelector["Strategy Selector"]
            ST["Presets:<br/>• COST_FIRST (aggressive, higher risk OK)<br/>• BALANCED (default)<br/>• NO_DOWNTIME_FIRST (conservative)<br/>• CUSTOM"]
        end

        subgraph Sliders["Risk Sliders"]
            Slider1["<b>Maximum Risk Ceiling</b><br/>Range: 5%–80% (step 5)<br/>Default: 25%<br/><br/>Controls: hard reject threshold<br/>for spot pool selection<br/>and S2S trigger point"]
            
            Slider2["<b>Risk/Savings Tradeoff</b><br/>Range: 0%–50% (step 5)<br/>Default: 20%<br/><br/>Controls: how much savings<br/>to sacrifice for safety<br/>in S2S Pass 2"]
        end

        subgraph WritePath["Save Path"]
            Save["PUT /clusters/{id}/optimization-settings<br/>→ optimization_strategy table<br/>→ risk_ceiling_percent<br/>→ risk_savings_tradeoff_pct"]
        end

        StrategySelector --> Sliders --> WritePath
    end
```

---

## 10. Complete Risk Threshold Reference

```mermaid
flowchart TD
    subgraph Thresholds["All Risk Thresholds in the System"]
        direction TB
        
        subgraph MLGates["ML Pipeline Gates"]
            T1["0.35 — ONNX Hard Gate<br/><i>pool_ranking_service.py Step 7</i><br/>Pools above this NEVER selected"]
            T2["0.50 — Safety Net Gate<br/><i>Fallback scoring only</i><br/>Absolute maximum for any pool"]
            T3["0.20 — Circuit Breaker Default<br/><i>When ONNX fails</i><br/>All pools get this risk"]
        end

        subgraph UserConfig2["User-Configurable"]
            T4["risk_ceiling_percent<br/>Default: 25% (0.25)<br/>× market_factor (0.80–1.20)<br/>Effective range: 20%–30%"]
            T5["risk_savings_tradeoff_pct<br/>Default: 20%<br/>S2S Pass 2 only"]
        end

        subgraph S2SThresholds["S2S Decision Thresholds"]
            T6["Check 0 Opportunistic:<br/>Δrisk ≥ 5pp + vol_boost<br/>Δsavings ≥ 1pp + vol_boost×0.5"]
            T7["Check 2 Risk Trigger:<br/>node_risk > effective_ceiling"]
        end

        subgraph UIThresholds["UI Display Thresholds"]
            T8["0.60 — At-Risk Count<br/><i>PoolRankings.jsx summary card</i><br/>Nodes with risk > 60% counted"]
            T9["75% of ceiling — Warning bar<br/><i>Amber 'Approaching' label</i>"]
            T10["> ceiling — Breach bar<br/><i>Red glow + '⚠ S2S next cycle'</i>"]
        end

        subgraph BlendOverrides["Blend Hard Overrides"]
            T11["0.75 — Blacklisted pool floor<br/><i>ITN event in last 24h</i>"]
            T12["0.65 — Dry-run failure floor<br/><i>No spot capacity available</i>"]
        end

        subgraph RiskTiers["Risk Tier Assignment"]
            T13["Tier 0: < 5% (Safest)<br/>Tier 1: 5%–10%<br/>Tier 2: 10%–15%<br/>Tier 3: 15%–20%<br/>Tier 4: > 20% (Riskiest)"]
        end
        
        subgraph DEV3["Decision Engine V3 Overrides"]
            T14["COST_FIRST: 25%<br/>BALANCED: 20%<br/>NO_DOWNTIME_FIRST: 10%<br/>Volatile: −5%<br/>Trust Phase 0: force 15%<br/>Trust Phase 1: force 20%"]
        end
    end
```

---

## 11. Risk-Based Actions — What Happens When

```mermaid
flowchart TD
    subgraph Scenario1["Scenario: Node Risk Exceeds Ceiling"]
        A1["Node t3a.medium:ap-south-1c<br/>risk_probability = 0.32<br/>ceiling = 0.25"]
        A2["auto_rebalancer Check 2 fires:<br/>'risk_threshold: risk=0.32 > ceil=0.25'"]
        A3["Target Selection:<br/>Pass 1: Find pool with risk < 0.25 AND ≥ savings"]
        A4{"Found safer pool?"}
        A5["Create S2S action<br/>→ Patch NodePool → Trigger Pod<br/>→ Wait for Spot → Cordon → Drain → Terminate"]
        A6["Pass 2: Accept pool with<br/>savings ≥ 80% of current<br/>(tradeoff 20%)"]
        A7["OD Fallback:<br/>Replace spot with on-demand same-type<br/>(last resort, sacrifices all savings)"]
        
        A1 --> A2 --> A3 --> A4
        A4 -->|"Yes"| A5
        A4 -->|"No"| A6
        A6 -->|"No match"| A7
    end

    subgraph Scenario2["Scenario: Spot Interruption (Emergency)"]
        B1["AWS 2-minute ITN warning<br/>agent/poller.py detects via IMDS"]
        B2["Agent sends heartbeat with<br/>interruption_warning=true"]
        B3["substitute_manager.py<br/>selects replacement from<br/>ML-ranked pools (risk_score weighted)"]
        B4{"ML pools available?"}
        B5["Launch replacement from<br/>ranked pool with lowest risk"]
        B6["Hardcoded family fallback<br/>(conservative sizes)"]
        B7["record_interruption_event()<br/>→ EMA history shifts<br/>→ that pool's future risk ↑"]
        
        B1 --> B2 --> B3 --> B4
        B4 -->|"Yes"| B5
        B4 -->|"No"| B6
        B5 --> B7
        B6 --> B7
    end

    subgraph Scenario3["Scenario: Market Volatility Spike"]
        C1["Volatility regime changes<br/>NORMAL → HIGH"]
        C2["market_factor drops<br/>1.0 → 0.85"]
        C3["Effective ceiling tightens<br/>25% × 0.85 = 21.25%"]
        C4["Nodes previously 'safe' at 23%<br/>now BREACH the ceiling"]
        C5["S2S Check 2 triggers<br/>more aggressively"]
        C6["Opportunistic thresholds widen<br/>Δrisk ≥ 7pp (was 5pp)<br/>= harder to trigger opportunistic moves"]
        
        C1 --> C2 --> C3 --> C4 --> C5
        C2 --> C6
    end

    subgraph Scenario4["Scenario: Pool Re-Ranking (every 30 min)"]
        D1["Celery: execute_pool_ranking_pipeline"]
        D2["For each pool in region:<br/>1. Build 45 features<br/>2. Run ONNX classifier<br/>3. Blend 4 signals<br/>4. Compute unified score"]
        D3["Store in Redis:<br/>global_pool_rankings:{region}<br/>TTL: 65 min"]
        D4["Next rebalancer cycle picks up<br/>new risk scores for S2S evaluation"]
        D5["Node fleet UI refreshes<br/>risk bars on next API call"]
        
        D1 --> D2 --> D3 --> D4
        D3 --> D5
    end
```

---

## 12. Data Flow — Risk Score to UI Display

```mermaid
sequenceDiagram
    participant ML as ML Pipeline<br/>(Celery every 30m)
    participant Redis as Redis Cache
    participant API as ascpai_routes.py
    participant FE as PoolRankings.jsx

    Note over ML: Pool Ranking Pipeline runs
    ML->>ML: Build 45 features per pool
    ML->>ML: Run classifier_6.onnx
    ML->>ML: Blend: 40% ONNX + 35% Price + 25% SA
    ML->>ML: Apply hard overrides (blacklist/dryrun)
    ML->>Redis: SET global_pool_rankings:{region}<br/>{pool: {risk_probability, savings, ev, ...}}

    Note over FE: User views Node Fleet tab
    FE->>API: GET /ascpai/clusters/{id}/node-recommendations
    API->>Redis: GET global_pool_rankings:{region}
    Redis-->>API: Cached pool data
    API->>API: Load risk_ceiling from DB
    API->>API: Apply market_factor to ceiling
    API->>API: For each node:<br/>- Find current pool in rankings<br/>- Get risk_probability<br/>- Check if > ceiling → s2s_candidate=true<br/>- Set s2s_trigger reason
    API-->>FE: [{risk_score, s2s_candidate, s2s_trigger, ...}]

    Note over FE: Render Node Fleet table
    FE->>FE: Summary: atRiskNodes = filter(risk > 0.60)
    FE->>FE: Per-node: pct = risk/ceiling × 100
    FE->>FE: Color: green(<75%) / amber(75-100%) / red(>100%)
    FE->>FE: Label: "12% / 25%" with progress bar
    FE->>FE: If breaching: "⚠ S2S next cycle" (red pulse)
```

---

## 13. Strategy Presets — Risk Impact

```mermaid
flowchart LR
    subgraph Presets["Strategy Presets (optimization_strategy.strategy_type)"]
        direction TB
        
        subgraph CostFirst["COST_FIRST"]
            CF1["risk_ceiling: 25%<br/>min_savings: 15%<br/>tradeoff: 10%<br/>migration_penalty: 1.0"]
            CF2["<i>Aggressive: accepts higher risk<br/>for better savings</i>"]
        end

        subgraph Balanced["BALANCED (default)"]
            BA1["risk_ceiling: 25%<br/>min_savings: 15%<br/>tradeoff: 20%<br/>migration_penalty: 1.5"]
            BA2["<i>Middle ground: will sacrifice<br/>20% savings for safety</i>"]
        end

        subgraph NoDowntime["NO_DOWNTIME_FIRST"]
            ND1["risk_ceiling: 10%<br/>min_savings: 5%<br/>tradeoff: 40%<br/>migration_penalty: 3.0"]
            ND2["<i>Conservative: very low risk tolerance<br/>will sacrifice 40% savings for safety</i>"]
        end
    end

    subgraph Effective["Effective Behavior"]
        E_CF["More pools qualify<br/>Fewer S2S triggers<br/>Higher savings, higher interruption chance"]
        E_BA["Moderate pool selection<br/>S2S triggers at 25%<br/>Balanced savings/safety"]
        E_ND["Very few pools qualify<br/>S2S triggers at 10%<br/>Minimal interruptions, less savings"]
    end

    CostFirst --> E_CF
    Balanced --> E_BA
    NoDowntime --> E_ND
    
    style CostFirst fill:#fff3e0
    style Balanced fill:#e8f5e9
    style NoDowntime fill:#e3f2fd
```

---

## 14. Risk Data Model

```mermaid
erDiagram
    optimization_strategy {
        string cluster_id PK
        string strategy_type "COST_FIRST|BALANCED|NO_DOWNTIME_FIRST|CUSTOM"
        int risk_ceiling_percent "5-80, default 25"
        int min_savings_percent "default 15"
        int volatility_tolerance_percent "default 20"
        float migration_penalty_multiplier "default 1.5"
        string diversity_strictness_level "Low|Medium|High"
        int risk_savings_tradeoff_pct "0-50, default 20"
    }

    cluster_optimization_settings {
        string cluster_id PK
        bool auto_rebalance_enabled
        bool auto_rightsizing_enabled
        bool diversify_pools "default false"
        int max_family_diversification_cap_pct "default 40"
        int check_interval_seconds "default 15"
    }

    rebalancing_actions {
        int id PK
        string cluster_id FK
        string source_pool "e.g. t3.medium:ap-south-1a"
        string target_pool "e.g. t3a.medium:ap-south-1c"
        string status "pending|in_progress|completed|failed"
        jsonb metadata "reason, risk scores, S2S trigger"
        float realized_savings_monthly_usd
    }

    clusters ||--|| optimization_strategy : "has one"
    clusters ||--|| cluster_optimization_settings : "has one"
    clusters ||--o{ rebalancing_actions : "has many"
```

---

## 15. All Risk Thresholds — Quick Reference Table

| Threshold | Value | Source | Purpose |
|-----------|-------|--------|---------|
| **ONNX Hard Gate** | 0.35 | `risk_threshold.json` | Reject pools from ML pipeline |
| **Safety Net** | 0.50 | `pool_ranking_service.py` | Absolute maximum (fallback scoring) |
| **ONNX Fallback** | 0.20 | `pool_ranking_service.py` | Default risk when ONNX circuit breaker trips |
| **Risk Ceiling (user)** | 25% default | `optimization_strategy` table | Per-cluster configurable ceiling |
| **Market Factor** | 0.80–1.20× | Redis `market_factor:{region}` | Multiplied into risk ceiling |
| **S2S Opportunistic Δrisk** | ≥5pp base | `auto_rebalancer.py` Check 0 | Must be this much safer |
| **S2S Opportunistic Δsavings** | ≥1pp base | `auto_rebalancer.py` Check 0 | Must also be cheaper |
| **HIGH vol boost** | +2pp risk, +1pp savings | `auto_rebalancer.py` | Widens opportunistic thresholds |
| **CRITICAL vol boost** | +4pp risk, +2pp savings | `auto_rebalancer.py` | Widens even more |
| **S2S Tradeoff** | 20% default | `optimization_strategy` table | Accept pool 20% costlier if safer |
| **At-Risk UI badge** | >60% | `PoolRankings.jsx` | Counts nodes in summary card |
| **UI Warning bar** | ≥75% of ceiling | `PoolRankings.jsx` | Amber "Approaching" label |
| **UI Breach bar** | >100% of ceiling | `PoolRankings.jsx` | Red glow + "⚠ S2S next cycle" |
| **Blacklist floor** | 0.75 | `compute_blended_risk()` | Pool with ITN in last 24h |
| **Dry-run fail floor** | 0.65 | `compute_blended_risk()` | Pool failed capacity check |
| **DE V3 COST_FIRST** | 25% | `05_risk_filter.py` | Strategy-based ceiling |
| **DE V3 BALANCED** | 20% | `05_risk_filter.py` | Strategy-based ceiling |
| **DE V3 NO_DOWNTIME** | 10% | `05_risk_filter.py` | Strategy-based ceiling |
| **DE V3 Volatile adj** | -5% | `05_risk_filter.py` | Subtracted when volatile |
| **Trust Phase 0** | force 15% | `05_risk_filter.py` | First 30 min of cluster life |
| **Trust Phase 1** | force 20% | `05_risk_filter.py` | 30 min – 2 hr of cluster life |
| **Risk Tier boundaries** | 5%, 10%, 15%, 20% | `assign_risk_tier()` | Tier 0 through Tier 4 |
