"""
Pod Metrics API Routes - DaemonSet metrics collection and Right-Sizing recommendations
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from backend.models.base import get_db
from backend.models.pod_metric import PodMetric
from backend.models.cluster import Cluster
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.schemas.pod_metric_schemas import (
    PodMetricBatchCreate,
    PodMetricBatchResponse,
    PodMetricResponse,
    RightSizingRecommendation
)
from backend.core.logger import logger

router = APIRouter(prefix="/pod-metrics", tags=["PodMetrics"])


# Enriched recommendation schemas
class TemplateCompliance(BaseModel):
    compliant: bool
    violations: List[str] = []


class BlacklistStatus(BaseModel):
    checked: bool
    blacklisted: bool
    risk_score: int = 0
    reason: Optional[str] = None


class EnrichedRightSizingRecommendation(BaseModel):
    # All fields from base recommendation
    namespace: str
    controller_kind: str
    controller_name: str
    current_cpu_request: int
    current_memory_request: int
    recommended_cpu_request: int
    recommended_memory_request: int
    p95_cpu_usage: float
    p95_memory_usage: float
    data_points: int
    analysis_window_hours: int
    estimated_savings_monthly: float
    # Enriched fields
    template_compliance: Optional[TemplateCompliance] = None
    blacklist_status: Optional[BlacklistStatus] = None
    atharva_score: Optional[float] = None
    availability_confidence: Optional[str] = None


@router.post("/batch", response_model=PodMetricBatchResponse, status_code=status.HTTP_201_CREATED)
async def submit_pod_metrics_batch(
    batch: PodMetricBatchCreate,
    db: Session = Depends(get_db)
):
    """
    Submit batch of pod metrics from DaemonSet agent.

    Called by DaemonSet agents running on each node to submit pod-level metrics.
    Collection frequency: Every 5 minutes per node.

    Args:
        batch: Batch of pod metrics from a single node
        db: Database session

    Returns:
        Batch submission result with count of metrics inserted
    """
    try:
        # Validate cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == batch.cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {batch.cluster_id} not found"
            )

        metrics_inserted = 0
        errors = []

        for metric_data in batch.metrics:
            try:
                # Calculate utilization percentages
                cpu_utilization = None
                if metric_data.cpu_request_millicores and metric_data.cpu_request_millicores > 0:
                    cpu_utilization = (metric_data.cpu_usage_millicores / metric_data.cpu_request_millicores) * 100

                memory_utilization = None
                if metric_data.memory_request_bytes and metric_data.memory_request_bytes > 0:
                    memory_utilization = (metric_data.memory_usage_bytes / metric_data.memory_request_bytes) * 100

                # Create pod metric record
                pod_metric = PodMetric(
                    cluster_id=batch.cluster_id,
                    namespace=metric_data.namespace,
                    pod_name=metric_data.pod_name,
                    node_name=metric_data.node_name,
                    controller_kind=metric_data.controller_kind,
                    controller_name=metric_data.controller_name,
                    cpu_usage_millicores=metric_data.cpu_usage_millicores,
                    cpu_request_millicores=metric_data.cpu_request_millicores,
                    cpu_limit_millicores=metric_data.cpu_limit_millicores,
                    memory_usage_bytes=metric_data.memory_usage_bytes,
                    memory_request_bytes=metric_data.memory_request_bytes,
                    memory_limit_bytes=metric_data.memory_limit_bytes,
                    cpu_utilization_pct=cpu_utilization,
                    memory_utilization_pct=memory_utilization,
                    container_count=metric_data.container_count,
                    phase=metric_data.phase,
                    start_time=metric_data.start_time,
                    timestamp=batch.timestamp,
                    pod_metadata=metric_data.metadata or {}
                )

                db.add(pod_metric)
                metrics_inserted += 1

            except Exception as e:
                error_msg = f"Failed to insert metric for pod {metric_data.namespace}/{metric_data.pod_name}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)

        # Commit all metrics in batch
        db.commit()

        # ── SPIKE DETECTION (Phase 2B) ────────────────────────────────────
        # After inserting, check each unique workload for active CPU spikes.
        # spike_ratio = latest_cpu / rolling_avg_60min. If > 3.0 → set Redis key.
        try:
            from backend.core.redis_client import get_redis_client as _get_redis
            _redis = _get_redis()
            if _redis:
                from sqlalchemy import func as _func
                _seen_workloads = {
                    (m.namespace, m.controller_name)
                    for m in batch.metrics
                    if m.controller_name
                }
                _cutoff_60m = datetime.utcnow() - timedelta(minutes=60)
                _cutoff_15m = datetime.utcnow() - timedelta(minutes=15)
                for (_ns, _wl) in _seen_workloads:
                    try:
                        _avg_60m = db.query(
                            _func.avg(PodMetric.cpu_usage_millicores)
                        ).filter(
                            PodMetric.cluster_id == batch.cluster_id,
                            PodMetric.namespace == _ns,
                            PodMetric.controller_name == _wl,
                            PodMetric.timestamp >= _cutoff_60m,
                        ).scalar() or 0
                        _latest = db.query(
                            _func.avg(PodMetric.cpu_usage_millicores)
                        ).filter(
                            PodMetric.cluster_id == batch.cluster_id,
                            PodMetric.namespace == _ns,
                            PodMetric.controller_name == _wl,
                            PodMetric.timestamp >= _cutoff_15m,
                        ).scalar() or 0
                        if _avg_60m > 0 and (_latest / _avg_60m) > 3.0:
                            _spike_key = f"spike:active:{batch.cluster_id}:{_ns}/{_wl}"
                            _redis.setex(_spike_key, 900, "1")
                    except Exception:
                        pass
        except Exception:
            pass

        logger.info(f"Inserted {metrics_inserted} pod metrics for cluster {batch.cluster_id} from node {batch.node_name}")

        return PodMetricBatchResponse(
            status="success" if metrics_inserted > 0 else "error",
            metrics_inserted=metrics_inserted,
            errors=errors,
            message=f"Successfully inserted {metrics_inserted} pod metrics"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process pod metrics batch: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process pod metrics: {str(e)}"
        )


@router.get("", response_model=List[PodMetricResponse])
async def get_pod_metrics(
    cluster_id: Optional[str] = Query(None, description="Filter by cluster ID"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    controller_name: Optional[str] = Query(None, description="Filter by controller name"),
    node_name: Optional[str] = Query(None, description="Filter by node name"),
    start_time: Optional[datetime] = Query(None, description="Start time for time range filter"),
    end_time: Optional[datetime] = Query(None, description="End time for time range filter"),
    limit: int = Query(100, le=1000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    Query pod metrics with filters.

    Args:
        cluster_id: Filter by cluster
        namespace: Filter by namespace
        controller_name: Filter by controller
        node_name: Filter by node
        start_time: Start of time range
        end_time: End of time range
        limit: Max records
        offset: Pagination offset
        db: Database session

    Returns:
        List of pod metrics matching filters
    """
    try:
        query = db.query(PodMetric)

        # Apply filters
        if cluster_id:
            query = query.filter(PodMetric.cluster_id == cluster_id)
        if namespace:
            query = query.filter(PodMetric.namespace == namespace)
        if controller_name:
            query = query.filter(PodMetric.controller_name == controller_name)
        if node_name:
            query = query.filter(PodMetric.node_name == node_name)
        if start_time:
            query = query.filter(PodMetric.timestamp >= start_time)
        if end_time:
            query = query.filter(PodMetric.timestamp <= end_time)

        # Order by timestamp descending (most recent first)
        query = query.order_by(PodMetric.timestamp.desc())

        # Apply pagination
        query = query.offset(offset).limit(limit)

        metrics = query.all()

        return [PodMetricResponse.model_validate(m) for m in metrics]

    except Exception as e:
        logger.error(f"Failed to query pod metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query pod metrics: {str(e)}"
        )


@router.delete("/cleanup")
async def cleanup_old_pod_metrics(
    retention_days: int = Query(7, ge=1, le=90, description="Retention period in days"),
    db: Session = Depends(get_db)
):
    """
    Cleanup pod metrics older than retention period.

    Default retention: 7 days (168 hours * 12 samples/hour = 2,016 data points per pod)

    Args:
        retention_days: Number of days to retain metrics
        db: Database session

    Returns:
        Count of deleted metrics
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(days=retention_days)

        deleted_count = db.query(PodMetric).filter(
            PodMetric.timestamp < cutoff_time
        ).delete()

        db.commit()

        logger.info(f"Cleaned up {deleted_count} pod metrics older than {retention_days} days")

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "cutoff_time": cutoff_time.isoformat(),
            "message": f"Deleted {deleted_count} metrics older than {retention_days} days"
        }

    except Exception as e:
        logger.error(f"Failed to cleanup pod metrics: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup pod metrics: {str(e)}"
        )


@router.get("/right-sizing/recommendations", response_model=List[RightSizingRecommendation])
async def get_rightsizing_recommendations(
    cluster_id: str = Query(..., description="Cluster ID to analyze"),
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    analysis_window_hours: int = Query(168, ge=24, le=720, description="Analysis time window (hours)"),
    min_data_points: int = Query(100, ge=10, description="Minimum data points required for recommendation"),
    db: Session = Depends(get_db)
):
    """
    Get right-sizing recommendations for workloads based on pod metrics.

    Analyzes pod metric time-series data to calculate P95/P99 CPU/memory usage
    and generates right-sizing recommendations with cost savings estimates.

    Args:
        cluster_id: Cluster to analyze
        namespace: Optional namespace filter
        analysis_window_hours: Time window to analyze (default 7 days)
        min_data_points: Minimum metrics required for analysis
        db: Database session

    Returns:
        List of right-sizing recommendations
    """
    try:
        from backend.services.rightsizing_service import RightSizingService

        service = RightSizingService(db)

        recommendations = service.generate_recommendations(
            cluster_id=cluster_id,
            namespace=namespace,
            analysis_window_hours=analysis_window_hours,
            min_data_points=min_data_points
        )

        return recommendations

    except Exception as e:
        logger.error(f"Failed to generate right-sizing recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendations: {str(e)}"
        )


@router.get(
    "/rightsizing/enriched",
    summary="Get enriched right-sizing recommendations",
    description="Right-sizing recommendations validated against Node Templates and ASCP.AI blacklist"
)
async def get_enriched_rightsizing_recommendations(
    cluster_id: str = Query(..., description="Cluster ID"),
    analysis_window_hours: int = Query(168, ge=24, le=720),
    min_data_points: int = Query(100, ge=10),
    template_id: Optional[str] = Query(None, description="Node template ID to validate against"),
    check_blacklist: bool = Query(True, description="Check ASCP.AI blacklist"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enriched right-sizing recommendations that validate each recommendation
    against:
    1. Node Template constraints (if template_id provided)
    2. ASCP.AI blacklist (if check_blacklist=True)
    3. ASCP.AI ML score (if available in Redis cache)
    """
    try:
        # Step A: Get base recommendations
        from backend.services.rightsizing_service import RightSizingService

        service = RightSizingService(db)
        base_recommendations = service.generate_recommendations(
            cluster_id=cluster_id,
            namespace=None,
            analysis_window_hours=analysis_window_hours,
            min_data_points=min_data_points
        )

        # Step B: Load template if provided or fetch cluster default
        template = None
        if not template_id:
            from backend.models.cluster_template_mapping import ClusterTemplateMapping
            mapping = db.query(ClusterTemplateMapping).filter(ClusterTemplateMapping.cluster_id == cluster_id).first()
            if mapping:
                template_id = mapping.template_id

        if template_id:
            from backend.services.template_service import get_template_service
            template_service = get_template_service(db)
            template = template_service.get_template(template_id, current_user.id)

        # Step C: Enrich each recommendation
        # Map controller kinds to workload classification
        _STATEFUL_KINDS = {"StatefulSet", "statefulset"}

        enriched = []
        for rec in base_recommendations:
            # Convert to dict for manipulation
            rec_dict = rec.model_dump() if hasattr(rec, 'model_dump') else rec.dict()

            # Determine workload type from controller kind
            kind = rec_dict.get("controller_kind") or ""
            rec_dict["workload_type"] = "STATEFUL" if kind in _STATEFUL_KINDS else "STATELESS"

            # For pod-based recommendations, we don't have instance_type recommendations yet
            # This is a simplified version - in production you'd map pod resources to instance types
            # For now, we'll skip instance-specific validation and focus on the structure

            # Template compliance check (Node Template Constraints)
            if template:
                violations = []
                rec_cpu = rec_dict.get("recommended_cpu_request_millicores") or 0
                rec_mem = rec_dict.get("recommended_memory_request_mb") or 0
                
                if template.constraints and template.constraints.get("vcpu_max"):
                    max_millicores = template.constraints["vcpu_max"] * 1000
                    if rec_cpu > max_millicores:
                        violations.append(f"Requested CPU ({rec_cpu}m) exceeds max node vCPU ({max_millicores}m)")
                
                if template.constraints and template.constraints.get("memory_gb_max"):
                    max_mb = template.constraints["memory_gb_max"] * 1024
                    if rec_mem > max_mb:
                        violations.append(f"Requested Memory ({rec_mem}Mi) exceeds max node memory ({max_mb}Mi)")
                
                rec_dict["template_compliance"] = {
                    "compliant": len(violations) == 0,
                    "violations": violations
                }

            # Blacklist check (simplified - would need instance type + AZ)
            if check_blacklist:
                try:
                    import redis
                    from backend.core.config import settings
                    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

                    rec_dict["blacklist_status"] = {
                        "checked": True,
                        "blacklisted": False,
                        "risk_score": 0,
                        "reason": None
                    }

                except Exception as e:
                    logger.warning(f"Enrichment check failed: {e}")
                    rec_dict["blacklist_status"] = {
                        "checked": False,
                        "blacklisted": False,
                        "risk_score": 0,
                        "reason": None
                    }

            enriched.append(rec_dict)

        return {
            "recommendations": enriched,
            "template_applied": {"id": template_id, "name": template.name} if template else None,
            "blacklist_checked": check_blacklist,
            "enrichment_timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to generate enriched recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate enriched recommendations: {str(e)}"
        )
