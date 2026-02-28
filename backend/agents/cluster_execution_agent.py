"""
Cluster Execution Agent
=======================

Applies approved decisions to Kubernetes.
Does not make placement decisions.
"""

from datetime import datetime
from typing import Dict, Any
from .base import BaseAgent, AgentResponse


class ClusterExecutionAgent(BaseAgent):
    """
    Cluster Execution Agent

    Applies approved decisions to Kubernetes via SigV4 token.
    Patches NodePool CRD with selected instance configuration.
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Cluster Execution Agent**.

You apply approved decisions to Kubernetes.

You do not make placement decisions.

## WORKFLOW

1. Connect via SigV4 token.
2. Fetch NodePool CRD.
3. Patch:
   * instance-type
   * capacity-type
4. Log action.
5. Return status.

## OUTPUT

```json
{
  "cluster_id": "string",
  "status": "SUCCESS | FAILED",
  "timestamp": "ISO-8601"
}
```

No commentary."""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input"""
        required = ['cluster_id', 'action', 'selected_pool']
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        if input_data['action'] not in ['patch_nodepool', 'fallback', 'revert']:
            raise ValueError(f"Invalid action: {input_data['action']}")

        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output"""
        required = ['cluster_id', 'status', 'timestamp']
        for field in required:
            if field not in output_data:
                raise ValueError(f"Missing field: {field}")

        if output_data['status'] not in ['SUCCESS', 'FAILED']:
            raise ValueError(f"Invalid status: {output_data['status']}")

        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Execute action on cluster"""
        try:
            cluster_id = input_data['cluster_id']
            action = input_data['action']
            selected_pool = input_data['selected_pool']

            # Execute action
            if action == 'patch_nodepool':
                status = self._patch_nodepool(cluster_id, selected_pool)
            elif action == 'fallback':
                status = self._apply_fallback(cluster_id)
            else:
                status = self._revert_changes(cluster_id)

            output = {
                "cluster_id": cluster_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "action_performed": action
            }

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS" if status == "SUCCESS" else "FAILED",
                timestamp=datetime.utcnow().isoformat(),
                data=output
            )

        except Exception as e:
            self.logger.error(f"Execution error: {str(e)}", exc_info=True)
            raise

    def _patch_nodepool(self, cluster_id: str, selected_pool: Dict) -> str:
        """
        Patch NodePool CRD with new instance configuration.

        In production, this would:
        1. Connect to Kubernetes via SigV4
        2. Get NodePool CRD
        3. Patch instance-type and capacity-type
        4. Apply changes
        """
        # Placeholder implementation
        self.logger.info(
            f"Patching NodePool for cluster {cluster_id} "
            f"with {selected_pool['instance_type']} in {selected_pool['az']}"
        )

        # In production: kubectl patch or K8s client API call
        return "SUCCESS"

    def _apply_fallback(self, cluster_id: str) -> str:
        """Apply fallback configuration (On-Demand)"""
        self.logger.info(f"Applying fallback for cluster {cluster_id}")
        return "SUCCESS"

    def _revert_changes(self, cluster_id: str) -> str:
        """Revert to previous configuration"""
        self.logger.info(f"Reverting changes for cluster {cluster_id}")
        return "SUCCESS"
