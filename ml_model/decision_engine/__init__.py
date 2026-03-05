"""
Decision Engine — ML Policy Layer for Spot Pool Optimization
============================================================

This package implements the 15-step decision pipeline that evaluates
whether a spot pool switch should be executed for a given EKS cluster.

Pipeline Overview
-----------------
The Decision Engine is the "brain" that takes raw ML predictions (risk,
savings) from the Intelligence Layer and applies business policies before
approving any cluster action.

Step-by-step files in this package:
  01_scoring.py         - Core EV formula: savings × (1 - risk)
  02_ev_model.py        - Full economic EV with interruption cost, capacity
                          failure probability, migration penalty, volatility
  03_cooldown_guard.py  - Steps 1-2: Cluster + pool cooldown enforcement
  04_workload_classifier.py - Steps 2b-2c: Node classification, stateless filter
  05_risk_filter.py     - Step 6: Three-layer risk ceiling + volatility guard
  06_capacity_validator.py  - Step 7: Capacity freshness validation
  07_pool_scorer.py     - Step 9: Re-score candidate pools with full EV model
  08_template_filter.py - Step 11: Node template + Karpenter constraint filters
  09_diversity_check.py - Step 12: Instance family + AZ diversity constraints
  10_delta_selector.py  - Steps 13-14: Delta threshold + best candidate selection
  11_optimizer_coordinator.py - Phase management + combined EV for rightsizing
  pipeline.py           - Main entry point (DecisionEngine class, 15 steps)

Source Code Mapping
-------------------
This package is a documented mirror of the production backend code:
  backend/core/decision_engine.py      — pipeline.py
  backend/core/scoring.py              — 01_scoring.py
  backend/core/ev_model.py             — 02_ev_model.py
  backend/services/cooldown_controller.py — 03_cooldown_guard.py
  backend/services/workload_inspector.py  — 04_workload_classifier.py
  backend/services/diversity_enforcer.py  — 09_diversity_check.py
  backend/services/optimizer_coordinator.py — 11_optimizer_coordinator.py

Usage
-----
    from ml_model.decision_engine.pipeline import DecisionEngine

    engine = DecisionEngine(redis_client, db_session)
    result = engine.evaluate_action_plan(
        cluster_id="prod-cluster",
        current_pool={"instance_type": "m5.large", "az": "us-east-1a",
                      "predicted_savings": 0.6, "risk_probability": 0.05},
        candidate_pools=[...],
        action_type="POOL_SWITCH"
    )

    if result["approved"]:
        # Hand off to Execution Engine
        pass
"""
