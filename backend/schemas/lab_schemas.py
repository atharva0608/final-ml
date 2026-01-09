from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class ExperimentBase(BaseModel):
    name: str
    description: Optional[str] = None
    control_model_id: str
    variant_model_id: str
    control_percentage: float = 50.0
    variant_percentage: float = 50.0
    target_metric: str
    duration_hours: int = 24

class ExperimentCreate(ExperimentBase):
    pass

class ExperimentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class ExperimentResponse(ExperimentBase):
    id: str
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime

class ExperimentList(BaseModel):
    experiments: List[ExperimentResponse]
    total: int

class ExperimentFilter(BaseModel):
    cluster_id: Optional[str] = None
    status: Optional[str] = None
    target_metric: Optional[str] = None
    search: Optional[str] = None
    page: int = 1
    page_size: int = 50

class VariantPerformance(BaseModel):
    model_id: str
    metric_score: float
    instance_count: int
    model_config = {'protected_namespaces': ()}

class ExperimentResults(BaseModel):
    experiment_id: str
    winner_variant_id: Optional[str] = None
    variants: List[VariantPerformance]

# Aliases
class TelemetryData(BaseModel):
    timestamp: datetime
    metrics: Dict[str, float]

class LabExperimentCreate(ExperimentCreate): pass
class LabExperimentResponse(ExperimentResponse): pass

class MLModelUpload(BaseModel):
    name: str
    version: str
    framework: str
    payload_url: str

class MLModelResponse(BaseModel):
    id: str
    name: str
    version: str
    status: str
    created_at: datetime

class MLModelList(BaseModel):
    models: List[MLModelResponse]
    total: int

class ABTestConfig(BaseModel):
    experiment_id: str
    traffic_split: Dict[str, float]

class ABTestVariant(BaseModel):
    variant_id: str
    model_id: str
    weight: float
    model_config = {'protected_namespaces': ()}

class ABTestResults(BaseModel):
    experiment_id: str
    winner: Optional[str] = None
    improvement_percentage: Optional[float] = None
    control_stats: Dict[str, Any]
    variant_stats: Dict[str, Any]

class ModelPromoteRequest(BaseModel):
    model_id: str
    environment: str
    model_config = {'protected_namespaces': ()}
