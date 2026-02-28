"""
Instance Catalog Model (Enterprise Remediation Phase 1 - Task 1.2)
===================================================================

Database model for AWS EC2 instance type catalog.

Stores specifications fetched from ec2.describe_instance_types API.
Replaces hardcoded instance data with live AWS data.

Nightly refresh via instance_catalog_service.py.
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, Boolean, Index
from datetime import datetime
from backend.models.base import Base, generate_uuid


class InstanceCatalog(Base):
    """
    AWS EC2 Instance Type Catalog.

    Stores specifications for all instance types available in each region.
    Refreshed nightly from AWS EC2 API.
    """
    __tablename__ = "instance_catalog"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)

    # Instance identification
    instance_type = Column(String(50), nullable=False, index=True)  # e.g., "m5.large"
    region = Column(String(50), nullable=False, index=True, default='us-east-1')
    current_generation = Column(Boolean, nullable=False, default=True, index=True)

    # Architecture
    architecture = Column(String(20), nullable=False, default='x86_64', index=True)  # x86_64, arm64
    supported_architectures = Column(String(100), nullable=True)  # Comma-separated

    # vCPU
    vcpus = Column(Integer, nullable=False, default=0, index=True)
    cores = Column(Integer, nullable=False, default=0)
    threads_per_core = Column(Integer, nullable=False, default=1)

    # Memory
    memory_mib = Column(Integer, nullable=False, default=0)
    memory_gb = Column(Float, nullable=False, default=0.0, index=True)

    # Network
    network_performance = Column(String(100), nullable=True)  # e.g., "Up to 10 Gigabit"
    max_network_interfaces = Column(Integer, nullable=False, default=0)
    ipv4_addresses_per_interface = Column(Integer, nullable=False, default=0)
    ipv6_supported = Column(Boolean, nullable=False, default=False)
    ena_support = Column(String(20), nullable=True)  # required, supported, unsupported

    # Storage
    ebs_optimized = Column(String(20), nullable=True)  # default, supported, unsupported
    ebs_encryption_support = Column(String(20), nullable=True)  # supported, unsupported
    instance_storage_supported = Column(Boolean, nullable=False, default=False)
    instance_storage_type = Column(String(20), nullable=True)  # ssd, hdd, None
    instance_storage_total_gb = Column(Integer, nullable=False, default=0)

    # Processor
    hypervisor = Column(String(20), nullable=True)  # xen, nitro
    processor_manufacturer = Column(String(50), nullable=True)  # Intel, AMD, AWS
    sustained_clock_speed_ghz = Column(Float, nullable=True)

    # GPU
    gpu_count = Column(Integer, nullable=False, default=0)
    gpu_manufacturer = Column(String(50), nullable=True)  # NVIDIA, AMD, None
    gpu_memory_mib = Column(Integer, nullable=False, default=0)

    # Performance
    burstable_performance_supported = Column(Boolean, nullable=False, default=False)

    # Features
    auto_recovery_supported = Column(Boolean, nullable=False, default=False)
    hibernation_supported = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite indexes for performance
    __table_args__ = (
        Index("idx_instance_type_region", "instance_type", "region", unique=True),
        Index("idx_region_current_gen", "region", "current_generation"),
        Index("idx_region_arch", "region", "architecture"),
        Index("idx_vcpus_memory", "vcpus", "memory_gb"),
    )

    def __repr__(self):
        return (
            f"<InstanceCatalog(instance_type={self.instance_type}, "
            f"region={self.region}, vcpus={self.vcpus}, memory_gb={self.memory_gb})>"
        )

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "instance_type": self.instance_type,
            "region": self.region,
            "current_generation": self.current_generation,
            "architecture": self.architecture,
            "supported_architectures": self.supported_architectures,
            "vcpus": self.vcpus,
            "cores": self.cores,
            "threads_per_core": self.threads_per_core,
            "memory_mib": self.memory_mib,
            "memory_gb": self.memory_gb,
            "network_performance": self.network_performance,
            "max_network_interfaces": self.max_network_interfaces,
            "ipv4_addresses_per_interface": self.ipv4_addresses_per_interface,
            "ipv6_supported": self.ipv6_supported,
            "ena_support": self.ena_support,
            "ebs_optimized": self.ebs_optimized,
            "ebs_encryption_support": self.ebs_encryption_support,
            "instance_storage_supported": self.instance_storage_supported,
            "instance_storage_type": self.instance_storage_type,
            "instance_storage_total_gb": self.instance_storage_total_gb,
            "hypervisor": self.hypervisor,
            "processor_manufacturer": self.processor_manufacturer,
            "sustained_clock_speed_ghz": self.sustained_clock_speed_ghz,
            "gpu_count": self.gpu_count,
            "gpu_manufacturer": self.gpu_manufacturer,
            "gpu_memory_mib": self.gpu_memory_mib,
            "burstable_performance_supported": self.burstable_performance_supported,
            "auto_recovery_supported": self.auto_recovery_supported,
            "hibernation_supported": self.hibernation_supported,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }
