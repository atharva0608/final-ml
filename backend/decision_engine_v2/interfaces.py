"""
Interfaces for pluggable components

These define the contracts that all pipeline stages must follow.
This allows swapping implementations without changing the core logic.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from .context import DecisionContext, Candidate, SignalType


class IPipelineStage(ABC):
    """
    Base interface for all pipeline stages

    Each stage receives the DecisionContext, modifies it, and returns it.
    Stages are stateless and should not store data between executions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name for logging"""
        pass

    @property
    def skippable(self) -> bool:
        """Can this stage be skipped in config?"""
        return True

    @abstractmethod
    def process(self, context: DecisionContext) -> DecisionContext:
        """
        Process the context and return modified context

        Args:
            context: The decision context

        Returns:
            Modified decision context
        """
        pass

    def on_enter(self, context: DecisionContext):
        """Hook called before process()"""
        context.log_stage(self.name, f"Entering {self.name}")

    def on_exit(self, context: DecisionContext):
        """Hook called after process()"""
        context.log_stage(self.name, f"Exiting {self.name}")


class IInputAdapter(IPipelineStage):
    """
    Interface for input adapters (Layer 1)

    Input adapters normalize the request source and populate
    the initial candidate list.
    """

    @property
    def skippable(self) -> bool:
        return False  # Must have an input source

    @abstractmethod
    def fetch_candidates(self, context: DecisionContext) -> List[Candidate]:
        """
        Fetch initial list of candidates based on input request

        Returns:
            List of candidate spot pools to evaluate
        """
        pass


class IRiskModel(ABC):
    """
    Interface for ML risk models (Layer 3)

    Risk models predict crash probability for spot instances.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Model name for logging"""
        pass

    @abstractmethod
    def predict(self, candidates: List[Candidate]) -> Dict[str, float]:
        """
        Predict crash probability for each candidate

        Args:
            candidates: List of candidates to evaluate

        Returns:
            Dict mapping "instance_type@az" to crash_probability (0.0 to 1.0)
        """
        pass

    @abstractmethod
    def is_loaded(self) -> bool:
        """Check if model is ready to use"""
        pass


class IActuator(ABC):
    """
    Interface for actuators (Layer 6)

    Actuators execute the final decision (drain, switch, etc.)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Actuator name for logging"""
        pass

    @abstractmethod
    def execute(self, context: DecisionContext) -> bool:
        """
        Execute the final decision

        Args:
            context: Decision context with final_decision set

        Returns:
            True if execution succeeded, False otherwise
        """
        pass


class ISignalProvider(ABC):
    """
    Interface for AWS signal providers (Layer 5)

    Signal providers check for rebalance/termination notices.
    """

    @abstractmethod
    def check_signals(self, instance_id: Optional[str] = None) -> SignalType:
        """
        Check for AWS interrupt signals

        Args:
            instance_id: Instance ID to check (if None, check current instance)

        Returns:
            Signal type (NONE, REBALANCE, TERMINATION)
        """
        pass


class ISpotAdvisor(ABC):
    """
    Interface for historical spot data providers

    Provides historical interrupt rates for spot pools.
    """

    @abstractmethod
    def get_interrupt_rate(self, instance_type: str, az: str) -> float:
        """
        Get historical interrupt rate

        Args:
            instance_type: EC2 instance type
            az: Availability zone

        Returns:
            Historical interrupt rate (0.0 to 1.0)
        """
        pass


class IPriceProvider(ABC):
    """
    Interface for spot price providers

    Provides current spot and on-demand prices.
    """

    @abstractmethod
    def get_spot_price(self, instance_type: str, az: str) -> float:
        """Get current spot price"""
        pass

    @abstractmethod
    def get_on_demand_price(self, instance_type: str) -> float:
        """Get on-demand price"""
        pass


class IInstanceMetadata(ABC):
    """
    Interface for instance metadata providers

    Provides instance specifications (vCPU, memory, etc.)
    """

    @abstractmethod
    def get_metadata(self, instance_type: str) -> Dict[str, Any]:
        """
        Get instance metadata

        Returns:
            Dict with keys: vcpu, memory_gb, architecture, etc.
        """
        pass
