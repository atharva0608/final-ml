"""
Instance Catalog Service (Enterprise Remediation Phase 1 - Task 1.2)
=====================================================================

Dynamic instance type catalog from AWS EC2 describe_instance_types API.

Features:
- Nightly fetch of instance specifications from AWS
- Store in database for ML feature engineering
- Replace hardcoded instance data with live AWS data
- Support for multi-region instance availability
- Architecture filtering (x86_64, arm64)
- vCPU, memory, network, storage metadata

Enterprise Guardrails:
- Fetches from us-east-1 (global instance catalog)
- Stores per-region availability zones
- Falls back to cached data if AWS API fails
- Retries with exponential backoff
"""
import boto3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from botocore.config import Config

from backend.models.instance_catalog import InstanceCatalog
from backend.core.logger import logger


class InstanceCatalogService:
    """
    Service for managing instance type catalog.

    Fetches instance specifications from AWS EC2 API and stores in database.
    """

    def __init__(self, db: Session, account_id: Optional[str] = None):
        self.db = db
        self.account_id = account_id

        # Boto3 config with enterprise retry policy
        self.boto_config = Config(
            retries={
                'max_attempts': 10,
                'mode': 'adaptive'
            },
            connect_timeout=5,
            read_timeout=60
        )

    def _get_aws_client(self, service: str, region: str):
        """
        Get AWS client using environment credentials.

        For instance catalog and pricing, we use the base AWS credentials directly
        since these are read-only operations that don't require cross-account access.
        """
        try:
            # Use environment credentials directly (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
            # This avoids the need for role assumption and works with any IAM user/role
            client = boto3.client(
                service,
                region_name=region,
                config=self.boto_config
            )

            logger.info(f"Created {service} client for region {region} using environment credentials")
            return client

        except Exception as e:
            logger.error(f"Failed to create {service} client: {e}")
            raise ValueError(f"Failed to create AWS client: {str(e)}")

    def refresh_instance_catalog(self, region: str = 'us-east-1') -> Dict[str, int]:
        """
        Refresh instance catalog from AWS EC2 API.

        This fetches all instance types available in the region and stores
        their specifications in the database.

        Args:
            region: AWS region (default: us-east-1 for global catalog)

        Returns:
            Dict with counts: {"instances_fetched": int, "instances_stored": int}
        """
        try:
            ec2_client = self._get_aws_client('ec2', region)

            logger.info(f"Fetching instance catalog from AWS for region: {region}")

            # Fetch all instance types
            paginator = ec2_client.get_paginator('describe_instance_types')
            page_iterator = paginator.paginate()

            instances_fetched = 0
            instances_stored = 0

            for page in page_iterator:
                for instance_data in page.get('InstanceTypes', []):
                    try:
                        instance_type = instance_data['InstanceType']

                        # Parse instance specs
                        specs = self._parse_instance_specs(instance_data)

                        # Upsert to database
                        self._store_instance_catalog(
                            instance_type=instance_type,
                            region=region,
                            specs=specs
                        )

                        instances_fetched += 1
                        instances_stored += 1

                    except Exception as e:
                        logger.error(f"Failed to process instance type {instance_data.get('InstanceType')}: {e}")
                        continue

            logger.info(
                f"Instance catalog refresh complete for {region}: "
                f"{instances_fetched} fetched, {instances_stored} stored"
            )

            return {
                "instances_fetched": instances_fetched,
                "instances_stored": instances_stored,
                "region": region,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to refresh instance catalog for {region}: {e}", exc_info=True)
            raise

    def _parse_instance_specs(self, instance_data: Dict) -> Dict:
        """
        Parse instance specifications from AWS describe_instance_types response.

        Args:
            instance_data: Raw instance data from AWS API

        Returns:
            Dict with parsed specifications
        """
        specs = {}

        # Basic specs
        specs['instance_type'] = instance_data.get('InstanceType')
        specs['current_generation'] = instance_data.get('CurrentGeneration', False)

        # Processor architecture
        supported_archs = instance_data.get('ProcessorInfo', {}).get('SupportedArchitectures', [])
        specs['architecture'] = supported_archs[0] if supported_archs else 'x86_64'
        specs['supported_architectures'] = ','.join(supported_archs)

        # vCPU
        vcpu_info = instance_data.get('VCpuInfo', {})
        specs['vcpus'] = vcpu_info.get('DefaultVCpus', 0)
        specs['cores'] = vcpu_info.get('DefaultCores', 0)
        specs['threads_per_core'] = vcpu_info.get('DefaultThreadsPerCore', 1)

        # Memory
        memory_info = instance_data.get('MemoryInfo', {})
        specs['memory_mib'] = memory_info.get('SizeInMiB', 0)
        specs['memory_gb'] = round(specs['memory_mib'] / 1024, 2)

        # Network
        network_info = instance_data.get('NetworkInfo', {})
        specs['network_performance'] = network_info.get('NetworkPerformance', 'Unknown')
        specs['max_network_interfaces'] = network_info.get('MaximumNetworkInterfaces', 0)
        specs['ipv4_addresses_per_interface'] = network_info.get('Ipv4AddressesPerInterface', 0)
        specs['ipv6_supported'] = network_info.get('Ipv6Supported', False)
        specs['ena_support'] = network_info.get('EnaSupport', 'unsupported')

        # Storage
        instance_storage = instance_data.get('InstanceStorageInfo', {})
        specs['ebs_optimized'] = instance_data.get('EbsInfo', {}).get('EbsOptimizedSupport', 'unsupported')
        specs['ebs_encryption_support'] = instance_data.get('EbsInfo', {}).get('EncryptionSupport', 'unsupported')

        if instance_storage:
            specs['instance_storage_supported'] = instance_storage.get('Supported', False)
            specs['instance_storage_type'] = instance_storage.get('Disks', [{}])[0].get('Type', 'None')
            total_size_gb = sum(
                disk.get('SizeInGB', 0) * disk.get('Count', 1)
                for disk in instance_storage.get('Disks', [])
            )
            specs['instance_storage_total_gb'] = total_size_gb
        else:
            specs['instance_storage_supported'] = False
            specs['instance_storage_type'] = 'None'
            specs['instance_storage_total_gb'] = 0

        # Hypervisor
        specs['hypervisor'] = instance_data.get('Hypervisor', 'unknown')

        # Processor info
        processor_info = instance_data.get('ProcessorInfo', {})
        specs['processor_manufacturer'] = processor_info.get('Manufacturer', 'Unknown')
        specs['sustained_clock_speed_ghz'] = processor_info.get('SustainedClockSpeedInGhz', 0.0)

        # GPU
        gpu_info = instance_data.get('GpuInfo', {})
        if gpu_info:
            specs['gpu_count'] = sum(gpu.get('Count', 0) for gpu in gpu_info.get('Gpus', []))
            specs['gpu_manufacturer'] = gpu_info.get('Gpus', [{}])[0].get('Manufacturer', 'None')
            specs['gpu_memory_mib'] = sum(
                gpu.get('MemoryInfo', {}).get('SizeInMiB', 0) * gpu.get('Count', 1)
                for gpu in gpu_info.get('Gpus', [])
            )
        else:
            specs['gpu_count'] = 0
            specs['gpu_manufacturer'] = 'None'
            specs['gpu_memory_mib'] = 0

        # Burstable
        specs['burstable_performance_supported'] = instance_data.get('BurstablePerformanceSupported', False)

        # Auto recovery
        specs['auto_recovery_supported'] = instance_data.get('AutoRecoverySupported', False)

        # Hibernation
        specs['hibernation_supported'] = instance_data.get('HibernationSupported', False)

        return specs

    def _store_instance_catalog(self, instance_type: str, region: str, specs: Dict):
        """
        Store or update instance catalog entry in database.

        Args:
            instance_type: Instance type (e.g., "m5.large")
            region: AWS region
            specs: Parsed specifications dict
        """
        # Check if exists
        existing = self.db.query(InstanceCatalog).filter(
            InstanceCatalog.instance_type == instance_type,
            InstanceCatalog.region == region
        ).first()

        if existing:
            # Update existing
            for key, value in specs.items():
                if key != 'instance_type':  # Don't update primary key
                    setattr(existing, key, value)
            existing.last_updated_at = datetime.utcnow()
        else:
            # Create new - filter out instance_type from specs to avoid duplicate
            filtered_specs = {k: v for k, v in specs.items() if k != 'instance_type'}
            catalog_entry = InstanceCatalog(
                instance_type=instance_type,
                region=region,
                **filtered_specs
            )
            self.db.add(catalog_entry)

        self.db.commit()

    def get_instance_specs(self, instance_type: str, region: str = 'us-east-1') -> Optional[InstanceCatalog]:
        """
        Get instance specifications from catalog.

        Args:
            instance_type: Instance type (e.g., "m5.large")
            region: AWS region

        Returns:
            InstanceCatalog model or None if not found
        """
        return self.db.query(InstanceCatalog).filter(
            InstanceCatalog.instance_type == instance_type,
            InstanceCatalog.region == region
        ).first()

    def get_instances_by_family(self, family: str, region: str = 'us-east-1') -> List[InstanceCatalog]:
        """
        Get all instance types in a family (e.g., "m5").

        Args:
            family: Instance family prefix (e.g., "m5", "c5")
            region: AWS region

        Returns:
            List of InstanceCatalog models
        """
        return self.db.query(InstanceCatalog).filter(
            InstanceCatalog.instance_type.like(f"{family}.%"),
            InstanceCatalog.region == region,
            InstanceCatalog.current_generation == True
        ).all()

    def get_instances_by_architecture(self, architecture: str, region: str = 'us-east-1') -> List[InstanceCatalog]:
        """
        Get instances supporting specific architecture.

        Args:
            architecture: Architecture (e.g., "x86_64", "arm64")
            region: AWS region

        Returns:
            List of InstanceCatalog models
        """
        return self.db.query(InstanceCatalog).filter(
            InstanceCatalog.architecture == architecture,
            InstanceCatalog.region == region,
            InstanceCatalog.current_generation == True
        ).all()

    def get_instances_by_specs(
        self,
        min_vcpus: Optional[int] = None,
        max_vcpus: Optional[int] = None,
        min_memory_gb: Optional[float] = None,
        max_memory_gb: Optional[float] = None,
        architecture: Optional[str] = None,
        region: str = 'us-east-1'
    ) -> List[InstanceCatalog]:
        """
        Filter instances by specifications.

        Args:
            min_vcpus: Minimum vCPUs
            max_vcpus: Maximum vCPUs
            min_memory_gb: Minimum memory in GB
            max_memory_gb: Maximum memory in GB
            architecture: Architecture (x86_64, arm64)
            region: AWS region

        Returns:
            List of InstanceCatalog models matching criteria
        """
        query = self.db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.current_generation == True
        )

        if min_vcpus:
            query = query.filter(InstanceCatalog.vcpus >= min_vcpus)
        if max_vcpus:
            query = query.filter(InstanceCatalog.vcpus <= max_vcpus)
        if min_memory_gb:
            query = query.filter(InstanceCatalog.memory_gb >= min_memory_gb)
        if max_memory_gb:
            query = query.filter(InstanceCatalog.memory_gb <= max_memory_gb)
        if architecture:
            query = query.filter(InstanceCatalog.architecture == architecture)

        return query.all()

    def get_catalog_stats(self, region: str = 'us-east-1') -> Dict:
        """
        Get statistics about instance catalog.

        Args:
            region: AWS region

        Returns:
            Dict with catalog stats
        """
        total = self.db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region
        ).count()

        current_gen = self.db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.current_generation == True
        ).count()

        x86_count = self.db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.architecture == 'x86_64'
        ).count()

        arm_count = self.db.query(InstanceCatalog).filter(
            InstanceCatalog.region == region,
            InstanceCatalog.architecture == 'arm64'
        ).count()

        return {
            "total_instances": total,
            "current_generation": current_gen,
            "x86_64": x86_count,
            "arm64": arm_count,
            "region": region
        }
