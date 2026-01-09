"""
Decision Engine (CORE-DECIDE)
Central decision-making and conflict resolution system

The Decision Engine is the brain of the Spot Optimizer platform. It receives
optimization opportunities from various modules and resolves conflicts to
generate a safe, coherent action plan.

Key Responsibilities:
- Conflict detection and resolution
- Policy enforcement
- Risk assessment
- Action prioritization
- Safety validation
- Approval workflow integration

Dependencies:
- Cluster policies for constraints
- ML Model Server for risk predictions
- Global Risk Tracker for pool safety
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database.models import (
    Cluster,
    ClusterPolicy,
    OptimizationJob,
    ActionLog
)
from app.modules.ml_model_server import get_ml_model_server
from app.modules.risk_tracker import get_risk_tracker
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of optimization actions"""
    SPOT_REPLACEMENT = "spot_replacement"
    RIGHT_SIZE = "right_size"
    CONSOLIDATE = "consolidate"
    HIBERNATE = "hibernate"
    SCALE_DOWN = "scale_down"
    SCALE_UP = "scale_up"


class ActionPriority(Enum):
    """Action priority levels"""
    CRITICAL = 1  # Must execute immediately
    HIGH = 2      # Should execute soon
    MEDIUM = 3    # Can wait
    LOW = 4       # Nice to have


class ConflictType(Enum):
    """Types of action conflicts"""
    SAME_RESOURCE = "same_resource"  # Two actions target same resource
    POLICY_VIOLATION = "policy_violation"  # Action violates policy
    DEPENDENCY = "dependency"  # Action depends on another
    RISK_TOO_HIGH = "risk_too_high"  # Risk exceeds threshold


class DecisionEngine:
    """
    Central decision-making and conflict resolution engine
    """

    def __init__(self, db: Session, redis_client=None):
        """
        Initialize Decision Engine

        Args:
            db: Database session
            redis_client: Optional Redis client
        """
        self.db = db
        self.redis_client = redis_client or get_redis_client()
        self.ml_model_server = get_ml_model_server(db, self.redis_client)
        self.risk_tracker = get_risk_tracker(db, self.redis_client)

    def evaluate_action_plan(
        self,
        cluster_id: str,
        proposed_actions: List[Dict[str, Any]],
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate proposed action plan and resolve conflicts

        This is the main entry point for the Decision Engine.

        Args:
            cluster_id: UUID of cluster
            proposed_actions: List of proposed optimization actions
            job_id: Optional optimization job ID

        Returns:
            Dict with approved actions and metadata
        """
        logger.info(
            f"[CORE-DECIDE] Evaluating {len(proposed_actions)} proposed actions "
            f"for cluster {cluster_id}"
        )

        # Get cluster and policy
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        policy = self.db.query(ClusterPolicy).filter(
            ClusterPolicy.cluster_id == cluster_id
        ).first()

        # Step 1: Validate each action against policy
        validated_actions = []
        rejected_actions = []

        for action in proposed_actions:
            is_valid, reason = self._validate_action(action, cluster, policy)

            if is_valid:
                validated_actions.append(action)
            else:
                logger.warning(f"[CORE-DECIDE] Rejected action: {reason}")
                action["rejection_reason"] = reason
                rejected_actions.append(action)

        logger.info(
            f"[CORE-DECIDE] Validated: {len(validated_actions)} actions, "
            f"Rejected: {len(rejected_actions)}"
        )

        # Step 2: Detect conflicts
        conflicts = self._detect_conflicts(validated_actions, cluster, policy)

        logger.info(f"[CORE-DECIDE] Detected {len(conflicts)} conflicts")

        # Step 3: Resolve conflicts
        resolved_actions = self._resolve_conflicts(
            validated_actions, conflicts, cluster, policy
        )

        logger.info(f"[CORE-DECIDE] Resolved to {len(resolved_actions)} actions")

        # Step 4: Prioritize actions
        prioritized_actions = self._prioritize_actions(resolved_actions, cluster, policy)

        # Step 5: Check approval requirements
        requires_approval = self._check_approval_required(prioritized_actions, policy)

        # Step 6: Generate execution plan
        execution_plan = self._generate_execution_plan(
            prioritized_actions, cluster, policy
        )

        result = {
            "cluster_id": cluster_id,
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "proposed": len(proposed_actions),
                "validated": len(validated_actions),
                "rejected": len(rejected_actions),
                "conflicts_detected": len(conflicts),
                "approved": len(prioritized_actions)
            },
            "requires_approval": requires_approval,
            "approved_actions": prioritized_actions,
            "rejected_actions": rejected_actions,
            "execution_plan": execution_plan
        }

        return result

    def _validate_action(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        policy: Optional[ClusterPolicy]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate single action against cluster policy

        Args:
            action: Proposed action
            cluster: Cluster record
            policy: Cluster policy (may be None)

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        action_type = action.get("type", "")

        # If no policy, allow all actions
        if not policy:
            return True, None

        # Check if action type is enabled
        if action_type == ActionType.SPOT_REPLACEMENT.value:
            if not policy.allow_spot_replacement:
                return False, "Spot replacement disabled by policy"

        elif action_type == ActionType.RIGHT_SIZE.value:
            if not policy.allow_rightsizing:
                return False, "Right-sizing disabled by policy"

        elif action_type == ActionType.CONSOLIDATE.value:
            if not policy.allow_consolidation:
                return False, "Consolidation disabled by policy"

        elif action_type == ActionType.HIBERNATE.value:
            if not policy.allow_hibernation:
                return False, "Hibernation disabled by policy"

        # Check risk threshold
        action_risk = action.get("risk_score", 0.0)
        if action_risk > policy.max_risk_threshold:
            return False, f"Risk score {action_risk} exceeds threshold {policy.max_risk_threshold}"

        # Check min nodes constraint
        if action_type in [ActionType.CONSOLIDATE.value, ActionType.SCALE_DOWN.value]:
            projected_nodes = action.get("projected_node_count", 0)
            if projected_nodes < policy.min_nodes:
                return False, f"Would violate min nodes constraint ({policy.min_nodes})"

        # Check max nodes constraint
        if action_type == ActionType.SCALE_UP.value:
            projected_nodes = action.get("projected_node_count", 0)
            if policy.max_nodes and projected_nodes > policy.max_nodes:
                return False, f"Would exceed max nodes constraint ({policy.max_nodes})"

        return True, None

    def _detect_conflicts(
        self,
        actions: List[Dict[str, Any]],
        cluster: Cluster,
        policy: Optional[ClusterPolicy]
    ) -> List[Dict[str, Any]]:
        """
        Detect conflicts between actions

        Args:
            actions: List of validated actions
            cluster: Cluster record
            policy: Cluster policy

        Returns:
            List of detected conflicts
        """
        conflicts = []

        # Check for same-resource conflicts
        for i, action1 in enumerate(actions):
            for j, action2 in enumerate(actions):
                if i >= j:
                    continue

                # Check if actions target same resource
                if self._targets_same_resource(action1, action2):
                    conflicts.append({
                        "type": ConflictType.SAME_RESOURCE.value,
                        "action1_index": i,
                        "action2_index": j,
                        "resource": action1.get("target_resource")
                    })

        # Check for dependency conflicts
        for i, action in enumerate(actions):
            dependencies = action.get("depends_on", [])
            for dep in dependencies:
                # Check if dependency action exists
                dep_exists = any(
                    a.get("id") == dep for a in actions
                )
                if not dep_exists:
                    conflicts.append({
                        "type": ConflictType.DEPENDENCY.value,
                        "action_index": i,
                        "missing_dependency": dep
                    })

        return conflicts

    def _targets_same_resource(
        self,
        action1: Dict[str, Any],
        action2: Dict[str, Any]
    ) -> bool:
        """
        Check if two actions target the same resource

        Args:
            action1: First action
            action2: Second action

        Returns:
            True if same resource targeted
        """
        resource1 = action1.get("target_resource")
        resource2 = action2.get("target_resource")

        if not resource1 or not resource2:
            return False

        # Same instance, node, or workload
        return resource1 == resource2

    def _resolve_conflicts(
        self,
        actions: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        cluster: Cluster,
        policy: Optional[ClusterPolicy]
    ) -> List[Dict[str, Any]]:
        """
        Resolve conflicts by choosing best action

        Args:
            actions: List of actions
            conflicts: List of conflicts
            cluster: Cluster record
            policy: Cluster policy

        Returns:
            List of conflict-resolved actions
        """
        if not conflicts:
            return actions

        # Track actions to remove
        removed_indices = set()

        for conflict in conflicts:
            conflict_type = conflict.get("type")

            if conflict_type == ConflictType.SAME_RESOURCE.value:
                # Choose action with higher priority
                idx1 = conflict["action1_index"]
                idx2 = conflict["action2_index"]

                action1 = actions[idx1]
                action2 = actions[idx2]

                # Compare estimated savings
                savings1 = action1.get("estimated_savings", 0)
                savings2 = action2.get("estimated_savings", 0)

                # Remove action with lower savings
                if savings1 >= savings2:
                    removed_indices.add(idx2)
                    logger.info(
                        f"[CORE-DECIDE] Conflict resolved: Chose action {idx1} "
                        f"over {idx2} (higher savings)"
                    )
                else:
                    removed_indices.add(idx1)
                    logger.info(
                        f"[CORE-DECIDE] Conflict resolved: Chose action {idx2} "
                        f"over {idx1} (higher savings)"
                    )

            elif conflict_type == ConflictType.DEPENDENCY.value:
                # Remove action with missing dependency
                idx = conflict["action_index"]
                removed_indices.add(idx)
                logger.info(
                    f"[CORE-DECIDE] Conflict resolved: Removed action {idx} "
                    f"(missing dependency)"
                )

        # Filter out removed actions
        resolved = [
            action for i, action in enumerate(actions)
            if i not in removed_indices
        ]

        return resolved

    def _prioritize_actions(
        self,
        actions: List[Dict[str, Any]],
        cluster: Cluster,
        policy: Optional[ClusterPolicy]
    ) -> List[Dict[str, Any]]:
        """
        Prioritize actions by urgency and impact

        Args:
            actions: List of actions
            cluster: Cluster record
            policy: Cluster policy

        Returns:
            List of prioritized actions (sorted)
        """
        # Assign priority to each action
        for action in actions:
            # Priority based on:
            # 1. Action type urgency
            # 2. Estimated savings
            # 3. Risk level

            action_type = action.get("type")
            savings = action.get("estimated_savings", 0)
            risk = action.get("risk_score", 0.5)

            if action_type == ActionType.SPOT_REPLACEMENT.value:
                # High savings, medium urgency
                base_priority = ActionPriority.HIGH.value
            elif action_type == ActionType.CONSOLIDATE.value:
                # Medium savings, low urgency
                base_priority = ActionPriority.MEDIUM.value
            elif action_type == ActionType.RIGHT_SIZE.value:
                # Varied savings, medium urgency
                base_priority = ActionPriority.MEDIUM.value
            else:
                base_priority = ActionPriority.LOW.value

            # Adjust by savings (higher savings = higher priority)
            if savings > 100:
                priority = base_priority - 1
            elif savings < 20:
                priority = base_priority + 1
            else:
                priority = base_priority

            # Adjust by risk (higher risk = lower priority)
            if risk > 0.7:
                priority += 1

            # Clamp to valid range
            priority = max(1, min(4, priority))

            action["priority"] = priority
            action["priority_label"] = ActionPriority(priority).name

        # Sort by priority (ascending = higher priority first)
        sorted_actions = sorted(actions, key=lambda a: a["priority"])

        return sorted_actions

    def _check_approval_required(
        self,
        actions: List[Dict[str, Any]],
        policy: Optional[ClusterPolicy]
    ) -> bool:
        """
        Check if manual approval is required

        Args:
            actions: List of actions
            policy: Cluster policy

        Returns:
            True if approval required
        """
        if not policy:
            return False

        # Check policy requirement
        if policy.require_approval:
            return True

        # Check if any high-risk action
        for action in actions:
            if action.get("risk_score", 0) > 0.8:
                return True

            # Check for destructive actions
            if action.get("type") in [
                ActionType.CONSOLIDATE.value,
                ActionType.HIBERNATE.value
            ]:
                return True

        return False

    def _generate_execution_plan(
        self,
        actions: List[Dict[str, Any]],
        cluster: Cluster,
        policy: Optional[ClusterPolicy]
    ) -> Dict[str, Any]:
        """
        Generate phased execution plan

        Args:
            actions: List of prioritized actions
            cluster: Cluster record
            policy: Cluster policy

        Returns:
            Dict with execution plan
        """
        # Group actions into phases
        phases = []

        # Phase 1: Critical actions (execute immediately)
        critical = [a for a in actions if a["priority"] == ActionPriority.CRITICAL.value]
        if critical:
            phases.append({
                "phase": 1,
                "name": "Critical Actions",
                "actions": critical,
                "delay_seconds": 0
            })

        # Phase 2: High priority actions
        high = [a for a in actions if a["priority"] == ActionPriority.HIGH.value]
        if high:
            phases.append({
                "phase": 2,
                "name": "High Priority Actions",
                "actions": high,
                "delay_seconds": 60  # 1 minute after Phase 1
            })

        # Phase 3: Medium priority actions
        medium = [a for a in actions if a["priority"] == ActionPriority.MEDIUM.value]
        if medium:
            phases.append({
                "phase": 3,
                "name": "Medium Priority Actions",
                "actions": medium,
                "delay_seconds": 300  # 5 minutes after Phase 1
            })

        # Phase 4: Low priority actions
        low = [a for a in actions if a["priority"] == ActionPriority.LOW.value]
        if low:
            phases.append({
                "phase": 4,
                "name": "Low Priority Actions",
                "actions": low,
                "delay_seconds": 600  # 10 minutes after Phase 1
            })

        return {
            "total_phases": len(phases),
            "total_actions": len(actions),
            "estimated_duration_seconds": max(
                (p["delay_seconds"] for p in phases), default=0
            ) + 60,
            "phases": phases
        }


def get_decision_engine(db: Session, redis_client=None) -> DecisionEngine:
    """
    Factory function to create Decision Engine instance

    Args:
        db: Database session
        redis_client: Optional Redis client

    Returns:
        DecisionEngine instance
    """
    return DecisionEngine(db, redis_client)
