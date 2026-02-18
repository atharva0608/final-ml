"""
Network Resource Rules
======================
Classification rules for:
  • Load Balancers / ELB (idle detection)
  • Network Interfaces / ENI (orphaned)
  • Elastic IPs (unassociated)
  • NAT Gateways (high data transfer)
  • VPC (visibility)
  • VPC Endpoints (cost awareness)
  • Transit Gateways (visibility)
"""

from typing import Dict, Any, List, Optional, Tuple
from backend.Resource_rules import (
    RuleVerdict, AWS_MANAGED_ENI_KEYWORDS,
)


# ─── Load Balancers ───────────────────────────────────────────────────────────

def classify_load_balancer(
    has_active_targets: bool,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a load balancer.

    Rules:
        • No active (healthy/initial) targets → RISKY (ORPHANED)
        • Has active targets                  → None (skip — healthy)
    """
    if not has_active_targets:
        return RuleVerdict.RISKY, "No active targets attached"
    return None, None


# ─── Network Interfaces (ENI) ─────────────────────────────────────────────────

def classify_eni(
    status: str,
    description: str,
    requester_id: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a network interface.

    Rules:
        • Attached              → None (skip)
        • AWS-managed (Lambda, RDS, ECS, etc.) → None (skip)
        • Unattached + user-created → RISKY (ORPHANED / VPC clutter)
    """
    if status != 'available':
        return None, None  # Attached, skip

    desc_lower = description.lower()
    req_lower = requester_id.lower()

    # Skip AWS-managed ENIs
    if any(svc in desc_lower for svc in AWS_MANAGED_ENI_KEYWORDS) or 'amazon' in req_lower:
        return None, None

    return RuleVerdict.RISKY, "Unattached network interface (VPC clutter)"


# ─── Elastic IPs ──────────────────────────────────────────────────────────────

def classify_elastic_ip(
    has_association: bool,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an Elastic IP.

    Rules:
        • Not associated → SAFE  (95% certainty per zombie guide)
        • Associated     → None (skip — in use)
    """
    if not has_association:
        return RuleVerdict.SAFE, "Unattached Elastic IP (Safe to release)"
    return None, None


# ─── NAT Gateways ─────────────────────────────────────────────────────────────

DATA_TRANSFER_WARN_GB_PER_WEEK = 100

def classify_nat_gateway(
    weekly_gb_out: float,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a NAT Gateway by data transfer volume.

    Rules:
        • > 100 GB/week outbound → RISK (cost concern)
        • ≤ 100 GB/week         → None (skip — normal)
    """
    if weekly_gb_out > DATA_TRANSFER_WARN_GB_PER_WEEK:
        return RuleVerdict.RISK, f"High Data Transfer: {weekly_gb_out:.1f} GB/week"
    return None, None


# ─── VPC ──────────────────────────────────────────────────────────────────────

def classify_vpc(
    is_default: bool,
    state: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a VPC.

    Rules:
        • Default VPC     → None (skip)
        • Non-default, active → ACTIVE (visibility only)
    """
    if is_default:
        return None, None
    if state == 'available':
        return RuleVerdict.ACTIVE, "Active VPC"
    return None, None


# ─── VPC Endpoints ────────────────────────────────────────────────────────────

def classify_vpc_endpoint(
    ep_type: str,
    state: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a VPC Endpoint.

    Rules:
        • Interface endpoint (Active) → ACTIVE (costs ~$7.20/mo/AZ)
        • Gateway endpoint (Active)   → ACTIVE (free)
        • Not available               → None (skip)
    """
    if state != 'available':
        return None, None
    return RuleVerdict.ACTIVE, f"{ep_type} VPC Endpoint"


# ─── Transit Gateways ─────────────────────────────────────────────────────────

def classify_transit_gateway(
    state: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a Transit Gateway.

    Rules:
        • Active/Available → ACTIVE ($36/mo visibility)
        • Otherwise        → None (skip)
    """
    if state == 'available':
        return RuleVerdict.ACTIVE, "Active Transit Gateway"
    return None, None
