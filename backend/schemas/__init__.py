"""
Pydantic Schemas Package

Request/response validation schemas for all API endpoints
"""

# Authentication schemas
from backend.schemas.auth_schemas import (
    SignupRequest,
    LoginRequest,
    TokenResponse,
    UserContext,
    UserProfile,
    PasswordChangeRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
)

# Cluster schemas
from backend.schemas.cluster_schemas import (
    ClusterListItem,
    ClusterList,
    InstanceInfo,
    ClusterDetail,
    HeartbeatRequest,
    AgentCommandResponse,
    AgentCommandList,
    AgentCommandResult,
    OptimizationJobId,
    OptimizationJobResult,
)

# Template schemas
from backend.schemas.template_schemas import (
    NodeTemplateCreate,
    NodeTemplateUpdate,
    NodeTemplateResponse,
    NodeTemplateList,
    TemplateValidationResult,
)

# Policy schemas
from backend.schemas.policy_schemas import (
    BinpackSettings,
    ExclusionRules,
    PolicyConfig,
    PolicyUpdate,
    PolicyState,
    PolicyValidationResult,
)

# Hibernation schemas
from backend.schemas.hibernation_schemas import (
    ScheduleMatrix,
    HibernationScheduleCreate,
    HibernationScheduleUpdate,
    HibernationScheduleResponse,
    ScheduleOverride,
    SchedulePreview,
    SchedulePreviewResponse,
)

# Metric schemas
from backend.schemas.metric_schemas import (
    KPISet,
    ChartDataPoint,
    ChartData,
    MultiSeriesChartData,
    PieChartSlice,
    PieChartData,
    ActivityFeedItem,
    ActivityFeed,
    CostBreakdown,
    ClusterMetrics,
    DashboardMetrics,
)

# Audit schemas
from backend.schemas.audit_schemas import (
    DiffData,
    AuditLog,
    AuditLogList,
    AuditLogFilter,
    AuditEventStats,
    AuditSummary,
    ComplianceReport,
)

# Admin schemas
from backend.schemas.admin_schemas import (
    ClientListItem,
    ClientList,
    ClientOrganization,
    SystemHealth,
    PlatformStats,
    UserAction,
    CreateUserRequest,
    ImpersonateRequest,
    ImpersonateResponse,
)

# Lab schemas
from backend.schemas.lab_schemas import (
    TelemetryData,
    LabExperimentCreate,
    LabExperimentResponse,
    MLModelUpload,
    MLModelResponse,
    MLModelList,
    ABTestConfig,
    ABTestVariant,
    ABTestResults,
    ModelPromoteRequest,
)

__all__ = [
    # Auth
    "SignupRequest",
    "LoginRequest",
    "TokenResponse",
    "UserContext",
    "UserProfile",
    "PasswordChangeRequest",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    # Cluster
    "ClusterListItem",
    "ClusterList",
    "InstanceInfo",
    "ClusterDetail",
    "HeartbeatRequest",
    "AgentCommandResponse",
    "AgentCommandList",
    "AgentCommandResult",
    "OptimizationJobId",
    "OptimizationJobResult",
    # Template
    "NodeTemplateCreate",
    "NodeTemplateUpdate",
    "NodeTemplateResponse",
    "NodeTemplateList",
    "TemplateValidationResult",
    # Policy
    "BinpackSettings",
    "ExclusionRules",
    "PolicyConfig",
    "PolicyUpdate",
    "PolicyState",
    "PolicyValidationResult",
    # Hibernation
    "ScheduleMatrix",
    "HibernationScheduleCreate",
    "HibernationScheduleUpdate",
    "HibernationScheduleResponse",
    "ScheduleOverride",
    "SchedulePreview",
    "SchedulePreviewResponse",
    # Metrics
    "KPISet",
    "ChartDataPoint",
    "ChartData",
    "MultiSeriesChartData",
    "PieChartSlice",
    "PieChartData",
    "ActivityFeedItem",
    "ActivityFeed",
    "CostBreakdown",
    "ClusterMetrics",
    "DashboardMetrics",
    # Audit
    "DiffData",
    "AuditLog",
    "AuditLogList",
    "AuditLogFilter",
    "AuditEventStats",
    "AuditSummary",
    "ComplianceReport",
    # Admin
    "ClientListItem",
    "ClientList",
    "ClientOrganization",
    "SystemHealth",
    "PlatformStats",
    "UserAction",
    "CreateUserRequest",
    "ImpersonateRequest",
    "ImpersonateResponse",
    # Lab
    "TelemetryData",
    "LabExperimentCreate",
    "LabExperimentResponse",
    "MLModelUpload",
    "MLModelResponse",
    "MLModelList",
    "ABTestConfig",
    "ABTestVariant",
    "ABTestResults",
    "ModelPromoteRequest",
]
