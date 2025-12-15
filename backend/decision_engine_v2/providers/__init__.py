"""
Provider Implementations

These are concrete implementations of the provider interfaces.
Mock implementations are provided for testing, and can be replaced
with real AWS integrations in production.
"""

from .price_provider import MockPriceProvider, AWSPriceProvider
from .metadata_provider import MockInstanceMetadata, AWSInstanceMetadata
from .spot_advisor import MockSpotAdvisor, FileBasedSpotAdvisor
from .signal_provider import MockSignalProvider, IMDSSignalProvider
from .risk_models import (
    MockRiskModel,
    AlwaysSafeRiskModel,
    FamilyStressRiskModel
)

__all__ = [
    # Price Providers
    'MockPriceProvider',
    'AWSPriceProvider',
    # Metadata Providers
    'MockInstanceMetadata',
    'AWSInstanceMetadata',
    # Spot Advisors
    'MockSpotAdvisor',
    'FileBasedSpotAdvisor',
    # Signal Providers
    'MockSignalProvider',
    'IMDSSignalProvider',
    # Risk Models
    'MockRiskModel',
    'AlwaysSafeRiskModel',
    'FamilyStressRiskModel',
]
