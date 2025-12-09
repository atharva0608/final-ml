"""
Decision Pipeline - The core orchestrator

This is the "assembly line manager" that runs the DecisionContext
through all configured stages in order.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from .context import DecisionContext, DecisionType
from .interfaces import IPipelineStage


class PipelineConfig:
    """Configuration for which stages to enable"""

    def __init__(self):
        # Layer 1: Input (required)
        self.input_adapter: Optional[str] = "single_instance"  # or "k8s"

        # Layer 2: Static Intelligence
        self.enable_hardware_filter: bool = True
        self.enable_spot_advisor: bool = True
        self.enable_rightsizing: bool = False  # Expand to larger instances

        # Layer 3: Risk Engine (required)
        self.risk_model: str = "family_stress"  # or "random", "always_safe"

        # Layer 4: Optimization
        self.enable_safety_gate: bool = True
        self.enable_bin_packing: bool = False  # Only for K8s mode
        self.enable_tco_sorting: bool = True

        # Layer 5: Reactive Override (required)
        self.enable_signal_override: bool = True

        # Layer 6: Output (required)
        self.actuator: str = "log"  # or "k8s", "prometheus"

        # Thresholds
        self.max_crash_probability: float = 0.85  # Safety gate threshold
        self.max_historic_interrupt_rate: float = 0.20  # Spot advisor threshold

    def to_dict(self) -> Dict[str, Any]:
        """Export config as dict for logging"""
        return {
            'input_adapter': self.input_adapter,
            'enable_hardware_filter': self.enable_hardware_filter,
            'enable_spot_advisor': self.enable_spot_advisor,
            'enable_rightsizing': self.enable_rightsizing,
            'risk_model': self.risk_model,
            'enable_safety_gate': self.enable_safety_gate,
            'enable_bin_packing': self.enable_bin_packing,
            'enable_tco_sorting': self.enable_tco_sorting,
            'enable_signal_override': self.enable_signal_override,
            'actuator': self.actuator,
            'max_crash_probability': self.max_crash_probability,
            'max_historic_interrupt_rate': self.max_historic_interrupt_rate,
        }


class DecisionPipeline:
    """
    The Decision Pipeline orchestrator

    Manages the execution of all stages in the correct order.
    Each stage receives the DecisionContext, modifies it, and passes it along.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the pipeline

        Args:
            config: Pipeline configuration (uses defaults if None)
        """
        self.config = config or PipelineConfig()
        self.stages: List[IPipelineStage] = []

    def add_stage(self, stage: IPipelineStage):
        """Add a stage to the pipeline"""
        self.stages.append(stage)

    def execute(self, context: DecisionContext) -> DecisionContext:
        """
        Execute the pipeline

        Args:
            context: Input decision context

        Returns:
            Decision context after all stages have processed it
        """
        context.pipeline_start_time = datetime.now()

        print("\n" + "="*80)
        print("🚀 DECISION PIPELINE EXECUTION")
        print("="*80)
        print(f"Input: {context.input_request}")
        print(f"Config: {self.config.input_adapter} mode, {len(self.stages)} stages")
        print("="*80 + "\n")

        # Execute all stages in order
        for i, stage in enumerate(self.stages, 1):
            print(f"[Stage {i}/{len(self.stages)}] {stage.name}")
            print("-" * 80)

            try:
                stage.on_enter(context)
                context = stage.process(context)
                stage.on_exit(context)

                # Log stage summary
                valid_candidates = len(context.get_valid_candidates())
                total_candidates = len(context.candidates)
                print(f"  ✓ Completed: {valid_candidates}/{total_candidates} candidates valid")
                print()

            except Exception as e:
                print(f"  ❌ Stage failed: {e}")
                context.log_stage(stage.name, f"ERROR: {e}")
                # Continue to next stage (fail gracefully)

        context.pipeline_end_time = datetime.now()
        execution_time = (context.pipeline_end_time - context.pipeline_start_time).total_seconds()

        print("="*80)
        print("🏁 PIPELINE COMPLETE")
        print("="*80)
        print(f"Final Decision: {context.final_decision.value}")
        if context.selected_candidate:
            print(f"Selected: {context.selected_candidate}")
        print(f"Reason: {context.decision_reason}")
        print(f"Execution Time: {execution_time:.2f}s")
        print(f"AWS Signal: {context.aws_signal.value}")
        print("="*80 + "\n")

        return context

    def get_execution_summary(self, context: DecisionContext) -> Dict[str, Any]:
        """Get a summary of the pipeline execution"""
        return {
            'final_decision': context.final_decision.value,
            'selected_candidate': {
                'instance_type': context.selected_candidate.instance_type,
                'availability_zone': context.selected_candidate.availability_zone,
                'spot_price': context.selected_candidate.spot_price,
                'crash_probability': context.selected_candidate.crash_probability,
                'yield_score': context.selected_candidate.yield_score,
            } if context.selected_candidate else None,
            'decision_reason': context.decision_reason,
            'aws_signal': context.aws_signal.value,
            'candidates_evaluated': len(context.candidates),
            'candidates_valid': len(context.get_valid_candidates()),
            'execution_time_ms': (context.pipeline_end_time - context.pipeline_start_time).total_seconds() * 1000
                                 if context.pipeline_end_time else None,
            'stages_executed': len(self.stages),
            'execution_trace': context.execution_trace,
        }
