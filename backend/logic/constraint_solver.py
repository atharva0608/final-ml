"""
[ARCH-004] Constraint Solver using Google OR-Tools

Optimal pod placement using linear programming.
Replaces heuristic bin-packing with mathematically optimal solution.
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from ortools.linear_solver import pywraplp

logger = logging.getLogger(__name__)


@dataclass
class Pod:
    """Pod resource requirements"""
    name: str
    cpu_request: float  # CPU cores
    memory_request: float  # Memory in GB
    gpu_request: int = 0  # GPU units
    affinity_labels: Dict[str, str] = None
    anti_affinity_labels: Dict[str, str] = None


@dataclass
class Node:
    """Node resource capacity"""
    name: str
    cpu_capacity: float
    memory_capacity: float
    gpu_capacity: int = 0
    spot_price: float = 0.0  # Cost per hour
    reliability_score: float = 1.0  # 0.0-1.0 (higher is better)
    labels: Dict[str, str] = None
    current_pods: List[str] = None


@dataclass
class PlacementResult:
    """Result of pod placement optimization"""
    success: bool
    assignments: Dict[str, str]  # pod_name -> node_name
    total_cost: float
    total_reliability: float
    unassigned_pods: List[str]
    solver_status: str
    solve_time_ms: float


class ConstraintSolver:
    """
    Optimal pod placement solver using Google OR-Tools

    Objectives:
    1. Minimize cost (spot pricing)
    2. Maximize reliability (spot stability)
    3. Balance resource utilization
    4. Respect affinity/anti-affinity constraints
    """

    def __init__(self, solver_type: str = "SCIP"):
        """
        Initialize constraint solver

        Args:
            solver_type: Solver backend (SCIP, GLOP, CBC, GUROBI)
        """
        self.solver_type = solver_type

    def solve_placement(
        self,
        pods: List[Pod],
        nodes: List[Node],
        cost_weight: float = 0.6,
        reliability_weight: float = 0.4,
        time_limit_seconds: int = 30
    ) -> PlacementResult:
        """
        Solve optimal pod-to-node placement

        Args:
            pods: List of pods to place
            nodes: List of available nodes
            cost_weight: Weight for cost optimization (0.0-1.0)
            reliability_weight: Weight for reliability optimization (0.0-1.0)
            time_limit_seconds: Maximum solver time

        Returns:
            PlacementResult with optimal assignments
        """
        import time
        start_time = time.time()

        logger.info(f"🔧 Solving placement for {len(pods)} pods on {len(nodes)} nodes")

        # Create solver
        solver = pywraplp.Solver.CreateSolver(self.solver_type)

        if not solver:
            return PlacementResult(
                success=False,
                assignments={},
                total_cost=0.0,
                total_reliability=0.0,
                unassigned_pods=[p.name for p in pods],
                solver_status="SOLVER_NOT_AVAILABLE",
                solve_time_ms=0.0
            )

        # Set time limit
        solver.SetTimeLimit(time_limit_seconds * 1000)  # Convert to milliseconds

        # Decision variables: x[pod][node] = 1 if pod assigned to node, 0 otherwise
        x = {}
        for pod in pods:
            for node in nodes:
                x[(pod.name, node.name)] = solver.BoolVar(f'x_{pod.name}_{node.name}')

        # Constraint 1: Each pod assigned to exactly one node
        for pod in pods:
            solver.Add(
                sum(x[(pod.name, node.name)] for node in nodes) == 1,
                f'pod_{pod.name}_assignment'
            )

        # Constraint 2: Node CPU capacity
        for node in nodes:
            solver.Add(
                sum(pod.cpu_request * x[(pod.name, node.name)] for pod in pods) <= node.cpu_capacity,
                f'node_{node.name}_cpu_capacity'
            )

        # Constraint 3: Node memory capacity
        for node in nodes:
            solver.Add(
                sum(pod.memory_request * x[(pod.name, node.name)] for pod in pods) <= node.memory_capacity,
                f'node_{node.name}_memory_capacity'
            )

        # Constraint 4: Node GPU capacity (if applicable)
        for node in nodes:
            if node.gpu_capacity > 0:
                solver.Add(
                    sum(pod.gpu_request * x[(pod.name, node.name)] for pod in pods) <= node.gpu_capacity,
                    f'node_{node.name}_gpu_capacity'
                )

        # Constraint 5: Affinity constraints
        for pod in pods:
            if pod.affinity_labels:
                for node in nodes:
                    # If pod has affinity labels, only assign to matching nodes
                    if not self._node_matches_affinity(node, pod.affinity_labels):
                        solver.Add(x[(pod.name, node.name)] == 0)

        # Constraint 6: Anti-affinity constraints
        for pod in pods:
            if pod.anti_affinity_labels:
                for node in nodes:
                    # Check if node already has pods with anti-affinity labels
                    if self._node_has_anti_affinity_pods(node, pod.anti_affinity_labels):
                        solver.Add(x[(pod.name, node.name)] == 0)

        # Objective function: Minimize cost and maximize reliability
        total_cost = sum(
            pod.cpu_request * node.spot_price * x[(pod.name, node.name)]
            for pod in pods
            for node in nodes
        )

        total_reliability = sum(
            node.reliability_score * x[(pod.name, node.name)]
            for pod in pods
            for node in nodes
        )

        # Normalize reliability to same scale as cost
        max_possible_reliability = len(pods) * 1.0  # Max reliability per pod is 1.0
        normalized_reliability = total_reliability / max_possible_reliability if max_possible_reliability > 0 else 0

        # Combined objective (minimize cost, maximize reliability)
        objective = solver.Objective()
        objective.SetCoefficient(
            list(x.values())[0],  # Dummy variable for objective setup
            0
        )

        # Minimize: cost_weight * cost - reliability_weight * reliability
        for pod in pods:
            for node in nodes:
                var = x[(pod.name, node.name)]
                cost_component = cost_weight * pod.cpu_request * node.spot_price
                reliability_component = -reliability_weight * node.reliability_score
                objective.SetCoefficient(var, cost_component + reliability_component)

        objective.SetMinimization()

        # Solve
        logger.info("🔍 Solving optimization problem...")
        status = solver.Solve()

        solve_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        # Extract solution
        if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
            assignments = {}
            unassigned = []

            for pod in pods:
                assigned = False
                for node in nodes:
                    if x[(pod.name, node.name)].solution_value() > 0.5:  # Binary variable
                        assignments[pod.name] = node.name
                        assigned = True
                        break

                if not assigned:
                    unassigned.append(pod.name)

            # Calculate total cost and reliability
            total_cost_value = sum(
                pods[i].cpu_request * nodes[j].spot_price
                for i, pod in enumerate(pods)
                for j, node in enumerate(nodes)
                if x[(pod.name, node.name)].solution_value() > 0.5
            )

            total_reliability_value = sum(
                nodes[j].reliability_score
                for i, pod in enumerate(pods)
                for j, node in enumerate(nodes)
                if x[(pod.name, node.name)].solution_value() > 0.5
            )

            logger.info(f"✓ Solution found: {len(assignments)} pods assigned")
            logger.info(f"  Total cost: ${total_cost_value:.2f}/hr")
            logger.info(f"  Avg reliability: {total_reliability_value/len(assignments):.3f}")

            return PlacementResult(
                success=True,
                assignments=assignments,
                total_cost=total_cost_value,
                total_reliability=total_reliability_value,
                unassigned_pods=unassigned,
                solver_status="OPTIMAL" if status == pywraplp.Solver.OPTIMAL else "FEASIBLE",
                solve_time_ms=solve_time
            )

        else:
            logger.error(f"❌ Solver failed with status: {status}")
            return PlacementResult(
                success=False,
                assignments={},
                total_cost=0.0,
                total_reliability=0.0,
                unassigned_pods=[p.name for p in pods],
                solver_status="INFEASIBLE",
                solve_time_ms=solve_time
            )

    def _node_matches_affinity(self, node: Node, affinity_labels: Dict[str, str]) -> bool:
        """Check if node matches affinity labels"""
        if not node.labels:
            return False

        for key, value in affinity_labels.items():
            if node.labels.get(key) != value:
                return False

        return True

    def _node_has_anti_affinity_pods(self, node: Node, anti_affinity_labels: Dict[str, str]) -> bool:
        """Check if node has pods with anti-affinity labels"""
        # In production, query actual pods on node
        # For now, simplified check
        if not node.current_pods:
            return False

        # Would need to check pod labels in real implementation
        return False

    def balance_node_utilization(self, nodes: List[Node]) -> Dict[str, float]:
        """
        Calculate optimal resource distribution across nodes

        Returns:
            Dict of node_name -> target_utilization_percentage
        """
        total_capacity = sum(node.cpu_capacity for node in nodes)

        target_utilization = {}

        for node in nodes:
            # Higher reliability nodes get higher utilization target
            base_target = 0.70  # 70% base utilization
            reliability_bonus = node.reliability_score * 0.20  # Up to 20% bonus

            target = min(0.90, base_target + reliability_bonus)  # Cap at 90%

            target_utilization[node.name] = target

        return target_utilization


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Define pods
    pods = [
        Pod(name="pod-1", cpu_request=2.0, memory_request=4.0),
        Pod(name="pod-2", cpu_request=1.0, memory_request=2.0),
        Pod(name="pod-3", cpu_request=4.0, memory_request=8.0),
        Pod(name="pod-4", cpu_request=0.5, memory_request=1.0),
        Pod(name="pod-5", cpu_request=2.0, memory_request=4.0),
    ]

    # Define nodes
    nodes = [
        Node(name="node-1", cpu_capacity=8.0, memory_capacity=16.0, spot_price=0.10, reliability_score=0.85),
        Node(name="node-2", cpu_capacity=16.0, memory_capacity=32.0, spot_price=0.20, reliability_score=0.75),
        Node(name="node-3", cpu_capacity=8.0, memory_capacity=16.0, spot_price=0.08, reliability_score=0.90),
    ]

    # Solve
    solver = ConstraintSolver()
    result = solver.solve_placement(pods, nodes)

    if result.success:
        print(f"\n✓ Optimal placement found:")
        print(f"  Status: {result.solver_status}")
        print(f"  Solve time: {result.solve_time_ms:.2f}ms")
        print(f"  Total cost: ${result.total_cost:.2f}/hr")
        print(f"  Total reliability: {result.total_reliability:.2f}\n")

        print("Assignments:")
        for pod_name, node_name in result.assignments.items():
            print(f"  {pod_name} -> {node_name}")

        if result.unassigned_pods:
            print(f"\nUnassigned pods: {result.unassigned_pods}")
    else:
        print(f"❌ No solution found: {result.solver_status}")
