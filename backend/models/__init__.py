"""
Database models for Spot Optimizer Platform
"""
from backend.models.user import User
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.instance import Instance
from backend.models.cluster_policy import ClusterPolicy
from backend.models.hibernation_schedule import HibernationSchedule
from backend.models.audit_log import AuditLog
from backend.models.ml_model import MLModel
from backend.models.node_template import NodeTemplate, NodeTemplateVersion, ClusterTemplateMapping
from backend.models.optimization_job import OptimizationJob
from backend.models.lab_experiment import LabExperiment
from backend.models.agent_action import AgentAction, AgentActionStatus, AgentActionType
from backend.models.cluster_metric import ClusterMetric
from backend.models.pod_metric import PodMetric
from backend.models.api_key import APIKey
from backend.models.team import Team
from backend.models.authorized_resource import AuthorizedResource
from backend.models.permission import Permission
from backend.models.role import Role, RoleType, role_permissions
from backend.models.approval import Approval, ApprovalType, ApprovalStatus, ReasonCategory
from backend.models.platform_settings import PlatformSettings
from backend.models.organization import Organization
from backend.models.rds_analysis import RDSInstanceAnalysis
from backend.models.savings_plan_utilization import SavingsPlanUtilization
from backend.models.transfer_analysis import DataTransferAnalysis
from backend.models.onboarding import OnboardingState

# Billing / Cost Explorer Models
from backend.models.billing import DailyCost, CostExplorerSyncStatus

# Tag Management Models
from backend.models.tag_policy import TagPolicy, EnforcementLevel, ValueMode
from backend.models.auto_tag_rule import AutoTagRule, RunMode
from backend.models.tag_template import TagTemplate

from backend.models.tag_scoring_config import TagScoringConfig
from backend.models.tag_automation_rule import TagAutomationRule
from backend.models.tag_compliance_score import TagComplianceScore
from backend.models.tag_automation_log import TagAutomationLog

# Decision Engine v3 Models
from backend.models.cluster_cooldown import ClusterCooldown
from backend.models.pool_cooldown import PoolCooldown
from backend.models.substitute_state import SubstituteState
from backend.models.optimizer_state import OptimizerState
from backend.models.rightsizing_proposal import RightsizingProposal

# Phase 1 Remediation Models
from backend.models.instance_catalog import InstanceCatalog
from backend.models.node_template import NodeTemplate

# Phase 2 Remediation Models
from backend.models.family_hour_baseline import FamilyHourBaseline
from backend.models.model_registry import ModelRegistry

# Phase 3 Remediation Models
from backend.models.execution_state import ExecutionState, ExecutionStateEnum

# Phase 8 Remediation Models
from backend.models.circuit_breaker_state import CircuitBreakerState

# Phase 4 Remediation Models (Security & Alerting)
from backend.models.alert_config import AlertConfig, AlertChannel, AlertSeverity, AlertType
from backend.models.alert_history import AlertHistory, AlertStatus

# Phase 6 Remediation Models (JIT Security)
from backend.models.credential_cache import CredentialCache

# Phase 7 Remediation Models (Agent Security)
from backend.models.agent_identity import AgentIdentity

# Phase 9 Remediation Models (Chaos Testing)
from backend.models.chaos_experiment import ChaosExperiment, ChaosExperimentType, ChaosExperimentStatus

# Hygiene/Cleanup Models
from backend.models.hygiene_policy import HygienePolicy

# Multi-Cluster Dashboard Aggregation
from backend.models.daily_cluster_stats import DailyClusterStat

# Spot Optimizer New Models
from backend.models.spot_advisor_rates import SpotAdvisorRate
from backend.models.optimizer_proposal import OptimizerProposal, ProposalStatus
from backend.models.substitute_nodes import SubstituteNode, SubstituteNodeState

__all__ = [
    "User",
    "Organization",
    "Account",
    "Cluster",
    "Instance",
    "ClusterPolicy",
    "HibernationSchedule",
    "AuditLog",
    "MLModel",
    "NodeTemplate",
    "NodeTemplateVersion",
    "ClusterTemplateMapping",
    "OptimizationJob",
    "LabExperiment",
    "AgentAction",
    "AgentActionStatus",
    "AgentActionType",
    "ClusterMetric",
    "PodMetric",
    "APIKey",
    "Team",
    "AuthorizedResource",
    "Permission",
    "Role",
    "Approval",
    "RIUtilization",
    "S3BucketAnalysis",
    "RDSAnalysis",
    "DataTransferAnalysis",
    "SavingsPlanUtilization",
    "OnboardingState",
    # Billing / Cost Explorer
    "DailyCost",
    "CostExplorerSyncStatus",
    # Tag Management
    "TagPolicy",
    "AutoTagRule",
    "TagTemplate",
    "EnforcementLevel",
    "ValueMode",
    "RunMode",
    "TagScoringConfig",
    "TagAutomationRule",
    "TagComplianceScore",
    "TagAutomationLog",
    # Decision Engine v3
    "ClusterCooldown",
    "PoolCooldown",
    "SubstituteState",
    "OptimizerState",
    "RightsizingProposal",
    # Phase 1 Remediation
    "InstanceCatalog",
    "NodeTemplate",
    # Phase 2 Remediation
    "FamilyHourBaseline",
    "ModelRegistry",
    # Phase 3 Remediation
    "ExecutionState",
    "ExecutionStateEnum",
    # Phase 4 Remediation (Security & Alerting)
    "AlertConfig",
    "AlertChannel",
    "AlertSeverity",
    "AlertType",
    "AlertHistory",
    "AlertStatus",
    # Phase 6 Remediation (JIT Security)
    "CredentialCache",
    # Phase 7 Remediation (Agent Security)
    "AgentIdentity",
    # Phase 8 Remediation
    "CircuitBreakerState",
    # Phase 9 Remediation (Chaos Testing)
    "ChaosExperiment",
    "ChaosExperimentType",
    "ChaosExperimentStatus",
    # Hygiene/Cleanup
    "HygienePolicy",
    # Multi-Cluster Dashboard Aggregation
    "DailyClusterStat",
    # Spot Optimizer New Models
    "SpotAdvisorRate",
    "OptimizerProposal",
    "ProposalStatus",
    "SubstituteNode",
    "SubstituteNodeState",
]
