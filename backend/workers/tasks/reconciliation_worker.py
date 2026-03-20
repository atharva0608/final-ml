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
from backend.models.aws_account import AWSAccount
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
        from backend.core.decision_engine import DecisionEngine
        de = DecisionEngine(redis, db)

        instances = db.query(Instance).filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running',
            Instance.instance_id.like('i-%'),
        ).all()

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
            node_info = {
                'instance_type': inst.instance_type,
                'az': inst.az,
                'spot_price': inst.price or 0.0,
                'risk_tier': 2,  # conservative default for OD nodes
                'architecture': getattr(inst, 'architecture', None) or 'amd64',
            }
            alternatives = de.rank_for_node(cluster.id, node_info, region)
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
        clusters = db.query(Cluster).filter(Cluster.status == 'active').all()
        logger.info(f"[reconcile] Checking {len(clusters)} active cluster(s)")

        for cluster in clusters:
            # Skip if any in-progress or waiting_agent RebalancingAction exists —
            # the rebalancer is actively terminating/launching; don't interfere.
            in_progress_count = db.query(RebalancingAction).filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status.in_(['in_progress', 'waiting_agent']),
            ).count()
            if in_progress_count:
                logger.debug(
                    f"[reconcile] Skipping cluster {cluster.id} — "
                    f"{in_progress_count} action(s) in progress"
                )
                continue

            try:
                # Get account for this cluster
                account = db.query(AWSAccount).filter_by(id=cluster.aws_account_id).first()
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
                for db_inst in db_instances:
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

                if missed or terminated:
                    db.commit()
                    logger.info(
                        f"[reconcile] Cluster {cluster.id}: "
                        f"{missed} missed, {terminated} newly terminated"
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
