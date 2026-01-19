"""
RDS Instance Analysis Model
Tracks RDS utilization and Multi-AZ optimization opportunities
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class RDSInstanceAnalysis(Base):
    __tablename__ = "rds_instance_analysis"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Instance Details
    db_instance_identifier = Column(String(100), nullable=False, index=True)
    engine = Column(String(50), nullable=False)
    instance_class = Column(String(50), nullable=False)
    multi_az = Column(Boolean, default=False)
    status = Column(String(50), nullable=True)
    
    # Environment Detection
    environment_tag = Column(String(50), nullable=True) # dev, test, prod, etc.
    is_production = Column(Boolean, default=True)      # inferred
    
    # Utilization Metrics (Last 14 days)
    avg_cpu_utilization = Column(Float, default=0.0)
    max_cpu_utilization = Column(Float, default=0.0)
    avg_db_connections = Column(Float, default=0.0)
    
    # Cost Data
    current_monthly_cost = Column(Float, default=0.0)
    estimated_savings = Column(Float, default=0.0) # If converted to Single-AZ (and/or rightsized)
    
    # Recommendation
    recommendation_type = Column(String(50), nullable=True) # convert_to_single_az, rightsize, none
    recommendation_impact = Column(String(20), nullable=True) # high, medium, low
    
    last_analyzed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    account = relationship("Account")

    def __repr__(self):
        return f"<RDSInstanceAnalysis(id={self.db_instance_identifier}, multi_az={self.multi_az})>"
