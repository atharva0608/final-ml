"""
SQLAlchemy Database Models - Production Lab Mode

Defines production database schema for:
- Multi-tenant AWS account management
- Cross-account access with STS AssumeRole
- EC2 instance tracking and configuration
- ML model registry and experiment logging
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from .connection import Base

# Import system logging models
from .system_logs import SystemLog, ComponentHealth, ComponentType, LogLevel, ComponentStatus


# ============================================================================
# User Management
# ============================================================================

class UserRole(str, enum.Enum):
    """User role enum"""
    SUPER_ADMIN = "super_admin"  # Full system access
    ADMIN = "admin"               # Admin access
    CLIENT = "client"             # Client with AWS account access
    USER = "user"                 # Regular user
    LAB = "lab"                   # Lab mode user


class User(Base):
    """User accounts with JWT authentication"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default=UserRole.USER.value, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


# ============================================================================
# AWS Account Management (Cross-Account Access)
# ============================================================================

class Account(Base):
    """AWS Account configuration for agentless cross-account access"""
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # Account identification
    # Expanded to 64 chars to support temporary "pending-xxx" IDs during onboarding
    # Real AWS Account IDs are exactly 12 digits, but temp IDs need ~20 chars
    account_id = Column(String(64), unique=True, nullable=False, index=True)
    account_name = Column(String(100), nullable=False)

    # Environment type
    environment_type = Column(String(20), default='LAB', nullable=False)  # PROD or LAB

    # Connection method: 'iam_role' (CloudFormation) or 'access_keys' (Direct credentials)
    connection_method = Column(String(20), default='iam_role', nullable=False)

    # Cross-account access (STS AssumeRole with ExternalID for confused deputy protection)
    # Nullable for access_keys connection method
    role_arn = Column(String(255), nullable=True)  # arn:aws:iam::123456789012:role/SpotOptimizerRole
    external_id = Column(String(255), nullable=True)  # Mandatory for security when using IAM role

    # Direct AWS credentials (encrypted, for access_keys connection method)
    aws_access_key_id = Column(String(255), nullable=True)  # Encrypted access key ID
    aws_secret_access_key = Column(String(512), nullable=True)  # Encrypted secret access key

    # AWS region
    region = Column(String(20), default='ap-south-1', nullable=False)

    # Onboarding and discovery status
    # Status flow: pending → connected (credentials verified) → active (discovery complete) | failed
    status = Column(String(20), default='pending', nullable=False, index=True)

    # Metadata for discovery tracking
    account_metadata = Column(JSON, nullable=True)  # Stores scan results, errors, etc.

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    instances = relationship("Instance", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Account(id={self.account_id}, name={self.account_name}, env={self.environment_type})>"


# ============================================================================
# EC2 Instance Tracking
# ============================================================================

class Instance(Base):
    """EC2 Instance configuration and tracking for Lab Mode"""
    __tablename__ = "instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    # Instance identification
    instance_id = Column(String(50), unique=True, nullable=False, index=True)  # EC2 instance ID
    instance_type = Column(String(20), nullable=False)
    availability_zone = Column(String(20), nullable=False)

    # Lab Mode configuration
    assigned_model_version = Column(String(50))  # e.g., "v2.1.0", NULL = use default
    pipeline_mode = Column(String(20), default='CLUSTER', nullable=False)  # CLUSTER or LINEAR
    is_shadow_mode = Column(Boolean, default=False)  # Read-only mode (no actual switches)

    # Security Enforcer fields
    auth_status = Column(String(20), default='AUTHORIZED')  # AUTHORIZED, UNAUTHORIZED, FLAGGED, TERMINATED

    # Kubernetes cluster membership
    cluster_membership = Column(JSONB)  # {"cluster_name": "prod-eks", "node_group": "workers", "role": "worker"}

    # Orchestrator Type (Prevent Cross-Contamination)
    # KUBERNETES = Production (Managed by EKS)
    # STANDALONE = Lab (Managed by our API directly)
    orchestrator_type = Column(String(20), default='KUBERNETES', nullable=False)  # Enforce schema distinction

    # Replica System (Zero-Downtime Safety Net)
    # When rebalance notice (2hr warning) received, launch safety net immediately
    is_replica = Column(Boolean, default=False, nullable=False)  # Distinguishes safety net from production
    replica_of_id = Column(String(64), nullable=True)  # Links replica to primary instance_id
    replica_expiry = Column(DateTime, nullable=True)  # 6hr timer for false alarm cleanup

    # Status and metadata
    is_active = Column(Boolean, default=True)
    last_evaluation = Column(DateTime)
    instance_metadata = Column(JSONB)  # Additional instance metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="instances")
    experiment_logs = relationship("ExperimentLog", back_populates="instance", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Instance(id={self.instance_id}, type={self.instance_type}, mode={self.pipeline_mode})>"


# ============================================================================
# ML Model Management - ModelRegistry removed, use MLModel instead (see below)
# ============================================================================
# Experiment Logging
# ============================================================================

class ExperimentLog(Base):
    """Lab Mode experiment logs for R&D analytics"""
    __tablename__ = "experiment_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True), ForeignKey('instances.id', ondelete='CASCADE'), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey('ml_models.id'))

    # Execution metadata
    pipeline_mode = Column(String(20))  # CLUSTER or LINEAR
    is_shadow_run = Column(Boolean, default=False)  # Was this a shadow mode run?

    # ML prediction data
    prediction_score = Column(Float)  # Crash probability
    decision = Column(String(50))  # SWITCH, HOLD, FAILED
    decision_reason = Column(Text)

    # Execution timing
    execution_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    execution_duration_ms = Column(Integer)

    # Result data (if SWITCH decision)
    candidates_evaluated = Column(Integer)
    selected_instance_type = Column(String(20))
    selected_availability_zone = Column(String(20))
    old_spot_price = Column(Float)
    new_spot_price = Column(Float)
    projected_hourly_savings = Column(Float)

    # Feature values (for debugging)
    features_used = Column(JSONB)  # Feature vector snapshot

    # Error tracking
    error_message = Column(Text)

    # Relationships
    model = relationship("MLModel", backref="experiment_logs")
    instance = relationship("Instance", back_populates="experiment_logs")

    def __repr__(self):
        return f"<ExperimentLog(instance={self.instance_id}, decision={self.decision}, score={self.prediction_score})>"


# ============================================================================
# ML Model Governance Pipeline
# ============================================================================

class ModelStatus(str, enum.Enum):
    """Model lifecycle statuses"""
    CANDIDATE = "candidate"      # Uploaded, waiting for acceptance
    TESTING = "testing"          # Accepted, available in Lab Dropdowns
    GRADUATED = "graduated"      # Passed Lab, waiting for Prod Enable
    ENABLED = "enabled"          # Available for Production Dropdown
    ARCHIVED = "archived"        # Deprecated/removed from use


class MLModel(Base):
    """
    ML Model Governance and Lifecycle Management

    Tracks .pkl model files through the promotion pipeline:
    1. CANDIDATE: Detected in ml-model/ folder, available for Lab testing
    2. GRADUATED: Promoted by user, available in Production dropdown
    3. ARCHIVED: Deprecated or removed

    Only ONE model can be is_active_prod=True at a time (enforced in logic layer)
    """
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # File identification
    name = Column(String(255), unique=True, nullable=False, index=True)  # e.g., "v2_aggressive_risk.pkl"
    file_path = Column(String(512), nullable=False)  # Absolute path to .pkl file
    file_hash = Column(String(64))  # SHA256 hash for integrity validation

    # Lifecycle management
    status = Column(String(20), default=ModelStatus.CANDIDATE.value, nullable=False, index=True)
    is_active_prod = Column(Boolean, default=False, nullable=False, index=True)  # Only one can be True

    # Metadata
    description = Column(Text)  # User-provided description
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))  # Who added this model

    # Timing
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    graduated_at = Column(DateTime)  # When was it promoted to production-ready?
    deployed_at = Column(DateTime)   # When was it set as active production model?
    archived_at = Column(DateTime)   # When was it deprecated?

    # Performance tracking (populated from experiment_logs)
    total_predictions = Column(Integer, default=0)
    avg_prediction_score = Column(Float)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<MLModel(id={self.id}, name={self.name}, status={self.status}, active_prod={self.is_active_prod})>"


# ============================================================================
# Waste Management (Financial Hygiene)
# ============================================================================

class WasteResourceType(str, enum.Enum):
    """Types of wasted AWS resources"""
    ELASTIC_IP = "elastic_ip"
    EBS_VOLUME = "ebs_volume"
    EBS_SNAPSHOT = "ebs_snapshot"
    AMI = "ami"


class WasteResource(Base):
    """Tracking unused/orphaned AWS resources for automated cleanup"""
    __tablename__ = "waste_resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)

    # Resource identification
    resource_type = Column(String(20), nullable=False, index=True)  # elastic_ip, ebs_volume, ebs_snapshot, ami
    resource_id = Column(String(100), nullable=False, index=True)  # e.g., "eipalloc-abc123", "vol-xyz789"
    region = Column(String(20), nullable=False)

    # Cost data
    monthly_cost = Column(Float, default=0.0)  # Estimated monthly waste cost
    currency = Column(String(3), default='USD')

    # Detection metadata
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    days_unused = Column(Integer, default=0)  # How long has it been unused?

    # Status tracking
    status = Column(String(20), default='DETECTED', nullable=False)  # DETECTED, FLAGGED, SCHEDULED_DELETE, DELETED
    scheduled_deletion_date = Column(DateTime)  # Grace period before auto-delete
    deleted_at = Column(DateTime)

    # Metadata
    resource_metadata = Column(JSONB)  # Additional resource info (tags, attachments, etc.)
    reason = Column(Text)  # Why is this considered waste?

    # Relationships
    account = relationship("Account")

    def __repr__(self):
        return f"<WasteResource(type={self.resource_type}, id={self.resource_id}, cost=${self.monthly_cost})>"


# ============================================================================
# Global Risk Contagion (Hive Intelligence)
# ============================================================================

class SpotPoolRisk(Base):
    """Global spot pool risk tracking (hive intelligence across all customers)"""
    __tablename__ = "spot_pool_risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Spot pool identification (unique combination)
    region = Column(String(20), nullable=False, index=True)
    availability_zone = Column(String(20), nullable=False, index=True)
    instance_type = Column(String(20), nullable=False, index=True)

    # Risk tracking
    is_poisoned = Column(Boolean, default=False, nullable=False, index=True)  # Is this pool blocked?
    interruption_count = Column(Integer, default=0)  # Total interruptions observed
    last_interruption = Column(DateTime, index=True)  # Most recent interruption
    poisoned_at = Column(DateTime)  # When was it marked as poisoned?
    poison_expires_at = Column(DateTime)  # 15-day cooldown

    # Metadata
    triggering_customer_id = Column(UUID(as_uuid=True))  # Which customer experienced the interruption?
    pool_metadata = Column(JSONB)  # Additional context (rebalance event, price spike, etc.)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SpotPoolRisk(pool={self.region}/{self.availability_zone}/{self.instance_type}, poisoned={self.is_poisoned})>"


# ============================================================================
# Approval Workflow
# ============================================================================

class ApprovalStatus(str, enum.Enum):
    """Approval request statuses"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest(Base):
    """Manual approval gates for high-risk production actions"""
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id = Column(UUID(as_uuid=True), ForeignKey('instances.id', ondelete='CASCADE'), nullable=False, index=True)
    requester_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    approver_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))

    # Request details
    action_type = Column(String(50), nullable=False)  # "SWITCH_INSTANCE", "TERMINATE_ROGUE", "DELETE_WASTE"
    action_description = Column(Text)  # Human-readable description of what will happen
    risk_level = Column(String(20), default='MEDIUM')  # LOW, MEDIUM, HIGH, CRITICAL

    # Decision metadata (what will be executed if approved)
    action_payload = Column(JSONB, nullable=False)  # Contains all details needed to execute action

    # Status tracking
    status = Column(String(20), default=ApprovalStatus.PENDING.value, nullable=False, index=True)
    rejection_reason = Column(Text)

    # Timing
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)  # Auto-reject if not approved in time
    decided_at = Column(DateTime)  # When was approve/reject decision made?
    executed_at = Column(DateTime)  # When was the action actually executed (if approved)?

    # Relationships
    instance = relationship("Instance")
    requester = relationship("User", foreign_keys=[requester_id])
    approver = relationship("User", foreign_keys=[approver_id])

    def __repr__(self):
        return f"<ApprovalRequest(id={self.id}, action={self.action_type}, status={self.status})>"


# ============================================================================
# Global Risk Intelligence (Hive Mind)
# ============================================================================

class GlobalRiskEvent(Base):
    """
    Append-only log of spot disruptions across ALL clients

    Business Logic: One client's disruption blocks that pool globally for 15 days
    Why: AWS spot pool recovery time is ~15 days (empirical data)
    Impact: Prevents cascading failures, reduces emergency switches by 60%

    Never delete - used for ML training and historical analysis
    """
    __tablename__ = "global_risk_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Spot pool identification (composite unique key)
    pool_id = Column(String(128), nullable=False, index=True)  # Format: 'us-east-1a:c5.large'
    region = Column(String(20), nullable=False, index=True)
    availability_zone = Column(String(20), nullable=False, index=True)
    instance_type = Column(String(20), nullable=False, index=True)

    # Event classification
    event_type = Column(String(30), nullable=False, index=True)  # 'rebalance_notice', 'termination_notice'

    # Timing (15-day poisoning window)
    reported_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)  # reported_at + 15 days

    # Attribution and metadata
    source_client_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)  # Which client reported this
    event_metadata = Column(JSONB)  # Additional context (price spike, region-wide issue, etc.)

    def __repr__(self):
        return f"<GlobalRiskEvent(pool={self.pool_id}, type={self.event_type}, expires={self.expires_at})>"


class DowntimeLog(Base):
    """
    SLA Accountability - Tracks every second WE caused downtime (not AWS)

    Business Logic:
    - Distinguishes system fault (our responsibility) vs AWS fault (not our responsibility)
    - Proves SLA compliance (< 60s monthly downtime target)
    - Provides transparency for billing and trust

    Only logs downtime caused by:
    - Emergency switches (no replica ready)
    - System failures (optimizer crashed, worker died)

    Does NOT log AWS-caused downtime (spot terminations without our tool)
    """
    __tablename__ = "downtime_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Attribution
    client_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    instance_id = Column(String(64), nullable=False, index=True)  # EC2 instance ID

    # Downtime window
    start_time = Column(DateTime, nullable=False, index=True)  # Service lost
    end_time = Column(DateTime, nullable=False)  # Service restored
    duration_seconds = Column(Integer, nullable=False)  # end_time - start_time

    # Root cause analysis
    cause = Column(String(64), nullable=False, index=True)  # 'emergency_switch', 'no_replica', 'optimizer_failure', 'worker_crash'
    cause_details = Column(Text)  # Detailed explanation for post-mortem

    # Context
    downtime_metadata = Column(JSONB)  # Additional data (logs, metrics, AWS events)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    client = relationship("User", foreign_keys=[client_id])

    def __repr__(self):
        return f"<DowntimeLog(instance={self.instance_id}, duration={self.duration_seconds}s, cause={self.cause})>"


# ============================================================================
# Kubernetes Cluster Management (CAST AI Features)
# ============================================================================

class ClusterStatus(str, enum.Enum):
    """Kubernetes cluster connection states"""
    PENDING = "PENDING"                          # Cluster created, agent not verified
    CONNECTING = "CONNECTING"                    # Agent install in progress
    CONNECTED = "CONNECTED"                      # Agent fully operational
    READ_ONLY = "READ_ONLY"                      # Metrics only, optimization disabled
    PARTIALLY_CONNECTED = "PARTIALLY_CONNECTED"  # Missing permissions
    DISCONNECTED = "DISCONNECTED"                # Agent unreachable
    ERROR = "ERROR"                              # Terminal failure
    REMOVING = "REMOVING"                        # Deletion in progress
    REMOVED = "REMOVED"                          # Fully deleted


class Cluster(Base):
    """
    Kubernetes cluster tracking and management

    Supports: AWS EKS, GCP GKE, Azure AKS
    """
    __tablename__ = "clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=True, index=True)

    # Cluster identification
    name = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # 'AWS EKS', 'GCP GKE', 'Azure AKS'
    region = Column(String(50), nullable=False)
    version = Column(String(20))  # Kubernetes version (e.g., '1.28')

    # Connection status
    status = Column(String(30), default=ClusterStatus.PENDING.value, nullable=False, index=True)

    # Agent configuration
    agent_token = Column(String(255))  # Authentication token for cluster agent
    agent_last_heartbeat = Column(DateTime)  # Last agent check-in

    # Cluster metrics
    total_nodes = Column(Integer, default=0)
    spot_nodes = Column(Integer, default=0)
    on_demand_nodes = Column(Integer, default=0)
    fallback_nodes = Column(Integer, default=0)
    platform_managed_nodes = Column(Integer, default=0)
    cloud_managed_nodes = Column(Integer, default=0)

    # Resource totals
    total_cpu = Column(Integer, default=0)  # vCPU cores
    total_memory = Column(Integer, default=0)  # GB
    total_storage = Column(Integer, default=0)  # GB

    # Workload counts
    total_pods = Column(Integer, default=0)
    scheduled_pods = Column(Integer, default=0)
    pending_pods = Column(Integer, default=0)

    # Cost tracking
    monthly_cost = Column(Float, default=0.0)

    # Metadata
    cluster_metadata = Column(JSONB)  # Additional cluster info

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    connected_at = Column(DateTime)  # When agent first connected
    disconnected_at = Column(DateTime)  # When cluster was disconnected

    # Relationships
    user = relationship("User")
    account = relationship("Account")
    optimization_policies = relationship("OptimizationPolicy", back_populates="cluster", cascade="all, delete-orphan")
    hibernation_schedules = relationship("HibernationSchedule", back_populates="cluster", cascade="all, delete-orphan")
    autoscaler_policies = relationship("AutoscalerPolicy", back_populates="cluster", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Cluster(id={self.id}, name={self.name}, status={self.status}, provider={self.provider})>"


class OptimizationPolicy(Base):
    """
    Cluster optimization policies and settings
    """
    __tablename__ = "optimization_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True)

    # Workload Rightsizing
    rightsizing_enabled = Column(Boolean, default=False)
    current_efficiency = Column(Float)  # Percentage
    waste_cpu = Column(Float)  # CPU cores wasted
    waste_memory = Column(Float)  # GB wasted
    savings_from_rightsizing = Column(Float)  # USD/month

    # Spot Instances
    spot_instances_enabled = Column(Boolean, default=False)
    spot_mode = Column(String(20))  # 'all' or 'friendly_only'
    spot_workloads_count = Column(Integer, default=0)
    additional_actions_needed = Column(Integer, default=0)
    spot_savings_percentage = Column(Float)  # Percentage

    # ARM Support
    arm_enabled = Column(Boolean, default=False)
    arm_cpu_percentage = Column(Integer, default=0)  # 0-100
    arm_savings_percentage = Column(Float)  # Percentage

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="optimization_policies")

    def __repr__(self):
        return f"<OptimizationPolicy(cluster_id={self.cluster_id}, rightsizing={self.rightsizing_enabled}, spot={self.spot_instances_enabled})>"


class HibernationSchedule(Base):
    """
    Cluster hibernation schedules for cost savings
    """
    __tablename__ = "hibernation_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True)

    # Schedule configuration
    name = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True)

    # Active periods (when cluster runs)
    # Format: [{"day": "Monday", "start_time": "08:00", "end_time": "18:00"}, ...]
    active_periods = Column(JSONB)

    # Timezone
    timezone = Column(String(50), default='UTC')

    # Next action
    next_action = Column(String(20))  # 'hibernate' or 'resume'
    next_action_time = Column(DateTime)

    # Estimated savings
    estimated_monthly_savings = Column(Float)  # USD/month

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="hibernation_schedules")

    def __repr__(self):
        return f"<HibernationSchedule(id={self.id}, name={self.name}, enabled={self.enabled})>"


class AutoscalerPolicy(Base):
    """
    Cluster autoscaler policies
    """
    __tablename__ = "autoscaler_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True)

    # Policy type
    policy_name = Column(String(100), nullable=False)  # 'Unscheduled Pods', 'Node Deletion', 'Evictor', 'Scoped Mode'
    enabled = Column(Boolean, default=False)

    # Unscheduled Pods Policy
    add_nodes_for_unschedulable_pods = Column(Boolean, default=True)

    # Node Deletion Policy
    remove_idle_nodes = Column(Boolean, default=False)
    node_ttl_seconds = Column(Integer)  # Time to live for idle nodes

    # Evictor Mode
    compact_pods = Column(Boolean, default=False)
    aggressive_mode = Column(Boolean, default=False)  # Include single-replica apps

    # Scoped Mode
    scoped_to_platform_nodes = Column(Boolean, default=False)

    # Policy metadata
    policy_metadata = Column(JSONB)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="autoscaler_policies")

    def __repr__(self):
        return f"<AutoscalerPolicy(cluster_id={self.cluster_id}, name={self.policy_name}, enabled={self.enabled})>"


class AuditLog(Base):
    """
    Audit log for tracking user and system actions

    90-day retention policy
    """
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, index=True)  # Null for system actions
    cluster_id = Column(UUID(as_uuid=True), ForeignKey('clusters.id', ondelete='SET NULL'), nullable=True, index=True)

    # Action details
    operation = Column(String(100), nullable=False, index=True)  # 'disconnect', 'reconnect', 'template_create', etc.
    initiated_by = Column(String(100))  # User email or "system"

    # Event details
    details = Column(JSONB)  # Full event details, parameters, before/after values

    # Audit metadata
    ip_address = Column(String(50))
    user_agent = Column(String(255))

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User")
    cluster = relationship("Cluster")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, operation={self.operation}, initiated_by={self.initiated_by}, timestamp={self.timestamp})>"
