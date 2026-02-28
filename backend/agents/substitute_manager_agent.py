"""
Substitute Manager Agent
========================

Manages safety fallback nodes.
"""

from datetime import datetime
from typing import Dict, Any, List
from .base import BaseAgent, AgentResponse


class SubstituteManagerAgent(BaseAgent):
    """
    Substitute Manager Agent

    Manages safety fallback nodes based on cluster stress level.
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Substitute Manager Agent**.

You manage safety fallback nodes.

## LOGIC

If stress_level == normal:
* Choose cheapest low-risk Spot from different family + AZ.

If stress_level == elevated:
* Choose smallest On-Demand safe instance.

Never allow same family as failed instance.

## OUTPUT

```json
{
  "substitute_type": "spot | ondemand",
  "instance_type": "string",
  "az": "string"
}
```"""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input"""
        required = ['cluster_state', 'stress_level', 'candidate_pools']
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        if input_data['stress_level'] not in ['normal', 'elevated']:
            raise ValueError(f"Invalid stress_level: {input_data['stress_level']}")

        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output"""
        required = ['substitute_type', 'instance_type', 'az']
        for field in required:
            if field not in output_data:
                raise ValueError(f"Missing field: {field}")

        if output_data['substitute_type'] not in ['spot', 'ondemand']:
            raise ValueError(f"Invalid substitute_type: {output_data['substitute_type']}")

        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Select substitute instance"""
        try:
            stress_level = input_data['stress_level']
            cluster_state = input_data['cluster_state']
            candidate_pools = input_data['candidate_pools']

            failed_instance = cluster_state.get('failed_instance')

            if stress_level == 'normal':
                substitute = self._select_spot_substitute(
                    candidate_pools,
                    failed_instance
                )
            else:
                substitute = self._select_ondemand_substitute(failed_instance)

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS",
                timestamp=datetime.utcnow().isoformat(),
                data=substitute
            )

        except Exception as e:
            self.logger.error(f"Substitute selection error: {str(e)}", exc_info=True)
            raise

    def _select_spot_substitute(
        self,
        candidate_pools: List[Dict],
        failed_instance: str
    ) -> Dict:
        """Select cheapest low-risk Spot from different family + AZ"""
        failed_family = failed_instance.split('.')[0] if failed_instance else None

        # Filter out same family
        valid_pools = [
            p for p in candidate_pools
            if p['instance_type'].split('.')[0] != failed_family
            and p['risk_prob'] < 0.25  # Low risk only
        ]

        if not valid_pools:
            # Fallback to ondemand
            return self._select_ondemand_substitute(failed_instance)

        # Select cheapest
        cheapest = min(valid_pools, key=lambda p: p.get('spot_price', 999))

        return {
            "substitute_type": "spot",
            "instance_type": cheapest['instance_type'],
            "az": cheapest['az'],
            "risk_prob": cheapest['risk_prob']
        }

    def _select_ondemand_substitute(self, failed_instance: str) -> Dict:
        """Select smallest On-Demand safe instance"""
        # Default safe instances (smallest to largest)
        safe_instances = ['t3.medium', 't3.large', 'm5.large', 'm5.xlarge']

        # Exclude failed family
        if failed_instance:
            failed_family = failed_instance.split('.')[0]
            safe_instances = [
                i for i in safe_instances
                if i.split('.')[0] != failed_family
            ]

        return {
            "substitute_type": "ondemand",
            "instance_type": safe_instances[0] if safe_instances else 't3.medium',
            "az": "us-east-1a",  # Default AZ
            "risk_prob": 0.0
        }
