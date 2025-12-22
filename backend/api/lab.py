"""
Lab Mode API Endpoints - Production Database Integration

Real database-backed Lab Mode management with:
- EC2 instance tracking and configuration
- ML model version control
- Experiment logging and analytics
- Cross-account authorization
"""

from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from pathlib import Path
import shutil
import hashlib

from database.connection import get_db
from database.models import User, Account, Instance, MLModel, ExperimentLog, ModelStatus
from auth.jwt import get_current_active_user
from utils.aws_session import validate_account_access

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class AssignModelRequest(BaseModel):
    instance_id: str
    model_version: str  # e.g., "v2.1.0"


class PipelineStatusResponse(BaseModel):
    instance_id: str
    pipeline_mode: str
    scraper: dict
    safe_filter: dict
    bin_packing: dict
    right_sizing: dict
    ml_inference: dict
    execution: dict


class ModelInfo(BaseModel):
    id: str
    name: str
    version: str
    description: Optional[str]
    is_experimental: bool
    is_active: bool
    status: str  # testing, graduated, rejected
    created_at: datetime


class InstanceResponse(BaseModel):
    id: str
    instance_id: str
    instance_type: str
    availability_zone: str
    assigned_model_version: Optional[str]
    pipeline_mode: str
    is_shadow_mode: bool
    is_active: bool
    last_evaluation: Optional[datetime]
    account_name: str


class ExperimentLogResponse(BaseModel):
    id: str
    instance_id: str
    pipeline_mode: str
    prediction_score: Optional[float]
    decision: str
    decision_reason: Optional[str]
    execution_time: datetime
    execution_duration_ms: Optional[int]
    selected_instance_type: Optional[str]
    projected_hourly_savings: Optional[float]
    is_shadow_run: bool


class AccountResponse(BaseModel):
    id: str
    account_id: str
    account_name: str
    environment_type: str
    region: str
    is_active: bool
    instance_count: int


class CreateAccountRequest(BaseModel):
    account_id: str = Field(..., min_length=12, max_length=12)
    account_name: str
    environment_type: str = Field(default="LAB")
    role_arn: str
    external_id: str
    region: str = Field(default="ap-south-1")


# ============================================================================
# Instance Management
# ============================================================================

@router.get("/instances", response_model=List[InstanceResponse])
async def list_instances(
    account_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all instances (optionally filtered by account)

    Returns instances owned by the current user.
    Admins can see all instances.
    """
    query = db.query(Instance).join(Account)

    # Non-admin users can only see their own instances
    if current_user.role != "admin":
        query = query.filter(Account.user_id == current_user.id)

    # Filter by account if specified
    if account_id:
        query = query.filter(Account.account_id == account_id)

    instances = query.all()

    return [
        InstanceResponse(
            id=str(inst.id),
            instance_id=inst.instance_id,
            instance_type=inst.instance_type,
            availability_zone=inst.availability_zone,
            assigned_model_version=inst.assigned_model_version,
            pipeline_mode=inst.pipeline_mode,
            is_shadow_mode=inst.is_shadow_mode,
            is_active=inst.is_active,
            last_evaluation=inst.last_evaluation,
            account_name=inst.account.account_name
        )
        for inst in instances
    ]


@router.get("/instances/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get detailed instance information"""
    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).join(Account).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    # Authorization check
    if current_user.role != "admin" and instance.account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this instance"
        )

    return InstanceResponse(
        id=str(instance.id),
        instance_id=instance.instance_id,
        instance_type=instance.instance_type,
        availability_zone=instance.availability_zone,
        assigned_model_version=instance.assigned_model_version,
        pipeline_mode=instance.pipeline_mode,
        is_shadow_mode=instance.is_shadow_mode,
        is_active=instance.is_active,
        last_evaluation=instance.last_evaluation,
        account_name=instance.account.account_name
    )


@router.post("/assign-model")
async def assign_model_to_instance(
    request: AssignModelRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Assign a model version to an instance

    Sets the instance to SINGLE_LINEAR mode and assigns the specified model.
    Only works on LAB environment instances (safety check).
    """
    # Find instance
    instance = db.query(Instance).filter(
        Instance.instance_id == request.instance_id
    ).join(Account).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {request.instance_id} not found"
        )

    # Authorization check
    if current_user.role != "admin" and instance.account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this instance"
        )

    # Safety check: Only allow on LAB instances
    if instance.account.environment_type != "LAB":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change models on Production instances. Use Lab environment only."
        )

    # Update instance configuration
    instance.assigned_model_version = request.model_version
    instance.pipeline_mode = "LINEAR"  # Force LINEAR mode for Lab
    instance.updated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "updated",
        "mode": "Lab Experiment Active",
        "instance_id": instance.instance_id,
        "model_version": request.model_version,
        "pipeline_mode": "LINEAR"
    }


@router.put("/instances/{instance_id}/pipeline-mode")
async def set_pipeline_mode(
    instance_id: str,
    pipeline_mode: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Toggle between CLUSTER and LINEAR pipeline modes"""
    if pipeline_mode not in ["CLUSTER", "LINEAR"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pipeline mode must be 'CLUSTER' or 'LINEAR'"
        )

    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).join(Account).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    # Authorization check
    if current_user.role != "admin" and instance.account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this instance"
        )

    instance.pipeline_mode = pipeline_mode
    instance.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "updated",
        "instance_id": instance_id,
        "pipeline_mode": pipeline_mode
    }


@router.put("/instances/{instance_id}/shadow-mode")
async def toggle_shadow_mode(
    instance_id: str,
    is_shadow_mode: bool,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Toggle shadow mode (read-only mode that doesn't execute switches)"""
    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).join(Account).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    # Authorization check
    if current_user.role != "admin" and instance.account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this instance"
        )

    instance.is_shadow_mode = is_shadow_mode
    instance.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "updated",
        "instance_id": instance_id,
        "is_shadow_mode": is_shadow_mode
    }


@router.get("/pipeline-status/{instance_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    instance_id: str,
    db: Session = Depends(get_db)
):
    """Get pipeline status for frontend visualization"""
    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    is_linear = instance.pipeline_mode == "LINEAR"

    return PipelineStatusResponse(
        instance_id=instance_id,
        pipeline_mode=instance.pipeline_mode,
        scraper={
            "status": "active",
            "description": "Fetching real-time spot prices via STS AssumeRole"
        },
        safe_filter={
            "status": "active",
            "description": "Filtering by interrupt rate < 20%"
        },
        bin_packing={
            "status": "disabled" if is_linear else "active",
            "description": "Bypassed in LINEAR mode" if is_linear else "Calculating waste cost"
        },
        right_sizing={
            "status": "disabled" if is_linear else "active",
            "description": "Bypassed in LINEAR mode" if is_linear else "Finding better instance sizes"
        },
        ml_inference={
            "status": "active",
            "model_version": instance.assigned_model_version or "default",
            "description": f"Model: {instance.assigned_model_version or 'default production model'}"
        },
        execution={
            "status": "shadow" if instance.is_shadow_mode else "active",
            "description": "Shadow mode (read-only)" if instance.is_shadow_mode else (
                "Atomic switch" if is_linear else "Kubernetes drain"
            )
        }
    )


# ============================================================================
# Model Management
# ============================================================================

@router.get("/models", response_model=List[ModelInfo])
async def list_models(db: Session = Depends(get_db)):
    """List all available models in the registry"""
    models = db.query(MLModel).filter(
        MLModel.status != ModelStatus.ARCHIVED
    ).order_by(MLModel.uploaded_at.desc()).all()

    result = []
    for model in models:
        # Map status
        is_experimental = model.status == ModelStatus.CANDIDATE
        status_str = "candidate" if model.status == ModelStatus.CANDIDATE else "graduated"

        result.append(ModelInfo(
            id=str(model.id),
            name=model.name,
            version=model.name,  # Use name as version for compatibility
            description=model.description or "",
            is_experimental=is_experimental,
            is_active=model.is_active_prod,
            status=status_str,
            created_at=model.uploaded_at
        ))

    return result


@router.put("/models/{model_id}/graduate")
async def graduate_model(
    model_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Graduate a model from Lab (experimental) to Production (stable)"""
    model = db.query(MLModel).filter(MLModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    model.status = ModelStatus.GRADUATED
    model.graduated_at = datetime.utcnow()
    db.commit()
    return {"status": "graduated", "model_id": model_id}


@router.put("/models/{model_id}/reject")
async def reject_model(
    model_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Reject a model (mark as archived)"""
    model = db.query(MLModel).filter(MLModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    model.status = ModelStatus.ARCHIVED
    model.is_active_prod = False
    db.commit()
    return {"status": "rejected", "model_id": model_id}


@router.post("/models/upload")
async def upload_model(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
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
            logger = SystemLogger('ml_inference', db=db)
            logger.success(
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


# ============================================================================
# Experiment Logging
# ============================================================================

@router.get("/experiments/{instance_id}", response_model=List[ExperimentLogResponse])
async def get_experiment_logs(
    instance_id: str,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get experiment logs for an instance"""
    # Find instance UUID from instance_id string
    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    logs = db.query(ExperimentLog).filter(
        ExperimentLog.instance_id == instance.id
    ).order_by(ExperimentLog.execution_time.desc()).limit(limit).all()

    return [
        ExperimentLogResponse(
            id=str(log.id),
            instance_id=instance_id,
            pipeline_mode=log.pipeline_mode,
            prediction_score=log.prediction_score,
            decision=log.decision,
            decision_reason=log.decision_reason,
            execution_time=log.execution_time,
            execution_duration_ms=log.execution_duration_ms,
            selected_instance_type=log.selected_instance_type,
            projected_hourly_savings=log.projected_hourly_savings,
            is_shadow_run=log.is_shadow_run
        )
        for log in logs
    ]


@router.get("/experiments/model/{model_version}")
async def get_model_performance(
    model_version: str,
    db: Session = Depends(get_db)
):
    """Get aggregated performance metrics for a model version"""
    # Query experiment logs for this model version
    logs = db.query(ExperimentLog).join(Instance).filter(
        Instance.assigned_model_version == model_version
    ).all()

    if not logs:
        return {
            "model_version": model_version,
            "total_predictions": 0,
            "switch_count": 0,
            "switch_rate": 0.0,
            "average_score": 0.0,
            "total_savings": 0.0
        }

    total_predictions = len(logs)
    switch_count = sum(1 for log in logs if log.decision == "SWITCH")
    switch_rate = switch_count / total_predictions if total_predictions > 0 else 0.0

    scores = [log.prediction_score for log in logs if log.prediction_score is not None]
    average_score = sum(scores) / len(scores) if scores else 0.0

    savings = [log.projected_hourly_savings for log in logs if log.projected_hourly_savings is not None]
    total_savings = sum(savings)

    return {
        "model_version": model_version,
        "total_predictions": total_predictions,
        "switch_count": switch_count,
        "switch_rate": switch_rate,
        "average_score": average_score,
        "total_savings": total_savings
    }


# ============================================================================
# Account Management
# ============================================================================

@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all AWS accounts (admins see all, users see their own)"""
    query = db.query(Account)

    if current_user.role != "admin":
        query = query.filter(Account.user_id == current_user.id)

    accounts = query.all()

    result = []
    for account in accounts:
        instance_count = db.query(Instance).filter(
            Instance.account_id == account.id
        ).count()

        result.append(AccountResponse(
            id=str(account.id),
            account_id=account.account_id,
            account_name=account.account_name,
            environment_type=account.environment_type,
            region=account.region,
            is_active=account.is_active,
            instance_count=instance_count
        ))

    return result


@router.post("/accounts")
async def create_account(
    request: CreateAccountRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new AWS account configuration"""
    # Check if account already exists
    existing = db.query(Account).filter(
        Account.account_id == request.account_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account {request.account_id} already exists"
        )

    # Create account
    account = Account(
        user_id=current_user.id,
        account_id=request.account_id,
        account_name=request.account_name,
        environment_type=request.environment_type,
        role_arn=request.role_arn,
        external_id=request.external_id,
        region=request.region,
        is_active=True
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    return {
        "status": "created",
        "account_id": account.account_id,
        "id": str(account.id)
    }


@router.get("/accounts/{account_id}/validate")
async def validate_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Validate that cross-account access is working"""
    account = db.query(Account).filter(
        Account.account_id == account_id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    # Authorization check
    if current_user.role != "admin" and account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this account"
        )

    # Test STS AssumeRole
    result = validate_account_access(account_id, account.region, db)

    return result


@router.post("/instances/{instance_id}/evaluate")
async def evaluate_instance(
    instance_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger evaluation for an instance

    Runs the linear optimizer immediately instead of waiting for scheduled execution.
    """
    instance = db.query(Instance).filter(
        Instance.instance_id == instance_id
    ).join(Account).first()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance {instance_id} not found"
        )

    # Authorization check
    if current_user.role != "admin" and instance.account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to evaluate this instance"
        )

    # Run optimization (will be implemented in optimizer_task)
    from workers.optimizer_task import run_optimization_cycle

    result = run_optimization_cycle(instance_id, db)

    return result
    # Authorization check
    if current_user.role != "admin" and instance.account.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to evaluate this instance"
        )

    # Run optimization (will be implemented in optimizer_task)
    from workers.optimizer_task import run_optimization_cycle

    result = run_optimization_cycle(instance_id, db)

    return result
