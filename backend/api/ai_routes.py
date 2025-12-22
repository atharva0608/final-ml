"""
AI Model Governance API Routes

Provides endpoints for ML model lifecycle management:
- Scan ml-model/ folder for new .pkl files
- List models by status (candidate, graduated, active)
- Graduate models from Lab to Production
- Deploy models as active production model
- Archive deprecated models

All operations are logged and require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import shutil
import hashlib

from database.connection import get_db
from database.models import User, MLModel, ModelStatus
from api.auth import get_current_active_user as get_current_user
from logic.model_registry import (
    scan_and_register_models,
    graduate_model,
    set_production_model,
    get_active_production_model,
    archive_model
)
from utils.system_logger import logger


router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class ModelResponse(BaseModel):
    """Single model response"""
    id: int
    name: str
    file_path: str
    status: str
    is_active_prod: bool
    uploaded_at: datetime
    graduated_at: Optional[datetime]
    deployed_at: Optional[datetime]
    total_predictions: int
    success_count: int
    failure_count: int

    class Config:
        from_attributes = True


class ModelListResponse(BaseModel):
    """Model list grouped by status"""
    lab_candidates: List[ModelResponse]
    production_ready: List[ModelResponse]
    active_production_model: Optional[ModelResponse]
    archived_models: List[ModelResponse]


class ScanResultResponse(BaseModel):
    """Model scan results"""
    status: str
    new_models: int
    existing_models: int
    errors: int
    models: List[dict]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/scan", response_model=ScanResultResponse)
async def scan_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Scan ml-model/ folder and register new .pkl files as LAB CANDIDATES

    Only admins can trigger model scans.

    Returns:
        Scan results with counts of new, existing, and error files
    """
    # Admin only
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        result = scan_and_register_models(db, user_id=current_user.id)
        logger.info(
            f"Model scan completed by {current_user.email}: "
            f"{result['new_models']} new, {result['existing_models']} existing, "
            f"{result['errors']} errors"
        )
        return result

    except Exception as e:
        logger.error(f"Model scan failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model scan failed: {str(e)}"
        )


@router.get("/list", response_model=ModelListResponse)
async def list_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all models grouped by status

    Automatically scans for new models before returning the list.

    Returns:
        Models categorized as:
        - lab_candidates: Available for testing
        - production_ready: Available for deployment
        - active_production_model: Currently deployed model
        - archived_models: Deprecated models
    """
    # Auto-scan on list (ensures UI shows latest state)
    scan_and_register_models(db, user_id=current_user.id)

    # Fetch models by status
    lab_candidates = db.query(MLModel).filter(
        MLModel.status == ModelStatus.CANDIDATE.value
    ).order_by(MLModel.uploaded_at.desc()).all()

    production_ready = db.query(MLModel).filter(
        MLModel.status == ModelStatus.GRADUATED.value,
        MLModel.is_active_prod == False
    ).order_by(MLModel.graduated_at.desc()).all()

    active_model = get_active_production_model(db)

    archived_models = db.query(MLModel).filter(
        MLModel.status == ModelStatus.ARCHIVED.value
    ).order_by(MLModel.archived_at.desc()).limit(10).all()

    return ModelListResponse(
        lab_candidates=[ModelResponse.from_orm(m) for m in lab_candidates],
        production_ready=[ModelResponse.from_orm(m) for m in production_ready],
        active_production_model=ModelResponse.from_orm(active_model) if active_model else None,
        archived_models=[ModelResponse.from_orm(m) for m in archived_models]
    )


@router.post("/{model_id}/graduate")
async def promote_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Graduate a model from LAB CANDIDATE to PRODUCTION READY

    This makes the model available in the Production dropdown but does NOT
    automatically deploy it. The admin must explicitly deploy it.

    Only admins can graduate models.

    Args:
        model_id: ID of the model to graduate

    Returns:
        Success status and model details
    """
    # Admin only
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        success = graduate_model(model_id, db, user_id=current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model graduation failed. Check logs for details."
            )

        model = db.query(MLModel).filter(MLModel.id == model_id).first()

        logger.info(
            f"Model graduated by {current_user.email}: "
            f"{model.name} (id={model.id})"
        )

        return {
            "status": "success",
            "message": f"Model {model.name} is now PRODUCTION READY",
            "model": ModelResponse.from_orm(model)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model graduation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model graduation failed: {str(e)}"
        )


@router.post("/{model_id}/deploy")
async def deploy_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deploy a model as the ACTIVE PRODUCTION MODEL

    WARNING: This sets the model for ALL production clients immediately.

    Safety checks:
    - Only GRADUATED models can be deployed
    - Only ONE model can be active at a time
    - File integrity validation before deployment

    Only admins can deploy models.

    Args:
        model_id: ID of the model to deploy

    Returns:
        Success status and deployment details
    """
    # Admin only
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        # Get model info before deployment
        model = db.query(MLModel).filter(MLModel.id == model_id).first()

        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found"
            )

        if model.status != ModelStatus.GRADUATED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot deploy model with status '{model.status}'. Must be 'graduated'."
            )

        # Get current active model for logging
        current_active = get_active_production_model(db)

        # Deploy
        success = set_production_model(model_id, db, user_id=current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model deployment failed. Check logs for details."
            )

        # Refresh model data
        db.refresh(model)

        log_message = f"Model deployed by {current_user.email}: {model.name} (id={model.id})"
        if current_active:
            log_message += f" (replaced {current_active.name})"

        logger.warning(log_message)

        return {
            "status": "success",
            "message": f"Model {model.name} is now ACTIVE in PRODUCTION",
            "model": ModelResponse.from_orm(model),
            "previous_model": ModelResponse.from_orm(current_active) if current_active else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model deployment failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model deployment failed: {str(e)}"
        )


@router.post("/{model_id}/archive")
async def archive_model_endpoint(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Archive a model (soft delete)

    Archived models:
    - Cannot be deployed
    - Remain in database for audit trail
    - Can be restored by changing status back to CANDIDATE

    Cannot archive the currently active production model.

    Only admins can archive models.

    Args:
        model_id: ID of the model to archive

    Returns:
        Success status
    """
    # Admin only
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    try:
        model = db.query(MLModel).filter(MLModel.id == model_id).first()

        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model {model_id} not found"
            )

        if model.is_active_prod:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot archive the active production model. Deploy a different model first."
            )

        success = archive_model(model_id, db, user_id=current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model archival failed. Check logs for details."
            )

        logger.info(
            f"Model archived by {current_user.email}: "
            f"{model.name} (id={model.id})"
        )

        return {
            "status": "success",
            "message": f"Model {model.name} has been archived"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Model archival failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model archival failed: {str(e)}"
        )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model_details(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific model

    Args:
        model_id: ID of the model

    Returns:
        Model details including performance metrics
    """
    model = db.query(MLModel).filter(MLModel.id == model_id).first()

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )

    return ModelResponse.from_orm(model)


@router.post("/upload")
async def upload_model(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload and validate a new ML model (.pkl file)

    Steps:
    1. Validate file type and name
    2. Check for duplicates
    3. Save file to disk with error handling
    4. Test model loading (validation)
    5. Create database record
    6. Update health check status

    Returns:
        Model details with validation status
    """

    try:
        # Validate file type
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No filename provided"
            )

        if not file.filename.endswith('.pkl'):
            raise HTTPException(
                status_code=400,
                detail="Only .pkl files are supported"
            )

        # Define ml-models directory
        ml_models_dir = Path(__file__).parent.parent / "ml-models"

        # Ensure directory exists with proper error handling
        try:
            ml_models_dir.mkdir(exist_ok=True, parents=True)
        except PermissionError:
            raise HTTPException(
                status_code=500,
                detail="Cannot create model directory: Permission denied"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Cannot create model directory: {str(e)}"
            )

        # Save file path
        file_path = ml_models_dir / file.filename

        # Check if model already exists (explicit check before DB operation)
        existing_model = db.query(MLModel).filter(MLModel.name == file.filename).first()
        if existing_model:
            raise HTTPException(
                status_code=409,
                detail=f"Model {file.filename} already exists. Please use a different name or version."
            )

        # Save uploaded file with error handling
        try:
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except IOError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save model file: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error saving file: {str(e)}"
            )

        # Calculate file hash
        try:
            sha256 = hashlib.sha256()
            with file_path.open('rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256.update(chunk)
            file_hash = sha256.hexdigest()
        except Exception as e:
            # Clean up file if hash calculation fails
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate file hash: {str(e)}"
            )

        # Test model loading (validation)
        model_valid = False
        validation_error = None
        try:
            import pickle
            with file_path.open('rb') as f:
                model_obj = pickle.load(f)
                # Basic validation: check if it has predict method
                if hasattr(model_obj, 'predict'):
                    model_valid = True
                else:
                    validation_error = "Model does not have a 'predict' method"
        except Exception as e:
            validation_error = f"Model validation failed: {str(e)}"

        # If model is invalid, clean up and return error
        if not model_valid:
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model file: {validation_error}"
            )

        # Create database record with error handling
        try:
            new_model = MLModel(
                name=file.filename,
                file_path=str(file_path.absolute()),
                file_hash=file_hash,
                status=ModelStatus.CANDIDATE,
                is_active_prod=False,
                uploaded_by=current_user.id,
                uploaded_at=datetime.utcnow()
            )

            db.add(new_model)
            db.commit()
            db.refresh(new_model)
        except Exception as e:
            # Clean up file if database operation fails
            if file_path.exists():
                file_path.unlink()
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(e)}"
            )

        # Update system health check
        try:
            from utils.system_logger import SystemLogger
            sys_logger = SystemLogger('ml_inference', db=db)
            sys_logger.success(
                f"New model uploaded and validated: {file.filename}",
                details={
                    'model_id': new_model.id,
                    'model_name': file.filename,
                    'file_hash': file_hash,
                    'uploaded_by': current_user.email,
                    'validation_status': 'passed'
                }
            )
        except Exception as e:
            # Log error but don't fail the upload
            print(f"Warning: Failed to update health check: {e}")

        return {
            "status": "success",
            "id": new_model.id,
            "name": new_model.name,
            "model_status": new_model.status.value,
            "uploaded_at": new_model.uploaded_at.isoformat(),
            "file_hash": file_hash,
            "validation": {
                "passed": True,
                "message": "Model loaded successfully and has predict method"
            },
            "message": f"Model {file.filename} uploaded, validated, and registered successfully"
        }

    except HTTPException:
        # Re-raise HTTPExceptions (they're already properly formatted)
        raise
    except Exception as e:
        # Catch any other unexpected errors and return as JSON
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during model upload: {str(e)}"
        )
