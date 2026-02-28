"""
Optimizer Coordinator API Routes
=================================

Endpoints for managing the unified optimizer coordination between
Spot ML and Rightsizing optimizers.

Implements the phased optimization approach from problems.md.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.models.base import get_db
from backend.models.user import User
from backend.core.dependencies import get_current_user
from backend.services.optimizer_coordinator import OptimizerCoordinator
from backend.models.rightsizing_proposal import RightsizingProposal, ProposalStatus
from backend.core.logger import logger

# Initialize Redis
from backend.core.redis_client import get_redis_client

router = APIRouter(prefix="/optimizer", tags=["optimizer-coordinator"])


def get_coordinator(db: Session = Depends(get_db)) -> OptimizerCoordinator:
    """Dependency to get optimizer coordinator instance."""
    redis = get_redis_client()
    return OptimizerCoordinator(db, redis)


@router.get("/status/{cluster_id}")
def get_optimizer_status(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator)
):
    """
    Get comprehensive optimizer status for a cluster.

    Returns current phase, capabilities, pending proposals, and cooldown status.

    Phases:
    - INITIAL_POOL_OPTIMIZATION: First 30-60 min after connection
    - STABILIZATION: Waiting period before rightsizing (≥1 hour)
    - RIGHTSIZING_EVALUATION: Rightsizing is proposing size changes
    - COMBINED_EXECUTION: Evaluating combined EV (Option A vs B vs C)
    - COOLDOWN: Post-execution cooldown (6h resize / 30min pool switch)
    """
    try:
        status = coordinator.get_cluster_status(cluster_id)
        return {
            "status": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"Failed to get optimizer status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate/{cluster_id}")
def trigger_combined_evaluation(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator),
    db: Session = Depends(get_db)
):
    """
    Manually trigger a combined optimization evaluation.

    This will:
    1. Check if rightsizing evaluation is allowed
    2. Generate rightsizing proposals (if any)
    3. Evaluate proposals using combined EV calculation
    4. Return results without executing (user must approve)

    Used for manual optimization checks outside the normal 24-hour cycle.
    """
    try:
        # Check if evaluation is allowed
        can_eval, reason = coordinator.can_run_rightsizing_evaluation(cluster_id)

        if not can_eval:
            return {
                "status": "blocked",
                "reason": reason,
                "can_evaluate": False
            }

        # Generate rightsizing proposals
        from backend.services.rightsizing_service import RightSizingService
        rightsizing_svc = RightSizingService(db)

        proposal_ids = rightsizing_svc.create_rightsizing_proposals(
            cluster_id=cluster_id,
            min_savings_pct=10.0,
            stability_window_hours=24
        )

        if not proposal_ids:
            return {
                "status": "success",
                "message": "No rightsizing opportunities found",
                "proposals_created": 0
            }

        # Record evaluation
        coordinator.record_rightsizing_evaluation(cluster_id, proposal_ids[0] if proposal_ids else None)

        # Evaluate first proposal
        if proposal_ids:
            result = coordinator.evaluate_combined_proposal(proposal_ids[0])

            return {
                "status": "success",
                "message": f"Created and evaluated {len(proposal_ids)} proposal(s)",
                "proposals_created": len(proposal_ids),
                "evaluation_result": result
            }

        return {
            "status": "success",
            "message": "Evaluation completed",
            "proposals_created": 0
        }

    except Exception as e:
        logger.error(f"Failed to trigger evaluation for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proposals/{cluster_id}")
def list_proposals(
    cluster_id: str,
    status: Optional[str] = Query(None, description="Filter by status: PENDING, APPROVED, REJECTED, EXECUTED"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List rightsizing proposals for a cluster.

    Returns all proposals with their evaluation results and status.
    """
    try:
        query = db.query(RightsizingProposal).filter(
            RightsizingProposal.cluster_id == cluster_id
        )

        if status:
            try:
                status_enum = ProposalStatus(status.upper())
                query = query.filter(RightsizingProposal.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        proposals = query.order_by(RightsizingProposal.created_at.desc()).all()

        return {
            "status": "success",
            "count": len(proposals),
            "proposals": [
                {
                    "id": p.id,
                    "status": p.status.value,
                    "current_instance_type": p.current_instance_type,
                    "proposed_instance_type": p.proposed_instance_type,
                    "savings_percentage": p.savings_percentage,
                    "estimated_monthly_savings": p.estimated_monthly_savings,
                    "estimated_hourly_savings": p.estimated_hourly_savings,
                    "created_at": p.created_at.isoformat(),
                    "evaluated_at": p.evaluated_at.isoformat() if p.evaluated_at else None,
                    "selected_option": p.selected_option,
                    "combined_ev_option_a": p.combined_ev_option_a,
                    "combined_ev_option_b": p.combined_ev_option_b,
                    "combined_ev_option_c": p.combined_ev_option_c,
                    "rejection_reason": p.rejection_reason,
                    # Task 8.1: EV breakdown from unified ev_model
                    "ev_breakdown": p.ev_breakdown,
                    "net_ev": p.net_ev,
                }
                for p in proposals
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list proposals for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator)
):
    """
    Approve and execute a rightsizing proposal.

    This will:
    1. Verify proposal is in APPROVED status (must be evaluated first)
    2. Execute the resize operation
    3. Activate 6-hour cooldown
    4. Transition cluster to COOLDOWN phase

    Requires EXECUTION permission.
    """
    try:
        # Execute approved proposal
        result = coordinator.execute_approved_proposal(proposal_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["reason"])

        return {
            "status": "success",
            "message": "Proposal executed successfully",
            "result": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    reason: str = Query(..., description="Reason for rejection"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually reject a rightsizing proposal.

    Used when user wants to override the coordinator's recommendation.
    """
    try:
        proposal = db.query(RightsizingProposal).filter(
            RightsizingProposal.id == proposal_id
        ).first()

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        if proposal.status == ProposalStatus.EXECUTED:
            raise HTTPException(status_code=400, detail="Cannot reject executed proposal")

        proposal.status = ProposalStatus.REJECTED
        proposal.rejection_reason = f"Manual rejection: {reason}"
        db.commit()

        logger.info(f"Proposal {proposal_id} manually rejected by user {current_user.email}")

        return {
            "status": "success",
            "message": "Proposal rejected"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comparison/{proposal_id}")
def get_ev_comparison(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed EV comparison breakdown for a proposal.

    Returns Option A vs B vs C analysis:
    - Option A: Current size + new pool (pool optimization only)
    - Option B: New size + best pool (combined optimization)
    - Option C: Do nothing (baseline)

    Includes EV calculation details, cost breakdown, and recommendation.
    """
    try:
        proposal = db.query(RightsizingProposal).filter(
            RightsizingProposal.id == proposal_id
        ).first()

        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")

        if not proposal.evaluation_breakdown:
            return {
                "status": "not_evaluated",
                "message": "Proposal has not been evaluated yet"
            }

        return {
            "status": "success",
            "proposal_id": proposal_id,
            "cluster_id": proposal.cluster_id,
            "evaluation_breakdown": proposal.evaluation_breakdown,
            "selected_option": proposal.selected_option,
            "recommendation": {
                "approved": proposal.status == ProposalStatus.APPROVED,
                "reason": proposal.rejection_reason if proposal.status == ProposalStatus.REJECTED else "Sufficient EV improvement"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get comparison for proposal {proposal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize/{cluster_id}")
def initialize_cluster_state(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator)
):
    """
    Initialize optimizer state for a newly connected cluster.

    Creates OptimizerState entry and sets phase to INITIAL_POOL_OPTIMIZATION.
    This is called automatically when a cluster connects, but can also be
    triggered manually.
    """
    try:
        state = coordinator.initialize_cluster_state(cluster_id)

        return {
            "status": "success",
            "message": "Optimizer state initialized",
            "data": {
                "cluster_id": cluster_id,
                "phase": state.current_phase.value,
                "phase_started_at": state.phase_started_at.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Failed to initialize state for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust-phase/{cluster_id}")
def get_trust_phase(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator)
):
    """
    Get progressive trust phase information for a cluster.

    Returns:
    - phase: 0 (0-30min), 1 (30-120min), or 2 (>2h)
    - rightsizing_allowed: bool
    - safety_buffer_pct: percentage buffer to apply
    - min_samples: minimum samples required for rightsizing
    - risk_ceiling_override: optional risk ceiling override
    - cluster_age_hours: hours since cluster connected
    - reason: explanation of current phase
    """
    try:
        trust_data = coordinator.get_cluster_trust_phase(cluster_id)

        # Get cluster age
        state = coordinator.get_or_create_state(cluster_id)
        from datetime import datetime
        if state.created_at:
            cluster_age_hours = (datetime.utcnow() - state.created_at).total_seconds() / 3600
        else:
            cluster_age_hours = 0

        trust_data["cluster_age_hours"] = round(cluster_age_hours, 2)

        return {
            "status": "success",
            "data": trust_data
        }

    except Exception as e:
        logger.error(f"Failed to get trust phase for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resize-guard/{cluster_id}")
def get_resize_guard_status(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator),
    db: Session = Depends(get_db)
):
    """
    Get resize guard monitoring status.

    Returns:
    - active: bool - whether guard is currently monitoring
    - recent_executions: count of executions in last 2 hours
    - monitoring_proposals: list of proposal IDs being monitored
    - last_check: timestamp of last guard check
    """
    try:
        from datetime import datetime, timedelta

        # Check for recent executions (last 2 hours)
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        recent_executions = db.query(RightsizingProposal).filter(
            RightsizingProposal.cluster_id == cluster_id,
            RightsizingProposal.status == ProposalStatus.EXECUTED,
            RightsizingProposal.executed_at >= two_hours_ago
        ).all()

        # Get rollback flags from Redis
        redis = get_redis_client()
        rollback_key = f"resize:rollback_needed:{cluster_id}"
        rollback_reason = redis.get(rollback_key)

        return {
            "status": "success",
            "data": {
                "active": len(recent_executions) > 0,
                "recent_executions": len(recent_executions),
                "monitoring_proposals": [p.id for p in recent_executions],
                "last_check": datetime.utcnow().isoformat(),
                "rollback_pending": rollback_reason is not None,
                "rollback_reason": rollback_reason.decode('utf-8') if rollback_reason else None
            }
        }

    except Exception as e:
        logger.error(f"Failed to get resize guard status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-breaker/{cluster_id}")
def get_circuit_breaker_status(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    coordinator: OptimizerCoordinator = Depends(get_coordinator)
):
    """
    Get circuit breaker status for resize operations.

    Returns:
    - is_open: bool - whether circuit breaker is open (blocking resizes)
    - failure_count: current failure count in 24h window
    - threshold: failure threshold before circuit opens (3)
    - time_until_reset: seconds until automatic reset (if open)
    """
    try:
        redis = get_redis_client()
        failure_key = f"resize:failure_count_24h:{cluster_id}"

        failure_count = int(redis.get(failure_key) or 0)
        is_open = failure_count >= 3

        # Get TTL for auto-reset time
        ttl = redis.ttl(failure_key)
        time_until_reset = ttl if ttl > 0 else None

        return {
            "status": "success",
            "data": {
                "is_open": is_open,
                "failure_count": failure_count,
                "threshold": 3,
                "time_until_reset": time_until_reset,
                "auto_reset_hours": 24
            }
        }

    except Exception as e:
        logger.error(f"Failed to get circuit breaker status for {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
