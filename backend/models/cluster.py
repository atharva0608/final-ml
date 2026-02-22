
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Boolean, Integer, JSON, Float
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

    id = Column(String, primary_key=True)
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
    optimization_jobs = relationship("OptimizationJob", back_populates="cluster")
    agent_actions = relationship("AgentAction", back_populates="cluster")
    metrics = relationship("ClusterMetric", back_populates="cluster")
    pod_metrics = relationship("PodMetric", back_populates="cluster", cascade="all, delete-orphan")
    # hibernation_schedules relationship is defined via backref in HibernationSchedule model (many-to-many)
    api_keys = relationship("APIKey", back_populates="cluster")
