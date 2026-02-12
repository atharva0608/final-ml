"""
Billing Models - AWS Cost Explorer data caching
"""
from sqlalchemy import Column, String, Float, DateTime, Date, ForeignKey, Index
from sqlalchemy.orm import relationship
from backend.models.base import Base
from datetime import datetime


class DailyCost(Base):
    """
    Stores daily AWS costs from Cost Explorer API.

    This model caches AWS Cost Explorer data to:
    1. Reduce API calls (Cost Explorer is expensive)
    2. Speed up dashboard queries
    3. Provide historical cost trends

    Data is fetched daily by the cost_explorer worker.
    """
    __tablename__ = "daily_costs"

    # Primary key format: "ACC-ID_YYYY-MM-DD_SERVICE"
    # Example: "123456789012_2026-02-10_AmazonEC2"
    id = Column(String, primary_key=True)

    # Foreign key to accounts table
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False, index=True)

    # Date of the cost record
    date = Column(Date, nullable=False, index=True)

    # AWS Service name (e.g., 'Amazon Elastic Compute Cloud - Compute')
    service_name = Column(String, nullable=False, index=True)

    # Cost amount in USD
    cost_amount = Column(Float, default=0.0, nullable=False)

    # Currency (always USD for AWS Cost Explorer)
    currency = Column(String, default="USD", nullable=False)

    # Cost type: 'Usage', 'Tax', 'Support', 'Refund'
    cost_type = Column(String, default="Usage", nullable=False)

    # Metadata
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    account = relationship("Account", back_populates="daily_costs")

    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_account_date', 'account_id', 'date'),
        Index('idx_date_service', 'date', 'service_name'),
        Index('idx_account_date_service', 'account_id', 'date', 'service_name'),
    )

    def __repr__(self):
        return f"<DailyCost(account={self.account_id}, date={self.date}, service={self.service_name}, cost=${self.cost_amount})>"


class CostExplorerSyncStatus(Base):
    """
    Tracks the last successful sync from AWS Cost Explorer.
    Used to prevent duplicate fetches and track sync health.
    """
    __tablename__ = "cost_explorer_sync_status"

    id = Column(String, primary_key=True)  # Format: "ACC-ID"
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False, unique=True)

    # Last successful sync timestamp
    last_sync_at = Column(DateTime, nullable=False)

    # Last date that was successfully fetched
    last_synced_date = Column(Date, nullable=False)

    # Sync status: 'SUCCESS', 'FAILED', 'IN_PROGRESS'
    status = Column(String, default="SUCCESS", nullable=False)

    # Error message if sync failed
    error_message = Column(String, nullable=True)

    # Number of records synced in last run
    records_synced = Column(Float, default=0, nullable=False)

    # Metadata
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    account = relationship("Account", back_populates="cost_sync_status")

    def __repr__(self):
        return f"<CostExplorerSyncStatus(account={self.account_id}, last_sync={self.last_sync_at}, status={self.status})>"
