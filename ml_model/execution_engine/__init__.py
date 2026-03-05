"""
Execution Engine — Agent Command Dispatch Layer
================================================

The Execution Engine is the "hands" of the ML system.
After the Decision Engine approves an action, the Execution Engine
actually carries it out by sending commands to the Kubernetes agent.

ARCHITECTURE OVERVIEW
----------------------

  Backend (Python)
  ├── 01_action_queue.py     — Creates AgentAction records in PostgreSQL
  │                            Auto-rebalancer reads Decision Engine output →
  │                            creates CORDON_NODE + DRAIN_NODE + PATCH_KARPENTER_NODEPOOL records
  │
  ├── 02_command_dispatcher.py — Sends queued commands to the cluster agent
  │                              Primary path: WebSocket push (real-time)
  │                              Fallback path: HTTP polling (agent polls every 10s)
  │
  └── 05_substitute_manager.py — Manages warm spare instances
                                  Uses Redis state machine (IDLE → PREWARMING → READY → ACTIVE)
                                  Ensures a replacement spot node is always ready before drain

  Kubernetes Cluster (DaemonSet Agent)
  ├── 03_k8s_actuator.py     — Executes Kubernetes operations
  │                            cordon_node(), drain_node(), evict_pod()
  │                            label_node(), update_deployment()
  │
  ├── 04_karpenter_controller.py — Manages Karpenter CRDs
  │                                patch_karpenter_nodepool() → tells Karpenter what spot pool to use
  │                                install_karpenter() → helm upgrade --install
  │                                _create_default_karpenter_resources() → EC2NodeClass + NodePool
  │
  └── 06_result_reporter.py  — Reports action results back to backend
                                POST /api/v1/agents/actions/{id}/result

FULL EXECUTION FLOW
--------------------

  1. Decision Engine APPROVES action
     → recommendation["pool"] = target spot pool
     → recommendation["action_type"] = "POOL_SWITCH"

  2. Auto-rebalancer (Celery task, runs every 15s) reads decision
     → Creates 3 AgentAction records in DB:
         CORDON_NODE   — mark node unschedulable (no new pods)
         DRAIN_NODE    — evict existing pods (they reschedule on other nodes)
         PATCH_KARPENTER_NODEPOOL — tell Karpenter to provision spot node

  3. Agent picks up actions via WebSocket (or HTTP polling)
     → execute_action_v2(action_type, payload)

  4. Agent executes in order:
     a. CORDON_NODE → kubectl cordon <node>
        Effect: New pods won't schedule here. Existing pods stay.

     b. DRAIN_NODE → kubectl drain <node>
        Effect: Evicts all pods. They reschedule on other nodes (on-demand for now).
        Key: After drain, the node is empty but still running. Karpenter manages the rest.

     c. PATCH_KARPENTER_NODEPOOL → patch NodePool CRD with target instance type
        Effect: Karpenter sees pods PENDING (no room) → provisions a new SPOT node
        of the target type. Pods reschedule on the new spot node.
        ⚠️ NOTE: This only works if the old node is TERMINATED (not just drained)!
                 See the "Why Drain Alone Doesn't Work" section below.

  5. Agent reports result → POST /api/v1/agents/actions/{id}/result

  6. Backend confirms action completed → update RebalancingAction status

WHY DRAIN ALONE DOESN'T TRIGGER KARPENTER
-------------------------------------------
Karpenter provisions new nodes ONLY when pods are PENDING (no available node).
After drain:
  - Pods are evicted from the drained node
  - They try to reschedule → existing on-demand nodes have capacity
  - Pods land on OTHER on-demand nodes → NOT PENDING
  - Karpenter sees no pending pods → does NOT provision a spot node
  - Result: No real migration happens in AWS

To trigger Karpenter:
  - The drained node MUST BE TERMINATED (EC2 termination via AWS API)
  - Then: pods from all remaining on-demand nodes can't fit → some become PENDING
  - Karpenter sees PENDING pods → provisions new spot node matching NodePool requirements
  - Pods land on spot node → migration complete

This is why the auto-rebalancer's real-world effect requires EC2 termination
after drain (future enhancement tracked in auto_rebalancer.py TODO comments).

Files in this package:
  01_action_queue.py      — Backend: AgentAction creation (auto_rebalancer.py)
  02_command_dispatcher.py — Backend: WebSocket + HTTP dispatch to agent
  03_k8s_actuator.py      — Agent: K8s operations (cordon, drain, evict)
  04_karpenter_controller.py — Agent: Karpenter NodePool + install
  05_substitute_manager.py — Backend: Warm spare lifecycle (Redis state machine)
  06_result_reporter.py   — Agent: Report results back to backend
  pipeline.py             — Orchestrator that ties all steps together
"""
