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

            # Dynamic cap: at least 50, or 30% of viable pools, whichever is larger,
            # capped at 200 to prevent downstream memory bloat in large regions like
            # us-east-1 which can produce 300+ valid combinations.
            _pool_cap = min(200, max(50, int(len(pools) * 0.30)))
            output = {
                "region": region,
                "generated_at": datetime.utcnow().isoformat(),
                "pools": pools[:_pool_cap]
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

            risk_prob = self._predict_risk(
                instance_type, az, historical_features,
                interruption_rate=interruption_rate,
                spot_price=spot_price,
                ondemand_price=ondemand_price,
            )

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
        historical_features: List[Dict],
        interruption_rate: float = 0.0,
        spot_price: float = 0.0,
        ondemand_price: float = 1.0,
    ) -> float:
        """
        Compute a risk probability score [0, 1] for a given pool.

        Three real signals (no LLM, no placeholder):

        1. Interruption rate (Spot Advisor historical, 0–10% range mapped to 0–0.60)
           — primary signal, carries 60% weight
        2. Spot price pressure (spot / on-demand ratio mapped to 0–0.25)
           — high price pressure = AWS reclaiming capacity
        3. Real-time price spike from historical_features (0 or 0.25)
           — if current spot > 1.5× trailing 1-hour average → imminent eviction signal

        Formula: risk = ir_score + price_pressure_score + spike_score, capped at 1.0
        """
        # 1. Interruption rate signal (0-10% maps linearly to 0-0.60)
        ir_score = min(interruption_rate / 0.10 * 0.60, 0.60)

        # 2. Price pressure (high spot/OD ratio = capacity squeeze)
        price_ratio = (spot_price / ondemand_price) if ondemand_price > 0 else 0.5
        price_pressure_score = min(price_ratio * 0.25, 0.25)

        # 3. Price spike from historical features (dual-window: 1h + 24h)
        # Both conditions must hold to reduce false positives from transient 1h noise:
        #   - spot > 1.5× trailing 1h avg  (short-term spike)
        #   - spot > 1.2× trailing 24h avg (sustained pressure — not just momentary)
        spike_score = 0.0
        pool_key = f"{instance_type}:{az}"
        for feat in (historical_features or []):
            if feat.get("pool_key") == pool_key:
                avg_1h = feat.get("avg_price_1h", 0.0)
                avg_24h = feat.get("avg_price_24h", 0.0)
                short_spike = avg_1h > 0 and spot_price > avg_1h * 1.5
                sustained = avg_24h > 0 and spot_price > avg_24h * 1.2
                if short_spike and sustained:
                    spike_score = 0.25  # Dual-window spike → imminent eviction warning
                break

        return min(ir_score + price_pressure_score + spike_score, 1.0)
