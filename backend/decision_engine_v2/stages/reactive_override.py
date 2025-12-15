"""
Layer 5: Reactive Override

This stage checks for AWS interrupt signals and overrides the ML decision if needed.
This is the "safety net" that ensures immediate response to AWS warnings.
"""

from datetime import datetime
from ..context import DecisionContext, DecisionType, SignalType
from ..interfaces import IPipelineStage, ISignalProvider


class AWSSignalOverride(IPipelineStage):
    """
    Check for AWS interrupt signals and override decision if needed

    Priority: AWS Signals > ML Model

    Signals:
    - REBALANCE_RECOMMENDATION: 2-minute warning → DRAIN
    - INSTANCE_TERMINATION: Immediate termination → EVACUATE

    If no signal: Use ML model's recommendation
    """

    def __init__(self, signal_provider: ISignalProvider):
        self.signal_provider = signal_provider

    @property
    def name(self) -> str:
        return "AWSSignalOverride"

    @property
    def skippable(self) -> bool:
        return False  # This is critical for safety

    def process(self, context: DecisionContext) -> DecisionContext:
        """Check AWS signals and override decision if needed"""
        request = context.input_request

        print(f"  Checking AWS interrupt signals...")

        # Check for signals
        signal = self.signal_provider.check_signals(
            instance_id=request.current_instance_id
        )

        context.aws_signal = signal
        context.signal_time = datetime.now()

        if signal == SignalType.TERMINATION:
            # IMMEDIATE TERMINATION NOTICE
            print(f"    🚨 TERMINATION NOTICE DETECTED!")
            print(f"       Instance will be terminated in ~2 minutes")
            context.final_decision = DecisionType.EVACUATE
            context.decision_reason = "AWS Termination Notice received - immediate evacuation required"
            print(f"       Decision: EVACUATE (override all other signals)")

        elif signal == SignalType.REBALANCE:
            # REBALANCE RECOMMENDATION
            print(f"    ⚠️  REBALANCE RECOMMENDATION DETECTED!")
            print(f"       Instance at elevated risk of termination")
            context.final_decision = DecisionType.DRAIN
            context.decision_reason = "AWS Rebalance Recommendation received - draining workloads"
            print(f"       Decision: DRAIN (graceful migration)")

        else:
            # NO SIGNAL - Use ML model recommendation
            print(f"    ✓ No AWS interrupt signals detected")

            # Make decision based on ML model
            if request.mode == "test":
                # Test mode: Check if current instance is safe
                if context.is_current_instance_safe():
                    context.final_decision = DecisionType.STAY
                    context.decision_reason = "Current instance is safe (crash probability < 0.85)"
                    print(f"       Decision: STAY (current instance is safe)")
                else:
                    context.final_decision = DecisionType.SWITCH
                    context.decision_reason = "Current instance is risky (crash probability >= 0.85)"
                    print(f"       Decision: SWITCH (current instance is unsafe)")

            else:
                # K8s mode: Select best candidate
                valid_candidates = context.get_valid_candidates()

                if valid_candidates:
                    # Pick top candidate (already sorted by yield score)
                    context.selected_candidate = valid_candidates[0]
                    context.final_decision = DecisionType.SWITCH
                    context.decision_reason = f"Selected best candidate: {context.selected_candidate.instance_type}@{context.selected_candidate.availability_zone}"
                    print(f"       Decision: SWITCH to {context.selected_candidate.instance_type}")
                else:
                    context.final_decision = DecisionType.STAY
                    context.decision_reason = "No valid candidates found - staying on current instance"
                    print(f"       Decision: STAY (no better alternatives)")

        return context
