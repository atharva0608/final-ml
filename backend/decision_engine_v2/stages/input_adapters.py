"""
Layer 1: Input Adapters

These stages normalize the input source and populate the initial candidate list.
"""

from typing import List, Dict, Any
from ..context import DecisionContext, Candidate, InputRequest
from ..interfaces import IInputAdapter, IPriceProvider, IInstanceMetadata


class SingleInstanceInputAdapter(IInputAdapter):
    """
    Input adapter for testing a single instance

    Use case: "I am running c5.large in ap-south-1a. Am I safe?"

    This adapter:
    1. Takes the current instance as the only candidate
    2. Fetches current spot/on-demand prices
    3. Enriches with instance metadata
    """

    def __init__(self,
                 price_provider: IPriceProvider,
                 metadata_provider: IInstanceMetadata):
        self.price_provider = price_provider
        self.metadata_provider = metadata_provider

    @property
    def name(self) -> str:
        return "SingleInstanceInput"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Process single instance test mode"""
        request = context.input_request

        if request.mode != "test":
            raise ValueError(f"SingleInstanceInputAdapter requires mode='test', got '{request.mode}'")

        if not request.current_instance_type or not request.current_availability_zone:
            raise ValueError("SingleInstanceInputAdapter requires current_instance_type and current_availability_zone")

        print(f"  Mode: Single Instance Test")
        print(f"  Instance: {request.current_instance_type}")
        print(f"  AZ: {request.current_availability_zone}")

        # Fetch candidates (just the current instance)
        candidates = self.fetch_candidates(context)
        context.candidates = candidates

        print(f"  ✓ Loaded {len(candidates)} candidate (current instance)")

        return context

    def fetch_candidates(self, context: DecisionContext) -> List[Candidate]:
        """Fetch the current instance as the only candidate"""
        request = context.input_request

        instance_type = request.current_instance_type
        az = request.current_availability_zone

        # Fetch prices
        spot_price = self.price_provider.get_spot_price(instance_type, az)
        od_price = self.price_provider.get_on_demand_price(instance_type)

        # Fetch metadata
        metadata = self.metadata_provider.get_metadata(instance_type)

        candidate = Candidate(
            instance_type=instance_type,
            availability_zone=az,
            spot_price=spot_price,
            on_demand_price=od_price,
            discount_depth=1 - (spot_price / od_price) if od_price > 0 else 0,
            vcpu=metadata.get('vcpu'),
            memory_gb=metadata.get('memory_gb'),
            architecture=metadata.get('architecture', 'x86_64'),
        )

        return [candidate]


class K8sInputAdapter(IInputAdapter):
    """
    Input adapter for Kubernetes mode

    Use case: "A pod needs 2 vCPU and 4GB RAM. Find best spot pool."

    This adapter:
    1. Reads resource requirements from K8s API (or request)
    2. Fetches ALL spot pools in the region that match requirements
    3. Enriches with prices and metadata
    """

    def __init__(self,
                 price_provider: IPriceProvider,
                 metadata_provider: IInstanceMetadata,
                 region: str = "ap-south-1"):
        self.price_provider = price_provider
        self.metadata_provider = metadata_provider
        self.region = region

    @property
    def name(self) -> str:
        return "K8sInput"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Process K8s mode"""
        request = context.input_request

        if request.mode != "k8s":
            raise ValueError(f"K8sInputAdapter requires mode='k8s', got '{request.mode}'")

        if not request.resource_requirements:
            raise ValueError("K8sInputAdapter requires resource_requirements")

        reqs = request.resource_requirements

        print(f"  Mode: Kubernetes")
        print(f"  Requirements: {reqs.vcpu} vCPU, {reqs.memory_gb}GB RAM, {reqs.architecture}")

        # Fetch candidates (all matching spot pools)
        candidates = self.fetch_candidates(context)
        context.candidates = candidates

        print(f"  ✓ Loaded {len(candidates)} candidates across {len(set(c.availability_zone for c in candidates))} AZs")

        return context

    def fetch_candidates(self, context: DecisionContext) -> List[Candidate]:
        """Fetch all spot pools that meet resource requirements"""
        reqs = context.input_request.resource_requirements

        # Get all instance types in the region (from metadata provider)
        # In production, this would query AWS EC2 API
        # For now, we'll use a hardcoded list of common types
        instance_types = self._get_instance_types_in_region()

        candidates = []
        availability_zones = self._get_availability_zones()

        for instance_type in instance_types:
            # Get metadata
            metadata = self.metadata_provider.get_metadata(instance_type)

            # Check hardware compatibility
            if metadata['vcpu'] < reqs.vcpu:
                continue  # Too small
            if metadata['memory_gb'] < reqs.memory_gb:
                continue  # Not enough RAM
            if metadata['architecture'] != reqs.architecture:
                continue  # Wrong architecture

            # Check max_vcpu limit (if set)
            if reqs.max_vcpu and metadata['vcpu'] > reqs.max_vcpu:
                continue  # Too large

            # Fetch prices for all AZs
            od_price = self.price_provider.get_on_demand_price(instance_type)

            for az in availability_zones:
                try:
                    spot_price = self.price_provider.get_spot_price(instance_type, az)

                    candidate = Candidate(
                        instance_type=instance_type,
                        availability_zone=az,
                        spot_price=spot_price,
                        on_demand_price=od_price,
                        discount_depth=1 - (spot_price / od_price) if od_price > 0 else 0,
                        vcpu=metadata['vcpu'],
                        memory_gb=metadata['memory_gb'],
                        architecture=metadata['architecture'],
                    )

                    candidates.append(candidate)

                except Exception as e:
                    # Spot price not available in this AZ
                    continue

        return candidates

    def _get_instance_types_in_region(self) -> List[str]:
        """Get list of instance types available in the region"""
        # Hardcoded for Mumbai (ap-south-1)
        # In production, query from AWS EC2 describe-instance-types
        return [
            # C5 family
            'c5.large', 'c5.xlarge', 'c5.2xlarge', 'c5.4xlarge', 'c5.9xlarge',
            'c5.12xlarge', 'c5.18xlarge', 'c5.24xlarge', 'c5.metal',
            # M5 family
            'm5.large', 'm5.xlarge', 'm5.2xlarge', 'm5.4xlarge', 'm5.8xlarge',
            'm5.12xlarge', 'm5.16xlarge', 'm5.24xlarge', 'm5.metal',
            # R5 family
            'r5.large', 'r5.xlarge', 'r5.2xlarge', 'r5.4xlarge', 'r5.8xlarge',
            'r5.12xlarge', 'r5.16xlarge', 'r5.24xlarge', 'r5.metal',
            # T3 family
            't3.micro', 't3.small', 't3.medium', 't3.large', 't3.xlarge', 't3.2xlarge',
        ]

    def _get_availability_zones(self) -> List[str]:
        """Get availability zones in the region"""
        # Hardcoded for Mumbai (ap-south-1)
        return ['ap-south-1a', 'ap-south-1b', 'ap-south-1c']
