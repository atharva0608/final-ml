from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Numeric, Enum
from backend.models.base import Base

class SpotPriceHistory(Base):
    """Historical Spot Prices"""
    __tablename__ = "spot_price_history"

    id = Column(Integer, primary_key=True, index=True)
    instance_type = Column(String, index=True)
    availability_zone = Column(String, index=True)
    region = Column(String, index=True)
    product_description = Column(String)
    price = Column(Numeric(10, 4))
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

class OnDemandPricing(Base):
    """On-Demand Pricing Reference"""
    __tablename__ = "ondemand_pricing"

    id = Column(Integer, primary_key=True, index=True)
    instance_type = Column(String, index=True)
    region = Column(String, index=True)
    price = Column(Numeric(10, 4))
    updated_at = Column(DateTime, default=datetime.utcnow)

class SpotAdvisorData(Base):
    """Spot Advisor Data"""
    __tablename__ = "spot_advisor_data"

    id = Column(Integer, primary_key=True, index=True)
    instance_type = Column(String, index=True)
    region = Column(String, index=True)
    os_type = Column(String, default="Linux")
    interruption_frequency = Column(String)  # e.g., "<5%"
    interruption_index = Column(Integer)     # 0-4
    savings_percentage = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow)
