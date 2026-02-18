"""
Resource Rules Module
=====================
Modular classification rules for determining whether AWS resources are
SAFE to delete, RISKY (needs review), or ACTIVE (protected).

Each sub-module contains pure rule functions that accept resource metadata
and return a RuleVerdict with a human-readable reason. The actual AWS API
calls remain in hygiene_service.py — these modules handle *only* the
classification logic.
"""

from enum import Enum
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone


# ── Verdict Enum ──────────────────────────────────────────────────────────────

class RuleVerdict(str, Enum):
    """Result of applying a classification rule to a resource."""
    SAFE = "SAFE_TO_DELETE"       # High confidence: can be cleaned up
    RISKY = "ORPHANED"            # Needs manual review before action
    REVIEW = "LEGACY_UPGRADE"     # Optimisation opportunity, not waste
    ACTIVE = "ACTIVE"             # Healthy / in-use — do not touch
    NOT_COMPLIANT = "NOT_COMPLIANT"  # Tag policy violation
    STOPPED = "STOPPED"           # Instance stopped but not yet safe
    UNAUTHORIZED = "UNAUTHORIZED" # Not managed, flagged for review
    RISK = "RISK"                 # Elevated concern (e.g. high data transfer)


# ── Shared Constants ──────────────────────────────────────────────────────────

SAFE_THRESHOLD_DAYS = 30          # Resources older than this are "safe" waste
GRACE_PERIOD_HOURS = 24           # Skip resources created within this window
IDLE_METRIC_DAYS = 14             # CloudWatch look-back period for idle checks
DORMANT_USER_DAYS = 90            # IAM user inactivity threshold

EXEMPT_KEYWORDS = [
    'backup', 'spare', 'template', 'reserved',
    'do-not-delete', 'keep', 'permanent',
]

LEGACY_RDS_PREFIXES = ['db.t2', 'db.m4', 'db.m3']
NON_PROD_ENVIRONMENTS = ['dev', 'test', 'staging', 'development']

AWS_MANAGED_ENI_KEYWORDS = [
    'aws', 'lambda', 'rds', 'ecs', 'elb',
    'eks', 'elasticache', 'redshift', 'vpc endpoint', 'interface',
]


# ── Helper Functions ──────────────────────────────────────────────────────────

def get_tag_value(tags: List[Dict], key: str) -> str:
    """Extract a tag value by key from an AWS-style tag list."""
    for t in tags:
        if t.get('Key') == key:
            return t['Value']
    return "Unknown"


def is_exempt_by_tags(tags: List[Dict], exempt_keywords: List[str] = None) -> bool:
    """Return True if any tag key or value contains an exempt keyword."""
    keywords = exempt_keywords or EXEMPT_KEYWORDS
    for t in tags:
        tag_str = f"{t.get('Key', '')}:{t.get('Value', '')}".lower()
        if any(kw in tag_str for kw in keywords):
            return True
    return False


def check_tag_compliance(tags: List[Dict], required_tags: List[str]) -> Tuple[bool, List[str]]:
    """Check whether a resource has all required tags.

    Returns:
        (is_compliant, list_of_missing_tag_keys)
    """
    tag_keys = {t.get('Key', '') for t in tags}
    missing = [rt for rt in required_tags if rt not in tag_keys]
    return len(missing) == 0, missing


def age_days(created_at: datetime) -> int:
    """Return the number of days since *created_at*."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created_at).days


def is_within_grace_period(created_at: datetime) -> bool:
    """Return True if the resource was created less than GRACE_PERIOD_HOURS ago."""
    grace = datetime.now(timezone.utc) - timedelta(hours=GRACE_PERIOD_HOURS)
    return created_at > grace


# ── Public Exports ────────────────────────────────────────────────────────────

from backend.Resource_rules.compute_rules import *   # noqa: F401,F403,E402
from backend.Resource_rules.storage_rules import *   # noqa: F401,F403,E402
from backend.Resource_rules.database_rules import *  # noqa: F401,F403,E402
from backend.Resource_rules.network_rules import *   # noqa: F401,F403,E402
from backend.Resource_rules.identity_rules import *  # noqa: F401,F403,E402
from backend.Resource_rules.security_rules import *  # noqa: F401,F403,E402
from backend.Resource_rules.management_rules import * # noqa: F401,F403,E402
