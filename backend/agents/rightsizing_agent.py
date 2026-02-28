"""
Rightsizing Agent
=================

Workload efficiency analysis.
Analyzes pod-level metrics and generates instance resizing recommendations.
Does NOT apply changes.
"""

from datetime import datetime
from typing import Dict, Any, List
from .base import BaseAgent, AgentResponse


class RightsizingAgent(BaseAgent):
    """
    Rightsizing Agent

    Analyzes pod-level metrics and generates instance resizing recommendations
    with ML risk and savings metadata.
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Rightsizing Agent**.

Your task is workload efficiency analysis.

You analyze pod-level metrics and generate instance resizing recommendations.

You do NOT apply changes.

## LOGIC

1. Group metrics by controller.
2. Compute P95 CPU and memory.
3. If P95 < 50% request → oversized.
4. If P95 > 95% request → undersized.
5. Add 20% safety buffer.
6. Map to valid instance types.
7. Intersect with global_ranked_pools.
8. Attach ML risk and savings metadata.

## OUTPUT FORMAT

```json
{
  "cluster_id": "string",
  "recommendations": [
    {
      "controller": "string",
      "current_instance": "string",
      "recommended_instance": "string",
      "confidence": "HIGH | MEDIUM | LOW",
      "monthly_savings": 0.0,
      "risk_prob": 0.0,
      "diversity_ok": true
    }
  ]
}
```

Strict JSON only."""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input structure"""
        required_fields = [
            'cluster_id',
            'analysis_window_hours',
            'pod_metrics',
            'instance_cost_data',
            'global_ranked_pools'
        ]

        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output structure"""
        if 'cluster_id' not in output_data:
            raise ValueError("Missing 'cluster_id' in output")

        if 'recommendations' not in output_data:
            raise ValueError("Missing 'recommendations' in output")

        # Validate recommendation structure
        for rec in output_data['recommendations']:
            required = [
                'controller',
                'current_instance',
                'recommended_instance',
                'confidence',
                'monthly_savings',
                'risk_prob',
                'diversity_ok'
            ]
            for field in required:
                if field not in rec:
                    raise ValueError(f"Missing field '{field}' in recommendation")

            if rec['confidence'] not in ['HIGH', 'MEDIUM', 'LOW']:
                raise ValueError(f"Invalid confidence: {rec['confidence']}")

        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Main processing logic"""
        try:
            cluster_id = input_data['cluster_id']
            pod_metrics = input_data['pod_metrics']
            instance_costs = input_data['instance_cost_data']
            global_pools = input_data['global_ranked_pools']

            # Analyze workloads
            recommendations = self._analyze_workloads(
                pod_metrics=pod_metrics,
                instance_costs=instance_costs,
                global_pools=global_pools
            )

            output = {
                "cluster_id": cluster_id,
                "recommendations": recommendations,
                "analyzed_at": datetime.utcnow().isoformat()
            }

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS",
                timestamp=datetime.utcnow().isoformat(),
                data=output
            )

        except Exception as e:
            self.logger.error(f"Error processing: {str(e)}", exc_info=True)
            raise

    def _analyze_workloads(
        self,
        pod_metrics: List[Dict],
        instance_costs: Dict,
        global_pools: List[Dict]
    ) -> List[Dict]:
        """
        Analyze workload metrics and generate recommendations.

        Logic:
        1. Group by controller
        2. Compute P95 CPU and memory
        3. Determine sizing issues
        4. Add 20% safety buffer
        5. Map to instance types
        6. Enrich with ML data
        """
        # Group metrics by controller
        controllers = {}
        for metric in pod_metrics:
            controller = metric.get('controller', 'unknown')
            if controller not in controllers:
                controllers[controller] = []
            controllers[controller].append(metric)

        recommendations = []

        for controller, metrics in controllers.items():
            # Compute P95 for CPU and memory
            cpu_values = [m['cpu_usage'] for m in metrics if 'cpu_usage' in m]
            mem_values = [m['memory_usage'] for m in metrics if 'memory_usage' in m]

            if not cpu_values or not mem_values:
                continue

            cpu_p95 = self._percentile(cpu_values, 95)
            mem_p95 = self._percentile(mem_values, 95)

            # Get current instance
            current_instance = metrics[0].get('instance_type', 'unknown')

            # Get current requests
            cpu_request = metrics[0].get('cpu_request', cpu_p95)
            mem_request = metrics[0].get('memory_request', mem_p95)

            # Determine sizing issue
            sizing_issue = None
            confidence = "HIGH"

            if cpu_p95 < cpu_request * 0.5 or mem_p95 < mem_request * 0.5:
                sizing_issue = "oversized"
            elif cpu_p95 > cpu_request * 0.95 or mem_p95 > mem_request * 0.95:
                sizing_issue = "undersized"

            if not sizing_issue:
                continue  # No recommendation needed

            # Add 20% safety buffer
            target_cpu = cpu_p95 * 1.2
            target_mem = mem_p95 * 1.2

            # Find recommended instance
            recommended = self._find_best_instance(
                target_cpu=target_cpu,
                target_mem=target_mem,
                current_instance=current_instance,
                sizing_issue=sizing_issue,
                global_pools=global_pools,
                instance_costs=instance_costs
            )

            if recommended:
                recommendations.append(recommended)

        return recommendations

    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile"""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int(len(sorted_values) * (percentile / 100))
        if index >= len(sorted_values):
            index = len(sorted_values) - 1

        return sorted_values[index]

    def _find_best_instance(
        self,
        target_cpu: float,
        target_mem: float,
        current_instance: str,
        sizing_issue: str,
        global_pools: List[Dict],
        instance_costs: Dict
    ) -> Dict[str, Any]:
        """
        Find best instance match based on target resources.

        Maps to valid instance types and enriches with ML data.
        """
        # Simple instance type mapping (production would use actual specs)
        instance_specs = {
            'm5.large': {'cpu': 2, 'memory': 8},
            'm5.xlarge': {'cpu': 4, 'memory': 16},
            'm5.2xlarge': {'cpu': 8, 'memory': 32},
            'm5.4xlarge': {'cpu': 16, 'memory': 64},
            'c5.large': {'cpu': 2, 'memory': 4},
            'c5.xlarge': {'cpu': 4, 'memory': 8},
            'c5.2xlarge': {'cpu': 8, 'memory': 16},
            'r5.large': {'cpu': 2, 'memory': 16},
            'r5.xlarge': {'cpu': 4, 'memory': 32},
        }

        # Find instance that fits requirements
        candidates = []
        for instance_type, specs in instance_specs.items():
            if specs['cpu'] >= target_cpu and specs['memory'] >= target_mem:
                # Check if in global pools
                pool_match = next(
                    (p for p in global_pools if p['instance_type'] == instance_type),
                    None
                )

                if pool_match:
                    current_cost = instance_costs.get(current_instance, 0)
                    new_cost = instance_costs.get(instance_type, 0)
                    monthly_savings = (current_cost - new_cost) * 730  # hours in month

                    candidates.append({
                        'instance_type': instance_type,
                        'monthly_savings': monthly_savings,
                        'risk_prob': pool_match['risk_prob'],
                        'composite_score': pool_match['composite_score']
                    })

        if not candidates:
            return None

        # Select best candidate (highest composite_score)
        best = max(candidates, key=lambda c: c['composite_score'])

        # Determine confidence
        confidence = "HIGH"
        if sizing_issue == "undersized":
            confidence = "MEDIUM"  # Higher risk

        return {
            "controller": "deployment-example",  # Would come from metrics
            "current_instance": current_instance,
            "recommended_instance": best['instance_type'],
            "confidence": confidence,
            "monthly_savings": round(best['monthly_savings'], 2),
            "risk_prob": best['risk_prob'],
            "diversity_ok": True  # Would check actual diversity
        }
