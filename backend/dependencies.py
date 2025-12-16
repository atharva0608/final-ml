"""
FastAPI dependency injection

Provides singleton instances of core components.
"""

import json
from pathlib import Path
from functools import lru_cache

from config import settings
from decision_engine_v2.pipeline import DecisionPipeline, PipelineConfig
from decision_engine_v2.providers import (
    MockPriceProvider,
    MockInstanceMetadata,
    FileBasedSpotAdvisor,
    IMDSSignalProvider,
    FamilyStressRiskModel,
)
from decision_engine_v2.stages import (
    SingleInstanceInputAdapter,
    SpotAdvisorFilter,
    RiskModelStage,
    SafetyGateFilter,
    AWSSignalOverride,
    LogActuator,
)


@lru_cache()
def get_static_data():
    """Load static intelligence data (cached)"""
    data_file = Path(settings.static_data_path)

    if not data_file.exists():
        print(f"⚠️  Static data file not found: {data_file}")
        print(f"   Run scraper first: python scraper/fetch_static_data.py")
        return None

    with open(data_file, 'r') as f:
        return json.load(f)


@lru_cache()
def get_decision_pipeline():
    """
    Get configured decision pipeline (cached singleton)

    Auto-configures based on environment (TEST vs PROD).
    """
    engine_config = settings.get_decision_engine_config()

    # Create pipeline config
    config = PipelineConfig()
    config.input_adapter = engine_config['input_adapter']
    config.enable_hardware_filter = engine_config['enable_hardware_filter']
    config.enable_spot_advisor = engine_config['enable_spot_advisor']
    config.enable_rightsizing = engine_config['enable_rightsizing']
    config.risk_model = engine_config['risk_model']
    config.enable_safety_gate = engine_config['enable_safety_gate']
    config.enable_bin_packing = engine_config['enable_bin_packing']
    config.enable_tco_sorting = engine_config['enable_tco_sorting']
    config.enable_signal_override = engine_config['enable_signal_override']
    config.actuator = engine_config['actuator']
    config.max_crash_probability = engine_config['max_crash_probability']
    config.max_historic_interrupt_rate = engine_config['max_historic_interrupt_rate']

    # Initialize providers
    price_provider = MockPriceProvider()
    metadata_provider = MockInstanceMetadata()

    # Spot advisor (uses static data file)
    spot_advisor_data = get_static_data()
    if spot_advisor_data and 'spot_advisor' in spot_advisor_data:
        # Create a temporary file-like object for FileBasedSpotAdvisor
        # or just pass the data directly
        spot_advisor = FileBasedSpotAdvisor(settings.static_data_path)
    else:
        from decision_engine_v2.providers import MockSpotAdvisor
        spot_advisor = MockSpotAdvisor()

    signal_provider = IMDSSignalProvider()
    risk_model = FamilyStressRiskModel(model_path=settings.risk_model_path)

    # Build pipeline
    pipeline = DecisionPipeline(config)

    # Add stages (TEST mode configuration)
    if settings.is_test():
        pipeline.add_stage(SingleInstanceInputAdapter(price_provider, metadata_provider))
        pipeline.add_stage(SpotAdvisorFilter(spot_advisor, threshold=config.max_historic_interrupt_rate))
        pipeline.add_stage(RiskModelStage(risk_model))
        pipeline.add_stage(SafetyGateFilter(threshold=config.max_crash_probability))
        pipeline.add_stage(AWSSignalOverride(signal_provider))
        pipeline.add_stage(LogActuator())

    # TODO: Add PROD mode stages (K8s)

    return pipeline


def get_pipeline():
    """FastAPI dependency for pipeline injection"""
    return get_decision_pipeline()
