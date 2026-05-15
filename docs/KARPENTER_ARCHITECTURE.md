# Karpenter ↔ Spot Optimizer Architecture

> Generated: 9 April 2026  
> Last verified against codebase: 16 April 2026  
>
> This document describes the **current, implemented** architecture. Every section is verified against actual source code. For a change log, see `docs/BUGS_AND_FIXES.md`.

---

## 1. System Overview

The platform has four independent layers that work together:

- **Frontend** — user-facing toggles that drive consolidation and rebalancing policy
- **Backend** — FastAPI routes + Celery workers that decide *when* and *what* to migrate
- **Karpenter** — provisions and terminates EC2 nodes on demand via NodePool specs
- **Agent** — DaemonSet that executes node-level cordon / drain / eviction inside the cluster

```mermaid
flowchart TB
    subgraph Frontend["Frontend (React)"]
        UI["ClusterDetails.jsx\nToggle: auto_rebalancing_enabled\nToggle: auto_rightsizing_enabled\nToggle: diversify_pools"]
    end

    subgraph Backend["Backend (FastAPI + Celery)"]
        API_Karp["karpenter_routes.py\nPATCH /karpenter/config/{cluster_id}\n→ patch_consolidation_policy()"]
        Celery["auto_rebalancer.py\nCelery Beat every 15s"]
        KarpSvc["karpenter_service.py\nadd_allowed_instance_type()\nremove_allowed_instance_type()\n_update_nodepool()\ncreate_spot_trigger_pod()"]
        PoolRank["pool_ranking_service.py\nML Risk + Savings Ranking\n(200+ instance types)"]
        EvictSvc["eviction_safety.py\neviction_gate() / safe_to_evict()\nprotect_single_replica()\ncheck_endpoints_for_node_pods()"]
        WorkloadInsp["workload_inspector.py\nbuild_workload_profile()\ncollect_misconfig_recommendations()"]
        RollbackWorker["resize_guard_worker.py\nresize_rollback_consumer()"]
    end

    subgraph EKS["EKS Cluster (K8s)"]
        subgraph Karpenter["Karpenter v1.0.8"]
            NP_Default["NodePool: default\ncapacity: spot + on-demand\ndisruption: WhenEmpty (when rebalancing ON)\nconsolidateAfter: Never (during injection)"]
            NP_Stateless["NodePool: stateless-spot\ncapacity: spot only\ndisruption: WhenEmptyOrUnderutilized, 30s"]
            NP_Stateful["NodePool: stateful-od\ncapacity: on-demand only\ndisruption: WhenEmpty, 60s"]
        end
        Agent["Spot Optimizer Agent\n(DaemonSet + Orchestrator)"]
        Nodes["EC2 Nodes (OD + Spot)"]
    end

    subgraph AWS["AWS"]
        EC2["EC2 Fleet API"]
        ASG["Auto Scaling Groups"]
    end

    UI --> API_Karp
    API_Karp --> KarpSvc
    Celery --> KarpSvc
    Celery --> PoolRank
    Celery --> EvictSvc
    Celery --> WorkloadInsp
    WorkloadInsp --> RollbackWorker
    KarpSvc -->|"K8s API PATCH"| NP_Default
    NP_Default -->|"Provisions/Terminates"| EC2
    NP_Default --> Nodes
    Agent -->|"Heartbeat + Metrics"| Backend
    Agent -->|"Cordon/Drain/Evict"| Nodes
    Celery -->|"terminate_instance_in_asg()"| ASG
```

---

## 2. Workload Classification & Tiers

Every workload is profiled once per scan cycle by `build_workload_profile()` and stored in Redis. The tier drives kube-proxy soak time during endpoint convergence and determines eviction strategy.

```mermaid
flowchart TD
    Scan["build_all_profiles_for_cluster()\nPre-fetches: KEDA ScaledObjects + HPAs\nIterates all nodes\nGroups pods by controller"]

    Scan --> Profile["Per-controller profile stored at:\nspot:workload_profile:{cid}:{ns}/{ctrl}\n\nFields:\n• pdb_defined / pdb_healthy_count / pdb_min_available\n• readiness_probe_defined / min_initial_delay\n• termination_grace_period_seconds\n• has_prestop_hook\n• has_service_mesh_sidecar\n• keda_managed / scaled_object_name\n• keda_min_replicas / keda_max_replicas\n• replica_count"]

    Profile --> TierAssign["Tier Assignment\n(W6 — workload_inspector.py)"]

    TierAssign --> T0["TIER 0: NEVER_MIGRATE\nOperator-owned CRDs\nStatefulSet OnDelete strategy\nSoak: 45s"]
    TierAssign --> T1["TIER 1: ANCHORED_MANUAL\nStateful, manually scaled\nSoak: 45s"]
    TierAssign --> T2["TIER 2: SPOT_WITH_CAUTION\nKEDA-managed (has ScaledObject)\nSoak: 30s"]
    TierAssign --> T3["TIER 3: KEDA_GATED\nQueue workers\nSoak: 20s"]
    TierAssign --> T4["TIER 4: SPOT_ELIGIBLE\nStateless Deployments with readiness probe\nSoak: 10s"]

    Profile --> Recs["collect_misconfig_recommendations()\n→ spot:workload_recommendations:{cid}\n\nChecks:\n• MISSING_PRESTOP_HOOK (HIGH)\n• SINGLE_REPLICA_NO_PDB (CRITICAL)\n• MISSING_READINESS_PROBE (MEDIUM)"]
```

---

## 3. Auto-Rebalancer State Machine

The Celery Beat task (`auto_rebalancer.py`) runs every 15 seconds per cluster. Two separate paths handle OD→Spot and Spot→Spot rebalancing.

```mermaid
stateDiagram-v2
    [*] --> CycleStart: Celery Beat every 15s

    CycleStart --> CooldownCheck: Load cluster settings
    CooldownCheck --> Skip: 24h cooldown active
    CooldownCheck --> ConcurrencyGuard: Cooldown expired

    ConcurrencyGuard --> Skip: In-flight AgentActions (S2S mode only)
    ConcurrencyGuard --> LastNodeGuard: No in-flight / OD batch bypass

    LastNodeGuard --> Skip: Only 1 running node
    LastNodeGuard --> NodeTypeCheck: ≥2 running nodes

    NodeTypeCheck --> ODtoSpot: OD instances found
    NodeTypeCheck --> S2SChecks: All spot, no OD

    state ODtoSpot {
        [*] --> BatchSize: batch_percent% of OD nodes
        BatchSize --> PerNodeLock: Redis nx key per instance_id
        PerNodeLock --> GlobalSemaphore: Lock acquired (TTL 24h)
        GlobalSemaphore --> DryRunValidation: Under limit (max 3 concurrent)
        DryRunValidation --> MLRanking: Capacity confirmed (parallel dry-runs)
        MLRanking --> NodePoolLookup: Top-1 type selected
        NodePoolLookup --> Phase1: Target NodePool resolved from node label
    }

    state Phase1 {
        [*] --> EKSAuthCheck: Verify KarpenterNodeRole access entry
        EKSAuthCheck --> InjectType: Auto-fix if missing
        InjectType --> LabelExistingNodes: PATCH NodePool with top-1 type\nconsolidateAfter → Never
        LabelExistingNodes --> CreateTriggerPod: Mark nodes spot-optimizer.io/existing-node=true
        CreateTriggerPod --> WaitForSpot: Pod stays Pending → Karpenter provisions new node
        WaitForSpot --> E2Gate: New node Ready (timeout 30 min)
    }

    state E2Gate {
        [*] --> EndpointCheck: check_endpoints_for_node_pods()\ncurrent_step = endpoint_convergence
        EndpointCheck --> SoakByTier: All pod IPs in EndpointSlice
        SoakByTier --> Phase2Ready: Tier-aware kube-proxy soak complete\n(T4=10s, T3=20s, T2=30s, T0/T1=45s)
        EndpointCheck --> WaitNextCycle: Not yet routable → re-check next cycle (fail-open after 5 min)
    }

    state Phase2 {
        [*] --> SingleReplicaCheck: protect_single_replica() if replica=1\nScale 1→2, wait Ready
        SingleReplicaCheck --> EvictionGate: eviction_gate() per controller\nAtomic Redis lock (10s TTL)
        EvictionGate --> PreEvictionDelay: safe_to_evict() passed\n2s pre-eviction delay (kube-proxy sync)
        PreEvictionDelay --> Cordon: kubectl cordon old-node
        Cordon --> Drain: Evict pods with per-pod grace period\nSIGTERM → wait → SIGKILL if needed
        Drain --> StuckPodAssess: assess_stuck_pods()\nABORT + uncordon if unsafe to terminate
        StuckPodAssess --> TerminateEC2: terminate_instance_in_auto_scaling_group()
        TerminateEC2 --> CleanupNodePool: remove_allowed_instance_type()\nRestore original consolidateAfter from Redis baseline
        CleanupNodePool --> RestoreReplica: restore_single_replica() if scaled up
        RestoreReplica --> Cooldown: Set 24h cooldown
    }

    state S2SChecks {
        [*] --> RiskModeCheck: _s2s_risk_only_mode = NOT diversify_pools
        RiskModeCheck -->|"diversify OFF"| RiskOnly: Check 2 only — risk > ceiling?
        RiskModeCheck -->|"diversify ON"| Check0: Opportunistic — better risk AND savings?
        Check0 -->|"Yes"| S2STrigger
        Check0 -->|"No"| Check1: Pool-level — same (type, az) has >1 node?
        Check1 -->|"Yes"| S2STrigger
        Check1 -->|"No"| Check15: Family cap — family X > 40% of nodes?
        Check15 -->|"Yes"| S2STrigger
        Check15 -->|"No"| Check2: Risk threshold — current risk > ceiling?
        Check2 -->|"Yes"| S2STrigger
        Check2 -->|"No"| Skip
        RiskOnly -->|"Yes"| S2STrigger
        RiskOnly -->|"No"| Skip
        S2STrigger: Create S2S RebalancingAction → Phase 1/Phase 2
    }

    Phase1 --> E2Gate
    E2Gate --> Phase2
    Phase2 --> [*]: Optimization Complete
    Skip --> [*]: Next 15s cycle
```

---

## 4. Karpenter NodePool Injection — Detailed Flow

The inject/cleanup cycle is designed to be idempotent and non-destructive to the NodePool's existing configuration.

```mermaid
sequenceDiagram
    participant Celery as auto_rebalancer.py
    participant KSvc as karpenter_service.py
    participant Redis as Redis
    participant K8s as K8s API Server
    participant Karp as Karpenter Controller
    participant EC2 as AWS EC2

    Note over Celery: A6 — Resolve target NodePool from source node label
    Celery->>K8s: list_node(label_selector=karpenter.sh/nodepool)
    K8s-->>Celery: Node labels → _target_nodepool_name (e.g. "stateless-spot")

    Note over Celery: A5 — Inject only top-1 ML-ranked type
    Celery->>KSvc: add_allowed_instance_type("t3a.medium", nodepool="stateless-spot")
    KSvc->>Redis: GET karpenter:nodepool_baseline:{cid}:stateless-spot
    Redis-->>KSvc: None (first call)
    KSvc->>K8s: GET NodePool "stateless-spot"
    K8s-->>KSvc: Current spec with instance-type requirements + consolidateAfter=30s
    KSvc->>Redis: SET karpenter:nodepool_baseline (snapshot, TTL 24h)
    KSvc->>Redis: SET karpenter:nodepool_consolidate_after_baseline = "30s"
    KSvc->>Redis: SET spot:injected_type:{cid}:stateless-spot:t3a.medium (TTL 2h)
    KSvc->>K8s: PATCH NodePool — add t3a.medium to instance-type values\nAND set consolidateAfter=Never (freeze consolidation)
    Note over KSvc: ⚠️ NEVER modifies consolidationPolicy during injection\n consolidateAfter=Never is sufficient to freeze Karpenter

    Note over Celery: Enhancement 3 — Create trigger pod at end of Phase 1 (saves 15s)
    Celery->>K8s: Parallel label all existing nodes:\n  spot-optimizer.io/existing-node=true
    Celery->>KSvc: create_spot_trigger_pod(pod_name="spot-trigger-{action_id}",\n  target_instance_type="t3a.medium",\n  nodepool="stateless-spot",\n  exclude_nodes=[...existing...])
    KSvc->>K8s: CREATE Pod with:\n  nodeSelector: karpenter.sh/capacity-type=spot\n  nodeSelector: karpenter.sh/nodepool=stateless-spot\n  nodeAffinity.DoesNotExist: spot-optimizer.io/existing-node

    Note over Karp: Pod is Pending — Karpenter provisions new node
    Karp->>K8s: Read NodePool "stateless-spot" requirements
    Karp->>EC2: RunInstances (t3a.medium, target AZ)
    EC2-->>Karp: i-0abc123 (t3a.medium spot)
    Karp->>K8s: Register Node — no spot-optimizer.io/existing-node label (new node)
    Note over Karp: Trigger pod schedules to new node, becomes Running

    Note over Celery: E2 gate — wait for pod IPs in EndpointSlice + tier-aware soak
    Celery->>K8s: check_endpoints_for_node_pods(new_node)
    K8s-->>Celery: All pod IPs present and ready=True
    Note over Celery: Soak 10–45s based on workload tier

    Note over Celery: Phase 2 — Drain + Terminate old node
    Celery->>K8s: PATCH node (cordon)
    Celery->>K8s: Evict pods (per-pod grace, pre-eviction delay 2s)
    Celery->>EC2: terminate_instance_in_auto_scaling_group(old_instance_id)

    Note over Celery: Cleanup
    Celery->>KSvc: remove_allowed_instance_type("t3a.medium", "stateless-spot")
    KSvc->>Redis: GET karpenter:nodepool_consolidate_after_baseline
    Redis-->>KSvc: "30s"
    KSvc->>K8s: PATCH NodePool — restore to baseline types\nAND restore consolidateAfter=30s
    KSvc->>Redis: DEL baseline key (next injection starts fresh)
```

---

## 5. Consolidation Policy — Full Lifecycle

Karpenter's `consolidationPolicy` and `consolidateAfter` are managed at three independent points. All three must be consistent for correct behaviour.

```mermaid
flowchart TD
    subgraph A["① NodePool Creation (agent/actuator.py)"]
        A1["Creates 3 NodePools on Karpenter install\ndefault: WhenEmptyOrUnderutilized, 30s\nstateless-spot: WhenEmptyOrUnderutilized, 30s\nstateful-od: WhenEmpty, 60s"]
    end

    subgraph B["② User Toggles auto_rebalancing (karpenter_routes.py)"]
        B1{"auto_rebalancing\ntoggled?"}
        B2["ON → patch_consolidation_policy(\n  policy='WhenEmpty',\n  consolidate_after='Never'\n)\nAll NodePools patched atomically"]
        B3["OFF → patch_consolidation_policy(\n  policy='WhenEmptyOrUnderutilized',\n  consolidate_after='30s'\n)\nRestores native Karpenter behaviour"]
        B1 -->|"ON"| B2
        B1 -->|"OFF"| B3
    end

    subgraph C["③ Active Rebalance Injection (karpenter_service.py)"]
        C1["add_allowed_instance_type()\n→ Saves original consolidateAfter to Redis baseline\n→ Patches NodePool: consolidateAfter=Never\n   (does NOT touch consolidationPolicy)"]
        C2["remove_allowed_instance_type()\n→ Reads baseline from Redis\n→ Restores original consolidateAfter value\n→ Clears baseline key"]
        C1 --> C2
    end

    A --> B
    B --> C

    subgraph Result["Effective Policy at Runtime"]
        R1["rebalancing OFF:\nWhenEmptyOrUnderutilized + 30s\n→ Karpenter manages freely"]
        R2["rebalancing ON, idle:\nWhenEmpty + Never\n→ Karpenter only removes empty nodes"]
        R3["rebalancing ON, during injection:\nWhenEmpty + Never (unchanged)\n→ Karpenter frozen, rebalancer controls"]
    end

    B2 --> R2
    C1 --> R3
    C2 --> R2
    B3 --> R1
```

**`_update_nodepool()` design rule (verified in code):**  
The disruption block is **only included** in the PATCH body when the caller explicitly passes `consolidation_policy` or `consolidate_after`. Type-only updates (injections) never touch `spec.disruption`, so the policy set in step ② is always preserved.

---

## 6. Instance Type Selection Pipeline

```mermaid
flowchart TD
    Source["Source node chosen by rebalancer\ne.g. t3.medium (CPU 5%, Mem 20%)"]

    RSCheck{"auto_rightsizing_enabled?"}
    Source --> RSCheck

    RSCheck -->|"ON"| BinPack["Bin-pack: find smallest type\nfitting actual_usage + 30% buffer\nPool: 200+ types (DescribeInstanceTypeOfferings)"]
    RSCheck -->|"OFF"| SameSize["Keep same size class\ntarget family = t3/t3a or equivalent"]

    BinPack --> MLRank["pool_ranking_service.py\nML scoring: risk + savings + AZ distribution\nFilters: same arch, ≥2 AZ variants retained"]
    SameSize --> MLRank

    MLRank --> DryRun["Parallel dry-run validation\nThreadPoolExecutor(max_workers=5)\nCache: dry_run:{itype}:{az} (30 min TTL)"]
    DryRun --> A5["A5: Inject only TOP-1 ranked type\n(not up to 8 — keeps NodePool clean)"]
    A5 --> A6["A6: Inject into the NodePool\nthat owns the source node\n(karpenter.sh/nodepool label)"]
    A6 --> Retry["Enhancement 8: Non-blocking retry\nIf PATCH fails → status=deferred\nMax 3 attempts across Celery cycles"]
```

---

## 7. Eviction Safety Pipeline

All evictions run through a multi-layer safety pipeline before a pod is touched. Each check is independent; any failure blocks eviction without affecting other controllers.

```mermaid
flowchart TD
    DrainStart["Phase 2: Start draining old node"]

    subgraph SingleReplica["Layer 0 — Single-Replica Protection (P4)"]
        SR1{"replica_count == 1\nAND pdb_defined == False?"}
        SR2{"HPA with min=max=1?"}
        SR3["Scale Deployment 1→2\nWait for second pod Ready (2 min timeout)\nRollback on timeout"]
        SR1 -->|"Yes"| SR2
        SR2 -->|"Yes"| Block_HPA["EVICTION_BLOCKED_NO_CAPACITY\nCannot safely scale up"]
        SR2 -->|"No"| SR3
        SR1 -->|"No"| EvGate
        SR3 --> EvGate
    end

    subgraph EvGate["Layer 1 — Eviction Gate (P6) — eviction_safety.py"]
        EG1["Acquire Redis lock:\nspot:eviction_gate:{cid}:{ns}/{ctrl}\nTTL 10s, blocking_timeout 5s"]
        EG2["safe_to_evict(): check PDB budget\nactive_drains vs min_available\nNo PDB: only 1 drain at a time"]
        EG3{"KEDA managed?\n(keda_managed=True)"}
        EG4["queue_allows_migration()\ncheck spot:keda_metric\nvs spot:queue_baseline (ratio ≤ 1.5x)"]
        EG5["register_active_drain()\nINCR spot:active_drains:{cid}:{ns}/{ctrl}\nTTL 600s"]
        EG1 --> EG2
        EG2 -->|"Budget OK"| EG3
        EG2 -->|"Exhausted"| BlockPDB["Block — PDB exhausted\nRetry next Celery cycle"]
        EG3 -->|"Yes"| EG4
        EG3 -->|"No"| EG5
        EG4 -->|"Queue stable"| EG5
        EG4 -->|"QUEUE_SURGE"| BlockKEDA["Block — QUEUE_SURGE: ratio > 1.5x\nRetry when queue drains"]
    end

    subgraph Eviction["Layer 2 — Eviction Execution (P1 + P3)"]
        EV1["Pre-eviction delay: sleep 2s\n(kube-proxy propagation sync — P1)"]
        EV2["Read terminationGracePeriodSeconds\nfrom pod spec (P3 dynamic grace period)"]
        EV3["Create V1Eviction with actual grace period\nSpot interruption: cap at 60s (emergency flag)"]
        EV4{"PDB blocking\neviction? (429)"}
        EV5["Exponential backoff retry:\n10s→15s→22s→34s→50s (total ~131s)"]
        EV6["force=True path:\nSIGTERM (pod's grace period)\nWait → SIGKILL if still running (grace_period=0)"]
        EV1 --> EV2 --> EV3 --> EV4
        EV4 -->|"No"| Done["Pod evicted"]
        EV4 -->|"Yes — retry"| EV5 --> EV3
        EV4 -->|"Yes — force"| EV6 --> Done
    end

    subgraph StuckPod["Layer 3 — Stuck Pod Assessment (P5)"]
        SP1["After drain timeout:\nassess_stuck_pods()\nCategories: Unschedulable / VolumeFail / Unknown"]
        SP2["should_terminate_with_stuck_pods()\n→ OK if pods are DaemonSet or completed\n→ ABORT if Unschedulable with no capacity"]
        SP3["ABORT: uncordon source node\nDo NOT terminate EC2"]
        SP1 --> SP2
        SP2 -->|"Unsafe"| SP3
        SP2 -->|"Safe"| Terminate["Proceed to EC2 terminate"]
    end

    DrainStart --> SingleReplica
    EvGate --> Eviction
    Eviction --> StuckPod
    StuckPod --> Cleanup["release_active_drain()\nDECR spot:active_drains\nrestore_single_replica() if scaled up\nremove_allowed_instance_type() (cleanup NodePool)"]
```

---

## 8. Concurrency Controls

Three independent layers prevent concurrent operations from conflicting. They operate at different scopes.

```mermaid
flowchart TD
    subgraph L1["Layer 1: In-Flight AgentAction Guard (auto_rebalancer.py)"]
        direction LR
        LA1["Query AgentActions for cluster\nStatus = PENDING or PICKED_UP"]
        LA2{"Any active\nAgentActions?"}
        LA3{"Initial OD→Spot\nbatch? (bypass)"}
        LA1 --> LA2
        LA2 -->|"Yes"| LA3
        LA2 -->|"No"| PassL1["✅ Proceed"]
        LA3 -->|"Yes (OD batch)"| PassL1
        LA3 -->|"No (S2S mode)"| BlockL1["⛔ Skip cluster this cycle"]
    end

    subgraph L2["Layer 2: Per-Node Redis Lock (auto_rebalancer.py)"]
        direction LR
        LB1["Redis SET NX:\nspot:node_active_action:{instance_id}\nValue = action_id, TTL = 86400s (24h)"]
        LB2{"Acquired?"}
        LB1 --> LB2
        LB2 -->|"No (another action owns this node)"| BlockL2["⛔ Skip node\nDefer until TTL clears"]
        LB2 -->|"Yes"| PassL2["✅ Own this node for 24h"]
    end

    subgraph L3["Layer 3: Global Concurrent Action Semaphore"]
        direction LR
        LC1["Redis INCR rebalance:active_count\nTTL 3600s (safety reset)"]
        LC2{"count > 3\n(max concurrent)?"}
        LC1 --> LC2
        LC2 -->|"Yes"| BlockL3["⛔ DECR and break batch loop"]
        LC2 -->|"No"| PassL3["✅ Slot reserved"]
    end

    subgraph L4["Layer 4: Per-Controller Eviction Gate (eviction_safety.py)"]
        direction LR
        LD1["Redis LOCK:\nspot:eviction_gate:{cid}:{ns}/{ctrl}\nTTL 10s, blocking 5s"]
        LD2["Atomic PDB budget + KEDA queue check\nregister_active_drain() inside lock"]
        LD1 --> LD2
    end

    PassL1 --> L2
    PassL2 --> L3
    PassL3 --> L4
```

---

## 9. Three NodePools — Design & Ownership

```mermaid
flowchart LR
    subgraph NPs["Karpenter NodePools (created by agent/actuator.py)"]
        direction TB

        subgraph Default["NodePool: default  (weight=1, catch-all)"]
            D1["Capacity: spot + on-demand"]
            D2["Default types: m5.large, m5.xlarge\nm6i.large, m6i.xlarge, m6g.large\nm6g.xlarge, c5.large, c5.xlarge\nc6g.large, c6g.xlarge"]
            D3["Disruption: WhenEmpty (when rebalancing ON)\nconsolidateAfter: Never during injection\nRestored to 30s after cleanup"]
        end

        subgraph Stateless["NodePool: stateless-spot  (weight=10, preferred)"]
            S1["Capacity: spot only"]
            S2["Same default types"]
            S3["Labels: workload=stateless"]
            S4["Rebalancer injects into this pool when\nsource node carries karpenter.sh/nodepool=stateless-spot"]
        end

        subgraph Stateful["NodePool: stateful-od  (weight=5)"]
            SF1["Capacity: on-demand only"]
            SF2["Same default types"]
            SF3["Disruption: WhenEmpty, 60s\n(never downsized by Karpenter)"]
            SF4["Labels: workload=stateful"]
        end
    end
```

---

## 10. Rightsizing Rollback Pipeline

```mermaid
flowchart TD
    Exec["AgentAction: PATCH_CONTAINER_RESOURCES\nApplied to Deployment/StatefulSet\noriginal_resources saved to:\n  action.result.original_resources\n  spot:rightsize_monitor:{cid}:{ns}/{ctrl}"]

    Guard["resize_guard_worker.py\nMonitors CPU/Mem after resize\nIf regression detected:\n  → SET resize:rollback_needed:{cid} = reason"]

    Consumer["resize_rollback_consumer()\nPolls resize:rollback_needed:{cid}\nFinds recent FAILED proposals"]

    Rollback["Creates new AgentAction:\n  action_type = PATCH_CONTAINER_RESOURCES\n  payload.resources = original_resources\n  payload.is_rollback = True\nMarks proposal.status = ROLLED_BACK"]

    Exec --> Guard --> Consumer --> Rollback
```

---

## 11. UI Rebalancing Timeline (8 Steps)

The frontend (`RebalancingTimeline.jsx`) maps to these backend `current_step` values:

| Step | UI Label | Backend `current_step` | Notes |
|------|----------|------------------------|-------|
| 1 | NodePool Updated | `nodepool_updated` | Karpenter NodePool patched with top-1 ML type; consolidateAfter frozen |
| 2 | New Node Joined | `waiting_for_spot` → `spot_node_ready` | Trigger pod caused Karpenter to provision replacement |
| 3 | Endpoints Verified | `endpoint_convergence` | E2 gate: all pod IPs routable in EndpointSlice + tier soak |
| 4 | Node Cordoned | `cordon` | Source node marked unschedulable |
| 5 | Pods Drained | `drain` | Graceful eviction: per-pod grace period, 2s pre-delay, PDB backoff |
| 6 | Pods Rescheduled | `verifying_pod_readiness` | P5 stuck pod assessment; ABORT+uncordon if unsafe |
| 7 | Old Node Terminated | `terminate` | EC2 terminate only if P5 passes |
| 8 | Complete | `complete` | NodePool cleanup, consolidateAfter restored, cooldown set, replica restored |

> Step 3 (Endpoints Verified) is **implemented in backend** but shown as "Coming soon" in the UI (dashed dot) pending production validation.

**Execution order:** NodePool Updated → New Node Joined → **Endpoints Verified (pre-cordon E2 gate)** → Node Cordoned → Pods Drained → Pods Rescheduled → Old Node Terminated → Complete.

---

## 12. Complete Redis Key Reference

| Key Pattern | Set by | TTL | Purpose |
|-------------|--------|-----|---------|
| `karpenter:nodepool_baseline:{cid}:{np}` | `add_allowed_instance_type()` | 24h | Baseline instance-type list before injection (restore point) |
| `karpenter:nodepool_consolidate_after_baseline:{cid}:{np}` | `add_allowed_instance_type()` | — | Original consolidateAfter value, restored on cleanup |
| `spot:injected_type:{cid}:{np}:{itype}` | `add_allowed_instance_type()` | 2h | Per-injection presence key |
| `karpenter_config:{cluster_id}` | `karpenter_routes.py` | 24h | Full Karpenter config dict (diversify, policy, etc.) |
| `spot:karpenter:installed:{cluster_id}` | Agent heartbeat | — | Live-detection key (Karpenter installed flag) |
| `spot:karpenter_auth_verified:{cluster_id}` | Phase 1 pre-flight | — | EKS access entry verified cache |
| `spot:node_active_action:{instance_id}` | Phase 1 lock acquisition | 86400s | Per-node lock (one-at-a-time rebalance) |
| `rebalance:active_count` | Global semaphore | 3600s | Count of concurrent in-flight actions (max 3) |
| `dry_run:{itype}:{az}` | DryRun validator | 30 min | Cached parallel capacity check results |
| `spot:workload_profile:{cid}:{ns}/{ctrl}` | `workload_inspector.py` | scan TTL | Full workload profile (PDB, grace, tier, KEDA fields) |
| `spot:workload_tier:{cid}:{ns}/{ctrl}` | `workload_inspector.py` | scan TTL | Lightweight tier summary |
| `spot:workload_recommendations:{cid}` | `workload_inspector.py` | scan TTL | Cluster-wide misconfig recommendations |
| `spot:eviction_gate:{cid}:{ns}/{ctrl}` | `eviction_gate()` | 10s | Per-controller Redis lock (atomic pre-flight) |
| `spot:active_drains:{cid}:{ns}/{ctrl}` | `register_active_drain()` | 600s | Counter of in-flight drains per controller |
| `spot:keda_metric:{ns}/{ctrl}` | KEDA scraper | — | Current queue depth |
| `spot:queue_baseline:{ns}/{ctrl}` | KEDA baseline task | 3600s | Stable baseline for surge detection (ratio ≤ 1.5x) |
| `spot:migration_ready:{cid}:{ns}/{ctrl}` | `queue_allows_migration()` | 300s | KEDA zero-scale migration window flag |
| `spot:rightsize_monitor:{cid}:{ns}/{ctrl}` | Agent resize action | — | original_resources backup for rollback |
| `resize:rollback_needed:{cluster_id}` | `resize_guard_worker` | — | Trigger key for rollback consumer |

---

## 13. Open Issues

| # | Description | File | Severity |
|---|-------------|------|----------|
| 5 | `add_allowed_instance_type()` uses baseline-snapshot approach but if cleanup crashes mid-flight, the baseline key survives with stale types. Next injection appends to stale baseline → NodePool type list grows unbounded over time. Mitigation: 24h TTL on baseline key forces reset. **Fix needed:** periodic NodePool audit task to compare actual vs baseline. | `karpenter_service.py` | MEDIUM |
| 6 | Karpenter v1.0+ can autonomously expand instance families beyond the explicit NodePool list under certain EC2 capacity conditions. Even with `WhenEmpty`, if a node becomes empty via natural workload scale-down (not our drain), Karpenter may replace with a cheaper type it selects independently. **Fix needed:** explicit `instance-type` requirement with `operator: In` listing only approved types. | `actuator.py` (NodePool creation) | MEDIUM |
