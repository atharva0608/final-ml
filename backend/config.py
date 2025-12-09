"""
Configuration management for Spot Optimizer Platform

Auto-detects environment (TEST vs PROD) and loads appropriate settings.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""

    # Environment
    environment: str = Field(default="TEST", env="ENV")

    # API Settings
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_reload: bool = Field(default=True, env="API_RELOAD")

    # Decision Engine Settings
    decision_engine_mode: str = Field(default="test", env="DECISION_ENGINE_MODE")
    risk_model_path: str = Field(
        default="../models/production/family_stress_model.pkl",
        env="RISK_MODEL_PATH"
    )
    max_crash_probability: float = Field(default=0.85, env="MAX_CRASH_PROBABILITY")
    max_historic_interrupt_rate: float = Field(default=0.20, env="MAX_HISTORIC_INTERRUPT_RATE")

    # Data Paths
    static_data_path: str = Field(
        default="./data/static_intelligence.json",
        env="STATIC_DATA_PATH"
    )

    # AWS Settings (for PROD mode)
    aws_region: str = Field(default="ap-south-1", env="AWS_REGION")
    k8s_config_path: Optional[str] = Field(default=None, env="K8S_CONFIG_PATH")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_json: bool = Field(default=False, env="LOG_JSON")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment.upper() == "PROD"

    def is_test(self) -> bool:
        """Check if running in test mode"""
        return self.environment.upper() == "TEST"

    def get_decision_engine_config(self) -> dict:
        """Get decision engine configuration based on environment"""
        if self.is_production():
            return {
                'input_adapter': 'k8s',
                'enable_hardware_filter': True,
                'enable_spot_advisor': True,
                'enable_rightsizing': True,
                'risk_model': 'family_stress',
                'enable_safety_gate': True,
                'enable_bin_packing': True,
                'enable_tco_sorting': True,
                'enable_signal_override': False,  # N/A for K8s mode
                'actuator': 'k8s',
                'max_crash_probability': self.max_crash_probability,
                'max_historic_interrupt_rate': self.max_historic_interrupt_rate,
            }
        else:
            return {
                'input_adapter': 'single_instance',
                'enable_hardware_filter': False,
                'enable_spot_advisor': True,
                'enable_rightsizing': False,
                'risk_model': 'family_stress',
                'enable_safety_gate': True,
                'enable_bin_packing': False,
                'enable_tco_sorting': False,
                'enable_signal_override': True,  # Critical for test mode!
                'actuator': 'log',  # Safe for testing
                'max_crash_probability': self.max_crash_probability,
                'max_historic_interrupt_rate': self.max_historic_interrupt_rate,
            }


# Global settings instance
settings = Settings()
