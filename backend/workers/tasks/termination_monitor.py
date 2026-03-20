"""Termination Monitoring Worker - System B: Spot Interruption Detection

Detects spot instance termination notices from:
1. EventBridge: AWS-provided termination notices (2-minute warning)
2. DaemonSet: Node-level termination detection via API endpoint
3. Manual: User-initiated flags

Actions on detection:
- Flag pool in global blacklist (Redis, 12-hour TTL)
- Log event to termination_events table
- Trigger emergency rebalancing (90 seconds)
- Broadcast to all clusters using this pool

Celery Task: Runs continuously monitoring EventBridge + periodic blacklist cleanup
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from backend.core.logger import logger
from backend.models.base import get_db
from backend.models.termination_event import TerminationEvent
from backend.models.rebalancing_action import RebalancingAction
from backend.core.redis_client import get_redis_client

# Import EmergencyEventProcessor for centralized event handling
try:
    from backend.services.emergency_event_processor import EmergencyEventProcessor
    _emergency_processor_available = True
except ImportError:
    _emergency_processor_available = False


def cleanup_expired_blacklist(redis_client, db: Session):
    """Remove expired entries from global blacklist."""
    try:
        # Get all blacklisted pools
        risky_pools = redis_client.smembers("risky_pools")

        cleaned_count = 0
        for pool_key in risky_pools:
            pool_key_str = pool_key.decode('utf-8') if isinstance(pool_key, bytes) else pool_key

            # Check TTL
            ttl = redis_client.ttl(f"risky_pool_meta:{pool_key_str}")

            if ttl <= 0:
                # Expired or doesn't exist, remove from set
                redis_client.srem("risky_pools", pool_key_str)
                redis_client.delete(f"risky_pool_meta:{pool_key_str}")
                cleaned_count += 1
                logger.info(f"Removed expired blacklist entry: {pool_key_str}")

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} expired blacklist entries")

    except Exception as e:
        logger.error(f"Failed to cleanup blacklist: {e}")


def detect_termination_notice(
    instance_type: str,
    az: str,
    region: str,
    cluster_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    node_name: Optional[str] = None,
    source: str = "daemonset",
    metadata: Optional[Dict] = None
) -> Dict:
    """
    Detects and processes a spot instance termination notice.

    Called by:
    - EventBridge listener (AWS termination events)
    - DaemonSet agent (2-minute node warnings)
    - Manual API endpoint (user flags)

    Args:
        instance_type: EC2 instance type (e.g., 'm5.xlarge')
        az: Availability zone (e.g., 'aps1-az1')
        region: AWS region (e.g., 'ap-south-1')
        cluster_id: Kubernetes cluster ID (optional)
        instance_id: AWS instance ID (e.g., 'i-12345')
        node_name: Kubernetes node name (optional)
        source: Detection source ('daemonset', 'eventbridge', 'manual')
        metadata: Additional context (termination time, reason, etc.)

    Returns:
        Dict with flagged pool info, rebalancing status
    """
    db = next(get_db())
    redis_client = get_redis_client()

    try:
        pool_key = f"{instance_type}:{az}"

        # ── Issue #20 / Task 2.3: Deduplicate emergency events ───────────
        # SQS, IMDS, and EventBridge can all fire for the same interruption.
        # Use a Redis NX lock per instance_id with a 2-minute TTL so only
        # the first event triggers blacklist + rebalancer.  Subsequent events
        # within the window are silently skipped.
        if instance_id:
            _dedup_key = f"emergency:dedup:{instance_id}"
            if not redis_client.set(_dedup_key, "1", nx=True, ex=120):
                logger.info(
                    f"[termination_monitor] Dedup: skipping duplicate event "
                    f"for {instance_id} (pool={pool_key}, source={source})"
                )
                return {
                    "status": "deduplicated",
                    "instance_id": instance_id,
                    "pool_key": pool_key,
                    "message": "Duplicate event suppressed (2-min dedup window)",
                }

        logger.info(f"Termination notice detected: {pool_key} (source: {source})")

        # 1. Flag pool in global blacklist (Redis, 12-hour TTL)
        flag_pool_in_blacklist(
            redis_client=redis_client,
            instance_type=instance_type,
            az=az,
            ttl_hours=12,
            reason="termination_detected",
            metadata=metadata
        )

        # 2. Log termination event to database
        termination_event = TerminationEvent(
            instance_type=instance_type,
            az=az,
            region=region,
            cluster_id=cluster_id,
            instance_id=instance_id,
            node_name=node_name,
            detected_at=datetime.utcnow(),
            source=source,
            action_taken='flagged',
            event_metadata=metadata or {}
        )
        db.add(termination_event)
        db.commit()

        logger.info(f"Logged termination event: {pool_key} (event_id: {termination_event.id})")

        # 3. Trigger emergency rebalancing if cluster_id provided
        rebalancing_triggered = False
        emergency_result = None

        if cluster_id:
            # Delegate to EmergencyEventProcessor if available, otherwise fallback
            if _emergency_processor_available and instance_id:
                try:
                    processor = EmergencyEventProcessor()
                    emergency_result = processor.process(
                        event_type='termination',
                        instance_id=instance_id,
                        node_name=node_name or '',
                        cluster_id=cluster_id,
                        region=region,
                        az=az,
                        instance_type=instance_type,
                    )
                    rebalancing_triggered = emergency_result.get('status') in ('handled', 'ok')
                except Exception as proc_err:
                    logger.warning(f"[termination_monitor] EmergencyEventProcessor failed: {proc_err}")
                    # Fallback to legacy path
                    rebalancing_triggered = trigger_emergency_rebalancing(
                        db=db,
                        cluster_id=cluster_id,
                        source_pool=pool_key,
                        termination_event_id=termination_event.id,
                    )
            else:
                rebalancing_triggered = trigger_emergency_rebalancing(
                    db=db,
                    cluster_id=cluster_id,
                    source_pool=pool_key,
                    termination_event_id=termination_event.id,
                )

            # Update termination event action
            if rebalancing_triggered:
                termination_event.action_taken = 'rebalanced'
                db.commit()

        return {
            'status': 'success',
            'pool_key': pool_key,
            'flagged_at': datetime.utcnow().isoformat(),
            'ttl_hours': 12,
            'termination_event_id': termination_event.id,
            'rebalancing_triggered': rebalancing_triggered,
            'emergency_result': emergency_result,
            'message': f'Pool {pool_key} flagged globally for 12 hours'
        }

    except Exception as e:
        logger.error(f"Failed to process termination notice: {e}")
        db.rollback()
        return {
            'status': 'error',
            'error': str(e)
        }
    finally:
        db.close()


def flag_pool_in_blacklist(
    redis_client,
    instance_type: str,
    az: str,
    ttl_hours: int = 12,
    reason: str = "termination_detected",
    metadata: Optional[Dict] = None
):
    """
    Flags a pool in the global blacklist (Redis).

    Pool format: 'instance_type:az' (e.g., 'm5.xlarge:aps1-az1')

    Data structure in Redis:
    - SET risky_pools: {'m5.xlarge:aps1-az1', 'c5.large:aps1-az2', ...}
    - KEY risky_pool_meta:m5.xlarge:aps1-az1 → JSON metadata (TTL: 12 hours)
    """
    pool_key = f"{instance_type}:{az}"

    try:
        # Add to risky_pools set
        redis_client.sadd("risky_pools", pool_key)

        # Store metadata with TTL
        meta_data = {
            'instance_type': instance_type,
            'az': az,
            'flagged_at': datetime.utcnow().isoformat(),
            'reason': reason,
            'ttl_seconds': ttl_hours * 3600,
            **(metadata or {})
        }

        meta_key = f"risky_pool_meta:{pool_key}"
        redis_client.setex(
            meta_key,
            ttl_hours * 3600,  # 12 hours in seconds
            json.dumps(meta_data)
        )

        logger.info(f"Flagged pool {pool_key} in global blacklist (TTL: {ttl_hours}h)")

    except Exception as e:
        logger.error(f"Failed to flag pool in blacklist: {e}")
        raise


def trigger_emergency_rebalancing(
    db: Session,
    cluster_id: str,
    source_pool: str,
    termination_event_id: int
) -> bool:
    """
    Triggers emergency rebalancing for a cluster.

    Dispatches to the dedicated emergency_rebalancer task which handles
    standby-first failover. Also creates a DB record for tracking.
    """
    try:
        # Find the interrupted instance
        from backend.models.instance import Instance
        parts = source_pool.split(":")
        instance_type = parts[0] if parts else ""
        az = parts[1] if len(parts) > 1 else ""

        interrupted_instance = db.query(Instance).filter(
            Instance.cluster_id == cluster_id,
            Instance.instance_type == instance_type,
            Instance.state == "running",
        ).first()

        if interrupted_instance:
            # Dispatch to emergency_rebalancer (standby-aware)
            from backend.workers.tasks.emergency_rebalancer import emergency_rebalancer
            emergency_rebalancer.delay(
                cluster_id=cluster_id,
                instance_id=interrupted_instance.id,
                reason="spot_interruption",
            )
            logger.info(
                f"Emergency rebalancer dispatched for {cluster_id} "
                f"(instance {interrupted_instance.id})"
            )
            return True

        # Fallback: Report termination to DE for blacklisting
        try:
            from backend.services.decision_engine_service import DecisionEngineService
            from backend.core.redis_client import get_redis_client
            de = DecisionEngineService(db, get_redis_client())
            de.report_termination(pool_key=source_pool)
        except Exception as de_err:
            logger.warning(f"DE report_termination fallback failed: {de_err}")

        # Create rebalancing action record (legacy path)
        rebalancing_action = RebalancingAction(
            cluster_id=cluster_id,
            trigger='emergency',
            source_pool=source_pool,
            target_pool='pending',
            status='in_progress',
            started_at=datetime.utcnow(),
            action_metadata={
                'termination_event_id': termination_event_id,
                'emergency': True,
                'bypass_double_gate': True,
            }
        )
        db.add(rebalancing_action)
        db.commit()

        logger.info(f"Emergency rebalancing triggered: {cluster_id} ({source_pool})")
        return True

    except Exception as e:
        logger.error(f"Failed to trigger emergency rebalancing: {e}")
        db.rollback()
        return False


# Celery task registration
from backend.workers.app import app

@app.task(name='workers.termination_monitor')
def monitor_terminations():
    """Celery task entry point for termination monitoring."""
    logger.info("Termination monitor task started")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        # Check for new termination events from EventBridge
        # In production, this would poll EventBridge events
        # For now, we'll check for events logged by DaemonSet

        # Cleanup expired blacklist entries (>12 hours)
        cleanup_expired_blacklist(redis_client, db)

        logger.info("Termination monitor task completed successfully")

    except Exception as e:
        logger.error(f"Termination monitor task failed: {e}")
        raise
    finally:
        db.close()
