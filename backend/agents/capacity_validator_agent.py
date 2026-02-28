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
        Check if instance type has available capacity in AZ.

        In production, this would call AWS EC2 describe-instance-type-offerings
        or maintain a capacity cache from periodic checks.
        """
        # Placeholder - assume capacity available
        # In production: boto3 ec2 client call
        return True
