"""
S3 Bucket Analysis Model
Tracks bucket storage classes and cost optimization opportunities
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.models.base import Base, generate_uuid


class S3BucketAnalysis(Base):
    """
    S3 Bucket Analysis Model.
    Stores storage usage, access patterns, and tiering recommendations.
    """
    __tablename__ = "s3_bucket_analysis"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization link
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # AWS Account link
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Bucket Info
    bucket_name = Column(String(255), nullable=False, index=True)
    region = Column(String(50), nullable=False)
    
    # Storage Stats
    total_size_bytes = Column(Float, default=0.0)
    object_count = Column(Integer, default=0)
    
    # Storage Class Distribution (in bytes)
    size_standard = Column(Float, default=0.0)
    size_ia = Column(Float, default=0.0)
    size_glacier = Column(Float, default=0.0)
    size_deep_archive = Column(Float, default=0.0)
    size_intelligent = Column(Float, default=0.0)
    
    # Cost Data
    monthly_cost = Column(Float, default=0.0)
    estimated_savings = Column(Float, default=0.0)
    
    # Configuration
    has_lifecycle_policy = Column(Boolean, default=False)
    is_versioning_enabled = Column(Boolean, default=False)
    
    # Access Analysis (Data from S3 Analytics)
    last_accessed_date = Column(DateTime, nullable=True)
    size_hot = Column(Float, default=0.0)   # Accessed < 30 days
    size_warm = Column(Float, default=0.0)  # Accessed 30-90 days
    size_cold = Column(Float, default=0.0)  # Accessed > 90 days
    size_frozen = Column(Float, default=0.0) # Accessed > 365 days
    
    # Recommendation
    recommendation_type = Column(String(50), nullable=True)  # intelligent_tiering, lifecycle_glacier, lifecycle_deep, none
    recommendation_detail = Column(JSON, nullable=True)
    
    # Timestamps
    last_analyzed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")
    account = relationship("Account")

    @property
    def total_size_gb(self) -> float:
        return self.total_size_bytes / (1024**3)

    @property
    def waste_percentage(self) -> float:
        """Percentage of cost that could be saved"""
        if self.monthly_cost == 0:
            return 0.0
        return (self.estimated_savings / self.monthly_cost) * 100

    @property
    def cold_data_percentage(self) -> float:
        """Percentage of data not accessed in 90+ days"""
        if self.total_size_bytes == 0:
            return 0.0
        return (self.size_cold + self.size_frozen) / self.total_size_bytes * 100

    def __repr__(self):
        return f"<S3BucketAnalysis(bucket={self.bucket_name}, savings=${self.estimated_savings})>"
