"""
Static Data Scraper for Spot Optimizer Platform - Redis Edition

Fetches:
1. Historical interrupt rates from AWS Spot Advisor
2. Instance hardware specifications (vCPU, RAM, Architecture)

Writes to: Redis (primary) + backend/data/static_intelligence.json (backup)

Redis Keys:
- spot_risk:{region}:{instance_type} - Interrupt rate and savings data
- spot_price_history:{region}:{family} - Historical price statistics
- instance_metadata:{instance_type} - Instance specifications

TTL: 3600 seconds (1 hour)
"""

import json
import redis
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class SpotAdvisorScraper:
    """Fetches historical interrupt rates from AWS Spot Advisor"""

    # AWS Spot Advisor data URL
    SPOT_ADVISOR_URL = "https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json"

    def __init__(self, region: str = "ap-south-1"):
        self.region = region

    def fetch(self) -> Dict[str, Dict]:
        """
        Fetch spot advisor data

        Returns:
            Dict mapping "instance_type@az" to interrupt rate data
        """
        print(f"\n📊 Fetching Spot Advisor data for {self.region}...")

        try:
            response = requests.get(self.SPOT_ADVISOR_URL, timeout=30)
            response.raise_for_status()
            data = response.json()

            print(f"  ✓ Downloaded spot advisor data")

            # Parse the data structure
            # Format: data['spot_advisor'][region][az]['Linux'][instance_type]['r']
            # where 'r' is interrupt rate (0-5 scale)

            result = {}

            if 'spot_advisor' not in data:
                print(f"  ⚠️  Unexpected data format, using fallback")
                return self._get_fallback_data()

            region_data = data['spot_advisor'].get(self.region, {})

            for az, az_data in region_data.items():
                linux_data = az_data.get('Linux', {})

                for instance_type, type_data in linux_data.items():
                    interrupt_rate_code = type_data.get('r', 2)  # Default to 2 (5-10%)
                    savings_code = type_data.get('s', 50)  # Savings percentage

                    # Convert AWS's 0-5 scale to actual interrupt rate
                    # 0: <5%, 1: 5-10%, 2: 10-15%, 3: 15-20%, 4: >20%
                    interrupt_rate_map = {
                        0: 0.025,  # <5%
                        1: 0.075,  # 5-10%
                        2: 0.125,  # 10-15%
                        3: 0.175,  # 15-20%
                        4: 0.225,  # >20%
                        5: 0.250,  # >20% (high)
                    }

                    interrupt_rate = interrupt_rate_map.get(interrupt_rate_code, 0.125)

                    key = f"{instance_type}@{az}"
                    result[key] = {
                        'interrupt_rate': interrupt_rate,
                        'interrupt_rate_code': interrupt_rate_code,
                        'savings_vs_od': savings_code / 100.0,  # Convert to 0-1 scale
                        'availability_zone': az,
                        'last_updated': datetime.now().isoformat()
                    }

            print(f"  ✓ Parsed {len(result)} spot pools")
            return result

        except Exception as e:
            print(f"  ❌ Failed to fetch spot advisor data: {e}")
            print(f"  ℹ️  Using fallback data")
            return self._get_fallback_data()

    def _get_fallback_data(self) -> Dict[str, Dict]:
        """Fallback data when AWS API is unavailable"""
        # Create reasonable defaults for common instances
        fallback = {}

        instance_types = [
            'c5.large', 'c5.xlarge', 'c5.2xlarge', 'c5.4xlarge',
            'm5.large', 'm5.xlarge', 'm5.2xlarge', 'm5.4xlarge',
            'r5.large', 'r5.xlarge', 'r5.2xlarge', 'r5.4xlarge',
            't3.micro', 't3.small', 't3.medium', 't3.large',
        ]

        azs = ['ap-south-1a', 'ap-south-1b', 'ap-south-1c']

        for instance_type in instance_types:
            for az in azs:
                key = f"{instance_type}@{az}"
                # Larger instances = slightly higher interrupt risk
                base_rate = 0.08 if 'large' in instance_type or 'xlarge' in instance_type else 0.12
                fallback[key] = {
                    'interrupt_rate': base_rate,
                    'interrupt_rate_code': 1,
                    'savings_vs_od': 0.65,  # Default 65% savings
                    'availability_zone': az,
                    'last_updated': datetime.now().isoformat(),
                    'source': 'fallback'
                }

        return fallback


class InstanceMetadataScraper:
    """Fetches instance hardware specifications"""

    # Hardcoded metadata for common Mumbai instances
    # In production, could scrape from ec2instances.info API
    INSTANCE_METADATA = {
        # C5 family (compute-optimized)
        'c5.large': {'vcpu': 2, 'memory_gb': 4, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.xlarge': {'vcpu': 4, 'memory_gb': 8, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.2xlarge': {'vcpu': 8, 'memory_gb': 16, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.4xlarge': {'vcpu': 16, 'memory_gb': 32, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.9xlarge': {'vcpu': 36, 'memory_gb': 72, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.12xlarge': {'vcpu': 48, 'memory_gb': 96, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.18xlarge': {'vcpu': 72, 'memory_gb': 144, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.24xlarge': {'vcpu': 96, 'memory_gb': 192, 'architecture': 'x86_64', 'family': 'c5'},
        'c5.metal': {'vcpu': 96, 'memory_gb': 192, 'architecture': 'x86_64', 'family': 'c5'},
        # M5 family (general-purpose)
        'm5.large': {'vcpu': 2, 'memory_gb': 8, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.xlarge': {'vcpu': 4, 'memory_gb': 16, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.2xlarge': {'vcpu': 8, 'memory_gb': 32, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.4xlarge': {'vcpu': 16, 'memory_gb': 64, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.8xlarge': {'vcpu': 32, 'memory_gb': 128, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.12xlarge': {'vcpu': 48, 'memory_gb': 192, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.16xlarge': {'vcpu': 64, 'memory_gb': 256, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.24xlarge': {'vcpu': 96, 'memory_gb': 384, 'architecture': 'x86_64', 'family': 'm5'},
        'm5.metal': {'vcpu': 96, 'memory_gb': 384, 'architecture': 'x86_64', 'family': 'm5'},
        # R5 family (memory-optimized)
        'r5.large': {'vcpu': 2, 'memory_gb': 16, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.xlarge': {'vcpu': 4, 'memory_gb': 32, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.2xlarge': {'vcpu': 8, 'memory_gb': 64, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.4xlarge': {'vcpu': 16, 'memory_gb': 128, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.8xlarge': {'vcpu': 32, 'memory_gb': 256, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.12xlarge': {'vcpu': 48, 'memory_gb': 384, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.16xlarge': {'vcpu': 64, 'memory_gb': 512, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.24xlarge': {'vcpu': 96, 'memory_gb': 768, 'architecture': 'x86_64', 'family': 'r5'},
        'r5.metal': {'vcpu': 96, 'memory_gb': 768, 'architecture': 'x86_64', 'family': 'r5'},
        # T3 family (burstable)
        't3.micro': {'vcpu': 2, 'memory_gb': 1, 'architecture': 'x86_64', 'family': 't3'},
        't3.small': {'vcpu': 2, 'memory_gb': 2, 'architecture': 'x86_64', 'family': 't3'},
        't3.medium': {'vcpu': 2, 'memory_gb': 4, 'architecture': 'x86_64', 'family': 't3'},
        't3.large': {'vcpu': 2, 'memory_gb': 8, 'architecture': 'x86_64', 'family': 't3'},
        't3.xlarge': {'vcpu': 4, 'memory_gb': 16, 'architecture': 'x86_64', 'family': 't3'},
        't3.2xlarge': {'vcpu': 8, 'memory_gb': 32, 'architecture': 'x86_64', 'family': 't3'},
        # T4g family (ARM Graviton2)
        't4g.micro': {'vcpu': 2, 'memory_gb': 1, 'architecture': 'arm64', 'family': 't4g'},
        't4g.small': {'vcpu': 2, 'memory_gb': 2, 'architecture': 'arm64', 'family': 't4g'},
        't4g.medium': {'vcpu': 2, 'memory_gb': 4, 'architecture': 'arm64', 'family': 't4g'},
        't4g.large': {'vcpu': 2, 'memory_gb': 8, 'architecture': 'arm64', 'family': 't4g'},
        't4g.xlarge': {'vcpu': 4, 'memory_gb': 16, 'architecture': 'arm64', 'family': 't4g'},
        't4g.2xlarge': {'vcpu': 8, 'memory_gb': 32, 'architecture': 'arm64', 'family': 't4g'},
    }

    def fetch(self) -> Dict[str, Dict]:
        """Fetch instance metadata"""
        print(f"\n🖥️  Loading instance metadata...")
        print(f"  ✓ Loaded {len(self.INSTANCE_METADATA)} instance types")
        return self.INSTANCE_METADATA


class RedisWriter:
    """Writes scraped data to Redis"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, ttl: int = 3600):
        """
        Initialize Redis writer

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self.ttl = ttl
        try:
            self.redis = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True
            )
            self.redis.ping()
            self.connected = True
            print(f"\n✅ Connected to Redis: {host}:{port}/{db}")
        except Exception as e:
            print(f"\n⚠️  Failed to connect to Redis: {e}")
            print(f"  → Data will only be saved to JSON file")
            self.redis = None
            self.connected = False

    def write_spot_risk_data(self, spot_data: Dict[str, Dict], region: str):
        """
        Write spot risk data to Redis

        Keys: spot_risk:{region}:{instance_type}
        TTL: 3600 seconds (1 hour)

        Args:
            spot_data: Dict of spot advisor data
            region: AWS region
        """
        if not self.connected:
            return

        print(f"\n📝 Writing spot risk data to Redis...")

        written_count = 0
        for key, data in spot_data.items():
            # Parse instance_type@az format
            instance_type, az = key.split('@')

            # Create Redis key
            redis_key = f"spot_risk:{region}:{instance_type}"

            # Prepare data
            risk_data = {
                "interrupt_rate": data['interrupt_rate'],
                "savings_vs_od": data.get('savings_vs_od', 0.65),
                "updated_at": datetime.now().isoformat(),
                "source": data.get('source', 'aws_spot_advisor')
            }

            # Write to Redis with TTL
            try:
                self.redis.setex(
                    redis_key,
                    self.ttl,
                    json.dumps(risk_data)
                )
                written_count += 1
            except Exception as e:
                print(f"  ⚠️  Failed to write {redis_key}: {e}")

        print(f"  ✓ Wrote {written_count} spot risk entries to Redis")

    def write_price_history(self, spot_data: Dict[str, Dict], region: str):
        """
        Write price history statistics to Redis

        Keys: spot_price_history:{region}:{family}
        TTL: 3600 seconds (1 hour)

        This aggregates data by instance family (e.g., c5, m5) to calculate
        regional demand indicators.

        Args:
            spot_data: Dict of spot advisor data
            region: AWS region
        """
        if not self.connected:
            return

        print(f"\n📊 Calculating price history statistics...")

        # Group by family
        family_stats: Dict[str, Dict] = {}

        for key, data in spot_data.items():
            instance_type, az = key.split('@')
            family = instance_type.split('.')[0]  # e.g., "c5.large" -> "c5"

            if family not in family_stats:
                family_stats[family] = {
                    'interrupt_rates': [],
                    'savings_rates': []
                }

            family_stats[family]['interrupt_rates'].append(data['interrupt_rate'])
            family_stats[family]['savings_rates'].append(data.get('savings_vs_od', 0.65))

        # Write aggregated statistics to Redis
        written_count = 0
        for family, stats in family_stats.items():
            redis_key = f"spot_price_history:{region}:{family}"

            # Calculate statistics
            interrupt_rates = stats['interrupt_rates']
            savings_rates = stats['savings_rates']

            price_history = {
                "current_avg_price": 0.028,  # Placeholder - would come from real pricing API
                "min_price": 0.020,
                "max_price": 0.040,
                "avg_interrupt_rate": sum(interrupt_rates) / len(interrupt_rates),
                "avg_savings": sum(savings_rates) / len(savings_rates),
                "sample_size": len(interrupt_rates),
                "last_updated": datetime.now().isoformat()
            }

            try:
                self.redis.setex(
                    redis_key,
                    self.ttl,
                    json.dumps(price_history)
                )
                written_count += 1
            except Exception as e:
                print(f"  ⚠️  Failed to write {redis_key}: {e}")

        print(f"  ✓ Wrote {written_count} price history entries to Redis")

    def write_instance_metadata(self, metadata: Dict[str, Dict]):
        """
        Write instance metadata to Redis

        Keys: instance_metadata:{instance_type}
        TTL: 86400 seconds (24 hours) - metadata changes rarely

        Args:
            metadata: Dict of instance metadata
        """
        if not self.connected:
            return

        print(f"\n🖥️  Writing instance metadata to Redis...")

        written_count = 0
        for instance_type, specs in metadata.items():
            redis_key = f"instance_metadata:{instance_type}"

            metadata_entry = {
                "vcpu": specs['vcpu'],
                "memory_gb": specs['memory_gb'],
                "architecture": specs['architecture'],
                "family": specs['family'],
                "updated_at": datetime.now().isoformat()
            }

            try:
                # Use longer TTL for metadata (24 hours)
                self.redis.setex(
                    redis_key,
                    86400,  # 24 hours
                    json.dumps(metadata_entry)
                )
                written_count += 1
            except Exception as e:
                print(f"  ⚠️  Failed to write {redis_key}: {e}")

        print(f"  ✓ Wrote {written_count} metadata entries to Redis")


def main():
    """Main scraper execution"""
    print("="*80)
    print("STATIC DATA SCRAPER - REDIS EDITION")
    print("="*80)
    print(f"Start Time: {datetime.now()}")
    print("="*80)

    # Initialize scrapers
    region = "ap-south-1"
    spot_scraper = SpotAdvisorScraper(region=region)
    metadata_scraper = InstanceMetadataScraper()

    # Fetch data
    spot_data = spot_scraper.fetch()
    metadata = metadata_scraper.fetch()

    # Write to Redis
    redis_writer = RedisWriter(
        host="localhost",
        port=6379,
        db=0,
        ttl=3600  # 1 hour
    )

    redis_writer.write_spot_risk_data(spot_data, region)
    redis_writer.write_price_history(spot_data, region)
    redis_writer.write_instance_metadata(metadata)

    # Also save to JSON as backup
    output_data = {
        'metadata': {
            'last_updated': datetime.now().isoformat(),
            'region': region,
            'source': 'AWS Spot Advisor + Hardcoded Metadata',
            'redis_ttl': redis_writer.ttl
        },
        'spot_advisor': spot_data,
        'instance_metadata': metadata
    }

    output_dir = Path(__file__).parent.parent / 'backend' / 'data'
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / 'static_intelligence.json'

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Saved backup to: {output_file}")
    print(f"  - Spot pools: {len(spot_data)}")
    print(f"  - Instance types: {len(metadata)}")
    print("="*80)
    print("\n📋 Redis Key Summary:")
    print(f"  - spot_risk:{region}:<instance_type> (TTL: 1 hour)")
    print(f"  - spot_price_history:{region}:<family> (TTL: 1 hour)")
    print(f"  - instance_metadata:<instance_type> (TTL: 24 hours)")
    print("="*80)


if __name__ == "__main__":
    main()
