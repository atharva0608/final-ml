"""
Base Executor Interface

All executor implementations must implement this interface to ensure
compatibility with the Decision Engine.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class InstanceState:
    """Current state of an instance"""
    instance_id: str
    instance_type: str
    az: str
    lifecycle: str  # 'spot' or 'on-demand'
    state: str  # 'running', 'stopped', 'terminated'
    subnet_id: str
    vpc_id: str
    tags: Dict[str, str]


@dataclass
class UsageMetrics:
    """Usage metrics for an instance"""
    cpu_p95: float
    cpu_avg: float
    network_in_p95: Optional[float] = None
    network_out_p95: Optional[float] = None
    memory_p95: Optional[float] = None
    memory_avg: Optional[float] = None


@dataclass
class PoolInfo:
    """Information about a spot pool"""
    pool_id: str
    az: str
    instance_type: str
    current_spot_price: float
    discount_percent: float


@dataclass
class PricingSnapshot:
    """Current pricing information"""
    instance_type: str
    region: str
    on_demand_price: float
    pools: List[PoolInfo]


@dataclass
class TargetSpec:
    """Specification for launching a new instance"""
    instance_type: str
    az: str
    subnet_id: str
    pool_id: str
    ami_id: Optional[str] = None
    launch_template_id: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    lifecycle: str = 'spot'  # 'spot' or 'on-demand'


class Executor(ABC):
    """
    Base class for all executor implementations.

    Executors abstract infrastructure operations so the Decision Engine
    can remain cloud-agnostic.
    """

    @abstractmethod
    def get_instance_state(self, instance_id: str) -> InstanceState:
        """
        Get current state of an instance.

        Args:
            instance_id: Instance identifier

        Returns:
            InstanceState object with current state

        Raises:
            InstanceNotFoundException: If instance doesn't exist
        """
        pass

    @abstractmethod
    def get_usage_metrics(self, instance_id: str, window_minutes: int = 30) -> UsageMetrics:
        """
        Get usage metrics for an instance over a time window.

        Args:
            instance_id: Instance identifier
            window_minutes: Time window to collect metrics over

        Returns:
            UsageMetrics object with p95 and average values
        """
        pass

    @abstractmethod
    def get_pricing_snapshot(
        self,
        instance_type: str,
        region: str,
        pools: Optional[List[str]] = None
    ) -> PricingSnapshot:
        """
        Get current pricing for instance type across pools.

        Args:
            instance_type: EC2 instance type
            region: AWS region
            pools: Optional list of specific pool IDs to check

        Returns:
            PricingSnapshot with current prices
        """
        pass

    @abstractmethod
    def launch_instance(self, target_spec: TargetSpec) -> str:
        """
        Launch a new instance.

        Args:
            target_spec: Specification for new instance

        Returns:
            Instance ID of launched instance

        Raises:
            LaunchFailedException: If launch fails
        """
        pass

    @abstractmethod
    def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate an instance.

        Args:
            instance_id: Instance to terminate

        Returns:
            True if termination initiated successfully
        """
        pass

    @abstractmethod
    def wait_for_instance_state(
        self,
        instance_id: str,
        target_state: str,
        timeout_seconds: int = 300
    ) -> bool:
        """
        Wait for instance to reach target state.

        Args:
            instance_id: Instance to wait for
            target_state: Target state ('running', 'terminated', etc.)
            timeout_seconds: Max time to wait

        Returns:
            True if state reached, False if timeout
        """
        pass
