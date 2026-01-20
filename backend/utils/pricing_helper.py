"""
AWS Pricing Helper
Fetches and caches current AWS pricing data from the Price List API
"""
import boto3
import json
from typing import Dict, Optional
from datetime import timedelta
from backend.core.config import settings
from backend.core.redis_client import get_redis_client


class PricingHelper:
    """Helper class for fetching AWS pricing data"""
    
    # Cache pricing for 24 hours
    CACHE_TTL = int(getattr(settings, 'PRICING_CACHE_TTL', 24)) * 3600
    
    def __init__(self):
        self.redis = get_redis_client()
        # Price List API is only available in us-east-1 and ap-south-1
        self.pricing_client = boto3.client(
            'pricing',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name='us-east-1'
        )
    
    def get_s3_storage_price(self, region: str, storage_class: str = 'Standard') -> float:
        """
        Get S3 storage price per GB-month for a specific region and storage class
        
        Args:
            region: AWS region (e.g., 'us-east-1')
            storage_class: Storage class (Standard, IA, Glacier, DeepArchive, IntelligentTiering)
        
        Returns:
            Price per GB-month in USD
        """
        cache_key = f"pricing:s3:{region}:{storage_class}"
        
        # Check cache first
        cached = self.redis.get(cache_key)
        if cached:
            return float(cached)
        
        try:
            # Map storage class to AWS terminology
            storage_class_map = {
                'Standard': 'General Purpose',
                'IA': 'Infrequent Access',
                'StandardIA': 'Infrequent Access',
                'Glacier': 'Amazon Glacier',
                'GlacierInstantRetrieval': 'Glacier Instant Retrieval',
                'DeepArchive': 'Glacier Deep Archive',
                'IntelligentTiering': 'Intelligent-Tiering'
            }
            
            aws_storage_class = storage_class_map.get(storage_class, storage_class)
            
            # Convert region to location name (e.g., us-east-1 -> US East (N. Virginia))
            location = self._get_location_name(region)
            
            # Query Price List API
            filters = [
                {'Type': 'TERM_MATCH', 'Field': 'ServiceCode', 'Value': 'AmazonS3'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'storageClass', 'Value': aws_storage_class},
                {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': 'Standard'}
            ]
            
            response = self.pricing_client.get_products(
                ServiceCode='AmazonS3',
                Filters=filters,
                MaxResults=1
            )
            
            if response['PriceList']:
                price_item = json.loads(response['PriceList'][0])
                on_demand = price_item['terms']['OnDemand']
                price_dimensions = list(on_demand.values())[0]['priceDimensions']
                price_per_gb = float(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
                
                # Cache the result
                self.redis.setex(cache_key, self.CACHE_TTL, str(price_per_gb))
                return price_per_gb
            else:
                # Fallback to default pricing if not found
                return self._get_fallback_s3_price(storage_class)
                
        except Exception as e:
            print(f"Error fetching S3 pricing: {e}")
            return self._get_fallback_s3_price(storage_class)
    
    def get_data_transfer_price(self, region: str, transfer_type: str = 'internet') -> float:
        """
        Get data transfer pricing
        
        Args:
            region: AWS region
            transfer_type: 'internet', 'inter_az', 'inter_region'
        
        Returns:
            Price per GB in USD
        """
        cache_key = f"pricing:transfer:{region}:{transfer_type}"
        
        cached = self.redis.get(cache_key)
        if cached:
            return float(cached)
        
        try:
            location = self._get_location_name(region)
            
            # Map transfer type to AWS terminology
            transfer_type_map = {
                'internet': 'InterRegion Outbound',
                'inter_az': 'IntraRegion',
                'inter_region': 'InterRegion Outbound'
            }
            
            filters = [
                {'Type': 'TERM_MATCH', 'Field': 'ServiceCode', 'Value': 'AmazonEC2'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'transferType', 'Value': transfer_type_map.get(transfer_type, 'InterRegion Outbound')}
            ]
            
            response = self.pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=filters,
                MaxResults=1
            )
            
            if response['PriceList']:
                price_item = json.loads(response['PriceList'][0])
                on_demand = price_item['terms']['OnDemand']
                price_dimensions = list(on_demand.values())[0]['priceDimensions']
                price_per_gb = float(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
                
                self.redis.setex(cache_key, self.CACHE_TTL, str(price_per_gb))
                return price_per_gb
            else:
                return self._get_fallback_transfer_price(transfer_type)
                
        except Exception as e:
            print(f"Error fetching transfer pricing: {e}")
            return self._get_fallback_transfer_price(transfer_type)
    
    def _get_location_name(self, region: str) -> str:
        """Convert region code to AWS location display name"""
        region_map = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'eu-west-1': 'EU (Ireland)',
            'eu-west-2': 'EU (London)',
            'eu-west-3': 'EU (Paris)',
            'eu-central-1': 'EU (Frankfurt)',
            'eu-north-1': 'EU (Stockholm)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-southeast-2': 'Asia Pacific (Sydney)',
            'ap-northeast-1': 'Asia Pacific (Tokyo)',
            'ap-northeast-2': 'Asia Pacific (Seoul)',
            'sa-east-1': 'South America (Sao Paulo)',
            'ca-central-1': 'Canada (Central)',
            'ap-east-1': 'Asia Pacific (Hong Kong)',
            'me-south-1': 'Middle East (Bahrain)',
            'af-south-1': 'Africa (Cape Town)'
        }
        return region_map.get(region, 'US East (N. Virginia)')
    
    def _get_fallback_s3_price(self, storage_class: str) -> float:
        """Fallback pricing when API fails (us-east-1 rates)"""
        fallback_prices = {
            'Standard': 0.023,
            'IA': 0.0125,
            'StandardIA': 0.0125,
            'Glacier': 0.004,
            'GlacierInstantRetrieval': 0.004,
            'DeepArchive': 0.00099,
            'IntelligentTiering': 0.023  # Variable, use Standard as approximation
        }
        return fallback_prices.get(storage_class, 0.023)
    
    def _get_fallback_transfer_price(self, transfer_type: str) -> float:
        """Fallback transfer pricing"""
        fallback_prices = {
            'internet': 0.09,
            'inter_az': 0.01,
            'inter_region': 0.02
        }
        return fallback_prices.get(transfer_type, 0.09)
    
    def clear_cache(self, pattern: str = "pricing:*"):
        """Clear pricing cache"""
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)
        return len(keys)


# Singleton instance
_pricing_helper = None

def get_pricing_helper() -> PricingHelper:
    """Get or create pricing helper singleton"""
    global _pricing_helper
    if _pricing_helper is None:
        _pricing_helper = PricingHelper()
    return _pricing_helper
