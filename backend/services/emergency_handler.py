"""
Emergency Handler — Handles spot instance termination events.
"""
import json
import logging
from datetime import datetime
from backend.core.redis_client import (
    get_redis_client,
    key_emergency_in_progress,
    key_cluster_floor,
    key_cluster_cooldown,
    key_blacklist_global,
)
from backend.core.config import EMERGENCY_COOLDOWN_MINUTES
from backend.models.base import get_db

logger = logging.getLogger(__name__)


def handle_termination(instance_id, cluster_id, region, instance_type, az, node_name) -> dict:
    """
    Handle a spot instance termination event.

    Steps:
    1. Acquire emergency lock (prevent concurrent emergency handling)
    2. Trigger ExecutionController for direct replacement
    3. Blacklist terminated pool for 24h
    4. Set cluster floor
    5. Set emergency cooldown
    """
    redis = get_redis_client()
    lock_key = key_emergency_in_progress(cluster_id)
    if not redis.set(lock_key, instance_id, nx=True, ex=300):
        return {'status': 'concurrent_emergency', 'cluster_id': cluster_id}
    try:
        db = next(get_db())
        pool_key = f'{instance_type}:{az}'

        # Direct replacement via ExecutionController
        try:
            from backend.services.execution_controller import ExecutionController
            controller = ExecutionController(cluster_id=cluster_id, region=region)
            controller.execute_replacement(bypass_double_gate=True, db=db)
        except Exception as e:
            logger.error(f'[emergency_handler] ExecutionController failed: {e}')

        # Blacklist terminated pool for 24h
        redis.setex(key_blacklist_global(pool_key), 86400, '1')
        # Set cluster floor
        redis.setex(key_cluster_floor(cluster_id), 86400, json.dumps({'instance_type': instance_type, 'az': az}))
        # Set emergency cooldown
        redis.setex(key_cluster_cooldown(cluster_id), EMERGENCY_COOLDOWN_MINUTES * 60, '1')

        return {'status': 'handled', 'instance_id': instance_id, 'cluster_id': cluster_id}
    finally:
        redis.delete(lock_key)
