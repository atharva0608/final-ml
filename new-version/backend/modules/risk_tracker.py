"""
Global Risk Tracker (SVC-RISK-GLB)
Shared intelligence system across all clients (The "Hive Mind")
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from redis import Redis

from backend.core.config import settings

logger = logging.getLogger(__name__)


class GlobalRiskTracker:
    """
    SVC-RISK-GLB: Global risk intelligence system

    The "Hive Mind" - when one client experiences a Spot interruption,
    all clients are warned about that instance pool for 30 minutes.

    Responsibilities:
    - Flag risky instance pools in Redis
    - Check pool risk status before launching instances
    - Share interruption intelligence across all clients
    - Auto-expire flags after 30 minutes
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.ttl_seconds = int(getattr(settings, 'GLOBAL_RISK_TTL', 1800))  # 30 minutes default

    def flag_risky_pool(
        self,
        instance_type: str,
        availability_zone: str,
        region: str = "us-east-1",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        Flag an instance pool as risky after an interruption event

        Args:
            instance_type: EC2 instance type (e.g., "c5.xlarge")
            availability_zone: AZ where interruption occurred (e.g., "us-east-1a")
            region: AWS region
            metadata: Optional metadata about the interruption

        Returns:
            {
                "status": "flagged",
                "key": "RISK:us-east-1a:c5.xlarge",
                "ttl_seconds": 1800,
                "expires_at": "2026-01-02T10:30:00Z"
            }
        """
        # Create Redis key
        risk_key = f"RISK:{availability_zone}:{instance_type}"

        logger.warning(
            f"[SVC-RISK-GLB] ⚠️ FLAGGING RISKY POOL: {instance_type} in {availability_zone}"
        )

        # Set flag with TTL
        self.redis.setex(
            risk_key,
            self.ttl_seconds,
            "DANGER"
        )

        # Increment interruption counter (persistent)
        counter_key = f"interruption_history:{region}:{availability_zone}:{instance_type}"
        current_count = self.redis.incr(counter_key)

        # Store metadata if provided
        if metadata:
            metadata_key = f"{risk_key}:metadata"
            self.redis.setex(
                metadata_key,
                self.ttl_seconds,
                str(metadata)
            )

        # Calculate expiration time
        expires_at = datetime.utcnow() + timedelta(seconds=self.ttl_seconds)

        logger.info(
            f"[SVC-RISK-GLB] Flagged {risk_key} (interruption #{current_count}), "
            f"expires at {expires_at.isoformat()}Z"
        )

        # Publish event to Redis Pub/Sub for real-time notifications
        self.redis.publish(
            "risk:flagged",
            f"{instance_type}|{availability_zone}|{region}"
        )

        return {
            "status": "flagged",
            "key": risk_key,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": expires_at.isoformat() + "Z",
            "interruption_count": current_count
        }

    def check_pool_risk(
        self,
        instance_type: str,
        availability_zone: str
    ) -> Dict[str, Any]:
        """
        Check if an instance pool is currently flagged as risky

        Args:
            instance_type: EC2 instance type
            availability_zone: AZ to check

        Returns:
            {
                "risky": True,
                "flag": "DANGER",
                "ttl_remaining": 1245,  # seconds
                "recommendation": "AVOID"
            }
            OR
            {
                "risky": False,
                "recommendation": "SAFE"
            }
        """
        risk_key = f"RISK:{availability_zone}:{instance_type}"

        # Check if flag exists
        flag = self.redis.get(risk_key)

        if flag:
            # Get TTL remaining
            ttl_remaining = self.redis.ttl(risk_key)

            logger.info(
                f"[SVC-RISK-GLB] ⚠️ Pool {instance_type} in {availability_zone} is RISKY "
                f"(expires in {ttl_remaining}s)"
            )

            return {
                "risky": True,
                "flag": flag.decode('utf-8') if isinstance(flag, bytes) else flag,
                "ttl_remaining": ttl_remaining,
                "recommendation": "AVOID",
                "expires_in_minutes": round(ttl_remaining / 60, 1)
            }

        return {
            "risky": False,
            "recommendation": "SAFE"
        }

    def get_all_risky_pools(self, region: str = "*") -> List[Dict[str, Any]]:
        """
        Get all currently flagged risky pools

        Args:
            region: AWS region filter (or "*" for all)

        Returns:
            [
                {
                    "instance_type": "c5.xlarge",
                    "availability_zone": "us-east-1a",
                    "ttl_remaining": 1245,
                    "flagged_at": "2026-01-02T10:00:00Z"
                },
                ...
            ]
        """
        # Scan for all RISK:* keys
        pattern = f"RISK:*"
        risky_pools = []

        for key in self.redis.scan_iter(match=pattern):
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key

            # Parse key: RISK:{az}:{instance_type}
            parts = key_str.split(':')
            if len(parts) == 3:
                _, az, instance_type = parts

                ttl = self.redis.ttl(key)
                flagged_at = datetime.utcnow() - timedelta(seconds=(self.ttl_seconds - ttl))

                risky_pools.append({
                    "instance_type": instance_type,
                    "availability_zone": az,
                    "ttl_remaining": ttl,
                    "expires_in_minutes": round(ttl / 60, 1),
                    "flagged_at": flagged_at.isoformat() + "Z"
                })

        logger.info(f"[SVC-RISK-GLB] Found {len(risky_pools)} currently risky pools")
        return risky_pools

    def clear_pool_flag(self, instance_type: str, availability_zone: str) -> bool:
        """
        Manually clear a risky pool flag (admin only)

        Args:
            instance_type: Instance type
            availability_zone: AZ

        Returns:
            True if flag was cleared, False if no flag existed
        """
        risk_key = f"RISK:{availability_zone}:{instance_type}"

        deleted = self.redis.delete(risk_key)

        if deleted:
            logger.info(f"[SVC-RISK-GLB] Cleared risk flag for {risk_key}")
            return True

        return False


def get_risk_tracker(redis_client: Redis) -> GlobalRiskTracker:
    """Get Global Risk Tracker instance"""
    return GlobalRiskTracker(redis_client)
