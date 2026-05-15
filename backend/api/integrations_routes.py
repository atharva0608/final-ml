"""Integrations Health Routes — K4

Provides a unified health status endpoint that combines KEDA and Karpenter
installation detection into a single response for the integrations dashboard.

Endpoint:
  GET /api/v1/integrations/health  — K4.1  Joint KEDA + Karpenter health
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.core.logger import logger

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get(
    "/health",
    summary="Joint KEDA + Karpenter installation health status",
)
def get_integrations_health(
    cluster_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the combined installation health for KEDA and Karpenter.

    If ``cluster_id`` is provided, both checks are scoped to that cluster.
    Results are assembled from cached Redis values where possible (300s TTL).

    Response shape:
    ```json
    {
      "keda": {
        "installed": true,
        "operator_running": true,
        "version": "2.13.0",
        "error": null
      },
      "karpenter": {
        "installed": true,
        "healthy": true,
        "version": "0.36.0",
        "error": null
      },
      "overall_healthy": true
    }
    ```
    """
    keda_result: dict = {
        "installed": False,
        "operator_running": False,
        "crd_exists": False,
        "version": None,
        "namespace": None,
        "error": None,
    }
    karpenter_result: dict = {
        "installed": False,
        "healthy": False,
        "version": None,
        "error": None,
    }

    # ── KEDA ─────────────────────────────────────────────────────────────────
    if cluster_id:
        try:
            from backend.services.keda_service import KedaService
            from backend.core.redis_client import get_redis_client
            try:
                _redis = get_redis_client()
            except Exception:
                _redis = None
            keda_svc = KedaService(db=db, redis=_redis)
            keda = keda_svc.detect_installation(cluster_id)
            keda_result = {
                "installed":       keda.installed,
                "operator_running": keda.operator_running,
                "crd_exists":      keda.crd_exists,
                "version":         keda.version,
                "namespace":       keda.operator_namespace,
                "error":           keda.error,
            }
        except Exception as e:
            keda_result["error"] = str(e)
            logger.warning(f"[integrations] KEDA health check failed: {e}")

    # ── Karpenter ─────────────────────────────────────────────────────────────
    if cluster_id:
        try:
            from backend.services.karpenter_service import KarpenterService
            kp_svc = KarpenterService(db=db)
            # detect_karpenter_in_cluster may not exist if it uses a different name
            detect_fn = getattr(kp_svc, "detect_karpenter_in_cluster", None) or getattr(
                kp_svc, "check_karpenter_installation", None
            )
            if detect_fn:
                kp = detect_fn(cluster_id)
                karpenter_result = {
                    "installed": kp.get("installed", False) if isinstance(kp, dict) else getattr(kp, "installed", False),
                    "healthy":   kp.get("healthy", False) if isinstance(kp, dict) else getattr(kp, "healthy", False),
                    "version":   kp.get("version") if isinstance(kp, dict) else getattr(kp, "version", None),
                    "error":     kp.get("error") if isinstance(kp, dict) else getattr(kp, "error", None),
                }
            else:
                karpenter_result["error"] = "Karpenter detection method not available"
        except Exception as e:
            karpenter_result["error"] = str(e)
            logger.warning(f"[integrations] Karpenter health check failed: {e}")

    overall_healthy = (
        keda_result.get("operator_running", False)
        and karpenter_result.get("installed", False)
    )

    return {
        "cluster_id":      cluster_id,
        "keda":            keda_result,
        "karpenter":       karpenter_result,
        "overall_healthy": overall_healthy,
    }
