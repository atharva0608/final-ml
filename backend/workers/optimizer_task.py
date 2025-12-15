"""
Optimizer Task - Pipeline Router for Lab Mode

This module contains the main optimization cycle that decides whether
to run the full CLUSTER_FULL pipeline or the simplified SINGLE_LINEAR
pipeline based on instance configuration.

This is the "fork in the road" that enables Lab Mode experimentation.
"""

from typing import Dict, Any, Optional
from datetime import datetime

from decision_engine_v2.context import DecisionContext, InputRequest, SignalType
from decision_engine_v2.pipeline import DecisionPipeline, PipelineConfig


# In-memory config store (will be replaced with database queries)
INSTANCE_CONFIGS = {}


def get_instance_config(instance_id: str) -> Dict[str, Any]:
    """
    Fetch instance configuration from database

    In production, this would query the instance_config table.
    For now, uses in-memory store with defaults.

    Args:
        instance_id: EC2 instance ID

    Returns:
        Configuration dict with pipeline_mode and feature flags
    """
    # TODO: Replace with database query
    # config = db.query(InstanceConfig).filter_by(instance_id=instance_id).first()

    if instance_id in INSTANCE_CONFIGS:
        return INSTANCE_CONFIGS[instance_id]

    # Default configuration (Production mode)
    return {
        "instance_id": instance_id,
        "pipeline_mode": "CLUSTER_FULL",
        "assigned_model_id": None,
        "enable_bin_packing": True,
        "enable_right_sizing": True,
        "enable_family_stress": True,
        "aws_region": "ap-south-1"
    }


def run_cluster_pipeline(instance_id: str, config: Dict[str, Any]) -> DecisionContext:
    """
    Run the full production pipeline (CLUSTER_FULL mode)

    This is the standard 6-layer pipeline with all optimizations enabled:
    1. Input Adapter
    2. Static Intelligence (Hardware Filter, Spot Advisor, Right Sizing)
    3. Risk Engine (Family Stress Prediction)
    4. Optimization (Safety Gate, Bin Packing, TCO Sorting)
    5. Reactive Override (AWS Signal Handling)
    6. Actuator (Kubernetes Drain)

    Args:
        instance_id: EC2 instance ID
        config: Instance configuration dict

    Returns:
        DecisionContext with final decision
    """
    print(f"🏭 Running CLUSTER_FULL Pipeline for {instance_id}")
    print(f"   Region: {config.get('aws_region', 'ap-south-1')}")
    print(f"   Bin Packing: {config.get('enable_bin_packing', True)}")
    print(f"   Right Sizing: {config.get('enable_right_sizing', True)}")
    print()

    # TODO: Import and configure stages
    # from decision_engine_v2.stages.input_adapters import SingleInstanceAdapter
    # from decision_engine_v2.stages.static_intelligence import HardwareFilterStage, SpotAdvisorStage
    # from decision_engine_v2.stages.risk_engine import FamilyStressStage
    # from decision_engine_v2.stages.optimization import SafetyGateStage, TCOSortingStage
    # from decision_engine_v2.stages.reactive_override import SignalOverrideStage
    # from decision_engine_v2.stages.actuators import K8sActuator

    # Create pipeline config
    pipeline_config = PipelineConfig()
    pipeline_config.enable_bin_packing = config.get('enable_bin_packing', True)
    pipeline_config.enable_rightsizing = config.get('enable_right_sizing', True)

    # Create pipeline
    pipeline = DecisionPipeline(config=pipeline_config)

    # Add all stages (placeholder - needs actual stage imports)
    # pipeline.add_stage(SingleInstanceAdapter())
    # pipeline.add_stage(HardwareFilterStage())
    # pipeline.add_stage(SpotAdvisorStage())
    # if config.get('enable_right_sizing'):
    #     pipeline.add_stage(RightSizingStage())
    # pipeline.add_stage(FamilyStressStage())
    # pipeline.add_stage(SafetyGateStage())
    # if config.get('enable_bin_packing'):
    #     pipeline.add_stage(BinPackingStage())
    # pipeline.add_stage(TCOSortingStage())
    # pipeline.add_stage(SignalOverrideStage())
    # pipeline.add_stage(K8sActuator())

    # Create context
    input_request = InputRequest(
        mode="test",
        current_instance_id=instance_id,
        region=config.get('aws_region', 'ap-south-1')
    )
    context = DecisionContext(input_request=input_request)

    # Execute pipeline
    # context = pipeline.execute(context)

    print(f"✓ Cluster pipeline completed")
    return context


def run_linear_pipeline(instance_id: str, config: Dict[str, Any]) -> DecisionContext:
    """
    Run the simplified Lab Mode pipeline (SINGLE_LINEAR mode)

    This is a streamlined pipeline for R&D experimentation:
    1. Scraper (fetch real-time spot prices)
    2. Safe Filter (historic interrupt rate < 20%)
    3. ML Inference (with assigned model)
    4. Atomic Switch (direct instance replacement)

    BYPASSED in Lab Mode:
    - Bin Packing (no waste cost calculation)
    - Right Sizing (no upsizing/downsizing)
    - Kubernetes Drain (uses atomic switch instead)

    Args:
        instance_id: EC2 instance ID
        config: Instance configuration dict with assigned_model_id

    Returns:
        DecisionContext with final decision
    """
    print(f"🔬 Running SINGLE_LINEAR Pipeline for {instance_id}")
    print(f"   Model ID: {config.get('assigned_model_id', 'default')}")
    print(f"   Region: {config.get('aws_region', 'ap-south-1')}")
    print(f"   Mode: Lab Experiment (Bin Packing & Right Sizing BYPASSED)")
    print()

    # Import lab-specific pipeline
    from pipelines.linear_optimizer import LinearPipeline

    # Create and execute linear pipeline
    linear_pipeline = LinearPipeline(config)
    context = linear_pipeline.execute(instance_id)

    print(f"✓ Linear pipeline completed")
    return context


def run_optimization_cycle(instance_id: str) -> Dict[str, Any]:
    """
    Main optimization task - THE ROUTER

    This is the entry point that determines which pipeline to run
    based on instance configuration.

    Decision Flow:
    1. Fetch instance configuration from database
    2. Check pipeline_mode
    3. Route to appropriate pipeline:
       - SINGLE_LINEAR → Lab Mode (simplified)
       - CLUSTER_FULL → Production Mode (full pipeline)

    Args:
        instance_id: EC2 instance ID to optimize

    Returns:
        Execution summary with decision, timing, and metadata
    """
    print("\n" + "="*80)
    print("🎯 OPTIMIZATION CYCLE STARTED")
    print("="*80)
    print(f"Instance ID: {instance_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*80 + "\n")

    # Step 1: Fetch configuration
    config = get_instance_config(instance_id)
    pipeline_mode = config.get('pipeline_mode', 'CLUSTER_FULL')

    print(f"📋 Configuration Loaded:")
    print(f"   Pipeline Mode: {pipeline_mode}")
    print(f"   Assigned Model: {config.get('assigned_model_id', 'None')}")
    print(f"   Region: {config.get('aws_region', 'ap-south-1')}")
    print()

    # Step 2: THE FORK - Choose which pipeline to run
    start_time = datetime.now()

    if pipeline_mode == 'SINGLE_LINEAR':
        # Lab Mode: Simplified pipeline for experimentation
        context = run_linear_pipeline(instance_id, config)
    else:
        # Production Mode: Full 6-layer pipeline
        context = run_cluster_pipeline(instance_id, config)

    end_time = datetime.now()
    execution_time_ms = (end_time - start_time).total_seconds() * 1000

    # Step 3: Build execution summary
    summary = {
        "instance_id": instance_id,
        "pipeline_mode": pipeline_mode,
        "decision": context.final_decision.value,
        "reason": context.decision_reason,
        "aws_signal": context.aws_signal.value,
        "execution_time_ms": execution_time_ms,
        "timestamp": end_time.isoformat(),
        "selected_candidate": {
            "instance_type": context.selected_candidate.instance_type,
            "availability_zone": context.selected_candidate.availability_zone,
            "spot_price": context.selected_candidate.spot_price,
            "crash_probability": context.selected_candidate.crash_probability,
        } if context.selected_candidate else None
    }

    print("\n" + "="*80)
    print("🏁 OPTIMIZATION CYCLE COMPLETE")
    print("="*80)
    print(f"Pipeline: {pipeline_mode}")
    print(f"Decision: {summary['decision']}")
    print(f"Execution Time: {execution_time_ms:.2f}ms")
    print("="*80 + "\n")

    return summary


# For testing/debugging
if __name__ == '__main__':
    # Test with Lab Mode configuration
    INSTANCE_CONFIGS['i-lab-test-001'] = {
        "instance_id": "i-lab-test-001",
        "pipeline_mode": "SINGLE_LINEAR",
        "assigned_model_id": "model-001",
        "enable_bin_packing": False,
        "enable_right_sizing": False,
        "aws_region": "ap-south-1"
    }

    # Run optimization
    result = run_optimization_cycle('i-lab-test-001')
    print("\nResult:", result)
