"""
Policy Service

Business logic for cluster optimization policy management
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, or_
from backend.models.cluster_policy import ClusterPolicy
from backend.models.cluster import Cluster
from backend.models.node_template import NodeTemplate
from backend.models.account import Account
from backend.schemas.policy_schemas import (
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicyList,
    PolicyFilter,
)
from backend.core.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ValidationError,
)
from backend.core.validators import validate_percentage
from backend.core.logger import StructuredLogger
from datetime import datetime
import uuid

logger = StructuredLogger(__name__)


class PolicyService:
    """Service for cluster optimization policy management"""

    def __init__(self, db: Session):
        self.db = db

    def create_policy(
        self,
        user_id: str,
        policy_data: PolicyCreate
    ) -> PolicyResponse:
        """
        Create a new optimization policy

        Args:
            user_id: User UUID
            policy_data: Policy creation data

        Returns:
            PolicyResponse with created policy

        Raises:
            ResourceNotFoundError: If cluster or template not found
            ResourceAlreadyExistsError: If policy already exists for cluster
            ValidationError: If validation fails
        """
        # Verify cluster belongs to user
        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == policy_data.cluster_id,
                Account.user_id == user_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", policy_data.cluster_id)

        # Verify template belongs to user
        template = self.db.query(NodeTemplate).filter(
            and_(
                NodeTemplate.id == policy_data.template_id,
                NodeTemplate.user_id == user_id
            )
        ).first()

        if not template:
            raise ResourceNotFoundError("NodeTemplate", policy_data.template_id)

        # Check for existing policy on this cluster
        existing = self.db.query(ClusterPolicy).filter(
            ClusterPolicy.cluster_id == policy_data.cluster_id
        ).first()

        if existing:
            raise ResourceAlreadyExistsError(
                "ClusterPolicy",
                f"cluster {cluster.name}"
            )

        # Validate percentages
        if not validate_percentage(policy_data.spot_percentage):
            raise ValidationError(
                f"spot_percentage must be between 0 and 100, got {policy_data.spot_percentage}"
            )

        # Validate min/max nodes
        if policy_data.min_nodes < 0:
            raise ValidationError(f"min_nodes cannot be negative: {policy_data.min_nodes}")
        if policy_data.max_nodes < policy_data.min_nodes:
            raise ValidationError(
                f"max_nodes ({policy_data.max_nodes}) must be >= min_nodes ({policy_data.min_nodes})"
            )

        # Create policy
        new_policy = ClusterPolicy(
            id=str(uuid.uuid4()),
            cluster_id=policy_data.cluster_id,
            template_id=policy_data.template_id,
            spot_percentage=policy_data.spot_percentage,
            fallback_to_on_demand=policy_data.fallback_to_on_demand,
            max_price_per_hour=policy_data.max_price_per_hour,
            diversification_enabled=policy_data.diversification_enabled,
            min_nodes=policy_data.min_nodes,
            max_nodes=policy_data.max_nodes,
            target_cpu_utilization=policy_data.target_cpu_utilization,
            target_memory_utilization=policy_data.target_memory_utilization,
            scale_down_cooldown_minutes=policy_data.scale_down_cooldown_minutes,
            is_active=policy_data.is_active,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_policy)
        self.db.commit()
        self.db.refresh(new_policy)

        logger.info(
            "Policy created",
            policy_id=new_policy.id,
            cluster_id=policy_data.cluster_id,
            template_id=policy_data.template_id,
            spot_percentage=policy_data.spot_percentage,
            user_id=user_id
        )

        return self._to_response(new_policy)

    def get_policy(self, policy_id: str, user_id: str) -> PolicyResponse:
        """
        Get policy by ID

        Args:
            policy_id: Policy UUID
            user_id: User UUID

        Returns:
            PolicyResponse

        Raises:
            ResourceNotFoundError: If policy not found
        """
        policy = self.db.query(ClusterPolicy).join(Cluster).join(Account).filter(
            and_(
                ClusterPolicy.id == policy_id,
                Account.user_id == user_id
            )
        ).first()

        if not policy:
            raise ResourceNotFoundError("ClusterPolicy", policy_id)

        return self._to_response(policy)

    def get_policy_by_cluster(
        self,
        cluster_id: str,
        user_id: str
    ) -> Optional[PolicyResponse]:
        """
        Get policy for a specific cluster

        Args:
            cluster_id: Cluster UUID
            user_id: User UUID

        Returns:
            PolicyResponse or None

        Raises:
            ResourceNotFoundError: If cluster not found
        """
        # Verify cluster belongs to user
        cluster = self.db.query(Cluster).join(Account).filter(
            and_(
                Cluster.id == cluster_id,
                Account.user_id == user_id
            )
        ).first()

        if not cluster:
            raise ResourceNotFoundError("Cluster", cluster_id)

        policy = self.db.query(ClusterPolicy).filter(
            ClusterPolicy.cluster_id == cluster_id
        ).first()

        if not policy:
            return None

        return self._to_response(policy)

    def list_policies(
        self,
        user_id: str,
        filters: PolicyFilter
    ) -> PolicyList:
        """
        List policies with filters and pagination

        Args:
            user_id: User UUID
            filters: Filter criteria

        Returns:
            PolicyList with paginated results
        """
        query = self.db.query(ClusterPolicy).join(Cluster).join(Account).filter(
            Account.user_id == user_id
        )

        # Apply filters
        if filters.cluster_id:
            query = query.filter(ClusterPolicy.cluster_id == filters.cluster_id)
        if filters.template_id:
            query = query.filter(ClusterPolicy.template_id == filters.template_id)
        if filters.is_active is not None:
            query = query.filter(
                ClusterPolicy.is_active == ("Y" if filters.is_active else "N")
            )
        if filters.min_spot_percentage is not None:
            query = query.filter(
                ClusterPolicy.spot_percentage >= filters.min_spot_percentage
            )

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        policies = query.order_by(desc(ClusterPolicy.created_at)).offset(
            (filters.page - 1) * filters.page_size
        ).limit(filters.page_size).all()

        # Convert to response schemas
        policy_responses = [self._to_response(policy) for policy in policies]

        return PolicyList(
            policies=policy_responses,
            total=total,
            page=filters.page,
            page_size=filters.page_size
        )

    def update_policy(
        self,
        policy_id: str,
        user_id: str,
        update_data: PolicyUpdate
    ) -> PolicyResponse:
        """
        Update policy

        Args:
            policy_id: Policy UUID
            user_id: User UUID
            update_data: Update data

        Returns:
            Updated PolicyResponse

        Raises:
            ResourceNotFoundError: If policy or template not found
            ValidationError: If validation fails
        """
        policy = self.db.query(ClusterPolicy).join(Cluster).join(Account).filter(
            and_(
                ClusterPolicy.id == policy_id,
                Account.user_id == user_id
            )
        ).first()

        if not policy:
            raise ResourceNotFoundError("ClusterPolicy", policy_id)

        # Validate updates
        update_dict = update_data.model_dump(exclude_unset=True)

        if "template_id" in update_dict:
            template = self.db.query(NodeTemplate).filter(
                and_(
                    NodeTemplate.id == update_dict["template_id"],
                    NodeTemplate.user_id == user_id
                )
            ).first()
            if not template:
                raise ResourceNotFoundError("NodeTemplate", update_dict["template_id"])

        if "spot_percentage" in update_dict:
            if not validate_percentage(update_dict["spot_percentage"]):
                raise ValidationError(
                    f"spot_percentage must be between 0 and 100, got {update_dict['spot_percentage']}"
                )

        if "min_nodes" in update_dict or "max_nodes" in update_dict:
            min_nodes = update_dict.get("min_nodes", policy.min_nodes)
            max_nodes = update_dict.get("max_nodes", policy.max_nodes)
            if max_nodes < min_nodes:
                raise ValidationError(
                    f"max_nodes ({max_nodes}) must be >= min_nodes ({min_nodes})"
                )

        # Apply updates
        for field, value in update_dict.items():
            setattr(policy, field, value)

        policy.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(policy)

        logger.info(
            "Policy updated",
            policy_id=policy_id,
            updated_fields=list(update_dict.keys()),
            user_id=user_id
        )

        return self._to_response(policy)

    def delete_policy(self, policy_id: str, user_id: str) -> bool:
        """
        Delete policy

        Args:
            policy_id: Policy UUID
            user_id: User UUID

        Returns:
            True if deleted

        Raises:
            ResourceNotFoundError: If policy not found
        """
        policy = self.db.query(ClusterPolicy).join(Cluster).join(Account).filter(
            and_(
                ClusterPolicy.id == policy_id,
                Account.user_id == user_id
            )
        ).first()

        if not policy:
            raise ResourceNotFoundError("ClusterPolicy", policy_id)

        cluster_name = policy.cluster.name

        self.db.delete(policy)
        self.db.commit()

        logger.info(
            "Policy deleted",
            policy_id=policy_id,
            cluster_name=cluster_name,
            user_id=user_id
        )

        return True

    def toggle_policy(self, policy_id: str, user_id: str) -> PolicyResponse:
        """
        Toggle policy active status

        Args:
            policy_id: Policy UUID
            user_id: User UUID

        Returns:
            Updated PolicyResponse

        Raises:
            ResourceNotFoundError: If policy not found
        """
        policy = self.db.query(ClusterPolicy).join(Cluster).join(Account).filter(
            and_(
                ClusterPolicy.id == policy_id,
                Account.user_id == user_id
            )
        ).first()

        if not policy:
            raise ResourceNotFoundError("ClusterPolicy", policy_id)

        # Toggle active status
        policy.is_active = "N" if policy.is_active == "Y" else "Y"
        policy.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(policy)

        logger.info(
            "Policy toggled",
            policy_id=policy_id,
            is_active=policy.is_active == "Y",
            user_id=user_id
        )

        return self._to_response(policy)

    def _to_response(self, policy: ClusterPolicy) -> PolicyResponse:
        """
        Convert ClusterPolicy model to PolicyResponse schema

        Args:
            policy: ClusterPolicy model

        Returns:
            PolicyResponse schema
        """
        return PolicyResponse(
            id=policy.id,
            cluster_id=policy.cluster_id,
            template_id=policy.template_id,
            spot_percentage=policy.spot_percentage,
            fallback_to_on_demand=policy.fallback_to_on_demand == "Y",
            max_price_per_hour=policy.max_price_per_hour,
            diversification_enabled=policy.diversification_enabled == "Y",
            min_nodes=policy.min_nodes,
            max_nodes=policy.max_nodes,
            target_cpu_utilization=policy.target_cpu_utilization,
            target_memory_utilization=policy.target_memory_utilization,
            scale_down_cooldown_minutes=policy.scale_down_cooldown_minutes,
            is_active=policy.is_active == "Y",
            created_at=policy.created_at,
            updated_at=policy.updated_at
        )


def get_policy_service(db: Session) -> PolicyService:
    """Get policy service instance"""
    return PolicyService(db)
