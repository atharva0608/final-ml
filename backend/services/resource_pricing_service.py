"""
Resource Pricing Service - Individual Resource Cost Calculation

This service implements Pricing Model B: Resources Cost (Sum of Individual Resources @ 24/7)
- Calculates monthly cost for each resource assuming 24/7 uptime
- Stores costs in Redis with 24-hour TTL
- Background worker refreshes prices daily
- API endpoints read from Redis only (never calculate on-demand)

Pricing Model B is used for:
- Resource Hygiene Cost/Mo column
- Sidebar category totals
"""
import boto3
import logging
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session

from backend.core.redis_client import get_redis_client
from backend.models.account import Account
from backend.models.system_config import SystemConfig
import json

logger = logging.getLogger(__name__)


class ResourcePricingService:
    """
    Service for calculating individual resource costs (Pricing Model B).

    All costs assume 24/7 uptime and are stored in Redis with 24-hour TTL.
    """

    def __init__(self, db: Session):
        self.db = db
        self.redis = get_redis_client()

    def _get_platform_session(self):
        """Get the platform AWS session for pricing queries"""
        access_key = self.db.query(SystemConfig).filter(
            SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY"
        ).first()
        secret_key = self.db.query(SystemConfig).filter(
            SystemConfig.key == "PLATFORM_AWS_SECRET"
        ).first()
        region = self.db.query(SystemConfig).filter(
            SystemConfig.key == "PLATFORM_AWS_REGION"
        ).first()

        region_name = region.value if region and region.value else 'us-east-1'

        if access_key and secret_key and access_key.value and secret_key.value:
            return boto3.Session(
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value,
                region_name=region_name
            )
        return boto3.Session(region_name=region_name)

    def calculate_instance_cost(
        self,
        instance_type: str,
        region: str = 'us-east-1',
        hours: int = 720
    ) -> Decimal:
        """
        Calculate EC2 instance cost for specified hours (default: 720 = 30 days).

        Args:
            instance_type: EC2 instance type (e.g., 't3.micro')
            region: AWS region
            hours: Number of hours (default: 720 for monthly)

        Returns:
            Decimal: Total cost for the specified hours
        """
        try:
            # Try to get hourly rate from pricing API
            session = self._get_platform_session()
            pricing = session.client('pricing', region_name='us-east-1')

            # Map region to location name
            location = self._map_region_to_location(region)

            response = pricing.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                    {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                    {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                    {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                    {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
                ],
                MaxResults=1
            )

            if response.get('PriceList'):
                price_item = json.loads(response['PriceList'][0])
                on_demand_terms = price_item['terms']['OnDemand']
                price_dimensions = list(on_demand_terms.values())[0]['priceDimensions']
                hourly_rate = Decimal(list(price_dimensions.values())[0]['pricePerUnit']['USD'])
                return hourly_rate * Decimal(hours)
        except Exception as e:
            logger.warning(f"Failed to fetch pricing for {instance_type}: {e}")

        # Fallback to static pricing table
        return self._get_fallback_instance_price(instance_type, hours)

    def calculate_volume_cost(
        self,
        volume_type: str,
        size_gb: float
    ) -> Decimal:
        """
        Calculate EBS volume cost per month.

        Args:
            volume_type: EBS volume type (gp3, gp2, io1, io2, st1, sc1)
            size_gb: Volume size in GB

        Returns:
            Decimal: Monthly cost
        """
        # Standard EBS pricing (us-east-1, approximate)
        price_per_gb = {
            'gp3': Decimal('0.08'),
            'gp2': Decimal('0.10'),
            'io1': Decimal('0.125'),
            'io2': Decimal('0.125'),
            'st1': Decimal('0.045'),
            'sc1': Decimal('0.015'),
            'standard': Decimal('0.05')
        }

        rate = price_per_gb.get(volume_type.lower(), Decimal('0.10'))
        return rate * Decimal(str(size_gb))

    def calculate_snapshot_cost(
        self,
        size_gb: float
    ) -> Decimal:
        """
        Calculate EBS snapshot cost per month.

        Args:
            size_gb: Snapshot size in GB

        Returns:
            Decimal: Monthly cost
        """
        # Standard snapshot pricing: $0.05 per GB-month
        return Decimal('0.05') * Decimal(str(size_gb))

    def calculate_eip_cost(
        self,
        is_attached: bool
    ) -> Decimal:
        """
        Calculate Elastic IP cost per month.

        Args:
            is_attached: Whether the EIP is attached to a running instance

        Returns:
            Decimal: Monthly cost
        """
        if is_attached:
            return Decimal('0.0')  # No charge when attached
        else:
            # $0.005 per hour = $3.60 per month (720 hours)
            return Decimal('3.60')

    def calculate_load_balancer_cost(
        self,
        lb_type: str
    ) -> Decimal:
        """
        Calculate Load Balancer base cost per month (excluding data processing).

        Args:
            lb_type: 'application', 'network', or 'classic'

        Returns:
            Decimal: Monthly base cost
        """
        # Base hourly rates × 720 hours
        rates = {
            'application': Decimal('0.0225') * Decimal('720'),  # $16.20
            'network': Decimal('0.0225') * Decimal('720'),      # $16.20
            'classic': Decimal('0.025') * Decimal('720')         # $18.00
        }
        return rates.get(lb_type.lower(), Decimal('16.20'))

    def calculate_nat_gateway_cost(self) -> Decimal:
        """
        Calculate NAT Gateway base cost per month (excluding data processing).

        Returns:
            Decimal: Monthly base cost
        """
        # $0.045 per hour × 720 hours = $32.40
        return Decimal('0.045') * Decimal('720')

    def calculate_rds_cost(
        self,
        instance_class: str,
        region: str = 'us-east-1',
        engine: str = 'mysql',
        hours: int = 720
    ) -> Decimal:
        """
        Calculate RDS instance cost for specified hours.

        Args:
            instance_class: RDS instance class (e.g., 'db.t3.micro')
            region: AWS region
            engine: Database engine (mysql, postgres, oracle, sqlserver)
            hours: Number of hours (default: 720 for monthly)

        Returns:
            Decimal: Total cost
        """
        # Fallback to static pricing (approximate us-east-1)
        return self._get_fallback_rds_price(instance_class, hours)

    def get_resource_cost_from_cache(
        self,
        resource_id: str,
        resource_type: str
    ) -> Optional[Dict]:
        """
        Get resource cost from Redis cache.

        Args:
            resource_id: AWS resource ID
            resource_type: Resource type (INSTANCE, VOLUME, SNAPSHOT, etc.)

        Returns:
            Dict with cost info or None if not cached
        """
        cache_key = f"resource_price:{resource_type}:{resource_id}"
        cached_data = self.redis.get(cache_key)

        if cached_data:
            try:
                return json.loads(cached_data)
            except:
                return None
        return None

    def cache_resource_cost(
        self,
        resource_id: str,
        resource_type: str,
        cost: Decimal,
        metadata: Optional[Dict] = None
    ):
        """
        Cache resource cost in Redis with 24-hour TTL.

        Args:
            resource_id: AWS resource ID
            resource_type: Resource type
            cost: Monthly cost
            metadata: Optional metadata (size, type, etc.)
        """
        cache_key = f"resource_price:{resource_type}:{resource_id}"
        cache_data = {
            "cost": float(cost),
            "currency": "USD",
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        # Cache for 24 hours
        self.redis.setex(cache_key, 86400, json.dumps(cache_data))

    def _map_region_to_location(self, region: str) -> str:
        """Map AWS region code to location name for pricing API"""
        region_map = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'eu-west-1': 'EU (Ireland)',
            'eu-central-1': 'EU (Frankfurt)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-southeast-2': 'Asia Pacific (Sydney)',
            'ap-northeast-1': 'Asia Pacific (Tokyo)',
        }
        return region_map.get(region, 'US East (N. Virginia)')

    def _get_fallback_instance_price(self, instance_type: str, hours: int) -> Decimal:
        """
        Fallback static pricing for EC2 instances (us-east-1 approximate).
        """
        # Hourly rates for common instance types
        hourly_rates = {
            # T3 family
            't3.nano': Decimal('0.0052'),
            't3.micro': Decimal('0.0104'),
            't3.small': Decimal('0.0208'),
            't3.medium': Decimal('0.0416'),
            't3.large': Decimal('0.0832'),
            't3.xlarge': Decimal('0.1664'),
            't3.2xlarge': Decimal('0.3328'),

            # T2 family
            't2.nano': Decimal('0.0058'),
            't2.micro': Decimal('0.0116'),
            't2.small': Decimal('0.023'),
            't2.medium': Decimal('0.0464'),
            't2.large': Decimal('0.0928'),

            # M5 family
            'm5.large': Decimal('0.096'),
            'm5.xlarge': Decimal('0.192'),
            'm5.2xlarge': Decimal('0.384'),
            'm5.4xlarge': Decimal('0.768'),

            # C5 family
            'c5.large': Decimal('0.085'),
            'c5.xlarge': Decimal('0.17'),
            'c5.2xlarge': Decimal('0.34'),
            'c5.4xlarge': Decimal('0.68'),

            # R5 family
            'r5.large': Decimal('0.126'),
            'r5.xlarge': Decimal('0.252'),
            'r5.2xlarge': Decimal('0.504'),
            'r5.4xlarge': Decimal('1.008'),
        }

        rate = hourly_rates.get(instance_type, Decimal('0.05'))  # Default fallback
        return rate * Decimal(hours)

    def _get_fallback_rds_price(self, instance_class: str, hours: int) -> Decimal:
        """
        Fallback static pricing for RDS instances (us-east-1 approximate).
        """
        # Hourly rates for common RDS instance classes
        hourly_rates = {
            'db.t3.micro': Decimal('0.017'),
            'db.t3.small': Decimal('0.034'),
            'db.t3.medium': Decimal('0.068'),
            'db.t3.large': Decimal('0.136'),
            'db.t2.micro': Decimal('0.017'),
            'db.t2.small': Decimal('0.034'),
            'db.t2.medium': Decimal('0.068'),
            'db.m5.large': Decimal('0.192'),
            'db.m5.xlarge': Decimal('0.384'),
            'db.r5.large': Decimal('0.24'),
            'db.r5.xlarge': Decimal('0.48'),
        }

        rate = hourly_rates.get(instance_class, Decimal('0.05'))
        return rate * Decimal(hours)

    def calculate_s3_cost(
        self,
        bucket_size_gb: float,
        storage_class: str = "STANDARD",
        requests_per_month: int = 0
    ) -> Decimal:
        """
        Calculate S3 bucket cost per month.

        Args:
            bucket_size_gb: Size of bucket in GB
            storage_class: S3 storage class
            requests_per_month: Number of requests

        Returns:
            Monthly cost in USD
        """
        # Storage costs per GB-month (us-east-1)
        storage_prices = {
            "STANDARD": Decimal('0.023'),
            "INTELLIGENT_TIERING": Decimal('0.0125'),
            "STANDARD_IA": Decimal('0.0125'),
            "ONE_ZONE_IA": Decimal('0.01'),
            "GLACIER_INSTANT_RETRIEVAL": Decimal('0.004'),
            "GLACIER_FLEXIBLE_RETRIEVAL": Decimal('0.0036'),
            "GLACIER_DEEP_ARCHIVE": Decimal('0.00099')
        }

        storage_cost = Decimal(str(bucket_size_gb)) * storage_prices.get(
            storage_class.upper(),
            Decimal('0.023')
        )

        # Request costs (simplified - PUT/POST/LIST are more expensive)
        # $0.005 per 1000 PUT/COPY/POST/LIST requests
        # $0.0004 per 1000 GET/SELECT requests (average both)
        request_cost = (Decimal(requests_per_month) / Decimal('1000')) * Decimal('0.005')

        return storage_cost + request_cost

    def calculate_cloudwatch_cost(
        self,
        log_gb_ingested: float = 0,
        log_gb_stored: float = 0,
        custom_metrics: int = 0,
        alarms: int = 0
    ) -> Decimal:
        """
        Calculate CloudWatch costs per month.

        Args:
            log_gb_ingested: GB of logs ingested per month
            log_gb_stored: GB of logs stored
            custom_metrics: Number of custom metrics
            alarms: Number of alarms

        Returns:
            Monthly cost in USD
        """
        # Log ingestion: $0.50/GB
        ingestion_cost = Decimal(str(log_gb_ingested)) * Decimal('0.50')

        # Log storage: $0.03/GB-month
        storage_cost = Decimal(str(log_gb_stored)) * Decimal('0.03')

        # Custom metrics: $0.30/metric-month
        metrics_cost = Decimal(custom_metrics) * Decimal('0.30')

        # Alarms: $0.10/alarm-month (standard alarms)
        alarms_cost = Decimal(alarms) * Decimal('0.10')

        return ingestion_cost + storage_cost + metrics_cost + alarms_cost

    def calculate_lambda_cost(
        self,
        invocations_per_month: int,
        avg_duration_ms: int,
        memory_mb: int
    ) -> Decimal:
        """
        Calculate Lambda function cost per month.

        Args:
            invocations_per_month: Number of invocations
            avg_duration_ms: Average execution duration in milliseconds
            memory_mb: Allocated memory in MB

        Returns:
            Monthly cost in USD
        """
        # Requests: $0.20 per 1M requests (with 1M free tier)
        free_invocations = 1_000_000
        billable_invocations = max(0, invocations_per_month - free_invocations)
        request_cost = (Decimal(billable_invocations) / Decimal('1000000')) * Decimal('0.20')

        # Compute: $0.0000166667 per GB-second (with 400,000 GB-seconds free tier)
        gb_seconds = (
            Decimal(invocations_per_month) *
            (Decimal(avg_duration_ms) / Decimal('1000')) *
            (Decimal(memory_mb) / Decimal('1024'))
        )
        free_gb_seconds = Decimal('400000')
        billable_gb_seconds = max(Decimal('0'), gb_seconds - free_gb_seconds)
        compute_cost = billable_gb_seconds * Decimal('0.0000166667')

        return request_cost + compute_cost

    def calculate_kms_cost(self, key_count: int) -> Decimal:
        """
        Calculate KMS cost per month.

        Args:
            key_count: Number of customer-managed keys

        Returns:
            Monthly cost in USD ($1 per key per month)
        """
        return Decimal(key_count) * Decimal('1.0')

    def calculate_vpc_endpoint_cost(self, endpoint_hours: int = 720) -> Decimal:
        """
        Calculate VPC Endpoint (Interface Endpoint) cost.

        Args:
            endpoint_hours: Hours active (default 720 = 30 days)

        Returns:
            Monthly cost in USD
        """
        # Interface endpoints: $0.01 per hour per AZ
        # Assuming 1 AZ deployment
        hourly_rate = Decimal('0.01')
        return hourly_rate * Decimal(endpoint_hours)

    def calculate_transit_gateway_cost(self, hours: int = 720) -> Decimal:
        """
        Calculate Transit Gateway cost.

        Args:
            hours: Hours active (default 720 = 30 days)

        Returns:
            Monthly cost in USD
        """
        # Transit Gateway: $0.05 per hour
        hourly_rate = Decimal('0.05')
        return hourly_rate * Decimal(hours)

    def calculate_resource_cost(
        self,
        resource_type: str,
        resource_data: dict
    ) -> Decimal:
        """
        Calculate cost for any resource type.

        Args:
            resource_type: Type of resource (matches ResourceType enum)
            resource_data: Dictionary with resource-specific data

        Returns:
            Monthly cost in USD
        """
        resource_type = resource_type.upper()

        # Storage resources
        if resource_type == "S3_BUCKET":
            size_gb = resource_data.get('size_gb', 0)
            storage_class = resource_data.get('storage_class', 'STANDARD')
            requests = resource_data.get('requests_per_month', 0)
            return self.calculate_s3_cost(size_gb, storage_class, requests)

        elif resource_type == "VOLUME":
            volume_type = resource_data.get('volume_type', 'gp3')
            size_gb = resource_data.get('size_gb', 0)
            return self.calculate_volume_cost(volume_type, size_gb)

        elif resource_type == "SNAPSHOT":
            size_gb = resource_data.get('size_gb', 0)
            return self.calculate_snapshot_cost(size_gb)

        # Network resources
        elif resource_type == "VPC":
            return Decimal('0.0')  # VPCs are free

        elif resource_type == "NAT_GATEWAY":
            return self.calculate_nat_gateway_cost()

        elif resource_type == "VPC_ENDPOINT":
            hours = resource_data.get('hours', 720)
            return self.calculate_vpc_endpoint_cost(hours)

        elif resource_type == "TRANSIT_GATEWAY":
            hours = resource_data.get('hours', 720)
            return self.calculate_transit_gateway_cost(hours)

        elif resource_type == "ELASTIC_IP":
            is_attached = resource_data.get('is_attached', False)
            return self.calculate_eip_cost(is_attached)

        elif resource_type == "LOAD_BALANCER":
            lb_type = resource_data.get('lb_type', 'application')
            return self.calculate_load_balancer_cost(lb_type)

        # Security resources
        elif resource_type == "SECURITY_HUB":
            # Security Hub: $0.0010 per check per month (first 10,000 checks free)
            # Approximate: $10-15/month for typical setup
            return Decimal('10.0')

        elif resource_type == "KMS_KEY":
            return self.calculate_kms_cost(1)

        elif resource_type == "SECRETS_MANAGER":
            # Secrets Manager: $0.40 per secret per month
            return Decimal('0.40')

        elif resource_type == "CLOUDTRAIL":
            # CloudTrail: First trail free, additional trails $2.00/month
            return Decimal('2.0')

        elif resource_type == "GUARDDUTY":
            # GuardDuty: Usage-based, approximate $5-10/month
            return Decimal('5.0')

        # Management resources
        elif resource_type == "CONFIG_RECORDER":
            # Config: $0.003 per configuration item
            # Approximate: $5-15/month
            return Decimal('10.0')

        elif resource_type == "SSM_MANAGED_INSTANCE":
            # SSM itself is free (Standard instances)
            return Decimal('0.0')

        elif resource_type == "CLOUDWATCH_LOG_GROUP":
            log_gb_ingested = resource_data.get('log_gb_ingested', 0)
            log_gb_stored = resource_data.get('log_gb_stored', 0)
            return self.calculate_cloudwatch_cost(log_gb_ingested, log_gb_stored)

        elif resource_type == "CLOUDWATCH_ALARM":
            # Standard alarms: $0.10/alarm-month
            return Decimal('0.10')

        elif resource_type == "LAMBDA_FUNCTION":
            invocations = resource_data.get('invocations_per_month', 0)
            duration_ms = resource_data.get('avg_duration_ms', 1000)
            memory_mb = resource_data.get('memory_mb', 128)
            return self.calculate_lambda_cost(invocations, duration_ms, memory_mb)

        elif resource_type == "EVENTBRIDGE_RULE":
            # EventBridge: $1.00 per million events
            events = resource_data.get('events_per_month', 0)
            return (Decimal(events) / Decimal('1000000')) * Decimal('1.0')

        # Compute resources
        elif resource_type == "INSTANCE":
            instance_type = resource_data.get('instance_type', 't3.micro')
            region = resource_data.get('region', 'us-east-1')
            hours = resource_data.get('hours', 720)
            return self.calculate_instance_cost(instance_type, region, hours)

        elif resource_type == "EKS_CLUSTER":
            # EKS: $0.10 per hour = $72/month
            return Decimal('72.0')

        elif resource_type == "ECS_CLUSTER":
            # ECS control plane is free (pay only for resources)
            return Decimal('0.0')

        elif resource_type == "AUTO_SCALING_GROUP":
            # ASG itself is free
            return Decimal('0.0')

        # Database resources
        elif resource_type == "RDS_DB":
            instance_class = resource_data.get('instance_class', 'db.t3.micro')
            region = resource_data.get('region', 'us-east-1')
            engine = resource_data.get('engine', 'mysql')
            hours = resource_data.get('hours', 720)
            return self.calculate_rds_cost(instance_class, region, engine, hours)

        elif resource_type == "DYNAMODB_TABLE":
            # DynamoDB: On-demand approximate $1.25/million reads, $6.25/million writes
            # Estimate: $5/month for light usage
            return Decimal('5.0')

        elif resource_type == "ELASTICACHE_CLUSTER":
            # ElastiCache: Similar to EC2 pricing, approximate
            return Decimal('20.0')

        # Default
        else:
            logger.warning(f"Unknown resource type for pricing: {resource_type}")
            return Decimal('0.0')
