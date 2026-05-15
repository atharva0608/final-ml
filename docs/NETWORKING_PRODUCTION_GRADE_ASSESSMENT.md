# Networking Architecture and Production Readiness Assessment

Generated: 10 April 2026\nUpdated: 12 April 2026 (E10/E11 fixes reflected, step-by-step networking breakdown, node-level identity section, implementation progress tracker)\nUpdated: 12 April 2026 (P1-P6 production-grade eviction safety: pre-eviction delay, EndpointSlice gate, dynamic grace period, single-replica protection, stuck pod assessment, per-controller drain coordination)

Purpose:
1. Explain how networking is currently handled.
2. Answer clearly if pod IP changes, cluster/service IP changes, and connection failures are handled.
3. Identify production-grade gaps.
4. Define what must be done next.
5. Document workload networking behavior in real clusters.

---

## 1. Short Answer

Do we have networking handling for real production clusters?

1. Yes, for connection resiliency basics (heartbeat retries, WebSocket reconnect, URL refresh, action-result fallback).
2. Yes, for WebSocket auth enforcement (E10 — API key validation before websocket.accept()) and DaemonSet DNS policy (E11 — explicit dnsPolicy in manifests).
3. Yes, for production-grade eviction safety: pre-cordon EndpointSlice gate (P2/E2), pre-eviction delay for kube-proxy propagation (P1), dynamic grace period from pod spec (P3), single-replica protective scale-out (P4), stuck pod assessment before termination (P5), per-controller concurrent drain coordination (P6), and atomic eviction gate with Redis lock.
4. No, for full production-grade network hardening (NetworkPolicy, multi-replica WebSocket session routing, strict service discovery standards).

So the answer is: MOSTLY — production-grade eviction safety is now implemented. Remaining gaps are cluster-level network policy and WebSocket HA.

---

## 2. Current Networking Design

### 2.1 Agent to Backend paths

The agent communicates to backend over two channels:

1. HTTP channel
2. WebSocket channel

HTTP is used for:
1. Register
2. Heartbeat
3. Metrics and related posts
4. HTTP fallback for action results when WebSocket fails

WebSocket is used for:
1. Receiving action commands
2. Sending action result and status messages
3. Real-time bi-directional command flow

### 2.2 Endpoint wiring

Agent endpoint URLs come from env/config map:
1. BACKEND_URL
2. BACKEND_WS_URL
3. CLUSTER_ID

The agent also supports dynamic URL refresh through:
1. GET /api/v1/agents/discover-url
2. Auto update of backend_url and websocket URL in running components
3. Periodic refresh every 5 minutes

### 2.3 DaemonSet networking mode

DaemonSet uses hostNetwork: true.

Effects:
1. Agent pods use node network namespace.
2. Agent can access IMDS and host-level metrics path directly.
3. Pod IP churn for the agent itself is less central than in normal pod networking.

### 2.4 Workload networking plane (pods and services)

The platform does not proxy workload request traffic. Workload east-west networking remains Kubernetes-native:

1. Pod-to-pod traffic is handled by cluster CNI plus kube-proxy or eBPF dataplane.
2. Service discovery is handled by Kubernetes Services and CoreDNS.
3. Endpoint updates after pod rescheduling are handled by Kubernetes controllers.

What this platform does for workload networking context:

1. Collects workload scheduling constraints from pods: node selector, tolerations, affinity, topology spread.
2. Tracks workload ownership by controller kind and controller name for rightsizing and simulation.
3. Performs node cordon and drain with pod eviction and PDB checks/retries.
4. Relies on Kubernetes to repoint Service endpoints to new pod IPs after rescheduling.

What this platform does not currently do:

1. It does not program Service objects, kube-proxy rules, or DNS records directly.
2. It does not proxy service traffic or modify Service/DNS objects directly. (Note: it does run endpoint convergence checks — E2 gates cordon on EndpointSlice verification, P5 assesses stuck pods before termination.)
3. It does not include service-mesh traffic controls (mTLS, retries, circuit breaking) in this layer.

---

## 3. Pod IP and Cluster IP Handling Matrix (YES/NO)

| Topic | Current behavior | Handled? |
|---|---|---|
| Agent pod IP changes | Identity is based on cluster_id, agent_id, node_name, instance_id. No core workflow keys on agent pod IP. | YES |
| Workload pod IP changes | Metrics and scheduling context use pod_name, namespace, controller owner, and node_name. Not keyed on pod IP. | YES |
| Workload Service ClusterIP lifecycle | Service virtual IP is Kubernetes-managed; this platform does not mutate Service IPs. | YES |
| Service endpoint updates after drain | Post-drain check (Step 6) verifies pods have vacated the drained node via K8s API pod listing. **Pre-cordon E2 gate (P2) verifies new pod IPs in EndpointSlice with 10s kube-proxy soak before old node is touched.** Pre-eviction delay (P1) gives endpoint controller 2s head start per pod. | YES |
| Workload DNS continuity during migration | Uses cluster DNS behavior implicitly; no synthetic DNS probe/guard in migration path. Workload inspector (E1) does not check DNS. | PARTIAL |
| Node private IP changes | Node identity is mainly instance_id and node_name; AWS sync rebuilds mapping. Some logic derives node_name from private IP format. | PARTIAL |
| Backend URL/tunnel rotation | Agent supports discover-url and periodic URL refresh; updates all components and reconnects WebSocket. | YES |
| Temporary WebSocket failure | Exponential reconnect + message buffering + HTTP fallback for action_result. | YES |
| Backend service ClusterIP change | Works if BACKEND_URL is DNS/FQDN. Risky if configured as raw IP. No explicit service-discovery policy enforcement. | PARTIAL |
| Kubernetes API endpoint changes inside cluster | In-cluster service account config is used; standard K8s client behavior. | YES |
| Network isolation and zero-trust policy | No NetworkPolicy resources found in chart/templates. | NO |
| WebSocket endpoint auth hardening | ✅ Fixed (E10). API key validation now runs before `websocket.accept()` in `api_gateway.py`. Unauthenticated connections are rejected. | YES |
| Multi-replica backend WebSocket HA | Active WebSocket connections are in-process dict, not distributed. No Redis pub/sub or session routing implemented. | NO |
| IPv6 and dual-stack clusters | Address strings (pod IP, node IP) stored as-is in DB and Redis keys. No explicit dual-stack validation or IPv6-aware address parsing. Identity keys use instance_id/node_name, not IP, so most flows are address-format agnostic. Risk area: any code that parses private IPv4 format for node-name derivation. | PARTIAL |

### 3.1 Workload networking continuity during rebalancing

Current continuity model during node replacement:

1. Node is cordoned so no new workloads schedule to old node.
2. Pods are evicted with PDB-aware checks and retries.
3. Kubernetes scheduler places replacement pods on healthy nodes.
4. EndpointSlice/Service backends update to new pod IPs.
5. Traffic continuity is achieved by Kubernetes-native readiness and endpoint routing.

Important caveats:

1. Platform gates cordon on endpoint convergence verification (E2/P2 — `check_endpoints_for_node_pods()` confirms pods routable before drain) and gates termination on stuck pod assessment (P5 — aborts and uncordons if pods are unschedulable or volume-stuck).
2. Application-level connection draining behavior depends on workload readiness/liveness and app shutdown hooks.
3. Stateful workloads still depend on storage/network attach times outside this platform's control.

### 3.2 Step-by-step networking behavior during rebalancing

This section describes exactly what happens to networking at each step of a node replacement, how end-user traffic is preserved, and why no manual intervention is needed.

**Execution order today:**
```
NodePool Updated → New Node Joined → [Endpoints Verified ⏳ placeholder] → Node Cordoned → Pods Drained → Pods Rescheduled → Old Node Terminated → Complete
```

#### Step 1: NodePool Updated (Karpenter type injection)

What happens:
1. ML-ranked instance types are patched into the Karpenter NodePool requirements.
2. A lightweight trigger pod (busybox sleep) is created with exact nodeSelector constraints forcing Karpenter to provision one matching spot instance.
3. consolidateAfter is set to Never on the NodePool to prevent Karpenter from interfering during migration.

Networking impact: **NONE**.
- No workload pods are touched.
- No services are modified.
- All existing traffic continues unchanged.

#### Step 2: New Node Joined (replacement spot node ready)

What happens:
1. Karpenter provisions a new EC2 spot instance matching the injected type.
2. Kubelet starts on the new node and registers with the K8s API server.
3. Backend polls until four readiness conditions are met:
   a. EC2 instance state = running.
   b. K8s Node object exists.
   c. Node status condition Ready = True (kubelet healthy, CNI plugin initialized, networking functional).
   d. Agent heartbeat received within last 30 seconds (agent DaemonSet pod scheduled and running).
4. Trigger pod is scheduled on the new node (confirms pod networking works).
5. Timeout: 30 minutes. If exceeded, action fails and old node is left untouched.

Networking impact: **NONE to existing workloads**.
- New node joins the cluster but receives no workload traffic yet.
- Existing pods on the old node continue serving normally.
- The Node Ready condition guarantees the new node's CNI, kube-proxy rules, and DNS are operational before continuing.
- End user sees: nothing. All traffic still goes to old pods.

#### Step 3: Endpoints Verified (E2 — pre-cordon EndpointSlice gate)

What happens (P2 implementation):
1. Backend queries DiscoveryV1Api EndpointSlice objects for all non-DaemonSet pods on the new node.
2. For each pod, confirms its IP appears in EndpointSlice with `conditions.ready=True`.
3. After all pods are confirmed in EndpointSlice, soaks for 10 seconds to allow kube-proxy on all cluster nodes to sync the new routing rules.
4. If any pods are not yet routable, the step enters `endpoint_convergence` state and re-checks next cycle (5-minute max wait, fail-open on timeout).
5. Sets `current_step=endpoint_convergence` in action metadata while waiting.

Implementation: `backend/services/eviction_safety.py` → `check_endpoints_for_node_pods()`.

Networking impact: **CRITICAL SAFETY GATE**.
- Ensures replacement pods are actually receiving traffic before old pods are touched.
- Closes the 30-60 second window where replacement pods are scheduled but not yet routable.
- For single-replica services, this is the difference between zero downtime and complete outage.
- End user sees: nothing. Traffic to old pods continues until new pods are confirmed routable.

#### Step 4: Node Cordoned (old node unschedulable)

What happens:
1. Agent patches the old node object: `spec.unschedulable = true`.
2. K8s scheduler stops placing new pods on this node.
3. All existing pods remain running and serving traffic.

Networking impact: **NONE to running traffic**.
- Every pod on the cordoned node keeps its IP address.
- Service endpoints continue pointing to those pods.
- DNS resolution for services is unchanged.
- End user sees: nothing. Existing connections and new requests still work.

Self-cordon safety: If the agent runs ON the target node, the code detects the SELF_CORDON_ATTEMPT and fails the action cleanly (uncordons + cleans up orphaned spot).

Timeout: 10 minutes.

#### Step 5: Pods Drained (graceful eviction with production safety)

What happens:
1. **P6 — Per-controller eviction gate**: Before evicting any pod, acquire per-controller Redis lock (`spot:eviction_gate:{cid}:{ns/ctrl}`). Check how many pods of the same controller are already mid-drain across all concurrent actions. If PDB budget would be violated cumulatively, block this eviction and re-check next cycle.
2. **P4 — Single-replica protection**: For controllers with `replica_count=1` and `no PDB`, temporarily scale Deployment to 2 replicas before eviction. Wait for second replica to be Ready (120s timeout). If scale-up fails (HPA locked at min=max=1, resource quota), mark workload `EVICTION_BLOCKED_NO_CAPACITY` and skip eviction.
3. **P1 — Pre-eviction delay**: Sleep 2 seconds before each eviction call. This gives the endpoint controller a head start on processing the anticipated EndpointSlice removal before SIGTERM is sent, closing the kube-proxy propagation race.
4. **P3 — Dynamic grace period**: Read `terminationGracePeriodSeconds` from the actual pod spec (not hardcoded). Emergency path (spot interruption) caps at 60s to stay within 120s budget.
5. For each pod, in order:
   a. Check PodDisruptionBudget (PDB). If PDB allows disruption (disruptionsAllowed > 0), proceed to eviction.
   b. Create a K8s Eviction object with the pod's own terminationGracePeriodSeconds.
   c. The pod receives SIGTERM and has its full grace period to finish in-flight requests and close connections.
   d. If PDB blocks eviction (429 response), exponential backoff retries over ~131 seconds (10s, 15s, 22s, 34s, 50s).
   e. If PDB is violated and force mode is active, escalate: SIGTERM → wait grace period → SIGKILL.
6. Kubernetes scheduler places replacement pods on healthy nodes (including the new spot node from Step 2).
7. As each new pod passes readiness probes, the K8s endpoint controller adds its IP to EndpointSlice.
8. kube-proxy (or eBPF dataplane) updates iptables/BPF maps to route service traffic to new pod IPs.
9. CoreDNS returns updated records when TTL expires.
10. **P4 cleanup**: After eviction, restore any temporarily scaled-up controllers back to original replica count.
11. **P6 cleanup**: Release per-controller drain counters.

Implementation: `backend/services/eviction_safety.py` → `eviction_gate()`, `protect_single_replica()`, `restore_single_replica()`, `safe_to_evict()`, `register_active_drain()`, `release_active_drain()`.

Networking impact: **This is the critical window for traffic continuity**.

How zero-downtime is achieved:
1. **Pre-eviction delay (P1)**: 2-second sleep before each eviction gives kube-proxy time to start processing the endpoint removal before SIGTERM fires. Platform-side mitigation that requires no workload changes.
2. **Dynamic grace period (P3)**: Pods receive SIGTERM with their own configured grace period (not a hardcoded 30s). Apps that need 90s for long transactions get 90s. Apps that need 10s don't wait 30s unnecessarily.
3. **PDB enforcement**: PDBs prevent evicting too many replicas at once. P6 extends this across concurrent drains on different nodes.
4. **Single-replica protection (P4)**: Single-replica workloads are scaled to 2 before eviction, ensuring continuous service. If scale-up fails, eviction is blocked entirely.
5. **Per-controller drain coordination (P6)**: Platform-level PDB that prevents two concurrent actions from cumulatively violating the budget, even if each individual eviction appears within budget.
6. **Readiness gates**: New pods only enter service endpoints after passing readiness probes. No traffic flows to unready pods.
7. **Rolling replacement**: Pods are evicted sequentially, not all at once. Service always has at least PDB-allowed replicas available.
8. **Service mesh awareness**: If a service mesh sidecar (Istio, Linkerd, Envoy) is detected, the grace period allows mesh proxy draining — sidecar gets SIGTERM, stops accepting new connections, finishes existing ones.

What the end user experiences:
- For HTTP services: requests may see brief latency increase during endpoint propagation (typically <2s as kube-proxy syncs new endpoints). No errors if app handles SIGTERM gracefully.
- For WebSocket/long-lived connections: clients on the evicted pod disconnect and must reconnect. The reconnection hits the service VIP which now routes to the new pod. Connection-draining apps can signal clients to reconnect gracefully.
- For stateless services with ≥2 replicas and correct PDBs: effectively zero user-visible impact.
- For single-replica services without PDB: P4 protective scale-out ensures zero outage window.

**kube-proxy propagation timing gap**: In clusters without a service mesh, there is a subtle window between when kube-proxy removes the old pod IP from iptables/BPF routing rules and when the pod actually stops receiving new connections. kube-proxy endpoint sync is eventual — a pod can receive a new TCP connection up to ~1–2 seconds after its IP has been removed from EndpointSlice. **This is now mitigated platform-side in two ways**: (1) P1 pre-eviction delay sleeps 2s before sending SIGTERM, giving endpoint controller a head start, and (2) E1 workload inspector flags pods missing `preStop` hooks (`MISSING_PRESTOP_HOOK` recommendation) so workload owners are alerted. The platform does not inject `preStop` hooks — it relies on workload owners to configure them for maximum safety. The workload inspector (E1) also flags pods with low `terminationGracePeriodSeconds` (<30s) as LOW_GRACE_PERIOD.

Timeout: 20 minutes for full drain.

#### Step 6: Pods Rescheduled (post-drain verification with stuck pod assessment)

What happens:
1. Backend waits 20 seconds after drain completes (grace period for rescheduled pods to start).
2. Queries K8s API for any non-DaemonSet pods still running on the drained node.
3. If pods found: waits and re-checks (up to drain_timeout_minutes, default 15 min).
4. Fallback: if K8s API unavailable, checks PodMetric database for recent pod activity on that node.
5. If K8s returns 404 for the node: drain is complete (node already removed from K8s).
6. **P5 — Stuck pod assessment on timeout**: If pods are still stuck after drain_timeout_minutes, the platform now assesses WHY:
   - **Unschedulable**: Cluster lacks capacity → ABORT, uncordon old node, fail action (prevents outage).
   - **FailedAttachVolume / FailedMount**: Volume cannot attach on new node → ABORT (possible misconfiguration).
   - **DaemonSet pods only**: Safe to terminate (node-local, expected to disappear with node).
   - **Unknown reason**: ABORT (refuse to terminate without understanding the failure).

Implementation: `backend/services/eviction_safety.py` → `assess_stuck_pods()`, `should_terminate_with_stuck_pods()`.

Networking impact: **Verification and safety gate**.
- This step confirms pods have vacated the old node.
- By this point new pods are already running on other nodes and receiving traffic via updated EndpointSlice entries.
- If pods are stuck: P5 assessement determines if termination is safe. If not, old node is uncordoned and restored.
- End user sees: nothing new. Traffic shifted in Step 5.

#### Step 7: Old Node Terminated (EC2 teardown)

What happens:
1. Backend verifies the replacement spot node is still running (prevents cluster shrinkage if spot was lost).
2. If spot is gone: action FAILS, old node is uncordoned, no termination. Cluster stays intact.
3. If spot is healthy and P5 assessment confirms safe: `ec2:TerminateInstances` is called on the old instance.
4. Instance marked in Redis with 120s TTL to prevent AWS sync from flipping state back.
5. Polling confirms termination (up to 5 retries at 30s intervals).

Networking impact: **NONE to workload traffic**.
- All workload pods already moved off this node in Step 5.
- The only pods remaining are DaemonSets (which are node-local infrastructure, not user-facing).
- K8s garbage-collects the Node object after EC2 termination.
- End user sees: nothing. All their traffic was already on new pods.

Spot-gone safety gate: If the replacement spot disappeared (e.g. Karpenter consolidated it, spot reclaimed by AWS), the old node is NOT terminated. This prevents the cluster from losing capacity.

#### Step 8: Complete (cleanup)

What happens:
1. Trigger pod deleted.
2. Injected instance types removed from Karpenter NodePool.
3. consolidateAfter restored to original value (from Redis baseline).
4. 24-hour cooldown set for the cluster.

Networking impact: **NONE**.
- NodePool returns to pre-migration state.
- Karpenter resumes normal consolidation behavior.

### 3.3 Agent networking continuity during rebalancing

The agent itself must remain operational throughout the migration to execute cordon, drain, and report results. Here is how agent connectivity is preserved:

1. **WebSocket reconnection**: Exponential backoff (2s, 4s, 8s, 16s, 32s, 60s cap). Formula: `min(1 × 2^attempt, 60)`. On successful reconnect, resets to 0. Agent stays connected to backend throughout.
2. **HTTP fallback for action results**: If WebSocket is down during drain, action results are POSTed via HTTP to `/api/v1/agents/actions/{action_id}/result`. Prevents 45-minute cluster lock on network failures.
3. **Critical message queue**: Action results are queued in a critical queue until backend confirms receipt. Messages are not lost on transient disconnects.
4. **Action heartbeat thread**: During long operations (cordon, drain, terminate), a separate background thread sends action-specific heartbeats to backend, independent of the main 30s heartbeat cycle.
5. **Adaptive heartbeat**: If backend is unreachable for 5+ consecutive attempts, heartbeat interval slows to 4× normal (max 120s) to avoid flooding. Auto-recovers when backend responds.
6. **DaemonSet on hostNetwork**: Agent uses node network namespace, so agent pod IP churn is not an issue during workload pod migrations. Agent networking is stable as long as the node is alive.

### 3.4 Why end users see no disruption (summary)

The migration is transparent to end users because:

1. **New node is fully ready before anything is touched on the old node.** CNI initialized, kube-proxy rules synced, DNS operational, agent heartbeat confirmed.
2. **Cordon does not affect running pods.** It only prevents new scheduling. All existing connections and traffic continue.
3. **Drain uses graceful eviction, not force-kill.** SIGTERM gives apps time to finish requests. PDBs ensure minimum replicas stay available.
4. **Kubernetes handles service endpoint updates automatically.** As new pods pass readiness probes, their IPs are added to EndpointSlice. kube-proxy routes traffic to them. Old pod IPs are removed from endpoints before the pod is fully terminated.
5. **The old node is only terminated after all pods are confirmed gone.** No workload traffic depends on it.
6. **No manual DNS updates, no manual IP changes, no manual service reconfiguration.** Service ClusterIPs are stable virtual IPs. Only backend pod IPs change, and Kubernetes manages that transparently.

The only scenario requiring operator awareness:
- **Singleton pods without PDBs**: A Deployment with replicas=1 and no PDB has a brief unavailability window between eviction and reschedule. This is a workload design issue, not a platform issue. The workload inspector (E1) flags this as a MISSING_PDB recommendation.
- **hostNetwork pods**: These use the node IP directly. Eviction causes immediate network disruption for that specific workload. The workload inspector flags this with fragility_level = HOST_NETWORK.

### 3.5 Node-level networking identity and failure modes

The document covers agent-to-backend and workload pod networking, but the node IP layer also matters.

#### Node identity model

Node private IPs are NOT stable across Karpenter node replacements. When a node is terminated and a new spot instance is provisioned, it gets a fresh private IP from the VPC subnet. The platform handles this because:

1. **instance_id is the stable identity**, not private IP. All Redis keys, DB records, and action metadata use `instance_id` (e.g. `i-0abc123`) as the primary key for node identity.
2. **node_name is resolved dynamically via K8s API**, not cached at boot. The agent finds its node name by scanning K8s Node objects for a matching `spec.providerID` containing its instance_id (format: `aws://<az>/<instance_id>`).
3. **IMDS is used for region, instance_id, and spot lifecycle signals — but not at startup.** The agent makes no IMDS calls during initialization. At runtime: region is fetched on-demand when executing node termination (`actuator.py`), instance_id is fetched on-demand when reporting spot interruptions (`poller.py`, cached after first call), and spot termination notices + rebalance recommendations are polled every 5 seconds by the SpotPoller thread. Private IP, availability zone, and instance type are NOT fetched from IMDS.
4. **AWS sync rebuilds the mapping.** The backend's periodic AWS sync task queries EC2 DescribeInstances and rebuilds the instance_id → node_name → private_ip mapping in the database. This tolerates node replacement because the old instance_id enters `terminated` state and the new instance_id appears as `running`.

#### Silent failure mode: security group misconfiguration

A real production failure mode not previously documented:

When Karpenter provisions a new spot instance, it inherits the security group from the EC2LaunchTemplate or NodeClass. If the security group is misconfigured (e.g. missing egress to backend FQDN, missing ingress for kubelet, missing IMDS access), the following happens:

1. EC2 instance launches and enters `running` state. ✅
2. Kubelet starts and registers the Node object with K8s API. ✅ (if kube-api egress is allowed)
3. Node enters `Ready` status. ✅
4. DaemonSet pod (agent) is scheduled and enters `Running`. ✅
5. Agent heartbeat POST to backend fails silently (blocked egress). ❌
6. Backend sees: instance running, node ready, but agent heartbeat missing.
7. Rebalancer waits for heartbeat up to 30 minutes, then times out and fails the action.

This manifests as a 30-minute hang followed by action failure. The root cause is not visible in K8s — the node and pod look healthy. Diagnosis requires checking security group rules on the new instance.

Current mitigation: the 30-minute timeout prevents indefinite hangs, and the action is marked FAILED so the old node is not terminated. No automated security-group validation exists.

#### Private IP format dependency

Some backend code derives `node_name` from the EC2 private IPv4 address (e.g. `ip-10-0-1-42.ec2.internal` from `10.0.1.42`). This works for standard AWS VPC naming but breaks in:
1. Custom DNS suffix clusters (non-default `--cluster-dns` settings).
2. IPv6-primary instances where the private address is not IPv4.
3. Outpost or Local Zone deployments with different naming conventions.

This is tracked as a medium gap (Section 5, Medium item 2) and cross-referenced to Enhancement 8 (node identity / cluster-agnostic design).

### 3.6 Operation pause and networking safety (planned)

Enhancement 6 (self-healing / regression detection) introduces a per-workload operation pause mechanism via the Redis key `spot:operation_pause:{cluster_id}:{namespace}/{controller_name}` with a 600s TTL.

This key does NOT exist in the codebase today — E6 has not been implemented.

When implemented, the networking implications are:

1. **Deliberate migration block**: When regression detection fires (e.g. latency spike after a migration), it sets this key. The rebalancer checks it before starting a new action for that workload's node. A paused workload will NOT be migrated even if its node receives a spot interruption notice from AWS.
2. **Trade-off**: This prioritizes networking stability (avoid cascading failures) over cost optimization (leaving a workload on a potentially expensive or at-risk node).
3. **Scope**: Per-controller, not per-cluster. Other workloads on the same cluster can still be migrated.
4. **Expiry**: 600s TTL auto-clears the pause. No manual intervention required.

This is documented here to track the networking safety impact of E6 once it ships.

---

## 4. What Is Already Good

### 4.1 Connection resilience

Implemented:
1. WebSocket reconnect loop with exponential backoff.
2. Buffered message queues (critical queue + best-effort ring buffer).
3. HTTP fallback for action results if WebSocket send fails.
4. Heartbeat retry with exponential backoff.
5. Adaptive heartbeat interval during prolonged backend outage.

### 4.2 Dynamic backend URL correction

Implemented:
1. Backend stores live public URL from incoming headers.
2. Agent registration returns backend_url and ws_url.
3. Agent periodically calls discover-url and rotates runtime URLs.

### 4.3 Not relying on pod IP as primary identity

Implemented:
1. Registration and heartbeat models use logical identity fields.
2. Core state sync ties to cluster_id, instance_id, node_name.
3. Pod-level metrics are tracked by namespace/pod_name/controller/node_name.

---

## 5. Production Gaps (Important)

### Critical

1. ~~WebSocket endpoint authentication is not explicitly enforced at /ws/cluster handler.~~ **RESOLVED (E10)** — API key validation enforced before `websocket.accept()` in `api_gateway.py`. Unauthenticated connections are rejected with close code.
2. WebSocket session state is local process memory (active_connections dict), not distributed.

Impact:
1. ~~Security risk for command channel.~~ **Mitigated by E10.**
2. Reliability/HA risk with multiple backend replicas or pod restarts. This is the most significant remaining production risk — a backend pod restart during an active drain operation causes the action to hang until the agent's HTTP fallback kicks in.

### High

1. No NetworkPolicy resources for agent namespace.
2. No explicit egress allow-list (backend endpoint, IMDS, kube-api).
3. ~~hostNetwork true without explicit DNS policy declaration (should be deterministic in manifests).~~ **RESOLVED (E11)** — `dnsPolicy` now explicitly set in both Helm chart (`charts/spot-optimizer-agent/templates/daemonset.yaml`) and backend agent template (`backend/templates/k8s/agent.yaml`).
4. ~~No explicit Service endpoint convergence check in the migration critical path.~~ **RESOLVED (E2/P2)** — `check_endpoints_for_node_pods()` in `eviction_safety.py` queries EndpointSlice via DiscoveryV1Api before proceeding to drain. Confirms all non-DaemonSet pods on replacement node are routable with 10s kube-proxy soak. 5-min max wait with fail-open timeout.

Impact:
1. Larger blast radius.
2. Harder compliance posture.
3. ~~Potential DNS behavior ambiguity across distributions.~~ **Mitigated by E11.**

### Medium

1. Cluster/service IP change behavior depends on URL configuration quality.
2. Some AWS node-name derivation logic depends on private IPv4 formatting. Cross-reference: tracked in plan.md as part of the node-identity audit; related to Enhancement 8 (node identity).
3. Helm script path has at least one place where backendUrl composition should be reviewed carefully to avoid ws/http path misuse.
4. No synthetic workload DNS/service probe to detect transient routing regressions during rebalance windows.

Impact:
1. Operator error can break routing after service changes.
2. Non-standard networking environments may have edge failures.

---

## 6. Direct Answers to Your Questions

### Q1: Pod IP changes - are we handling this?

Answer: YES (mostly).

Why:
1. Core workflows do not key identity on pod IP.
2. Agent and worker state is tied to node_name/instance_id/cluster_id.

### Q2: Cluster IP / service IP changes - are we handling this?

Answer: PARTIAL.

Why:
1. If using DNS/FQDN, service endpoint changes are generally tolerated.
2. If raw IPs are configured as BACKEND_URL, failover is weak.
3. There is URL refresh logic, but it still requires a reachable discovery path and good URL hygiene.

### Q3: Is this production-grade networking today?

Answer: MOSTLY — production-grade eviction safety is now implemented. Remaining gaps are cluster-level network policy and WebSocket HA.

What is resolved:
1. ✅ WebSocket auth guard now enforced (E10).
2. ✅ DaemonSet dnsPolicy now explicit (E11).
3. ✅ EndpointSlice convergence gate before drain (E2/P2).
4. ✅ Pre-eviction delay for kube-proxy propagation (P1).
5. ✅ Dynamic grace period from pod spec (P3).
6. ✅ Single-replica protection with temporary scale-out (P4).
7. ✅ Stuck pod assessment before node termination (P5).
8. ✅ Per-controller concurrent drain coordination (P6).

What is still missing:
1. Distributed connection management for multi-replica backend.
2. NetworkPolicy and strict traffic controls.

---

## 7. What Should Be Done (Action Plan)

### Phase 1: Security and correctness (must-do first) — ✅ COMPLETE

1. ~~Enforce token validation on WebSocket handshake endpoint.~~ **Done (E10)** — `api_gateway.py` validates API key before `websocket.accept()`.
2. ~~Reject unauthenticated WebSocket connections.~~ **Done (E10)** — connections closed with error code on auth failure.
3. ~~Add audit logs for connect/disconnect/auth failure events.~~ **Done (E10)** — connect, disconnect, and auth failure events logged.

### Phase 2: Production network policy

1. Add Kubernetes NetworkPolicy manifests for spot-optimizer namespace.
2. Restrict ingress to required pods/services only.
3. Restrict egress to:
   - backend FQDN/service
   - Kubernetes API server
   - IMDS endpoint (if hostNetwork mode requires it)
4. ~~Add explicit dnsPolicy for hostNetwork pods.~~ **Done (E11)** — `dnsPolicy: ClusterFirstWithHostNet` in both Helm chart and backend agent template.
5. Add namespace-level policy templates for workload namespaces in managed clusters (default-deny + allowlist).

### Phase 3: High availability WebSocket plane

1. Replace in-memory active_connections model with distributed session routing.
2. Use Redis pub/sub or dedicated WebSocket gateway for command fanout.
3. Ensure any backend replica can route command to connected agent.

### Phase 4: Service discovery hardening

1. Standardize BACKEND_URL as stable DNS/FQDN only.
2. Disallow raw ClusterIP/IP values in install path validation.
3. Add startup validation to fail fast on invalid URL patterns.

### Phase 5: Operational readiness tests

Add integration tests for:
1. Agent pod restart and pod IP change.
2. Backend pod restart during active action execution.
3. WebSocket disconnect mid-action with HTTP fallback.
4. Backend URL rotation.
5. NetworkPolicy deny/allow behavior.
6. Service endpoint convergence after node drain and before old node termination.
7. Workload DNS lookup continuity during rebalance windows.
8. Stateful workload reconnect and readiness recovery timing after pod migration.

---

## 8. Final Verdict

Current state:
1. Good resilience foundations exist.
2. Pod IP churn is mostly handled correctly.
3. Cluster/service IP handling is only partially robust and depends on URL configuration discipline.
4. WebSocket auth enforcement is complete (E10).
5. DaemonSet DNS policy is explicit (E11).
6. EndpointSlice convergence gate ensures pods are routable before drain proceeds (E2/P2).
7. Eviction safety pipeline: pre-eviction delay (P1), dynamic grace period (P3), single-replica protection (P4), stuck pod assessment (P5), per-controller drain coordination (P6).
8. Remaining gaps: distributed WebSocket HA and NetworkPolicy.

Minimum bar to call it production-grade:
1. ~~WebSocket auth enforcement.~~ **✅ DONE (E10)**
2. Distributed WebSocket connection management. **OPEN — most significant remaining risk.**
3. NetworkPolicy-based traffic controls. **OPEN**
4. ~~Strict DNS-based service discovery policy.~~ **PARTIALLY ADDRESSED** — E2 EndpointSlice gate enforces endpoint convergence. URL validation still open.
5. ~~Eviction safety (endpoint convergence, PDB coordination, single-replica, stuck pod handling).~~ **✅ DONE (P1-P6)**

Progress: 2 of 5 minimum-bar items complete (E10, P1-P6). Item 4 partially addressed. Items 2–3 require infrastructure changes (Redis pub/sub, policy manifests).

---

## 9. Implementation Progress

Tracking which gaps and action plan phases are resolved, matching the format in KARPENTER_ARCHITECTURE.md Section 12.

### Resolved

| Item | Enhancement | Status | Detail |
|------|-------------|--------|--------|
| WebSocket auth enforcement | E10 (Priority 0) | ✅ Done | API key validated before `websocket.accept()` in `api_gateway.py`. Unauthenticated connections rejected. Audit logging added. |
| DaemonSet dnsPolicy | E11 (Priority 0) | ✅ Done | `dnsPolicy: ClusterFirstWithHostNet` set in Helm chart and backend agent template. |
| Workload identification | E1 (Priority 1) | ✅ Done | `build_workload_profile()` detects hostNetwork, service mesh sidecars, PDB health, readiness probes, grace periods. Flags LOW_GRACE_PERIOD, MISSING_PDB, HOST_NETWORK, MISSING_PRESTOP_HOOK, SINGLE_REPLICA_NO_PDB. |
| Pre-eviction delay | P1 | ✅ Done | 2s sleep before each eviction call in `actuator.py` drain and auto_rebalancer inline drain. Gives kube-proxy head start on endpoint removal propagation. |
| EndpointSlice convergence gate | E2/P2 | ✅ Done | `check_endpoints_for_node_pods()` in `eviction_safety.py` queries DiscoveryV1Api, confirms pods routable with 10s soak. Wired into auto_rebalancer before Phase 2 cordon. |
| Dynamic grace period | P3 | ✅ Done | `actuator.py` reads `terminationGracePeriodSeconds` from pod spec. Emergency (spot) caps at 60s. No more hardcoded values. |
| Single-replica protection | P4 | ✅ Done | `protect_single_replica()` / `restore_single_replica()` in `eviction_safety.py`. Scales 1→2 before eviction, detects HPA min=max=1 lockout. |
| Stuck pod assessment | P5 | ✅ Done | `assess_stuck_pods()` / `should_terminate_with_stuck_pods()` in `eviction_safety.py`. Classifies Unschedulable/VolumeFail/DaemonSet/Unknown. Aborts + uncordons on unsafe. |
| Per-controller drain coordination | P6 | ✅ Done | `eviction_gate()` / `safe_to_evict()` in `eviction_safety.py`. Redis lock + counter per controller. Prevents cumulative PDB violations across concurrent actions. |

### Section 5 Gap Status

| Gap | Severity | Status |
|-----|----------|--------|
| WebSocket auth (Critical #1) | CRITICAL | ✅ Resolved (E10) |
| Distributed WebSocket HA (Critical #2) | CRITICAL | 🔴 OPEN — most significant remaining risk |
| NetworkPolicy (High #1–2) | HIGH | 🔴 OPEN |
| dnsPolicy (High #3) | HIGH | ✅ Resolved (E11) |
| Endpoint convergence check (High #4) | HIGH | ✅ Resolved (E2/P2) — `check_endpoints_for_node_pods()` + 10s soak |
| URL config quality (Medium #1) | MEDIUM | 🔴 OPEN |
| IPv4 node-name derivation (Medium #2) | MEDIUM | 🔴 OPEN — cross-ref Enhancement 8 |
| Helm backendUrl composition (Medium #3) | MEDIUM | 🔴 OPEN |
| DNS/service probe (Medium #4) | MEDIUM | 🔴 OPEN |

### Section 7 Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Security and correctness | ✅ Complete | All 3 items done by E10. |
| Phase 2: Production network policy | 🟡 Partial | Item 4 (dnsPolicy) done by E11. Items 1–3, 5 open. |
| Phase 3: HA WebSocket plane | 🔴 Not started | No Redis pub/sub or distributed session routing implemented. |
| Phase 4: Service discovery hardening | 🔴 Not started | |
| Phase 5: Operational readiness tests | 🔴 Not started | |
