"""
Feature Registry - Central registry for all protected features requiring JIT approvals

This module defines all features that require Just-In-Time privilege escalation.
Each feature has metadata including display information, permission requirements,
and approval constraints.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class FeatureCategory(str, Enum):
    """High-level categorization of features"""
    COMPUTE = "compute"
    STORAGE = "storage"
    DATABASE = "database"
    NETWORK = "network"
    CLOUD = "cloud"
    HYGIENE = "hygiene"
    GOVERNANCE = "governance"
    TEAM = "team"
    BILLING = "billing"
    SECURITY = "security"
    AUDIT = "audit"


@dataclass
class Feature:
    """Definition of a protected feature"""
    id: str  # Unique identifier (e.g., "hygiene:execute")
    name: str  # Display name
    description: str  # User-facing description
    category: FeatureCategory
    permission_slug: str  # Required permission (e.g., "hygiene:execute")
    requires_approval: bool = True  # Whether approval is needed
    max_duration_hours: int = 24  # Maximum time window allowed
    default_duration_hours: int = 1  # Default duration for requests
    min_approver_role: str = "TEAM_LEAD"  # Minimum role that can approve
    risk_level: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    requires_reason: bool = True  # Whether justification is mandatory
    supports_resource_scope: bool = True  # Whether can be scoped to specific resources
    ui_icon: str = "shield"  # Icon for frontend display
    ui_color: str = "yellow"  # Color theme for frontend


# ============================================================================
# FEATURE DEFINITIONS
# ============================================================================

FEATURE_REGISTRY: Dict[str, Feature] = {
    # ========== COMPUTE OPERATIONS ==========
    "compute:terminate": Feature(
        id="compute:terminate",
        name="Terminate Instances",
        description="Terminate EC2 instances or container workloads",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:terminate:any",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="power-off",
        ui_color="red"
    ),

    "feat-instance-terminate": Feature(
        id="feat-instance-terminate",
        name="Terminate Instance",
        description="Gracefully drains and shuts down a specific EC2 node",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:terminate:any",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="power-off",
        ui_color="red"
    ),

    "feat-instance-reboot": Feature(
        id="feat-instance-reboot",
        name="Reboot Instance",
        description="Restarts a node for troubleshooting or maintenance",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:reboot",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="refresh-cw",
        ui_color="orange"
    ),

    "compute:stop": Feature(
        id="compute:stop",
        name="Stop Instances",
        description="Stop running instances (non-destructive)",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:stop",
        requires_approval=True,
        max_duration_hours=8,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="pause",
        ui_color="yellow"
    ),

    "feat-instance-stop": Feature(
        id="feat-instance-stop",
        name="Stop Instance",
        description="Powers down an instance while preserving its root EBS volume",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:stop",
        requires_approval=True,
        max_duration_hours=8,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="pause-circle",
        ui_color="yellow"
    ),

    "feat-instance-launch-spot": Feature(
        id="feat-instance-launch-spot",
        name="Manual Spot Launch",
        description="Manually creates a Spot instance to replace an existing On-Demand node",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:launch",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="zap",
        ui_color="purple"
    ),

    "feat-asg-scale": Feature(
        id="feat-asg-scale",
        name="Update ASG Capacity",
        description="Manually overrides the Min/Max/Desired count of an Auto Scaling Group",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:asg_modify",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="sliders",
        ui_color="blue"
    ),

    "compute:modify": Feature(
        id="compute:modify",
        name="Modify Compute Resources",
        description="Change instance types, scaling groups, or configurations",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:modify",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="edit",
        ui_color="blue"
    ),

    # ========== STORAGE OPERATIONS ==========
    "storage:delete": Feature(
        id="storage:delete",
        name="Delete Storage Resources",
        description="Delete volumes, snapshots, or persistent storage",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:delete:any",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="trash",
        ui_color="red"
    ),

    "feat-ebs-detach": Feature(
        id="feat-ebs-detach",
        name="Detach Volume",
        description="Unmounts an EBS volume from a running or stopped instance",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:detach",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="unlink",
        ui_color="orange"
    ),

    "feat-ebs-delete": Feature(
        id="feat-ebs-delete",
        name="Delete Unattached Volume",
        description="Permanently deletes orphaned EBS volumes to eliminate storage costs",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:delete:any",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="trash-2",
        ui_color="red"
    ),

    "feat-ebs-resize": Feature(
        id="feat-ebs-resize",
        name="Modify Volume",
        description="Increases volume size or changes the volume type (e.g., converting gp2 to gp3)",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:modify",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="maximize",
        ui_color="blue"
    ),

    "feat-s3-policy-edit": Feature(
        id="feat-s3-policy-edit",
        name="Update Lifecycle Policy",
        description="Manually triggers or modifies S3 Glacier/Intelligent Tiering transitions",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:s3_lifecycle",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="archive",
        ui_color="blue"
    ),

    # ========== DATABASE OPERATIONS ==========
    "db:delete": Feature(
        id="db:delete",
        name="Delete Databases",
        description="Delete RDS instances or database clusters",
        category=FeatureCategory.DATABASE,
        permission_slug="db:delete",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="database-delete",
        ui_color="red"
    ),

    "db:stop": Feature(
        id="db:stop",
        name="Stop Databases",
        description="Stop RDS instances (non-destructive)",
        category=FeatureCategory.DATABASE,
        permission_slug="db:stop",
        requires_approval=True,
        max_duration_hours=8,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="database-pause",
        ui_color="yellow"
    ),

    # ========== NETWORK OPERATIONS ==========
    "network:modify": Feature(
        id="network:modify",
        name="Modify Network Resources",
        description="Change security groups, load balancers, or network ACLs",
        category=FeatureCategory.NETWORK,
        permission_slug="network:modify",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="network",
        ui_color="orange"
    ),

    "network:delete": Feature(
        id="network:delete",
        name="Delete Network Resources",
        description="Delete Elastic IPs, load balancers, or network interfaces",
        category=FeatureCategory.NETWORK,
        permission_slug="network:delete",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="network-delete",
        ui_color="red"
    ),

    # ========== CLOUD INTEGRATION ==========
    "cloud:connect": Feature(
        id="cloud:connect",
        name="Connect AWS Account",
        description="Connect new AWS accounts to Spot Optimizer",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:connect",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="cloud-plus",
        ui_color="blue"
    ),

    "feat-account-add": Feature(
        id="feat-account-add",
        name="Link AWS Account",
        description="Allows adding a new AWS account using IAM roles and External IDs",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:connect",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="link",
        ui_color="blue"
    ),

    "cloud:disconnect": Feature(
        id="cloud:disconnect",
        name="Disconnect AWS Account",
        description="Remove AWS account integration from Spot Optimizer",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:disconnect",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="cloud-minus",
        ui_color="red"
    ),

    "feat-account-remove": Feature(
        id="feat-account-remove",
        name="Disconnect AWS Account",
        description="Permanently removes an account and stops all background scanning",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:disconnect",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="x-circle",
        ui_color="red"
    ),

    "feat-iam-reverify": Feature(
        id="feat-iam-reverify",
        name="Validate Credentials",
        description="Manually triggers an STS check to verify if the platform still has cross-account access",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:verify",
        requires_approval=False,  # Low risk - just checking
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=True,
        ui_icon="check-circle",
        ui_color="green"
    ),

    "feat-cluster-deregister": Feature(
        id="feat-cluster-deregister",
        name="Deregister Cluster",
        description="Removes a cluster from the management dashboard without deleting the physical resource",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:cluster_deregister",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="minus-circle",
        ui_color="orange"
    ),

    # ========== RESOURCE HYGIENE ==========
    "hygiene:execute": Feature(
        id="hygiene:execute",
        name="Execute Resource Cleanup",
        description="Terminate, delete, or release resources flagged by hygiene scans",
        category=FeatureCategory.HYGIENE,
        permission_slug="hygiene:execute",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="broom",
        ui_color="yellow"
    ),

    "hygiene:scan": Feature(
        id="hygiene:scan",
        name="Run Hygiene Scan",
        description="Scan AWS accounts for orphaned or wasteful resources",
        category=FeatureCategory.HYGIENE,
        permission_slug="hygiene:scan",
        requires_approval=False,  # Low risk, just scanning
        max_duration_hours=24,
        default_duration_hours=8,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=True,
        ui_icon="search",
        ui_color="green"
    ),

    "hygiene:view_costs": Feature(
        id="hygiene:view_costs",
        name="View Cost Analysis",
        description="View detailed cost breakdowns and savings opportunities",
        category=FeatureCategory.HYGIENE,
        permission_slug="hygiene:view_costs",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="dollar-sign",
        ui_color="green"
    ),

    # ========== HIBERNATION & SCHEDULING ==========
    "feat-hibernation-create": Feature(
        id="feat-hibernation-create",
        name="Set New Schedule",
        description="Allows creating a 168-hour Wake/Sleep matrix for a cluster",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="hibernation:create",
        requires_approval=True,
        max_duration_hours=24,
        default_duration_hours=8,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="calendar",
        ui_color="blue"
    ),

    "feat-hibernation-toggle": Feature(
        id="feat-hibernation-toggle",
        name="Enable/Disable Schedule",
        description="Turns the existing hibernation logic on or off for a cluster",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="hibernation:toggle",
        requires_approval=True,
        max_duration_hours=8,
        default_duration_hours=4,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="toggle-right",
        ui_color="blue"
    ),

    "feat-hibernation-override": Feature(
        id="feat-hibernation-override",
        name="Manual Wake/Sleep",
        description="Triggers an immediate Wake or Sleep command that ignores the current schedule bit",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="hibernation:override",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="zap",
        ui_color="orange"
    ),

    # ========== GOVERNANCE ==========
    "approval:approve": Feature(
        id="approval:approve",
        name="Approve Access Requests",
        description="Approve JIT access requests from team members",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="approval:approve",
        requires_approval=False,  # Team leads have this by default
        max_duration_hours=168,  # 1 week
        default_duration_hours=24,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="check-circle",
        ui_color="green"
    ),

    "approval:reject": Feature(
        id="approval:reject",
        name="Reject Access Requests",
        description="Reject JIT access requests from team members",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="approval:reject",
        requires_approval=False,
        max_duration_hours=168,
        default_duration_hours=24,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="x-circle",
        ui_color="red"
    ),

    "approval:bypass": Feature(
        id="approval:bypass",
        name="Bypass Approval Requirements",
        description="Execute actions without approval (emergency use only)",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="approval:bypass",
        requires_approval=True,  # Requires ORG_ADMIN approval
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="alert-triangle",
        ui_color="red"
    ),

    "feat-automation-master-toggle": Feature(
        id="feat-automation-master-toggle",
        name="Toggle Global Automation",
        description="The master switch to enable or disable all background system actions",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="automation:master_toggle",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="power",
        ui_color="red"
    ),

    "feat-automation-approval-config": Feature(
        id="feat-automation-approval-config",
        name="Configure HITL",
        description="Toggles whether system-generated optimizations require human approval",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="automation:config",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="settings",
        ui_color="orange"
    ),

    "feat-policy-binpack-update": Feature(
        id="feat-policy-binpack-update",
        name="Edit Bin-Packing",
        description="Changes the aggressiveness of node consolidation policies",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="policy:binpack",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="package",
        ui_color="blue"
    ),

    "feat-tag-template-delete": Feature(
        id="feat-tag-template-delete",
        name="Delete Tag Template",
        description="Removes a standardized tagging blueprint from the organization",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="tag:template_delete",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="tag",
        ui_color="gray"
    ),

    "feat-team-lead-assign": Feature(
        id="feat-team-lead-assign",
        name="Promote to Team Lead",
        description="Elevates a Member's role within a specific team",
        category=FeatureCategory.TEAM,
        permission_slug="team:promote",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="user-check",
        ui_color="purple"
    ),

    # ========== LAB & EXPERIMENTAL ==========
    "feat-lab-live-switch": Feature(
        id="feat-lab-live-switch",
        name="Execute Live Switch",
        description="Runs the experimental Stop → Detach → Launch Spot → Reattach workflow",
        category=FeatureCategory.COMPUTE,
        permission_slug="lab:live_switch",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="flask",
        ui_color="red"
    ),

    "feat-model-promote": Feature(
        id="feat-model-promote",
        name="Promote ML Model",
        description="Graduates a specific ML model version to production for all optimization decisions",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="ml:model_promote",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="trending-up",
        ui_color="purple"
    ),

    # ========== TEAM MANAGEMENT ==========
    "team:invite": Feature(
        id="team:invite",
        name="Invite Team Members",
        description="Send invitations to join the team or organization",
        category=FeatureCategory.TEAM,
        permission_slug="team:invite",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=8,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="user-plus",
        ui_color="blue"
    ),

    "team:remove": Feature(
        id="team:remove",
        name="Remove Team Members",
        description="Remove users from team or revoke organization access",
        category=FeatureCategory.TEAM,
        permission_slug="team:remove_member",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="user-minus",
        ui_color="red"
    ),

    "team:promote": Feature(
        id="team:promote",
        name="Promote Team Members",
        description="Elevate user roles (Member to Team Lead, etc.)",
        category=FeatureCategory.TEAM,
        permission_slug="team:promote",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="arrow-up-circle",
        ui_color="purple"
    ),

    # ========== BILLING ==========
    "billing:view": Feature(
        id="billing:view",
        name="View Billing Information",
        description="Access spending reports, invoices, and payment history",
        category=FeatureCategory.BILLING,
        permission_slug="billing:view_spend",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="credit-card",
        ui_color="green"
    ),

    "billing:manage": Feature(
        id="billing:manage",
        name="Manage Payment Methods",
        description="Add, update, or remove credit cards and payment methods",
        category=FeatureCategory.BILLING,
        permission_slug="billing:manage_cc",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="credit-card-edit",
        ui_color="orange"
    ),

    # ========== SECURITY (SOC 2) ==========
    "security:mfa": Feature(
        id="security:mfa",
        name="Manage MFA Settings",
        description="Configure or disable multi-factor authentication",
        category=FeatureCategory.SECURITY,
        permission_slug="auth:manage_mfa",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="shield",
        ui_color="red"
    ),

    "security:sso": Feature(
        id="security:sso",
        name="Manage SSO Configuration",
        description="Configure or modify Single Sign-On settings",
        category=FeatureCategory.SECURITY,
        permission_slug="auth:manage_sso",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="key",
        ui_color="red"
    ),

    "security:session_revoke": Feature(
        id="security:session_revoke",
        name="Revoke User Sessions",
        description="Force logout users and revoke active sessions",
        category=FeatureCategory.SECURITY,
        permission_slug="auth:revoke_session",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="log-out",
        ui_color="red"
    ),

    "security:api_keys": Feature(
        id="security:api_keys",
        name="Manage API Keys",
        description="Create, rotate, or revoke API keys",
        category=FeatureCategory.SECURITY,
        permission_slug="api_key:manage",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="key-variant",
        ui_color="orange"
    ),

    # ========== AUDIT ==========
    "audit:export": Feature(
        id="audit:export",
        name="Export Audit Logs",
        description="Download audit logs and compliance reports",
        category=FeatureCategory.AUDIT,
        permission_slug="audit:export",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="ORG_ADMIN",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="download",
        ui_color="blue"
    ),

    # ========== GRANULAR RBAC PERMISSIONS (Read/Write/Delete Model) ==========

    # ----- Cloud Account & Credentials (High Risk) -----
    "feat-acc-view": Feature(
        id="feat-acc-view",
        name="View AWS Accounts",
        description="View linked AWS accounts, Account IDs, Regions, and connection status",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:view",
        requires_approval=False,  # Read-only, no approval needed
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="cloud",
        ui_color="blue"
    ),

    "feat-acc-edit": Feature(
        id="feat-acc-edit",
        name="Edit AWS Account",
        description="Modify account metadata, update IAM Role ARNs, or change regions",
        category=FeatureCategory.CLOUD,
        permission_slug="cloud:edit",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="edit",
        ui_color="orange"
    ),

    # ----- Compute Management (EC2 / ASG / EKS) -----
    "feat-comp-view": Feature(
        id="feat-comp-view",
        name="View Compute Resources",
        description="View instance lists, node health, fleet composition, and utilization metrics",
        category=FeatureCategory.COMPUTE,
        permission_slug="compute:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="server",
        ui_color="blue"
    ),

    # ----- Storage & S3 Management -----
    "feat-stor-view": Feature(
        id="feat-stor-view",
        name="View Storage Resources",
        description="View EBS volumes, S3 buckets, snapshots, and storage analytics",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="database",
        ui_color="blue"
    ),

    "feat-stor-s3-tier": Feature(
        id="feat-stor-s3-tier",
        name="Modify S3 Storage Tier",
        description="Manually move S3 data to Glacier, Deep Archive, or Intelligent Tiering",
        category=FeatureCategory.STORAGE,
        permission_slug="storage:s3_tier",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="archive",
        ui_color="purple"
    ),

    # ----- Automation & ML Settings -----
    "feat-auto-view": Feature(
        id="feat-auto-view",
        name="View Automation Settings",
        description="View current automation status, ML model versions, and configuration",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="automation:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="robot",
        ui_color="blue"
    ),

    # ----- Hibernation Scheduling -----
    "feat-hib-view": Feature(
        id="feat-hib-view",
        name="View Hibernation Schedules",
        description="View 168-hour cluster wake/sleep schedules and hibernation status",
        category=FeatureCategory.COMPUTE,
        permission_slug="hibernation:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="calendar",
        ui_color="blue"
    ),

    "feat-hib-edit": Feature(
        id="feat-hib-edit",
        name="Edit Hibernation Schedule",
        description="Modify existing hibernation schedule for a cluster",
        category=FeatureCategory.COMPUTE,
        permission_slug="hibernation:edit",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="calendar-edit",
        ui_color="orange"
    ),

    "feat-hib-delete": Feature(
        id="feat-hib-delete",
        name="Delete Hibernation Schedule",
        description="Remove a hibernation schedule entirely (cluster stays always-on)",
        category=FeatureCategory.COMPUTE,
        permission_slug="hibernation:delete",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="calendar-remove",
        ui_color="red"
    ),

    # ----- Tagging & Governance -----
    "feat-gov-view": Feature(
        id="feat-gov-view",
        name="View Governance Policies",
        description="View tagging compliance, active policies, and cost allocation rules",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="governance:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="shield-check",
        ui_color="blue"
    ),

    "feat-gov-tag-edit": Feature(
        id="feat-gov-tag-edit",
        name="Edit Resource Tags",
        description="Manually edit tags on live cloud resources via the UI",
        category=FeatureCategory.GOVERNANCE,
        permission_slug="governance:tag_edit",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="tag",
        ui_color="orange"
    ),

    # ----- Internal Team & User Management -----
    "feat-user-view": Feature(
        id="feat-user-view",
        name="View Team Members",
        description="View team members, their assigned roles, and access levels",
        category=FeatureCategory.TEAM,
        permission_slug="user:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="MEMBER",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="users",
        ui_color="blue"
    ),

    "feat-user-invite": Feature(
        id="feat-user-invite",
        name="Invite New Users",
        description="Generate and send invitation links to new team members",
        category=FeatureCategory.TEAM,
        permission_slug="user:invite",
        requires_approval=True,
        max_duration_hours=4,
        default_duration_hours=2,
        min_approver_role="TEAM_LEAD",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="user-plus",
        ui_color="green"
    ),

    "feat-user-role-edit": Feature(
        id="feat-user-role-edit",
        name="Change User Role",
        description="Promote or demote a user's role (e.g., Member to Team Lead)",
        category=FeatureCategory.TEAM,
        permission_slug="user:role_edit",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="user-cog",
        ui_color="orange"
    ),

    "feat-user-remove": Feature(
        id="feat-user-remove",
        name="Remove User",
        description="Revoke a user's access to the organization permanently",
        category=FeatureCategory.TEAM,
        permission_slug="user:remove",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="user-minus",
        ui_color="red"
    ),

    "feat-team-create": Feature(
        id="feat-team-create",
        name="Create Team",
        description="Create new sub-teams within the organization",
        category=FeatureCategory.TEAM,
        permission_slug="team:create",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="MEDIUM",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="users-plus",
        ui_color="green"
    ),

    "feat-team-delete": Feature(
        id="feat-team-delete",
        name="Delete Team",
        description="Remove a team and reassign its members",
        category=FeatureCategory.TEAM,
        permission_slug="team:delete",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=True,
        ui_icon="users-minus",
        ui_color="red"
    ),

    # ----- Audit & Security Logs -----
    "feat-audit-view": Feature(
        id="feat-audit-view",
        name="View Audit Logs",
        description="Access the Audit Log dashboard to see who did what and when",
        category=FeatureCategory.AUDIT,
        permission_slug="audit:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="file-text",
        ui_color="blue"
    ),

    "feat-ticket-bypass": Feature(
        id="feat-ticket-bypass",
        name="Bypass JIT Approval",
        description="Execute protected actions without waiting for approval (Admin emergency access)",
        category=FeatureCategory.SECURITY,
        permission_slug="security:bypass_approval",
        requires_approval=True,
        max_duration_hours=1,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="CRITICAL",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="alert-circle",
        ui_color="red"
    ),

    # ----- Billing & Finance -----
    "feat-bill-view": Feature(
        id="feat-bill-view",
        name="View Billing Information",
        description="View cost savings, invoices, payment methods, and spending analytics",
        category=FeatureCategory.BILLING,
        permission_slug="billing:view",
        requires_approval=False,
        max_duration_hours=24,
        default_duration_hours=24,
        min_approver_role="TEAM_LEAD",
        risk_level="LOW",
        requires_reason=False,
        supports_resource_scope=False,
        ui_icon="dollar-sign",
        ui_color="green"
    ),

    "feat-bill-edit": Feature(
        id="feat-bill-edit",
        name="Edit Billing Information",
        description="Update credit card info, billing addresses, or payment methods",
        category=FeatureCategory.BILLING,
        permission_slug="billing:edit",
        requires_approval=True,
        max_duration_hours=2,
        default_duration_hours=1,
        min_approver_role="ORG_ADMIN",
        risk_level="HIGH",
        requires_reason=True,
        supports_resource_scope=False,
        ui_icon="credit-card",
        ui_color="orange"
    ),
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_feature(feature_id: str) -> Optional[Feature]:
    """Get feature definition by ID"""
    return FEATURE_REGISTRY.get(feature_id)


def get_features_by_category(category: FeatureCategory) -> List[Feature]:
    """Get all features in a specific category"""
    return [f for f in FEATURE_REGISTRY.values() if f.category == category]


def get_features_requiring_approval() -> List[Feature]:
    """Get all features that require approval"""
    return [f for f in FEATURE_REGISTRY.values() if f.requires_approval]


def get_features_by_risk_level(risk_level: str) -> List[Feature]:
    """Get features by risk level (LOW, MEDIUM, HIGH, CRITICAL)"""
    return [f for f in FEATURE_REGISTRY.values() if f.risk_level == risk_level]


def list_all_feature_ids() -> List[str]:
    """Get list of all feature IDs"""
    return list(FEATURE_REGISTRY.keys())


def validate_feature_id(feature_id: str) -> bool:
    """Check if feature ID exists in registry"""
    return feature_id in FEATURE_REGISTRY


def get_feature_categories() -> List[str]:
    """Get list of all feature categories"""
    return [cat.value for cat in FeatureCategory]
