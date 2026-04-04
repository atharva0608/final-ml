"""
Emergency Rebalancer — Karpenter-Only Spot Interruption Handler
================================================================

Dedicated Celery task for handling spot interruptions via Karpenter.

Karpenter path:
1. CORDON the interrupted node
2. DRAIN with emergency settings (90s grace, force=True)
3. TERMINATE_NODE with termination_mode=karpenter (direct EC2 terminate)
4. Karpenter automatically provisions replacement via NodePool constraints

Requires Karpenter to be installed. Non-Karpenter clusters are skipped.

Triggered by:
- SQS messages from EventBridge (spot interruption warning)
- Direct HTTP calls from the agent (metadata polling)
- recovery_monitor task (orphaned instance detection)
"""

from datetime import datetime, timedelta
from backend.core.logger import logger
from backend.workers.app import app
from backend.core.config import EMERGENCY_COOLDOWN_MINUTES


@app.task(name="emergency_rebalancer", bind=True, max_retries=1, queue="emergency")
def emergency_rebalancer(
    self,
    cluster_id: str,
    instance_id: str,
    reason: str = "spot_interruption",
):
    """
    Handle spot interruption with standby-first strategy.

    Args:
        cluster_id: Cluster ID
        instance_id: Instance DB ID of the interrupted node
        reason: "spot_interruption" or "recovery"
    """
    from backend.models.base import get_db, generate_uuid
    from backend.models.cluster import Cluster
    from backend.models.instance import Instance
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.models.rebalancing_action import RebalancingAction
    from backend.core.redis_client import get_redis_client, key_cluster_cooldown, key_blacklist_global, key_rebalance_lock

    db = next(get_db())
    redis = get_redis_client()

    # Override cooldowns — emergency takes priority
    redis.delete(key_cluster_cooldown(cluster_id))
    redis.delete(key_rebalance_lock(cluster_id))
    logger.info(f"[emergency] Cleared cooldowns for cluster {cluster_id} (emergency override)")

    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        interrupted = db.query(Instance).filter(Instance.id == instance_id).first()

        if not cluster or not interrupted:
            logger.error(
                f"[emergency] Cluster {cluster_id} or instance {instance_id} not found"
            )
            return {"status": "error", "message": "not_found"}

        logger.info(
            f"[emergency] Handling {reason} for {interrupted.node_name} "
            f"({interrupted.instance_type}) in cluster {cluster.name}"
        )

        # Report termination to DE (blacklist the pool) and set 24h global blacklist
        pool_key = f"{interrupted.instance_type}:{interrupted.az}"
        try:
            from backend.services.decision_engine_service import DecisionEngineService
            de = DecisionEngineService(db, redis)
            de.report_termination(pool_key=pool_key, region=cluster.region or "ap-south-1")
        except Exception as de_err:
            logger.warning(f"[emergency] DE report_termination failed: {de_err}")

        # Blacklist terminated pool for 24 hours
        from backend.core.config import POOL_TERMINATION_BLACKLIST_HOURS
        redis.setex(key_blacklist_global(pool_key), POOL_TERMINATION_BLACKLIST_HOURS * 3600, '1')
        logger.info(f"[emergency] Blacklisted pool {pool_key} for {POOL_TERMINATION_BLACKLIST_HOURS}h")

        # Update global EMA interruption tracker
        try:
            from backend.services.global_ema_service import update_ema_on_interruption
            update_ema_on_interruption(
                redis=redis, db=db, pool_key=pool_key,
                instance_type=interrupted.instance_type,
                az=interrupted.az,
                region=cluster.region or "ap-south-1",
                cluster_id=cluster_id,
            )
        except Exception as _ema_err:
            logger.warning(f"[emergency] EMA update failed for {pool_key}: {_ema_err}")

        # Issue 14: Event-driven pool ranking refresh — trigger incremental rebuild
        # after a spot interruption so the ranking cache reflects the updated blacklist
        # without waiting for the next hourly build. Debounced to at most 1 refresh/60s.
        try:
            _er_region = cluster.region or "ap-south-1"
            _refresh_debounce_key = f'ranking_refresh_pending:{_er_region}'
            if not redis.get(_refresh_debounce_key):
                redis.setex(_refresh_debounce_key, 60, '1')
                from backend.workers.app import app as _celery_app
                _celery_app.send_task(
                    'build_global_pool_cache',
                    args=[_er_region],
                    countdown=5,
                    queue='celery',
                )
                logger.debug(
                    '[emergency] Triggered incremental pool ranking refresh for region %s '
                    'after spot interruption of pool %s', _er_region, pool_key
                )
        except Exception as _pref_err:
            logger.debug('[emergency] Ranking refresh trigger failed (non-fatal): %s', _pref_err)

        # Create rebalancing action record — use actual model fields:
        # trigger (NOT NULL), source_pool (NOT NULL), target_pool (NOT NULL), started_at (NOT NULL)
        # source_pool / target_pool format: "{instance_type}:{az}"
        _pool_key = f"{interrupted.instance_type}:{interrupted.az}"
        action = RebalancingAction(
            cluster_id=cluster_id,
            trigger='emergency',
            source_pool=_pool_key,
            target_pool=_pool_key,
            status="in_progress",
            started_at=datetime.utcnow(),
            source_instance_id=interrupted.instance_id,
            action_metadata={"trigger_reason": reason},
        )
        db.add(action)
        db.commit()

        # ── Karpenter-only path ────────────────────────────────────────
        # Only Karpenter clusters are supported. If Karpenter is not installed,
        # log a warning and skip — the old non-Karpenter emergency paths have
        # been removed.
        _karp_key = f"spot:karpenter:installed:{cluster_id}"
        if not redis.exists(_karp_key):
            logger.warning(
                f"[emergency] Karpenter not installed on {cluster.name} — "
                f"cannot handle emergency rebalancing. Install Karpenter first."
            )
            action.status = "failed"
            action.error_message = "Karpenter not installed — emergency rebalancing requires Karpenter"
            action.completed_at = datetime.utcnow()
            db.commit()
            return {"status": "error", "message": "karpenter_not_installed"}

        logger.info(
            f"[emergency] Karpenter installed on {cluster.name} — "
            f"using EC2 direct terminate path"
        )
        result = _execute_karpenter_emergency(
            db, redis, cluster, interrupted, action
        )
        # Set 2-hour emergency cooldown after completion
        redis.setex(
            key_cluster_cooldown(cluster_id),
            EMERGENCY_COOLDOWN_MINUTES * 60,
            '1'
        )
        logger.info(f"[emergency] Set {EMERGENCY_COOLDOWN_MINUTES}min cooldown for cluster {cluster_id}")
        return result

    except Exception as e:
        logger.error(f"[emergency] Failed for cluster {cluster_id}: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def _execute_karpenter_emergency(db, redis, cluster, interrupted, action):
    """
    Karpenter emergency path — direct EC2 terminate, zero ASG interaction.

    Steps:
    1. CORDON the interrupted node (prevent new scheduling)
    2. DRAIN with 90s grace + force (emergency mode)
    3. Direct ec2.terminate_instances() — Karpenter will auto-provision replacement
    4. Update action record

    Karpenter's `consolidationPolicy: WhenUnderutilized` + NodePool constraints
    ensure a replacement is launched automatically once the node is gone.
    """
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.models.base import generate_uuid

    try:
        # 1. Cordon interrupted node
        cordon_action = AgentAction(
            id=generate_uuid(),
            cluster_id=cluster.id,
            action_type=AgentActionType.CORDON_NODE,
            payload={"node_name": interrupted.node_name},
            status=AgentActionStatus.PENDING,
            priority=10,  # Emergency priority
        )
        db.add(cordon_action)
        db.commit()

        # 2. Drain with emergency settings (90s grace, force=True)
        drain_action = AgentAction(
            id=generate_uuid(),
            cluster_id=cluster.id,
            action_type=AgentActionType.DRAIN_NODE,
            payload={
                "node_name": interrupted.node_name,
                "grace_period": 90,
                "ignore_daemonsets": True,
                "force": True,
                "emergency": True,
            },
            status=AgentActionStatus.PENDING,
            priority=10,
        )
        db.add(drain_action)
        db.commit()
        logger.info(f"[emergency/karpenter] CORDON+DRAIN queued for {interrupted.node_name}")

        # 3. Queue TERMINATE_NODE with termination_mode=karpenter
        #    The agent actuator will call ec2.terminate_instances() directly,
        #    with zero ASG detach/suspend/resume calls.
        terminate_action = AgentAction(
            id=generate_uuid(),
            cluster_id=cluster.id,
            action_type=AgentActionType.TERMINATE_NODE,
            payload={
                "node_name": interrupted.node_name,
                "instance_id": interrupted.instance_id,
                "termination_mode": "karpenter",
                "reason": "emergency_karpenter",
            },
            status=AgentActionStatus.PENDING,
            priority=10,
        )
        db.add(terminate_action)
        db.commit()
        logger.info(
            f"[emergency/karpenter] TERMINATE_NODE queued for {interrupted.instance_id} "
            f"(mode=karpenter, direct EC2 terminate)"
        )

        # 4. Mark interrupted as terminating
        interrupted.state = "terminating"
        db.commit()

        # 5. Update action record
        action.status = "completed"
        action.completed_at = datetime.utcnow()
        action.action_metadata = {
            "emergency": True,
            "method": "karpenter_direct",
            "termination_mode": "karpenter",
        }
        db.commit()

        return {
            "status": "ok",
            "method": "karpenter_direct",
            "interrupted_node": interrupted.node_name,
            "interrupted_instance": interrupted.instance_id,
            "termination_mode": "karpenter",
        }

    except Exception as e:
        logger.error(f"[emergency/karpenter] Karpenter emergency failed: {e}")
        db.rollback()
        return {"status": "error", "method": "karpenter_direct", "error": str(e)}
