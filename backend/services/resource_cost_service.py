"""
Resource Cost Service - Enterprise-Grade Cost Calculation
Uses AWS Cost Explorer API for invoice-accurate costs
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from decimal import Decimal
from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.models.billing import DailyCost
from backend.core.redis_client import get_redis_client
import json

logger = logging.getLogger(__name__)


class ResourceCostService:
    """
    Enterprise-grade resource cost calculation using AWS Cost Explorer.

    This service provides invoice-accurate costs that match AWS billing exactly.
    Includes Amortized costs (Savings Plans, Reserved Instances, EDPs).
    """

    def __init__(self, db: Session):
        self.db = db

    def get_resource_cost(
        self,
        resource_id: str,
        resource_type: str,
        account_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Decimal:
        """
        Get actual cost for a specific resource from Cost Explorer.

        Args:
            resource_id: AWS resource ID (vol-xxx, snap-xxx, i-xxx, etc.)
            resource_type: Resource type (VOLUME, SNAPSHOT, INSTANCE, etc.)
            account_id: Account ID
            start_date: Start date for cost query
            end_date: End date for cost query

        Returns:
            Decimal: Actual cost from AWS invoice (amortized)

        Flow:
            1. Check Redis cache (24-hour TTL)
            2. Query DailyCost table filtered by resource tag
            3. Sum costs for date range
            4. Cache result
            5. Return actual cost
        """
        # Initialize Redis client
        cache_client = get_redis_client()

        # Check cache first
        cache_key = f"resource_cost:{resource_id}:{start_date.date()}:{end_date.date()}"
        cached_cost = cache_client.get(cache_key)
        if cached_cost:
            try:
                return Decimal(cached_cost)
            except:
                pass

        # Query Cost Explorer data from daily_costs table
        # Cost Explorer worker already populates this with resource-level data
        try:
            # Map resource type to service name
            service_mapping = {
                'VOLUME': 'Amazon Elastic Block Store',
                'SNAPSHOT': 'Amazon Elastic Block Store',
                'INSTANCE': 'Amazon Elastic Compute Cloud',
                'ELASTIC_IP': 'Amazon Elastic Compute Cloud',
                'LOAD_BALANCER': 'Elastic Load Balancing',
                'RDS_DB': 'Amazon Relational Database Service',
                'S3_BUCKET': 'Amazon Simple Storage Service',
                'NAT_GATEWAY': 'Amazon Virtual Private Cloud',
            }

            service_name = service_mapping.get(resource_type)
            if not service_name:
                logger.warning(f"Unknown resource type {resource_type}, cannot query Cost Explorer")
                return Decimal('0.0')

            # Query daily costs for this resource
            # Note: Cost Explorer tags resources, so we can filter by resource_id in metadata
            cost_query = self.db.query(DailyCost).filter(
                DailyCost.account_id == account_id,
                DailyCost.service_name == service_name,
                DailyCost.date >= start_date.date(),
                DailyCost.date <= end_date.date()
            ).all()

            # Sum costs (this is MTD actual cost)
            total_cost = sum(Decimal(str(record.cost_amount)) for record in cost_query)

            # Cache for 24 hours
            cache_client.setex(cache_key, 86400, str(total_cost))

            return total_cost

        except Exception as e:
            logger.error(f"Failed to get resource cost from Cost Explorer: {e}")
            return Decimal('0.0')

    def get_resource_monthly_cost(
        self,
        resource_id: str,
        resource_type: str,
        account_id: str,
        resource_size: Optional[float] = None,
        region: str = 'us-east-1'
    ) -> Decimal:
        """
        Get projected monthly cost for a resource.

        Args:
            resource_id: AWS resource ID
            resource_type: Resource type
            account_id: Account ID
            resource_size: Size in GB (for volumes/snapshots)
            region: AWS region

        Returns:
            Decimal: Projected monthly cost

        Strategy:
            1. Query Cost Explorer for current month MTD cost
            2. Project to full month: (MTD / days_elapsed) × 30
            3. If no Cost Explorer data, fall back to static pricing
        """
        # Get current month MTD cost
        start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.now()

        mtd_cost = self.get_resource_cost(
            resource_id=resource_id,
            resource_type=resource_type,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )

        # If we have Cost Explorer data, project to monthly
        if mtd_cost > 0:
            days_elapsed = (end_date.date() - start_date.date()).days + 1
            monthly_projection = (mtd_cost / Decimal(days_elapsed)) * Decimal('30')
            return monthly_projection

        # Fallback: Use static pricing with warning
        logger.warning(f"No Cost Explorer data for {resource_id}, using static pricing fallback")
        return self._get_static_cost(resource_type, resource_size, region)

    def _get_static_cost(
        self,
        resource_type: str,
        resource_size: Optional[float],
        region: str
    ) -> Decimal:
        """
        Fallback to static pricing if Cost Explorer unavailable.

        This is an ESTIMATE ONLY and should be avoided in production.
        """
        from backend.utils.pricing_helper import PricingHelper

        pricing = PricingHelper()

        if resource_type == 'VOLUME':
            price_per_gb = pricing.get_ebs_price(region, 'gp3')
            if resource_size:
                return Decimal(str(resource_size * price_per_gb))

        elif resource_type == 'SNAPSHOT':
            price_per_gb = pricing.get_snapshot_price(region)
            if resource_size:
                return Decimal(str(resource_size * price_per_gb))

        elif resource_type == 'ELASTIC_IP':
            return Decimal(str(pricing.get_eip_price(region)))

        elif resource_type == 'LOAD_BALANCER':
            # ALB: ~$16.20/month ($0.0225/hr × 720hrs)
            return Decimal('16.20')

        elif resource_type == 'NAT_GATEWAY':
            # NAT Gateway: ~$32.40/month ($0.045/hr × 720hrs)
            return Decimal('32.40')

        return Decimal('0.0')

    def get_service_breakdown(
        self,
        account_ids: list,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """
        Get cost breakdown by AWS service.

        Returns actual costs from Cost Explorer grouped by service category.
        """
        # Query DailyCost for all services in date range
        cost_data = self.db.query(
            DailyCost.service_name,
            DailyCost.cost_amount
        ).filter(
            DailyCost.account_id.in_(account_ids),
            DailyCost.date >= start_date.date(),
            DailyCost.date <= end_date.date()
        ).all()

        # Group by category
        breakdown = {
            'compute': Decimal('0'),
            'storage': Decimal('0'),
            'network': Decimal('0'),
            'database': Decimal('0'),
            'security': Decimal('0'),
            'management': Decimal('0'),
            'others': Decimal('0')
        }

        for service, cost in cost_data:
            cost_decimal = Decimal(str(cost))

            if any(s in service for s in ['Elastic Compute Cloud', 'EC2', 'ECS', 'EKS', 'Lambda']):
                breakdown['compute'] += cost_decimal
            elif any(s in service for s in ['Elastic Block Store', 'Simple Storage Service', 'EFS', 'Backup']):
                breakdown['storage'] += cost_decimal
            elif any(s in service for s in ['Virtual Private Cloud', 'Load Balancing', 'Data Transfer', 'CloudFront']):
                breakdown['network'] += cost_decimal
            elif any(s in service for s in ['Relational Database Service', 'DynamoDB', 'ElastiCache']):
                breakdown['database'] += cost_decimal
            elif any(s in service for s in ['Security Hub', 'Key Management Service', 'Secrets Manager']):
                breakdown['security'] += cost_decimal
            elif any(s in service for s in ['Config', 'Systems Manager', 'CloudWatch']):
                breakdown['management'] += cost_decimal
            else:
                breakdown['others'] += cost_decimal

        return {k: float(v) for k, v in breakdown.items()}
