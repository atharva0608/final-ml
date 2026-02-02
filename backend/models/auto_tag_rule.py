"""
Auto-Tag Rule Model
Defines automated tagging rules based on resource patterns
"""
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from backend.models.base import Base, generate_uuid


class RunMode(str, Enum):
    """Auto-tag rule execution mode"""
    FUTURE_ONLY = "future_only"      # Only new resources
    RETROACTIVE = "retroactive"      # Apply to existing resources too


class ValueSourceType(str, Enum):
    """Dynamic tag value source types"""
    STATIC = "static"                # User-provided static text
    USER_EMAIL = "user_email"        # Current user's email
    USER_ID = "user_id"              # Current user's ID
    USER_NAME = "user_name"          # Current user's full name
    ORG_ID = "org_id"                # Organization ID
    ORG_NAME = "org_name"            # Organization name
    CREATION_DATE = "creation_date"  # Resource creation date (YYYY-MM-DD)
    CREATION_TIME = "creation_time"  # Resource creation timestamp (ISO)
    ENV_VARIABLE = "env_variable"    # Read from environment variable


class OverrideBehavior(str, Enum):
    """Behavior when tag already exists on resource"""
    SKIP_EXISTING = "skip_existing"  # Don't overwrite existing tags
    OVERWRITE = "overwrite"          # Replace existing tag values


class ResourceScope(str, Enum):
    """Resource scope for auto-tag rules"""
    ALL = "all"                      # All resource types
    COMPUTE_ONLY = "compute_only"    # EC2, ECS, Lambda
    STORAGE_ONLY = "storage_only"    # S3, EBS, EFS
    DATABASE_ONLY = "database_only"  # RDS, DynamoDB, ElastiCache
    NETWORK_ONLY = "network_only"    # VPC, ELB, ENI


class AutoTagRule(Base):
    """
    Auto-Tag Rule model for automated tag application.
    Applies tags automatically based on resource name patterns and types.
    """
    __tablename__ = "auto_tag_rules"

    # Primary Key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization Link
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Rule Definition
    name = Column(String(255), nullable=False)                  # e.g., "Tag Prod Resources"
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    
    # Matching Criteria
    resource_types = Column(JSON, default=list)                 # ["EC2", "RDS"]
    regions = Column(JSON, default=list)                        # ["us-east-1", "us-west-2"] or ["*"]
    name_pattern = Column(String(500), nullable=True)           # Regex: "^prod-.*" or wildcard: "prod-*"
    pattern_type = Column(String(20), default="wildcard")       # "wildcard" or "regex"
    
    # Tags to Apply
    tags_to_apply = Column(JSON, nullable=False)                # {"Environment": "Production", "Team": "Backend"}
    
    # Dynamic Tags Configuration (NEW: Smart Auto-Tag System)
    # Format: {"key": {"source": "user_email", "static_value": null, "env_var_name": null}}
    dynamic_tags = Column(JSON, nullable=True, default=dict)    # Tags with dynamic value sources
    
    # Enhanced Scope & Behavior (NEW)
    resource_scope = Column(String(50), default=ResourceScope.ALL.value)  # Broader scope filter
    override_behavior = Column(String(20), default=OverrideBehavior.SKIP_EXISTING.value)
    inject_system_tags = Column(Boolean, default=True)          # Auto-inject ManagedBy tag
    
    # Execution Settings
    run_mode = Column(String(20), default=RunMode.FUTURE_ONLY.value)
    priority = Column(Integer, default=100)                     # Lower = higher priority
    
    # Execution Tracking
    last_run_at = Column(DateTime, nullable=True)
    last_run_matched = Column(Integer, default=0)               # Resources matched in last run
    last_run_tagged = Column(Integer, default=0)                # Resources tagged in last run
    total_resources_tagged = Column(Integer, default=0)         # Lifetime count
    
    # Audit
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="auto_tag_rules")
    creator = relationship("User")
    
    def matches_resource_name(self, resource_name: str) -> bool:
        """Check if resource name matches this rule's pattern"""
        if not self.name_pattern:
            return True  # No pattern means match all
        
        import re
        if self.pattern_type == "regex":
            return bool(re.match(self.name_pattern, resource_name))
        else:  # wildcard
            # Convert wildcard to regex: prod-* becomes ^prod-.*$
            pattern = self.name_pattern.replace("*", ".*").replace("?", ".")
            if not pattern.startswith("^"):
                pattern = "^" + pattern
            if not pattern.endswith("$"):
                pattern = pattern + "$"
            return bool(re.match(pattern, resource_name))
    
    def matches_resource(self, resource_type: str, resource_name: str, region: str = None) -> bool:
        """Check if resource matches all criteria"""
        # Check type
        if self.resource_types and resource_type not in self.resource_types:
            return False
        
        # Check region
        if region and self.regions and "*" not in self.regions:
            if region not in self.regions:
                return False
        
        # Check name pattern
        if not self.matches_resource_name(resource_name):
            return False
        
        return True
    
    @property
    def tag_count(self) -> int:
        """Number of tags this rule applies"""
        return len(self.tags_to_apply) if self.tags_to_apply else 0
    
    def __repr__(self):
        return f"<AutoTagRule(name={self.name}, active={self.is_active}, tags={self.tag_count})>"
