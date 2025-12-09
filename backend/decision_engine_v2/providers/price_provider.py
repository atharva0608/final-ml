"""
Price Providers

Implementations for fetching spot and on-demand prices.
"""

from typing import Dict
from ..interfaces import IPriceProvider


class MockPriceProvider(IPriceProvider):
    """
    Mock price provider for testing

    Returns realistic but fake prices based on instance family.
    """

    # Static on-demand prices (Mumbai/ap-south-1)
    ON_DEMAND_PRICES = {
        # C5 family
        'c5.large': 0.096, 'c5.xlarge': 0.192, 'c5.2xlarge': 0.384,
        'c5.4xlarge': 0.768, 'c5.9xlarge': 1.728, 'c5.12xlarge': 2.304,
        'c5.18xlarge': 3.456, 'c5.24xlarge': 4.608, 'c5.metal': 4.608,
        # M5 family
        'm5.large': 0.107, 'm5.xlarge': 0.214, 'm5.2xlarge': 0.428,
        'm5.4xlarge': 0.856, 'm5.8xlarge': 1.712, 'm5.12xlarge': 2.568,
        'm5.16xlarge': 3.424, 'm5.24xlarge': 5.136, 'm5.metal': 5.136,
        # R5 family
        'r5.large': 0.142, 'r5.xlarge': 0.284, 'r5.2xlarge': 0.568,
        'r5.4xlarge': 1.136, 'r5.8xlarge': 2.272, 'r5.12xlarge': 3.408,
        'r5.16xlarge': 4.544, 'r5.24xlarge': 6.816, 'r5.metal': 6.816,
        # T3 family
        't3.micro': 0.012, 't3.small': 0.024, 't3.medium': 0.048,
        't3.large': 0.096, 't3.xlarge': 0.192, 't3.2xlarge': 0.384,
    }

    def get_spot_price(self, instance_type: str, az: str) -> float:
        """Get mock spot price"""
        od_price = self.get_on_demand_price(instance_type)

        # Spot prices vary by AZ (mock variation)
        az_multiplier = {
            'ap-south-1a': 0.35,  # 65% discount
            'ap-south-1b': 0.40,  # 60% discount
            'ap-south-1c': 0.30,  # 70% discount (best)
        }

        multiplier = az_multiplier.get(az, 0.40)

        # Add some randomness based on instance type
        if 'large' in instance_type or 'xlarge' in instance_type:
            multiplier *= 0.9  # Larger instances cheaper

        return od_price * multiplier

    def get_on_demand_price(self, instance_type: str) -> float:
        """Get on-demand price"""
        return self.ON_DEMAND_PRICES.get(instance_type, 0.10)  # Default fallback


class AWSPriceProvider(IPriceProvider):
    """
    Real AWS price provider (production)

    Uses boto3 to fetch real-time spot prices from AWS.
    """

    def __init__(self, region: str = "ap-south-1"):
        self.region = region
        # In production, initialize boto3 client here
        # self.ec2_client = boto3.client('ec2', region_name=region)
        # self.pricing_client = boto3.client('pricing', region_name='us-east-1')

    def get_spot_price(self, instance_type: str, az: str) -> float:
        """Get real-time spot price from AWS"""
        # In production, call AWS API:
        # response = self.ec2_client.describe_spot_price_history(
        #     InstanceTypes=[instance_type],
        #     AvailabilityZone=az,
        #     MaxResults=1
        # )
        # return float(response['SpotPriceHistory'][0]['SpotPrice'])

        # For now, fall back to mock
        return MockPriceProvider().get_spot_price(instance_type, az)

    def get_on_demand_price(self, instance_type: str) -> float:
        """Get on-demand price from AWS Pricing API"""
        # In production, query AWS Pricing API
        # This is complex as it requires filtering through JSON
        # For now, fall back to mock
        return MockPriceProvider().get_on_demand_price(instance_type)
