"""
Instance Metadata Providers

Provides instance specifications (vCPU, memory, architecture, etc.)
"""

from typing import Dict, Any
from ..interfaces import IInstanceMetadata


class MockInstanceMetadata(IInstanceMetadata):
    """Mock instance metadata for testing"""

    # Static metadata for common instance types
    METADATA = {
        # C5 family (compute-optimized)
        'c5.large': {'vcpu': 2, 'memory_gb': 4, 'architecture': 'x86_64'},
        'c5.xlarge': {'vcpu': 4, 'memory_gb': 8, 'architecture': 'x86_64'},
        'c5.2xlarge': {'vcpu': 8, 'memory_gb': 16, 'architecture': 'x86_64'},
        'c5.4xlarge': {'vcpu': 16, 'memory_gb': 32, 'architecture': 'x86_64'},
        'c5.9xlarge': {'vcpu': 36, 'memory_gb': 72, 'architecture': 'x86_64'},
        'c5.12xlarge': {'vcpu': 48, 'memory_gb': 96, 'architecture': 'x86_64'},
        'c5.18xlarge': {'vcpu': 72, 'memory_gb': 144, 'architecture': 'x86_64'},
        'c5.24xlarge': {'vcpu': 96, 'memory_gb': 192, 'architecture': 'x86_64'},
        'c5.metal': {'vcpu': 96, 'memory_gb': 192, 'architecture': 'x86_64'},
        # M5 family (general-purpose)
        'm5.large': {'vcpu': 2, 'memory_gb': 8, 'architecture': 'x86_64'},
        'm5.xlarge': {'vcpu': 4, 'memory_gb': 16, 'architecture': 'x86_64'},
        'm5.2xlarge': {'vcpu': 8, 'memory_gb': 32, 'architecture': 'x86_64'},
        'm5.4xlarge': {'vcpu': 16, 'memory_gb': 64, 'architecture': 'x86_64'},
        'm5.8xlarge': {'vcpu': 32, 'memory_gb': 128, 'architecture': 'x86_64'},
        'm5.12xlarge': {'vcpu': 48, 'memory_gb': 192, 'architecture': 'x86_64'},
        'm5.16xlarge': {'vcpu': 64, 'memory_gb': 256, 'architecture': 'x86_64'},
        'm5.24xlarge': {'vcpu': 96, 'memory_gb': 384, 'architecture': 'x86_64'},
        'm5.metal': {'vcpu': 96, 'memory_gb': 384, 'architecture': 'x86_64'},
        # R5 family (memory-optimized)
        'r5.large': {'vcpu': 2, 'memory_gb': 16, 'architecture': 'x86_64'},
        'r5.xlarge': {'vcpu': 4, 'memory_gb': 32, 'architecture': 'x86_64'},
        'r5.2xlarge': {'vcpu': 8, 'memory_gb': 64, 'architecture': 'x86_64'},
        'r5.4xlarge': {'vcpu': 16, 'memory_gb': 128, 'architecture': 'x86_64'},
        'r5.8xlarge': {'vcpu': 32, 'memory_gb': 256, 'architecture': 'x86_64'},
        'r5.12xlarge': {'vcpu': 48, 'memory_gb': 384, 'architecture': 'x86_64'},
        'r5.16xlarge': {'vcpu': 64, 'memory_gb': 512, 'architecture': 'x86_64'},
        'r5.24xlarge': {'vcpu': 96, 'memory_gb': 768, 'architecture': 'x86_64'},
        'r5.metal': {'vcpu': 96, 'memory_gb': 768, 'architecture': 'x86_64'},
        # T3 family (burstable)
        't3.micro': {'vcpu': 2, 'memory_gb': 1, 'architecture': 'x86_64'},
        't3.small': {'vcpu': 2, 'memory_gb': 2, 'architecture': 'x86_64'},
        't3.medium': {'vcpu': 2, 'memory_gb': 4, 'architecture': 'x86_64'},
        't3.large': {'vcpu': 2, 'memory_gb': 8, 'architecture': 'x86_64'},
        't3.xlarge': {'vcpu': 4, 'memory_gb': 16, 'architecture': 'x86_64'},
        't3.2xlarge': {'vcpu': 8, 'memory_gb': 32, 'architecture': 'x86_64'},
    }

    def get_metadata(self, instance_type: str) -> Dict[str, Any]:
        """Get instance metadata"""
        return self.METADATA.get(instance_type, {
            'vcpu': 2,
            'memory_gb': 4,
            'architecture': 'x86_64'
        })


class AWSInstanceMetadata(IInstanceMetadata):
    """Real AWS metadata provider"""

    def __init__(self, region: str = "ap-south-1"):
        self.region = region
        # In production: self.ec2_client = boto3.client('ec2', region_name=region)

    def get_metadata(self, instance_type: str) -> Dict[str, Any]:
        """Get real instance metadata from AWS"""
        # In production:
        # response = self.ec2_client.describe_instance_types(
        #     InstanceTypes=[instance_type]
        # )
        # type_info = response['InstanceTypes'][0]
        # return {
        #     'vcpu': type_info['VCpuInfo']['DefaultVCpus'],
        #     'memory_gb': type_info['MemoryInfo']['SizeInMiB'] / 1024,
        #     'architecture': type_info['ProcessorInfo']['SupportedArchitectures'][0]
        # }

        # Fall back to mock
        return MockInstanceMetadata().get_metadata(instance_type)
