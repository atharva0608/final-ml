"""
Node Template API Routes

Endpoints for node template management (CRUD operations)
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.models.user import User
from backend.schemas.template_schemas import (
    NodeTemplateCreate,
    NodeTemplateUpdate,
    NodeTemplateResponse,
    NodeTemplateList,
)
from backend.services.template_service import get_template_service, TemplateService
from backend.core.dependencies import get_current_user, RequireAccess
from backend.core.logger import StructuredLogger

logger = StructuredLogger(__name__)

router = APIRouter(prefix="/templates", tags=["Node Templates"])


@router.get(
    "",
    response_model=NodeTemplateList,
    summary="List node templates",
    description="Get all node templates for the current user"
)
def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> NodeTemplateList:
    """
    List all templates for current user

    Returns templates ordered by default first, then by creation date
    """
    service = get_template_service(db)
    return service.list_templates(current_user.id)


@router.get(
    "/{template_id}",
    response_model=NodeTemplateResponse,
    summary="Get template details",
    description="Get details of a specific node template"
)
def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> NodeTemplateResponse:
    """Get template by ID"""
    service = get_template_service(db)
    return service.get_template(template_id, current_user.id)


@router.post(
    "",
    response_model=NodeTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create node template",
    description="Create a new node template with instance families and configuration"
)
def create_template(
    template_data: NodeTemplateCreate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> NodeTemplateResponse:
    """
    Create a new template

    Validates instance families and creates template with specified configuration
    """
    service = get_template_service(db)
    result = service.create_template(current_user.id, template_data)

    logger.info(
        "Template created via API",
        template_id=result.id,
        user_id=current_user.id,
        name=template_data.name
    )

    return result


@router.patch(
    "/{template_id}",
    response_model=NodeTemplateResponse,
    summary="Update template",
    description="Update an existing node template"
)
def update_template(
    template_id: str,
    template_data: NodeTemplateUpdate,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> NodeTemplateResponse:
    """Update template configuration"""
    service = get_template_service(db)
    return service.update_template(template_id, current_user.id, template_data)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete template",
    description="Delete a node template (cannot delete last template)"
)
def delete_template(
    template_id: str,
    current_user: User = Depends(RequireAccess("FULL")),
    db: Session = Depends(get_db)
):
    """
    Delete a template

    Raises 409 if trying to delete the last template
    """
    service = get_template_service(db)
    service.delete_template(template_id, current_user.id)

    logger.info(
        "Template deleted via API",
        template_id=template_id,
        user_id=current_user.id
    )


@router.post(
    "/{template_id}/set-default",
    response_model=NodeTemplateResponse,
    summary="Set default template",
    description="Set a template as the default for the user"
)
def set_default_template(
    template_id: str,
    current_user: User = Depends(RequireAccess("EXECUTION")),
    db: Session = Depends(get_db)
) -> NodeTemplateResponse:
    """
    Set template as default

    Unsets any other default templates for the user
    """
    service = get_template_service(db)
    return service.set_default(template_id, current_user.id)
