"""
Decision Engine Agent (Policy Brain)
====================================

Final authority for cluster node placement decisions.
Consumes global intelligence and cluster state.
Enforces policies.
Decides: ALLOW, DENY, or FALLBACK.
Must be deterministic.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from .base import BaseAgent, AgentResponse


class DecisionEngineAgent(BaseAgent):
    """
    Decision Engine Agent

    Enforces policies and makes placement decisions based on:
    - Global ranked pools
    - Node templates
    - Karpenter constraints
    - Cluster state
    - Cooldown records
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Decision Engine Agent**.

You are the final authority for cluster node placement decisions.

You consume global intelligence and cluster state.
You enforce policies.
You decide: ALLOW, DENY, or FALLBACK.

You must be deterministic.

## DECISION WORKFLOW

1. Filter by node_template.
2. Intersect with karpenter_constraints.
3. Apply diversity rules:
   * No duplicate instance_type + AZ
   * max_same_family_ratio <= 0.4
4. Reject pools in cooldown.
5. Reject pools where:
   * risk_prob > 0.45
   * predicted_savings < 2%
6. Evaluate candidates in ranked order.

## MODE LOGIC

### If manual:

Return top 3 candidates:
* best_balanced (highest composite_score)
* max_savings
* most_stable (lowest risk)

### If auto:

Select first valid candidate.
If none valid → FALLBACK.

## OUTPUT FORMAT

### Manual Mode
```json
{
  "mode": "manual",
  "candidates": [
    {
      "label": "best_balanced",
      "instance_type": "string",
      "az": "string",
      "risk_prob": 0.0,
      "predicted_savings": 0.0,
      "decision_confidence": 0.0
    }
  ]
}
```

### Auto Mode
```json
{
  "mode": "auto",
  "action": "ALLOW | FALLBACK | DENY",
  "selected_pool": {
    "instance_type": "string",
    "az": "string"
  },
  "reason": "string"
}
```

No explanations beyond JSON."""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input structure"""
        required_fields = [
            'cluster_id',
            'mode',
            'global_ranked_pools',
            'node_template',
            'karpenter_constraints',
            'cluster_state',
            'cooldown_records',
            'recent_actions'
        ]

        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        if input_data['mode'] not in ['manual', 'auto']:
            raise ValueError(f"Invalid mode: {input_data['mode']}")

        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output structure"""
        if 'mode' not in output_data:
            raise ValueError("Missing 'mode' in output")

        mode = output_data['mode']

        if mode == 'manual':
            if 'candidates' not in output_data:
                raise ValueError("Missing 'candidates' in manual mode output")

        elif mode == 'auto':
            required = ['action', 'selected_pool', 'reason']
            for field in required:
                if field not in output_data:
                    raise ValueError(f"Missing '{field}' in auto mode output")

            if output_data['action'] not in ['ALLOW', 'FALLBACK', 'DENY']:
                raise ValueError(f"Invalid action: {output_data['action']}")

        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """Main processing logic"""
        try:
            mode = input_data['mode']
            cluster_id = input_data['cluster_id']

            # Apply decision workflow
            filtered_pools = self._apply_decision_workflow(
                global_pools=input_data['global_ranked_pools'],
                node_template=input_data['node_template'],
                karpenter_constraints=input_data['karpenter_constraints'],
                cluster_state=input_data['cluster_state'],
                cooldown_records=input_data['cooldown_records'],
                recent_actions=input_data['recent_actions']
            )

            # Generate output based on mode
            if mode == 'manual':
                output = self._generate_manual_output(filtered_pools)
            else:
                output = self._generate_auto_output(filtered_pools)

            output['cluster_id'] = cluster_id
            output['timestamp'] = datetime.utcnow().isoformat()

            return AgentResponse(
                agent_name=self.name,
                status="SUCCESS",
                timestamp=datetime.utcnow().isoformat(),
                data=output
            )

        except Exception as e:
            self.logger.error(f"Error processing: {str(e)}", exc_info=True)
            raise

    def _apply_decision_workflow(
        self,
        global_pools: List[Dict],
        node_template: Dict,
        karpenter_constraints: Dict,
        cluster_state: Dict,
        cooldown_records: Dict,
        recent_actions: List[Dict]
    ) -> List[Dict]:
        """
        Apply decision workflow:
        1. Filter by node_template
        2. Intersect with karpenter_constraints
        3. Apply diversity rules
        4. Reject cooldown pools
        5. Reject low-quality pools
        """
        candidates = []

        # Get existing instance types and families for diversity check
        existing_instances = cluster_state.get('existing_instances', [])
        family_counts = {}
        total_instances = len(existing_instances)

        for inst in existing_instances:
            family = inst.split('.')[0]  # e.g., m5.large → m5
            family_counts[family] = family_counts.get(family, 0) + 1

        for pool in global_pools:
            instance_type = pool['instance_type']
            az = pool['az']
            pool_key = f"{instance_type}:{az}"

            # 1. Filter by node_template
            if not self._matches_template(instance_type, node_template):
                continue

            # 2. Intersect with karpenter_constraints
            if not self._matches_constraints(instance_type, az, karpenter_constraints):
                continue

            # 3. Apply diversity rules
            # Check for duplicate instance_type + AZ
            if pool_key in [f"{i['type']}:{i['az']}" for i in existing_instances]:
                continue

            # Check max_same_family_ratio <= 0.4
            # +1/+1 because we are evaluating whether ADDING this instance would violate
            family = instance_type.split('.')[0]
            projected_ratio = (family_counts.get(family, 0) + 1) / (total_instances + 1)
            if projected_ratio > 0.4:
                continue

            # 4. Reject pools in cooldown
            if pool_key in cooldown_records:
                continue

            # 5. Reject low-quality pools
            if pool['risk_prob'] > 0.45:
                continue
            if pool['predicted_savings'] < 0.02:  # < 2%
                continue

            candidates.append(pool)

        return candidates

    def _matches_template(self, instance_type: str, template: Dict) -> bool:
        """Check if instance matches node template"""
        if not template:
            return True

        allowed_families = template.get('allowed_families', [])
        if allowed_families and instance_type.split('.')[0] not in allowed_families:
            return False

        allowed_sizes = template.get('allowed_sizes', [])
        if allowed_sizes and instance_type.split('.')[-1] not in allowed_sizes:
            return False

        excluded = template.get('excluded_instance_types', [])
        if instance_type in excluded:
            return False

        return True

    def _matches_constraints(self, instance_type: str, az: str, constraints: Dict) -> bool:
        """Check if instance matches Karpenter constraints"""
        if not constraints:
            return True

        allowed_azs = constraints.get('allowed_azs', [])
        if allowed_azs and az not in allowed_azs:
            return False

        return True

    def _generate_manual_output(self, pools: List[Dict]) -> Dict[str, Any]:
        """Generate output for manual mode (top 3 candidates)"""
        candidates = []

        if len(pools) >= 1:
            # Best balanced (highest composite_score)
            best = max(pools, key=lambda p: p['composite_score'])
            candidates.append({
                "label": "best_balanced",
                "instance_type": best['instance_type'],
                "az": best['az'],
                "risk_prob": best['risk_prob'],
                "predicted_savings": best['predicted_savings'],
                "decision_confidence": 0.95
            })

        if len(pools) >= 2:
            # Max savings
            max_savings = max(pools, key=lambda p: p['predicted_savings'])
            if max_savings not in [best]:
                candidates.append({
                    "label": "max_savings",
                    "instance_type": max_savings['instance_type'],
                    "az": max_savings['az'],
                    "risk_prob": max_savings['risk_prob'],
                    "predicted_savings": max_savings['predicted_savings'],
                    "decision_confidence": 0.85
                })

        if len(pools) >= 3:
            # Most stable (lowest risk)
            most_stable = min(pools, key=lambda p: p['risk_prob'])
            if most_stable not in [best, max_savings]:
                candidates.append({
                    "label": "most_stable",
                    "instance_type": most_stable['instance_type'],
                    "az": most_stable['az'],
                    "risk_prob": most_stable['risk_prob'],
                    "predicted_savings": most_stable['predicted_savings'],
                    "decision_confidence": 0.90
                })

        return {
            "mode": "manual",
            "candidates": candidates
        }

    def _generate_auto_output(self, pools: List[Dict]) -> Dict[str, Any]:
        """Generate output for auto mode (select first valid or fallback)"""
        if not pools:
            return {
                "mode": "auto",
                "action": "FALLBACK",
                "selected_pool": None,
                "reason": "No valid candidates after applying all filters"
            }

        # Select first candidate (highest composite_score due to pre-sorting)
        selected = pools[0]

        return {
            "mode": "auto",
            "action": "ALLOW",
            "selected_pool": {
                "instance_type": selected['instance_type'],
                "az": selected['az']
            },
            "reason": f"Selected best candidate with composite_score={selected['composite_score']}"
        }
