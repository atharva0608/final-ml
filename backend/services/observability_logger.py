"""
Observability Logger — Deterministic Decision Audit Trail
=========================================================
Implements problems.md §10: Every decision logs risk components,
EV breakdown, guardrail passes/failures, state transitions, and
execution outcomes. System is replayable from stored snapshots.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ObservabilityLogger:
    """
    Structured logger for all optimizer decisions.
    Writes to both application logger (JSON) and audit DB table if available.
    """

    def __init__(self, db: Optional[Session] = None, redis_client=None):
        self.db = db
        self.redis = redis_client

    def log_decision(
        self,
        cluster_id: str,
        decision_type: str,
        approved: bool,
        reason: str,
        risk_components: Optional[Dict] = None,
        ev_breakdown: Optional[Dict] = None,
        guardrail_results: Optional[Dict] = None,
        state_transition: Optional[Dict] = None,
        market_snapshot: Optional[Dict] = None,
        execution_result: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Log a full optimization decision with all explainable components.

        Returns a decision_id for correlation.
        """
        decision_id = f"{cluster_id[:8]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"

        record = {
            "decision_id": decision_id,
            "cluster_id": cluster_id,
            "decision_type": decision_type,
            "approved": approved,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "risk_components": risk_components or {},
            "ev_breakdown": ev_breakdown or {},
            "guardrail_results": guardrail_results or {},
            "state_transition": state_transition or {},
            "market_snapshot": market_snapshot or {},
            "execution_result": execution_result or {},
            "metadata": metadata or {},
        }

        # Structured JSON log (always)
        logger.info(json.dumps({
            "event": "optimizer_decision",
            **record,
        }))

        # Cache in Redis (last 100 decisions per cluster, 24h TTL)
        if self.redis:
            try:
                key = f"obs:decisions:{cluster_id}"
                self.redis.lpush(key, json.dumps(record))
                self.redis.ltrim(key, 0, 99)  # Keep only last 100
                self.redis.expire(key, 86400)
            except Exception as e:
                logger.warning(f"[ObsLogger] Redis write failed: {e}")

        # Persist to DB audit log if available
        if self.db:
            try:
                self._persist_to_db(record)
            except Exception as e:
                logger.warning(f"[ObsLogger] DB persist failed: {e}")

        return decision_id

    def log_state_transition(
        self,
        cluster_id: str,
        from_state: str,
        to_state: str,
        trigger: str,
        context: Optional[Dict] = None,
    ):
        """Log a circuit breaker or phase state transition."""
        self.log_decision(
            cluster_id=cluster_id,
            decision_type="STATE_TRANSITION",
            approved=True,
            reason=f"{from_state} → {to_state}: {trigger}",
            state_transition={
                "from": from_state,
                "to": to_state,
                "trigger": trigger,
                "context": context or {},
            },
        )

    def log_guardrail_block(
        self,
        cluster_id: str,
        violations: List[str],
        proposed_action: str,
    ):
        """Log a guardrail block event."""
        self.log_decision(
            cluster_id=cluster_id,
            decision_type="GUARDRAIL_BLOCK",
            approved=False,
            reason=f"Blocked by {len(violations)} guardrail(s)",
            guardrail_results={"violations": violations, "proposed_action": proposed_action},
        )

    def log_pool_switch(
        self,
        cluster_id: str,
        from_pool: Dict,
        to_pool: Dict,
        risk_components: Dict,
        ev_breakdown: Dict,
        approved: bool,
        reason: str,
    ):
        """Log a pool switch decision with full context."""
        self.log_decision(
            cluster_id=cluster_id,
            decision_type="POOL_SWITCH",
            approved=approved,
            reason=reason,
            risk_components=risk_components,
            ev_breakdown=ev_breakdown,
            metadata={"from_pool": from_pool, "to_pool": to_pool},
        )

    def log_rightsizing_proposal(
        self,
        cluster_id: str,
        proposal_id: str,
        option_selected: str,
        ev_breakdown: Dict,
        approved: bool,
        reason: str,
    ):
        """Log a right-sizing proposal evaluation."""
        self.log_decision(
            cluster_id=cluster_id,
            decision_type="RIGHTSIZING_PROPOSAL",
            approved=approved,
            reason=reason,
            ev_breakdown=ev_breakdown,
            metadata={"proposal_id": proposal_id, "option_selected": option_selected},
        )

    def get_recent_decisions(self, cluster_id: str, limit: int = 20) -> List[Dict]:
        """Retrieve recent decisions from Redis cache."""
        if not self.redis:
            return []
        try:
            key = f"obs:decisions:{cluster_id}"
            raw_list = self.redis.lrange(key, 0, limit - 1)
            return [json.loads(r) for r in raw_list]
        except Exception as e:
            logger.warning(f"[ObsLogger] Redis read failed: {e}")
            return []

    def _persist_to_db(self, record: Dict):
        """Persist decision record to audit_logs table if model available."""
        try:
            from backend.models.audit_log import AuditLog
            log_entry = AuditLog(
                action=record["decision_type"],
                resource_type="cluster",
                resource_id=record["cluster_id"],
                details=json.dumps({
                    "decision_id": record["decision_id"],
                    "approved": record["approved"],
                    "reason": record["reason"],
                    "risk_components": record.get("risk_components", {}),
                    "ev_breakdown": record.get("ev_breakdown", {}),
                }),
            )
            self.db.add(log_entry)
            self.db.commit()
        except Exception as e:
            logger.debug(f"[ObsLogger] AuditLog persist error: {e}")
