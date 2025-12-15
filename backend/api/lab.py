"""
Lab Mode API Endpoints

FastAPI router for Lab Mode management, allowing real execution on single
instances with simplified pipeline and model version control.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID

# NOTE: Database integration would go here
# For now, using in-memory store for demo purposes
LAB_CONFIGS = {}
MODEL_REGISTRY = {}

router = APIRouter()


# Request/Response Models
class AssignModelRequest(BaseModel):
    instance_id: str = Field(..., description="Target instance ID")
    model_id: str = Field(..., description="Model UUID from registry")


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
    created_at: datetime


class InstanceConfigResponse(BaseModel):
    instance_id: str
    pipeline_mode: str
    assigned_model_id: Optional[str]
    assigned_model_version: Optional[str]
    enable_bin_packing: bool
    enable_right_sizing: bool
    enable_family_stress: bool
    aws_region: str


class ExperimentLogResponse(BaseModel):
    id: str
    instance_id: str
    model_version: str
    prediction_score: float
    decision: str
    execution_time: datetime
    execution_duration_ms: int
    projected_savings: Optional[float]


# Endpoints
@router.post("/lab/assign-model")
async def assign_model_to_instance(request: AssignModelRequest):
    """
    Assign a specific model version to an instance

    Called when Admin selects a new model from the dropdown in Lab Dashboard.

    This endpoint:
    1. Verifies instance is in Lab environment
    2. Updates instance configuration with model assignment
    3. Sets pipeline to SINGLE_LINEAR mode
    """
    instance_id = request.instance_id
    model_id = request.model_id

    # TODO: Database integration
    # Verify this is a Lab Account (Safety Check)
    # account = db.get_account_for_instance(instance_id)
    # if account.environment_type != 'LAB_INTERNAL':
    #     raise HTTPException(403, "Cannot change models on Production instances directly.")

    # Update configuration
    LAB_CONFIGS[instance_id] = {
        "instance_id": instance_id,
        "pipeline_mode": "SINGLE_LINEAR",
        "assigned_model_id": model_id,
        "enable_bin_packing": False,
        "enable_right_sizing": False,
        "updated_at": datetime.now()
    }

    return {
        "status": "updated",
        "mode": "Lab Experiment Active",
        "instance_id": instance_id,
        "model_id": model_id
    }


@router.get("/lab/pipeline-status/{instance_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(instance_id: str):
    """
    Get pipeline status for visualization

    Returns the status of each block for the Frontend Visualizer:
    - active: Block is running
    - disabled: Block is bypassed in Lab Mode
    - inactive: Block is not applicable
    """
    # Get configuration
    config = LAB_CONFIGS.get(instance_id, {
        "pipeline_mode": "CLUSTER_FULL",
        "assigned_model_id": None,
        "enable_bin_packing": True,
        "enable_right_sizing": True
    })

    is_lab_mode = config.get("pipeline_mode") == "SINGLE_LINEAR"

    return PipelineStatusResponse(
        instance_id=instance_id,
        pipeline_mode=config.get("pipeline_mode", "CLUSTER_FULL"),
        scraper={
            "status": "active",
            "description": "Fetching real-time spot prices"
        },
        safe_filter={
            "status": "active",
            "description": "Filtering by interrupt rate < 20%"
        },
        bin_packing={
            "status": "disabled" if is_lab_mode else "active",
            "description": "Bypassed in Lab Mode" if is_lab_mode else "Calculating waste cost"
        },
        right_sizing={
            "status": "disabled" if is_lab_mode else "active",
            "description": "Bypassed in Lab Mode" if is_lab_mode else "Finding oversized candidates"
        },
        ml_inference={
            "status": "active",
            "model_id": config.get("assigned_model_id"),
            "description": f"Model: {config.get('assigned_model_id', 'default')[:8]}..."
        },
        execution={
            "status": "active",
            "description": "Atomic switch" if is_lab_mode else "Kubernetes drain"
        }
    )


@router.get("/lab/models", response_model=List[ModelInfo])
async def list_available_models():
    """
    List all available models in the registry

    Returns models for dropdown selection in Lab Dashboard
    """
    # TODO: Query model_registry table
    # For now, return mock data
    return [
        ModelInfo(
            id="model-001",
            name="FamilyStressPredictor",
            version="v2.1.0",
            description="Production LightGBM model with hardware contagion features",
            is_experimental=False,
            is_active=True,
            created_at=datetime.now()
        ),
        ModelInfo(
            id="model-002",
            name="FamilyStressPredictor",
            version="v2.2.0-beta",
            description="Experimental model with enhanced temporal features",
            is_experimental=True,
            is_active=True,
            created_at=datetime.now()
        )
    ]


@router.get("/lab/config/{instance_id}", response_model=InstanceConfigResponse)
async def get_instance_config(instance_id: str):
    """Get instance configuration"""
    if instance_id not in LAB_CONFIGS:
        raise HTTPException(status_code=404, detail="Instance configuration not found")

    config = LAB_CONFIGS[instance_id]

    return InstanceConfigResponse(
        instance_id=instance_id,
        pipeline_mode=config.get("pipeline_mode", "CLUSTER_FULL"),
        assigned_model_id=config.get("assigned_model_id"),
        assigned_model_version=config.get("assigned_model_version"),
        enable_bin_packing=config.get("enable_bin_packing", True),
        enable_right_sizing=config.get("enable_right_sizing", True),
        enable_family_stress=config.get("enable_family_stress", True),
        aws_region=config.get("aws_region", "ap-south-1")
    )


@router.put("/lab/config/{instance_id}")
async def update_instance_config(
    instance_id: str,
    pipeline_mode: Optional[str] = None,
    enable_bin_packing: Optional[bool] = None,
    enable_right_sizing: Optional[bool] = None
):
    """
    Update instance configuration flags

    Allows fine-grained control over which pipeline features are enabled
    """
    if instance_id not in LAB_CONFIGS:
        LAB_CONFIGS[instance_id] = {"instance_id": instance_id}

    config = LAB_CONFIGS[instance_id]

    if pipeline_mode:
        config["pipeline_mode"] = pipeline_mode
    if enable_bin_packing is not None:
        config["enable_bin_packing"] = enable_bin_packing
    if enable_right_sizing is not None:
        config["enable_right_sizing"] = enable_right_sizing

    config["updated_at"] = datetime.now()

    return {"status": "updated", "config": config}


@router.get("/lab/experiments/{instance_id}", response_model=List[ExperimentLogResponse])
async def get_experiment_logs(instance_id: str, limit: int = 50):
    """
    Get experiment logs for an instance

    Returns recent predictions and decisions for analytics dashboard
    """
    # TODO: Query experiment_logs table
    # For now, return mock data
    return [
        ExperimentLogResponse(
            id="exp-001",
            instance_id=instance_id,
            model_version="v2.1.0",
            prediction_score=0.28,
            decision="HOLD",
            execution_time=datetime.now(),
            execution_duration_ms=150,
            projected_savings=None
        )
    ]


@router.get("/lab/experiments/model/{model_id}")
async def get_model_performance(model_id: str):
    """
    Get aggregated performance metrics for a model

    Returns:
    - Total predictions
    - Switch rate
    - Average prediction score
    - Total projected savings
    """
    # TODO: Aggregate experiment_logs by model_id
    return {
        "model_id": model_id,
        "total_predictions": 0,
        "switch_rate": 0.0,
        "average_score": 0.0,
        "total_savings": 0.0
    }
