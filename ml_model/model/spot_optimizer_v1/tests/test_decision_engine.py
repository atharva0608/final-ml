import pytest

from decision_engine.engine import DecisionEngine, SpotCandidate, UserConstraints


def test_accept_valid_candidate():
    constraints = UserConstraints(max_price=0.50, criticality="low")
    engine = DecisionEngine(constraints)
    candidate = SpotCandidate(
        instance_type="c6i.large",
        availability_zone="us-east-1a",
        predicted_savings=0.60,
        risk_score=0.10,
        interruption_rate=0.03,
        on_demand_price=0.10,
        pool_baseline=0.55,
        pool_std=0.04,
    )
    result = engine.evaluate(candidate)
    assert result["decision"] == "ACCEPT"
    assert result["score"] > 0


def test_reject_high_risk_score():
    constraints = UserConstraints(max_price=0.50, max_risk_score=0.7)
    engine = DecisionEngine(constraints)
    candidate = SpotCandidate(
        instance_type="c6i.large",
        availability_zone="us-east-1a",
        predicted_savings=0.60,
        risk_score=0.85,  # Above 0.7
        interruption_rate=0.03,
        on_demand_price=0.10,
        pool_baseline=0.55,
        pool_std=0.04,
    )
    result = engine.evaluate(candidate)
    assert result["decision"] == "REJECT"
    assert "High Risk Score" in result["reason"]


def test_reject_danger_z_score():
    constraints = UserConstraints(max_price=0.50, z_score_threshold=-3.0)
    engine = DecisionEngine(constraints)
    # Predicted savings (0.25) much lower than baseline (0.60)
    # (0.25 - 0.60) / 0.05 = -7.0
    candidate = SpotCandidate(
        instance_type="m6i.large",
        availability_zone="us-east-1b",
        predicted_savings=0.25,
        risk_score=0.10,
        interruption_rate=0.03,
        on_demand_price=0.12,
        pool_baseline=0.60,
        pool_std=0.05,
    )
    result = engine.evaluate(candidate)
    assert result["decision"] == "REJECT"
    assert "Danger: Z-Score" in result["reason"]


def test_reject_high_interruption_rate_criticality():
    # Criticality "high" should be stricter (max 5%)
    constraints = UserConstraints(max_price=0.50, criticality="high")
    engine = DecisionEngine(constraints)
    candidate = SpotCandidate(
        instance_type="c6i.large",
        availability_zone="us-east-1a",
        predicted_savings=0.60,
        risk_score=0.10,
        interruption_rate=0.07,  # > 5%
        on_demand_price=0.10,
        pool_baseline=0.55,
        pool_std=0.04,
    )
    result = engine.evaluate(candidate)
    assert result["decision"] == "REJECT"
    assert "High Historical Interruption" in result["reason"]


def test_reject_max_price():
    constraints = UserConstraints(max_price=0.02)  # Very low max price
    engine = DecisionEngine(constraints)
    # Spot price = 0.10 * (1 - 0.60) = 0.04
    candidate = SpotCandidate(
        instance_type="c6i.large",
        availability_zone="us-east-1a",
        predicted_savings=0.60,
        risk_score=0.10,
        interruption_rate=0.03,
        on_demand_price=0.10,
        pool_baseline=0.55,
        pool_std=0.04,
    )
    result = engine.evaluate(candidate)
    assert result["decision"] == "REJECT"
    assert "exceeds limit" in result["reason"]
