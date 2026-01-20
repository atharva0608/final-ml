"""
Tag Policy Model
Defines tag governance policies with validation rules and enforcement levels
"""
from sqlalchemy import Column, String, DateTime, Boolean, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from backend.models.base import Base, generate_uuid


class EnforcementLevel(str, Enum):
    """Tag policy enforcement levels"""
    ADVISORY = "advisory"      # Warning only, no blocking
    REQUIRED = "required"      # Blocks cleanup/delete actions
    STRICT = "strict"          # Blocks all operations (future)


class ValueMode(str, Enum):
    """Tag value validation mode"""
    FREE_TEXT = "free_text"    # Any value allowed
    PREDEFINED = "predefined"  # Must match allowed_values list


class TagPolicy(Base):
    """
    Tag Policy model for governance and compliance.
    Defines requirements, validation rules, and enforcement for resource tags.
    """
    __tablename__ = "tag_policies"

    # Primary Key
    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    
    # Organization Link
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Policy Definition
    tag_key = Column(String(255), nullable=False, index=True)  # e.g., "Owner", "CostCenter"
    description = Column(Text, nullable=True)                   # Help text for users
    
    # Value Validation
    value_mode = Column(String(20), default=ValueMode.FREE_TEXT.value)
    allowed_values = Column(JSON, nullable=True)                # ["Prod", "Dev", "Staging"] for predefined
    validation_regex = Column(String(500), nullable=True)       # e.g., "^CC-\d{4}$" for format checking
    
    # Enforcement
    enforcement_level = Column(String(20), default=EnforcementLevel.ADVISORY.value, index=True)
    
    # Scope (which resources this applies to)
    resource_types = Column(JSON, default=list)                 # ["EC2", "S3", "RDS"] or ["*"] for all
    regions = Column(JSON, default=list)                        # ["us-east-1"] or ["*"] for all
    
    # Metadata
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="tag_policies")
    
    @property
    def is_required(self) -> bool:
        """Check if this policy blocks actions"""
        return self.enforcement_level in [EnforcementLevel.REQUIRED.value, EnforcementLevel.STRICT.value]
    
    @property
    def applies_to_all_resources(self) -> bool:
        """Check if policy applies to all resource types"""
        return not self.resource_types or "*" in self.resource_types
    
    def applies_to_resource(self, resource_type: str, region: str = None) -> bool:
        """Check if policy applies to specific resource"""
        # Check resource type
        if not self.applies_to_all_resources:
            if resource_type not in self.resource_types:
                return False
        
        # Check region if specified
        if region and self.regions and "*" not in self.regions:
            if region not in self.regions:
                return False
        
        return True
    
    def validate_value(self, value: str) -> tuple[bool, str]:
        """
        Validate a tag value against policy rules.
        Returns (is_valid, error_message)
        """
        if not value:
            return False, "Value cannot be empty"
        
        # Check predefined values
        if self.value_mode == ValueMode.PREDEFINED.value:
            if self.allowed_values and value not in self.allowed_values:
                return False, f"Value must be one of: {', '.join(self.allowed_values)}"
        
        # Check regex validation
        if self.validation_regex:
            import re
            if not re.match(self.validation_regex, value):
                return False, f"Value does not match required format: {self.validation_regex}"
        
        return True, ""
    
    def __repr__(self):
        return f"<TagPolicy(key={self.tag_key}, enforcement={self.enforcement_level})>"
