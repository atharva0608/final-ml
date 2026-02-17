"""
Spot Price History Model - AtharvaAi ML Features

Stores historical spot prices for lag and rolling window features.
Maintains 24-hour rolling buffer (144 data points per pool at 10-min intervals).
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from backend.models.base import Base


class SpotPriceHistory(Base):
    """Historical spot price data for ML feature engineering."""

    __tablename__ = "spot_price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_type = Column(String(50), nullable=False, index=True)
    az = Column(String(20), nullable=False, index=True)
    region = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    spot_price = Column(Numeric(10, 6), nullable=False)
    ondemand_price = Column(Numeric(10, 6), nullable=False)
    savings = Column(Numeric(5, 4), nullable=True)  # (ondemand - spot) / ondemand
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('instance_type', 'az', 'timestamp', name='uq_spot_price_history'),
        {'extend_existing': True},
    )

    def __repr__(self):
        return f"<SpotPriceHistory {self.instance_type}:{self.az} @ {self.timestamp}>"
