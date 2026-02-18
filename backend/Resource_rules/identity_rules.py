"""
Identity Resource Rules
=======================
Classification rules for:
  • IAM Users (dormant detection via console + access key activity)
  • IAM Access Keys (stale / risky keys)
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from backend.Resource_rules import (
    RuleVerdict, DORMANT_USER_DAYS, age_days,
)


# ─── IAM Users ────────────────────────────────────────────────────────────────

def classify_iam_user(
    days_inactive: int,
    has_active_keys: bool,
) -> Tuple[RuleVerdict, str]:
    """Classify an IAM user based on activity.

    Rules:
        • Inactive > 90 days + active access keys  → RISKY (service account risk)
        • Inactive > 90 days + no active keys       → SAFE  (dormant, safe to remove)
        • Active (< 90 days inactive)               → ACTIVE (skip)
    """
    if days_inactive <= DORMANT_USER_DAYS:
        return RuleVerdict.ACTIVE, "Active IAM user"

    if has_active_keys:
        # Active keys indicate potential service account — don't auto-delete
        return RuleVerdict.RISKY, f"Inactive for {days_inactive} days (Has active access keys - verify before deletion)"
    return RuleVerdict.SAFE, f"Inactive for {days_inactive} days (No active keys)"


# ─── IAM Access Keys ──────────────────────────────────────────────────────────

def classify_iam_key(
    key_status: str,
    days_since_last_used: Optional[int],
    days_since_creation: int,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an IAM access key.

    Rules:
        • Inactive key                             → None (skip)
        • Active + never used + > 90 days old      → SAFE  (forgotten key)
        • Active + not used > 90 days              → RISKY (stale but once-active)
        • Active + used recently                   → ACTIVE (skip)
    """
    if key_status != 'Active':
        return None, None  # Inactive keys, not relevant

    if days_since_last_used is None:
        # Never used
        if days_since_creation > DORMANT_USER_DAYS:
            return RuleVerdict.SAFE, f"Access key never used, created {days_since_creation} days ago"
        return RuleVerdict.ACTIVE, "Recently created access key"

    if days_since_last_used > DORMANT_USER_DAYS:
        return RuleVerdict.RISKY, f"Access key not used for {days_since_last_used} days"

    return RuleVerdict.ACTIVE, "Active access key"
