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
        Patch the Karpenter NodePool CRD with the selected spot pool via
        KarpenterService.sync_ml_rankings_to_nodepool().

        KarpenterService handles SigV4 auth, kubeconfig construction, and
        the actual kubectl-patch-equivalent API call.
        """
        from backend.models.base import get_db
        from backend.services.karpenter_service import KarpenterService
        from backend.core.redis_client import get_redis_client

        db = None
        try:
            db = next(get_db())
            try:
                redis = get_redis_client()
            except Exception:
                redis = None

            ksvc = KarpenterService(db, redis)
            top_pools = [{
                "instance_type": selected_pool["instance_type"],
                "az": selected_pool["az"],
                "ml_score": float(selected_pool.get("composite_score", 0.5)),
            }]
            result = ksvc.sync_ml_rankings_to_nodepool(
                cluster_id=cluster_id,
                top_pools=top_pools,
                nodepool_name="default",
            )
            if result.get("status") == "success":
                self.logger.info(
                    f"[execution] NodePool patched for cluster {cluster_id} "
                    f"→ {selected_pool['instance_type']} in {selected_pool['az']}"
                )
                return "SUCCESS"
            else:
                self.logger.error(
                    f"[execution] NodePool patch failed for cluster {cluster_id}: {result}"
                )
                return "FAILED"
        except Exception as e:
            self.logger.error(f"[execution] _patch_nodepool exception: {e}", exc_info=True)
            return "FAILED"
        finally:
            if db:
                db.close()

    def _apply_fallback(self, cluster_id: str) -> str:
        """
        Apply on-demand fallback via KarpenterService.switch_to_ondemand().
        Uses the cluster's current instance types to keep the same sizing.
        """
        from backend.models.base import get_db
        from backend.models.instance import Instance, InstanceLifecycle
        from backend.services.karpenter_service import KarpenterService
        from backend.core.redis_client import get_redis_client

        db = None
        try:
            db = next(get_db())
            try:
                redis = get_redis_client()
            except Exception:
                redis = None
            # Collect current running instance types to keep sizing constraints intact
            od_types = [
                i.instance_type for i in db.query(Instance).filter(
                    Instance.cluster_id == cluster_id,
                    Instance.state == "running",
                ).all() if i.instance_type
            ]
            od_types = list(set(od_types)) or ["t3.medium"]
            ksvc = KarpenterService(db, redis)
            result = ksvc.switch_to_ondemand(
                cluster_id=cluster_id,
                template_instance_types=od_types,
            )
            return "SUCCESS" if result.get("status") == "success" else "FAILED"
        except Exception as e:
            self.logger.error(f"[execution] _apply_fallback exception: {e}", exc_info=True)
            return "FAILED"
        finally:
            if db:
                db.close()

    def _revert_changes(self, cluster_id: str) -> str:
        """
        Revert by switching back to on-demand (same as fallback).
        KarpenterService will re-enable spot on the next ML ranking cycle.
        """
        return self._apply_fallback(cluster_id)
