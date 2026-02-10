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
        self.pricing_client = None
        
        # Only create pricing client if AWS credentials are available
        aws_access = getattr(settings, 'AWS_ACCESS_KEY', None)
        aws_secret = getattr(settings, 'AWS_SECRET_KEY', None)
        
        if aws_access and aws_secret:
            try:
                # Price List API is only available in us-east-1 and ap-south-1
                self.pricing_client = boto3.client(
                    'pricing',
                    aws_access_key_id=aws_access,
                    aws_secret_access_key=aws_secret,
                    region_name='us-east-1'
                )
            except Exception as e:
                print(f"Warning: Failed to initialize AWS Pricing client: {e}")
                self.pricing_client = None
        else:
            print("Info: AWS credentials not configured. Using fallback pricing.")
    
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
        cached = self.redis.get(cache_key) if self.redis else None
        if cached:
            return float(cached)
        
        # Return fallback if no pricing client available
        if not self.pricing_client:
            return self._get_fallback_s3_price(storage_class)
        
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
    
    
    def get_ebs_price(self, region: str, volume_type: str = 'gp3') -> float:
        """Get EBS storage price per GB-month"""
        # Fallback rates (approximate public pricing)
        rates = {
            'gp2': 0.10,
            'gp3': 0.08,
            'io1': 0.125,
            'io2': 0.125,
            'st1': 0.045,
            'sc1': 0.025,
            'standard': 0.05
        }
        return rates.get(volume_type, 0.10)

    def get_snapshot_price(self, region: str, storage_class: str = 'standard') -> float:
        """Get EBS Snapshot price per GB-month"""
        return 0.05

    def get_eip_price(self, region: str) -> float:
        """Get Elastic IP price per month"""
        # $0.005/hr * 730 hours
        return 3.65

    def get_ec2_price(self, region: str, instance_type: str) -> float:
        """
        Get EC2 On-Demand price per month
        
        Args:
            region: AWS region
            instance_type: EC2 instance type (e.g. t3.medium)
            
        Returns:
            Price per month in USD
        """
        cache_key = f"pricing:ec2:{region}:{instance_type}"
        
        # Check cache first
        cached = self.redis.get(cache_key) if self.redis else None
        if cached:
            return float(cached)
            
        # Return fallback if no pricing client available
        if not self.pricing_client:
            return self._get_fallback_ec2_price(instance_type)
            
        try:
            location = self._get_location_name(region)
            
            # Query Price List API
            filters = [
                {'Type': 'TERM_MATCH', 'Field': 'ServiceCode', 'Value': 'AmazonEC2'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
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
                price_per_hour = float(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
                
                # Convert to monthly (730 hours)
                price_per_month = price_per_hour * 730
                
                # Cache the result
                if self.redis:
                    self.redis.setex(cache_key, self.CACHE_TTL, str(price_per_month))
                    
                return price_per_month
            else:
                return self._get_fallback_ec2_price(instance_type)
                
        except Exception as e:
            print(f"Error fetching EC2 pricing: {e}")
            return self._get_fallback_ec2_price(instance_type)

    def get_rds_price(self, region: str, instance_class: str, engine: str) -> float:
        """
        Get RDS On-Demand price per month
        
        Args:
            region: AWS region
            instance_class: RDS instance class (e.g. db.t3.medium)
            engine: Database engine (e.g. mysql, postgres)
        """
        cache_key = f"pricing:rds:{region}:{instance_class}:{engine}"
        
        # Check cache first
        cached = self.redis.get(cache_key) if self.redis else None
        if cached:
            return float(cached)
            
        if not self.pricing_client:
             return self._get_fallback_rds_price(instance_class)
             
        try:
            location = self._get_location_name(region)
            
            # Engine mapping
            engine_map = {
                'mysql': 'MySQL',
                'postgres': 'PostgreSQL',
                'oracle': 'Oracle',
                'sqlserver': 'SQL Server'
            }
            aws_engine = engine_map.get(engine.lower(), 'MySQL')
            
            filters = [
                {'Type': 'TERM_MATCH', 'Field': 'ServiceCode', 'Value': 'AmazonRDS'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_class},
                {'Type': 'TERM_MATCH', 'Field': 'databaseEngine', 'Value': aws_engine},
                 {'Type': 'TERM_MATCH', 'Field': 'deploymentOption', 'Value': 'Single-AZ'}
            ]
            
            response = self.pricing_client.get_products(
                ServiceCode='AmazonRDS',
                Filters=filters,
                MaxResults=1
            )
            
            if response['PriceList']:
                price_item = json.loads(response['PriceList'][0])
                on_demand = price_item['terms']['OnDemand']
                price_dimensions = list(on_demand.values())[0]['priceDimensions']
                price_per_hour = float(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
                
                price_per_month = price_per_hour * 730
                
                if self.redis:
                    self.redis.setex(cache_key, self.CACHE_TTL, str(price_per_month))
                    
                return price_per_month
            else:
                return self._get_fallback_rds_price(instance_class)

        except Exception as e:
            print(f"Error fetching RDS pricing: {e}")
            return self._get_fallback_rds_price(instance_class)

    def _get_fallback_ec2_price(self, instance_type: str) -> float:
        """
        Fallback EC2 pricing (approximate us-east-1 on-demand rates)

        Returns monthly cost (price_per_hour * 730 hours)
        """
        prices = {
            # T2 family (Previous Generation)
            't2.nano': 4.20,
            't2.micro': 8.50,
            't2.small': 17.00,
            't2.medium': 34.00,
            't2.large': 68.00,
            't2.xlarge': 136.00,
            't2.2xlarge': 272.00,

            # T3 family (Current Generation Burstable)
            't3.nano': 3.80,
            't3.micro': 7.50,
            't3.small': 15.00,
            't3.medium': 30.00,
            't3.large': 60.00,
            't3.xlarge': 121.00,
            't3.2xlarge': 242.00,

            # T3a family (AMD)
            't3a.nano': 3.40,
            't3a.micro': 6.80,
            't3a.small': 13.50,
            't3a.medium': 27.00,
            't3a.large': 54.00,
            't3a.xlarge': 109.00,
            't3a.2xlarge': 218.00,

            # M5 family (General Purpose)
            'm5.large': 70.00,
            'm5.xlarge': 140.00,
            'm5.2xlarge': 280.00,
            'm5.4xlarge': 560.00,
            'm5.8xlarge': 1120.00,
            'm5.12xlarge': 1680.00,
            'm5.16xlarge': 2240.00,
            'm5.24xlarge': 3360.00,

            # M5a family (AMD General Purpose)
            'm5a.large': 63.00,
            'm5a.xlarge': 126.00,
            'm5a.2xlarge': 252.00,
            'm5a.4xlarge': 504.00,
            'm5a.8xlarge': 1008.00,
            'm5a.12xlarge': 1512.00,
            'm5a.16xlarge': 2016.00,
            'm5a.24xlarge': 3024.00,

            # C5 family (Compute Optimized)
            'c5.large': 62.00,
            'c5.xlarge': 124.00,
            'c5.2xlarge': 248.00,
            'c5.4xlarge': 496.00,
            'c5.9xlarge': 1116.00,
            'c5.12xlarge': 1488.00,
            'c5.18xlarge': 2232.00,
            'c5.24xlarge': 2976.00,

            # C5a family (AMD Compute Optimized)
            'c5a.large': 56.00,
            'c5a.xlarge': 112.00,
            'c5a.2xlarge': 224.00,
            'c5a.4xlarge': 448.00,
            'c5a.8xlarge': 896.00,
            'c5a.12xlarge': 1344.00,
            'c5a.16xlarge': 1792.00,
            'c5a.24xlarge': 2688.00,

            # R5 family (Memory Optimized)
            'r5.large': 91.00,
            'r5.xlarge': 183.00,
            'r5.2xlarge': 365.00,
            'r5.4xlarge': 730.00,
            'r5.8xlarge': 1460.00,
            'r5.12xlarge': 2190.00,
            'r5.16xlarge': 2920.00,
            'r5.24xlarge': 4380.00,

            # R5a family (AMD Memory Optimized)
            'r5a.large': 82.00,
            'r5a.xlarge': 164.00,
            'r5a.2xlarge': 328.00,
            'r5a.4xlarge': 657.00,
            'r5a.8xlarge': 1314.00,
            'r5a.12xlarge': 1971.00,
            'r5a.16xlarge': 2628.00,
            'r5a.24xlarge': 3942.00,

            # GPU instances
            'g4dn.xlarge': 380.00,
            'g4dn.2xlarge': 548.00,
            'g4dn.4xlarge': 876.00,
            'g4dn.8xlarge': 1576.00,
            'g4dn.12xlarge': 2835.00,
            'g4dn.16xlarge': 3152.00,
            'p3.2xlarge': 2242.00,
            'p3.8xlarge': 8967.00,
            'p3.16xlarge': 17934.00,
        }

        # If exact match not found, try to infer from family
        if instance_type not in prices:
            # Try to extract family (e.g., 't3' from 't3.nano')
            family = instance_type.split('.')[0] if '.' in instance_type else None

            # Return average price for family or generic fallback
            if family == 't3':
                return 50.00
            elif family in ['m5', 'm5a']:
                return 100.00
            elif family in ['c5', 'c5a']:
                return 100.00
            elif family in ['r5', 'r5a']:
                return 150.00
            else:
                return 75.00  # Generic fallback for unknown instance types

        return prices.get(instance_type, 75.00)

    def _get_fallback_rds_price(self, instance_class: str) -> float:
        """Fallback RDS pricing"""
        prices = {
            'db.t3.micro': 15.00,
            'db.t3.small': 30.00,
            'db.t3.medium': 60.00,
            'db.m5.large': 140.00
        }
        return prices.get(instance_class, 50.00)

    def get_load_balancer_price(self, region: str, type: str) -> float:
        return 16.00  # Approx $0.0225/hr

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
    
    def get_spot_price(self, region: str, instance_type: str, az: str = None) -> float:
        """
        Get current Spot price for an instance type

        Args:
            region: AWS region
            instance_type: EC2 instance type (e.g. t3.medium)
            az: Availability zone (optional, uses region default if not provided)

        Returns:
            Spot price per month in USD (uses 12-hour cache)
        """
        cache_key = f"pricing:spot:{region}:{instance_type}:{az or 'any'}"

        # Check cache first (12-hour TTL as requested)
        cached = self.redis.get(cache_key) if self.redis else None
        if cached:
            return float(cached)

        # Try to fetch real spot price from AWS
        try:
            import boto3
            from datetime import datetime, timedelta

            ec2 = boto3.client('ec2', region_name=region)

            # Get spot price history (last 1 hour)
            filters = {
                'InstanceTypes': [instance_type],
                'ProductDescriptions': ['Linux/UNIX'],
                'StartTime': datetime.utcnow() - timedelta(hours=1),
                'MaxResults': 1
            }

            if az:
                filters['AvailabilityZone'] = az

            response = ec2.describe_spot_price_history(**filters)

            if response.get('SpotPriceHistory'):
                spot_price_hourly = float(response['SpotPriceHistory'][0]['SpotPrice'])
                spot_price_monthly = spot_price_hourly * 730  # Convert to monthly

                # Cache for 12 hours (43200 seconds)
                if self.redis:
                    self.redis.setex(cache_key, 43200, str(spot_price_monthly))

                return spot_price_monthly
            else:
                # No spot price history, use fallback
                return self._get_fallback_spot_price(instance_type)

        except Exception as e:
            print(f"Error fetching spot price for {instance_type}: {e}")
            return self._get_fallback_spot_price(instance_type)

    def _get_fallback_spot_price(self, instance_type: str) -> float:
        """
        Fallback spot pricing (typically 60-70% cheaper than on-demand)
        """
        on_demand_price = self._get_fallback_ec2_price(instance_type)
        # Typical spot discount is 60-70%, we use 65% for estimates
        return on_demand_price * 0.35

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
