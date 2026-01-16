from sqlalchemy import Column, Integer, Boolean, String, DateTime
from sqlalchemy.sql import func
from backend.models.base import Base

class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id = Column(Integer, primary_key=True, index=True)
    
    # System Controls
    maintenance_mode = Column(Boolean, default=False)
    global_signup_enabled = Column(Boolean, default=True)
    default_trial_days = Column(Integer, default=14)
    
    # ML/AI Configuration
    active_ml_model_version = Column(String, default="optimizer_v1")
    
    # Integrations
    pricing_api_url = Column(String, nullable=True)
    
    # Metadata
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def as_dict(self):
        return {
            "id": self.id,
            "maintenance_mode": self.maintenance_mode,
            "global_signup_enabled": self.global_signup_enabled,
            "default_trial_days": self.default_trial_days,
            "active_ml_model_version": self.active_ml_model_version,
            "updated_at": self.updated_at
        }
