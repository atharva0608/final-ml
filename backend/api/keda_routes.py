"""KEDA API Routes — K1

Provides detection, ScaledObject listing, and pause/restore endpoints
for the KEDA integration.

Endpoints:
  GET  /api/v1/keda/{cluster_id}/detect               — K1.7  KEDA installation check
  GET  /api/v1/keda/{cluster_id}/scaled-objects        — K1.3  List all ScaledObjects
  GET  /api/v1/keda/{cluster_id}/scaled-objects/{ns}/{name}  — Get single ScaledObject info
  POST /api/v1/keda/{cluster_id}/scaled-objects/{ns}/{name}/pause    — K1.6 Pause
  POST /api/v1/keda/{cluster_id}/scaled-objects/{ns}/{name}/restore  — K1.6 Restore
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.core.logger import logger

router = APIRouter(prefix="/api/v1/keda", tags=["keda"])


def _get_keda_svc(db: Session):
    """Lazily import KedaService to avoid circular imports."""
    from backend.services.keda_service import KedaService
    from backend.core.redis_client import get_redis_client
    try:
        redis = get_redis_client()
    except Exception:
        redis = None
    return KedaService(db=db, redis=redis)


# ── Detection ─────────────────────────────────────────────────────────────────


@router.get(
    "/{cluster_id}/detect",
    summary="Detect KEDA installation in a cluster",
)
def detect_keda(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns KEDA installation status for the given cluster.

    Response is cached in Redis for 5 minutes (spot:keda_detection:{cluster_id}).
    """
    try:
        svc = _get_keda_svc(db)
        result = svc.detect_installation(cluster_id)
        return {
            "cluster_id":         cluster_id,
            "installed":          result.installed,
            "crd_exists":         result.crd_exists,
            "operator_running":   result.operator_running,
            "version":            result.version,
            "operator_namespace": result.operator_namespace,
            "operator_pod_count": result.operator_pod_count,
            "error":              result.error,
        }
    except Exception as exc:
        logger.error(f"[KEDA] /detect failed for cluster {cluster_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"KEDA detection failed: {exc}",
        )


# ── ScaledObject listing ───────────────────────────────────────────────────────


@router.get(
    "/{cluster_id}/scaled-objects",
    summary="List all ScaledObjects in a cluster",
)
def list_scaled_objects(
    cluster_id: str,
    namespace: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns all ScaledObjects across the cluster, or filtered to `namespace`.
    """
    try:
        svc = _get_keda_svc(db)
        objects = svc.get_all_scaled_objects(cluster_id, namespace=namespace)
        return {
            "cluster_id": cluster_id,
            "namespace":  namespace,
            "count":      len(objects),
            "items": [
                {
                    "name":                   o.name,
                    "namespace":              o.namespace,
                    "scale_target_ref_name":  o.scale_target_ref_name,
                    "scale_target_ref_kind":  o.scale_target_ref_kind,
                    "min_replicas":           o.min_replicas,
                    "max_replicas":           o.max_replicas,
                    "trigger_types":          o.trigger_types,
                    "paused":                 o.paused,
                    "external_metric_names":  o.external_metric_names,
                    "ready":                  o.ready,
                    "active":                 o.active,
                }
                for o in objects
            ],
        }
    except Exception as exc:
        logger.error(f"[KEDA] /scaled-objects failed for cluster {cluster_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list ScaledObjects: {exc}",
        )


@router.get(
    "/{cluster_id}/scaled-objects/{namespace}/{name}",
    summary="Get a specific ScaledObject and its current metric values",
)
def get_scaled_object(
    cluster_id: str,
    namespace: str,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a ScaledObject plus its current external metric names from status.
    """
    try:
        svc = _get_keda_svc(db)
        metric_names = svc.get_current_metric_value(cluster_id, namespace, name)
        objects = svc.get_all_scaled_objects(cluster_id, namespace=namespace)
        obj = next((o for o in objects if o.name == name), None)

        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ScaledObject {namespace}/{name} not found",
            )

        return {
            "cluster_id":            cluster_id,
            "name":                  obj.name,
            "namespace":             obj.namespace,
            "scale_target_ref_name": obj.scale_target_ref_name,
            "scale_target_ref_kind": obj.scale_target_ref_kind,
            "min_replicas":          obj.min_replicas,
            "max_replicas":          obj.max_replicas,
            "trigger_types":         obj.trigger_types,
            "paused":                obj.paused,
            "external_metric_names": metric_names or obj.external_metric_names,
            "ready":                 obj.ready,
            "active":                obj.active,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"[KEDA] GET scaled-object failed for {cluster_id}/{namespace}/{name}: {exc}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get ScaledObject: {exc}",
        )


# ── Pause / Restore ────────────────────────────────────────────────────────────


@router.post(
    "/{cluster_id}/scaled-objects/{namespace}/{name}/pause",
    summary="Pause a ScaledObject (freeze autoscaling during migration)",
)
def pause_scaled_object(
    cluster_id: str,
    namespace: str,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pauses the ScaledObject by setting spec.paused=true.
    The original paused state is cached in Redis for safe restore.
    """
    try:
        svc = _get_keda_svc(db)
        ok = svc.pause_scaled_object(cluster_id, namespace, name)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to pause ScaledObject {namespace}/{name}",
            )
        return {"success": True, "message": f"ScaledObject {namespace}/{name} paused"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[KEDA] pause failed for {cluster_id}/{namespace}/{name}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pause failed: {exc}",
        )


@router.post(
    "/{cluster_id}/scaled-objects/{namespace}/{name}/restore",
    summary="Restore a ScaledObject's paused state after migration",
)
def restore_scaled_object(
    cluster_id: str,
    namespace: str,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Restores the ScaledObject to its pre-pause paused state.
    Reads original state from Redis key spot:keda_paused_state:{ns}/{name}.
    """
    try:
        svc = _get_keda_svc(db)
        ok = svc.restore_scaled_object(cluster_id, namespace, name)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to restore ScaledObject {namespace}/{name}",
            )
        return {"success": True, "message": f"ScaledObject {namespace}/{name} restored"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[KEDA] restore failed for {cluster_id}/{namespace}/{name}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {exc}",
        )


# ── Install / Uninstall (K2) ───────────────────────────────────────────────────


@router.post(
    "/{cluster_id}/install",
    summary="Install KEDA via Helm (queues AgentAction)",
)
def install_keda(
    cluster_id: str,
    version: str = "2.13.0",
    namespace: str = "keda",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Queues an INSTALL_KEDA AgentAction. The in-cluster agent will
    execute the Helm install. Sets spot:keda_installing:{cluster_id}
    flag (TTL=300s) so /install-status returns install_in_progress=True
    while the install runs.
    """
    try:
        svc = _get_keda_svc(db)
        result = svc.install_keda(
            cluster_id=cluster_id,
            version=version,
            namespace=namespace,
        )
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Install failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[KEDA] POST /install failed for {cluster_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"KEDA install failed: {exc}",
        )


@router.delete(
    "/{cluster_id}/install",
    summary="Uninstall KEDA via Helm (queues AgentAction)",
)
def uninstall_keda(
    cluster_id: str,
    namespace: str = "keda",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Queues an UNINSTALL_KEDA AgentAction. Invalidates the detection cache
    so subsequent detect calls reflect the uninstall.
    """
    try:
        svc = _get_keda_svc(db)
        result = svc.uninstall_keda(cluster_id=cluster_id, namespace=namespace)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Uninstall failed"),
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[KEDA] DELETE /install failed for {cluster_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"KEDA uninstall failed: {exc}",
        )


@router.get(
    "/{cluster_id}/install-status",
    summary="Get KEDA installation status (mirrors Karpenter 3-tier detection)",
)
def get_install_status(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns combined install status:
      - installed: whether KEDA CRD + operator are running
      - install_in_progress: spot:keda_installing flag is set
      - action_status: latest INSTALL_KEDA / UNINSTALL_KEDA action status
      - action_id: latest action ID (for polling)
      - crd_exists, operator_running, version, operator_namespace
    """
    try:
        svc = _get_keda_svc(db)
        return svc.get_install_status(cluster_id)
    except Exception as exc:
        logger.error(f"[KEDA] GET /install-status failed for {cluster_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get install status: {exc}",
        )
