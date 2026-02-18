"""
Storage Resource Rules
======================
Classification rules for:
  • EBS Volumes (attached, unattached, age-based)
  • EBS Snapshots (AMI-backed, orphaned)
  • S3 Buckets (empty, tag compliance)
  • S3 Lifecycle (missing policy on large buckets)
  • EFS File Systems (placeholder)
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
from backend.Resource_rules import (
    RuleVerdict, SAFE_THRESHOLD_DAYS, age_days,
    check_tag_compliance, is_exempt_by_tags,
)


# ─── EBS Volumes ──────────────────────────────────────────────────────────────

def classify_ebs_volume(
    state: str,
    created_at: datetime,
    tags: List[Dict],
    required_tags: List[str],
) -> Tuple[RuleVerdict, str]:
    """Classify an EBS volume.

    Rules:
        • In-use (attached)             → ACTIVE
        • Unattached > 30 days          → SAFE
        • Unattached ≤ 30 days          → RISKY (ORPHANED)
    """
    if state == 'in-use':
        return RuleVerdict.ACTIVE, "Attached to instance"

    # Unattached volume
    days_old = age_days(created_at)
    if days_old > SAFE_THRESHOLD_DAYS:
        return RuleVerdict.SAFE, "Unattached > 30 days (Safe)"
    return RuleVerdict.RISKY, "Unattached volume"


# ─── EBS Snapshots ────────────────────────────────────────────────────────────

def classify_snapshot(
    snap_id: str,
    volume_id: Optional[str],
    start_time: Optional[datetime],
    ami_snapshot_ids: Set[str],
    all_volume_ids: Set[str],
) -> Tuple[RuleVerdict, str]:
    """Classify an EBS snapshot.

    Rules:
        • Used by AMI                          → ACTIVE (protected, do not delete)
        • Source volume deleted > 30 days ago   → SAFE
        • Source volume deleted ≤ 30 days ago   → RISKY (ORPHANED)
        • Source volume still exists             → None (skip — not orphaned)
    """
    # AMI-protected
    if snap_id in ami_snapshot_ids:
        return RuleVerdict.ACTIVE, "Used by AMI (Do Not Delete)"

    # Orphaned: source volume is gone
    if volume_id and volume_id not in all_volume_ids:
        if start_time and age_days(start_time) > SAFE_THRESHOLD_DAYS:
            return RuleVerdict.SAFE, "Volume deleted > 30 days (Safe)"
        return RuleVerdict.RISKY, "Volume deleted (Orphaned Snapshot)"

    # Volume still exists → not orphaned, skip
    return None, None  # type: ignore[return-value]


# ─── S3 Buckets ───────────────────────────────────────────────────────────────

def classify_s3_bucket(
    is_empty: bool,
    tags: List[Dict],
    required_tags: List[str],
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an S3 bucket.

    Rules:
        • Empty bucket        → SAFE
        • Missing required tags → NOT_COMPLIANT
        • Otherwise            → None (skip — healthy)
    """
    if is_empty:
        return RuleVerdict.SAFE, "Empty bucket"

    is_compliant, missing = check_tag_compliance(tags, required_tags)
    if not is_compliant:
        return RuleVerdict.NOT_COMPLIANT, f"Missing tags: {', '.join(missing)}"

    return None, None  # Healthy, skip


# ─── S3 Lifecycle ─────────────────────────────────────────────────────────────

def classify_s3_lifecycle(
    has_lifecycle: bool,
    size_bytes: float,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an S3 bucket based on lifecycle policy.

    Rules:
        • No lifecycle policy AND size > 1 GB → REVIEW (LEGACY_UPGRADE)
        • Otherwise                           → None (skip)
    """
    ONE_GB = 1 * 1024 * 1024 * 1024
    if not has_lifecycle and size_bytes > ONE_GB:
        return RuleVerdict.REVIEW, "No Lifecycle Policy on >1GB Bucket"
    return None, None


# ─── EFS File Systems (placeholder) ──────────────────────────────────────────

def classify_efs(
    mount_target_count: int,
    size_bytes: float,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an EFS file system.

    Rules (placeholder — expand when scanner is added):
        • 0 mount targets  → RISKY (orphaned)
        • Otherwise        → ACTIVE
    """
    if mount_target_count == 0:
        return RuleVerdict.RISKY, "EFS with 0 mount targets (orphaned)"
    return RuleVerdict.ACTIVE, "Active EFS file system"
