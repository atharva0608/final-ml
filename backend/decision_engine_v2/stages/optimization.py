"""
Layer 4: Optimization Engine

These stages rank and sort candidates to find the best business value:
- Safety gate (drop dangerous candidates)
- Bin packing (calculate waste cost)
- TCO sorting (rank by total cost)
"""

from ..context import DecisionContext, Candidate
from ..interfaces import IPipelineStage


class SafetyGateFilter(IPipelineStage):
    """
    Filter out candidates with unacceptable crash probability

    This is the final safety check before ranking.
    Default threshold: 0.85 (85% crash probability = too dangerous)
    """

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold

    @property
    def name(self) -> str:
        return "SafetyGate"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Filter candidates above crash probability threshold"""
        print(f"  Safety gate: Filtering candidates with crash_probability > {self.threshold:.2f}...")

        filtered_count = 0

        for candidate in context.get_valid_candidates():
            if candidate.crash_probability is None:
                # No risk score - filter out to be safe
                context.filter_candidate(candidate, "No risk score available")
                filtered_count += 1
            elif candidate.crash_probability > self.threshold:
                context.filter_candidate(
                    candidate,
                    f"Crash probability too high: {candidate.crash_probability:.2f} > {self.threshold:.2f}"
                )
                filtered_count += 1

        print(f"    ✗ Filtered {filtered_count} candidates (too risky)")
        print(f"    ✓ Remaining: {len(context.get_valid_candidates())} candidates")

        return context


class BinPackingCalculator(IPipelineStage):
    """
    Calculate bin packing waste cost

    Scenario: Pod needs 2 vCPU, instance has 4 vCPU
    Waste: 2 vCPU unused
    Waste Cost: (2 vCPU / 4 vCPU) * Spot Price

    This only applies to K8s mode where we know the exact workload.
    """

    @property
    def name(self) -> str:
        return "BinPacking"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Calculate waste cost for oversized instances"""
        request = context.input_request

        if request.mode != "k8s":
            print(f"    ℹ️  Test mode: Skipping bin packing (not applicable)")
            # Set waste_cost to 0 for all candidates
            for candidate in context.candidates:
                candidate.waste_cost = 0.0
            return context

        reqs = request.resource_requirements

        print(f"  Calculating bin packing waste...")
        print(f"    Requested: {reqs.vcpu} vCPU")

        for candidate in context.get_valid_candidates():
            # Calculate waste
            wasted_vcpu = candidate.vcpu - reqs.vcpu
            waste_fraction = wasted_vcpu / candidate.vcpu if candidate.vcpu > 0 else 0

            # Waste cost = spot price * waste fraction
            candidate.waste_cost = candidate.spot_price * waste_fraction

        print(f"    ✓ Calculated waste cost for {len(context.get_valid_candidates())} candidates")

        return context


class TCOSorter(IPipelineStage):
    """
    Sort candidates by Total Cost of Ownership (TCO)

    TCO = Spot Price + Waste Cost

    Then calculate Yield Score:
    Yield Score = 100 * (1 - TCO/Max_TCO) * (1 - crash_probability)

    Higher score = better value (cheap + safe)
    """

    @property
    def name(self) -> str:
        return "TCOSorter"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Sort candidates by yield score"""
        print(f"  Calculating yield scores and ranking...")

        valid_candidates = context.get_valid_candidates()

        if not valid_candidates:
            print(f"    ⚠️  No valid candidates to rank")
            return context

        # Calculate TCO for each candidate
        for candidate in valid_candidates:
            # TCO = Spot Price + Waste Cost
            tco = candidate.spot_price + (candidate.waste_cost or 0)

            # Yield Score = 100 * (1 - TCO/Max_TCO) * (1 - crash_probability)
            # This balances cost efficiency with safety
            # Higher score = better value

            max_tco = max(c.spot_price + (c.waste_cost or 0) for c in valid_candidates)

            cost_efficiency = 1 - (tco / max_tco) if max_tco > 0 else 0
            safety = 1 - (candidate.crash_probability or 0.5)

            candidate.yield_score = 100 * cost_efficiency * safety

        # Sort by yield score (descending)
        context.candidates.sort(
            key=lambda c: c.yield_score if (c.is_valid and c.yield_score is not None) else -1,
            reverse=True
        )

        # Show top 5
        top_5 = [c for c in valid_candidates if c.yield_score is not None][:5]

        print(f"    Top 5 Candidates (by Yield Score):")
        for i, candidate in enumerate(top_5, 1):
            tco = candidate.spot_price + (candidate.waste_cost or 0)
            print(f"      #{i}: {candidate.instance_type}@{candidate.availability_zone}")
            print(f"          Spot: ${candidate.spot_price:.4f}, Waste: ${candidate.waste_cost or 0:.4f}")
            print(f"          TCO: ${tco:.4f}, Risk: {candidate.crash_probability:.2f}")
            print(f"          Yield Score: {candidate.yield_score:.1f}")

        print(f"    ✓ Ranked {len(valid_candidates)} candidates")

        return context
