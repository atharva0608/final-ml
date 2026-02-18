"""
Database Resource Rules
=======================
Classification rules for:
  • RDS Instances (idle detection, legacy class)
  • RDS Multi-AZ (non-prod waste)
  • DynamoDB Tables (placeholder)
  • ElastiCache Clusters (placeholder)
"""

from typing import Dict, Any, List, Optional, Tuple
from backend.Resource_rules import (
    RuleVerdict, LEGACY_RDS_PREFIXES, NON_PROD_ENVIRONMENTS,
)


# ─── RDS Instances ────────────────────────────────────────────────────────────

def classify_rds_instance(
    is_idle: bool,
    has_replicas: bool,
    db_class: str,
) -> Tuple[RuleVerdict, str]:
    """Classify an RDS instance.

    Rules:
        • Idle (0 connections 14d) + no replicas  → RISKY (ORPHANED / Idle)
        • Idle but has read replicas               → ACTIVE (source DB)
        • Legacy class (db.t2 / db.m4 / db.m3)     → REVIEW (LEGACY_UPGRADE)
        • Otherwise                                 → ACTIVE
    """
    if is_idle:
        if has_replicas:
            return RuleVerdict.ACTIVE, "Has read replicas (source DB)"
        return RuleVerdict.RISKY, "Zero connections for 14 days (Idle)"

    is_legacy = any(db_class.startswith(prefix) for prefix in LEGACY_RDS_PREFIXES)
    if is_legacy:
        return RuleVerdict.REVIEW, f"Legacy instance class ({db_class}). Upgrade to T3/M5/M6 for savings."

    return RuleVerdict.ACTIVE, "Active RDS instance"


# ─── RDS Multi-AZ ─────────────────────────────────────────────────────────────

def classify_rds_multi_az(
    is_multi_az: bool,
    environment: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an RDS instance based on Multi-AZ deployment.

    Rules:
        • Multi-AZ enabled in non-prod env → REVIEW (LEGACY_UPGRADE / downgrade)
        • Otherwise                        → None (skip)
    """
    if is_multi_az and environment.lower() in NON_PROD_ENVIRONMENTS:
        return RuleVerdict.REVIEW, f"Multi-AZ enabled in {environment} environment"
    return None, None


# ─── DynamoDB Tables (placeholder) ────────────────────────────────────────────

def classify_dynamodb_table(
    read_capacity: int,
    write_capacity: int,
    item_count: int,
    consumed_read_pct: float,
    consumed_write_pct: float,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify a DynamoDB table.

    Rules (placeholder — expand when scanner is added):
        • Empty table (0 items) with provisioned capacity  → RISKY
        • Very low utilization (< 10% read & write)        → REVIEW
        • Otherwise                                        → ACTIVE
    """
    if item_count == 0 and (read_capacity > 0 or write_capacity > 0):
        return RuleVerdict.RISKY, "Empty DynamoDB table with provisioned capacity"
    if consumed_read_pct < 10 and consumed_write_pct < 10 and (read_capacity > 5 or write_capacity > 5):
        return RuleVerdict.REVIEW, f"Low utilization (Read: {consumed_read_pct:.0f}%, Write: {consumed_write_pct:.0f}%)"
    return RuleVerdict.ACTIVE, "Active DynamoDB table"


# ─── ElastiCache Clusters (placeholder) ───────────────────────────────────────

def classify_elasticache_cluster(
    engine: str,
    num_nodes: int,
    cpu_utilization_pct: float,
    cache_hit_rate_pct: float,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an ElastiCache cluster.

    Rules (placeholder — expand when scanner is added):
        • CPU < 5% and hit rate < 1%  → RISKY (idle)
        • CPU < 10% and hit rate < 5% → REVIEW
        • Otherwise                   → ACTIVE
    """
    if cpu_utilization_pct < 5 and cache_hit_rate_pct < 1:
        return RuleVerdict.RISKY, f"Idle ElastiCache ({engine}) — CPU {cpu_utilization_pct:.0f}%, hits {cache_hit_rate_pct:.0f}%"
    if cpu_utilization_pct < 10 and cache_hit_rate_pct < 5:
        return RuleVerdict.REVIEW, f"Low utilization ElastiCache ({engine}) — CPU {cpu_utilization_pct:.0f}%, hits {cache_hit_rate_pct:.0f}%"
    return RuleVerdict.ACTIVE, f"Active ElastiCache ({engine})"
