"""
SpotAdvisorRate model — stores per-region/instance-type interruption rate data
scraped from AWS Spot Advisor.
"""
from sqlalchemy import Column, String, Float, DateTime, Date, UniqueConstraint
from backend.models.base import Base
from uuid import uuid4
from datetime import datetime


class SpotAdvisorRate(Base):
    __tablename__ = 'spot_advisor_rates'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    region = Column(String(20), nullable=False, index=True)
    instance_type = Column(String(50), nullable=False, index=True)
    interruption_rate_category = Column(String(10))
    interruption_rate_pct = Column(Float, nullable=False)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    valid_from = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint('region', 'instance_type', 'valid_from'),
    )
