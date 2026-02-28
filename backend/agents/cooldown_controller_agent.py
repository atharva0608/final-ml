"""
Cooldown Controller Agent
=========================

Enforces anti-flapping rules.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
from .base import BaseAgent, AgentResponse


class CooldownControllerAgent(BaseAgent):
    """
    Cooldown Controller Agent

    Enforces anti-flapping rules to prevent rapid switching between pools.
    """

    @property
    def system_prompt(self) -> str:
        return """You enforce anti-flapping rules.

## RULES

* Prevent switching within 60 minutes.
* Prevent reuse of same pool within 120 minutes.

## OUTPUT

```json
{
  "cooldown_active": true,
  "reason": "string"
}
```"""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input"""
        required = ['cluster_id', 'recent_actions']
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")
        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output"""
        required = ['cooldown_active', 'reason']
        for field in required:
            if field not in output_data:
                raise ValueError(f"Missing field: {field}")
        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Check cooldown status"""
        try:
            cluster_id = input_data['cluster_id']
            recent_actions = input_data['recent_actions']
            proposed_pool = input_data.get('proposed_pool')

            # Check cooldown rules
            cooldown_result = self._check_cooldown(recent_actions, proposed_pool)

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS",
                timestamp=datetime.utcnow().isoformat(),
                data=cooldown_result
            )

        except Exception as e:
            self.logger.error(f"Cooldown check error: {str(e)}", exc_info=True)
            raise

    def _check_cooldown(
        self,
        recent_actions: List[Dict],
        proposed_pool: Dict = None
    ) -> Dict:
        """
        Check if cooldown rules are violated.

        Rules:
        1. No switching within 60 minutes of last action
        2. No reuse of same pool within 120 minutes
        """
        now = datetime.utcnow()

        if not recent_actions:
            return {
                "cooldown_active": False,
                "reason": "No recent actions"
            }

        # Sort by timestamp descending
        sorted_actions = sorted(
            recent_actions,
            key=lambda a: a.get('timestamp', ''),
            reverse=True
        )

        last_action = sorted_actions[0]
        last_action_time = datetime.fromisoformat(
            last_action['timestamp'].replace('Z', '+00:00')
        )

        # Rule 1: Check 60-minute switching cooldown
        time_since_last = (now - last_action_time).total_seconds() / 60

        if time_since_last < 60:
            return {
                "cooldown_active": True,
                "reason": f"Last action was {int(time_since_last)} minutes ago (min: 60)",
                "remaining_minutes": 60 - int(time_since_last)
            }

        # Rule 2: Check 120-minute pool reuse cooldown
        if proposed_pool:
            proposed_key = f"{proposed_pool['instance_type']}:{proposed_pool['az']}"

            for action in sorted_actions:
                action_time = datetime.fromisoformat(
                    action['timestamp'].replace('Z', '+00:00')
                )
                time_since = (now - action_time).total_seconds() / 60

                if time_since >= 120:
                    break  # No need to check older actions

                action_pool = action.get('pool', '')
                if action_pool == proposed_key:
                    return {
                        "cooldown_active": True,
                        "reason": f"Pool {proposed_key} was used {int(time_since)} minutes ago (min: 120)",
                        "remaining_minutes": 120 - int(time_since)
                    }

        return {
            "cooldown_active": False,
            "reason": "All cooldown checks passed"
        }
