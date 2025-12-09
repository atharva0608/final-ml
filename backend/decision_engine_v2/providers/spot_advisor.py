"""
Spot Advisor Providers

Provides historical spot interrupt rates from scraped data or AWS Spot Advisor.
"""

import json
from pathlib import Path
from typing import Dict
from ..interfaces import ISpotAdvisor


class MockSpotAdvisor(ISpotAdvisor):
    """Mock spot advisor for testing"""

    def get_interrupt_rate(self, instance_type: str, az: str) -> float:
        """Get mock interrupt rate"""
        # Mock: Larger instances = higher interrupt risk
        if 'metal' in instance_type or '24xlarge' in instance_type:
            return 0.18  # 18% interrupt rate
        elif '12xlarge' in instance_type or '16xlarge' in instance_type:
            return 0.12  # 12%
        elif '4xlarge' in instance_type or '8xlarge' in instance_type:
            return 0.08  # 8%
        else:
            return 0.05  # 5% for small instances


class FileBasedSpotAdvisor(ISpotAdvisor):
    """
    File-based spot advisor (uses scraper_data.json)

    Format expected:
    {
        "c5.large@ap-south-1a": {
            "interrupt_rate": 0.05,
            "last_updated": "2024-12-01"
        },
        ...
    }
    """

    def __init__(self, data_file: str):
        self.data_file = Path(data_file)
        self.data: Dict[str, Dict] = {}
        self._load_data()

    def _load_data(self):
        """Load spot advisor data from file"""
        if not self.data_file.exists():
            print(f"⚠️  Spot advisor data file not found: {self.data_file}")
            print(f"   Using mock data as fallback")
            return

        try:
            with open(self.data_file, 'r') as f:
                self.data = json.load(f)
            print(f"✓ Loaded spot advisor data from {self.data_file}")
        except Exception as e:
            print(f"⚠️  Failed to load spot advisor data: {e}")
            print(f"   Using mock data as fallback")

    def get_interrupt_rate(self, instance_type: str, az: str) -> float:
        """Get interrupt rate from file data"""
        key = f"{instance_type}@{az}"

        if key in self.data:
            return self.data[key].get('interrupt_rate', 0.10)

        # Fallback to mock if not found
        return MockSpotAdvisor().get_interrupt_rate(instance_type, az)
