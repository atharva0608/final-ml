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


def get_template_service(db: Session) -> TemplateService:
    """Get template service instance"""
    return TemplateService(db)
