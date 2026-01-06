"""
Lab Schemas - Request/Response models for ML experimentation and A/B testing
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class TelemetryData(BaseModel):
    """Telemetry data from experiment"""
    cpu_utilization: float = Field(..., ge=0, le=100, description="CPU utilization percentage")
    memory_utilization: float = Field(..., ge=0, le=100, description="Memory utilization percentage")
    network_bytes_in: int = Field(..., ge=0, description="Network bytes in")
    network_bytes_out: int = Field(..., ge=0, description="Network bytes out")
    disk_read_bytes: int = Field(..., ge=0, description="Disk read bytes")
    disk_write_bytes: int = Field(..., ge=0, description="Disk write bytes")
    custom_metrics: Optional[Dict[str, Any]] = Field(None, description="Custom experiment metrics")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cpu_utilization": 45.2,
                "memory_utilization": 62.8,
                "network_bytes_in": 1024000,
                "network_bytes_out": 512000,
                "disk_read_bytes": 2048000,
                "disk_write_bytes": 1024000,
                "custom_metrics": {
                    "request_latency_ms": 125.3,
                    "error_rate": 0.01
                }
            }
        }
    }


class LabExperimentCreate(BaseModel):
    """Create lab experiment request"""
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "model_id": "ff0e8400-e29b-41d4-a716-446655440000",
                "instance_id": "i-0abc12345def67890",
                "test_type": "A/B",
                "telemetry": {
                    "cpu_utilization": 45.2,
                    "memory_utilization": 62.8,
                    "network_bytes_in": 1024000,
                    "network_bytes_out": 512000,
                    "disk_read_bytes": 2048000,
                    "disk_write_bytes": 1024000
                }
            }
        }
    }

    model_id: str = Field(..., description="ML model UUID")
    instance_id: str = Field(..., description="AWS instance ID for testing")
    test_type: str = Field(..., description="Test type (A/B, CANARY, SHADOW)")
    telemetry: TelemetryData = Field(..., description="Telemetry data from experiment")

    @field_validator('test_type')
    @classmethod
    def validate_test_type(cls, v: str) -> str:
        if v not in ['A/B', 'CANARY', 'SHADOW']:
            raise ValueError('Test type must be A/B, CANARY, or SHADOW')
        return v


class LabExperimentResponse(BaseModel):
    """Lab experiment response"""
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "id": "000e8400-e29b-41d4-a716-446655440000",
                "model_id": "ff0e8400-e29b-41d4-a716-446655440000",
                "instance_id": "i-0abc12345def67890",
                "test_type": "A/B",
                "telemetry": {
                    "cpu_utilization": 45.2,
                    "memory_utilization": 62.8,
                    "network_bytes_in": 1024000,
                    "network_bytes_out": 512000,
                    "disk_read_bytes": 2048000,
                    "disk_write_bytes": 1024000
                },
                "created_at": "2025-12-31T12:00:00Z"
            }
        }
    }

    id: str = Field(..., description="Experiment UUID")
    model_id: str = Field(..., description="ML model UUID")
    instance_id: str = Field(..., description="AWS instance ID")
    test_type: str = Field(..., description="Test type")
    telemetry: TelemetryData = Field(..., description="Telemetry data")
    created_at: datetime = Field(..., description="Experiment creation timestamp")


class MLModelUpload(BaseModel):
    """ML model upload request"""
    version: str = Field(..., min_length=1, max_length=50, description="Model version (e.g., v1.2.3)")
    file_path: str = Field(..., description="Path to model file in storage")
    performance_metrics: Optional[Dict[str, Any]] = Field(None, description="Model performance metrics")

    model_config = {
        "json_schema_extra": {
            "example": {
                "version": "v1.2.3",
                "file_path": "/models/spot-optimizer-v1.2.3.pkl",
                "performance_metrics": {
                    "accuracy": 0.95,
                    "precision": 0.93,
                    "recall": 0.96,
                    "f1_score": 0.945
                }
            }
        }
    }


class MLModelResponse(BaseModel):
    """ML model response"""
    id: str = Field(..., description="Model UUID")
    version: str = Field(..., description="Model version")
    file_path: str = Field(..., description="Model file path")
    status: str = Field(..., description="Model status (TESTING, PRODUCTION, DEPRECATED)")
    performance_metrics: Optional[Dict[str, Any]] = Field(None, description="Performance metrics")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    validated_at: Optional[datetime] = Field(None, description="Validation timestamp")
    promoted_at: Optional[datetime] = Field(None, description="Production promotion timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "ff0e8400-e29b-41d4-a716-446655440000",
                "version": "v1.2.3",
                "file_path": "/models/spot-optimizer-v1.2.3.pkl",
                "status": "PRODUCTION",
                "performance_metrics": {
                    "accuracy": 0.95,
                    "precision": 0.93,
                    "recall": 0.96
                },
                "uploaded_at": "2025-12-30T10:00:00Z",
                "validated_at": "2025-12-30T15:00:00Z",
                "promoted_at": "2025-12-31T09:00:00Z"
            }
        }
    }


class MLModelList(BaseModel):
    """List of ML models"""
    models: List[MLModelResponse] = Field(..., description="Array of ML models")
    total: int = Field(..., ge=0, description="Total number of models")

    model_config = {
        "json_schema_extra": {
            "example": {
                "models": [
                    {
                        "id": "ff0e8400-e29b-41d4-a716-446655440000",
                        "version": "v1.2.3",
                        "file_path": "/models/spot-optimizer-v1.2.3.pkl",
                        "status": "PRODUCTION",
                        "performance_metrics": {"accuracy": 0.95},
                        "uploaded_at": "2025-12-30T10:00:00Z",
                        "validated_at": "2025-12-30T15:00:00Z",
                        "promoted_at": "2025-12-31T09:00:00Z"
                    }
                ],
                "total": 1
            }
        }
    }


class ABTestConfig(BaseModel):
    """A/B test configuration"""
    name: str = Field(..., min_length=1, max_length=255, description="Test name")
    control_model_id: str = Field(..., description="Control (current) model UUID")
    treatment_model_id: str = Field(..., description="Treatment (new) model UUID")
    traffic_split: float = Field(..., ge=0, le=100, description="Percentage of traffic to treatment")
    duration_hours: int = Field(..., ge=1, le=168, description="Test duration in hours")
    success_metrics: List[str] = Field(..., description="Metrics to track for success")
    minimum_sample_size: int = Field(default=1000, ge=100, description="Minimum sample size per variant")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Spot Optimizer v1.2.3 vs v1.3.0",
                "control_model_id": "ff0e8400-e29b-41d4-a716-446655440000",
                "treatment_model_id": "000e8400-e29b-41d4-a716-446655440000",
                "traffic_split": 20.0,
                "duration_hours": 72,
                "success_metrics": ["cost_savings", "interruption_rate", "prediction_accuracy"],
                "minimum_sample_size": 5000
            }
        }
    }


class ABTestVariant(BaseModel):
    """A/B test variant results"""
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "model_id": "ff0e8400-e29b-41d4-a716-446655440000",
                "model_version": "v1.2.3",
                "sample_size": 8000,
                "metrics": {
                    "cost_savings": 27.5,
                    "interruption_rate": 2.3,
                    "prediction_accuracy": 0.95
                },
                "confidence_interval": {
                    "cost_savings": {"lower": 26.2, "upper": 28.8}
                }
            }
        }
    }

    model_id: str = Field(..., description="Model UUID")
    model_version: str = Field(..., description="Model version")
    sample_size: int = Field(..., ge=0, description="Number of samples")
    metrics: Dict[str, float] = Field(..., description="Variant metrics")
    confidence_interval: Optional[Dict[str, Any]] = Field(None, description="Confidence intervals")


class ABTestResults(BaseModel):
    """A/B test results"""
    test_id: str = Field(..., description="Test UUID")
    name: str = Field(..., description="Test name")
    status: str = Field(..., description="Test status (RUNNING, COMPLETED, STOPPED)")
    start_time: datetime = Field(..., description="Test start time")
    end_time: Optional[datetime] = Field(None, description="Test end time")
    control: ABTestVariant = Field(..., description="Control variant results")
    treatment: ABTestVariant = Field(..., description="Treatment variant results")
    winner: Optional[str] = Field(None, description="Winning variant (control or treatment)")
    statistical_significance: Optional[float] = Field(None, ge=0, le=1, description="P-value for significance")
    recommendation: Optional[str] = Field(None, description="Test recommendation")

    model_config = {
        "json_schema_extra": {
            "example": {
                "test_id": "110e8400-e29b-41d4-a716-446655440000",
                "name": "Spot Optimizer v1.2.3 vs v1.3.0",
                "status": "COMPLETED",
                "start_time": "2025-12-28T00:00:00Z",
                "end_time": "2025-12-31T00:00:00Z",
                "control": {
                    "model_id": "ff0e8400-e29b-41d4-a716-446655440000",
                    "model_version": "v1.2.3",
                    "sample_size": 8000,
                    "metrics": {"cost_savings": 27.5}
                },
                "treatment": {
                    "model_id": "000e8400-e29b-41d4-a716-446655440000",
                    "model_version": "v1.3.0",
                    "sample_size": 2000,
                    "metrics": {"cost_savings": 31.2}
                },
                "winner": "treatment",
                "statistical_significance": 0.03,
                "recommendation": "Promote v1.3.0 to production"
            }
        }
    }


class ModelPromoteRequest(BaseModel):
    """Request to promote model to production"""
    reason: str = Field(..., min_length=10, max_length=512, description="Reason for promotion")

    model_config = {
        "json_schema_extra": {
            "example": {
                "reason": "A/B test shows 13% improvement in cost savings with statistical significance p<0.05"
            }
        }
    }


class LabExperimentUpdate(BaseModel):
    """Update lab experiment"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    control_percentage: Optional[int] = Field(None, ge=0, le=100)
    variant_percentage: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[str] = Field(None, description="Experiment status")
    
    model_config = {
        "protected_namespaces": ()
    }


class LabExperimentFilter(BaseModel):
    """Filter for experiments"""
    search: Optional[str] = Field(None)
    status: Optional[str] = Field(None)
    model_id: Optional[str] = Field(None)
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=100)


class LabExperimentList(BaseModel):
    """List of experiments"""
    experiments: List[LabExperimentResponse] = Field(..., description="List of experiments")
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)


# Aliases for backward compatibility
ExperimentCreate = LabExperimentCreate
ExperimentUpdate = LabExperimentUpdate
ExperimentResponse = LabExperimentResponse
ExperimentList = LabExperimentList
ExperimentFilter = LabExperimentFilter
ExperimentResults = ABTestResults
VariantPerformance = ABTestVariant
