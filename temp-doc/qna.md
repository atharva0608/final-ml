Viewed ActiveActions.jsx:411-426
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Edited ActiveActions.jsx
Ran command: `grep -i "dry_run" /Users/atharvapudale/Desktop/backend-ecc/Atharva\ Repo/github/final-ml/backend/workers/tasks/auto_rebalancer.py`
Searched for "AgentAction"

The reason you are seeing these execution records (and why they feel "fake" and disconnected from your AWS account) comes down to two architectural factors in the system:

### 1. Manual Execution Bypasses Automation Toggles
The "Auto Rebalancing" and "Auto Rightsizing" toggles in the cluster settings **only control the background cron worker** (unattended automation). 
However, if you (or anyone testing the UI) click "Execute Plan" or "Migrate" from the Workload Placement or Node Bin Packing screens, the backend generates an explicit placement plan and forcibly creates those `RebalancingAction` and `AgentAction` records in the database, regardless of whether the automation toggles are turned on.

### 2. The Agent Pull-Architecture (Why AWS isn't changing)
The backend does **not** communicate directly with AWS or the Kubernetes API. Instead, it uses an asynchronous pull-based model:
* When an execution starts, the backend creates `CORDON_NODE`, `DRAIN_NODE`, and `TERMINATE_NODE` records in the `agent_actions` database table.
* A lightweight Kubernetes Operator/Agent (which is supposed to be deployed in your actual cluster) constantly polls the `/api/v1/actions/poll` endpoint. 
* The Agent picks up the action, performs the actual Kubernetes API calls to cordon/drain the node, and reports the success/failure back to the backend.

**The Problem:**
If nothing is actually happening in your AWS account, it means either:
1. **The Kubernetes Agent is not deployed/running** in your cluster, so the actions are timing out or being processed by a local mock/seeder script used for UI testing.
2. **Dry-Run Mode is Active:** The backend worker (`auto_rebalancer.py`) has a `DRY_RUN` mode for Karpenter. If the backend detects it cannot reach the cluster or Karpenter is in dry-run mode, it will simulate the state transitions in the database without actually requesting Spot instances from AWS.

**Summary:** You are seeing historical database records of manual UI test executions, but because the cluster-side Agent is either missing or mocked, the database state advanced without any actual AWS infrastructure mutations.

Viewed placement_rollout_service.py:1-419

Here is exactly how your Pod Distribution and Rollout Plan works in the backend, based on the `PlacementRolloutService` and orchestration engine.

### 1. What sequences are used? (The Rollout Strategies)
The system uses two completely different strategies depending on the workload and the migration path:

**Strategy A: "Create-Before-Delete" (High-Availability Migration)**
Used primarily for moving critical Deployments (like Gold-tier workloads) from **OD to Spot**. 
1. **Pre-check:** Verifies if there is actual Spot capacity.
2. **Lock:** Annotates the current On-Demand node with `karpenter.sh/do-not-disrupt=true` so Karpenter doesn’t kill the node mid-migration.
3. **Scale Up:** Increases workload replicas by `+1`.
4. **Placement Verification:** Checks if the Kubernetes scheduler *actually* placed the new pod on a Spot node. (If it landed on OD again, it scales back down and aborts to prevent a loop).
5. **Wait:** Waits for the new pod to become ready.
6. **Evict:** Explicitly evicts the *old* pod from the On-Demand node.
7. **Unlock:** Removes the `do-not-disrupt` annotation so Karpenter can spin down the empty OD node.

**Strategy B: Node-Level Rebalancing (Cordon & Drain)**
Used for **OD to OD consolidation**, **Spot to Spot topology spreading**, and importantly, **StatefulSets**. 
Because StatefulSets have ordinal identities (pod-0, pod-1) and bound storage, "Strategy A" (+1 replica) is fundamentally unsafe. The engine explicitly rejects them and routes them to Node-level migration where the entire source node is cordoned and drained, relying on Kubernetes to recreate the pods on the target node pool.

### 2. How does it check Pod Health?
The `PlacementRolloutService` does not poll the Kubernetes API directly. Instead, it relies on your Kubernetes Agent pushing metrics to Redis. 
The backend polls the Redis key `spot:workload:state:{cluster_id}:{workload_id}` and checks two exact metrics:
1. `ready_replicas` must be `>=` the target amount.
2. `unhealthy_pending_pods` must equal `0`. 
If a pod crash-loops or gets stuck pending, the timeout triggers (usually 2 minutes) and the migration is rolled back.

### 3. Current State & Problems (Why it's failing/mocking)
The logic flow is highly robust, but **the execution layer is incomplete/mocked**. 

If you look at the `PlacementRolloutService` code:
* The `_trigger_pod_eviction()` function literally just contains `pass`. It does absolutely nothing.
* The `_annotate_node()` function only contains a `logger.debug()` statement. It does not actually queue an `AgentAction` to annotate the node.
* Only `_scale_workload` and `_evict_pod` (the newer v1.4 methods) actually write to the database.

**The Problem:** The rollout engine has world-class logic to ensure zero-downtime migrations, but half of the vital Kubernetes commands (like protecting the node from Karpenter during migration) are mocked out and not actually dispatching `AgentActions` to your cluster agent.  

To make your migration and replica strategy work flawlessly—especially considering PVCs and the Karpenter controller node—here are the **best architectural changes** we need to implement in the codebase:

### 1. Protect the Karpenter "Anchor" Node (Avoid Self-Destruction)
If Karpenter runs on a node that it also manages, it might accidentally consolidate its own node and terminate itself, freezing the cluster.
**The Fix:** 
We must update the `PodPlacementEngine` to automatically detect which node is running the `karpenter` controller pods. The engine must flag this specific On-Demand node as an "Anchor" and automatically inject the `karpenter.sh/do-not-disrupt: "true"` annotation. This ensures Karpenter handles every other OD node in the cluster, but leaves its own host alone.

### 2. Handle PVCs Correctly (Bypass "+1 Scaling")
Currently, the `PlacementRolloutService` tries to do a "Create-before-delete" (+1 scale up) for zero-downtime migrations. 
**The Fix:** 
AWS EBS volumes (PVCs) are `ReadWriteOnce`. This means the new replica cannot mount the storage volume while the old replica is still running. We must add a check in the rollout service: **If a Deployment has a PVC attached, it must bypass the "+1 scaling" strategy**. It must be routed to the Node-Level Drain strategy (cordon the node, delete the pod, let Kubernetes reattach the PVC to the new node). 

### 3. Implement the Missing Kubernetes Agent Commands
As discovered earlier, the rollout service is currently "mocking" the critical Kubernetes commands. 
**The Fix:** 
In `backend/services/placement_rollout_service.py`, we need to replace the `pass` statements in `_trigger_pod_eviction()` and `_annotate_node()` with actual database inserts that queue `AgentAction`s. This will command your in-cluster agent to actually perform the Kubernetes API calls (evicting the pod and tagging the nodes).

### 4. Pod Disruption Budgets (PDBs) Integration
During scale-downs or node draining, we need to ensure workloads don't go completely offline. 
**The Fix:** 
We need to ensure the backend rollout engine respects `minAvailable` and `maxUnavailable` PDB thresholds before it queues an `EVICT_POD` action. If a StatefulSet or critical DB only has 1 replica, the engine should optionally trigger an EBS Snapshot before executing the drain.


alos we need real time validator is reaaly the node terminated is really pod drain etc all areal life action should be validated real time 