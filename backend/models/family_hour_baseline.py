"""
Family Hour Baseline Model (Enterprise Remediation Phase 2)
============================================================

Database model for storing hourly family baselines for ML feature engineering.

Stores pre-computed statistics for each instance family by hour of day.
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, Date, Index
from datetime import datetime
from backend.models.base import Base, generate_uuid


class FamilyHourBaseline(Base):
    """
    Family Hour Baseline Model.

    Stores hourly price statistics for instance families to support
    ML feature engineering and volatility index computation.
    """
    __tablename__ = "family_hour_baselines"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Family and region
    instance_family = Column(String(50), nullable=False, index=True)  # e.g., "m5", "c5"
    region = Column(String(50), nullable=False, index=True)

    # Time dimensions
    date = Column(Date, nullable=False, index=True)  # Date of baseline
    hour = Column(Integer, nullable=False, index=True)  # Hour of day (0-23)

    # Price statistics
    mean_price = Column(Float, nullable=False, default=0.0)  # Mean spot price
    min_price = Column(Float, nullable=False, default=0.0)   # Min spot price
    max_price = Column(Float, nullable=False, default=0.0)   # Max spot price
    stddev_price = Column(Float, nullable=False, default=0.0)  # Standard deviation
    sample_count = Column(Integer, nullable=False, default=0)  # Number of samples

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite indexes for performance
    __table_args__ = (
        Index("idx_family_region_date_hour", "instance_family", "region", "date", "hour", unique=True),
        Index("idx_family_region_hour", "instance_family", "region", "hour"),
        Index("idx_region_date", "region", "date"),
    )

    def __repr__(self):
        return (
            f"<FamilyHourBaseline(family={self.instance_family}, "
            f"region={self.region}, hour={self.hour}, mean={self.mean_price:.4f})>"
        )

    @property
    def volatility_index(self) -> float:
        """Calculate volatility index (stddev / mean)."""
        if self.mean_price == 0:
            return 0.0
        return self.stddev_price / self.mean_price

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "instance_family": self.instance_family,
            "region": self.region,
            "date": self.date.isoformat() if self.date else None,
            "hour": self.hour,
            "mean_price": self.mean_price,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "stddev_price": self.stddev_price,
            "volatility_index": self.volatility_index,
            "sample_count": self.sample_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
