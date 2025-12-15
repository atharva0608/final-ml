"""
Decision Engine V2 - Example Usage

This demonstrates how to use the modular Decision Engine in different modes.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decision_engine_v2.context import DecisionContext, InputRequest, ResourceRequirements, SignalType
from decision_engine_v2.pipeline import DecisionPipeline, PipelineConfig
from decision_engine_v2.stages import (
    SingleInstanceInputAdapter,
    K8sInputAdapter,
    HardwareCompatibilityFilter,
    SpotAdvisorFilter,
    RightsizingExpander,
    RiskModelStage,
    SafetyGateFilter,
    BinPackingCalculator,
    TCOSorter,
    AWSSignalOverride,
    LogActuator,
)
from decision_engine_v2.providers import (
    MockPriceProvider,
    MockInstanceMetadata,
    MockSpotAdvisor,
    MockSignalProvider,
    MockRiskModel,
    AlwaysSafeRiskModel,
    FamilyStressRiskModel,
)


def example_single_instance_test():
    """
    Example 1: Single Instance Test Mode

    Use case: "I am running c5.large in ap-south-1a. Am I safe?"

    This mode tests a single instance and checks:
    1. Current spot price
    2. Crash probability from ML model
    3. AWS signals (rebalance/termination)
    4. Recommendation: STAY, SWITCH, DRAIN, or EVACUATE
    """
    print("\n" + "="*80)
    print("EXAMPLE 1: SINGLE INSTANCE TEST MODE")
    print("="*80)

    # Step 1: Configure the pipeline
    config = PipelineConfig()
    config.input_adapter = "single_instance"
    config.enable_hardware_filter = False  # Not needed for single instance
    config.enable_spot_advisor = True
    config.enable_rightsizing = False  # Not applicable for test mode
    config.risk_model = "family_stress"  # Use real model
    config.enable_safety_gate = True
    config.enable_bin_packing = False  # Not applicable for test mode
    config.enable_tco_sorting = False  # Not needed for single instance
    config.enable_signal_override = True  # Critical!
    config.actuator = "log"  # Safe for testing

    # Step 2: Initialize providers
    price_provider = MockPriceProvider()
    metadata_provider = MockInstanceMetadata()
    spot_advisor = MockSpotAdvisor()

    # Signal provider: You can test different scenarios
    signal_provider = MockSignalProvider(SignalType.NONE)  # No signal
    # signal_provider = MockSignalProvider(SignalType.REBALANCE)  # Test rebalance
    # signal_provider = MockSignalProvider(SignalType.TERMINATION)  # Test termination

    # Risk model: Choose which to use
    # risk_model = MockRiskModel()  # Mock for testing
    # risk_model = AlwaysSafeRiskModel()  # Always returns safe
    risk_model = FamilyStressRiskModel()  # Real model (if available)

    # Step 3: Build the pipeline
    pipeline = DecisionPipeline(config)

    # Add stages in order
    pipeline.add_stage(SingleInstanceInputAdapter(price_provider, metadata_provider))
    pipeline.add_stage(SpotAdvisorFilter(spot_advisor, threshold=0.20))
    pipeline.add_stage(RiskModelStage(risk_model))
    pipeline.add_stage(SafetyGateFilter(threshold=0.85))
    pipeline.add_stage(AWSSignalOverride(signal_provider))
    pipeline.add_stage(LogActuator())

    # Step 4: Create input request
    request = InputRequest(
        mode="test",
        current_instance_type="c5.large",
        current_availability_zone="ap-south-1a",
        current_instance_id="i-1234567890abcdef0",  # Optional
        region="ap-south-1"
    )

    # Step 5: Create context
    context = DecisionContext(input_request=request)

    # Step 6: Execute pipeline
    context = pipeline.execute(context)

    # Step 7: Get summary
    summary = pipeline.get_execution_summary(context)

    print("\n" + "="*80)
    print("EXECUTION SUMMARY")
    print("="*80)
    print(f"Final Decision: {summary['final_decision']}")
    print(f"Reason: {summary['decision_reason']}")
    print(f"AWS Signal: {summary['aws_signal']}")
    print(f"Candidates Evaluated: {summary['candidates_evaluated']}")
    print(f"Execution Time: {summary['execution_time_ms']:.2f}ms")
    print("="*80)


def example_k8s_mode():
    """
    Example 2: Kubernetes Mode

    Use case: "A pod needs 2 vCPU and 4GB RAM. Find best spot pool."

    This mode:
    1. Fetches all matching spot pools in the region
    2. Filters by hardware compatibility and historical data
    3. Scores with ML model
    4. Ranks by yield score (safety + cost)
    5. Returns top 5 recommendations
    """
    print("\n" + "="*80)
    print("EXAMPLE 2: KUBERNETES MODE")
    print("="*80)

    # Configure pipeline
    config = PipelineConfig()
    config.input_adapter = "k8s"
    config.enable_hardware_filter = True  # Filter by vCPU/RAM
    config.enable_spot_advisor = True
    config.enable_rightsizing = True  # Allow oversized instances
    config.risk_model = "family_stress"
    config.enable_safety_gate = True
    config.enable_bin_packing = True  # Calculate waste cost
    config.enable_tco_sorting = True  # Rank by TCO
    config.enable_signal_override = False  # Not applicable (no current instance)
    config.actuator = "log"

    # Initialize providers
    price_provider = MockPriceProvider()
    metadata_provider = MockInstanceMetadata()
    spot_advisor = MockSpotAdvisor()
    signal_provider = MockSignalProvider(SignalType.NONE)
    risk_model = MockRiskModel()  # Use mock for faster demo

    # Build pipeline
    pipeline = DecisionPipeline(config)
    pipeline.add_stage(K8sInputAdapter(price_provider, metadata_provider))
    pipeline.add_stage(HardwareCompatibilityFilter())
    pipeline.add_stage(SpotAdvisorFilter(spot_advisor, threshold=0.20))
    pipeline.add_stage(RiskModelStage(risk_model))
    pipeline.add_stage(SafetyGateFilter(threshold=0.85))
    pipeline.add_stage(BinPackingCalculator())
    pipeline.add_stage(TCOSorter())
    pipeline.add_stage(LogActuator())

    # Create input request
    request = InputRequest(
        mode="k8s",
        resource_requirements=ResourceRequirements(
            vcpu=2.0,
            memory_gb=4.0,
            architecture="x86_64",
            min_vcpu=2.0,
            max_vcpu=8.0  # Allow up to 4x oversizing
        ),
        region="ap-south-1"
    )

    # Execute
    context = DecisionContext(input_request=request)
    context = pipeline.execute(context)

    # Summary
    summary = pipeline.get_execution_summary(context)
    print("\n" + "="*80)
    print("EXECUTION SUMMARY")
    print("="*80)
    print(f"Final Decision: {summary['final_decision']}")
    if summary['selected_candidate']:
        print(f"Selected Instance: {summary['selected_candidate']['instance_type']}")
        print(f"AZ: {summary['selected_candidate']['availability_zone']}")
        print(f"Spot Price: ${summary['selected_candidate']['spot_price']:.4f}")
        print(f"Risk: {summary['selected_candidate']['crash_probability']:.2f}")
        print(f"Yield Score: {summary['selected_candidate']['yield_score']:.1f}")
    print(f"Candidates Evaluated: {summary['candidates_evaluated']}")
    print(f"Candidates Valid: {summary['candidates_valid']}")
    print(f"Execution Time: {summary['execution_time_ms']:.2f}ms")
    print("="*80)


def example_rebalance_test():
    """
    Example 3: Testing Rebalance Signal Handling

    Use case: "Current instance receives rebalance signal. What do we do?"

    This tests the reactive override layer.
    """
    print("\n" + "="*80)
    print("EXAMPLE 3: REBALANCE SIGNAL TEST")
    print("="*80)

    # Configure pipeline (same as example 1, but with REBALANCE signal)
    config = PipelineConfig()
    config.input_adapter = "single_instance"
    config.enable_spot_advisor = True
    config.risk_model = "mock"
    config.enable_safety_gate = True
    config.enable_signal_override = True
    config.actuator = "log"

    # Providers
    price_provider = MockPriceProvider()
    metadata_provider = MockInstanceMetadata()
    spot_advisor = MockSpotAdvisor()
    signal_provider = MockSignalProvider(SignalType.REBALANCE)  # REBALANCE signal!
    risk_model = AlwaysSafeRiskModel()  # Model says safe, but signal overrides

    # Build pipeline
    pipeline = DecisionPipeline(config)
    pipeline.add_stage(SingleInstanceInputAdapter(price_provider, metadata_provider))
    pipeline.add_stage(SpotAdvisorFilter(spot_advisor))
    pipeline.add_stage(RiskModelStage(risk_model))
    pipeline.add_stage(SafetyGateFilter())
    pipeline.add_stage(AWSSignalOverride(signal_provider))
    pipeline.add_stage(LogActuator())

    # Execute
    request = InputRequest(
        mode="test",
        current_instance_type="c5.large",
        current_availability_zone="ap-south-1a",
        current_instance_id="i-1234567890abcdef0"
    )
    context = DecisionContext(input_request=request)
    context = pipeline.execute(context)

    # Summary
    summary = pipeline.get_execution_summary(context)
    print("\n" + "="*80)
    print("EXECUTION SUMMARY")
    print("="*80)
    print(f"Final Decision: {summary['final_decision']} (Expected: DRAIN)")
    print(f"Reason: {summary['decision_reason']}")
    print(f"AWS Signal: {summary['aws_signal']}")
    print("="*80)


if __name__ == "__main__":
    # Run examples
    example_single_instance_test()
    # example_k8s_mode()
    # example_rebalance_test()
