"""
Reserved Instance Analysis Model
Tracks RI utilization and waste detection
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class RIOfferingClass:
    STANDARD = "standard"
    CONVERTIBLE = "convertible"


class RIScope:
    REGIONAL = "regional"
    ZONAL = "zonal"


class RIUtilization(Base):
    """
    Reserved Instance Utilization tracking model.
    Stores analysis results from AWS Cost Explorer.
    """
    __tablename__ = "ri_utilization"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization link
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # AWS Account link
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # RI Identification
    reservation_id = Column(String(100), nullable=False, index=True)  # AWS RI ID
    instance_type = Column(String(50), nullable=False)  # e.g., m5.large, t3.medium
    platform = Column(String(50), nullable=True)  # Linux/UNIX, Windows, etc.
    region = Column(String(50), nullable=False)
    availability_zone = Column(String(50), nullable=True)  # For zonal RIs
    
    # RI Details
    offering_class = Column(String(20), default=RIOfferingClass.STANDARD)  # standard or convertible
    scope = Column(String(20), default=RIScope.REGIONAL)  # regional or zonal
    instance_count = Column(Integer, default=1)
    
    # Financial Data
    upfront_cost = Column(Float, default=0.0)  # Upfront payment made
    hourly_cost = Column(Float, default=0.0)  # Hourly recurring cost
    monthly_cost = Column(Float, default=0.0)  # Total monthly commitment
    
    # Utilization Metrics
    utilization_percentage = Column(Float, default=0.0)  # 0-100%
    utilized_hours = Column(Float, default=0.0)
    total_hours = Column(Float, default=0.0)
    
    # Waste Calculation
    monthly_waste = Column(Float, default=0.0)  # Wasted spend per month
    annual_waste = Column(Float, default=0.0)  # Projected annual waste
    unused_days = Column(Integer, default=0)  # Days with 0% utilization
    
    # Marketplace Data (for resale)
    estimated_resale_value = Column(Float, nullable=True)
    resale_percentage = Column(Float, nullable=True)  # % of remaining value recoverable
    
    # Dates
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)  # Expiration date
    days_remaining = Column(Integer, default=0)
    
    # Analysis Metadata
    last_analyzed_at = Column(DateTime, default=datetime.utcnow)
    analysis_period_days = Column(Integer, default=30)  # Analysis window
    
    # Recommendation
    recommendation_type = Column(String(50), nullable=True)  # sell, modify, keep, convert
    recommendation_detail = Column(JSON, nullable=True)  # Full recommendation payload
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    account = relationship("Account")

    @property
    def is_underutilized(self) -> bool:
        """Check if RI is underutilized (below 70% threshold)"""
        return self.utilization_percentage < 70.0

    @property
    def is_unused(self) -> bool:
        """Check if RI is completely unused for extended period"""
        return self.unused_days >= 14 or self.utilization_percentage == 0

    @property
    def risk_level(self) -> str:
        """Determine risk level based on utilization"""
        if self.utilization_percentage >= 80:
            return "healthy"
        elif self.utilization_percentage >= 60:
            return "warning"
        elif self.utilization_percentage > 0:
            return "critical"
        else:
            return "unused"

    def __repr__(self):
        return f"<RIUtilization(id={self.id}, type={self.instance_type}, utilization={self.utilization_percentage}%)>"
