
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Boolean, Integer, JSON, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.models.base import Base

class ClusterStatus(enum.Enum):
    PENDING = "PENDING"       # Awaiting agent connection verification
    DISCOVERED = "DISCOVERED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"
    TERMINATED = "TERMINATED"
    DISCONNECTED = "DISCONNECTED"

class ClusterType(enum.Enum):
    EKS = "EKS"
    ECS = "ECS"
    GKE = "GKE" # Provision for future
    AKS = "AKS" # Provision for future

class KarpenterMode(enum.Enum):
    DRY_RUN = "dry_run"     # Insights only — no EC2 changes
    AUTO = "auto"            # Full autonomous management

class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String(36), primary_key=True)
    name = Column(String, index=True)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    arn = Column(String, unique=True, index=True)
    region = Column(String)
    cluster_type = Column(Enum(ClusterType), default=ClusterType.EKS)
    version = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)
    ca_data = Column(Text, nullable=True)  # Base64 encoded CA certificate for K8s API auth
    
    status = Column(Enum(ClusterStatus), default=ClusterStatus.DISCOVERED)
    
    # Connection/Agent details
    agent_installed = Column(String, default="N") # 'Y' or 'N'
    is_agentless = Column(String, default="Y") # 'Y' or 'N'
    api_key = Column(String, nullable=True)  # Auto-generated for agent auth
    
    # AWS Auth
    aws_role_arn = Column(String, nullable=True)
    aws_external_id = Column(String, nullable=True)
    
    # Health
    last_heartbeat = Column(DateTime, nullable=True)
    
    # Cost Insights
    monthly_cost = Column(Integer, default=0) # Stored in USD (or cents if needed, but float/int for display)
    estimated_savings = Column(Integer, default=0)
    last_cost_update = Column(DateTime, nullable=True)

    # "Teaser" / Shallow Scan Data (Phase 2 Enterprise)
    potential_savings_monthly = Column(Float, default=0.0)  # Savings IF we switch ON_DEMAND to SPOT
    realized_savings_monthly = Column(Float, default=0.0)   # Savings we're ALREADY getting from SPOT instances
    on_demand_node_count = Column(Integer, default=0)
    # spot_node_count (reuse spot_count below)
    last_assessed = Column(DateTime, nullable=True)
    inventory_summary = Column(JSON, default={}) # {"total": 20, "on_demand": 10, "spot": 10}

    # Node metrics (updated by discovery/agent)
    node_count = Column(Integer, default=0)
    spot_count = Column(Integer, default=0)
    cpu_total = Column(Integer, default=0)
    mem_total = Column(Integer, default=0)  # In GiB
    cpu_usage_pct = Column(Float, default=0.0)  # CPU usage percentage
    mem_usage_pct = Column(Float, default=0.0)  # Memory usage percentage

    tags = Column(JSON, default={})

    # Karpenter operating mode: null = not installed, dry_run = insights only, auto = full management
    karpenter_mode = Column(Enum(KarpenterMode), nullable=True, default=None)

    # AtharvaAI v3 Decision Engine settings
    optimization_mode = Column(
        String(20), nullable=False, default="BALANCED", server_default="BALANCED"
    )  # "COST_FIRST", "BALANCED", "NO_DOWNTIME_FIRST"

    model_version = Column(
        String(10), nullable=True, default="6"
    )  # Pinned model version for this cluster

    workload_type = Column(
        String(10), nullable=False, default="STATELESS", server_default="STATELESS"
    )  # INFORMATIONAL CACHE ONLY — real source of truth is WorkloadInspector.
    # This column stores the LAST classification for audit/display.
    # Decision Engine uses WorkloadInspector.get_cached_classification() at runtime.
    # ⚠️ Do NOT use this column for safety decisions. Use live classification.

    # Auto-rebalancing setting
    auto_rebalance_enabled = Column(Boolean, default=False)  # Enable automatic on-demand → spot migration
    rightsizing_enabled = Column(Boolean, default=False)     # Enable right-sizing feature

    # Hibernation state tracking
    is_hibernating = Column(Boolean, default=False)  # True when cluster is currently hibernated
    hibernation_state = Column(JSON, nullable=True)  # Saved state (replica counts, etc.) for wake operation
    hibernation_lock = Column(String(255), nullable=True)  # UUID of worker holding hibernation lock
    hibernation_lock_acquired_at = Column(DateTime, nullable=True)  # When lock was acquired

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="clusters")
    instances = relationship("Instance", back_populates="cluster")
    cluster_policy = relationship("ClusterPolicy", back_populates="cluster", uselist=False)
    template_mappings = relationship("ClusterTemplateMapping", back_populates="cluster", cascade="all, delete-orphan")
    optimization_jobs = relationship("OptimizationJob", back_populates="cluster")
    agent_actions = relationship("AgentAction", back_populates="cluster", cascade="all, delete-orphan", passive_deletes=True)
    metrics = relationship("ClusterMetric", back_populates="cluster")
    pod_metrics = relationship("PodMetric", back_populates="cluster", cascade="all, delete-orphan")
    # hibernation_schedules relationship is defined via backref in HibernationSchedule model (many-to-many)
    api_keys = relationship("APIKey", back_populates="cluster")
    optimization_state = relationship("OptimizerState", back_populates="cluster", uselist=False, cascade="all, delete-orphan")
    rightsizing_proposals = relationship("RightsizingProposal", back_populates="cluster", cascade="all, delete-orphan")

    optimization_settings = relationship("ClusterOptimizationSettings", back_populates="cluster", uselist=False, cascade="all, delete-orphan")
    optimization_strategy_profile = relationship("OptimizationStrategy", back_populates="cluster", uselist=False, cascade="all, delete-orphan")
    stateless_rules = relationship("StatelessRuntimeRules", back_populates="cluster", uselist=False, cascade="all, delete-orphan")
    stateful_rules = relationship("StatefulRules", back_populates="cluster", uselist=False, cascade="all, delete-orphan")


class ClusterOptimizationSettings(Base):
    __tablename__ = "cluster_optimization_settings"
    cluster_id = Column(String, ForeignKey("clusters.id"), primary_key=True)
    auto_rebalance_enabled = Column(Boolean, default=False)
    auto_rightsizing_enabled = Column(Boolean, default=False)
    auto_stateful_rightsizing_enabled = Column(Boolean, default=False)
    cooldown_override_minutes = Column(Integer, nullable=True)
    spot_join_timeout_minutes = Column(Integer, nullable=True)  # How long to wait for new spot node to join (default 30 min)
    conservative_mode_enabled = Column(Boolean, default=True)
    manual_approval_required = Column(Boolean, default=False)
    target_spot_exposure_pct = Column(Integer, default=100)
    
    # New platform v3.5 properties
    maintain_standby = Column(Boolean, default=False)
    diversify_pools = Column(Boolean, default=False)
    max_family_diversification_cap_pct = Column(Integer, default=40)
    failure_cooldown_minutes = Column(Integer, default=30)
    
    # Billing model preference for right-sizing: "spot" or "on_demand".
    # When both auto_rebalance_enabled AND auto_rightsizing_enabled are True
    # (synergy mode), API force-locks this to "spot".
    optimization_target = Column(String(20), default="spot")

    # Instance-Aware Rightsizing: when True, only generate recommendations
    # if a better spot pool exists (double gate: risk < current AND price < OD).
    instance_aware_rightsizing = Column(Boolean, default=False)

    # Task 4.8: Max instance types to attempt during spot launch cascade.
    # Replaces hardcoded [:6] slice in auto_rebalancer._launch_spot_instance_direct().
    max_instance_type_attempts = Column(Integer, default=6, nullable=False)

    # Dynamic autoscaler settings (mini-CA built into the rebalancer)
    # min_node_count  — hard floor: watchdog never scales below this value.
    #                   Default 1 ensures at least 1 node is always running.
    # scale_down_threshold_pct — avg CPU+mem utilization below which a node is
    #                   considered idle. Idle nodes are removed one-at-a-time
    #                   (respecting min_node_count). Default 20%.
    # scale_down_stabilization_minutes — how long avg util must be below threshold
    #                   before a scale-down fires. Prevents thrashing. Default 15 min.
    min_node_count = Column(Integer, default=1, nullable=False)
    scale_down_threshold_pct = Column(Integer, default=20, nullable=False)
    scale_down_stabilization_minutes = Column(Integer, default=15, nullable=False)

    # ASCP built-in auto-scaler (optional — off by default).
    # When True, auto_scaler.py task monitors pending pods and adjusts ASG
    # desired capacity, using a per-cluster Redis target as the source of truth.
    # When False (default), the platform never changes ASG desired automatically;
    # any external scaler (CA / Karpenter) remains in full control.
    enable_ascp_auto_scaler = Column(Boolean, default=False, nullable=False)

    # Per-cluster rebalance check interval (seconds). Default 15 s matches the
    # Celery beat schedule. Increase to reduce check frequency for stable clusters.
    check_interval_seconds = Column(Integer, default=15, nullable=False)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    cluster = relationship("Cluster", back_populates="optimization_settings")

class OptimizationStrategy(Base):
    __tablename__ = "optimization_strategy"
    cluster_id = Column(String, ForeignKey("clusters.id"), primary_key=True)
    strategy_type = Column(String, default="BALANCED") # COST_FIRST, BALANCED, NO_DOWNTIME_FIRST, CUSTOM
    risk_ceiling_percent = Column(Integer, default=25)
    min_savings_percent = Column(Integer, default=15)
    volatility_tolerance_percent = Column(Integer, default=20)
    migration_penalty_multiplier = Column(Float, default=1.5)
    diversity_strictness_level = Column(String, default="Medium")
    risk_savings_tradeoff_pct = Column(Integer, default=20)  # Accept pool up to X% more expensive if safer
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    cluster = relationship("Cluster", back_populates="optimization_strategy_profile")

class StatelessRuntimeRules(Base):
    __tablename__ = "stateless_runtime_rules"
    cluster_id = Column(String, ForeignKey("clusters.id"), primary_key=True)
    instance_diversification_enabled = Column(Boolean, default=True)
    respect_pdb_enabled = Column(Boolean, default=True)
    prewarm_minutes = Column(Integer, default=0)
    substitute_strategy = Column(String, default="PREWARMED") # PREWARMED, ON_DEMAND
    max_rebalances_per_24h = Column(Integer, default=5)
    resize_cooldown_minutes = Column(Integer, default=120)
    resize_headroom_multiplier = Column(Float, default=1.2)
    volatility_safety_multiplier = Column(Float, default=1.35)
    fresh_cluster_stabilization_minutes = Column(Integer, default=1440)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    cluster = relationship("Cluster", back_populates="stateless_rules")

class StatefulRules(Base):
    __tablename__ = "stateful_rules"
    cluster_id = Column(String, ForeignKey("clusters.id"), primary_key=True)
    manual_resize_allowed = Column(Boolean, default=True)
    show_ondemand_only = Column(Boolean, default=True)
    require_approval = Column(Boolean, default=True)
    block_spot_for_stateful = Column(Boolean, default=True)
    max_downscale_percent = Column(Integer, default=25)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cluster = relationship("Cluster", back_populates="stateful_rules")


class NodeAlternativeCache(Base):
    """
    Per-node alternative pool list with coverage status.
    Populated by reconciliation_worker every 5 min.
    Primary storage: Redis cluster_coverage:{cluster_id} (TTL 300s).
    This table provides historical record.
    """
    __tablename__ = 'node_alternative_cache'
    __table_args__ = (
        Index('idx_nac_cluster_node', 'cluster_id', 'node_name'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id = Column(String(36), nullable=True, index=True)          # Instance.id (if available)
    node_name = Column(String(255), nullable=False)                  # K8s node name / instance_id
    instance_type = Column(String(50), nullable=True)
    resource_profile = Column(JSONB, nullable=True)                  # NodeProfile dict
    alternative_pools = Column(JSONB, nullable=True)                 # List of ranked pool dicts
    alternative_count = Column(Integer, nullable=True, default=0)
    best_pool = Column(String(150), nullable=True)                   # "t3a.medium:ap-south-1a"
    best_saving_pct = Column(Float, nullable=True)
    coverage_status = Column(String(20), nullable=True)              # COVERED/AT_RISK/STRANDED/IMMOVABLE
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ClusterBaseline(Base):
    """
    Cluster-level baseline snapshot.
    Stores primary node type, region, and cost baseline for delta calculations.
    """
    __tablename__ = 'cluster_baselines'

    cluster_id = Column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), primary_key=True)
    primary_node_type = Column(String(50), nullable=True)
    primary_az = Column(String(50), nullable=True)
    baseline_monthly_cost = Column(Float, nullable=True)
    baseline_spot_count = Column(Integer, nullable=True)
    baseline_od_count = Column(Integer, nullable=True)
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
