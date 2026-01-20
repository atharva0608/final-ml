"""
Savings Plan Utilization Model
Tracks AWS Savings Plans usage and coverage
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base, generate_uuid


class SavingsPlanType(str, enum.Enum):
    """Savings Plan types"""
    COMPUTE = "Compute"
    EC2_INSTANCE = "EC2Instance"
    SAGEMAKER = "SageMaker"


class SavingsPlanUtilization(Base):
    """
    Savings Plan Utilization Model.
    Tracks Savings Plans usage similar to Reserved Instance tracking.
    """
    __tablename__ = "savings_plan_utilization"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization link
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # AWS Account link
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Savings Plan Info
    savings_plan_id = Column(String(255), nullable=False, unique=True, index=True)
    savings_plan_arn = Column(String(512), nullable=True)
    plan_type = Column(SQLEnum(SavingsPlanType), nullable=False)
    
    # Commitment
    hourly_commitment = Column(Float, nullable=False)  # USD per hour
    monthly_commitment = Column(Float, nullable=False)  # Calculated from hourly
    
    # Utilization Metrics
    utilization_percentage = Column(Float, default=0.0)
    utilized_commitment = Column(Float, default=0.0)  # USD actually used
    unused_commitment = Column(Float, default=0.0)  # USD wasted
    
    # Savings Metrics
    actual_savings = Column(Float, default=0.0)  # Actual on-demand cost avoided
    potential_savings = Column(Float, default=0.0)  # Could save if 100% utilized
    
    # Coverage (what % of spend is covered)
    coverage_percentage = Column(Float, default=0.0)
    on_demand_spend = Column(Float, default=0.0)  # Uncovered spend
    
    # Analysis metadata
    lookback_days = Column(Integer, default=30)
    
    # Term information
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    payment_option = Column(String(50), nullable=True)  # All Upfront, Partial, No Upfront
    
    # Recommendation
    recommendation_type = Column(String(50), nullable=True)  # increase, decrease, keep, none
    recommendation_detail = Column(JSON, nullable=True)
    
    # Status tracking
    is_underutilized = Column(Boolean, default=False)
    is_expiring_soon = Column(Boolean, default=False)  # < 30 days
    
    # Timestamps
    last_analyzed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    account = relationship("Account")

    @property
    def monthly_waste(self) -> float:
        """Monthly cost wasted due to underutilization"""
        return self.unused_commitment

    @property
    def annual_waste(self) -> float:
        """Annual cost wasted"""
        return self.monthly_waste * 12

    @property
    def days_remaining(self) -> int:
        """Days until Savings Plan expires"""
        if self.end_date:
            delta = self.end_date - datetime.utcnow()
            return max(0, delta.days)
        return 0

    @property
    def health_status(self) -> str:
        """Overall health status"""
        if self.utilization_percentage >= 90:
            return "excellent"
        elif self.utilization_percentage >= 70:
            return "good"
        elif self.utilization_percentage >= 50:
            return "warning"
        else:
            return "critical"

    def __repr__(self):
        return f"<SavingsPlanUtilization(id={self.savings_plan_id}, utilization={self.utilization_percentage}%)>"
