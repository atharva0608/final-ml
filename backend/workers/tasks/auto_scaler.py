"""ASCP.ai Built-in Auto-Scaler (optional, default OFF)

Activated per-cluster via `enable_ascp_auto_scaler = True` in
ClusterOptimizationSettings.  When OFF the task is a no-op for that cluster
and the platform behaves exactly as before: the rebalancer converts OD→spot and
ASG desired may go to zero, leaving any external scaler (CA/Karpenter) in full
control.

Design
------
• `cluster:target:{cluster_id}` (Redis, TTL 7 days) — desired running-node
  count, updated dynamically when pending pods are detected.
• One scale-up action per 30-second cycle (rate-limited via
  `cluster:scaler:cooldown:{cluster_id}`).
• Scale-up is skipped when an in-flight OD node is already being converted
  (avoids over-provisioning during the OD→spot transition window).
• Scale-down: graceful CORDON queued via AgentAction when avg(cpu+mem)
  stays below threshold for the stabilization window.
• Karpenter AUTO mode → task skips that cluster (conflict avoidance).
"""

from datetime import datetime, timedelta

from backend.core.logger import logger
from backend.core.redis_client import get_redis_client
from backend.models.base import get_db
from backend.models.cluster import Cluster, ClusterStatus, ClusterOptimizationSettings, KarpenterMode
from backend.models.instance import Instance, InstanceLifecycle
from backend.models.rebalancing_action import RebalancingAction
from backend.workers.app import app


# ─────────────────────────────────────────────────────────────────────────────
# Celery task
# ─────────────────────────────────────────────────────────────────────────────

@app.task(name='workers.auto_scaler.run', bind=True, max_retries=0)
def run_ascp_auto_scaler(self):
    """Run the built-in auto-scaler for every cluster that has it enabled."""
    db = next(get_db())
    try:
        redis = get_redis_client()
        clusters = (
            db.query(Cluster)
            .filter(Cluster.status == ClusterStatus.ACTIVE)
            .all()
        )
        for cluster in clusters:
            try:
                _run_for_cluster(cluster, db, redis)
            except Exception as exc:
                logger.warning(f"[auto_scaler] Cluster {cluster.name}: {exc}")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Per-cluster logic
# ─────────────────────────────────────────────────────────────────────────────

def _run_for_cluster(cluster, db, redis):
    # ── Gate: only run when explicitly enabled ──────────────────────────────
    settings = (
        db.query(ClusterOptimizationSettings)
        .filter_by(cluster_id=cluster.id)
        .first()
    )
    if not settings or not getattr(settings, 'enable_ascp_auto_scaler', False):
        return

    # ── Gate: skip if Karpenter is managing capacity autonomously ───────────
    if cluster.karpenter_mode == KarpenterMode.AUTO:
        logger.debug(
            f"[auto_scaler] {cluster.name}: Karpenter AUTO active — skip"
        )
        return

    # ── Gate: only run when auto-rebalancing is enabled ─────────────────────
    if not getattr(settings, 'auto_rebalance_enabled', False):
        return

    # ── Resolve ASG name ────────────────────────────────────────────────────
    asg_key = f"cluster:last_asg_name:{cluster.id}"
    asg_name = (redis.get(asg_key) or b'').decode() or None
    if not asg_name:
        last_done = (
            db.query(RebalancingAction)
            .filter(
                RebalancingAction.cluster_id == cluster.id,
                RebalancingAction.status == 'completed',
            )
            .order_by(RebalancingAction.completed_at.desc())
            .first()
        )
        if last_done:
            asg_name = (last_done.action_metadata or {}).get('asg_name_used')
        if asg_name:
            redis.set(asg_key, asg_name, ex=86400 * 30)
    if not asg_name:
        logger.debug(
            f"[auto_scaler] {cluster.name}: no ASG name found — skip until "
            "first completed rebalancing action"
        )
        return

    # ── Read settings ────────────────────────────────────────────────────────
    min_nodes = int(getattr(settings, 'min_node_count', 1) or 1)
    sd_thresh = int(getattr(settings, 'scale_down_threshold_pct', 20) or 20)
    sd_stab_m = int(getattr(settings, 'scale_down_stabilization_minutes', 15) or 15)

    # ── Count running nodes (real EC2 IDs, no orphans / unknown) ────────────
    running_count = (
        db.query(Instance)
        .filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running',
            Instance.instance_id.like('i-%'),
            Instance.instance_type != 'unknown',
        )
        .count()
    )

    # ── Target node count (persisted in Redis) ───────────────────────────────
    target_key = f"cluster:target:{cluster.id}"
    raw_target = redis.get(target_key)
    if raw_target is None:
        # First run — initialise to current running count (≥ min_nodes)
        target = max(running_count, min_nodes)
        redis.set(target_key, target, ex=86400 * 7)
    else:
        target = max(int(raw_target), min_nodes)

    # ── Detect pending / unschedulable pods ─────────────────────────────────
    pending_pod_count = 0
    try:
        from backend.models.pod_metric import PodMetric
        pm_window = datetime.utcnow() - timedelta(minutes=3)
        pending_pod_count = (
            db.query(PodMetric)
            .filter(
                PodMetric.cluster_id == cluster.id,
                PodMetric.timestamp >= pm_window,
                PodMetric.node_name.in_(['unknown', '', 'None', None]),
                PodMetric.cpu_request_millicores > 0,
            )
            .count()
        )
    except Exception as exc:
        logger.debug(f"[auto_scaler] Pending pod query failed: {exc}")

    # Update target when pods are unschedulable (+1 node per 10 pending pods)
    if pending_pod_count > 0:
        additional = max(1, (pending_pod_count + 9) // 10)
        new_target = running_count + additional
        if new_target > target:
            redis.set(target_key, new_target, ex=86400 * 7)
            target = new_target
            logger.info(
                f"[auto_scaler] {cluster.name}: "
                f"pending_pods={pending_pod_count} → target {target}"
            )

    # ── Active rebalancing check ─────────────────────────────────────────────
    has_active = (
        db.query(RebalancingAction)
        .filter(
            RebalancingAction.cluster_id == cluster.id,
            RebalancingAction.status.in_(['in_progress', 'waiting_agent', 'pending']),
        )
        .first()
        is not None
    )

    # ── In-flight OD nodes (being converted by rebalancer) ──────────────────
    od_count = (
        db.query(Instance)
        .filter(
            Instance.cluster_id == cluster.id,
            Instance.state == 'running',
            Instance.lifecycle == InstanceLifecycle.ON_DEMAND,
            Instance.instance_id.like('i-%'),
        )
        .count()
    )

    # ── Scale-up decision ────────────────────────────────────────────────────
    needs_scaleup = (running_count < target) or (running_count < min_nodes)

    # ── Scale-down decision ──────────────────────────────────────────────────
    needs_scaledown = False
    avg_util = 0.0
    if (
        not has_active
        and not needs_scaleup
        and running_count > min_nodes
        and od_count == 0
    ):
        try:
            from sqlalchemy import func
            sd_window = datetime.utcnow() - timedelta(minutes=sd_stab_m)
            avg_row = (
                db.query(
                    func.avg(Instance.cpu_util).label('avg_cpu'),
                    func.avg(Instance.memory_util).label('avg_mem'),
                )
                .filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    Instance.updated_at >= sd_window,
                )
                .first()
            )
            if avg_row:
                avg_cpu = float(avg_row.avg_cpu or 0)
                avg_mem = float(avg_row.avg_mem or 0)
                avg_util = (avg_cpu + avg_mem) / 2
                if avg_util < sd_thresh:
                    needs_scaledown = True
                    logger.info(
                        f"[auto_scaler] {cluster.name}: "
                        f"avg_util={avg_util:.1f}% < {sd_thresh}% "
                        f"for {sd_stab_m}min → scale-down candidate"
                    )
        except Exception as exc:
            logger.debug(f"[auto_scaler] Scale-down check failed: {exc}")

    if not needs_scaleup and not needs_scaledown:
        return

    # ── Build AWS autoscaling client ─────────────────────────────────────────
    try:
        from backend.utils.aws.asg import get_assumed_credentials
        import boto3

        creds = get_assumed_credentials(cluster, db)
        cred_kwargs = {}
        if creds:
            cred_kwargs = {
                'aws_access_key_id': creds.get('AccessKeyId') or creds.get('access_key'),
                'aws_secret_access_key': creds.get('SecretAccessKey') or creds.get('secret_key'),
                'aws_session_token': creds.get('SessionToken') or creds.get('session_token'),
            }

        asg_client = boto3.client(
            'autoscaling',
            region_name=cluster.region or 'ap-south-1',
            **cred_kwargs,
        )
        asg_info = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        asg_groups = asg_info.get('AutoScalingGroups', [])
        if not asg_groups:
            logger.warning(f"[auto_scaler] ASG '{asg_name}' not found")
            return

        cur_des = asg_groups[0]['DesiredCapacity']
        max_sz = asg_groups[0]['MaxSize']
        min_sz = asg_groups[0]['MinSize']

        # ── Execute scale-up ────────────────────────────────────────────────
        if needs_scaleup:
            scaleup_cooldown_key = f"cluster:scaler:cooldown:{cluster.id}"
            if redis.get(scaleup_cooldown_key):
                # Rate-limited: wait for cooldown to expire
                return

            if od_count > 0:
                # In-flight OD conversion in progress — don't double-bump
                logger.debug(
                    f"[auto_scaler] {cluster.name}: {od_count} OD in-flight "
                    "— skip bump, will retry next cycle"
                )
                return

            new_des = min(cur_des + 1, max_sz)
            if new_des > cur_des:
                asg_client.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    DesiredCapacity=new_des,
                )
                # 30-second cooldown between scale-up bumps
                redis.set(scaleup_cooldown_key, '1', ex=30)
                logger.info(
                    f"[auto_scaler] SCALE-UP '{asg_name}': "
                    f"desired {cur_des}→{new_des} "
                    f"(running={running_count}, target={target}, "
                    f"pending_pods={pending_pod_count})"
                )
            else:
                logger.debug(
                    f"[auto_scaler] {cluster.name}: "
                    f"already at ASG max ({max_sz}) — cannot scale up further"
                )

        # ── Execute scale-down (graceful) ───────────────────────────────────
        elif needs_scaledown and not has_active:
            idle_node = (
                db.query(Instance)
                .filter(
                    Instance.cluster_id == cluster.id,
                    Instance.state == 'running',
                    Instance.lifecycle == InstanceLifecycle.SPOT,
                    Instance.instance_id.like('i-%'),
                )
                .order_by(Instance.cpu_util.asc().nullslast())
                .first()
            )
            if idle_node:
                from backend.models.agent_action import (
                    AgentAction,
                    AgentActionType,
                    AgentActionStatus,
                )
                sd_action = AgentAction(
                    cluster_id=cluster.id,
                    action_type=AgentActionType.CORDON_NODE,
                    status=AgentActionStatus.PENDING,
                    payload={
                        "node_name": idle_node.node_name,
                        "reason": "ascp_autoscaler_scale_down",
                    },
                    action_metadata={
                        "autoscaler": True,
                        "scale_down": True,
                        "avg_util": f"{avg_util:.1f}%",
                        "asg_name": asg_name,
                    },
                )
                db.add(sd_action)
                # Decrement Redis target so we don't immediately scale back up
                new_target = max(min_nodes, target - 1)
                redis.set(target_key, new_target, ex=86400 * 7)
                db.flush()
                logger.info(
                    f"[auto_scaler] SCALE-DOWN: queued cordon of "
                    f"{idle_node.node_name} "
                    f"(avg_util={avg_util:.1f}% < {sd_thresh}%, "
                    f"running={running_count}, target {target}→{new_target})"
                )

    except Exception as exc:
        logger.warning(
            f"[auto_scaler] ASG operation failed for '{asg_name}': {exc}"
        )
