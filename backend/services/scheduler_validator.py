"""
Scheduler Validation Service
============================
Simulates kube-scheduler behavior to verify if pods can be successfully
placed on target nodes before a node drain is initiated.
"""

import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    is_valid: bool
    reason: Optional[str] = None
    failed_pods: List[str] = None

class SchedulerValidator:
    """
    Simulates pod placement logic (filtering/scoring) to prevent 'Pending' pods.
    Checks:
    - Resource Capacity (CPU, Memory, ENI/IPs)
    - Node Affinity (requiredDuringSchedulingIgnoredDuringExecution)
    - Pod Anti-Affinity (topology constraints)
    - Taints and Tolerations
    """

    def __init__(self, cluster_id: str):
        self.cluster_id = cluster_id

    def validate_placement(self, pods: List[Dict[str, Any]], nodes: List[Dict[str, Any]]) -> ValidationResult:
        """
        Validates that all 'pods' can fit into the provided 'nodes'.
        
        Args:
            pods: List of pod dictionaries (with requests, affinity, tolerations)
            nodes: List of node dictionaries (with allocatable resources, taints, existing pods)
            
        Returns:
            ValidationResult indicating success or failure with reasons.
        """
        if not pods:
            return ValidationResult(is_valid=True)
            
        if not nodes:
            return ValidationResult(is_valid=False, reason="No target nodes available for placement")

        # 1. Prepare simulated nodes (copy original nodes to track remaining capacity)
        simulated_nodes = []
        for n in nodes:
            simulated_nodes.append({
                "name": n["name"],
                "cpu_remaining": n.get("allocatable_cpu", 0),
                "mem_remaining": n.get("allocatable_memory", 0),
                "ip_remaining": n.get("ip_available", 0),
                "pods_remaining": n.get("max_pods", 110) - n.get("current_pod_count", 0),
                "labels": n.get("labels", {}),
                "taints": n.get("taints", []),
                "existing_pod_labels": n.get("existing_pod_labels", []) # List of dicts
            })

        failed_pods = []
        
        # 2. Iterate through pods and attempt to find a valid node for each
        # We sort pods by resource requests (descending) to improve bin-packing success probability
        sorted_pods = sorted(pods, key=lambda x: x.get("cpu_request", 0) + x.get("memory_request", 0) / 1024, reverse=True)

        for pod in sorted_pods:
            found_node = False
            pod_name = f"{pod.get('namespace')}/{pod.get('name')}"
            
            # Filter nodes for this specific pod
            eligible_nodes = self._filter_nodes(pod, simulated_nodes)
            
            if not eligible_nodes:
                failed_pods.append(pod_name)
                continue
                
            # Pick the "best" node among eligible (simple Best-Fit for simulation)
            eligible_nodes.sort(key=lambda x: (x["cpu_remaining"], x["mem_remaining"]))
            
            for node in eligible_nodes:
                # Double-check capacity (redundant but safe)
                if self._check_capacity(pod, node):
                    # "Place" the pod on the node
                    node["cpu_remaining"] -= pod.get("cpu_request", 0)
                    node["mem_remaining"] -= pod.get("memory_request", 0)
                    node["ip_remaining"] -= 1
                    node["pods_remaining"] -= 1
                    node["existing_pod_labels"].append(pod.get("labels", {}))
                    found_node = True
                    break
            
            if not found_node:
                failed_pods.append(pod_name)

        if failed_pods:
            return ValidationResult(
                is_valid=False, 
                reason=f"Failed to place {len(failed_pods)} pods: {', '.join(failed_pods[:3])}...",
                failed_pods=failed_pods
            )

        return ValidationResult(is_valid=True)

    def _filter_nodes(self, pod: Dict[str, Any], nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Applies K8s-like filtering (Taints, Affinities, Capacity)."""
        eligible = []
        for node in nodes:
            # A. Check Taints/Tolerations
            if not self._check_tolerations(pod, node):
                continue
                
            # B. Check Node Affinity
            if not self._check_node_affinity(pod, node):
                continue
                
            # C. Check Pod Anti-Affinity
            if not self._check_pod_anti_affinity(pod, node):
                continue
                
            # D. Check Capacity
            if not self._check_capacity(pod, node):
                continue
                
            eligible.append(node)
        return eligible

    def _check_tolerations(self, pod: Dict[str, Any], node: Dict[str, Any]) -> bool:
        tolerations = pod.get("tolerations", [])
        for taint in node.get("taints", []):
            match = False
            for tol in tolerations:
                if tol.get("key") == taint.get("key") and (tol.get("operator") == "Exists" or tol.get("value") == taint.get("value")):
                    match = True
                    break
            if not match and taint.get("effect") in ["NoSchedule", "NoExecute"]:
                return False
        return True

    def _check_node_affinity(self, pod: Dict[str, Any], node: Dict[str, Any]) -> bool:
        affinity = pod.get("node_affinity_required", {})
        if not affinity:
            return True
            
        # Simplistic node selector match (matchExpressions/matchFields)
        # In a real implementation, we'd use a more robust matcher.
        node_labels = node.get("labels", {})
        for term in affinity.get("nodeSelectorTerms", []):
            term_match = True
            for expr in term.get("matchExpressions", []):
                key = expr.get("key")
                op = expr.get("operator")
                vals = expr.get("values", [])
                
                label_val = node_labels.get(key)
                if op == "In":
                    if label_val not in vals:
                        term_match = False; break
                elif op == "NotIn":
                    if label_val in vals:
                        term_match = False; break
                elif op == "Exists":
                    if key not in node_labels:
                        term_match = False; break
                elif op == "DoesNotExist":
                    if key in node_labels:
                        term_match = False; break
            if term_match:
                return True
        return False

    def _check_pod_anti_affinity(self, pod: Dict[str, Any], node: Dict[str, Any]) -> bool:
        anti_affinity = pod.get("pod_anti_affinity_required", [])
        if not anti_affinity:
            return True
            
        # Check if any pod on this node violates anti-affinity
        for term in anti_affinity:
            selector = term.get("labelSelector", {})
            # Simplified selector match
            match_labels = selector.get("matchLabels", {})
            
            for existing_labels in node.get("existing_pod_labels", []):
                if all(existing_labels.get(k) == v for k, v in match_labels.items()):
                    return False # Conflict!
        return True

    def _check_capacity(self, pod: Dict[str, Any], node: Dict[str, Any]) -> bool:
        if node["cpu_remaining"] < pod.get("cpu_request", 0):
            return False
        if node["mem_remaining"] < pod.get("memory_request", 0):
            return False
        if node["ip_remaining"] < 1:
            return False
        if node["pods_remaining"] < 1:
            return False
        return True
