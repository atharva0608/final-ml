"""
AWS Pricing Service
===================

Real-time AWS pricing aggregation with regional caching and freshness guarantees.

Enterprise Guardrails:
- Pricing Freshness Contract: DO NOT allow optimization if pricing is stale (>15 min)
- Regional aggregation to minimize API calls
- Strict retry configuration (max_attempts=10, mode=adaptive)
- In-flight executions continue, never force switch to On-Demand mid-execution
"""

import boto3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from redis import Redis
from sqlalchemy.orm import Session
from botocore.config import Config

from backend.core.logger import logger
from backend.core.crypto import decrypt_credential, redact_credential
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.system_config import SystemConfig


class PricingFreshnessException(Exception):
    """Raised when pricing data is stale and optimization should be blocked."""
    pass


class AWSPricingService:
    """
    AWS Pricing Service with enterprise guardrails.

    Features:
    - Regional pricing aggregation
    - 15-minute freshness guarantee
    - Batch requests with retry logic
    - Global Redis caching
    """

    FRESHNESS_THRESHOLD_MINUTES = 15
    PRICING_TTL_SECONDS = 600  # 10 minutes (within 15-min freshness window)
    MAX_BATCH_SIZE = 100

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis

        # Boto3 config with enterprise retry policy
        self.boto_config = Config(
            retries={
                'max_attempts': 10,
                'mode': 'adaptive'
            },
            connect_timeout=5,
            read_timeout=60
        )

    def _get_platform_credentials(self) -> Optional[Dict[str, str]]:
        """
        Fetch and decrypt platform AWS credentials from SystemConfig.

        Platform credentials are used for:
        - Global pricing data (pricing:GetProducts)
        - Spot price history (ec2:DescribeSpotPriceHistory)
        - Instance catalog (ec2:DescribeInstanceTypes)

        Returns:
            Dict with 'access_key_id' and 'secret_access_key', or None if not configured

        Security:
            - Credentials are AES-256-GCM encrypted in database
            - Decrypted in-memory only, never logged
            - Used only for platform-level API calls
        """
        try:
            # Fetch encrypted credentials from database
            access_key_config = self.db.query(SystemConfig).filter(
                SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY"
            ).first()

            secret_key_config = self.db.query(SystemConfig).filter(
                SystemConfig.key == "PLATFORM_AWS_SECRET"
            ).first()

            if not access_key_config or not secret_key_config:
                logger.warning(
                    "Platform AWS credentials not configured in SystemConfig. "
                    "Pricing data will not be available. "
                    "Configure credentials in Admin > Platform Settings."
                )
                return None

            if not access_key_config.value or not secret_key_config.value:
                logger.warning("Platform AWS credentials are empty")
                return None

            # Try to decrypt credentials (handle both encrypted and plain-text)
            try:
                access_key = decrypt_credential(access_key_config.value)
                secret_key = decrypt_credential(secret_key_config.value)
            except (ValueError, Exception) as decrypt_error:
                # If decryption fails, assume credentials are stored in plain text
                logger.debug(f"Decryption failed, using credentials as plain text: {decrypt_error}")
                access_key = access_key_config.value
                secret_key = secret_key_config.value

            logger.info(
                f"Platform AWS credentials loaded: {redact_credential(access_key)}"
            )

            return {
                'access_key_id': access_key,
                'secret_access_key': secret_key
            }

        except Exception as e:
            logger.error(f"Failed to load platform credentials: {type(e).__name__}")
            return None

    def get_spot_price(
        self,
        instance_type: str,
        availability_zone: str,
        region: str,
        validate_freshness: bool = True
    ) -> Optional[float]:
        """
        Get spot price for instance type in specific AZ.

        Args:
            instance_type: EC2 instance type (e.g., "m5.large")
            availability_zone: AZ (e.g., "us-east-1a")
            region: AWS region
            validate_freshness: If True, raise exception if pricing is stale

        Returns:
            Spot price in USD/hour, or None if unavailable

        Raises:
            PricingFreshnessException: If pricing is stale and validate_freshness=True
        """
        # Check pricing freshness
        if validate_freshness:
            self._enforce_pricing_freshness(region)

        # Try cache first
        cache_key = f"pricing:spot:{region}:{availability_zone}:{instance_type}"
        cached = self.redis.get(cache_key)

        if cached:
            return float(cached)

        # Fetch from AWS (this will trigger regional refresh)
        self._refresh_regional_pricing(region, [instance_type])

        # Try cache again after refresh
        cached = self.redis.get(cache_key)
        return float(cached) if cached else None

    def get_ondemand_price(
        self,
        instance_type: str,
        region: str,
        validate_freshness: bool = True
    ) -> Optional[float]:
        """
        Get on-demand price for instance type.

        Args:
            instance_type: EC2 instance type
            region: AWS region
            validate_freshness: If True, raise exception if pricing is stale

        Returns:
            On-demand price in USD/hour, or None if unavailable

        Raises:
            PricingFreshnessException: If pricing is stale
        """
        if validate_freshness:
            self._enforce_pricing_freshness(region)

        cache_key = f"pricing:ondemand:{region}:{instance_type}"
        cached = self.redis.get(cache_key)

        if cached:
            return float(cached)

        # Fetch from Pricing API using platform credentials
        try:
            # Get platform credentials
            creds = self._get_platform_credentials()
            if not creds:
                logger.warning("Cannot fetch on-demand pricing: platform credentials not configured")
                return None

            pricing_client = boto3.client(
                'pricing',
                region_name='us-east-1',
                aws_access_key_id=creds['access_key_id'],
                aws_secret_access_key=creds['secret_access_key'],
                config=self.boto_config
            )

            response = pricing_client.get_products(
                ServiceCode='AmazonEC2',
                Filters=[
                    {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                    {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': self._region_to_location(region)},
                    {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                    {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                    {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                    {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
                ],
                MaxResults=1
            )

            if response.get('PriceList'):
                price_item = json.loads(response['PriceList'][0])
                on_demand_terms = price_item['terms']['OnDemand']

                for term in on_demand_terms.values():
                    for price_dimension in term['priceDimensions'].values():
                        price_per_hour = float(price_dimension['pricePerUnit']['USD'])

                        # Cache for 10 minutes
                        self.redis.setex(cache_key, self.PRICING_TTL_SECONDS, str(price_per_hour))

                        # Persist to database for historical tracking
                        try:
                            from backend.models.pricing import OnDemandPricing

                            # Upsert: check if exists, update if yes, insert if no
                            existing = self.db.query(OnDemandPricing).filter(
                                OnDemandPricing.instance_type == instance_type,
                                OnDemandPricing.region == region
                            ).first()

                            if existing:
                                existing.price = price_per_hour
                                existing.updated_at = datetime.utcnow()
                            else:
                                od_record = OnDemandPricing(
                                    instance_type=instance_type,
                                    region=region,
                                    price=price_per_hour,
                                    updated_at=datetime.utcnow()
                                )
                                self.db.add(od_record)

                            self.db.commit()
                            logger.debug(f"Persisted on-demand price for {instance_type} in {region}: ${price_per_hour}/hr")
                        except Exception as db_error:
                            logger.warning(f"Failed to persist on-demand price to database: {db_error}")
                            self.db.rollback()

                        return price_per_hour

            return None

        except Exception as e:
            logger.error(f"Failed to fetch on-demand price for {instance_type} in {region}: {e}")
            return None

    def refresh_regional_pricing_batch(
        self,
        region: str,
        instance_types: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Refresh pricing for all instance types in a region (batch operation).

        This is called by the pricing_worker to aggregate pricing for all clusters
        in a region, minimizing AWS API calls.

        Args:
            region: AWS region
            instance_types: List of instance types to refresh (if None, fetch all from clusters)

        Returns:
            Dict with counts: {"spot_prices_fetched": int, "ondemand_prices_fetched": int}
        """
        if instance_types is None:
            # Aggregate instance types from all clusters in this region
            instance_types = self._get_required_instance_types_for_region(region)

        # Refresh spot prices
        spot_count = self._refresh_regional_pricing(region, instance_types)

        # Refresh on-demand prices (batch)
        ondemand_count = 0
        for instance_type in instance_types:
            if self.get_ondemand_price(instance_type, region, validate_freshness=False):
                ondemand_count += 1

        # ── Task 2.1 / Issue #5: Detect partial-staleness ─────────────
        # A refresh that fetches only some of the requested types can still
        # update `pricing:last_updated`, suppressing the 15-minute gate.
        # To surface this, set per-cluster `partial_stale` flag when <80%
        # of requested instance types were actually refreshed.
        _total_requested = len(instance_types) if instance_types else 1
        _total_fetched = spot_count + ondemand_count
        _coverage_pct = (_total_fetched / max(1, _total_requested * 2)) * 100  # ×2: spot+OD
        if _coverage_pct < 80 and _total_requested > 0:
            logger.warning(
                f"[pricing] Partial refresh for {region}: "
                f"coverage {_coverage_pct:.0f}% ({_total_fetched}/{_total_requested * 2})"
            )
            try:
                _clusters = self.db.query(Cluster).filter(Cluster.region == region).all()
                for _c in _clusters:
                    _ps_key = f"spot:pricing:partial_stale:{_c.id}"
                    self.redis.setex(_ps_key, 900, json.dumps({
                        "region": region,
                        "coverage_pct": round(_coverage_pct, 1),
                        "spot_fetched": spot_count,
                        "od_fetched": ondemand_count,
                        "total_requested": _total_requested,
                        "detected_at": datetime.utcnow().isoformat(),
                    }))
                logger.info(
                    f"[pricing] Set partial_stale flag on {len(_clusters)} "
                    f"clusters in {region} (15-min TTL)"
                )
            except Exception as _ps_err:
                logger.error(f"[pricing] Failed to set partial_stale flags: {_ps_err}")

        # Update last_updated timestamp
        last_updated_key = f"pricing:last_updated:{region}"
        self.redis.set(last_updated_key, datetime.utcnow().isoformat())

        logger.info(
            f"Refreshed regional pricing for {region}: "
            f"{spot_count} spot prices, {ondemand_count} on-demand prices"
        )

        return {
            "spot_prices_fetched": spot_count,
            "ondemand_prices_fetched": ondemand_count
        }

    def _refresh_regional_pricing(
        self,
        region: str,
        instance_types: List[str]
    ) -> int:
        """
        Fetch spot prices for instance types in all AZs of a region.

        Args:
            region: AWS region
            instance_types: List of instance types

        Returns:
            Number of prices fetched
        """
        try:
            # Get platform credentials
            creds = self._get_platform_credentials()
            if not creds:
                logger.warning("Cannot fetch spot pricing: platform credentials not configured")
                return 0

            ec2_client = boto3.client(
                'ec2',
                region_name=region,
                aws_access_key_id=creds['access_key_id'],
                aws_secret_access_key=creds['secret_access_key'],
                config=self.boto_config
            )

            # Fetch spot price history (most recent)
            response = ec2_client.describe_spot_price_history(
                InstanceTypes=instance_types[:self.MAX_BATCH_SIZE],
                ProductDescriptions=['Linux/UNIX'],
                MaxResults=1000
            )

            prices_fetched = 0
            timestamp = datetime.utcnow()

            # Import pricing model
            from backend.models.pricing import SpotPriceHistory

            for item in response.get('SpotPriceHistory', []):
                instance_type = item['InstanceType']
                az = item['AvailabilityZone']
                price = float(item['SpotPrice'])
                product_description = item.get('ProductDescription', 'Linux/UNIX')

                # Cache in Redis
                cache_key = f"pricing:spot:{region}:{az}:{instance_type}"
                self.redis.setex(cache_key, self.PRICING_TTL_SECONDS, str(price))

                # Persist to database for historical tracking
                try:
                    spot_record = SpotPriceHistory(
                        instance_type=instance_type,
                        availability_zone=az,
                        region=region,
                        product_description=product_description,
                        price=price,
                        timestamp=timestamp,
                        created_at=timestamp
                    )
                    self.db.add(spot_record)
                except Exception as db_error:
                    logger.warning(f"Failed to insert spot price to database: {db_error}")
                    # Continue even if database insert fails (Redis cache is still updated)

                prices_fetched += 1

            # Commit all records at once
            try:
                self.db.commit()
                logger.info(f"Persisted {prices_fetched} spot prices to database for region {region}")
            except Exception as commit_error:
                logger.error(f"Failed to commit spot prices to database: {commit_error}")
                self.db.rollback()

            return prices_fetched

        except Exception as e:
            logger.error(f"Failed to refresh spot pricing for {region}: {e}")
            return 0

    def _enforce_pricing_freshness(self, region: str):
        """
        Enforce 15-minute pricing freshness contract.

        Raises PricingFreshnessException if pricing is stale.

        Enterprise Guardrail:
        - If pricing is stale, DO NOT allow new optimizations
        - Mark clusters as PRICING_STALE
        - Emit regional alert
        - In-flight executions continue (never auto-switch to On-Demand mid-drain)
        """
        last_updated_key = f"pricing:last_updated:{region}"
        last_updated_str = self.redis.get(last_updated_key)

        if not last_updated_str:
            # No pricing data available
            raise PricingFreshnessException(
                f"No pricing data available for region {region}. "
                f"Run pricing refresh first."
            )

        last_updated = datetime.fromisoformat(last_updated_str.decode('utf-8'))
        age_minutes = (datetime.utcnow() - last_updated).total_seconds() / 60

        if age_minutes > self.FRESHNESS_THRESHOLD_MINUTES:
            # Mark clusters as PRICING_STALE
            self._mark_clusters_pricing_stale(region)

            # Emit regional alert (debounced)
            self._emit_pricing_stale_alert(region, age_minutes)

            raise PricingFreshnessException(
                f"Pricing data for region {region} is stale "
                f"({age_minutes:.1f} minutes old, threshold: {self.FRESHNESS_THRESHOLD_MINUTES} minutes). "
                f"Blocking new optimizations until pricing is refreshed."
            )

    def _mark_clusters_pricing_stale(self, region: str):
        """Mark all clusters in region as PRICING_STALE."""
        try:
            clusters = self.db.query(Cluster).filter(Cluster.region == region).all()

            for cluster in clusters:
                # Store in Redis flag
                stale_key = f"cluster:{cluster.id}:pricing_stale"
                self.redis.setex(stale_key, 3600, "true")  # 1 hour TTL

            logger.warning(f"Marked {len(clusters)} clusters in {region} as PRICING_STALE")

        except Exception as e:
            logger.error(f"Failed to mark clusters as PRICING_STALE: {e}")

    def _emit_pricing_stale_alert(self, region: str, age_minutes: float):
        """Emit regional alert for stale pricing (debounced)."""
        alert_key = f"alert:pricing_stale:{region}"

        # Check if alert already sent (debounce for 1 hour)
        if self.redis.exists(alert_key):
            return

        # Set debounce flag
        self.redis.setex(alert_key, 3600, "sent")

        # TODO: Integrate with NotificationService when available
        logger.critical(
            f"PRICING STALE ALERT: Region {region} pricing is {age_minutes:.1f} minutes old. "
            f"New optimizations blocked until refresh completes."
        )

    def _get_required_instance_types_for_region(self, region: str) -> List[str]:
        """Get all instance types used by clusters in a region."""
        try:
            clusters = self.db.query(Cluster).filter(Cluster.region == region).all()

            instance_types = set()

            # TODO: Query actual node pools / instances from clusters
            # For now, return a default set
            default_types = [
                'm5.large', 'm5.xlarge', 'm5.2xlarge',
                'c5.large', 'c5.xlarge', 'c5.2xlarge',
                'r5.large', 'r5.xlarge', 'r5.2xlarge',
                't3.medium', 't3.large', 't3.xlarge'
            ]

            return list(instance_types) if instance_types else default_types

        except Exception as e:
            logger.error(f"Failed to get instance types for region {region}: {e}")
            return []

    def _region_to_location(self, region: str) -> str:
        """Convert AWS region to pricing API location name."""
        region_map = {
            'us-east-1': 'US East (N. Virginia)',
            'us-east-2': 'US East (Ohio)',
            'us-west-1': 'US West (N. California)',
            'us-west-2': 'US West (Oregon)',
            'eu-west-1': 'EU (Ireland)',
            'eu-central-1': 'EU (Frankfurt)',
            'ap-south-1': 'Asia Pacific (Mumbai)',
            'ap-southeast-1': 'Asia Pacific (Singapore)',
            'ap-northeast-1': 'Asia Pacific (Tokyo)',
        }
        return region_map.get(region, region)

    def is_pricing_fresh(self, region: str) -> Tuple[bool, Optional[float]]:
        """
        Check if pricing is fresh for a region.

        Returns:
            Tuple of (is_fresh: bool, age_minutes: Optional[float])
        """
        last_updated_key = f"pricing:last_updated:{region}"
        last_updated_str = self.redis.get(last_updated_key)

        if not last_updated_str:
            return (False, None)

        last_updated = datetime.fromisoformat(last_updated_str.decode('utf-8'))
        age_minutes = (datetime.utcnow() - last_updated).total_seconds() / 60

        return (age_minutes <= self.FRESHNESS_THRESHOLD_MINUTES, age_minutes)
