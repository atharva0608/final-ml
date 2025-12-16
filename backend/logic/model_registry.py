"""
ML Model Registry and Governance Pipeline

Manages the lifecycle of ML models from candidate to production:
1. Scan ml-model/ folder for new .pkl files
2. Register as LAB CANDIDATES (testing only)
3. Graduate to PRODUCTION READY (available for deployment)
4. Deploy as ACTIVE PRODUCTION MODEL (applied to all clients)

Safety Features:
- Only graduated models can be deployed to production
- Only one model can be active in production at a time
- File integrity validation via SHA256 hashing
- Atomic database transactions for state changes
"""

import os
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.models import MLModel, ModelStatus
from utils.system_logger import logger


# Configuration
MODEL_DIR = os.getenv('ML_MODEL_DIR', '/home/user/final-ml/ml-model')


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file for integrity validation"""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Failed to compute hash for {file_path}: {e}")
        return ""


def scan_and_register_models(db: Session, user_id=None) -> dict:
    """
    Scans the ml-model/ folder and registers new .pkl files as LAB CANDIDATES

    Args:
        db: Database session
        user_id: Optional user ID to track who triggered the scan

    Returns:
        Dictionary with scan results including new, existing, and error counts
    """
    # Ensure directory exists
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
        logger.info(f"Created ML model directory: {MODEL_DIR}")

    new_count = 0
    existing_count = 0
    error_count = 0
    new_models = []

    try:
        # Scan directory for .pkl files
        for filename in os.listdir(MODEL_DIR):
            if not filename.endswith('.pkl'):
                continue

            try:
                file_path = os.path.join(MODEL_DIR, filename)

                # Check if already registered
                existing = db.query(MLModel).filter(MLModel.name == filename).first()

                if existing:
                    existing_count += 1
                    # Update file hash if file changed
                    new_hash = compute_file_hash(file_path)
                    if new_hash and new_hash != existing.file_hash:
                        logger.warning(
                            f"Model file changed: {filename} "
                            f"(hash: {existing.file_hash[:8]}... -> {new_hash[:8]}...)"
                        )
                        existing.file_hash = new_hash
                        db.commit()
                    continue

                # Register new model as CANDIDATE
                file_hash = compute_file_hash(file_path)
                new_model = MLModel(
                    name=filename,
                    file_path=file_path,
                    file_hash=file_hash,
                    status=ModelStatus.CANDIDATE.value,
                    is_active_prod=False,
                    uploaded_by=user_id,
                    uploaded_at=datetime.utcnow()
                )

                db.add(new_model)
                db.commit()
                db.refresh(new_model)

                new_models.append(new_model)
                new_count += 1

                logger.info(
                    f"Registered new LAB CANDIDATE: {filename} "
                    f"(id={new_model.id}, hash={file_hash[:8]}...)"
                )

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to register model {filename}: {e}")
                db.rollback()

        return {
            "status": "success",
            "new_models": new_count,
            "existing_models": existing_count,
            "errors": error_count,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "uploaded_at": m.uploaded_at.isoformat()
                }
                for m in new_models
            ]
        }

    except Exception as e:
        logger.error(f"Model scan failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "new_models": 0,
            "existing_models": 0,
            "errors": error_count
        }


def graduate_model(model_id: int, db: Session, user_id=None) -> bool:
    """
    Promotes a model from LAB CANDIDATE to PRODUCTION READY

    This makes the model available in the Production dropdown but does NOT
    automatically deploy it. The admin must explicitly select it.

    Args:
        model_id: ID of the model to graduate
        db: Database session
        user_id: Optional user ID for audit trail

    Returns:
        True if successful, False otherwise
    """
    try:
        model = db.query(MLModel).filter(MLModel.id == model_id).first()

        if not model:
            logger.error(f"Model {model_id} not found for graduation")
            return False

        if model.status == ModelStatus.GRADUATED.value:
            logger.warning(f"Model {model.name} is already graduated")
            return True

        # Validate file still exists
        if not os.path.exists(model.file_path):
            logger.error(f"Cannot graduate {model.name}: file not found at {model.file_path}")
            return False

        # Promote to GRADUATED
        model.status = ModelStatus.GRADUATED.value
        model.graduated_at = datetime.utcnow()

        db.commit()

        logger.info(
            f"🎓 Model GRADUATED: {model.name} (id={model.id}) "
            f"is now available for Production deployment"
        )

        return True

    except Exception as e:
        logger.error(f"Failed to graduate model {model_id}: {e}")
        db.rollback()
        return False


def set_production_model(model_id: int, db: Session, user_id=None) -> bool:
    """
    Sets the active production model for ALL clients

    Safety checks:
    1. Only GRADUATED models can be deployed
    2. Only ONE model can be active at a time (atomically unsets previous)
    3. File integrity validation before deployment

    Args:
        model_id: ID of the model to deploy
        db: Database session
        user_id: Optional user ID for audit trail

    Returns:
        True if successful, False otherwise
    """
    try:
        # Fetch target model
        model = db.query(MLModel).filter(MLModel.id == model_id).first()

        if not model:
            logger.error(f"Model {model_id} not found for production deployment")
            return False

        # SAFETY CHECK: Only graduated models can be deployed
        if model.status != ModelStatus.GRADUATED.value:
            logger.error(
                f"Cannot deploy {model.name}: status is {model.status}, "
                f"must be {ModelStatus.GRADUATED.value}"
            )
            return False

        # SAFETY CHECK: Validate file exists and integrity
        if not os.path.exists(model.file_path):
            logger.error(f"Cannot deploy {model.name}: file not found at {model.file_path}")
            return False

        current_hash = compute_file_hash(model.file_path)
        if current_hash != model.file_hash:
            logger.error(
                f"Cannot deploy {model.name}: file integrity check failed "
                f"(expected {model.file_hash[:8]}..., got {current_hash[:8]}...)"
            )
            return False

        # ATOMIC OPERATION: Unset current active, set new active
        # Get current active model for logging
        current_active = db.query(MLModel).filter(MLModel.is_active_prod == True).first()

        # Unset ALL active flags
        db.query(MLModel).update({MLModel.is_active_prod: False})

        # Set new active model
        model.is_active_prod = True
        model.deployed_at = datetime.utcnow()

        db.commit()

        if current_active:
            logger.warning(
                f"🔄 Production model SWITCHED: {current_active.name} -> {model.name}"
            )
        else:
            logger.info(f"🚀 Production model DEPLOYED: {model.name} (id={model.id})")

        return True

    except Exception as e:
        logger.error(f"Failed to deploy model {model_id}: {e}")
        db.rollback()
        return False


def get_active_production_model(db: Session):
    """
    Returns the currently active production model

    Returns:
        MLModel object or None if no model is active
    """
    try:
        return db.query(MLModel).filter(
            and_(
                MLModel.is_active_prod == True,
                MLModel.status == ModelStatus.GRADUATED.value
            )
        ).first()
    except Exception as e:
        logger.error(f"Failed to fetch active production model: {e}")
        return None


def archive_model(model_id: int, db: Session, user_id=None) -> bool:
    """
    Archives a model (soft delete)

    Archived models cannot be deployed but remain in database for audit trail.
    If the model is currently active in production, deployment fails.

    Args:
        model_id: ID of the model to archive
        db: Database session
        user_id: Optional user ID for audit trail

    Returns:
        True if successful, False otherwise
    """
    try:
        model = db.query(MLModel).filter(MLModel.id == model_id).first()

        if not model:
            logger.error(f"Model {model_id} not found for archival")
            return False

        # SAFETY CHECK: Cannot archive active production model
        if model.is_active_prod:
            logger.error(
                f"Cannot archive {model.name}: it is currently active in production. "
                "Deploy a different model first."
            )
            return False

        model.status = ModelStatus.ARCHIVED.value
        model.archived_at = datetime.utcnow()

        db.commit()

        logger.info(f"📦 Model ARCHIVED: {model.name} (id={model.id})")

        return True

    except Exception as e:
        logger.error(f"Failed to archive model {model_id}: {e}")
        db.rollback()
        return False
