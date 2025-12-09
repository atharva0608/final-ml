"""
Layer 3: Risk Engine (ML Models)

This stage uses ML models to predict crash probability for each candidate.
"""

from typing import Dict
from ..context import DecisionContext, Candidate
from ..interfaces import IPipelineStage, IRiskModel


class RiskModelStage(IPipelineStage):
    """
    Apply ML model to predict crash probability

    This is the "brain" of the system. It enriches each candidate
    with a crash_probability score (0.0 to 1.0).
    """

    def __init__(self, risk_model: IRiskModel):
        self.risk_model = risk_model

    @property
    def name(self) -> str:
        return f"RiskModel({self.risk_model.name})"

    @property
    def skippable(self) -> bool:
        return False  # Risk model is required

    def process(self, context: DecisionContext) -> DecisionContext:
        """Apply ML model to predict crash probabilities"""
        print(f"  Applying ML model: {self.risk_model.name}")

        # Check if model is loaded
        if not self.risk_model.is_loaded():
            print(f"    ⚠️  WARNING: Model not loaded! Using fallback scores.")
            # Use fallback: moderate risk for all
            for candidate in context.candidates:
                if candidate.is_valid:
                    candidate.crash_probability = 0.50
            return context

        # Get valid candidates
        valid_candidates = context.get_valid_candidates()

        if not valid_candidates:
            print(f"    ⚠️  No valid candidates to score")
            return context

        print(f"    Scoring {len(valid_candidates)} candidates...")

        # Predict crash probabilities
        predictions = self.risk_model.predict(valid_candidates)

        # Enrich candidates with predictions
        for candidate in valid_candidates:
            key = f"{candidate.instance_type}@{candidate.availability_zone}"
            candidate.crash_probability = predictions.get(key, 0.50)  # Default to 0.50 if missing

        # Summary statistics
        risks = [c.crash_probability for c in valid_candidates if c.crash_probability is not None]
        if risks:
            avg_risk = sum(risks) / len(risks)
            min_risk = min(risks)
            max_risk = max(risks)
            print(f"    Risk Distribution: min={min_risk:.2f}, avg={avg_risk:.2f}, max={max_risk:.2f}")

        print(f"    ✓ Scored {len(valid_candidates)} candidates")

        return context
