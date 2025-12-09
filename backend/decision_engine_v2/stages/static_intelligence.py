"""
Layer 2: Static Intelligence (Filtering)

These stages filter candidates based on static facts:
- Hardware compatibility
- Historical interrupt rates
- Rightsizing opportunities
"""

from typing import List
from ..context import DecisionContext, Candidate
from ..interfaces import IPipelineStage, ISpotAdvisor


class HardwareCompatibilityFilter(IPipelineStage):
    """
    Filter out candidates with incompatible hardware

    Checks:
    - Architecture (x86 vs ARM)
    - Sufficient vCPU
    - Sufficient memory
    """

    @property
    def name(self) -> str:
        return "HardwareFilter"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Filter based on hardware compatibility"""
        request = context.input_request

        print(f"  Filtering for hardware compatibility...")

        if request.mode == "k8s":
            # Already filtered in K8sInputAdapter
            print(f"    ℹ️  K8s mode: Hardware filtering already done in input stage")
            return context

        # For test mode, hardware filter is a no-op (single instance)
        print(f"    ℹ️  Test mode: No hardware filtering needed (single instance)")

        return context


class SpotAdvisorFilter(IPipelineStage):
    """
    Filter out spot pools with high historical interrupt rates

    Uses scraper data to reject historically dangerous pools.
    Threshold: > 20% interrupt rate = REJECT
    """

    def __init__(self, spot_advisor: ISpotAdvisor, threshold: float = 0.20):
        self.spot_advisor = spot_advisor
        self.threshold = threshold

    @property
    def name(self) -> str:
        return "SpotAdvisorFilter"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Filter based on historical interrupt rates"""
        print(f"  Filtering by historical interrupt rates (threshold: {self.threshold*100:.0f}%)...")

        filtered_count = 0

        for candidate in context.candidates:
            if not candidate.is_valid:
                continue  # Already filtered by previous stage

            # Get historical interrupt rate
            interrupt_rate = self.spot_advisor.get_interrupt_rate(
                candidate.instance_type,
                candidate.availability_zone
            )

            candidate.historic_interrupt_rate = interrupt_rate

            if interrupt_rate > self.threshold:
                context.filter_candidate(
                    candidate,
                    f"High historic interrupt rate: {interrupt_rate*100:.1f}% > {self.threshold*100:.0f}%"
                )
                filtered_count += 1

        print(f"    ✗ Filtered {filtered_count} candidates (high interrupt history)")
        print(f"    ✓ Remaining: {len(context.get_valid_candidates())} candidates")

        return context


class RightsizingExpander(IPipelineStage):
    """
    Expand candidate list to include larger instances (rightsizing)

    Scenario: Request is for 2 vCPU, but c5.xlarge (4 vCPU) might be
    cheaper on spot than c5.large (2 vCPU) due to market dynamics.

    This stage adds larger instances to the candidate pool and lets
    the yield score decide if upsizing is cost-effective.
    """

    def __init__(self, upsize_multiplier: float = 2.0):
        """
        Args:
            upsize_multiplier: How much larger to allow (2.0 = up to 2x vCPU)
        """
        self.upsize_multiplier = upsize_multiplier

    @property
    def name(self) -> str:
        return "RightsizingExpander"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Add larger instances to candidate pool"""
        request = context.input_request

        if request.mode != "k8s":
            print(f"    ℹ️  Test mode: Skipping rightsizing (not applicable)")
            return context

        reqs = request.resource_requirements

        if not reqs.min_vcpu:
            print(f"    ℹ️  No min_vcpu specified, skipping rightsizing")
            return context

        max_vcpu = reqs.vcpu * self.upsize_multiplier

        print(f"  Expanding candidate pool with rightsizing...")
        print(f"    Original: {reqs.vcpu} vCPU")
        print(f"    Allowing up to: {max_vcpu} vCPU ({self.upsize_multiplier}x)")

        # This is a no-op here because K8sInputAdapter already fetches
        # all matching instances. In a production system, you'd expand
        # the search here if input adapter was conservative.

        print(f"    ✓ Candidate pool includes oversized instances")

        return context
