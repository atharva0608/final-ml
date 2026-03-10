"""
Emergency Event Processor — Deduplicates and routes spot interruption events.
"""
import logging
from backend.core.redis_client import get_redis_client, key_emergency_seen
from backend.core.config import EMERGENCY_DEDUP_TTL_SECS

logger = logging.getLogger(__name__)


class EmergencyEventProcessor:
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()

    def process(self, event_type: str, instance_id: str, node_name: str,
                cluster_id: str, region: str, az: str, instance_type: str) -> dict:
        """
        Process a spot interruption event with deduplication.

        Args:
            event_type: 'termination' or 'rebalance'
            instance_id: EC2 instance ID
            node_name: Kubernetes node name
            cluster_id: Cluster ID
            region: AWS region
            az: Availability zone
            instance_type: EC2 instance type

        Returns:
            Dict with status and details
        """
        dedup_key = key_emergency_seen(instance_id)
        if self.redis.exists(dedup_key):
            logger.info(f"[emergency_processor] Duplicate event for {instance_id} — skipping")
            return {'status': 'duplicate', 'instance_id': instance_id}
        self.redis.setex(dedup_key, EMERGENCY_DEDUP_TTL_SECS, '1')

        try:
            if event_type == 'termination':
                from backend.services.emergency_handler import handle_termination
                return handle_termination(instance_id, cluster_id, region, instance_type, az, node_name)
            elif event_type == 'rebalance':
                from backend.services.rebalance_tracker import track_rebalance_event
                return track_rebalance_event(region, instance_type, az)
            else:
                logger.warning(f'[emergency_processor] Unknown event type: {event_type}')
                return {'status': 'unknown_event_type'}
        except Exception as e:
            logger.error(f'[emergency_processor] Error processing {event_type} for {instance_id}: {e}')
            return {'status': 'error', 'error': str(e)}
