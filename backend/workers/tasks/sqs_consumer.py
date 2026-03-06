"""
SQS Interrupt Consumer — Proactive Spot Interruption Handling

Polls the SQS interruption queue for each active Karpenter cluster every 30 seconds.
When an EC2 spot interruption notice or instance health event arrives, immediately
triggers an emergency rebalancing action (bypasses the 10-minute graceful cooldown).

Flow:
  SQS message received → parse instance_id + AZ → find cluster + instance in DB
  → check: is it a spot node we're managing? → create emergency RebalancingAction
  → auto_rebalancer picks it up in its next 15-second cycle

Queue name convention: KarpenterInterruptionQueue-{cluster_name}
(same queue Karpenter uses for its native interruption handler)
"""

from datetime import datetime
from typing import Optional, Dict, Any
import json
import logging

from backend.workers.app import app
from backend.models.base import get_db
from backend.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@app.task(bind=True, name="workers.sqs_consumer.poll_interruption_queues")
def poll_interruption_queues(self) -> Dict[str, Any]:
    """
    Poll SQS interruption queues for all active clusters.
    Runs every 30 seconds.
    """
    db = next(get_db())
    redis = get_redis_client()
    processed = 0
    emergency_actions = 0

    try:
        from backend.models.cluster import Cluster
        from backend.models.instance import Instance, InstanceLifecycle
        from backend.models.rebalancing_action import RebalancingAction
        from backend.models.system_config import SystemConfig

        # Load platform credentials
        _pk = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        _ps = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        _plat_key    = (_pk.value if _pk and _pk.value else None)
        _plat_secret = (_ps.value if _ps and _ps.value else None)

        if not _plat_key or not _plat_secret:
            logger.debug("[sqs_consumer] No platform credentials — skipping SQS poll")
            return {"status": "skipped", "reason": "no_credentials"}

        import boto3
        from botocore.exceptions import ClientError

        # Get clusters with Karpenter (they have SQS queues)
        clusters = db.query(Cluster).filter(
            Cluster.karpenter_mode.isnot(None),
            Cluster.status == 'ACTIVE',
        ).all()

        for cluster in clusters:
            region = cluster.region or "ap-south-1"
            queue_name = f"KarpenterInterruptionQueue-{cluster.name}"

            # Assume cluster role for SQS access
            _creds = {}
            _role_arn = cluster.aws_role_arn
            _ext_id   = cluster.aws_external_id
            if not _role_arn and cluster.account_id:
                try:
                    from backend.models.account import Account
                    _acct = db.query(Account).filter(Account.id == cluster.account_id).first()
                    if _acct:
                        _role_arn = _acct.role_arn
                        _ext_id   = _acct.external_id
                except Exception:
                    pass

            try:
                if _role_arn:
                    _sts = boto3.client("sts",
                                       aws_access_key_id=_plat_key,
                                       aws_secret_access_key=_plat_secret,
                                       region_name=region)
                    _kw = {"RoleArn": _role_arn, "RoleSessionName": "spot-sqs-consumer"}
                    if _ext_id:
                        _kw["ExternalId"] = _ext_id
                    _assumed = _sts.assume_role(**_kw)
                    _c = _assumed["Credentials"]
                    _creds = {
                        "aws_access_key_id":     _c["AccessKeyId"],
                        "aws_secret_access_key": _c["SecretAccessKey"],
                        "aws_session_token":     _c["SessionToken"],
                    }
                else:
                    _creds = {"aws_access_key_id": _plat_key, "aws_secret_access_key": _plat_secret}

                sqs = boto3.client("sqs", region_name=region, **_creds)

                # Get queue URL
                try:
                    _url_resp = sqs.get_queue_url(QueueName=queue_name)
                    queue_url = _url_resp["QueueUrl"]
                except ClientError as e:
                    if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
                        continue  # No queue for this cluster yet
                    raise

                # Receive up to 10 messages (SQS max per request)
                _msgs = sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=1,  # short poll (not long poll — we run frequently)
                    AttributeNames=["All"],
                )

                for msg in _msgs.get("Messages", []):
                    processed += 1
                    receipt = msg["ReceiptHandle"]

                    try:
                        body = json.loads(msg.get("Body", "{}"))
                        _handled = _handle_interruption_message(
                            db, redis, cluster, body, region
                        )
                        if _handled:
                            emergency_actions += 1
                    except Exception as _parse_err:
                        logger.warning(
                            f"[sqs_consumer] Failed to parse message for {cluster.name}: {_parse_err}"
                        )

                    # Always delete — even if we couldn't parse, Karpenter also reads this queue
                    try:
                        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt)
                    except Exception:
                        pass

            except Exception as _cluster_err:
                logger.warning(
                    f"[sqs_consumer] Error polling queue for {cluster.name}: {_cluster_err}"
                )
                continue

        if processed > 0:
            logger.info(
                f"[sqs_consumer] Processed {processed} SQS messages, "
                f"triggered {emergency_actions} emergency rebalancing actions"
            )

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "messages_processed": processed,
            "emergency_actions": emergency_actions,
        }

    except Exception as e:
        logger.error(f"[sqs_consumer] Task failed: {e}")
        return {"status": "error", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
    finally:
        db.close()


def _handle_interruption_message(
    db, redis, cluster, body: dict, region: str
) -> bool:
    """
    Parse an SQS message and trigger emergency rebalancing if needed.

    Supported event types:
    - EC2 Spot Instance Interruption Warning (detail-type: "EC2 Spot Instance Interruption Warning")
    - EC2 Instance State-change Notification (state: stopping/stopped)
    - AWS Health Event (spotInterruption / scheduledChange)

    Returns True if an emergency rebalancing action was created.
    """
    from backend.models.instance import Instance, InstanceLifecycle
    from backend.models.rebalancing_action import RebalancingAction

    detail_type = body.get("detail-type", "")
    detail      = body.get("detail", {})

    # Extract instance ID from common event formats
    instance_id: Optional[str] = None

    if detail_type == "EC2 Spot Instance Interruption Warning":
        instance_id = detail.get("instance-id")
        action_type = "spot_interruption"

    elif detail_type == "EC2 Instance State-change Notification":
        instance_id = detail.get("instance-id")
        state       = detail.get("state", "")
        if state not in ("stopping", "stopped", "shutting-down", "terminated"):
            return False  # Not an interruption — ignore
        action_type = "state_change"

    elif detail_type == "AWS Health Event":
        # Extract from resources list
        resources = body.get("resources", [])
        instance_id = resources[0] if resources else None
        action_type = "health_event"

    else:
        logger.debug(f"[sqs_consumer] Unrecognised event type '{detail_type}' — skipping")
        return False

    if not instance_id:
        return False

    # Check if we're managing this instance
    instance = db.query(Instance).filter(
        Instance.cluster_id == cluster.id,
        Instance.instance_id == instance_id[:20],  # DB column is VARCHAR(20)
        Instance.lifecycle == InstanceLifecycle.SPOT,
        Instance.state == 'running',
    ).first()

    if not instance:
        logger.debug(
            f"[sqs_consumer] Instance {instance_id} not in managed spot pool for {cluster.name} — skipping"
        )
        return False

    # De-duplicate: don't create two emergency actions for the same instance
    _dedup_key = f"spot:emergency:dedup:{instance_id}"
    if redis.exists(_dedup_key):
        logger.info(
            f"[sqs_consumer] Emergency action already triggered for {instance_id} — skipping duplicate"
        )
        return False

    # Determine target pool via ML ranking
    source_az = instance.az or f"{region}a"
    source_pool  = f"{instance.instance_type}:{source_az}"
    target_pool  = source_pool  # fallback: same pool

    try:
        from backend.services.pool_ranking_service import PoolRankingService
        from backend.services.substitute_manager import _INSTANCE_VCPU_MEM
        _specs = _INSTANCE_VCPU_MEM.get(instance.instance_type, (2, 8))
        _ranked = PoolRankingService(db, redis).rank_pools_for_size(
            vcpu=_specs[0], memory_gb=float(_specs[1]),
            region=region, limit=3
        )
        if _ranked:
            _p = _ranked[0].pool
            target_pool = f"{_p.instance_type}:{_p.az}"
    except Exception:
        pass

    # Create emergency RebalancingAction
    action = RebalancingAction(
        cluster_id=cluster.id,
        trigger='emergency',
        source_pool=source_pool,
        target_pool=target_pool,
        status='in_progress',
        started_at=datetime.utcnow(),
        action_metadata={
            'reason': 'sqs_interruption_notice',
            'initiated_by': 'sqs_consumer',
            'instance_id': instance_id,
            'detail_type': detail_type,
            'action_type': action_type,
            'target_instance_type': target_pool.split(':')[0],
        }
    )
    db.add(action)
    db.commit()

    # Set de-dup key (2-hour TTL — spot interruption window is 2 minutes, but we give more buffer)
    redis.setex(_dedup_key, 7200, "1")

    logger.info(
        f"[sqs_consumer] ⚡ Emergency rebalancing triggered: {instance_id} "
        f"({detail_type}) → {target_pool} for cluster {cluster.name} "
        f"(action {action.id})"
    )
    return True
