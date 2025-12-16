"""
System Logs Model - Component-Level Logging

Tracks logs for all system components:
- Web Scraper (AWS Spot Advisor data fetching)
- Price Scraper (AWS Pricing API)
- Database Operations
- Linear Optimizer (switching decisions)
- ML Inference Engine
- Instance Management

Used for admin dashboard monitoring and troubleshooting.
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, Enum, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
import enum

from .connection import Base


class ComponentType(str, enum.Enum):
    """System component types"""
    WEB_SCRAPER = "web_scraper"
    PRICE_SCRAPER = "price_scraper"
    DATABASE = "database"
    LINEAR_OPTIMIZER = "linear_optimizer"
    ML_INFERENCE = "ml_inference"
    INSTANCE_MANAGER = "instance_manager"
    REDIS_CACHE = "redis_cache"
    API_SERVER = "api_server"


class LogLevel(str, enum.Enum):
    """Log severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ComponentStatus(str, enum.Enum):
    """Component health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class SystemLog(Base):
    """System-wide component logs for monitoring and troubleshooting"""
    __tablename__ = "system_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component = Column(String(50), nullable=False, index=True)  # ComponentType enum value
    level = Column(String(20), nullable=False, index=True)  # LogLevel enum value
    message = Column(Text, nullable=False)
    details = Column(JSONB)  # Additional context (errors, metrics, etc.)

    # Metadata
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    execution_time_ms = Column(Integer)  # Execution time if applicable
    success = Column(String(10))  # "success", "failure", or NULL

    def __repr__(self):
        return f"<SystemLog(component={self.component}, level={self.level}, timestamp={self.timestamp})>"


class ComponentHealth(Base):
    """Current health status of each system component"""
    __tablename__ = "component_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    component = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False)  # ComponentStatus enum value
    last_success = Column(DateTime)
    last_failure = Column(DateTime)
    last_check = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Metrics
    success_count_24h = Column(Integer, default=0)
    failure_count_24h = Column(Integer, default=0)
    avg_execution_time_ms = Column(Integer)

    # Additional info
    error_message = Column(Text)  # Last error message
    metadata = Column(JSONB)  # Component-specific metadata

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ComponentHealth(component={self.component}, status={self.status})>"


# Create indexes for efficient log queries
Index('idx_system_logs_component_timestamp', SystemLog.component, SystemLog.timestamp.desc())
Index('idx_system_logs_level_timestamp', SystemLog.level, SystemLog.timestamp.desc())
