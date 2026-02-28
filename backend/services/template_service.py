"""
Node Template Service

Service for managing node templates (instance type constraints for optimization).
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.models.node_template import NodeTemplate
from backend.schemas.template_schemas import (
    NodeTemplateCreate,
    NodeTemplateUpdate,
    TemplateValidationResult
)
from backend.core.logger import logger


class TemplateService:
    """Service for node template management."""

    def __init__(self, db: Session):
        self.db = db

    def create_template(self, template_data: NodeTemplateCreate, organization_id: str) -> NodeTemplate:
        """Create a new node template."""
        template = NodeTemplate(
            organization_id=organization_id,
            **template_data.dict()
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def get_template(self, template_id: str) -> Optional[NodeTemplate]:
        """Get template by ID."""
        return self.db.query(NodeTemplate).filter(NodeTemplate.id == template_id).first()

    def list_templates(self, organization_id: str) -> List[NodeTemplate]:
        """List all templates for an organization."""
        return self.db.query(NodeTemplate).filter(
            NodeTemplate.organization_id == organization_id
        ).all()

    def update_template(self, template_id: str, template_data: NodeTemplateUpdate) -> Optional[NodeTemplate]:
        """Update an existing template."""
        template = self.get_template(template_id)
        if not template:
            return None

        update_data = template_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(template, key, value)

        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        template = self.get_template(template_id)
        if not template:
            return False

        self.db.delete(template)
        self.db.commit()
        return True

    def validate_template(self, template: NodeTemplate) -> TemplateValidationResult:
        """Validate template configuration."""
        errors = []
        warnings = []
        matched_instances = []

        # Basic validation
        if not template.instance_families and not template.instance_types:
            errors.append("Template must specify at least one instance family or instance type")

        # TODO: Validate against instance_catalog table when available
        # For now, return basic validation
        return TemplateValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            matched_instances=matched_instances
        )


def get_template_service(db: Session) -> TemplateService:
    """Dependency injection helper for TemplateService."""
    return TemplateService(db)
