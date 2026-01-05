"""
Decision Engine Prototype
-------------------------
This module demonstrates the logic for the "V2" Decision Engine.
It sits ABOVE the LightGBM models and makes the final "Go/No-Go" decision.

Inputs:
1. Model Predictions (Savings %, Risk Score)
2. External Data (Interruption Rate)
3. User Constraints (Max Price, Criticality)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class SpotCandidate:
    instance_type: str
    availability_zone: str
    predicted_savings: float      # From Regressor (0.0 - 1.0)
    risk_score: float             # From Classifier (0.0 - 1.0)
    interruption_rate: float      # From AWS History (0.0 - 1.0)
    on_demand_price: float

@dataclass
class UserConstraints:
    max_price: float
    min_savings: float = 0.20     # Minimum 20% savings
    max_risk_score: float = 0.7   # Never accept risk > 70%
    criticality: str = 'low'      # 'low', 'medium', 'high'

class DecisionEngine:
    def __init__(self, constraints: UserConstraints):
        self.constraints = constraints

    def evaluate(self, candidate: SpotCandidate) -> Dict:
        """
        Evaluate a single candidate and return a decision.
        """
        reasons = []
        
        # --- 1. HARD FILTERS (Safety First) ---
        
        # A. Risk Score Check (Model Confidence)
        if candidate.risk_score > self.constraints.max_risk_score:
            return {'decision': 'REJECT', 'reason': f'High Risk Score ({candidate.risk_score:.2f})'}
            
        # B. Interruption Rate Check (Historical Reality)
        # Stricter rules for high criticality
        max_interrupt = 0.05 if self.constraints.criticality == 'high' else 0.20
        if candidate.interruption_rate > max_interrupt:
            return {'decision': 'REJECT', 'reason': f'High Historical Interruption ({candidate.interruption_rate:.1%})'}
            
        # C. Price Check
        spot_price = candidate.on_demand_price * (1 - candidate.predicted_savings)
        if spot_price > self.constraints.max_price:
            return {'decision': 'REJECT', 'reason': f'Price ${spot_price:.2f} exceeds limit'}
            
        # D. Min Savings Check
        if candidate.predicted_savings < self.constraints.min_savings:
            return {'decision': 'REJECT', 'reason': f'Savings {candidate.predicted_savings:.1%} below threshold'}

        # --- 2. SOFT SCORING (Value Optimization) ---
        
        # Formula: Value = Savings * (1 - Risk)
        # We penalize risky instances even if they pass the hard filter.
        # Example: 
        #   Option A: 60% savings, 10% risk -> Score 0.54
        #   Option B: 90% savings, 60% risk -> Score 0.36
        # Option A wins!
        
        final_score = candidate.predicted_savings * (1 - candidate.risk_score)
        
        return {
            'decision': 'ACCEPT',
            'score': final_score,
            'details': {
                'savings': candidate.predicted_savings,
                'risk': candidate.risk_score,
                'est_price': spot_price
            }
        }

# --- usage example ---
if __name__ == "__main__":
    # Mock Data
    candidates = [
        # Cheap but Risky
        SpotCandidate("c6i.large", "ap-south-1a", 0.90, 0.85, 0.25, 0.10),
        # Expensive but Safe
        SpotCandidate("c6i.large", "ap-south-1b", 0.10, 0.05, 0.01, 0.10),
        # The Sweet Spot
        SpotCandidate("m6i.large", "ap-south-1a", 0.60, 0.10, 0.05, 0.12),
    ]
    
    # User Constraints
    constraints = UserConstraints(max_price=0.08, criticality='medium')
    engine = DecisionEngine(constraints)
    
    print(f"Constraints: Max Price=${constraints.max_price}, Max Risk={constraints.max_risk_score}")
    print("-" * 60)
    print(f"{'Instance':<15} {'Savings':<10} {'Risk':<10} {'Decision':<10} {'Reason/Score'}")
    print("-" * 60)
    
    for c in candidates:
        result = engine.evaluate(c)
        reason = result.get('reason', f"Score: {result.get('score', 0):.2f}")
        print(f"{c.instance_type:<15} {c.predicted_savings:<10.0%} {c.risk_score:<10.2f} {result['decision']:<10} {reason}")
