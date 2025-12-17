"""
ML Model Registry Logic

Handles ML model lifecycle management:
- Scanning ml-models/ directory for new .pkl files
- Registering models as CANDIDATE status
- Graduating models from CANDIDATE to GRADUATED
- Setting production-active models (enforces single active model rule)
- Archiving deprecated models
"""

import os
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.models import MLModel, ModelStatus
from utils.system_logger import SystemLogger


# Path to ML models directory
ML_MODELS_DIR = Path(__file__).parent.parent / "ml-models"


def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def scan_and_register_models(db: Session, user_id: Optional[str] = None) -> Tuple[int, int]:
    """
    Scan ml-models/ directory for .pkl files and register new ones

    Args:
        db: Database session
        user_id: UUID of user who triggered the scan

    Returns:
        Tuple of (new_models_count, existing_models_count)
    """
    logger = SystemLogger("ml_inference", db=db)

    if not ML_MODELS_DIR.exists():
        ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created ml-models directory: {ML_MODELS_DIR}")

    # Find all .pkl files
    pkl_files = list(ML_MODELS_DIR.glob("*.pkl"))

    new_count = 0
    existing_count = 0

    for pkl_file in pkl_files:
        model_name = pkl_file.name

        # Check if model already registered
        existing_model = db.query(MLModel).filter(MLModel.name == model_name).first()

        if existing_model:
            existing_count += 1
            continue

        # Register new model
        file_hash = calculate_file_hash(str(pkl_file))

        new_model = MLModel(
            name=model_name,
            file_path=str(pkl_file.absolute()),
            file_hash=file_hash,
            status=ModelStatus.CANDIDATE,
            is_active_prod=False,
            uploaded_by=user_id,
            uploaded_at=datetime.utcnow()
        )

        db.add(new_model)
        new_count += 1

        logger.success(
            f"Registered new model: {model_name}",
            details={
                "model_name": model_name,
                "file_path": str(pkl_file),
                "file_hash": file_hash[:16],
                "status": ModelStatus.CANDIDATE.value
            }
        )

    if new_count > 0:
        db.commit()
        logger.info(f"Model scan complete: {new_count} new, {existing_count} existing")

    return new_count, existing_count


def graduate_model(db: Session, model_id: int, user_id: Optional[str] = None) -> MLModel:
    """
    Graduate a model from CANDIDATE to GRADUATED status

    Args:
        db: Database session
        model_id: ID of model to graduate
        user_id: UUID of user who performed graduation

    Returns:
        Updated MLModel instance

    Raises:
        ValueError: If model not found or already graduated/archived
    """
    logger = SystemLogger("ml_inference", db=db)

    model = db.query(MLModel).filter(MLModel.id == model_id).first()

    if not model:
        raise ValueError(f"Model with ID {model_id} not found")

    if model.status == ModelStatus.GRADUATED:
        raise ValueError(f"Model {model.name} is already graduated")

    if model.status == ModelStatus.ARCHIVED:
        raise ValueError(f"Model {model.name} is archived and cannot be graduated")

    # Update status
    model.status = ModelStatus.GRADUATED
    model.graduated_at = datetime.utcnow()

    db.commit()
    db.refresh(model)

    logger.success(
        f"Model graduated: {model.name}",
        details={
            "model_id": model_id,
            "model_name": model.name,
            "graduated_at": model.graduated_at.isoformat()
        }
    )

    return model


def set_production_model(db: Session, model_id: int, user_id: Optional[str] = None) -> MLModel:
    """
    Set a model as the active production model

    Enforces single-active-model rule:
    - Deactivates currently active model
    - Activates the specified model

    Args:
        db: Database session
        model_id: ID of model to activate
        user_id: UUID of user who performed activation

    Returns:
        Updated MLModel instance

    Raises:
        ValueError: If model not found or not graduated
    """
    logger = SystemLogger("ml_inference", db=db)

    model = db.query(MLModel).filter(MLModel.id == model_id).first()

    if not model:
        raise ValueError(f"Model with ID {model_id} not found")

    if model.status != ModelStatus.GRADUATED:
        raise ValueError(f"Model {model.name} must be graduated before production deployment")

    # Deactivate currently active model
    current_active = db.query(MLModel).filter(MLModel.is_active_prod == True).first()

    if current_active:
        current_active.is_active_prod = False
        logger.info(
            f"Deactivated previous production model: {current_active.name}",
            details={"model_id": current_active.id}
        )

    # Activate new model
    model.is_active_prod = True
    model.deployed_at = datetime.utcnow()

    db.commit()
    db.refresh(model)

    logger.success(
        f"Production model activated: {model.name}",
        details={
            "model_id": model_id,
            "model_name": model.name,
            "deployed_at": model.deployed_at.isoformat()
        }
    )

    return model


def get_active_production_model(db: Session) -> Optional[MLModel]:
    """
    Get the currently active production model

    Args:
        db: Database session

    Returns:
        MLModel instance or None if no active model
    """
    return db.query(MLModel).filter(
        and_(
            MLModel.is_active_prod == True,
            MLModel.status == ModelStatus.GRADUATED
        )
    ).first()


def archive_model(db: Session, model_id: int, user_id: Optional[str] = None) -> MLModel:
    """
    Archive a model (mark as deprecated/removed)

    Args:
        db: Database session
        model_id: ID of model to archive
        user_id: UUID of user who performed archival

    Returns:
        Updated MLModel instance

    Raises:
        ValueError: If model not found or is currently active in production
    """
    logger = SystemLogger("ml_inference", db=db)

    model = db.query(MLModel).filter(MLModel.id == model_id).first()

    if not model:
        raise ValueError(f"Model with ID {model_id} not found")

    if model.is_active_prod:
        raise ValueError(f"Cannot archive {model.name} - it is the active production model")

    # Update status
    model.status = ModelStatus.ARCHIVED
    model.is_active_prod = False

    db.commit()
    db.refresh(model)

    logger.warning(
        f"Model archived: {model.name}",
        details={
            "model_id": model_id,
            "model_name": model.name,
            "previous_status": model.status.value
        }
    )

    return model


def get_models_by_status(db: Session, status: ModelStatus) -> List[MLModel]:
    """
    Get all models with a specific status

    Args:
        db: Database session
        status: ModelStatus enum value

    Returns:
        List of MLModel instances
    """
    return db.query(MLModel).filter(MLModel.status == status).order_by(MLModel.uploaded_at.desc()).all()


def get_model_by_name(db: Session, model_name: str) -> Optional[MLModel]:
    """
    Get a model by its filename

    Args:
        db: Database session
        model_name: Name of the model file (e.g., "v2_aggressive_risk.pkl")

    Returns:
        MLModel instance or None
    """
    return db.query(MLModel).filter(MLModel.name == model_name).first()
