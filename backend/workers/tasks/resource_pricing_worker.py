"""
Resource Pricing Worker - Daily Price Refresh

Celery task that runs every 24 hours to:
1. Scan all resources across all accounts
2. Calculate monthly cost for each resource (Pricing Model B)
3. Cache costs in Redis with 24-hour TTL

This worker ensures Cost/Mo column in Resource Hygiene tables always shows current data.
"""
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from backend.workers.app import app
from backend.models.base import SessionLocal
from backend.models.account import Account
from backend.services.resource_pricing_service import ResourcePricingService
from backend.services.hygiene_service import HygieneService
from backend.core.redis_client import get_redis_client
import json

logger = logging.getLogger(__name__)


@app.task(name='workers.pricing.refresh_all_resource_prices')
def refresh_all_resource_prices():
    """
    Refresh resource prices for all accounts.

    This task:
    1. Iterates through all accounts with AWS credentials
    2. Scans resources in each account (instances, volumes, snapshots, etc.)
    3. Calculates monthly cost for each resource
    4. Caches costs in Redis with 24-hour TTL

    Runs: Every 24 hours (Celery Beat)
    """
    db = SessionLocal()
    try:
        pricing_service = ResourcePricingService(db)
        hygiene_service = HygieneService(db)
        redis_client = get_redis_client()

        # Get all active accounts
        accounts = db.query(Account).filter(
            Account.role_arn.isnot(None)
        ).all()

        total_resources = 0
        total_accounts = len(accounts)

        logger.info(f"Starting resource pricing refresh for {total_accounts} accounts")

        for account in accounts:
            try:
                logger.info(f"Processing account {account.id} ({account.aws_account_id})")

                # Scan resources in this account using hygiene service
                # This gives us all resources with their metadata
                regions = ['ALL']  # Scan all regions
                scan_result = hygiene_service.scan_resources(
                    account_id=str(account.id),
                    request_regions=regions,
                    force_refresh=False  # Use cache if available
                )

                # Process each resource and calculate cost
                for resource in scan_result.resources:
                    try:
                        cost = calculate_resource_cost(
                            resource=resource,
                            pricing_service=pricing_service,
                            account=account
                        )

                        if cost is not None:
                            # Cache the cost
                            pricing_service.cache_resource_cost(
                                resource_id=resource.resource_id,
                                resource_type=resource.type,
                                cost=cost,
                                metadata={
                                    'account_id': str(account.id),
                                    'region': resource.region,
                                    'name': resource.name or resource.resource_id,
                                    'state': getattr(resource, 'state', 'N/A')
                                }
                            )
                            total_resources += 1

                    except Exception as e:
                        logger.error(f"Failed to calculate cost for {resource.resource_id}: {e}")
                        continue

                logger.info(f"Completed account {account.id}: processed {len(scan_result.resources)} resources")

            except Exception as e:
                logger.error(f"Failed to process account {account.id}: {e}")
                continue

        logger.info(f"Resource pricing refresh complete: {total_resources} resources across {total_accounts} accounts")

        # Store summary in Redis
        summary = {
            "last_refresh": datetime.now().isoformat(),
            "total_accounts": total_accounts,
            "total_resources": total_resources,
            "status": "success"
        }
        redis_client.setex(
            "resource_pricing:last_refresh",
            86400,
            json.dumps(summary)
        )

    except Exception as e:
        logger.error(f"Resource pricing refresh failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


def calculate_resource_cost(resource, pricing_service: ResourcePricingService, account: Account):
    """
    Calculate monthly cost for a single resource.

    Args:
        resource: ResourceItem from hygiene scan
        pricing_service: ResourcePricingService instance
        account: Account model

    Returns:
        Decimal: Monthly cost or None if calculation fails
    """
    from decimal import Decimal

    try:
        resource_type = resource.type
        region = resource.region or 'us-east-1'

        # INSTANCES
        if resource_type == 'INSTANCE':
            instance_type = getattr(resource, 'instance_type', None)
            if instance_type:
                return pricing_service.calculate_instance_cost(
                    instance_type=instance_type,
                    region=region,
                    hours=720  # Monthly
                )

        # VOLUMES
        elif resource_type == 'VOLUME':
            size_gb = getattr(resource, 'size', 0)
            volume_type = getattr(resource, 'volume_type', 'gp3')
            if size_gb > 0:
                return pricing_service.calculate_volume_cost(
                    volume_type=volume_type,
                    size_gb=float(size_gb)
                )

        # SNAPSHOTS
        elif resource_type == 'SNAPSHOT':
            size_gb = getattr(resource, 'size', 0)
            if size_gb > 0:
                return pricing_service.calculate_snapshot_cost(
                    size_gb=float(size_gb)
                )

        # ELASTIC IPS
        elif resource_type == 'ELASTIC_IP':
            is_attached = getattr(resource, 'is_attached', False)
            return pricing_service.calculate_eip_cost(
                is_attached=is_attached
            )

        # LOAD BALANCERS
        elif resource_type == 'LOAD_BALANCER':
            lb_type = getattr(resource, 'lb_type', 'application')
            return pricing_service.calculate_load_balancer_cost(
                lb_type=lb_type
            )

        # NAT GATEWAYS
        elif resource_type == 'NAT_GATEWAY':
            return pricing_service.calculate_nat_gateway_cost()

        # RDS DATABASES
        elif resource_type == 'RDS_DB':
            instance_class = getattr(resource, 'instance_class', 'db.t3.micro')
            engine = getattr(resource, 'engine', 'mysql')
            return pricing_service.calculate_rds_cost(
                instance_class=instance_class,
                region=region,
                engine=engine,
                hours=720
            )

        # Unknown resource type
        else:
            logger.warning(f"Unknown resource type for pricing: {resource_type}")
            return None

    except Exception as e:
        logger.error(f"Failed to calculate cost for {resource.resource_id}: {e}")
        return None


@app.task(name='workers.pricing.get_refresh_status')
def get_refresh_status():
    """
    Get status of last resource pricing refresh.

    Returns:
        Dict with last refresh timestamp and stats
    """
    redis_client = get_redis_client()
    cached_data = redis_client.get("resource_pricing:last_refresh")

    if cached_data:
        try:
            return json.loads(cached_data)
        except:
            pass

    return {
        "last_refresh": None,
        "status": "never_run"
    }
