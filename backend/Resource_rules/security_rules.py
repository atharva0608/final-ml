"""
Security Resource Rules
=======================
Classification rules for:
  • KMS Keys (disabled / pending deletion / active)
  • Secrets Manager (stale secrets > 90 days)
  • Security Hub, CloudTrail, GuardDuty (visibility — always ACTIVE)
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from backend.Resource_rules import (
    RuleVerdict, DORMANT_USER_DAYS,
)


# ─── KMS Keys ─────────────────────────────────────────────────────────────────

def classify_kms_key(
    key_manager: str,
    key_state: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a KMS key (customer-managed only).

    Rules:
        • AWS-managed key         → None (skip)
        • Disabled                → RISKY  (candidate for scheduled deletion, 60% certainty)
        • Pending Deletion        → SAFE
        • Enabled                 → ACTIVE
    """
    if key_manager != 'CUSTOMER':
        return None, None  # Skip AWS-managed keys

    if key_state == 'Disabled':
        return RuleVerdict.RISKY, "Disabled KMS key (candidate for scheduled deletion)"
    if key_state == 'PendingDeletion':
        return RuleVerdict.SAFE, "KMS key pending deletion"
    if key_state == 'Enabled':
        return RuleVerdict.ACTIVE, "Customer-managed KMS key"
    return None, None  # Other states


# ─── Secrets Manager ──────────────────────────────────────────────────────────

def classify_secret(
    days_since_access: Optional[int],
) -> Tuple[RuleVerdict, str]:
    """Classify a Secrets Manager secret.

    Rules:
        • Not accessed for > 90 days  → RISKY  (zombie, 55% certainty)
        • Accessed recently           → ACTIVE
        • Access date unknown         → ACTIVE (cannot determine)
    """
    if days_since_access is not None and days_since_access > DORMANT_USER_DAYS:
        return RuleVerdict.RISKY, f"Secret not accessed for {days_since_access} days"
    return RuleVerdict.ACTIVE, "Active secret"


# ─── Security Hub ─────────────────────────────────────────────────────────────

def classify_security_hub(
    is_enabled: bool,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify Security Hub.

    Rules:
        • Enabled  → ACTIVE (visibility only)
        • Disabled → None (skip)
    """
    if is_enabled:
        return RuleVerdict.ACTIVE, "Security Hub enabled"
    return None, None


# ─── CloudTrail ───────────────────────────────────────────────────────────────

def classify_cloudtrail(
    is_logging: bool,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a CloudTrail trail.

    Rules:
        • Logging → ACTIVE (visibility)
        • Not logging → None (skip)
    """
    if is_logging:
        return RuleVerdict.ACTIVE, "Active CloudTrail"
    return None, None


# ─── GuardDuty ────────────────────────────────────────────────────────────────

def classify_guardduty(
    status: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a GuardDuty detector.

    Rules:
        • ENABLED → ACTIVE (visibility)
        • Other   → None (skip)
    """
    if status == 'ENABLED':
        return RuleVerdict.ACTIVE, "GuardDuty enabled"
    return None, None
