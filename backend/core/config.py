"""
Configuration Management

Centralized configuration using Pydantic Settings for environment variables
"""
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, List, Union
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = Field(default="Spot Optimizer Platform", description="Application name")
    APP_VERSION: str = Field(default="1.0.0", description="Application version")
    ENVIRONMENT: str = Field(default="development", description="Environment (development/staging/production)")
    DEBUG: bool = Field(default=False, description="Debug mode")

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    DATABASE_POOL_SIZE: int = Field(default=20, ge=1, le=100, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50, description="Max overflow connections")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=1, le=200, description="Redis max connections")

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", description="Celery broker URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", description="Celery result backend")
    CELERY_TASK_ALWAYS_EAGER: bool = Field(default=False, description="Execute tasks synchronously")

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(default="dev-secret-key-change-in-production", description="JWT secret key for signing tokens")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440, description="Access token expiration")
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90, description="Refresh token expiration")

    # AWS Configuration
    AWS_REGION: str = Field(default="us-east-1", description="Default AWS region")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(None, description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(None, description="AWS secret access key")

    # API Configuration
    API_V1_PREFIX: str = Field(default="/api/v1", description="API v1 prefix")
    API_RATE_LIMIT: int = Field(default=100, ge=10, le=1000, description="API rate limit per minute")
    API_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=300, description="API timeout in seconds")

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost,http://localhost:80",
        description="CORS allowed origins (comma-separated string or list)"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="CORS allow credentials")

    # Frontend
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend URL")

    # Backend public URL — used by agent install scripts and ConfigMap generation.
    # MUST be set in production (e.g. https://api.yourplatform.com).
    # When unset, installer derives URL from request headers (local dev only).
    BACKEND_PUBLIC_URL: Optional[str] = Field(None, description="Public-facing backend URL for agent install scripts. Set in production.")

    # Email Service (SendGrid/SES)
    EMAIL_ENABLED: bool = Field(default=False, description="Enable email sending")
    SENDGRID_API_KEY: Optional[str] = Field(None, description="SendGrid API key")
    SES_REGION: Optional[str] = Field(None, description="AWS SES region")
    EMAIL_FROM_ADDRESS: str = Field(default="noreply@spotoptimizer.com", description="Email from address")
    EMAIL_FROM_NAME: str = Field(default="Spot Optimizer", description="Email from name")

    # Stripe Billing (Optional)
    STRIPE_ENABLED: bool = Field(default=False, description="Enable Stripe billing")
    STRIPE_SECRET_KEY: Optional[str] = Field(None, description="Stripe secret key")
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(None, description="Stripe publishable key")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(None, description="Stripe webhook secret")

    # System Configuration
    WORKER_THREADS: int = Field(default=4, ge=1, le=16, description="Worker threads")
    MAX_UPLOAD_SIZE_MB: int = Field(default=100, ge=1, le=1000, description="Max upload size in MB")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="json", description="Log format (json/text)")

    # Development/Testing
    TESTING: bool = Field(default=False, description="Testing mode")
    SEED_DATABASE: bool = Field(default=False, description="Seed database with test data")

    # Kubernetes Agent
    AGENT_API_KEY_LENGTH: int = Field(default=64, ge=32, le=128, description="Agent API key length")
    AGENT_HEARTBEAT_INTERVAL_SECONDS: int = Field(default=60, ge=10, le=300, description="Agent heartbeat interval")
    AGENT_COMMAND_TIMEOUT_HOURS: int = Field(default=1, ge=1, le=24, description="Agent command timeout")

    # Prometheus Monitoring
    PROMETHEUS_ENABLED: bool = Field(default=False, description="Enable Prometheus metrics")
    PROMETHEUS_PORT: int = Field(default=9090, ge=1024, le=65535, description="Prometheus metrics port")

    # Feature Flags
    FEATURE_HIBERNATION_ENABLED: bool = Field(default=True, description="Enable hibernation feature")
    FEATURE_KARPENTER_ENABLED: bool = Field(default=True, description="Enable Karpenter integration")
    FEATURE_ML_LAB_ENABLED: bool = Field(default=True, description="Enable ML Lab")
    FEATURE_ADMIN_IMPERSONATION: bool = Field(default=True, description="Enable admin impersonation")
    
    # Placement Advisor
    FEATURE_PLACEMENT_ADVISOR_ENABLED: bool = Field(default=False, description="Enable Placement Intelligence Advisor")
    PLACEMENT_ADVISOR_OBSERVATION_MODE: bool = Field(default=True, description="Force actionable=false for safety")

    # Placement Controller (§4 — pod-level eviction + stateful rollout)
    # Disabled by default. Enable after shadow mode observation.
    # Shadow mode per cluster: SET spot:placement_controller:shadow_mode:{cluster_id} 1
    FEATURE_PLACEMENT_CONTROLLER_ENABLED: bool = Field(default=False, description="Enable PlacementController pod-level eviction + stateful rollout")
    FEATURE_NODE_METADATA_PUSH: bool = Field(default=True, description="Enable T-09 agent node metadata push")
    FEATURE_HPA_CONFIG_PUSH: bool = Field(default=True, description="Enable T-13 agent HPA config push")
    FEATURE_HEARTBEAT_EXTENDED_FIELDS: bool = Field(default=True, description="Enable T-05 extended Redis fields in heartbeat")
    FEATURE_CONSOLIDATION_ANALYSIS: bool = Field(default=True, description="Enable T-18 consolidation Celery task")
    # Safety: when true, disallow ARM64 instance families (m6g/m7g/t4g/etc.) for rebalancing decisions
    FORBID_ARM_INSTANCE_FAMILIES: bool = Field(default=False, description="When true, rebalancer will exclude ARM64 families from candidate lists")
    FEATURE_POOL_OPTIMIZATION_ACTIVE: bool = Field(default=False, description="Enable pool rotation execution in pool_optimization_worker")
    AGENT_MIN_VERSION: str = Field(default="2.0.0", description="Minimum supported agent version — older agents log a deprecation warning")
    CLUSTER_MAX_SPOT_RATIO_PROD: float = Field(default=0.50, description="Max spot ratio for prod clusters")
    CLUSTER_MAX_SPOT_RATIO_STAGING: float = Field(default=0.70, description="Max spot ratio for staging clusters")
    CLUSTER_MAX_SPOT_RATIO_DEV: float = Field(default=0.70, description="Max spot ratio for dev clusters")
    PLACEMENT_CYCLE_TIME_BUDGET_SECONDS: int = Field(default=480, description="Max seconds a placement cycle can run per cluster")

    # Security
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=14, description="Bcrypt hashing rounds")
    PASSWORD_MIN_LENGTH: int = Field(default=8, ge=6, le=32, description="Minimum password length")
    API_KEY_PREFIX: str = Field(default="sk-", description="API key prefix")

    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse CORS origins from comma-separated string or list"""
        if isinstance(v, str):
            # Split by comma and strip whitespace
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        elif isinstance(v, list):
            return v
        return []

    @field_validator('ENVIRONMENT')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value"""
        if v not in ['development', 'staging', 'production']:
            raise ValueError('ENVIRONMENT must be development, staging, or production')
        return v

    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        if v not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError('LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL')
        return v.upper()

    @field_validator('LOG_FORMAT')
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Validate log format"""
        if v not in ['json', 'text']:
            raise ValueError('LOG_FORMAT must be json or text')
        return v

    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT == "production"

    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT == "development"

    def is_testing_env(self) -> bool:
        """Check if running in testing mode"""
        return self.TESTING

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore"
    }


# Singleton settings instance
settings = Settings()

# ── Spot Optimizer Global Constants ────────────────────────────────────────
GLOBAL_CACHE_SIZE: int = 5000
GLOBAL_CACHE_TTL: int = 3600
CAPACITY_SCORE_DIVISOR: int = 4
RISK_TIER_THRESHOLDS: list = [0.05, 0.10, 0.15, 0.20]
MAX_FAMILY_SHARE: float = 0.40
PRICE_SPIKE_FACTOR: float = 1.60
LAUNCH_FAILURE_RATIO_THRESHOLD: float = 0.30
REGION_MARKET_HEALTH_TIER1_THRESHOLD: int = 100
GLOBAL_POOL_LOCK_TTL: int = 120
SPOT_PRICE_STALENESS_WARN_SECS: int = 1800
SPOT_ADVISOR_STALENESS_DAYS: int = 45
DEFAULT_INTERRUPTION_RATE_PCT: float = 15.0
CREDENTIAL_CACHE_TTL_BUFFER_SECS: int = 300
MAX_CONCURRENT_ASSUME_ROLE: int = 50
MAX_CONCURRENT_REGION_CALLS: int = 3
ORPHAN_INSTANCE_TIMEOUT_MIN: int = 15
EMERGENCY_DEDUP_TTL_SECS: int = 600
REBALANCE_BLACKLIST_TIER_HOURS: list = [1, 6, 24]
CLUSTER_COOLDOWN_MINUTES: int = 60
EMERGENCY_COOLDOWN_MINUTES: int = 120
NODE_FAILURE_COOLDOWN_MINUTES: int = 30
POOL_TERMINATION_BLACKLIST_HOURS: int = 24
RESIZE_COOLDOWN_HOURS: int = 6
DRY_RUN_CANDIDATE_LIMIT: int = 3
REBALANCE_THRESHOLD: int = 3


def get_settings() -> Settings:
    """
    Get application settings

    Returns:
        Settings instance
    """
    return settings


def is_production() -> bool:
    """Check if running in production environment"""
    return settings.ENVIRONMENT == "production"


def is_development() -> bool:
    """Check if running in development environment"""
    return settings.ENVIRONMENT == "development"


def is_testing() -> bool:
    """Check if running in testing mode"""
    return settings.TESTING


def get_database_url() -> str:
    """Get database URL with proper formatting"""
    return settings.DATABASE_URL


def get_redis_url() -> str:
    """Get Redis URL"""
    return settings.REDIS_URL


def get_cors_origins() -> List[str]:
    """
    Get CORS allowed origins as a list

    Handles both string (comma-separated) and list formats
    """
    cors = settings.CORS_ORIGINS
    if isinstance(cors, str):
        origins = [origin.strip() for origin in cors.split(',') if origin.strip()]
    else:
        origins = list(cors)

    if settings.is_development():
        for origin in (
            "http://localhost",
            "http://localhost:80",
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1",
            "http://127.0.0.1:80",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ):
            if origin not in origins:
                origins.append(origin)

    return origins
