"""
Compute Resource Rules
======================
Classification rules for:
  • EC2 Instances (running, stopped, managed, unmanaged)
  • Reserved Instances (utilization waste)
  • EKS Clusters (zombie detection)
  • ECS Clusters (empty / idle detection)
  • Auto Scaling Groups (zero-capacity detection)
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
from backend.Resource_rules import (
    RuleVerdict, SAFE_THRESHOLD_DAYS, age_days,
    check_tag_compliance, is_exempt_by_tags,
)


# ─── EC2 Instances ────────────────────────────────────────────────────────────

def classify_stopped_instance(
    stopped_days: int,
) -> Tuple[RuleVerdict, str]:
    """Classify a stopped EC2 instance.

    Rules:
        • Stopped > 30 days  → SAFE  (high confidence zombie)
        • Stopped ≤ 30 days  → STOPPED  (review needed)
    """
    if stopped_days > SAFE_THRESHOLD_DAYS:
        return RuleVerdict.SAFE, f"Stopped for {stopped_days} days (Safe to terminate)"
    return RuleVerdict.STOPPED, f"Instance stopped" + (f" ({stopped_days} days)" if stopped_days > 0 else "")


def classify_running_instance(
    instance_id: str,
    db_instance_ids: Set[str],
    tag_dict: Dict[str, str],
    required_tags: List[str],
) -> Tuple[RuleVerdict, str]:
    """Classify a running EC2 instance.

    Rules:
        • Managed by Spot Optimizer (in DB)         → ACTIVE
        • Tagged 'spot-optimizer:review' = 'true'    → UNAUTHORIZED (risky)
        • Missing required tags                      → NOT_COMPLIANT
        • Properly tagged, not managed               → ACTIVE (external workload)
        • No tag policy                              → ACTIVE (external workload)
    """
    # Managed instance
    if instance_id in db_instance_ids:
        return RuleVerdict.ACTIVE, "Managed by Spot Optimizer (Cluster Node)"

    # Explicitly flagged for review
    if tag_dict.get('spot-optimizer:review') == 'true':
        return RuleVerdict.UNAUTHORIZED, "Not managed by Spot Optimizer (Marked for review)"

    # Tag compliance check
    if required_tags:
        tag_keys = set(tag_dict.keys())
        missing = [rt for rt in required_tags if rt not in tag_keys]
        if missing:
            return RuleVerdict.NOT_COMPLIANT, f"Not managed (Missing tags: {', '.join(missing)})"
        return RuleVerdict.ACTIVE, "Not managed (Properly tagged external workload)"

    return RuleVerdict.ACTIVE, "Not managed (External workload)"


# ─── Reserved Instances ───────────────────────────────────────────────────────

def classify_reserved_instance(
    utilization: float,
    matched: int,
    count: int,
) -> Tuple[RuleVerdict, str]:
    """Classify an RI based on utilization.

    Rules:
        • Utilization < 100%  → RISKY  (partial / zero waste)
        • Utilization = 100%  → ACTIVE (fully consumed — not flagged)
    """
    if utilization < 1.0:
        return (
            RuleVerdict.RISKY,
            f"Utilization: {utilization*100:.1f}% ({matched}/{count} used)",
        )
    return RuleVerdict.ACTIVE, "Fully utilised"


# ─── EKS Clusters ─────────────────────────────────────────────────────────────

def classify_eks_cluster(
    nodegroup_count: int,
) -> Tuple[RuleVerdict, str]:
    """Classify an EKS cluster.

    Rules:
        • 0 nodegroups  → RISKY  (possible zombie, 65% certainty)
        • ≥ 1 nodegroup → ACTIVE
    """
    if nodegroup_count == 0:
        return RuleVerdict.RISKY, "EKS cluster with 0 nodegroups (possible zombie)"
    return RuleVerdict.ACTIVE, "Active EKS cluster"


# ─── ECS Clusters ─────────────────────────────────────────────────────────────

def classify_ecs_cluster(
    active_services: int,
    running_tasks: int,
    container_instances: int,
) -> Tuple[RuleVerdict, str]:
    """Classify an ECS cluster.

    Rules:
        • 0 services, 0 tasks, 0 instances  → SAFE  (empty, 85% certainty)
        • 0 running tasks                    → RISKY (zombie services)
        • Otherwise                          → ACTIVE
    """
    if active_services == 0 and running_tasks == 0 and container_instances == 0:
        return RuleVerdict.SAFE, "Empty ECS cluster (0 services, 0 tasks, 0 instances)"
    if running_tasks == 0:
        return RuleVerdict.RISKY, f"ECS cluster with 0 running tasks ({active_services} services defined)"
    return RuleVerdict.ACTIVE, f"Active ECS cluster ({running_tasks} tasks, {active_services} services)"


# ─── Auto Scaling Groups ──────────────────────────────────────────────────────

def classify_asg(
    desired: int,
    min_size: int,
    max_size: int,
    instance_count: int,
) -> Tuple[RuleVerdict, str]:
    """Classify an Auto Scaling Group.

    Rules:
        • min=0, max=0, desired=0  → SAFE  (fully disabled, 60% certainty)
        • desired=0, no instances  → RISKY (scaled to zero)
        • Otherwise                → ACTIVE
    """
    if desired == 0 and min_size == 0 and max_size == 0:
        return RuleVerdict.SAFE, "ASG with min=0, max=0, desired=0 (fully disabled)"
    if desired == 0 and instance_count == 0:
        return RuleVerdict.RISKY, "ASG scaled to zero (no running instances)"
    return RuleVerdict.ACTIVE, f"ASG with {instance_count} instances (desired: {desired})"
