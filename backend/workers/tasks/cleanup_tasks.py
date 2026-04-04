"""
Cleanup Tasks — Managed Node Group deletion after Karpenter migration.

When the auto-rebalancer finishes converting all On-Demand nodes to Spot
(on_demand_node_count == 0), this task is triggered to:
1. Verify zero OD instances remain.
2. Find and delete the EKS managed node group.
3. Set cluster.managed_node_group_deleted = True.
4. Set optimization_settings.karpenter_only_mode = True.
"""
import logging
from celery import shared_task
from datetime import datetime

logger = logging.getLogger(__name__)


@shared_task(name='workers.cleanup.cleanup_managed_node_group', bind=True, max_retries=3)
def cleanup_managed_node_group(self, cluster_id: str):
    """Delete the managed node group after all OD nodes have been migrated to Karpenter.

    Prerequisites:
    - Cluster must have zero on-demand instances.
    - Karpenter must be installed.
    - The managed node group must still exist.
    """
    from backend.core.database import SessionLocal
    from backend.models.cluster import Cluster, ClusterOptimizationSettings

    db = SessionLocal()
    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            logger.error(f"[cleanup] Cluster {cluster_id} not found")
            return {"status": "error", "reason": "cluster_not_found"}

        # Guard: already completed
        if getattr(cluster, 'managed_node_group_deleted', False):
            logger.info(f"[cleanup] Cluster {cluster.name}: managed node group already deleted")
            return {"status": "already_done"}

        # Guard: verify zero OD instances
        from backend.models.instance import Instance, InstanceLifecycle
        od_count = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
            Instance.state == 'running',
        ).count()
        if od_count > 0:
            logger.warning(
                f"[cleanup] Cluster {cluster.name}: still has {od_count} OD instance(s) — "
                f"aborting node group deletion"
            )
            return {"status": "aborted", "reason": f"{od_count} OD instances remaining"}

        # Get AWS credentials
        from backend.utils.aws.asg import get_assumed_credentials
        creds = get_assumed_credentials(cluster, db)
        region = cluster.region or "us-east-1"

        # Find managed node groups for this cluster
        import boto3
        eks_kwargs = {"region_name": region}
        if creds:
            eks_kwargs.update(creds)
        eks_client = boto3.client("eks", **eks_kwargs)

        cluster_name = cluster.name
        try:
            ng_response = eks_client.list_nodegroups(clusterName=cluster_name)
            node_groups = ng_response.get("nodegroups", [])
        except Exception as e:
            logger.error(f"[cleanup] Failed to list node groups for {cluster_name}: {e}")
            raise self.retry(exc=e, countdown=60)

        if not node_groups:
            logger.info(
                f"[cleanup] Cluster {cluster_name}: no managed node groups found — "
                f"marking as deleted"
            )
            _mark_migration_complete(db, cluster)
            return {"status": "completed", "reason": "no_node_groups_to_delete"}

        # Delete each managed node group
        deleted = []
        for ng_name in node_groups:
            try:
                # Verify the node group has zero instances before deleting
                ng_info = eks_client.describe_nodegroup(
                    clusterName=cluster_name,
                    nodegroupName=ng_name,
                )
                ng_detail = ng_info.get("nodegroup", {})
                scaling = ng_detail.get("scalingConfig", {})
                desired = scaling.get("desiredSize", 0)

                if desired > 0:
                    logger.warning(
                        f"[cleanup] Node group {ng_name} in {cluster_name} still has "
                        f"desiredSize={desired} — skipping deletion (instances may remain)"
                    )
                    continue

                eks_client.delete_nodegroup(
                    clusterName=cluster_name,
                    nodegroupName=ng_name,
                )
                deleted.append(ng_name)
                logger.info(
                    f"[cleanup] Deleted managed node group '{ng_name}' "
                    f"from cluster {cluster_name}"
                )
            except Exception as e:
                logger.error(
                    f"[cleanup] Failed to delete node group '{ng_name}' "
                    f"in {cluster_name}: {e}"
                )

        if deleted or not node_groups:
            _mark_migration_complete(db, cluster)

        return {
            "status": "completed",
            "deleted_node_groups": deleted,
            "cluster": cluster_name,
        }

    except Exception as e:
        logger.error(f"[cleanup] Unexpected error for cluster {cluster_id}: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def _mark_migration_complete(db, cluster):
    """Set migration-complete flags on cluster and optimization settings."""
    from backend.models.cluster import ClusterOptimizationSettings

    cluster.managed_node_group_deleted = True
    cluster.updated_at = datetime.utcnow()

    opt = db.query(ClusterOptimizationSettings).filter(
        ClusterOptimizationSettings.cluster_id == cluster.id
    ).first()
    if opt:
        opt.karpenter_only_mode = True
        opt.updated_at = datetime.utcnow()

    db.commit()
    logger.info(
        f"[cleanup] Cluster {cluster.name}: marked managed_node_group_deleted=True, "
        f"karpenter_only_mode=True"
    )
