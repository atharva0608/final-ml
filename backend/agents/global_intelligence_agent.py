"""
Global Intelligence Agent (AtharvaAI Core)
==========================================

Generates region-wide Spot Pool Intelligence for all tenants.
Does NOT make placement decisions.
Does NOT interact with Kubernetes.
Only ranks pools and generates predictive intelligence.
"""

import json
from datetime import datetime
from typing import Dict, Any, List
from .base import BaseAgent, AgentResponse


class GlobalIntelligenceAgent(BaseAgent):
    """
    Global Intelligence Agent (AtharvaAI Core)

    Produces ranked list of Spot pools with:
    - risk probability (next 1 hour)
    - predicted savings (next 1 hour)
    - composite score
    - eligibility flag
    """

    @property
    def system_prompt(self) -> str:
        return """You are **Global Intelligence Agent (AtharvaAI Core)**.

Your role is to generate region-wide Spot Pool Intelligence for all tenants.

You do NOT make placement decisions.
You do NOT interact with Kubernetes.
You only rank pools and generate predictive intelligence.

## HARD RULES

1. Remove pools with interruption_rate > 10%.
2. Remove blacklisted pools.
3. Reject pools with predicted risk > 0.45.
4. Composite score formula:

```
composite_score = (savings * 0.4) - (risk * 0.6)
```

5. Do NOT exceed 50 pools in output.
6. Always sort descending by composite_score.

## OUTPUT FORMAT (STRICT JSON)

```json
{
  "region": "ap-south-1",
  "generated_at": "ISO-8601 timestamp",
  "pools": [
    {
      "instance_type": "string",
      "az": "string",
      "risk_prob": 0.0,
      "predicted_savings": 0.0,
      "composite_score": 0.0,
      "interruption_rate": 0.0
    }
  ]
}
```

Do NOT include explanations.
Do NOT include text outside JSON."""

    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input structure"""
        required_fields = [
            'region',
            'spot_price_data',
            'ondemand_price_data',
            'interruption_rates',
            'blacklist',
            'historical_features'
        ]

        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        return True

    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output structure"""
        required_fields = ['region', 'generated_at', 'pools']

        for field in required_fields:
            if field not in output_data:
                raise ValueError(f"Missing required field in output: {field}")

        # Validate pool structure
        for pool in output_data['pools']:
            required_pool_fields = [
                'instance_type',
                'az',
                'risk_prob',
                'predicted_savings',
                'composite_score',
                'interruption_rate'
            ]
            for field in required_pool_fields:
                if field not in pool:
                    raise ValueError(f"Missing required field in pool: {field}")

        # Ensure max 50 pools
        if len(output_data['pools']) > 50:
            raise ValueError(f"Too many pools in output: {len(output_data['pools'])} (max 50)")

        return True

    def process(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        Main processing logic.

        Applies hard rules and generates ranked pool list.
        """
        try:
            region = input_data['region']
            blacklist = set(input_data['blacklist'])

            # Filter and rank pools
            pools = self._filter_and_rank_pools(
                spot_prices=input_data['spot_price_data'],
                ondemand_prices=input_data['ondemand_price_data'],
                interruption_rates=input_data['interruption_rates'],
                blacklist=blacklist,
                historical_features=input_data['historical_features']
            )

            output = {
                "region": region,
                "generated_at": datetime.utcnow().isoformat(),
                "pools": pools[:50]  # Limit to 50
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

    def _filter_and_rank_pools(
        self,
        spot_prices: List[Dict],
        ondemand_prices: Dict,
        interruption_rates: Dict,
        blacklist: set,
        historical_features: List[Dict]
    ) -> List[Dict]:
        """
        Apply hard rules and rank pools.

        Hard Rules:
        1. Remove pools with interruption_rate > 10%
        2. Remove blacklisted pools
        3. Reject pools with predicted risk > 0.45
        4. Calculate composite_score = (savings * 0.4) - (risk * 0.6)
        5. Sort descending by composite_score
        """
        pools = []

        for spot_data in spot_prices:
            instance_type = spot_data['instance_type']
            az = spot_data['az']
            spot_price = spot_data['price']

            # Get ondemand price
            ondemand_price = ondemand_prices.get(instance_type, spot_price * 2)

            # Calculate savings percentage
            if ondemand_price > 0:
                savings = (ondemand_price - spot_price) / ondemand_price
            else:
                savings = 0.0

            # Get interruption rate
            pool_key = f"{instance_type}:{az}"
            interruption_rate = interruption_rates.get(pool_key, 0.0)

            # HARD RULE 1: Remove if interruption_rate > 10%
            if interruption_rate > 0.10:
                continue

            # HARD RULE 2: Remove blacklisted pools
            if pool_key in blacklist:
                continue

            # Get predicted risk from historical features
            # This would normally come from ML model
            risk_prob = self._predict_risk(instance_type, az, historical_features)

            # HARD RULE 3: Reject if predicted risk > 0.45
            if risk_prob > 0.45:
                continue

            # HARD RULE 4: Calculate composite score
            composite_score = (savings * 0.4) - (risk_prob * 0.6)

            pools.append({
                "instance_type": instance_type,
                "az": az,
                "risk_prob": round(risk_prob, 4),
                "predicted_savings": round(savings, 4),
                "composite_score": round(composite_score, 4),
                "interruption_rate": round(interruption_rate, 4)
            })

        # HARD RULE 5 & 6: Sort by composite_score descending
        pools.sort(key=lambda x: x['composite_score'], reverse=True)

        return pools

    def _predict_risk(
        self,
        instance_type: str,
        az: str,
        historical_features: List[Dict]
    ) -> float:
        """
        Predict risk probability for next 1 hour.

        This is a placeholder - in production, this would call the ML model.
        """
        # Simple heuristic for now
        # In production: use ONNX model or ML service
        return 0.15  # Default low risk
