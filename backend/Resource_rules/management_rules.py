"""
Management Resource Rules
=========================
Classification rules for:
  • CloudWatch Log Groups (empty / stale zombie detection)
  • CloudWatch Alarms (INSUFFICIENT_DATA / no actions)
  • Lambda Functions (zero invocations = zombie)
  • EventBridge Rules (disabled / no targets)
  • Config Recorders, SSM Managed Instances (visibility — always ACTIVE)
"""

from typing import Dict, Any, List, Optional, Tuple
from backend.Resource_rules import RuleVerdict


# ─── CloudWatch Log Groups ────────────────────────────────────────────────────

def classify_log_group(
    stored_bytes: int,
    days_since_last_event: Optional[int],
) -> Tuple[RuleVerdict, str]:
    """Classify a CloudWatch Log Group.

    Rules:
        • 0 bytes stored                   → SAFE  (empty, 80% certainty)
        • No events for > 90 days          → RISKY (stale zombie)
        • Active / large                   → ACTIVE
    """
    if stored_bytes == 0:
        return RuleVerdict.SAFE, "Empty log group (0 bytes stored)"

    stored_gb = stored_bytes / (1024 ** 3)
    if days_since_last_event is not None and days_since_last_event > 90:
        return RuleVerdict.RISKY, f"No log events for {days_since_last_event} days ({stored_gb:.2f} GB stored)"

    return RuleVerdict.ACTIVE, f"Log group storing {stored_gb:.2f} GB"


# ─── CloudWatch Alarms ────────────────────────────────────────────────────────

def classify_cloudwatch_alarm(
    state_value: str,
    has_actions: bool,
) -> Tuple[RuleVerdict, str]:
    """Classify a CloudWatch Alarm.

    Rules:
        • INSUFFICIENT_DATA            → SAFE  (resource likely deleted, 85% certainty)
        • No alarm actions configured   → RISKY (orphaned alarm)
        • Otherwise                     → ACTIVE
    """
    if state_value == 'INSUFFICIENT_DATA':
        return RuleVerdict.SAFE, "INSUFFICIENT_DATA - resource likely deleted"
    if not has_actions:
        return RuleVerdict.RISKY, "No actions configured"
    return RuleVerdict.ACTIVE, "Active alarm"


# ─── Lambda Functions ─────────────────────────────────────────────────────────

def classify_lambda_function(
    invocations_30d: int,
) -> Tuple[RuleVerdict, str]:
    """Classify a Lambda function.

    Rules:
        • 0 invocations in 30 days  → RISKY (zombie, 65% certainty)
        • > 0 invocations           → ACTIVE
        • Unknown (-1)              → ACTIVE (cannot determine)
    """
    if invocations_30d == 0:
        return RuleVerdict.RISKY, "Zero invocations in last 30 days"
    return RuleVerdict.ACTIVE, "Active Lambda function"


# ─── EventBridge Rules ────────────────────────────────────────────────────────

def classify_eventbridge_rule(
    rule_state: str,
    target_count: int,
) -> Tuple[RuleVerdict, str]:
    """Classify an EventBridge rule.

    Rules:
        • Disabled                → RISKY (orphaned, 70% certainty)
        • Enabled + 0 targets     → SAFE  (rule with no effect)
        • Enabled + targets       → ACTIVE
    """
    if rule_state == 'DISABLED':
        return RuleVerdict.RISKY, "Disabled EventBridge rule"
    if target_count == 0:
        return RuleVerdict.SAFE, "EventBridge rule with no targets"
    return RuleVerdict.ACTIVE, f"Active rule ({target_count} targets)"


# ─── Config Recorder ──────────────────────────────────────────────────────────

def classify_config_recorder(
    is_recording: bool,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an AWS Config recorder.

    Rules:
        • Recording → ACTIVE (visibility)
        • Not recording → None (skip)
    """
    if is_recording:
        return RuleVerdict.ACTIVE, "Config recorder active"
    return None, None


# ─── SSM Managed Instance ─────────────────────────────────────────────────────

def classify_ssm_instance(
    ping_status: str,
) -> Tuple[Optional[RuleVerdict], Optional[str]]:
    """Classify an SSM managed instance.

    Rules:
        • Online → ACTIVE (visibility)
        • Other  → None (skip)
    """
    if ping_status == 'Online':
        return RuleVerdict.ACTIVE, "SSM managed instance"
    return None, None
