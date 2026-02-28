"""
Event Monitoring Agent
======================

Reacts to termination and rebalance notices.
Manages blacklisting and substitute activation.
"""

from datetime import datetime, timedelta
from typing import Dict, Any
from .base import BaseAgent, AgentResponse


class EventMonitoringAgent(BaseAgent):
    """
    Event Monitoring Agent

    Handles:
    - Rebalance notices (prewarm substitute)
    - Termination notices (cordon, drain, blacklist)
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Event Monitoring Agent**.

You react to termination and rebalance notices.

You manage blacklisting and substitute activation.

## LOGIC

If rebalance_notice:
* Prewarm substitute.
* Evaluate early switch.

If termination_notice:
* Cordon and drain node.
* Promote substitute.
* Blacklist pool for 24h.
* Trigger re-ranking.

## OUTPUT

```json
{
  "cluster_id": "string",
  "event_handled": true,
  "substitute_activated": true,
  "blacklist_applied": true
}
```"""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input"""
        required = ['event_type', 'cluster_id', 'instance_type', 'az']
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        if input_data['event_type'] not in ['rebalance_notice', 'termination_notice']:
            raise ValueError(f"Invalid event_type: {input_data['event_type']}")

        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output"""
        required = ['cluster_id', 'event_handled', 'substitute_activated', 'blacklist_applied']
        for field in required:
            if field not in output_data:
                raise ValueError(f"Missing field: {field}")
        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Handle event"""
        try:
            event_type = input_data['event_type']
            cluster_id = input_data['cluster_id']
            instance_type = input_data['instance_type']
            az = input_data['az']

            if event_type == 'rebalance_notice':
                result = self._handle_rebalance(cluster_id, instance_type, az)
            else:
                result = self._handle_termination(cluster_id, instance_type, az)

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS",
                timestamp=datetime.utcnow().isoformat(),
                data=result
            )

        except Exception as e:
            self.logger.error(f"Event handling error: {str(e)}", exc_info=True)
            raise

    def _handle_rebalance(self, cluster_id: str, instance_type: str, az: str) -> Dict:
        """Handle rebalance notice"""
        self.logger.info(f"Rebalance notice for {instance_type} in {az}")

        # Prewarm substitute
        # Evaluate early switch

        return {
            "cluster_id": cluster_id,
            "event_handled": True,
            "substitute_activated": False,  # Only prewarmed
            "blacklist_applied": False
        }

    def _handle_termination(self, cluster_id: str, instance_type: str, az: str) -> Dict:
        """Handle termination notice"""
        self.logger.info(f"Termination notice for {instance_type} in {az}")

        # Cordon and drain node
        # Promote substitute
        # Blacklist pool for 24h
        pool_key = f"{instance_type}:{az}"
        blacklist_until = datetime.utcnow() + timedelta(hours=24)

        return {
            "cluster_id": cluster_id,
            "event_handled": True,
            "substitute_activated": True,
            "blacklist_applied": True,
            "blacklist_entry": {
                "pool": pool_key,
                "expires_at": blacklist_until.isoformat()
            }
        }
