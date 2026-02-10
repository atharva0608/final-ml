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

        # Calculate aggregated metrics from node data
        total_cpu_capacity = 0
        total_mem_capacity = 0
        total_cpu_usage = 0
        total_mem_usage = 0

        logger.info(f"Processing {len(node_metrics)} node metrics for cluster {cluster_id}")

        for node in node_metrics:
            cpu_cap = node.get("cpu_capacity_millicores", 0)
            cpu_use = node.get("cpu_usage_millicores", 0)
            mem_cap = node.get("memory_capacity_bytes", 0)
            mem_use = node.get("memory_usage_bytes", 0)

            logger.info(f"Node {node.get('node_name')}: CPU cap={cpu_cap}, usage={cpu_use}, Mem cap={mem_cap}, usage={mem_use}")

            # CPU in millicores (1000 millicores = 1 core)
            total_cpu_capacity += cpu_cap
            total_cpu_usage += cpu_use
            # Memory in bytes
            total_mem_capacity += mem_cap
            total_mem_usage += mem_use

        logger.info(f"Totals - CPU cap={total_cpu_capacity}, usage={total_cpu_usage}, Mem cap={total_mem_capacity}, usage={total_mem_usage}")

        # Update individual instance CPU/memory utilization
        from datetime import timedelta
        from ..models.instance import Instance

        for node in node_metrics:
            node_name = node.get("node_name")
            cpu_cap = node.get("cpu_capacity_millicores", 0)
            cpu_use = node.get("cpu_usage_millicores", 0)
            mem_cap = node.get("memory_capacity_bytes", 0)
            mem_use = node.get("memory_usage_bytes", 0)

            # Calculate utilization percentages
            cpu_util_pct = round((cpu_use / cpu_cap) * 100, 2) if cpu_cap > 0 else 0
            mem_util_pct = round((mem_use / mem_cap) * 100, 2) if mem_cap > 0 else 0

            # Find instance by node name (match against instance_id or tags)
            # Node names are typically like ip-192-168-50-10.ec2.internal
            # Try to match with instance by looking for instances in this cluster
            instances = db.query(Instance).filter(
                Instance.cluster_id == cluster_id
            ).all()

            # Update the instance if we can match it
            # For now, update all instances equally (since we might not have exact mapping)
            # In production, you'd match by instance_id from node metadata
            for instance in instances:
                instance.cpu_util = cpu_util_pct
                instance.memory_util = mem_util_pct
                logger.info(f"Updated instance {instance.instance_id}: CPU={cpu_util_pct}%, Mem={mem_util_pct}%")

        # Count instances from instances table for accurate node count
        # Status can be: READY, running, pending, etc.
        total_nodes = db.query(Instance).filter(
            Instance.cluster_id == cluster_id
        ).count()

        # If no instances found, fall back to current batch count
        if total_nodes == 0:
            total_nodes = len(node_metrics)

        logger.info(f"Total nodes from instances table: {total_nodes}")

        # Update cluster with real-time aggregated data
        cluster.node_count = total_nodes
        cluster.cpu_total = int(total_cpu_capacity / 1000)  # Convert millicores to cores
        cluster.mem_total = int(total_mem_capacity / (1024**3))  # Convert bytes to GiB

        logger.info(f"Updated cluster: node_count={cluster.node_count}, cpu_total={cluster.cpu_total}, mem_total={cluster.mem_total}")

        # Calculate usage percentages
        if total_cpu_capacity > 0:
            cluster.cpu_usage_pct = round((total_cpu_usage / total_cpu_capacity) * 100, 2)
            logger.info(f"Calculated CPU usage %: {cluster.cpu_usage_pct}")
        else:
            cluster.cpu_usage_pct = 0
            logger.warning("CPU capacity is 0, setting usage to 0%")

        if total_mem_capacity > 0:
            cluster.mem_usage_pct = round((total_mem_usage / total_mem_capacity) * 100, 2)
            logger.info(f"Calculated Memory usage %: {cluster.mem_usage_pct}")
        else:
            cluster.mem_usage_pct = 0
            logger.warning("Memory capacity is 0, setting usage to 0%")

        logger.info(f"About to commit - cluster.cpu_usage_pct={cluster.cpu_usage_pct}, cluster.mem_usage_pct={cluster.mem_usage_pct}")

        # Calculate spot vs on-demand from node labels
        spot_count = sum(1 for node in node_metrics
                        if node.get("labels", {}).get("node.kubernetes.io/instance-type", "").startswith("spot"))
        cluster.spot_count = spot_count

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
                    "event_metrics": event_metrics[:20],  # Store sample
                    "total_cpu_cores": cluster.cpu_total,
                    "total_mem_gib": cluster.mem_total,
                    "cpu_usage_millicores": total_cpu_usage,
                    "mem_usage_bytes": total_mem_usage,
                    "cpu_usage_pct": float(cluster.cpu_usage_pct) if cluster.cpu_usage_pct else 0,
                    "mem_usage_pct": float(cluster.mem_usage_pct) if cluster.mem_usage_pct else 0
                },
                timestamp=datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow()
            )
            db.add(cluster_metric)

        # Commit cluster updates (including usage percentages)
        db.commit()
        logger.info(f"Committed - cluster.cpu_usage_pct={cluster.cpu_usage_pct}, cluster.mem_usage_pct={cluster.mem_usage_pct}")

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
