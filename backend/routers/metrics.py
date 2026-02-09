"""
Metrics Collection Router

Handles incoming metrics from agent clusters.
Stores pod, node, and event metrics for analysis.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
import logging

from ..models.base import get_db
from ..models.cluster import Cluster
from ..models.cluster_metric import ClusterMetric
from ..core.redis_client import get_redis_client

router = APIRouter(prefix="/api/v1/agent-metrics", tags=["agent-metrics"])
logger = logging.getLogger(__name__)


@router.post("/batch")
async def receive_metrics_batch(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Receive a batch of metrics from an agent.

    Metrics can be pod, node, or event metrics.
    This endpoint stores metrics in the database and caches recent values.
    """
    try:
        cluster_id = payload.get("cluster_id")
        metrics = payload.get("metrics", [])
        timestamp = payload.get("timestamp")

        if not cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cluster_id is required"
            )

        # Verify cluster exists
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cluster {cluster_id} not found"
            )

        # Process metrics by type
        pod_metrics = []
        node_metrics = []
        event_metrics = []

        for metric in metrics:
            metric_type = metric.get("metric_type")

            if metric_type == "pod":
                pod_metrics.append(metric)
            elif metric_type == "node":
                node_metrics.append(metric)
            elif metric_type == "event":
                event_metrics.append(metric)

        # Store aggregated metrics in database
        if pod_metrics or node_metrics or event_metrics:
            cluster_metric = ClusterMetric(
                cluster_id=cluster_id,
                metric_type="aggregated",
                metric_data={
                    "pod_count": len(pod_metrics),
                    "node_count": len(node_metrics),
                    "event_count": len(event_metrics),
                    "pod_metrics": pod_metrics[:10],  # Store sample
                    "node_metrics": node_metrics,     # Store all nodes
                    "event_metrics": event_metrics[:20]  # Store sample
                },
                timestamp=datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow()
            )
            db.add(cluster_metric)
            db.commit()

        # Cache latest metrics in Redis for fast access
        try:
            redis_client = get_redis_client()
            # Cache node metrics (latest state)
            for node_metric in node_metrics:
                cache_key = f"metrics:node:{cluster_id}:{node_metric.get('node_name')}"
                redis_client.setex(
                    cache_key,
                    300,  # 5 minute TTL
                    str(node_metric)
                )

            # Cache pod count and health summary
            running_pods = sum(1 for p in pod_metrics if p.get("phase") == "Running")
            cache_key = f"metrics:cluster:{cluster_id}:summary"
            redis_client.setex(
                cache_key,
                60,  # 1 minute TTL
                str({
                    "total_pods": len(pod_metrics),
                    "running_pods": running_pods,
                    "total_nodes": len(node_metrics),
                    "last_update": timestamp or datetime.utcnow().isoformat()
                })
            )
        except Exception as cache_error:
            logger.warning(f"Failed to cache metrics: {cache_error}")
            # Don't fail the request if caching fails

        logger.info(
            f"Received metrics batch from cluster {cluster_id}: "
            f"{len(pod_metrics)} pods, {len(node_metrics)} nodes, {len(event_metrics)} events"
        )

        return {
            "success": True,
            "cluster_id": cluster_id,
            "received": {
                "pods": len(pod_metrics),
                "nodes": len(node_metrics),
                "events": len(event_metrics)
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing metrics batch: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process metrics: {str(e)}"
        )


@router.get("/cluster/{cluster_id}/latest")
async def get_latest_metrics(
    cluster_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the latest metrics for a cluster.

    Returns cached metrics if available, otherwise queries database.
    """
    try:
        # Try cache first
        try:
            redis_client = get_redis_client()
            cache_key = f"metrics:cluster:{cluster_id}:summary"
            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.info(f"Returning cached metrics for cluster {cluster_id}")
                return {
                    "cluster_id": cluster_id,
                    "metrics": eval(cached_data),
                    "source": "cache"
                }
        except Exception as cache_error:
            logger.warning(f"Cache read failed: {cache_error}")

        # Fall back to database
        latest_metric = db.query(ClusterMetric).filter(
            ClusterMetric.cluster_id == cluster_id
        ).order_by(ClusterMetric.timestamp.desc()).first()

        if not latest_metric:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No metrics found for cluster {cluster_id}"
            )

        return {
            "cluster_id": cluster_id,
            "metrics": latest_metric.metric_data,
            "timestamp": latest_metric.timestamp.isoformat(),
            "source": "database"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching latest metrics for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics: {str(e)}"
        )


@router.get("/cluster/{cluster_id}/history")
async def get_metrics_history(
    cluster_id: str,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """
    Get historical metrics for a cluster.

    Returns metrics from the past N hours.
    """
    try:
        from datetime import timedelta

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        metrics = db.query(ClusterMetric).filter(
            ClusterMetric.cluster_id == cluster_id,
            ClusterMetric.timestamp >= cutoff_time
        ).order_by(ClusterMetric.timestamp.desc()).all()

        return {
            "cluster_id": cluster_id,
            "hours": hours,
            "total_records": len(metrics),
            "metrics": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "data": m.metric_data
                }
                for m in metrics
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching metrics history for cluster {cluster_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics history: {str(e)}"
        )
