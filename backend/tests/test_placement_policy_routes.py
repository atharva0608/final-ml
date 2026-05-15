"""
Task 1.20 — Sanitization Contract regression tests.

Ensures sanitize_placement_policy_output() NEVER mutates engine-owned boolean fields,
scores, or classification state — regardless of confidence_state.

See plan.md §0 Invariant 1 and Invariant 2.
Root cause of 2026-04-21 bug: sanitizer was silently setting spot_friendly=False for
DRAFT/PROVISIONAL workloads. These tests are the regression gate.
"""

import pytest
from backend.pipeline.stage3_ppe.policy_routes import sanitize_placement_policy_output, CURRENT_SCHEMA_VERSION


def _base_policy(**overrides) -> dict:
    base = {
        "workload_id": "test-wl-001",
        "cluster_id": "cluster-abc",
        "namespace": "default",
        "name": "my-deployment",
        "criticality_tier": "Silver",
        "confidence_state": "CONFIRMED",
        "spot_friendly": True,
        "observed_replicas": 5,
        "ondemand_target": 3,
        "spot_target": 2,
        "spot_target_raw": 2,
        "traffic_skew_detected": False,
        "skew_signal_source": None,
        "pod_cpu_cv": None,
        "pod_request_rate_cv": None,
        "assigned_nodepool_class": "spot-general",
        "spot_instance_families": ["m5", "c5"],
        "spot_instance_types": ["m5.large"],
        "baseline_affinity": {},
        "burst_affinity": {},
        "topology_spread": None,
        "spread_relaxation_tier": 0,
        "keda_min_replicas": None,
        "keda_max_replicas": None,
        "rollout_eligible": False,
        "rollout_blocked_reason": None,
        "estimated_savings_pct": 30.0,
        "estimated_monthly_saving_usd": 120.0,
        "actionable": True,
        "actionable_blocked_reason": None,
        "signals_used": ["tier=Silver", "confidence=CONFIRMED"],
        "schema_version": CURRENT_SCHEMA_VERSION,
        "input_hash": "abc123",
        "generated_at": "2026-04-22T12:00:00",
    }
    base.update(overrides)
    return base


class TestSanitizationContract:
    """
    Invariant 1 regression: sanitizer MUST NOT modify any engine-owned field.
    The 2026-04-21 bug was spot_friendly=False silently set for DRAFT workloads.
    """

    def test_spot_friendly_true_with_draft_remains_true(self):
        """Core regression test for 2026-04-21 bug."""
        policy = _base_policy(spot_friendly=True, confidence_state="DRAFT", actionable=False)
        result = sanitize_placement_policy_output(policy)
        assert result["spot_friendly"] is True, (
            "sanitize_placement_policy_output() MUST NOT set spot_friendly=False "
            "for DRAFT workloads. This is the exact bug from 2026-04-21."
        )

    def test_spot_friendly_true_with_provisional_remains_true(self):
        policy = _base_policy(spot_friendly=True, confidence_state="PROVISIONAL", actionable=False)
        result = sanitize_placement_policy_output(policy)
        assert result["spot_friendly"] is True

    def test_spot_friendly_false_unchanged(self):
        policy = _base_policy(spot_friendly=False, confidence_state="CONFIRMED")
        result = sanitize_placement_policy_output(policy)
        assert result["spot_friendly"] is False

    def test_actionable_not_mutated(self):
        policy = _base_policy(actionable=True)
        result = sanitize_placement_policy_output(policy)
        assert result["actionable"] is True

        policy = _base_policy(actionable=False)
        result = sanitize_placement_policy_output(policy)
        assert result["actionable"] is False

    def test_rollout_eligible_not_mutated(self):
        policy = _base_policy(rollout_eligible=True)
        result = sanitize_placement_policy_output(policy)
        assert result["rollout_eligible"] is True

    def test_ondemand_target_not_mutated(self):
        policy = _base_policy(ondemand_target=4)
        result = sanitize_placement_policy_output(policy)
        assert result["ondemand_target"] == 4

    def test_spot_target_not_mutated(self):
        policy = _base_policy(spot_target=1)
        result = sanitize_placement_policy_output(policy)
        assert result["spot_target"] == 1

    def test_estimated_savings_pct_not_mutated(self):
        policy = _base_policy(estimated_savings_pct=42.5)
        result = sanitize_placement_policy_output(policy)
        assert result["estimated_savings_pct"] == 42.5

    def test_confidence_state_not_mutated(self):
        for state in ("DRAFT", "PROVISIONAL", "CONFIRMED"):
            policy = _base_policy(confidence_state=state)
            result = sanitize_placement_policy_output(policy)
            assert result["confidence_state"] == state

    def test_tier_not_mutated(self):
        for tier in ("Platinum", "Gold", "Silver", "Bronze"):
            policy = _base_policy(criticality_tier=tier)
            result = sanitize_placement_policy_output(policy)
            assert result["criticality_tier"] == tier

    def test_schema_warning_added_on_version_mismatch(self):
        policy = _base_policy(schema_version="4.99")
        result = sanitize_placement_policy_output(policy)
        assert result.get("schema_warning") is True
        # Spot_friendly must still be unchanged despite schema warning
        assert result["spot_friendly"] is True

    def test_no_schema_warning_on_current_version(self):
        policy = _base_policy(schema_version=CURRENT_SCHEMA_VERSION)
        result = sanitize_placement_policy_output(policy)
        assert result.get("schema_warning") is False

    def test_returns_copy_not_mutation(self):
        policy = _base_policy(spot_friendly=True)
        original_sf = policy["spot_friendly"]
        result = sanitize_placement_policy_output(policy)
        assert policy["spot_friendly"] == original_sf  # original dict untouched
        assert result is not policy  # different object
