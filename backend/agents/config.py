"""
Agent System Configuration
===========================

Configuration settings for the multi-agent system.
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Configuration for agent system"""

    # LLM Settings
    llm_provider: str = "openai"  # 'openai', 'anthropic', 'local'
    llm_model: str = "gpt-4"
    llm_temperature: float = 0.0  # Deterministic by default
    llm_api_key: str = ""

    # Agent Execution Settings
    max_retries: int = 3
    retry_delay_seconds: int = 5
    timeout_seconds: int = 300

    # Global Intelligence Agent Settings
    global_intelligence_max_pools: int = 50
    global_intelligence_cache_ttl: int = 1800  # 30 minutes
    max_interruption_rate: float = 0.10  # 10%
    max_risk_prob: float = 0.45  # 45%
    min_savings_threshold: float = 0.02  # 2%

    # Decision Engine Settings
    max_same_family_ratio: float = 0.4  # 40%
    cooldown_switch_minutes: int = 60  # 1 hour
    cooldown_reuse_minutes: int = 120  # 2 hours

    # Rightsizing Agent Settings
    rightsizing_oversized_threshold: float = 0.5  # P95 < 50% request
    rightsizing_undersized_threshold: float = 0.95  # P95 > 95% request
    rightsizing_safety_buffer: float = 1.2  # 20% buffer
    rightsizing_default_window_hours: int = 168  # 7 days

    # Event Monitoring Settings
    blacklist_duration_hours: int = 24
    substitute_prewarm_enabled: bool = True

    # Capacity Validator Settings
    capacity_check_cache_ttl: int = 600  # 10 minutes
    capacity_batch_size: int = 50

    # Redis Keys
    redis_blacklist_key: str = "risky_pools"
    redis_cooldown_prefix: str = "cooldown"
    redis_global_pools_prefix: str = "global_pools"
    redis_optimization_results_prefix: str = "optimization_results"

    # Feature Flags
    enable_global_intelligence: bool = True
    enable_capacity_validation: bool = True
    enable_cooldown_check: bool = True
    enable_substitute_manager: bool = True
    enable_auto_execution: bool = True  # Disable for testing


# Default configuration instance
default_config = AgentConfig()


def get_agent_config() -> AgentConfig:
    """Get agent configuration (can be overridden by environment variables)"""
    import os

    config = AgentConfig()

    # Override from environment
    if os.getenv('LLM_PROVIDER'):
        config.llm_provider = os.getenv('LLM_PROVIDER')
    if os.getenv('LLM_MODEL'):
        config.llm_model = os.getenv('LLM_MODEL')
    if os.getenv('LLM_API_KEY'):
        config.llm_api_key = os.getenv('LLM_API_KEY')
    if os.getenv('OPENAI_API_KEY'):
        config.llm_api_key = os.getenv('OPENAI_API_KEY')

    # Feature flags
    if os.getenv('ENABLE_AUTO_EXECUTION'):
        config.enable_auto_execution = os.getenv('ENABLE_AUTO_EXECUTION').lower() == 'true'

    return config


# Composite score weights
COMPOSITE_SCORE_WEIGHTS = {
    'savings_weight': 0.4,
    'risk_weight': 0.6
}


# Instance family categorization
INSTANCE_FAMILIES = {
    'general_purpose': ['t3', 't4g', 'm5', 'm6i', 'm6a', 'm7i'],
    'compute_optimized': ['c5', 'c6i', 'c6a', 'c7i'],
    'memory_optimized': ['r5', 'r6i', 'r6a', 'r7i', 'x2'],
    'storage_optimized': ['i3', 'i4i', 'd3'],
    'accelerated': ['p3', 'p4', 'g4', 'g5']
}


# Default instance specs (simplified)
INSTANCE_SPECS = {
    'm5.large': {'cpu': 2, 'memory': 8, 'network': 'up_to_10'},
    'm5.xlarge': {'cpu': 4, 'memory': 16, 'network': 'up_to_10'},
    'm5.2xlarge': {'cpu': 8, 'memory': 32, 'network': 'up_to_10'},
    'm5.4xlarge': {'cpu': 16, 'memory': 64, 'network': '10'},
    'c5.large': {'cpu': 2, 'memory': 4, 'network': 'up_to_10'},
    'c5.xlarge': {'cpu': 4, 'memory': 8, 'network': 'up_to_10'},
    'c5.2xlarge': {'cpu': 8, 'memory': 16, 'network': 'up_to_10'},
    'r5.large': {'cpu': 2, 'memory': 16, 'network': 'up_to_10'},
    'r5.xlarge': {'cpu': 4, 'memory': 32, 'network': 'up_to_10'},
    't3.medium': {'cpu': 2, 'memory': 4, 'network': 'up_to_5'},
    't3.large': {'cpu': 2, 'memory': 8, 'network': 'up_to_5'},
}


# Orchestration pipeline stages
PIPELINE_STAGES = [
    'global_intelligence',
    'capacity_validation',
    'decision_engine',
    'cooldown_check',
    'cluster_execution'
]


# Agent roles and descriptions
AGENT_ROLES = {
    'GlobalIntelligenceAgent': {
        'role': 'Region-wide spot pool intelligence',
        'outputs': 'Ranked pool list with risk scores',
        'deterministic': True
    },
    'CapacityValidatorAgent': {
        'role': 'Batch capacity validation',
        'outputs': 'Validated and unavailable pools',
        'deterministic': True
    },
    'DecisionEngineAgent': {
        'role': 'Policy-driven placement decisions',
        'outputs': 'Selected pool or candidate list',
        'deterministic': True
    },
    'RightsizingAgent': {
        'role': 'Workload efficiency analysis',
        'outputs': 'Instance resizing recommendations',
        'deterministic': True
    },
    'CooldownControllerAgent': {
        'role': 'Anti-flapping enforcement',
        'outputs': 'Cooldown status and remaining time',
        'deterministic': True
    },
    'SubstituteManagerAgent': {
        'role': 'Safety fallback management',
        'outputs': 'Substitute instance selection',
        'deterministic': True
    },
    'ClusterExecutionAgent': {
        'role': 'Kubernetes execution layer',
        'outputs': 'Execution status',
        'deterministic': False  # External dependency
    },
    'EventMonitoringAgent': {
        'role': 'Interruption event handling',
        'outputs': 'Event response and blacklist updates',
        'deterministic': True
    }
}
