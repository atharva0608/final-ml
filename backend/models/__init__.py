"""
Database models for Spot Optimizer Platform
"""
from backend.models.user import User
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.instance import Instance
from backend.models.node_template import NodeTemplate
from backend.models.cluster_policy import ClusterPolicy
from backend.models.hibernation_schedule import HibernationSchedule
from backend.models.audit_log import AuditLog
from backend.models.ml_model import MLModel
from backend.models.optimization_job import OptimizationJob
from backend.models.lab_experiment import LabExperiment
from backend.models.agent_action import AgentAction, AgentActionStatus, AgentActionType
from backend.models.cluster_metric import ClusterMetric
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
from backend.models.savings_plan_utilization import SavingsPlanUtilization
from backend.models.transfer_analysis import DataTransferAnalysis
from backend.models.onboarding import OnboardingState

# Billing / Cost Explorer Models
from backend.models.billing import DailyCost, CostExplorerSyncStatus

# Tag Management Models
from backend.models.tag_policy import TagPolicy, EnforcementLevel, ValueMode
from backend.models.tag_template import TagTemplate
from backend.models.auto_tag_rule import AutoTagRule, RunMode

from backend.models.tag_scoring_config import TagScoringConfig
from backend.models.tag_automation_rule import TagAutomationRule
from backend.models.tag_compliance_score import TagComplianceScore
from backend.models.tag_automation_log import TagAutomationLog

__all__ = [
    "User",
    "Organization",
    "Account",
    "Cluster",
    "Instance",
    "NodeTemplate",
    "ClusterPolicy",
    "HibernationSchedule",
    "AuditLog",
    "MLModel",
    "OptimizationJob",
    "LabExperiment",
    "AgentAction",
    "AgentActionStatus",
    "AgentActionType",
    "ClusterMetric",
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
    "TagTemplate",
    "AutoTagRule",
    "EnforcementLevel",
    "ValueMode",
    "RunMode",
    "TagScoringConfig",
    "TagAutomationRule",
    "TagComplianceScore",
    "TagAutomationLog",
]
