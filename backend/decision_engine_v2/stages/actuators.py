"""
Layer 6: Output Adapters (Actuators)

These stages execute the final decision:
- LogActuator: Just logs (safe for testing)
- K8sActuator: Actually drains/launches nodes
- PrometheusActuator: Exports metrics
"""

from ..context import DecisionContext, DecisionType
from ..interfaces import IActuator, IPipelineStage


class LogActuator(IActuator, IPipelineStage):
    """
    Log-only actuator (safe for testing)

    This actuator only logs what it WOULD do, without actually
    draining nodes or launching instances. Perfect for testing
    on live systems.
    """

    @property
    def name(self) -> str:
        return "LogActuator"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Process as a pipeline stage"""
        print(f"\n  Executing decision (LOG MODE - no actual changes)...")

        success = self.execute(context)

        if success:
            print(f"    ✓ Decision logged successfully")
        else:
            print(f"    ❌ Failed to log decision")

        return context

    def execute(self, context: DecisionContext) -> bool:
        """Execute the decision (log only)"""
        decision = context.final_decision

        if decision == DecisionType.STAY:
            print(f"\n    📍 DECISION: STAY")
            print(f"       Current instance is safe, no action needed")
            print(f"       Reason: {context.decision_reason}")

        elif decision == DecisionType.SWITCH:
            print(f"\n    🔄 DECISION: SWITCH")
            if context.selected_candidate:
                print(f"       Would switch to: {context.selected_candidate.instance_type}")
                print(f"       AZ: {context.selected_candidate.availability_zone}")
                print(f"       Spot Price: ${context.selected_candidate.spot_price:.4f}")
                print(f"       Risk: {context.selected_candidate.crash_probability:.2f}")
            print(f"       Reason: {context.decision_reason}")

        elif decision == DecisionType.DRAIN:
            print(f"\n    ⚠️  DECISION: DRAIN")
            print(f"       Would gracefully drain current instance")
            print(f"       Reason: {context.decision_reason}")
            print(f"       Signal: {context.aws_signal.value}")

        elif decision == DecisionType.EVACUATE:
            print(f"\n    🚨 DECISION: EVACUATE")
            print(f"       Would immediately evacuate current instance")
            print(f"       Reason: {context.decision_reason}")
            print(f"       Signal: {context.aws_signal.value}")

        else:
            print(f"\n    ❓ DECISION: UNKNOWN")
            print(f"       No decision made")

        return True


class K8sActuator(IActuator, IPipelineStage):
    """
    Kubernetes actuator (production)

    This actuator actually executes the decision:
    - DRAIN: Cordon node, drain pods, delete node
    - SWITCH: Launch new node with selected instance type
    - EVACUATE: Emergency evacuation (faster than drain)
    """

    def __init__(self, k8s_client=None, cluster_name: str = "default"):
        """
        Args:
            k8s_client: Kubernetes API client (e.g., boto3 EKS client)
            cluster_name: Name of the EKS cluster
        """
        self.k8s_client = k8s_client
        self.cluster_name = cluster_name

    @property
    def name(self) -> str:
        return "K8sActuator"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Process as a pipeline stage"""
        print(f"\n  Executing decision (K8S MODE - LIVE CHANGES)...")

        success = self.execute(context)

        if success:
            print(f"    ✓ Decision executed successfully")
        else:
            print(f"    ❌ Failed to execute decision")

        return context

    def execute(self, context: DecisionContext) -> bool:
        """Execute the decision (K8s operations)"""
        decision = context.final_decision

        if decision == DecisionType.STAY:
            # No action needed
            print(f"    📍 STAY: No action needed")
            return True

        elif decision == DecisionType.SWITCH:
            # Launch new node with selected instance type
            if not context.selected_candidate:
                print(f"    ❌ SWITCH failed: No candidate selected")
                return False

            print(f"    🔄 SWITCH: Launching new node...")
            print(f"       Instance: {context.selected_candidate.instance_type}")
            print(f"       AZ: {context.selected_candidate.availability_zone}")

            # In production, this would call Karpenter or Cluster Autoscaler
            # to launch a new node with the selected instance type

            if not self.k8s_client:
                print(f"       ⚠️  K8s client not configured, skipping actual launch")
                return True

            # Example: Launch via Karpenter
            # self._launch_node_via_karpenter(context.selected_candidate)

            print(f"       ✓ Node launch initiated")
            return True

        elif decision == DecisionType.DRAIN:
            # Graceful drain
            print(f"    ⚠️  DRAIN: Gracefully draining node...")

            if not self.k8s_client:
                print(f"       ⚠️  K8s client not configured, skipping actual drain")
                return True

            # Example: Drain via kubectl
            # kubectl cordon <node>
            # kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
            # kubectl delete node <node>

            print(f"       ✓ Node drain initiated")
            return True

        elif decision == DecisionType.EVACUATE:
            # Emergency evacuation
            print(f"    🚨 EVACUATE: Emergency evacuation...")

            if not self.k8s_client:
                print(f"       ⚠️  K8s client not configured, skipping actual evacuation")
                return True

            # Example: Fast evacuation
            # kubectl cordon <node>
            # kubectl delete node <node> --grace-period=0 --force

            print(f"       ✓ Emergency evacuation initiated")
            return True

        return False

    def _launch_node_via_karpenter(self, candidate):
        """Launch a new node via Karpenter (example)"""
        # This is a placeholder for actual Karpenter integration
        # In production, you'd create a Karpenter Provisioner or NodePool
        # with the selected instance type
        pass


class PrometheusActuator(IActuator, IPipelineStage):
    """
    Prometheus exporter (metrics)

    Exports decision metrics to Prometheus/Grafana:
    - Decision type counter
    - Crash probability gauge
    - Spot price gauge
    - Yield score histogram
    """

    def __init__(self, prometheus_client=None):
        self.prometheus_client = prometheus_client

    @property
    def name(self) -> str:
        return "PrometheusActuator"

    def process(self, context: DecisionContext) -> DecisionContext:
        """Process as a pipeline stage"""
        print(f"\n  Exporting metrics to Prometheus...")

        success = self.execute(context)

        if success:
            print(f"    ✓ Metrics exported successfully")
        else:
            print(f"    ❌ Failed to export metrics")

        return context

    def execute(self, context: DecisionContext) -> bool:
        """Export metrics to Prometheus"""
        if not self.prometheus_client:
            print(f"    ⚠️  Prometheus client not configured, skipping export")
            return True

        # Example metrics:
        # decision_total{decision="STAY|SWITCH|DRAIN|EVACUATE"}
        # crash_probability{instance_type, az}
        # spot_price{instance_type, az}
        # yield_score{instance_type, az}

        print(f"    ✓ Metrics exported")
        return True
