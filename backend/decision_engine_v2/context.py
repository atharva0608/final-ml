"""
Decision Context - The shared data object that flows through the pipeline

This is the "assembly line cart" that carries all information through
each stage of the decision pipeline.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class DecisionType(Enum):
    """Final decision types"""
    STAY = "STAY"              # Current instance is safe, do nothing
    SWITCH = "SWITCH"          # Switch to a better candidate
    DRAIN = "DRAIN"            # Gracefully drain (2-minute warning)
    EVACUATE = "EVACUATE"      # Emergency evacuation (immediate)
    UNKNOWN = "UNKNOWN"        # No decision yet


class SignalType(Enum):
    """AWS interrupt signals"""
    NONE = "NONE"
    REBALANCE = "REBALANCE_RECOMMENDATION"  # 2-minute warning
    TERMINATION = "INSTANCE_TERMINATION"    # Immediate termination


@dataclass
class ResourceRequirements:
    """Workload resource requirements"""
    vcpu: float
    memory_gb: float
    architecture: str = "x86_64"  # "x86_64" or "arm64"
    min_vcpu: Optional[float] = None  # Allow upsizing
    max_vcpu: Optional[float] = None  # Limit upsizing


@dataclass
class Candidate:
    """A spot pool candidate being evaluated"""
    instance_type: str
    availability_zone: str
    spot_price: float
    on_demand_price: float

    # Enriched during pipeline
    crash_probability: Optional[float] = None  # From ML model (0.0 to 1.0)
    historic_interrupt_rate: Optional[float] = None  # From scraper data
    discount_depth: Optional[float] = None  # Calculated: 1 - (spot/od)
    waste_cost: Optional[float] = None  # Bin packing waste
    yield_score: Optional[float] = None  # Final ranking metric

    # Metadata
    vcpu: Optional[int] = None
    memory_gb: Optional[float] = None
    architecture: Optional[str] = None

    # Filtering flags
    filtered_reason: Optional[str] = None  # Why this candidate was dropped
    is_valid: bool = True

    def __repr__(self):
        status = "✓" if self.is_valid else "✗"
        risk = f"Risk:{self.crash_probability:.2f}" if self.crash_probability else "Risk:?"
        price = f"${self.spot_price:.4f}"
        return f"{status} {self.instance_type}@{self.availability_zone} {price} {risk}"


@dataclass
class InputRequest:
    """Input request from user/K8s/test"""
    # Mode: "k8s" (live pods) or "test" (single instance check)
    mode: str = "test"

    # For K8s mode: Resource requirements
    resource_requirements: Optional[ResourceRequirements] = None

    # For test mode: Current instance to evaluate
    current_instance_type: Optional[str] = None
    current_availability_zone: Optional[str] = None
    current_instance_id: Optional[str] = None

    # Common
    region: str = "ap-south-1"

    def __repr__(self):
        if self.mode == "k8s":
            return f"K8sRequest(vcpu={self.resource_requirements.vcpu}, mem={self.resource_requirements.memory_gb}GB)"
        else:
            return f"TestRequest({self.current_instance_type}@{self.current_availability_zone})"


@dataclass
class DecisionContext:
    """
    The shared context object that flows through all pipeline stages

    Think of this as the "cart" on an assembly line. Each stage
    reads from it, modifies it, and passes it to the next stage.
    """
    # Input
    input_request: InputRequest

    # Data enriched during pipeline
    candidates: List[Candidate] = field(default_factory=list)

    # AWS signals (from metadata service or EventBridge)
    aws_signal: SignalType = SignalType.NONE
    signal_time: Optional[datetime] = None

    # Final decision
    final_decision: DecisionType = DecisionType.UNKNOWN
    selected_candidate: Optional[Candidate] = None
    decision_reason: str = ""

    # Stage execution trace (for debugging)
    execution_trace: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    pipeline_start_time: datetime = field(default_factory=datetime.now)
    pipeline_end_time: Optional[datetime] = None

    def log_stage(self, stage_name: str, message: str, data: Optional[Dict] = None):
        """Log execution trace for debugging"""
        self.execution_trace.append({
            'timestamp': datetime.now().isoformat(),
            'stage': stage_name,
            'message': message,
            'data': data or {}
        })

    def get_valid_candidates(self) -> List[Candidate]:
        """Get only candidates that passed all filters"""
        return [c for c in self.candidates if c.is_valid]

    def filter_candidate(self, candidate: Candidate, reason: str):
        """Mark a candidate as filtered out"""
        candidate.is_valid = False
        candidate.filtered_reason = reason

    def is_current_instance_safe(self) -> bool:
        """Check if current instance is in the safe list"""
        if not self.input_request.current_instance_type:
            return False

        current = f"{self.input_request.current_instance_type}@{self.input_request.current_availability_zone}"

        for candidate in self.get_valid_candidates():
            if f"{candidate.instance_type}@{candidate.availability_zone}" == current:
                # Check if crash probability is acceptable (< 0.85)
                if candidate.crash_probability and candidate.crash_probability < 0.85:
                    return True
        return False

    def __repr__(self):
        valid = len(self.get_valid_candidates())
        total = len(self.candidates)
        return (f"DecisionContext(mode={self.input_request.mode}, "
                f"candidates={valid}/{total}, "
                f"decision={self.final_decision.value}, "
                f"signal={self.aws_signal.value})")
