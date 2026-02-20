"""
Node Template Service

Business logic for managing node templates (instance type families, architectures, strategies)
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from backend.models.node_template import NodeTemplate
from backend.schemas.template_schemas import (
    NodeTemplateCreate,
    NodeTemplateUpdate,
    NodeTemplateResponse,
    NodeTemplateList,
)
from backend.core.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ResourceConflictError,
)
from backend.core.logger import StructuredLogger
from datetime import datetime

logger = StructuredLogger(__name__)


class TemplateService:
    """Service for node template management"""

    def __init__(self, db: Session):
        self.db = db

    def list_templates(self, user_id: str) -> NodeTemplateList:
        """
        List all templates for a user

        Args:
            user_id: User UUID

        Returns:
            NodeTemplateList with all user templates
        """
        templates = self.db.query(NodeTemplate).filter(
            NodeTemplate.user_id == user_id
        ).order_by(NodeTemplate.is_default.desc(), NodeTemplate.created_at.desc()).all()

        template_responses = [
            NodeTemplateResponse(
                id=t.id,
                user_id=t.user_id,
                name=t.name,
                families=t.families,
                architecture=t.architecture,
                strategy=t.strategy.value,
                disk_type=t.disk_type.value,
                disk_size=t.disk_size,
                is_default=(t.is_default == "Y"),
                last_used_by_atharva_at=t.last_used_by_atharva_at,
                atharva_rankings_count=t.atharva_rankings_count or 0,
                created_at=t.created_at,
                updated_at=t.updated_at
            )
            for t in templates
        ]

        return NodeTemplateList(
            templates=template_responses,
            total=len(template_responses)
        )

    def get_template(self, template_id: str, user_id: str) -> NodeTemplateResponse:
        """
        Get a specific template

        Args:
            template_id: Template UUID
            user_id: User UUID

        Returns:
            NodeTemplateResponse

        Raises:
            ResourceNotFoundError: If template not found
        """
        template = self.db.query(NodeTemplate).filter(
            and_(
                NodeTemplate.id == template_id,
                NodeTemplate.user_id == user_id
            )
        ).first()

        if not template:
            raise ResourceNotFoundError("NodeTemplate", template_id)

        return NodeTemplateResponse(
            id=template.id,
            user_id=template.user_id,
            name=template.name,
            families=template.families,
            architecture=template.architecture,
            strategy=template.strategy.value,
            disk_type=template.disk_type.value,
            disk_size=template.disk_size,
            is_default=(template.is_default == "Y"),
            last_used_by_atharva_at=template.last_used_by_atharva_at,
            atharva_rankings_count=template.atharva_rankings_count or 0,
            created_at=template.created_at,
            updated_at=template.updated_at
        )

    def create_template(
        self,
        user_id: str,
        template_data: NodeTemplateCreate
    ) -> NodeTemplateResponse:
        """
        Create a new node template

        Args:
            user_id: User UUID
            template_data: Template creation data

        Returns:
            NodeTemplateResponse

        Raises:
            ResourceAlreadyExistsError: If template name already exists for user
        """
        # Check for duplicate name
        existing = self.db.query(NodeTemplate).filter(
            and_(
                NodeTemplate.user_id == user_id,
                NodeTemplate.name == template_data.name
            )
        ).first()

        if existing:
            raise ResourceAlreadyExistsError(
                "NodeTemplate",
                template_data.name,
                f"A template named '{template_data.name}' already exists"
            )

        # If this should be default, unset other defaults
        if template_data.is_default:
            self.db.query(NodeTemplate).filter(
                NodeTemplate.user_id == user_id
            ).update({"is_default": "N"})

        # Create template
        new_template = NodeTemplate(
            user_id=user_id,
            name=template_data.name,
            families=template_data.families,
            architecture=template_data.architecture,
            strategy=template_data.strategy,
            disk_type=template_data.disk_type,
            disk_size=template_data.disk_size,
            is_default="Y" if template_data.is_default else "N",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_template)
        self.db.commit()
        self.db.refresh(new_template)

        # Invalidate AtharvaAI cache
        self._invalidate_atharva_cache(user_id)

        logger.info(
            "Template created",
            template_id=new_template.id,
            user_id=user_id,
            name=template_data.name
        )

        return NodeTemplateResponse(
            id=new_template.id,
            user_id=new_template.user_id,
            name=new_template.name,
            families=new_template.families,
            architecture=new_template.architecture,
            strategy=new_template.strategy.value,
            disk_type=new_template.disk_type.value,
            disk_size=new_template.disk_size,
            is_default=(new_template.is_default == "Y"),
            last_used_by_atharva_at=new_template.last_used_by_atharva_at,
            atharva_rankings_count=new_template.atharva_rankings_count or 0,
            created_at=new_template.created_at,
            updated_at=new_template.updated_at
        )

    def update_template(
        self,
        template_id: str,
        user_id: str,
        template_data: NodeTemplateUpdate
    ) -> NodeTemplateResponse:
        """
        Update a template

        Args:
            template_id: Template UUID
            user_id: User UUID
            template_data: Template update data

        Returns:
            NodeTemplateResponse

        Raises:
            ResourceNotFoundError: If template not found
        """
        template = self.db.query(NodeTemplate).filter(
            and_(
                NodeTemplate.id == template_id,
                NodeTemplate.user_id == user_id
            )
        ).first()

        if not template:
            raise ResourceNotFoundError("NodeTemplate", template_id)

        # Update fields
        if template_data.name is not None:
            template.name = template_data.name
        if template_data.families is not None:
            template.families = template_data.families
        if template_data.architecture is not None:
            template.architecture = template_data.architecture
        if template_data.strategy is not None:
            template.strategy = template_data.strategy
        if template_data.disk_type is not None:
            template.disk_type = template_data.disk_type
        if template_data.disk_size is not None:
            template.disk_size = template_data.disk_size
        if template_data.is_default is not None:
            if template_data.is_default:
                # Unset other defaults
                self.db.query(NodeTemplate).filter(
                    and_(
                        NodeTemplate.user_id == user_id,
                        NodeTemplate.id != template_id
                    )
                ).update({"is_default": "N"})
            template.is_default = "Y" if template_data.is_default else "N"

        template.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(template)

        # Invalidate AtharvaAI cache
        self._invalidate_atharva_cache(user_id)

        logger.info(
            "Template updated",
            template_id=template_id,
            user_id=user_id
        )

        return NodeTemplateResponse(
            id=template.id,
            user_id=template.user_id,
            name=template.name,
            families=template.families,
            architecture=template.architecture,
            strategy=template.strategy.value,
            disk_type=template.disk_type.value,
            disk_size=template.disk_size,
            is_default=(template.is_default == "Y"),
            last_used_by_atharva_at=template.last_used_by_atharva_at,
            atharva_rankings_count=template.atharva_rankings_count or 0,
            created_at=template.created_at,
            updated_at=template.updated_at
        )

    def delete_template(self, template_id: str, user_id: str) -> bool:
        """
        Delete a template

        Args:
            template_id: Template UUID
            user_id: User UUID

        Returns:
            True if deleted

        Raises:
            ResourceNotFoundError: If template not found
            ResourceConflictError: If template is default and only one exists
        """
        template = self.db.query(NodeTemplate).filter(
            and_(
                NodeTemplate.id == template_id,
                NodeTemplate.user_id == user_id
            )
        ).first()

        if not template:
            raise ResourceNotFoundError("NodeTemplate", template_id)

        # Check if this is the last template
        template_count = self.db.query(NodeTemplate).filter(
            NodeTemplate.user_id == user_id
        ).count()

        if template_count == 1:
            raise ResourceConflictError(
                "Cannot delete the last template. At least one template must exist."
            )

        # If deleting default template, set another as default
        if template.is_default == "Y":
            other_template = self.db.query(NodeTemplate).filter(
                and_(
                    NodeTemplate.user_id == user_id,
                    NodeTemplate.id != template_id
                )
            ).first()
            if other_template:
                other_template.is_default = "Y"

        self.db.delete(template)
        self.db.commit()

        logger.info(
            "Template deleted",
            template_id=template_id,
            user_id=user_id
        )

        return True

    def set_default(self, template_id: str, user_id: str) -> NodeTemplateResponse:
        """
        Set a template as default

        Args:
            template_id: Template UUID
            user_id: User UUID

        Returns:
            NodeTemplateResponse

        Raises:
            ResourceNotFoundError: If template not found
        """
        template = self.db.query(NodeTemplate).filter(
            and_(
                NodeTemplate.id == template_id,
                NodeTemplate.user_id == user_id
            )
        ).first()

        if not template:
            raise ResourceNotFoundError("NodeTemplate", template_id)

        # Unset all other defaults
        self.db.query(NodeTemplate).filter(
            NodeTemplate.user_id == user_id
        ).update({"is_default": "N"})

        # Set this as default
        template.is_default = "Y"
        template.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(template)

        # Invalidate AtharvaAI cache
        self._invalidate_atharva_cache(user_id)

        logger.info(
            "Template set as default",
            template_id=template_id,
            user_id=user_id
        )

        return NodeTemplateResponse(
            id=template.id,
            user_id=template.user_id,
            name=template.name,
            families=template.families,
            architecture=template.architecture,
            strategy=template.strategy.value,
            disk_type=template.disk_type.value,
            disk_size=template.disk_size,
            is_default=True,
            created_at=template.created_at,
            updated_at=template.updated_at
        )

    def get_default_template(self, user_id: str, track_atharva_usage: bool = False):
        """
        Get the default template for a user

        Args:
            user_id: User UUID
            track_atharva_usage: If True, updates last_used_by_atharva_at and increments counter

        Returns:
            NodeTemplate or None
        """
        template = self.db.query(NodeTemplate).filter(
            NodeTemplate.user_id == user_id,
            NodeTemplate.is_default == "Y"
        ).first()

        # Update usage tracking if requested (when used by AtharvaAI)
        if template and track_atharva_usage:
            template.last_used_by_atharva_at = datetime.utcnow()
            template.atharva_rankings_count = (template.atharva_rankings_count or 0) + 1
            self.db.commit()
            logger.info(
                "Template usage tracked",
                template_id=template.id,
                user_id=user_id,
                usage_count=template.atharva_rankings_count
            )

        return template

    def _invalidate_atharva_cache(self, user_id: str):
        """Invalidate AtharvaAI Redis cache when template changes"""
        try:
            import redis
            from backend.core.config import settings
            r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            # Delete cached rankings for this user
            cache_pattern = f"atharva_rankings:{user_id}:*"
            keys = r.keys(cache_pattern)
            if keys:
                r.delete(*keys)
                logger.info(f"Invalidated {len(keys)} AtharvaAI cache entries for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to invalidate AtharvaAI cache: {e}")

    def get_template_options(self):
        """
        Returns available options for building a node template.
        Groups instance families by category with metadata.
        """
        return {
            "architectures": [
                {"value": "x86_64", "label": "x86_64 (AMD64)", "description": "Intel/AMD processors"},
                {"value": "arm64", "label": "ARM64 (Graviton)", "description": "AWS Graviton processors, ~20% cheaper"}
            ],
            "disk_types": [
                {"value": "GP3", "label": "General Purpose SSD (GP3)", "iops": "3000-16000", "throughput": "125-1000 MB/s"},
                {"value": "GP2", "label": "General Purpose SSD (GP2)", "iops": "100-16000", "throughput": "128-250 MB/s"},
                {"value": "IO1", "label": "Provisioned IOPS (IO1)", "iops": "100-64000", "throughput": "256-1000 MB/s"},
                {"value": "IO2", "label": "Provisioned IOPS (IO2)", "iops": "100-64000", "throughput": "256-4000 MB/s"}
            ],
            "strategies": [
                {"value": "CHEAPEST", "label": "Cheapest", "description": "Minimize cost, higher interruption risk"},
                {"value": "BALANCED", "label": "Balanced", "description": "Balance cost and stability"},
                {"value": "PERFORMANCE", "label": "Performance", "description": "Maximize performance, higher cost"}
            ],
            "instance_families": {
                "general_purpose": [
                    {"family": "t3", "arch": ["x86_64"], "generation": 3, "vcpu_range": "2-8", "memory_range": "0.5-32 GB", "burstable": True},
                    {"family": "t3a", "arch": ["x86_64"], "generation": 3, "vcpu_range": "2-8", "memory_range": "0.5-32 GB", "burstable": True},
                    {"family": "t4g", "arch": ["arm64"], "generation": 4, "vcpu_range": "2-8", "memory_range": "0.5-32 GB", "burstable": True},
                    {"family": "m5", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", "memory_range": "8-384 GB", "burstable": False},
                    {"family": "m5a", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", "memory_range": "8-384 GB", "burstable": False},
                    {"family": "m6i", "arch": ["x86_64"], "generation": 6, "vcpu_range": "2-128", "memory_range": "8-512 GB", "burstable": False},
                    {"family": "m6g", "arch": ["arm64"], "generation": 6, "vcpu_range": "2-64", "memory_range": "8-256 GB", "burstable": False},
                    {"family": "m7i", "arch": ["x86_64"], "generation": 7, "vcpu_range": "2-192", "memory_range": "8-768 GB", "burstable": False},
                    {"family": "m7g", "arch": ["arm64"], "generation": 7, "vcpu_range": "2-64", "memory_range": "8-256 GB", "burstable": False}
                ],
                "compute_optimized": [
                    {"family": "c5", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", "memory_range": "4-192 GB", "burstable": False},
                    {"family": "c5a", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", "memory_range": "4-192 GB", "burstable": False},
                    {"family": "c6i", "arch": ["x86_64"], "generation": 6, "vcpu_range": "2-128", "memory_range": "4-256 GB", "burstable": False},
                    {"family": "c6g", "arch": ["arm64"], "generation": 6, "vcpu_range": "2-64", "memory_range": "4-128 GB", "burstable": False},
                    {"family": "c7i", "arch": ["x86_64"], "generation": 7, "vcpu_range": "2-192", "memory_range": "4-384 GB", "burstable": False},
                    {"family": "c7g", "arch": ["arm64"], "generation": 7, "vcpu_range": "2-64", "memory_range": "4-128 GB", "burstable": False}
                ],
                "memory_optimized": [
                    {"family": "r5", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", "memory_range": "16-768 GB", "burstable": False},
                    {"family": "r5a", "arch": ["x86_64"], "generation": 5, "vcpu_range": "2-96", "memory_range": "16-768 GB", "burstable": False},
                    {"family": "r6i", "arch": ["x86_64"], "generation": 6, "vcpu_range": "2-128", "memory_range": "16-1024 GB", "burstable": False},
                    {"family": "r6g", "arch": ["arm64"], "generation": 6, "vcpu_range": "2-64", "memory_range": "16-512 GB", "burstable": False},
                    {"family": "r7i", "arch": ["x86_64"], "generation": 7, "vcpu_range": "2-192", "memory_range": "16-1536 GB", "burstable": False},
                    {"family": "r7g", "arch": ["arm64"], "generation": 7, "vcpu_range": "2-64", "memory_range": "16-512 GB", "burstable": False}
                ],
                "storage_optimized": [
                    {"family": "i3", "arch": ["x86_64"], "generation": 3, "vcpu_range": "2-72", "memory_range": "15.25-512 GB", "burstable": False},
                    {"family": "i3en", "arch": ["x86_64"], "generation": 3, "vcpu_range": "2-96", "memory_range": "16-768 GB", "burstable": False},
                    {"family": "i4i", "arch": ["x86_64"], "generation": 4, "vcpu_range": "2-128", "memory_range": "16-1024 GB", "burstable": False}
                ],
                "accelerated_computing": [
                    {"family": "p3", "arch": ["x86_64"], "generation": 3, "vcpu_range": "8-96", "memory_range": "61-768 GB", "burstable": False},
                    {"family": "g4dn", "arch": ["x86_64"], "generation": 4, "vcpu_range": "4-96", "memory_range": "16-384 GB", "burstable": False},
                    {"family": "g5", "arch": ["x86_64"], "generation": 5, "vcpu_range": "4-192", "memory_range": "16-768 GB", "burstable": False},
                    {"family": "inf2", "arch": ["x86_64"], "generation": 2, "vcpu_range": "4-192", "memory_range": "16-768 GB", "burstable": False}
                ]
            },
            "sizes": ["nano", "micro", "small", "medium", "large", "xlarge", "2xlarge", "4xlarge", "8xlarge", "12xlarge", "16xlarge", "24xlarge", "metal"],
            "interruption_tolerance_levels": [
                {"value": 1, "label": "Very Low Risk Only", "description": "<5% interruption frequency"},
                {"value": 2, "label": "Low Risk", "description": "<10% interruption frequency"},
                {"value": 3, "label": "Moderate Risk", "description": "<15% interruption frequency"},
                {"value": 4, "label": "High Risk Acceptable", "description": "<20% interruption frequency"},
                {"value": 5, "label": "Any Risk", "description": "No interruption filtering"}
            ]
        }


def get_template_service(db: Session) -> TemplateService:
    """Get template service instance"""
    return TemplateService(db)
