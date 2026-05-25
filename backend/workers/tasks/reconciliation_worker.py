"""
Reconciliation Worker — Issue #34
==================================

Runs every 5 minutes via Celery beat.
Compares live EC2 state against DB instances; marks instances terminated
after 2 consecutive misses (prevents false positives from API transients).

Guardrails:
- Skips any cluster with in-progress / waiting_agent RebalancingActions
  to avoid interfering with active cordon→drain→terminate sequences.
- Uses 2-miss Redis counter (10-min TTL) before marking terminated.
- Reuses the same STS assume-role pattern as discovery worker.
"""

import boto3
import json
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from backend.workers.app import app
from backend.models.base import get_db
from backend.models.instance import Instance, InstanceLifecycle
from backend.models.rebalancing_action import RebalancingAction
from backend.models.account import Account as AWSAccount
from backend.models.cluster import Cluster
from backend.models.system_config import SystemConfig
from backend.core.logger import logger
from backend.core.redis_client import get_redis_client

_MISS_KEY_PREFIX = "reconcile:miss:"
_MISS_THRESHOLD = 2   # Mark terminated after 2 consecutive misses
_MISS_TTL_S = 600     # 10-minute TTL on miss counters (auto-clears if instance reappears)
_COVERAGE_TTL_S = 300  # 5-minute TTL on cluster coverage report


def _compute_cluster_coverage(db: Session, redis, cluster) -> dict:
    """
    Compute per-node coverage report for a cluster.

    For each running instance, ranks alternative spot pools using the decision
    engine and classifies each node as:
      COVERED    — ≥3 valid alternatives
      AT_RISK    — 1-2 valid alternatives
      STRANDED   — 0 valid alternatives
      IMMOVABLE  — node is on-demand with local PV (skip)

    Writes to Redis: cluster_coverage:{cluster_id}  TTL=300s
    Returns the ClusterCoverageReport dict.
    """
    try:
        from backend.services.pool_ranking_service import PoolRankingService
        from backend.core.redis_client import get_redis_client as _grc_cov
        _prs_cov = PoolRankingService(db, _grc_cov())

        instances = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running',
            Instance.instance_id.like('i-%') | Instance.instance_id.like('ip-%'),
        ).all()

        # ── Filter out replacement instances from active migrations ────────
        # Replacement nodes are part of an ongoing migration and should not
        # appear as separate entries in the coverage / dropdown.
        _active_replacement_ids = set()
        try:
            _active_actions = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status.in_(['in_progress', 'waiting_agent', 'pending']),
            ).all()
            for _aa in _active_actions:
                _meta = _aa.action_metadata or {}
                _repl_id = _meta.get('replacement_spot_instance_id')
                if _repl_id:
                    _active_replacement_ids.add(_repl_id)
        except Exception as _mig_err:
            logger.warning(f"[coverage] migration filter failed: {_mig_err}")

        if _active_replacement_ids:
            instances = [i for i in instances if i.instance_id not in _active_replacement_ids]

        if not instances:
            report = {
                "cluster_id": cluster.id,
                "cluster_name": getattr(cluster, 'name', cluster.id),
                "total_nodes": 0,
                "covered_nodes": 0, "at_risk_nodes": 0,
                "stranded_nodes": 0, "immovable_nodes": 0,
                "cluster_coverage_pct": 0.0,
                "per_node_summary": [],
                "computed_at": datetime.utcnow().isoformat(),
            }
            redis.setex(f"cluster_coverage:{cluster.id}", _COVERAGE_TTL_S, json.dumps(report))
            return report

        region = getattr(cluster, 'region', None) or 'us-east-1'

        covered = at_risk = stranded = immovable = 0
        per_node_summary = []

        for inst in instances:
            try:
                from backend.workers.tasks.cache_builder import _lookup_specs as _cb_specs
                _vcpu, _mem, _arch, _ = _cb_specs(inst.instance_type)
            except Exception:
                _vcpu, _mem, _arch = 0, 0.0, 'amd64'
            node_info = {
                'instance_type': inst.instance_type,
                'az': inst.az,
                'spot_price': inst.price or 0.0,
                'risk_tier': 2,  # conservative default for OD nodes
                'architecture': _arch or getattr(inst, 'architecture', None) or 'amd64',
                'resource_profile': {
                    'min_vcpu_required': _vcpu,
                    'min_memory_required': _mem,
                    'architecture': _arch or 'amd64',
                },
            }
            alternatives = _prs_cov.rank_pools_for_node(
                node_info=node_info,
                cluster_id=cluster.id,
                region=region,
                include_dynamic_filters=True,
            )
            alt_count = len(alternatives)

            if alt_count >= 3:
                status = "COVERED"
                covered += 1
            elif alt_count >= 1:
                status = "AT_RISK"
                at_risk += 1
            else:
                status = "STRANDED"
                stranded += 1

            best_pool = best_saving_pct = None
            if alternatives:
                best = alternatives[0]
                best_pool = f"{best.get('instance_type', '')}:{best.get('az', '')}"
                src_price = inst.price or 0.0
                pool_price = best.get('spot_price') or best.get('price') or 0.0
                if src_price > 0 and pool_price > 0:
                    best_saving_pct = round((1 - pool_price / src_price) * 100, 1)

            per_node_summary.append({
                "node_id": inst.id,
                "instance_id": inst.instance_id,
                "node_name": getattr(inst, 'node_name', None) or inst.instance_id,
                "instance_type": inst.instance_type,
                "az": inst.az,
                "architecture": getattr(inst, 'architecture', 'amd64'),
                "lifecycle": inst.lifecycle.value if inst.lifecycle else 'on-demand',
                "status": status,
                # node_health_status: K8s / collector health (READY, UNKNOWN, CALIBRATING).
                # UNKNOWN = EC2 running in AWS but K8s node is gone (orphaned/failed-terminate).
                "node_health_status": getattr(inst, 'status', None) or 'READY',
                "alternative_count": alt_count,
                "best_pool": best_pool,
                "best_saving_pct": best_saving_pct,
            })

        rebalanceable = len(instances) - immovable
        coverage_pct = round(covered / rebalanceable * 100, 1) if rebalanceable > 0 else 0.0

        report = {
            "cluster_id": cluster.id,
            "cluster_name": getattr(cluster, 'name', cluster.id),
            "total_nodes": len(instances),
            "covered_nodes": covered,
            "at_risk_nodes": at_risk,
            "stranded_nodes": stranded,
            "immovable_nodes": immovable,
            "cluster_coverage_pct": coverage_pct,
            "per_node_summary": per_node_summary,
            "computed_at": datetime.utcnow().isoformat(),
        }
        redis.setex(f"cluster_coverage:{cluster.id}", _COVERAGE_TTL_S, json.dumps(report))
        return report

    except Exception as e:
        logger.error(f"[coverage] _compute_cluster_coverage failed for {cluster.id}: {e}")
        return {}


def _get_platform_sts_client(db: Session):
    """Get STS client using platform credentials stored in SystemConfig."""
    access_key = db.query(SystemConfig).filter_by(key="PLATFORM_AWS_ACCESS_KEY").first()
    secret_key = db.query(SystemConfig).filter_by(key="PLATFORM_AWS_SECRET").first()
    region = db.query(SystemConfig).filter_by(key="PLATFORM_AWS_REGION").first()
    region_name = region.value if region and region.value else 'us-east-1'
    if access_key and secret_key and access_key.value and secret_key.value:
        return boto3.client(
            'sts',
            aws_access_key_id=access_key.value,
            aws_secret_access_key=secret_key.value,
            region_name=region_name,
        )
    return boto3.client('sts', region_name=region_name)


def _assume_role_for_account(sts_client, account: AWSAccount):
    """Assume customer role; returns credentials dict or None (env chain fallback)."""
    if not account.role_arn:
        return None
    assume_kwargs = {
        'RoleArn': account.role_arn,
        'RoleSessionName': f"SpotOptimizer-Reconcile-{account.id}",
    }
    if account.external_id:
        assume_kwargs['ExternalId'] = account.external_id
    try:
        return sts_client.assume_role(**assume_kwargs)['Credentials']
    except ClientError as e:
        logger.warning(f"[reconcile] AssumeRole failed for {account.aws_account_id}: {e}")
        return None


def _ec2_client(region: str, credentials):
    if credentials:
        return boto3.client(
            'ec2', region_name=region,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
        )
    return boto3.client('ec2', region_name=region)


@app.task(name='workers.reconciliation_worker')
def reconciliation_worker():
    """
    Reconcile DB instance state against live EC2 every 5 min.
    Marks instances terminated after 2 consecutive misses.
    """
    db = next(get_db())
    redis = get_redis_client()

    try:
        sts_client = _get_platform_sts_client(db)

        # Get all active clusters
        clusters = db.query(Cluster).filter(Cluster.status == 'ACTIVE').all()
        logger.info(f"[reconcile] Checking {len(clusters)} active cluster(s)")

        for cluster in clusters:
            # Z14: Instead of skipping the entire cluster when actions are in progress,
            # collect the specific instance IDs involved in active actions and skip
            # only those during reconciliation — prevents ghost rows accumulating
            # in clusters that rebalance frequently.
            _active_actions = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
            ).all()
            _protected_instance_ids = set()
            for _aa in _active_actions:
                if _aa.source_instance_id:
                    _protected_instance_ids.add(_aa.source_instance_id)
                # Replacement spot ID lives in action_metadata
                _repl_id = (_aa.action_metadata or {}).get('replacement_spot_instance_id')
                if _repl_id:
                    _protected_instance_ids.add(_repl_id)
            if _protected_instance_ids:
                logger.debug(
                    f"[reconcile] Cluster {cluster.id}: protecting {len(_protected_instance_ids)} "
                    f"instance(s) involved in active actions"
                )

            try:
                # Get account for this cluster
                account = db.query(AWSAccount).filter_by(id=cluster.account_id).first()
                if not account:
                    logger.warning(f"[reconcile] No account found for cluster {cluster.id}")
                    continue

                region = cluster.region or 'us-east-1'
                credentials = _assume_role_for_account(sts_client, account)
                ec2 = _ec2_client(region, credentials)

                # Paginate live running/pending instances tagged to this cluster
                paginator = ec2.get_paginator('describe_instances')
                live_ids: set = set()
                tag_filter = [
                    {
                        'Name': f'tag:kubernetes.io/cluster/{cluster.name}',
                        'Values': ['owned', 'shared'],
                    },
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running', 'pending'],
                    },
                ]
                for page in paginator.paginate(Filters=tag_filter):
                    for reservation in page['Reservations']:
                        for inst in reservation['Instances']:
                            live_ids.add(inst['InstanceId'])

                # Query DB running instances with real EC2 IDs (exclude ip- placeholders)
                db_instances = db.query(Instance).filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    Instance.instance_id.like('i-%'),
                ).all()

                missed = 0
                terminated = 0
                _skipped_protected = 0
                for db_inst in db_instances:
                    # Z14: Skip instances actively managed by the rebalancer
                    if db_inst.instance_id in _protected_instance_ids:
                        _skipped_protected += 1
                        continue
                    miss_key = f"{_MISS_KEY_PREFIX}{db_inst.instance_id}"
                    if db_inst.instance_id not in live_ids:
                        miss_count = int(redis.incr(miss_key) or 0)
                        redis.expire(miss_key, _MISS_TTL_S)
                        missed += 1
                        if miss_count >= _MISS_THRESHOLD:
                            db_inst.state = 'terminated'
                            db_inst.terminated_at = datetime.utcnow()
                            redis.delete(miss_key)
                            terminated += 1
                            logger.warning(
                                f"[reconcile] Marked {db_inst.instance_id} terminated "
                                f"(missing {miss_count}x from EC2, cluster={cluster.id})"
                            )
                        else:
                            logger.debug(
                                f"[reconcile] {db_inst.instance_id} miss #{miss_count}/{_MISS_THRESHOLD}"
                            )
                    else:
                        # Instance is alive — clear any accumulated miss counter
                        redis.delete(miss_key)

                if missed or terminated or _skipped_protected:
                    db.commit()
                    logger.info(
                        f"[reconcile] Cluster {cluster.id}: "
                        f"{missed} missed, {terminated} newly terminated"
                        + (f", {_skipped_protected} skipped (active action)" if _skipped_protected else "")
                    )

                # Compute per-node coverage report after reconciliation
                _compute_cluster_coverage(db, redis, cluster)

            except Exception as cluster_err:
                logger.error(f"[reconcile] Cluster {cluster.id} failed: {cluster_err}")
                db.rollback()

        logger.info("[reconcile] Reconciliation cycle complete")

    except Exception as e:
        logger.error(f"[reconcile] Worker top-level error: {e}")
    finally:
        db.close()


@app.task(name='workers.cleanup_terminated_instances')
def cleanup_terminated_instances():
    """
    Nightly cleanup — Issue #23: Ghost Nodes Table Cleanup.
    Deletes Instance rows where state='terminated' AND updated_at < now() - 30 days.
    Keeps recent terminated rows (< 30 days) for audit / savings calculations.
    """
    db = next(get_db())
    cutoff = datetime.utcnow() - timedelta(days=30)

    try:
        # Count before delete for logging
        stale_count = db.query(Instance).filter(
            Instance.state == 'terminated',
            Instance.updated_at < cutoff,
        ).count()

        if stale_count == 0:
            logger.info("[cleanup] No stale terminated instances to delete")
            return

        db.query(Instance).filter(
            Instance.state == 'terminated',
            Instance.updated_at < cutoff,
        ).delete(synchronize_session=False)
        db.commit()
        logger.info(f"[cleanup] Deleted {stale_count} terminated instance row(s) older than 30 days")

    except Exception as e:
        logger.error(f"[cleanup] cleanup_terminated_instances failed: {e}")
        db.rollback()
    finally:
        db.close()


@app.task(name='workers.cleanup_old_migration_events')
def cleanup_old_migration_events():
    """
    Nightly cleanup — §10 Migration Event Retention.
    Deletes migration_event rows older than 30 days.
    The StatefulMigrationStatusPanel only needs the last 50 migrations;
    rows beyond 30 days accumulate indefinitely without this task.
    """
    db = next(get_db())
    cutoff = datetime.utcnow() - timedelta(days=30)

    try:
        from backend.models.migration_event import MigrationEvent
        stale_count = db.query(MigrationEvent).filter(
            MigrationEvent.created_at < cutoff,
        ).count()

        if stale_count == 0:
            logger.info("[cleanup] No stale migration_event rows to delete")
            return

        db.query(MigrationEvent).filter(
            MigrationEvent.created_at < cutoff,
        ).delete(synchronize_session=False)
        db.commit()
        logger.info(f"[cleanup] Deleted {stale_count} migration_event row(s) older than 30 days")

    except Exception as e:
        logger.error(f"[cleanup] cleanup_old_migration_events failed: {e}")
        db.rollback()
    finally:
        db.close()


@app.task(name='workers.karpenter.reconcile_nodepool_classes')
def reconcile_nodepool_classes_task():
    """
    Task 2.1: Reconcile NodePool classes for all active clusters.
    Runs every 5-10 minutes via Beat. Internally rate-limits to 30m per class.
    """
    db = next(get_db())
    redis = get_redis_client()
    
    if not redis:
        logger.warning("[reconcile_nodepool_classes] Redis not available — skipping")
        return
        
    try:
        from backend.models.cluster import Cluster
        from backend.services.nodepool_reconciler_service import NodePoolReconcilerService
        
        clusters = db.query(Cluster).filter(Cluster.status == 'ACTIVE').all()
        reconciler = NodePoolReconcilerService(redis)
        
        for cluster in clusters:
            try:
                reconciler.reconcile_all_classes(str(cluster.id), db, {})
            except Exception as e:
                logger.error(f"[reconcile_nodepool_classes] Failed for cluster {cluster.name}: {e}")
                
    except Exception as e:
        logger.error(f"[reconcile_nodepool_classes] Master error: {e}")
    finally:
        db.close()


@app.task(name='workers.karpenter.reconcile_nodepool_types')
def reconcile_nodepool_types():
    """
    W3.0e — Karpenter NodePool type list reconciliation.

    Runs every 6 hours via Celery beat. For each active cluster:
    1. Scan all per-injection tracking keys (spot:injected_type:*).
    2. For each expired injection (key no longer exists with TTL), check if
       the type is still in the NodePool but not in the baseline.
    3. If no active rebalancing action references the type, remove it.
    4. If the baseline key is missing entirely, re-snapshot the NodePool.

    This closes the accumulation bug (H2 / HOLE-2 in plan.md §5) where
    a Redis flush between add/remove leaves stale types in the NodePool.
    """
    import json as _json
    from backend.services.karpenter_service import KarpenterService
    from backend.models.rebalancing_action import RebalancingAction

    redis = get_redis_client()
    if not redis:
        logger.warning("[reconcile_nodepool] Redis not available — skipping")
        return

    db = next(get_db())
    try:
        clusters = db.query(Cluster).filter(
            Cluster.karpenter_mode.isnot(None),
        ).all()

        for cluster in clusters:
            cluster_id = str(cluster.id)
            try:
                ksvc = KarpenterService(db=db, redis=redis)
                api_client = ksvc._get_k8s_client(cluster)
                from kubernetes import client as _k8s
                custom_api = _k8s.CustomObjectsApi(api_client)

                # List all NodePools for this cluster
                try:
                    nps = custom_api.list_cluster_custom_object(
                        group="karpenter.sh", version="v1", plural="nodepools",
                    )
                except Exception as e:
                    logger.debug(f"[reconcile_nodepool] cluster {cluster.name}: list NodePools failed: {e}")
                    continue

                for np_item in nps.get("items", []):
                    np_name = np_item.get("metadata", {}).get("name", "default")
                    baseline_key = f"karpenter:nodepool_baseline:{cluster_id}:{np_name}"

                    # Read baseline
                    baseline_raw = redis.get(baseline_key)
                    if not baseline_raw:
                        # Baseline missing — re-snapshot current NodePool state as new baseline
                        reqs = (np_item.get("spec", {}).get("template", {})
                                .get("spec", {}).get("requirements", []))
                        current_types = []
                        for req in reqs:
                            if req.get("key") == "node.kubernetes.io/instance-type":
                                current_types = sorted(req.get("values", []))
                        if current_types:
                            redis.setex(baseline_key, 86400, _json.dumps(current_types))
                            logger.info(
                                f"[reconcile_nodepool] Re-snapshotted baseline for "
                                f"{cluster.name}/{np_name}: {current_types}"
                            )
                        continue

                    baseline_types = set(_json.loads(baseline_raw))

                    # Read current NodePool types
                    reqs = (np_item.get("spec", {}).get("template", {})
                            .get("spec", {}).get("requirements", []))
                    current_types: list = []
                    for req in reqs:
                        if req.get("key") == "node.kubernetes.io/instance-type":
                            current_types = req.get("values", [])
                    current_types_set = set(current_types)

                    # Find types NOT in baseline (potential orphans)
                    injected = current_types_set - baseline_types
                    if not injected:
                        continue

                    # Check which injected types still have active tracking keys
                    active_injected = set()
                    for itype in injected:
                        track_key = f"spot:injected_type:{cluster_id}:{np_name}:{itype}"
                        if redis.exists(track_key):
                            active_injected.add(itype)

                    # Orphans: injected but tracking key expired AND no active rebalancing action
                    orphans = injected - active_injected
                    if not orphans:
                        continue

                    # Verify no active rebalancing action references these types
                    active_actions = db.query(RebalancingAction).filter(
                        RebalancingAction.cluster_id == cluster.id,
                        RebalancingAction.status.in_(["pending", "running", "in_progress"]),
                    ).all()
                    action_types = set()
                    for act in active_actions:
                        meta = act.metadata or {}
                        it = meta.get("target_instance_type") or meta.get("instance_type")
                        if it:
                            action_types.add(it)

                    safe_to_remove = orphans - action_types
                    if not safe_to_remove:
                        continue

                    # Restore NodePool to baseline (remove stale types)
                    clean_types = sorted(current_types_set - safe_to_remove)
                    clean_patch = {
                        "spec": {
                            "template": {
                                "spec": {
                                    "requirements": [
                                        req for req in reqs
                                        if req.get("key") != "node.kubernetes.io/instance-type"
                                    ] + [
                                        {
                                            "key": "node.kubernetes.io/instance-type",
                                            "operator": "In",
                                            "values": clean_types,
                                        }
                                    ]
                                }
                            }
                        }
                    }
                    custom_api.patch_cluster_custom_object(
                        group="karpenter.sh", version="v1",
                        plural="nodepools", name=np_name,
                        body=clean_patch,
                    )
                    logger.info(
                        f"[reconcile_nodepool] Removed orphaned instance types "
                        f"{safe_to_remove} from {cluster.name}/{np_name}"
                    )

            except Exception as cluster_err:
                logger.error(
                    f"[reconcile_nodepool] Error processing cluster {cluster.name}: {cluster_err}"
                )
                continue

    except Exception as e:
        logger.error(f"[reconcile_nodepool] reconcile_nodepool_types failed: {e}")
    finally:
        db.close()
