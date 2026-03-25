"""
Emergency Rebalancer — Standby-Aware Spot Interruption Handler
================================================================

Dedicated Celery task for handling spot interruptions with a
standby-first strategy:

1. If a standby node is available → UNCORDON it, drain the interrupted
   node, terminate it, and launch a new standby.
2. If no standby → fall back to normal emergency launch (launch new
   spot, wait for it, drain interrupted node).

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

        # ── Task 3.1: Karpenter EC2 direct path ────────────────────────
        # If Karpenter manages this cluster, skip all ASG interaction
        # (detach / terminate-in-group would conflict with Karpenter's
        # NodeClaim reconciler).  Use direct ec2.terminate_instances().
        _karp_key = f"spot:karpenter:installed:{cluster_id}"
        if redis.exists(_karp_key):
            logger.info(
                f"[emergency] Karpenter installed on {cluster.name} — "
                f"using EC2 direct terminate path"
            )
            return _execute_karpenter_emergency(
                db, redis, cluster, interrupted, action
            )

        # Check cluster settings for standby
        # Use cluster.optimization_settings (ClusterOptimizationSettings relationship)
        # cluster.settings does not exist as a Cluster model attribute
        opt_settings = cluster.optimization_settings
        maintain_standby = opt_settings.maintain_standby if opt_settings else False

        if maintain_standby:
            standby = _find_ready_standby(db, cluster_id)
            if standby:
                logger.info(
                    f"[emergency] Using standby {standby.node_name} "
                    f"({standby.instance_type}) for failover"
                )
                result = _execute_standby_failover(
                    db, redis, cluster, interrupted, standby, action
                )
                # Set 2-hour emergency cooldown after standby failover
                redis.setex(
                    key_cluster_cooldown(cluster_id),
                    EMERGENCY_COOLDOWN_MINUTES * 60,
                    '1'
                )
                logger.info(f"[emergency] Set {EMERGENCY_COOLDOWN_MINUTES}min cooldown for cluster {cluster_id}")
                return result

        # Fallback: no standby — normal emergency flow
        logger.info(
            f"[emergency] No standby available for {cluster.name}, "
            f"using normal emergency flow"
        )
        result = _execute_normal_emergency(db, redis, cluster, interrupted, action)
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


def _find_ready_standby(db, cluster_id: str):
    """Find a running standby node."""
    from backend.models.instance import Instance
    return db.query(Instance).filter(
        Instance.cluster_id == cluster_id,
        Instance.standby == True,
        Instance.state == "running",
    ).first()


def _execute_standby_failover(db, redis, cluster, interrupted, standby, action):
    """
    Execute the standby-first failover path.

    1. UNCORDON standby
    2. CORDON interrupted node
    3. DRAIN interrupted node
    4. Terminate interrupted node
    5. Mark standby as no longer standby
    6. Launch a new standby asynchronously
    """
    from backend.models.agent_action import AgentAction, AgentActionType, AgentActionStatus
    from backend.models.base import generate_uuid

    try:
        # 1. Uncordon standby
        uncordon_action = AgentAction(
            id=generate_uuid(),
            cluster_id=cluster.id,
            action_type=AgentActionType.UNCORDON_NODE,
            payload={"node_name": standby.node_name, "reason": "standby_activated"},
            status=AgentActionStatus.PENDING,
        )
        db.add(uncordon_action)
        db.commit()
        logger.info(f"[emergency] Created UNCORDON for standby {standby.node_name}")

        # 2. Cordon interrupted node
        cordon_action = AgentAction(
            id=generate_uuid(),
            cluster_id=cluster.id,
            action_type=AgentActionType.CORDON_NODE,
            payload={"node_name": interrupted.node_name},
            status=AgentActionStatus.PENDING,
        )
        db.add(cordon_action)
        db.commit()

        # 3. Drain interrupted node — emergency mode:
        #    force=True  → bypasses PodDisruptionBudgets immediately. AWS does not
        #                   honour PDBs at the 2-minute hard deadline; waiting
        #                   politely guarantees ungraceful pod death.
        #    grace_period=90 → gives pods 90 seconds to shut down cleanly.
        #                       Any pod still running at T-90s is force-deleted by
        #                       the actuator's PDB bypass path so K8s can reschedule
        #                       it before the 120-second AWS kill arrives.
        drain_action = AgentAction(
            id=generate_uuid(),
            cluster_id=cluster.id,
            action_type=AgentActionType.DRAIN_NODE,
            payload={
                "node_name": interrupted.node_name,
                "grace_period": 90,
                "ignore_daemonsets": True,
                "force": True,        # bypass PDBs — required for 2-min window
                "emergency": True,    # signal actuator to use 90s escalation timer
            },
            status=AgentActionStatus.PENDING,
        )
        db.add(drain_action)
        db.commit()
        logger.info(f"[emergency] Created CORDON+DRAIN for {interrupted.node_name}")

        # 4. Mark interrupted as terminating
        interrupted.state = "terminating"
        db.commit()

        # 5. Mark standby as no longer standby (now active)
        standby.standby = False
        db.commit()
        logger.info(f"[emergency] Standby {standby.node_name} activated as normal node")

        # 6. Update action record
        action.target_instance_type = standby.instance_type
        action.target_az = standby.az
        action.status = "completed"
        action.completed_at = datetime.utcnow()
        db.commit()

        # 7. Launch a new standby asynchronously
        from backend.workers.tasks.standby import launch_standby_node
        launch_standby_node.delay(cluster.id)
        logger.info(f"[emergency] Triggered new standby launch for {cluster.name}")

        # Update cluster_pools in Redis
        try:
            pool_key = f"{standby.instance_type}:{standby.az}"
            redis.sadd(f"cluster_pools:{cluster.id}", pool_key)
        except Exception:
            pass

        return {
            "status": "ok",
            "method": "standby_failover",
            "standby_node": standby.node_name,
            "interrupted_node": interrupted.node_name,
        }

    except Exception as e:
        logger.error(f"[emergency] Standby failover failed: {e}")
        db.rollback()
        return {"status": "error", "method": "standby_failover", "error": str(e)}


def _execute_normal_emergency(db, redis, cluster, interrupted, action):
    """
    Execute normal emergency flow (no standby available).

    Creates a RebalancingAction with 'emergency' type that the
    auto_rebalancer will pick up and handle (bypassing the double gate).
    """
    try:
        # The action record was already created with status='in_progress'
        # and action_type='emergency'. The auto_rebalancer will detect this
        # and handle it with priority (bypass double gate checks).

        action.status = "pending"
        action.action_metadata = {
            "emergency": True,
            "bypass_double_gate": True,
            "triggered_at": datetime.utcnow().isoformat(),
        }
        db.commit()

        logger.info(
            f"[emergency] Created emergency rebalancing action {action.id} "
            f"for {interrupted.node_name} in {cluster.name} (normal flow)"
        )
        return {
            "status": "ok",
            "method": "normal_emergency",
            "action_id": action.id,
            "interrupted_node": interrupted.node_name,
        }

    except Exception as e:
        logger.error(f"[emergency] Normal emergency flow failed: {e}")
        db.rollback()
        return {"status": "error", "method": "normal_emergency", "error": str(e)}


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
