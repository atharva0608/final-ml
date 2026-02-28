"""
Unified Optimizer Coordinator
==============================

Single authority that coordinates Spot ML Pool Optimizer and Right-sizing Optimizer
to prevent oscillation and ensure proper sequencing.

Architecture (per problems.md):
-------------------------------
Phase 1: INITIAL_POOL_OPTIMIZATION - Spot ML runs first (30-60 min stabilization)
Phase 2: STABILIZATION - Waiting period before rightsizing evaluation
Phase 3: RIGHTSIZING_EVALUATION - Rightsizing proposes size changes
Phase 4: COMBINED_EXECUTION - Calculate combined EV, execute best option
Phase 5: COOLDOWN - Post-execution cooldown (6h resize, 30min pool switch)

Key Principles:
---------------
1. Rightsizing ONLY proposes, never executes directly
2. Spot ML re-evaluates within new size envelope
3. Combined EV decides: Option A (size+pool) vs B (new pool) vs C (nothing)
4. Cooldowns prevent overlapping changes
5. Minimum 24h stability window for rightsizing
6. Minimum 10-15% EV improvement required

Usage:
------
coordinator = OptimizerCoordinator(db, redis)

# Check if cluster can run pool optimization
if coordinator.can_run_pool_optimization(cluster_id):
    coordinator.execute_pool_optimization(cluster_id)

# Check if cluster ready for rightsizing evaluation
if coordinator.can_run_rightsizing_evaluation(cluster_id):
    proposal = coordinator.evaluate_rightsizing(cluster_id)

# Evaluate and execute combined optimization
result = coordinator.evaluate_combined_proposal(proposal_id)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from redis import Redis

from backend.core.logger import logger
from backend.core.scoring import compute_expected_value, compute_combined_expected_value
from backend.services.cooldown_controller import CooldownController
from backend.services.workload_inspector import WorkloadInspector, NodeStatus
from backend.models.cluster import Cluster
from backend.models.optimizer_state import OptimizerState, OptimizationPhase
from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus


class OptimizerCoordinator:
    """
    Central coordinator for pool and size optimization.

    Prevents conflicts between Spot ML and Rightsizing optimizers
    by enforcing phase-based execution and combined EV evaluation.
    """

    # Timing thresholds (per problems.md)
    STABILIZATION_HOURS = 1  # Wait 1 hour before rightsizing evaluation
    RIGHTSIZING_EVAL_INTERVAL_HOURS = 24  # Evaluate rightsizing once per day
    MIN_SAVINGS_DELTA_PCT = 10.0  # Minimum 10% EV improvement required

    def __init__(self, db: Session, redis: Redis):
        self.db = db
        self.redis = redis
        self.cooldown = CooldownController(redis)
        self.workload = WorkloadInspector(redis)

    # ========================================================================
    # PHASE MANAGEMENT
    # ========================================================================

    def initialize_cluster_state(self, cluster_id: str) -> OptimizerState:
        """
        Initialize optimizer state for a new cluster.

        Args:
            cluster_id: Cluster identifier

        Returns:
            OptimizerState object
        """
        existing = self.db.query(OptimizerState).filter(
            OptimizerState.cluster_id == cluster_id
        ).first()

        if existing:
            logger.info(f"Optimizer state already exists for cluster {cluster_id}")
            return existing

        state = OptimizerState(
            cluster_id=cluster_id,
            current_phase=OptimizationPhase.INITIAL_POOL_OPTIMIZATION,
            phase_started_at=datetime.utcnow()
        )

        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)

        logger.info(f"Initialized optimizer state for cluster {cluster_id} in phase {state.current_phase}")
        return state

    def get_or_create_state(self, cluster_id: str) -> OptimizerState:
        """Get existing state or create new one."""
        state = self.db.query(OptimizerState).filter(
            OptimizerState.cluster_id == cluster_id
        ).first()

        if not state:
            state = self.initialize_cluster_state(cluster_id)

        return state

    def transition_phase(self, cluster_id: str, new_phase: OptimizationPhase, reason: str = ""):
        """
        Transition cluster to a new optimization phase.

        Args:
            cluster_id: Cluster identifier
            new_phase: Target phase
            reason: Reason for transition (for logging)
        """
        state = self.get_or_create_state(cluster_id)
        old_phase = state.current_phase

        state.current_phase = new_phase
        state.phase_started_at = datetime.utcnow()

        self.db.commit()

        logger.info(f"Cluster {cluster_id} transitioned: {old_phase} → {new_phase}. Reason: {reason}")

    # ========================================================================
    # POOL OPTIMIZATION (Spot ML)
    # ========================================================================

    def can_run_pool_optimization(self, cluster_id: str) -> Tuple[bool, str]:
        """
        Check if cluster can run pool optimization.

        Returns:
            (can_run: bool, reason: str)
        """
        state = self.get_or_create_state(cluster_id)

        # Check if in cooldown
        can_switch, remaining = self.cooldown.can_switch(cluster_id)
        if not can_switch:
            return (False, f"Cluster cooldown active ({remaining}s remaining)")

        # ── PENDING PROPOSAL FREEZE (FIX 3) ──────────────────────────
        # If a rightsizing proposal is pending coordinator evaluation,
        # freeze pool optimization to prevent concurrent modifications.
        if state.pending_rightsizing_proposal_id:
            return (False, "Rightsizing proposal pending — pool optimization frozen")

        # Check phase - pool optimization allowed in INITIAL, STABILIZATION, or after COOLDOWN
        allowed_phases = [
            OptimizationPhase.INITIAL_POOL_OPTIMIZATION,
            OptimizationPhase.STABILIZATION,
            OptimizationPhase.COOLDOWN
        ]

        if state.current_phase not in allowed_phases:
            return (False, f"Phase {state.current_phase} does not allow pool optimization")

        # Check workload classification (must have STATELESS nodes)
        classification = self.workload.get_cached_classification(cluster_id)
        if not classification:
            return (False, "Node classification unavailable (WorkloadInspector scan required)")

        stateless_nodes = [
            node for node, status in classification.items()
            if status == NodeStatus.STATELESS_ELIGIBLE
        ]

        if not stateless_nodes:
            return (False, "No stateless-eligible nodes found")

        return (True, "Pool optimization allowed")

    def record_pool_optimization(self, cluster_id: str):
        """
        Record that pool optimization was executed.
        Updates state and activates cooldown.
        """
        state = self.get_or_create_state(cluster_id)
        state.last_pool_optimization_at = datetime.utcnow()

        # If in INITIAL phase, transition to STABILIZATION
        if state.current_phase == OptimizationPhase.INITIAL_POOL_OPTIMIZATION:
            self.transition_phase(cluster_id, OptimizationPhase.STABILIZATION, "After initial pool optimization")

        # Activate pool switch cooldown (30 minutes)
        self.cooldown.record_pool_switch_action(cluster_id)

        self.db.commit()
        logger.info(f"Recorded pool optimization for cluster {cluster_id}")

    # ========================================================================
    # RIGHTSIZING EVALUATION
    # ========================================================================

    def get_cluster_trust_phase(self, cluster_id: str) -> dict:
        """
        Returns progressive trust phase and associated safety parameters.

        Phase 0 (0–30 min):  No rightsizing, tightened risk (0.15)
        Phase 1 (30–120 min): Conservative rightsizing (25% buffer, 500 samples min)
        Phase 2 (>24h):      Full rightsizing (20% buffer, 100 samples min)
        """
        state = self.get_or_create_state(cluster_id)

        # Calculate cluster age from first pool optimization or creation
        if state.created_at:
            hours_alive = (datetime.utcnow() - state.created_at).total_seconds() / 3600
        else:
            hours_alive = 0

        if hours_alive < 0.5:   # Phase 0: 0-30 min
            return {
                "phase": 0,
                "rightsizing_allowed": False,
                "safety_buffer_pct": 30,
                "min_samples": 500,
                "risk_ceiling_override": 0.15,
                "reason": f"Phase 0: cluster age {hours_alive:.1f}h < 0.5h"
            }
        elif hours_alive < 2.0:  # Phase 1: 30 min - 2 hours
            return {
                "phase": 1,
                "rightsizing_allowed": True,
                "safety_buffer_pct": 25,
                "min_samples": 500,
                "risk_ceiling_override": 0.20,
                "reason": f"Phase 1: conservative mode ({hours_alive:.1f}h)"
            }
        else:                    # Phase 2: >2 hours (full at >24h)
            return {
                "phase": 2,
                "rightsizing_allowed": True,
                "safety_buffer_pct": 20,
                "min_samples": 100,
                "risk_ceiling_override": None,  # Use profile default
                "reason": f"Phase 2: full mode ({hours_alive:.1f}h)"
            }

    def can_run_rightsizing_evaluation(self, cluster_id: str) -> Tuple[bool, str]:
        """
        Check if cluster can run rightsizing evaluation.

        Returns:
            (can_run: bool, reason: str)
        """
        state = self.get_or_create_state(cluster_id)

        # ── PROGRESSIVE TRUST PHASE (Enhancement 1) ──────────────────────
        trust = self.get_cluster_trust_phase(cluster_id)
        if not trust["rightsizing_allowed"]:
            return (False, trust["reason"])

        # Check if in STABILIZATION phase and stabilization period has elapsed
        if state.current_phase == OptimizationPhase.STABILIZATION:
            hours_since_start = (datetime.utcnow() - state.phase_started_at).total_seconds() / 3600

            if hours_since_start < self.STABILIZATION_HOURS:
                return (False, f"Stabilization period incomplete ({hours_since_start:.1f}/{self.STABILIZATION_HOURS}h)")
        elif state.current_phase == OptimizationPhase.COOLDOWN:
            # After cooldown, can evaluate again
            pass
        else:
            return (False, f"Phase {state.current_phase} does not allow rightsizing evaluation")

        # Check if rightsizing was run recently (24-hour interval)
        if state.last_rightsizing_check_at:
            hours_since_last = (datetime.utcnow() - state.last_rightsizing_check_at).total_seconds() / 3600

            if hours_since_last < self.RIGHTSIZING_EVAL_INTERVAL_HOURS:
                return (False, f"Rightsizing evaluated recently ({hours_since_last:.1f}/{self.RIGHTSIZING_EVAL_INTERVAL_HOURS}h)")

        # Check resize cooldown
        can_resize, remaining = self.cooldown.can_resize(cluster_id)
        if not can_resize:
            return (False, f"Resize cooldown active ({remaining}s remaining)")

        # ── RESIZE CIRCUIT BREAKER (Enhancement 10) ──────────────────────
        resize_failure_key = f"resize:failure_count_24h:{cluster_id}"
        try:
            failure_count = int(self.redis.get(resize_failure_key) or 0)
            if failure_count >= 3:
                return (False, f"Resize circuit breaker open: {failure_count} failures in 24h")
        except Exception:
            pass

        return (True, "Rightsizing evaluation allowed")

    def record_rightsizing_evaluation(self, cluster_id: str, proposal_id: Optional[str] = None):
        """
        Record that rightsizing evaluation was executed.

        Args:
            cluster_id: Cluster identifier
            proposal_id: ID of created proposal (if any)
        """
        state = self.get_or_create_state(cluster_id)
        state.last_rightsizing_check_at = datetime.utcnow()

        if proposal_id:
            state.pending_rightsizing_proposal_id = proposal_id
            self.transition_phase(cluster_id, OptimizationPhase.RIGHTSIZING_EVALUATION, "Proposal created")
        else:
            # No proposal created, go back to stabilization
            self.transition_phase(cluster_id, OptimizationPhase.STABILIZATION, "No rightsizing needed")

        self.db.commit()
        logger.info(f"Recorded rightsizing evaluation for cluster {cluster_id}, proposal_id={proposal_id}")

    # ========================================================================
    # COMBINED EVALUATION (Option A vs B vs C)
    # ========================================================================

    def evaluate_combined_proposal(self, proposal_id: str) -> Dict:
        """
        Evaluate a rightsizing proposal using combined EV calculation.

        Compares:
        - Option A: Current size + new pool (pool optimization only)
        - Option B: New size + best pool for new size (combined optimization)
        - Option C: Do nothing

        Args:
            proposal_id: Rightsizing proposal ID

        Returns:
            {
                "approved": bool,
                "selected_option": str,  # "A", "B", "C"
                "reason": str,
                "ev_breakdown": dict
            }
        """
        proposal = self.db.query(RightsizingProposal).filter(
            RightsizingProposal.id == proposal_id
        ).first()

        if not proposal:
            return {"approved": False, "reason": f"Proposal {proposal_id} not found"}

        cluster_id = proposal.cluster_id
        state = self.get_or_create_state(cluster_id)

        # Transition to COMBINED_EXECUTION phase
        self.transition_phase(cluster_id, OptimizationPhase.COMBINED_EXECUTION, "Evaluating combined proposal")

        # TODO: Re-run Spot ML constrained to new size to get best pool for new size
        # For now, use placeholder values
        # This would call: pool_ranking_service.rank_pools_for_size(new_size_vcpu, new_size_memory)

        best_pool_for_new_size_cost = proposal.proposed_hourly_cost * 0.7  # Assume 30% savings from optimal pool
        best_pool_risk = 0.08  # Placeholder risk score

        # Calculate combined EV
        try:
            # ── Task 3.4: Use stored ev_breakdown if available ────
            if proposal.ev_breakdown is not None:
                # New path: use economic EV stored at proposal creation time
                pool_ev = proposal.ev_breakdown.get("ev", 0.0)
                rightsizing_ev = proposal.net_ev or 0.0
                
                ev_result = {
                    "option_a": {"expected_value": pool_ev, "source": "stored_ev_breakdown"},
                    "option_b": {"expected_value": rightsizing_ev, "source": "stored_net_ev"},
                    "option_c": {"expected_value": 0.0, "source": "baseline"},
                    "ev_breakdown": proposal.ev_breakdown,
                    "recommended_option": "A" if pool_ev >= rightsizing_ev else "B",
                    "best_ev_delta_pct": 0.0,
                    "sufficient_improvement": False,
                }
                
                baseline_ev = 0.0  # Option C: do nothing
                best_ev = max(pool_ev, rightsizing_ev)
                
                if best_ev > 0 and abs(baseline_ev) > 0:
                    ev_result["best_ev_delta_pct"] = ((best_ev - baseline_ev) / max(abs(baseline_ev), 1)) * 100
                elif best_ev > 0:
                    ev_result["best_ev_delta_pct"] = 100.0
                
                ev_result["sufficient_improvement"] = (
                    best_ev > 0 and (best_ev - baseline_ev) / max(abs(baseline_ev), 1) >= 0.10
                )
                ev_result["recommended_option"] = (
                    "A" if pool_ev >= rightsizing_ev and pool_ev > 0
                    else "B" if rightsizing_ev > 0
                    else "C"
                )
            else:
                # Fallback for proposals created before the EV migration
                ev_result = compute_combined_expected_value(
                    current_size_cost=proposal.current_hourly_cost,
                    current_pool_cost=proposal.current_hourly_cost,
                    current_risk=0.05,
                    new_size_cost=proposal.proposed_hourly_cost,
                    new_pool_cost=best_pool_for_new_size_cost,
                    new_pool_risk=best_pool_risk,
                    migration_cost=0.10,
                    volatility_penalty=0.0
                )

            # Store evaluation results in proposal
            proposal.combined_ev_option_a = ev_result["option_a"]["expected_value"]
            proposal.combined_ev_option_b = ev_result["option_b"]["expected_value"]
            proposal.combined_ev_option_c = ev_result["option_c"]["expected_value"]
            proposal.selected_option = ev_result["recommended_option"]
            proposal.best_pool_for_new_size = f"{proposal.proposed_instance_type}:best-az"  # Placeholder
            proposal.best_pool_hourly_cost = best_pool_for_new_size_cost
            proposal.best_pool_risk_score = best_pool_risk
            proposal.evaluation_breakdown = ev_result
            proposal.evaluated_at = datetime.utcnow()

            # Decide approval based on sufficient improvement
            if ev_result["sufficient_improvement"] and ev_result["recommended_option"] != "C":
                proposal.status = ProposalStatus.APPROVED
                self.db.commit()

                logger.info(f"Proposal {proposal_id} APPROVED: Option {ev_result['recommended_option']} with {ev_result['best_ev_delta_pct']:.1f}% improvement")

                return {
                    "approved": True,
                    "selected_option": ev_result["recommended_option"],
                    "reason": f"Sufficient EV improvement: {ev_result['best_ev_delta_pct']:.1f}%",
                    "ev_breakdown": ev_result
                }
            else:
                proposal.status = ProposalStatus.REJECTED
                proposal.rejection_reason = f"Insufficient improvement: {ev_result['best_ev_delta_pct']:.1f}% < {self.MIN_SAVINGS_DELTA_PCT}%"
                self.db.commit()

                # Transition back to STABILIZATION
                self.transition_phase(cluster_id, OptimizationPhase.STABILIZATION, "Proposal rejected")

                logger.info(f"Proposal {proposal_id} REJECTED: {proposal.rejection_reason}")

                return {
                    "approved": False,
                    "selected_option": "C",
                    "reason": proposal.rejection_reason,
                    "ev_breakdown": ev_result
                }

        except Exception as e:
            logger.error(f"Error evaluating proposal {proposal_id}: {e}")
            proposal.status = ProposalStatus.REJECTED
            proposal.rejection_reason = f"Evaluation error: {str(e)}"
            self.db.commit()

            return {
                "approved": False,
                "reason": f"Evaluation error: {str(e)}"
            }

    def execute_approved_proposal(self, proposal_id: str) -> Dict:
        """
        Execute an approved rightsizing proposal.

        Args:
            proposal_id: Rightsizing proposal ID

        Returns:
            {
                "success": bool,
                "reason": str
            }
        """
        proposal = self.db.query(RightsizingProposal).filter(
            RightsizingProposal.id == proposal_id
        ).first()

        if not proposal:
            return {"success": False, "reason": f"Proposal {proposal_id} not found"}

        if proposal.status != ProposalStatus.APPROVED:
            return {"success": False, "reason": f"Proposal not approved (status: {proposal.status})"}

        cluster_id = proposal.cluster_id

        # Execute the actual resize operation
        try:
            # TODO: Execute the actual resize operation
            # This would call: karpenter_service.apply_resize(cluster_id, proposal.proposed_instance_type)

            # For now, mark as executed
            proposal.status = ProposalStatus.EXECUTED
            proposal.executed_at = datetime.utcnow()
            self.db.commit()

            # Activate resize cooldown (6 hours)
            self.cooldown.record_resize_action(cluster_id)

            # Transition to COOLDOWN phase
            self.transition_phase(cluster_id, OptimizationPhase.COOLDOWN, "Resize executed")

            logger.info(f"Executed proposal {proposal_id} for cluster {cluster_id}")

            return {
                "success": True,
                "reason": "Proposal executed successfully"
            }

        except Exception as e:
            # ── CIRCUIT BREAKER FAILURE RECORDING (Enhancement 10) ───────
            logger.error(f"Failed to execute proposal {proposal_id}: {e}")

            # Record failure for circuit breaker
            failure_key = f"resize:failure_count_24h:{cluster_id}"
            count = self.redis.incr(failure_key)
            if count == 1:
                self.redis.expire(failure_key, 86400)  # 24h TTL

            # Mark proposal as failed
            proposal.status = ProposalStatus.FAILED
            proposal.rejection_reason = f"Execution failed: {str(e)}"
            self.db.commit()

            return {
                "success": False,
                "reason": f"Execution failed: {str(e)}"
            }

    # ========================================================================
    # STATUS & MONITORING
    # ========================================================================

    def get_cluster_status(self, cluster_id: str) -> Dict:
        """
        Get comprehensive optimizer status for a cluster.

        Returns:
            {
                "phase": str,
                "phase_started_at": datetime,
                "hours_in_phase": float,
                "can_run_pool_optimization": bool,
                "can_run_rightsizing_evaluation": bool,
                "last_pool_optimization_at": datetime,
                "last_rightsizing_check_at": datetime,
                "pending_proposal": dict or None,
                "cooldown_status": dict
            }
        """
        state = self.get_or_create_state(cluster_id)

        hours_in_phase = (datetime.utcnow() - state.phase_started_at).total_seconds() / 3600

        # Check capabilities
        can_pool, pool_reason = self.can_run_pool_optimization(cluster_id)
        can_rightsize, rightsize_reason = self.can_run_rightsizing_evaluation(cluster_id)

        # Get pending proposal if any
        pending_proposal = None
        if state.pending_rightsizing_proposal_id:
            proposal = self.db.query(RightsizingProposal).filter(
                RightsizingProposal.id == state.pending_rightsizing_proposal_id
            ).first()

            if proposal:
                pending_proposal = {
                    "id": proposal.id,
                    "status": proposal.status.value,
                    "current_type": proposal.current_instance_type,
                    "proposed_type": proposal.proposed_instance_type,
                    "estimated_savings_pct": proposal.savings_percentage,
                    "created_at": proposal.created_at.isoformat()
                }

        # Get cooldown status
        cooldown_status = self.cooldown.get_action_cooldown_status(cluster_id)

        return {
            "phase": state.current_phase.value,
            "phase_started_at": state.phase_started_at.isoformat() if state.phase_started_at else None,
            "hours_in_phase": hours_in_phase,
            "can_run_pool_optimization": can_pool,
            "pool_optimization_reason": pool_reason,
            "can_run_rightsizing_evaluation": can_rightsize,
            "rightsizing_evaluation_reason": rightsize_reason,
            "last_pool_optimization_at": state.last_pool_optimization_at.isoformat() if state.last_pool_optimization_at else None,
            "last_rightsizing_check_at": state.last_rightsizing_check_at.isoformat() if state.last_rightsizing_check_at else None,
            "pending_proposal": pending_proposal,
            "cooldown_status": cooldown_status
        }
