"""
Placement Mutating Webhook — v1.4
===================================
Intercepts new pod creation events from KEDA/HPA.

PURPOSE (strictly structural — no capacity decisions):
  - Inject soft AZ spread constraint (whenUnsatisfiable=ScheduleAnyway) when
    the workload's PlacementPolicy has az_spread_required=True.
  - Inject soft Spot node preference always (weight=80).

WHAT THIS WEBHOOK MUST NOT DO:
  - Never decide Spot vs On-Demand for existing pods.
  - Never count OD pods or apply Redis INCR counters.
  - Never read or evaluate capacity.
  - Never apply hard scheduling constraints.

Decision authority for Spot vs On-Demand belongs SOLELY to PlacementController.
Two decision layers on the same question create race conditions and conflicting state.

§5 of plan.md v1.4.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/placement", tags=["PlacementWebhook"])

# ---------------------------------------------------------------------------
# Redis policy lookup key (read-only — never written by webhook)
# ---------------------------------------------------------------------------
POLICY_KEY_TEMPLATE = "spot:placement:policy:{cluster_id}:{workload_id}"


# ---------------------------------------------------------------------------
# Webhook entry point
# ---------------------------------------------------------------------------

@router.post("/mutate-pods")
async def mutate_pods(request: Request):
    """
    Kubernetes MutatingWebhookConfiguration target.

    Injects structural placement hints into pods at birth:
      1. Soft AZ topology spread (ScheduleAnyway) if az_spread_required=True.
      2. Soft Spot node affinity (preferredDuringScheduling, weight=80).

    Returns a JSON Patch in base64 to the K8s API server.
    """
    try:
        admission_request = await request.json()
    except Exception:
        admission_request = None
    if not admission_request:
        return JSONResponse(content={"error": "empty body"}, status_code=400)

    uid = admission_request.get("request", {}).get("uid", "")
    pod_spec = admission_request.get("request", {}).get("object", {})

    namespace = pod_spec.get("metadata", {}).get("namespace", "default")
    labels = pod_spec.get("metadata", {}).get("labels", {})
    controller_name = (
        labels.get("app.kubernetes.io/name")
        or labels.get("app")
        or pod_spec.get("metadata", {}).get("generateName", "unknown").rstrip("-")
    )
    cluster_id = request.headers.get("X-Cluster-Id", "")

    # P1-A: stamp KEDA scale-event timestamp so PlacementController's KEDA guard fires
    if labels.get("app.kubernetes.io/managed-by") == "keda" and cluster_id:
        try:
            import time as _t
            from backend.core.redis_client import get_redis_client
            _wr = get_redis_client()
            if _wr:
                _wr.setex(f"spot:keda:last_scale_event:{cluster_id}", 300, str(_t.time()))
        except Exception:
            pass  # never reject an admission request on Redis errors

    patches = _build_patches(cluster_id, namespace, controller_name, pod_spec)

    response = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": True,
            "patchType": "JSONPatch" if patches else None,
            "patch": (
                base64.b64encode(json.dumps(patches).encode()).decode()
                if patches
                else None
            ),
        },
    }
    # Clean up None fields so K8s accepts the response
    response["response"] = {k: v for k, v in response["response"].items() if v is not None}

    return response


# ---------------------------------------------------------------------------
# Patch construction
# ---------------------------------------------------------------------------

def _build_patches(
    cluster_id: str,
    namespace: str,
    controller_name: str,
    pod_spec: dict,
) -> list:
    """
    Builds the JSONPatch list to inject into the pod spec.
    Returns empty list if no policy found or policy is not actionable.
    """
    policy = _get_policy(cluster_id, namespace, controller_name)
    if not policy or not policy.get("actionable"):
        return []

    patches = []

    spec = pod_spec.get("spec", {})

    # 1. AZ topology spread (§ 5.2 — ScheduleAnyway, never block scheduling)
    if policy.get("az_spread_required"):
        patches.extend(_az_spread_patches(spec))

    # 2. Soft Spot preference — always inject so scheduler prefers Spot nodes
    patches.extend(_spot_preference_patches(spec))

    return patches


def _az_spread_patches(spec: dict) -> list:
    """
    Injects a soft topology spread constraint for AZ spread.

    whenUnsatisfiable=ScheduleAnyway — pod is NEVER blocked pending due to
    AZ imbalance. PlacementController corrects the distribution post-scheduling.
    """
    existing = spec.get("topologySpreadConstraints", [])

    # Idempotent — skip if zone spread already declared
    for constraint in existing:
        if constraint.get("topologyKey") == "topology.kubernetes.io/zone":
            return []

    new_constraint = {
        "maxSkew": 1,
        "topologyKey": "topology.kubernetes.io/zone",
        "whenUnsatisfiable": "ScheduleAnyway",
        "labelSelector": {},
    }

    if existing:
        # Append to existing array
        return [
            {
                "op": "add",
                "path": "/spec/topologySpreadConstraints/-",
                "value": new_constraint,
            }
        ]
    else:
        # Create array
        return [
            {
                "op": "add",
                "path": "/spec/topologySpreadConstraints",
                "value": [new_constraint],
            }
        ]


def _spot_preference_patches(spec: dict) -> list:
    """
    Injects a preferredDuringSchedulingIgnoredDuringExecution affinity rule
    with weight=80 for karpenter.sh/capacity-type=spot.

    This is a PREFERENCE, not a requirement. PlacementController reconciles
    any pods that land on OD despite this preference.
    """
    spot_preference = {
        "weight": 80,
        "preference": {
            "matchExpressions": [
                {
                    "key": "karpenter.sh/capacity-type",
                    "operator": "In",
                    "values": ["spot"],
                }
            ]
        },
    }

    affinity = spec.get("affinity", {})
    node_affinity = affinity.get("nodeAffinity", {})
    preferred = node_affinity.get(
        "preferredDuringSchedulingIgnoredDuringExecution", []
    )

    # Idempotent — skip if Spot preference already injected
    for term in preferred:
        for expr in term.get("preference", {}).get("matchExpressions", []):
            if (
                expr.get("key") == "karpenter.sh/capacity-type"
                and "spot" in expr.get("values", [])
            ):
                return []

    patches = []

    if not affinity:
        patches.append({"op": "add", "path": "/spec/affinity", "value": {}})
    if not node_affinity:
        patches.append(
            {"op": "add", "path": "/spec/affinity/nodeAffinity", "value": {}}
        )
    if not preferred:
        patches.append(
            {
                "op": "add",
                "path": "/spec/affinity/nodeAffinity/preferredDuringSchedulingIgnoredDuringExecution",
                "value": [spot_preference],
            }
        )
    else:
        patches.append(
            {
                "op": "add",
                "path": "/spec/affinity/nodeAffinity/preferredDuringSchedulingIgnoredDuringExecution/-",
                "value": spot_preference,
            }
        )

    return patches


# ---------------------------------------------------------------------------
# Policy lookup (read-only)
# ---------------------------------------------------------------------------

def _get_policy(
    cluster_id: str, namespace: str, controller_name: str
) -> Optional[dict]:
    """
    Reads PlacementPolicy from Redis. Returns None on cache miss.
    The webhook NEVER writes to Redis.
    """
    try:
        from backend.core.redis_client import get_redis_client
        redis = get_redis_client()
    except Exception:
        return None
    if not redis:
        return None

    workload_id = f"{namespace}/{controller_name}"
    key = POLICY_KEY_TEMPLATE.format(
        cluster_id=cluster_id, workload_id=workload_id
    )
    raw = redis.get(key)
    if not raw:
        return None

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
