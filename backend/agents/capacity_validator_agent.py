"""
Capacity Validator Agent
========================

Batch-validates spot capacity.
"""

from datetime import datetime
from typing import Dict, Any, List
from .base import BaseAgent, AgentResponse


class CapacityValidatorAgent(BaseAgent):
    """
    Capacity Validator Agent

    Batch-validates spot capacity availability.
    Caches results to avoid repeated API calls.
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Capacity Validator Agent**.

You batch-validate spot capacity.

## LOGIC

* Validate capacity once per cycle.
* Cache results.
* Mark pools unavailable if validation fails.

## OUTPUT

```json
{
  "validated_pools": [...],
  "unavailable_pools": [...]
}
```"""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input"""
        required = ['region', 'candidate_pools']
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")
        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output"""
        required = ['validated_pools', 'unavailable_pools']
        for field in required:
            if field not in output_data:
                raise ValueError(f"Missing field: {field}")
        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Validate capacity for candidate pools"""
        try:
            region = input_data['region']
            candidate_pools = input_data['candidate_pools']

            # Validate each pool
            validated = []
            unavailable = []

            for pool in candidate_pools:
                instance_type = pool['instance_type']
                az = pool['az']

                # Check capacity
                has_capacity = self._check_capacity(region, instance_type, az)

                if has_capacity:
                    validated.append(pool)
                else:
                    unavailable.append({
                        "instance_type": instance_type,
                        "az": az,
                        "reason": "Insufficient capacity"
                    })

            output = {
                "region": region,
                "validated_pools": validated,
                "unavailable_pools": unavailable,
                "validated_at": datetime.utcnow().isoformat()
            }

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS",
                timestamp=datetime.utcnow().isoformat(),
                data=output
            )

        except Exception as e:
            self.logger.error(f"Capacity validation error: {str(e)}", exc_info=True)
            raise

    def _check_capacity(self, region: str, instance_type: str, az: str) -> bool:
        """
        Check spot capacity via EC2 RunInstances DryRun (cached 5 min in Redis).

        Uses backend/utils/aws/dry_run.py which:
        - Checks Redis cache key dry_run:{instance_type}:{az} first
        - Falls back to live EC2 RunInstances(DryRun=True) call
        - Returns True on DryRunOperation, False on InsufficientInstanceCapacity
        - Assumes available on any other error (conservative)
        """
        from backend.utils.aws.dry_run import dry_run_pool
        try:
            from backend.core.redis_client import get_redis_client
            redis = get_redis_client()
        except Exception:
            redis = None
        return dry_run_pool(region=region, instance_type=instance_type, az=az, redis=redis)
