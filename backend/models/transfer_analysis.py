"""
Data Transfer Analysis Model
Tracks high-cost data transfer types and usage
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class DataTransferAnalysis(Base):
    __tablename__ = "data_transfer_analysis"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Analysis Scope
    region = Column(String(50), nullable=False)
    
    # Transfer Metrics (Monthly Average based on last 30 days)
    transfer_type = Column(String(100), nullable=False) # e.g., 'Inter-AZ', 'Inter-Region', 'NAT Gateway', 'S3 Public'
    total_bytes_gb = Column(Float, default=0.0)
    monthly_cost = Column(Float, default=0.0)
    
    # Specific Source (if identifiable)
    source_resource_id = Column(String(100), nullable=True) # e.g. nat-012345
    
    # Recommendation
    recommendation_type = Column(String(50), nullable=True) # use_vpc_endpoint, consolidate_az, use_cloudfront
    estimated_savings = Column(Float, default=0.0)
    recommendation_detail = Column(JSON, nullable=True)
    
    # Production Metadata
    traffic_direction = Column(String(50), nullable=True)  # internet_egress, inter_az, inter_region, nat_gateway
    free_tier_consumed = Column(Integer, default=0)  # Whether free tier was applied
    lookback_days = Column(Integer, default=30)  # Analysis period used
    
    last_analyzed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    account = relationship("Account")

    def __repr__(self):
        return f"<DataTransferAnalysis(type={self.transfer_type}, cost=${self.monthly_cost})>"
