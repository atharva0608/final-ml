"""
Eviction Safety Module
======================

Production-grade pre-flight checks for pod eviction during node migrations.
Implements solutions for:

- Problem 2: Pre-cordon EndpointSlice gate (E2) — wait_for_routable()
- Problem 4: Single-replica protective scale-out — protect_single_replica()
- Problem 5: Stuck pod assessment before termination — assess_stuck_pods()
- Problem 6: Per-controller concurrent drain check — safe_to_evict()
- Execution guarantee: Per-controller Redis lock — eviction_gate()
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# W6 — Tier-based kube-proxy soak time (seconds) after pod IP appears in EndpointSlice.
# Higher-criticality tiers get a longer soak to ensure traffic stability before
# the old pod is touched.
KUBE_PROXY_SOAK_BY_TIER: Dict[int, int] = {
    0: 45,  # TIER_0: NEVER_MIGRATE — conservative default if somehow reached
    1: 45,  # TIER_1: ANCHORED_MANUAL — stateful databases, max soak
    2: 30,  # TIER_2: SPOT_WITH_CAUTION — KEDA-managed stateful workloads
    3: 20,  # TIER_3: KEDA_GATED — queue workers
    4: 10,  # TIER_4: SPOT_ELIGIBLE — stateless (current default)
}


# ── Problem 2: Pre-cordon EndpointSlice gate (E2) ─────────────────────────

def wait_for_routable(
    core_v1,
    discovery_v1,
    namespace: str,
    service_name: str,
    new_pod_ip: str,
    min_ready_seconds: int = 10,
    max_attempts: int = 30,
    poll_interval: int = 2,
) -> bool:
    """
    Wait until a new pod IP is confirmed routable via EndpointSlice.

    Two-phase check:
    1. Confirm pod IP appears in EndpointSlice with ready=True.
    2. Soak for min_ready_seconds to allow kube-proxy propagation across all nodes.

    Args:
        core_v1: K8s CoreV1Api client
        discovery_v1: K8s DiscoveryV1Api client
        namespace: Pod namespace
        service_name: Name of the K8s Service backing this workload
        new_pod_ip: IP address of the new pod to verify
        min_ready_seconds: Soak time after EndpointSlice confirmation (kube-proxy sync)
        max_attempts: Max polling attempts (each poll_interval apart)
        poll_interval: Seconds between polls

    Returns:
        True if pod is confirmed routable; False if timeout/failure (blocks cordon)
    """
    confirmed_in_slice = False
    confirmed_at = None

    for attempt in range(max_attempts):
        try:
            slices = discovery_v1.list_namespaced_endpoint_slice(
                namespace,
                label_selector=f"kubernetes.io/service-name={service_name}",
            )
            for es in slices.items:
                for ep in (es.endpoints or []):
                    if (
                        new_pod_ip in (ep.addresses or [])
                        and ep.conditions
                        and ep.conditions.ready
                    ):
                        confirmed_in_slice = True
                        confirmed_at = time.monotonic()
                        break
                if confirmed_in_slice:
                    break
        except Exception as e:
            logger.warning(
                f"[eviction_safety] EndpointSlice check failed for "
                f"{namespace}/{service_name}: {e}"
            )

        if confirmed_in_slice:
            break

        time.sleep(poll_interval)

    if not confirmed_in_slice:
        logger.warning(
            f"[eviction_safety] Pod IP {new_pod_ip} NOT found in EndpointSlice "
            f"for {namespace}/{service_name} after {max_attempts * poll_interval}s — "
            f"blocking cordon"
        )
        return False

    # Phase 2: Soak for kube-proxy propagation
    logger.info(
        f"[eviction_safety] Pod IP {new_pod_ip} confirmed in EndpointSlice for "
        f"{namespace}/{service_name} — soaking {min_ready_seconds}s for kube-proxy sync"
    )
    time.sleep(min_ready_seconds)
    return True


# ── W6.2: Tier-aware EndpointSlice gate ────────────────────────────────────

def wait_for_routable_tier_aware(
    core_v1,
    discovery_v1,
    namespace: str,
    service_name: str,
    new_pod_ip: str,
    tier: int = 4,
    max_attempts: int = 30,
    poll_interval: int = 2,
) -> bool:
    """
    Tier-aware wrapper for wait_for_routable().

    Selects the kube-proxy soak time based on workload tier so critical
    workloads get a longer traffic-convergence window before the old pod
    is touched.

    Args:
        tier: Workload tier (0-4). 0/1=NEVER/ANCHORED get 45s, 4=SPOT_ELIGIBLE gets 10s.

    Returns:
        True if pod is confirmed routable; False if timeout.
    """
    soak = KUBE_PROXY_SOAK_BY_TIER.get(tier, KUBE_PROXY_SOAK_BY_TIER[4])
    logger.debug(
        f"[eviction_safety] wait_for_routable_tier_aware: "
        f"tier={tier}, soak={soak}s for {namespace}/{service_name}"
    )
    return wait_for_routable(
        core_v1=core_v1,
        discovery_v1=discovery_v1,
        namespace=namespace,
        service_name=service_name,
        new_pod_ip=new_pod_ip,
        min_ready_seconds=soak,
        max_attempts=max_attempts,
        poll_interval=poll_interval,
    )


# ── W6.3: Verify new pod is serving traffic ─────────────────────────────────

def verify_new_pod_serving(
    core_v1,
    namespace: str,
    pod_name: str,
    readiness_initial_delay_s: int = 0,
    extra_wait: int = 30,
    poll_interval: int = 5,
) -> bool:
    """
    Verify a new pod has reached Ready state before touching the old pod.

    Polls the pod's Ready condition. Waits up to
    ``readiness_initial_delay_s + extra_wait + 120`` seconds total so
    slow-start workloads (e.g. JVM cold-start) are not declared failed
    prematurely.

    Args:
        readiness_initial_delay_s: Value of readinessProbe.initialDelaySeconds
            from the pod spec (used to skip the initial blind period).
        extra_wait: Additional seconds to wait after initial delay (default 30s).

    Returns:
        True if pod is Ready; False if timed out.
    """
    max_wait = readiness_initial_delay_s + extra_wait + 120  # hard cap
    deadline = time.monotonic() + max_wait

    while time.monotonic() < deadline:
        try:
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            conditions = pod.status.conditions or []
            ready_cond = next((c for c in conditions if c.type == "Ready"), None)
            if ready_cond and ready_cond.status == "True":
                logger.info(
                    f"[eviction_safety] Pod {namespace}/{pod_name} is Ready — "
                    f"verified serving traffic"
                )
                return True
        except Exception as e:
            logger.warning(
                f"[eviction_safety] verify_new_pod_serving read error for "
                f"{namespace}/{pod_name}: {e}"
            )

        time.sleep(poll_interval)

    logger.warning(
        f"[eviction_safety] Pod {namespace}/{pod_name} NOT ready after "
        f"{max_wait}s — proceeding cautiously"
    )
    return False


# ── W6.4: Wait for KEDA worker job completion ────────────────────────────────

def wait_for_job_completion(
    core_v1,
    namespace: str,
    pod_name: str,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Tuple[bool, str]:
    """
    Wait for a KEDA-managed worker pod to complete its current job before eviction.

    Polls pod phase. Returns as soon as phase is Succeeded or Failed (job done)
    or Terminating (already draining).

    Args:
        max_wait: Maximum seconds to wait (default 300s / 5 min).

    Returns:
        (completed, reason)
    """
    deadline = time.monotonic() + max_wait

    while time.monotonic() < deadline:
        try:
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            phase = (pod.status.phase or "Unknown")

            if phase in ("Succeeded", "Failed"):
                return True, f"Pod completed with phase={phase}"

            if pod.metadata.deletion_timestamp:
                return True, "Pod already terminating"

        except Exception as e:
            logger.warning(
                f"[eviction_safety] wait_for_job_completion read error for "
                f"{namespace}/{pod_name}: {e}"
            )
            return False, f"API error: {e}"

        time.sleep(poll_interval)

    return False, f"Job not completed after {max_wait}s — proceeding (timeout)"


def check_endpoints_for_node_pods(
    core_v1,
    discovery_v1,
    namespace_filter: Optional[str],
    new_node_name: str,
    min_ready_seconds: int = 10,
    timeout_seconds: int = 120,
) -> Tuple[bool, List[str]]:
    """
    Verify that all non-DaemonSet pods on a new node have their IPs
    in EndpointSlice (i.e., are routable).

    This is the aggregate E2 gate — checks ALL services backed by pods
    on the new node before allowing cordon of the old node.

    Returns:
        (all_routable, list_of_unroutable_pod_names)
    """
    unroutable = []
    start = time.monotonic()

    try:
        pods = core_v1.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={new_node_name},status.phase=Running",
        ).items

        # Filter to non-DaemonSet pods only
        workload_pods = [
            p for p in pods
            if not any(
                o.kind == "DaemonSet"
                for o in (p.metadata.owner_references or [])
            )
        ]

        if not workload_pods:
            # No workload pods on new node yet — OK to proceed
            # (trigger pod is the only thing there)
            return True, []

        for pod in workload_pods:
            pod_ip = pod.status.pod_ip if pod.status else None
            if not pod_ip:
                unroutable.append(
                    f"{pod.metadata.namespace}/{pod.metadata.name} (no IP)"
                )
                continue

            # Find services that select this pod
            pod_labels = pod.metadata.labels or {}
            if not pod_labels:
                continue  # No labels → no service → skip endpoint check

            # Check if this pod's IP is in any EndpointSlice
            found_in_slice = False
            try:
                slices = discovery_v1.list_namespaced_endpoint_slice(
                    pod.metadata.namespace,
                )
                for es in slices.items:
                    for ep in (es.endpoints or []):
                        if (
                            pod_ip in (ep.addresses or [])
                            and ep.conditions
                            and ep.conditions.ready
                        ):
                            found_in_slice = True
                            break
                    if found_in_slice:
                        break
            except Exception:
                pass

            if not found_in_slice:
                unroutable.append(
                    f"{pod.metadata.namespace}/{pod.metadata.name} ({pod_ip})"
                )

    except Exception as e:
        logger.warning(f"[eviction_safety] check_endpoints_for_node_pods failed: {e}")
        return True, []  # Fail-open: don't block on API errors

    if unroutable:
        elapsed = time.monotonic() - start
        logger.info(
            f"[eviction_safety] {len(unroutable)} pod(s) on {new_node_name} not yet "
            f"routable after {elapsed:.1f}s: {unroutable[:5]}"
        )
        return False, unroutable

    # All pods routable — soak for kube-proxy propagation
    logger.info(
        f"[eviction_safety] All pods on {new_node_name} confirmed in EndpointSlice "
        f"— soaking {min_ready_seconds}s for kube-proxy sync"
    )
    time.sleep(min_ready_seconds)
    return True, []


# ── Problem 4: Single-replica protective scale-out ─────────────────────────

def protect_single_replica(
    apps_v1,
    core_v1,
    namespace: str,
    controller_name: str,
    controller_kind: str,
    timeout: int = 120,
    poll_interval: int = 5,
) -> Dict:
    """
    For single-replica workloads with no PDB, temporarily scale to 2 replicas
    before eviction. Wait for the second replica to be Ready, then proceed.

    Returns:
        {
            "scaled": bool,
            "original_replicas": int,
            "reason": str,           # if not scaled
            "eviction_blocked": bool, # if True, caller must NOT evict
        }
    """
    result = {
        "scaled": False,
        "original_replicas": 1,
        "reason": "",
        "eviction_blocked": False,
    }

    # ── Unsupported kinds gate ─────────────────────────────────────────
    if controller_kind not in ("Deployment", "ReplicaSet", "StatefulSet"):
        result["reason"] = f"Unsupported controller kind: {controller_kind}"
        return result

    try:
        # ── StatefulSet path (W3.0a) ──────────────────────────────────
        if controller_kind == "StatefulSet":
            sts = apps_v1.read_namespaced_stateful_set(controller_name, namespace)
            current_replicas = sts.spec.replicas or 1
            result["original_replicas"] = current_replicas

            if current_replicas != 1:
                result["reason"] = f"Already has {current_replicas} replicas"
                return result

            # OnDelete strategy: scaling has no effect — block eviction entirely
            update_strategy = sts.spec.update_strategy
            if update_strategy and getattr(update_strategy, "type", None) == "OnDelete":
                result["reason"] = "StatefulSet uses OnDelete update strategy — cannot protective scale"
                result["eviction_blocked"] = True
                return result

            # Check for HPA with min=max=1 targeting this StatefulSet
            try:
                from kubernetes.client import AutoscalingV2Api
                autoscaling = AutoscalingV2Api()
                hpas = autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace)
                for hpa in hpas.items:
                    ref = hpa.spec.scale_target_ref
                    if (
                        ref.kind == "StatefulSet"
                        and ref.name == controller_name
                        and hpa.spec.min_replicas == 1
                        and hpa.spec.max_replicas == 1
                    ):
                        result["reason"] = "HPA locks StatefulSet replicas at min=max=1"
                        result["eviction_blocked"] = True
                        return result
            except Exception:
                pass  # HPA check is best-effort

            # Scale to 2.
            # For OrderedReady (default): pod-1 starts only after pod-0 is Running+Ready.
            # For Parallel: both pods come up simultaneously.
            # Either way wait until ready_replicas >= 2.
            apps_v1.patch_namespaced_stateful_set(
                controller_name, namespace,
                body={"spec": {"replicas": 2}},
            )
            logger.info(
                f"[eviction_safety] Scaled StatefulSet {namespace}/{controller_name} "
                f"1→2 (protective scale-out before eviction)"
            )

            waited = 0
            while waited < timeout:
                time.sleep(poll_interval)
                waited += poll_interval
                sts = apps_v1.read_namespaced_stateful_set(controller_name, namespace)
                ready = sts.status.ready_replicas or 0
                if ready >= 2:
                    result["scaled"] = True
                    logger.info(
                        f"[eviction_safety] StatefulSet {namespace}/{controller_name} "
                        f"has 2 ready replicas — safe to evict"
                    )
                    return result

            # Timeout: PVC provisioning delay or resource pressure
            logger.warning(
                f"[eviction_safety] StatefulSet {namespace}/{controller_name} scale-up "
                f"to 2 timed out after {timeout}s — rolling back and blocking eviction"
            )
            apps_v1.patch_namespaced_stateful_set(
                controller_name, namespace,
                body={"spec": {"replicas": 1}},
            )
            result["reason"] = "StatefulSet scale-up timed out — PVC provisioning or resource pressure"
            result["eviction_blocked"] = True
            return result

        # ── Deployment / ReplicaSet path ──────────────────────────────
        if controller_kind == "Deployment":
            deploy = apps_v1.read_namespaced_deployment(controller_name, namespace)
            current_replicas = deploy.spec.replicas or 1
            result["original_replicas"] = current_replicas

            if current_replicas != 1:
                result["reason"] = f"Already has {current_replicas} replicas"
                return result

            # Check for HPA with min=max=1 (locked replicas)
            try:
                from kubernetes.client import AutoscalingV2Api
                autoscaling = AutoscalingV2Api()
                hpas = autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace)
                for hpa in hpas.items:
                    ref = hpa.spec.scale_target_ref
                    if (
                        ref.kind == "Deployment"
                        and ref.name == controller_name
                        and hpa.spec.min_replicas == 1
                        and hpa.spec.max_replicas == 1
                    ):
                        result["reason"] = "HPA locks replicas at min=max=1"
                        result["eviction_blocked"] = True
                        return result
            except Exception:
                pass  # HPA check is best-effort

            # Scale up to 2
            apps_v1.patch_namespaced_deployment(
                controller_name, namespace,
                body={"spec": {"replicas": 2}},
            )
            logger.info(
                f"[eviction_safety] Scaled {namespace}/{controller_name} from 1→2 "
                f"(protective scale-out before eviction)"
            )

            # Wait for second replica to be Ready
            waited = 0
            while waited < timeout:
                time.sleep(poll_interval)
                waited += poll_interval
                deploy = apps_v1.read_namespaced_deployment(controller_name, namespace)
                ready = deploy.status.ready_replicas or 0
                if ready >= 2:
                    result["scaled"] = True
                    logger.info(
                        f"[eviction_safety] {namespace}/{controller_name} has 2 ready "
                        f"replicas — safe to evict"
                    )
                    return result

            # Timeout: scale-up failed (resource quota, scheduling issues)
            logger.warning(
                f"[eviction_safety] {namespace}/{controller_name} scale-up to 2 timed "
                f"out after {timeout}s — rolling back to 1 and blocking eviction"
            )
            apps_v1.patch_namespaced_deployment(
                controller_name, namespace,
                body={"spec": {"replicas": 1}},
            )
            result["reason"] = "Scale-up timed out — insufficient capacity"
            result["eviction_blocked"] = True
            return result

    except Exception as e:
        logger.warning(
            f"[eviction_safety] protect_single_replica failed for "
            f"{namespace}/{controller_name}: {e}"
        )
        result["reason"] = f"Error: {e}"
        result["eviction_blocked"] = True
        return result

    return result


def restore_single_replica(
    apps_v1,
    namespace: str,
    controller_name: str,
    original_replicas: int = 1,
    controller_kind: str = "Deployment",
):
    """Scale a controller back to its original replica count after eviction.

    Supports Deployment and StatefulSet (W3.0b).
    Idempotent — safe to call multiple times from a finally block.
    """
    try:
        if controller_kind == "StatefulSet":
            apps_v1.patch_namespaced_stateful_set(
                controller_name, namespace,
                body={"spec": {"replicas": original_replicas}},
            )
        else:
            apps_v1.patch_namespaced_deployment(
                controller_name, namespace,
                body={"spec": {"replicas": original_replicas}},
            )
        logger.info(
            f"[eviction_safety] Restored {controller_kind} {namespace}/{controller_name} to "
            f"{original_replicas} replica(s)"
        )
    except Exception as e:
        logger.warning(
            f"[eviction_safety] Failed to restore replicas for "
            f"{namespace}/{controller_name}: {e}"
        )


# ── Problem 5: Stuck pod assessment before termination ─────────────────────

def assess_stuck_pods(
    core_v1,
    stuck_pods: list,
    cluster_id: str,
) -> List[Dict]:
    """
    Assess WHY pods are stuck after drain — determines whether the old node
    can be safely terminated or must be uncordoned.

    Args:
        core_v1: K8s CoreV1Api client
        stuck_pods: List of stuck pod objects (from K8s API)
        cluster_id: Cluster identifier

    Returns:
        List of {pod, reason, message, safe_to_terminate} dicts
    """
    assessments = []

    for pod in stuck_pods:
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace

        # Skip DaemonSet pods — they are node-local and expected to disappear
        owner_refs = pod.metadata.owner_references or []
        is_daemonset = any(o.kind == "DaemonSet" for o in owner_refs)
        if is_daemonset:
            assessments.append({
                "pod": f"{namespace}/{pod_name}",
                "reason": "DAEMONSET",
                "message": "Node-local DaemonSet pod — will disappear with node",
                "safe_to_terminate": True,
            })
            continue

        # Check events for scheduling failure reasons
        reason = "UNKNOWN"
        message = ""
        safe_to_terminate = False

        try:
            events = core_v1.list_namespaced_event(
                namespace,
                field_selector=f"involvedObject.name={pod_name}",
            )
            for event in events.items:
                if event.reason in ("Unschedulable", "FailedScheduling"):
                    reason = "UNSCHEDULABLE"
                    message = event.message or "Pod cannot be scheduled"
                    safe_to_terminate = False
                    break
                elif event.reason == "FailedAttachVolume":
                    reason = "VOLUME_ATTACH_FAILURE"
                    message = event.message or "Volume cannot attach on new node"
                    safe_to_terminate = False
                    break
                elif event.reason == "FailedMount":
                    reason = "VOLUME_MOUNT_FAILURE"
                    message = event.message or "Volume mount failed"
                    safe_to_terminate = False
                    break
        except Exception as e:
            logger.warning(
                f"[eviction_safety] Failed to fetch events for {namespace}/{pod_name}: {e}"
            )

        assessments.append({
            "pod": f"{namespace}/{pod_name}",
            "reason": reason,
            "message": message[:200],
            "safe_to_terminate": safe_to_terminate,
        })

    return assessments


def should_terminate_with_stuck_pods(assessments: List[Dict]) -> Tuple[bool, str]:
    """
    Based on assess_stuck_pods() output, decide if the old node can be terminated.

    Returns:
        (safe_to_terminate, reason_string)
    """
    if not assessments:
        return True, "No stuck pods"

    blocking = [a for a in assessments if not a["safe_to_terminate"]]
    if not blocking:
        return True, "Only DaemonSet or safe-to-terminate pods stuck"

    unschedulable = [a for a in blocking if a["reason"] == "UNSCHEDULABLE"]
    volume_issues = [
        a for a in blocking
        if a["reason"] in ("VOLUME_ATTACH_FAILURE", "VOLUME_MOUNT_FAILURE")
    ]

    if unschedulable:
        return False, (
            f"ABORT: {len(unschedulable)} pod(s) Unschedulable — cluster lacks "
            f"capacity to absorb workload. Uncordon old node to prevent outage. "
            f"Pods: {', '.join(a['pod'] for a in unschedulable[:3])}"
        )

    if volume_issues:
        return False, (
            f"ABORT: {len(volume_issues)} pod(s) with volume attach/mount failures — "
            f"possible misconfiguration (stateless workload with PVC?). "
            f"Pods: {', '.join(a['pod'] for a in volume_issues[:3])}"
        )

    unknown = [a for a in blocking if a["reason"] == "UNKNOWN"]
    if unknown:
        return False, (
            f"ABORT: {len(unknown)} pod(s) stuck for unknown reason — refusing to "
            f"terminate. Pods: {', '.join(a['pod'] for a in unknown[:3])}"
        )

    return False, f"ABORT: {len(blocking)} non-DaemonSet pod(s) stuck"


# ── Problem 6: Per-controller concurrent drain check ───────────────────────

def safe_to_evict(
    cluster_id: str,
    namespace: str,
    controller_name: str,
    redis_client,
    profile: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    Check if it's safe to evict a pod of this controller, accounting for
    concurrent drains across all active actions in the cluster.

    PDB prevents individual evictions from violating budget, but does NOT
    coordinate across concurrent drains on different nodes for the same service.
    This function is that cross-drain coordination.

    Returns:
        (safe, reason)
    """
    drain_key = f"spot:active_drains:{cluster_id}:{namespace}/{controller_name}"

    try:
        active_drain_count = int(redis_client.get(drain_key) or 0)
    except Exception:
        active_drain_count = 0

    if profile is None:
        # Try to load from cache
        try:
            profile_key = f"spot:workload_profile:{cluster_id}:{namespace}/{controller_name}"
            raw = redis_client.get(profile_key)
            if raw:
                profile = json.loads(raw)
        except Exception:
            pass

    if profile is None:
        # No profile available — allow (fail-open) but only if no concurrent drains
        if active_drain_count > 0:
            return False, f"No profile available and {active_drain_count} drain(s) in-flight"
        return True, "No profile — fail-open"

    pdb_defined = profile.get("pdb_defined", False)

    if not pdb_defined:
        # No PDB — only allow one pod of this controller in drain at a time
        if active_drain_count > 0:
            return False, (
                f"No PDB and {active_drain_count} pod(s) of {namespace}/{controller_name} "
                f"already mid-drain — would cause downtime"
            )
        return True, "No PDB, no concurrent drains"

    # With PDB — check if budget allows another drain
    pdb_healthy = profile.get("pdb_healthy_count", 0)
    pdb_min_available = profile.get("pdb_min_available")

    if pdb_min_available is None:
        # PDB uses maxUnavailable instead — allow if no excessive drains
        if active_drain_count >= profile.get("replica_count", 1):
            return False, "All replicas already being drained"
        return True, "PDB uses maxUnavailable, within budget"

    effective_available = pdb_healthy - active_drain_count
    if effective_available <= pdb_min_available:
        return False, (
            f"PDB budget exhausted: healthy={pdb_healthy}, in-flight={active_drain_count}, "
            f"minAvailable={pdb_min_available}, effective={effective_available}"
        )

    return True, "Within PDB budget"


def register_active_drain(
    cluster_id: str, namespace: str, controller_name: str, redis_client, ttl: int = 600,
):
    """Increment the active drain counter for a controller (TTL = 10 min safety)."""
    key = f"spot:active_drains:{cluster_id}:{namespace}/{controller_name}"
    try:
        redis_client.incr(key)
        redis_client.expire(key, ttl)
    except Exception as e:
        logger.warning(f"[eviction_safety] Failed to register drain for {key}: {e}")


def release_active_drain(
    cluster_id: str, namespace: str, controller_name: str, redis_client,
):
    """Decrement the active drain counter (floor at 0)."""
    key = f"spot:active_drains:{cluster_id}:{namespace}/{controller_name}"
    try:
        val = redis_client.decr(key)
        if val < 0:
            redis_client.set(key, 0)
    except Exception as e:
        logger.warning(f"[eviction_safety] Failed to release drain for {key}: {e}")


# ── W5: KEDA Queue Gate ────────────────────────────────────────────────────────

def queue_allows_migration(
    cluster_id: str,
    namespace: str,
    controller_name: str,
    redis_client,
) -> Tuple[bool, str]:
    """
    Check whether the KEDA-managed queue depth allows a migration window.

    MUST use only cached Redis values — no K8s API calls. This function
    runs inside the eviction gate Redis lock (10s timeout), so any I/O
    must be instantaneous.

    Redis keys read:
      - ``spot:keda_metric:{ns}/{ctrl}``    KEDA metric cached by periodic task
      - ``spot:queue_baseline:{ns}/{ctrl}`` Stable baseline from a prior check

    Returns:
        (allowed, reason)
    """
    ctrl_key = f"{namespace}/{controller_name}"
    baseline_key = f"spot:queue_baseline:{ctrl_key}"
    metric_key = f"spot:keda_metric:{ctrl_key}"
    migration_ready_key = f"spot:migration_ready:{cluster_id}:{ctrl_key}"

    try:
        baseline_raw = redis_client.get(baseline_key)
        metric_raw = redis_client.get(metric_key)

        if metric_raw is None:
            # No metric cached — fail-open (can't block without data)
            logger.debug(
                f"[eviction_safety] No KEDA metric cached for {ctrl_key} — allowing"
            )
            return True, "No KEDA metric cached — fail-open"

        try:
            current_metric = float(metric_raw)
        except (ValueError, TypeError):
            return True, "KEDA metric unparsable — fail-open"

        # Zero-scale: queue is empty → ideal migration window
        if current_metric == 0.0:
            try:
                redis_client.setex(migration_ready_key, 300, "1")
            except Exception:
                pass
            return True, "KEDA zero-scale detected — migration window open"

        if baseline_raw is None:
            # No baseline yet: record current as baseline and allow
            try:
                redis_client.setex(baseline_key, 3600, str(current_metric))
            except Exception:
                pass
            return True, "No baseline — stored current as baseline, allowing"

        try:
            baseline = float(baseline_raw)
        except (ValueError, TypeError):
            return True, "Baseline unparsable — fail-open"

        if baseline <= 0:
            if current_metric > 0:
                return False, f"QUEUE_SURGE: queue was 0, now {current_metric:.0f}"
            return True, "Baseline zero, queue stable"

        ratio = current_metric / baseline
        if ratio > 1.5:
            return False, (
                f"QUEUE_SURGE: current={current_metric:.0f} is {ratio:.1f}x "
                f"baseline={baseline:.0f}"
            )

        return True, f"Queue stable (ratio={ratio:.2f})"

    except Exception as e:
        logger.warning(
            f"[eviction_safety] queue_allows_migration error for {ctrl_key}: {e}"
        )
        return True, f"Queue check error (fail-open): {e}"


# ── Execution Guarantee: Per-controller eviction gate lock ─────────────────

def eviction_gate(
    cluster_id: str,
    namespace: str,
    controller_name: str,
    redis_client,
    profile: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    Atomic pre-flight gate: acquire per-controller Redis lock, run all safety
    checks, decide whether eviction can proceed.

    This lock prevents two Celery workers from simultaneously passing all checks
    and both launching evictions that together violate the budget.

    Returns:
        (allowed, reason)
    """
    lock_key = f"spot:eviction_gate:{cluster_id}:{namespace}/{controller_name}"

    try:
        lock = redis_client.lock(lock_key, timeout=10, blocking_timeout=5)
        acquired = lock.acquire(blocking=True)
    except Exception as e:
        logger.warning(f"[eviction_safety] Lock acquisition failed for {lock_key}: {e}")
        return False, f"Lock failed: {e}"

    if not acquired:
        return False, "Could not acquire eviction gate lock (contention)"

    try:
        # Run all pre-flight checks under lock
        safe, reason = safe_to_evict(
            cluster_id, namespace, controller_name, redis_client, profile
        )
        if not safe:
            return False, reason

        # W5 — KEDA queue gate: only for KEDA-managed workloads (tier 2 or 3).
        # Load profile from Redis cache if not provided by caller.
        _profile = profile
        if _profile is None:
            try:
                _pk = f"spot:workload_profile:{cluster_id}:{namespace}/{controller_name}"
                _raw = redis_client.get(_pk)
                if _raw:
                    _profile = json.loads(_raw)
            except Exception:
                pass

        if _profile and _profile.get("keda_managed"):
            q_allowed, q_reason = queue_allows_migration(
                cluster_id, namespace, controller_name, redis_client
            )
            if not q_allowed:
                return False, f"KEDA queue gate: {q_reason}"

        # Register this drain
        register_active_drain(cluster_id, namespace, controller_name, redis_client)
        return True, "Eviction gate passed"

    finally:
        try:
            lock.release()
        except Exception:
            pass


# ── W7: HPA / KEDA Autoscaler Freeze ──────────────────────────────────────────

def freeze_autoscaler(
    apps_v1,
    keda_service,
    namespace: str,
    controller_name: str,
    controller_kind: str,
    current_replicas: int,
    redis_client,
    cluster_id: str = "",
) -> dict:
    """
    Freeze HPA and/or KEDA ScaledObject during a migration window.

    HPA freeze: patch spec.minReplicas = spec.maxReplicas = current_replicas.
    KEDA freeze: call keda_service.pause_scaled_object().
    State persisted to Redis ``spot:autoscaler_freeze:{ns}/{ctrl}`` (TTL 180s).

    Call AFTER protect_single_replica() so current_replicas reflects the
    post-scale-out count (never freeze at the original single-replica count).

    Args:
        apps_v1: kubernetes AppsV1Api client (may be None — skips HPA freeze).
        keda_service: KedaService instance (may be None — skips KEDA freeze).
        current_replicas: Replica count to lock HPA at.
        cluster_id: Needed for Redis profile lookup and KEDA service calls.

    Returns:
        State dict written to Redis.
    """
    ctrl_key = f"{namespace}/{controller_name}"
    freeze_key = f"spot:autoscaler_freeze:{ctrl_key}"

    state: dict = {
        "hpa_frozen": False,
        "keda_frozen": False,
        "hpa_name": None,
        "original_hpa_min": None,
        "original_hpa_max": None,
        "scaled_object_name": None,
        "controller_name": controller_name,
        "namespace": namespace,
        "frozen_at": time.time(),
    }

    # ── HPA freeze ────────────────────────────────────────────────────────────
    if apps_v1 and controller_kind in ("Deployment", "StatefulSet"):
        try:
            hpa_list = apps_v1.list_namespaced_horizontal_pod_autoscaler(namespace)
            for hpa in (hpa_list.items or []):
                ref = hpa.spec.scale_target_ref if hpa.spec else None
                if ref and ref.name == controller_name:
                    orig_min = hpa.spec.min_replicas
                    orig_max = hpa.spec.max_replicas
                    state["original_hpa_min"] = orig_min
                    state["original_hpa_max"] = orig_max
                    state["hpa_name"] = hpa.metadata.name
                    # Lock to current replicas (cap at max=120s hard cap handled by TTL)
                    hpa.spec.min_replicas = current_replicas
                    hpa.spec.max_replicas = current_replicas
                    apps_v1.patch_namespaced_horizontal_pod_autoscaler(
                        name=hpa.metadata.name, namespace=namespace, body=hpa
                    )
                    state["hpa_frozen"] = True
                    logger.info(
                        f"[eviction_safety] Froze HPA {namespace}/{hpa.metadata.name}: "
                        f"min={orig_min}→{current_replicas}, max={orig_max}→{current_replicas}"
                    )
                    break
        except Exception as e:
            logger.warning(f"[eviction_safety] HPA freeze failed for {ctrl_key}: {e}")

    # ── KEDA ScaledObject freeze ───────────────────────────────────────────────
    if keda_service and cluster_id:
        try:
            # Only pause if workload is KEDA-managed and not already paused.
            _pk = f"spot:workload_profile:{cluster_id}:{ctrl_key}"
            _profile_raw = redis_client.get(_pk)
            _profile = json.loads(_profile_raw) if _profile_raw else {}
            if _profile.get("keda_managed") and not _profile.get("keda_paused"):
                so_name = _profile.get("scaled_object_name") or controller_name
                paused = keda_service.pause_scaled_object(
                    cluster_id=cluster_id,
                    name=so_name,
                    namespace=namespace,
                )
                if paused:
                    state["keda_frozen"] = True
                    state["scaled_object_name"] = so_name
                    logger.info(
                        f"[eviction_safety] Paused KEDA ScaledObject "
                        f"{namespace}/{so_name}"
                    )
        except Exception as e:
            logger.warning(f"[eviction_safety] KEDA freeze failed for {ctrl_key}: {e}")

    # Persist freeze state (TTL 180s hard cap — stale freezes cleaned up by reconciliation task)
    try:
        redis_client.setex(freeze_key, 180, json.dumps(state))
    except Exception:
        pass

    return state


def restore_autoscaler(
    apps_v1,
    keda_service,
    namespace: str,
    controller_name: str,
    redis_client,
    cluster_id: str = "",
) -> bool:
    """
    Restore HPA and KEDA ScaledObject after a migration completes.

    Reads frozen state from Redis ``spot:autoscaler_freeze:{ns}/{ctrl}``
    and reverses each freeze operation. Called from the migration ``finally``
    block so restores happen even on failure.

    Returns:
        True if a freeze state was found and restore was attempted.
    """
    ctrl_key = f"{namespace}/{controller_name}"
    freeze_key = f"spot:autoscaler_freeze:{ctrl_key}"

    try:
        raw = redis_client.get(freeze_key)
        if not raw:
            return False
        state = json.loads(raw)
    except Exception as e:
        logger.warning(
            f"[eviction_safety] Cannot read freeze state for {ctrl_key}: {e}"
        )
        return False

    # ── Restore HPA ───────────────────────────────────────────────────────────
    if state.get("hpa_frozen") and apps_v1:
        try:
            hpa_name = state.get("hpa_name")
            orig_min = state.get("original_hpa_min")
            orig_max = state.get("original_hpa_max")
            if hpa_name and orig_min is not None and orig_max is not None:
                hpa = apps_v1.read_namespaced_horizontal_pod_autoscaler(
                    name=hpa_name, namespace=namespace
                )
                hpa.spec.min_replicas = orig_min
                hpa.spec.max_replicas = orig_max
                apps_v1.patch_namespaced_horizontal_pod_autoscaler(
                    name=hpa_name, namespace=namespace, body=hpa
                )
                logger.info(
                    f"[eviction_safety] Restored HPA {namespace}/{hpa_name}: "
                    f"min={orig_min}, max={orig_max}"
                )
        except Exception as e:
            logger.warning(
                f"[eviction_safety] HPA restore failed for {ctrl_key}: {e}"
            )

    # ── Restore KEDA ScaledObject ─────────────────────────────────────────────
    if state.get("keda_frozen") and keda_service and cluster_id:
        try:
            so_name = state.get("scaled_object_name") or controller_name
            keda_service.restore_scaled_object(
                cluster_id=cluster_id,
                name=so_name,
                namespace=namespace,
            )
            logger.info(
                f"[eviction_safety] Restored KEDA ScaledObject "
                f"{namespace}/{so_name}"
            )
        except Exception as e:
            logger.warning(
                f"[eviction_safety] KEDA restore failed for {ctrl_key}: {e}"
            )

    # Remove freeze state
    try:
        redis_client.delete(freeze_key)
    except Exception:
        pass

    return True
