"""
Tag Policy Service
Manages tag policies, validation, and compliance tracking
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from backend.models.tag_policy import TagPolicy, EnforcementLevel, ValueMode
from backend.models.organization import Organization
from backend.schemas.tag_policy_schemas import (
    TagPolicyCreate,
    TagPolicyUpdate,
    TagPolicyResponse,
    ComplianceStats
)


class TagPolicyService:
    """Service for managing tag policies"""
    
    def __init__(self, db: Session, organization_id: str):
        self.db = db
        self.organization_id = organization_id
    
    def create_policy(self, policy_data: TagPolicyCreate) -> TagPolicy:
        """Create a new tag policy"""
        # Check for duplicate tag key
        existing = self.db.query(TagPolicy).filter(
            TagPolicy.organization_id == self.organization_id,
            TagPolicy.tag_key == policy_data.tag_key,
            TagPolicy.is_active == True
        ).first()
        
        if existing:
            raise ValueError(f"Active policy for tag '{policy_data.tag_key}' already exists")
        
        # Create policy
        policy = TagPolicy(
            organization_id=self.organization_id,
            tag_key=policy_data.tag_key,
            description=policy_data.description,
            value_mode=policy_data.value_mode,
            allowed_values=policy_data.allowed_values,
            validation_regex=policy_data.validation_regex,
            enforcement_level=policy_data.enforcement_level,
            resource_types=policy_data.resource_types,
            regions=policy_data.regions
        )
        
        self.db.add(policy)
        self.db.commit()
        self.db.refresh(policy)
        
        return policy
    
    def get_policy(self, policy_id: str) -> Optional[TagPolicy]:
        """Get a specific policy"""
        return self.db.query(TagPolicy).filter(
            TagPolicy.id == policy_id,
            TagPolicy.organization_id == self.organization_id
        ).first()
    
    def list_policies(self, active_only: bool = True) -> List[TagPolicy]:
        """List all policies for the organization"""
        query = self.db.query(TagPolicy).filter(
            TagPolicy.organization_id == self.organization_id
        )
        
        if active_only:
            query = query.filter(TagPolicy.is_active == True)
        
        return query.order_by(TagPolicy.tag_key).all()
    
    def update_policy(self, policy_id: str, update_data: TagPolicyUpdate) -> TagPolicy:
        """Update an existing policy"""
        policy = self.get_policy(policy_id)
        if not policy:
            raise ValueError(f"Policy {policy_id} not found")
        
        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(policy, field, value)
        
        policy.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(policy)
        
        return policy
    
    def delete_policy(self, policy_id: str, hard_delete: bool = False) -> bool:
        """Delete a policy (soft delete by default)"""
        policy = self.get_policy(policy_id)
        if not policy:
            return False
        
        if hard_delete:
            self.db.delete(policy)
        else:
            policy.is_active = False
            policy.updated_at = datetime.utcnow()
        
        self.db.commit()
        return True
    
    def get_required_policies(self, resource_type: str = None, region: str = None) -> List[TagPolicy]:
        """Get all required policies that apply to a resource"""
        policies = self.list_policies(active_only=True)
        
        required = []
        for policy in policies:
            if policy.enforcement_level in [EnforcementLevel.REQUIRED.value, EnforcementLevel.STRICT.value]:
                if policy.applies_to_resource(resource_type or "*", region):
                    required.append(policy)
        
        return required
    
    def validate_tags(self, tags: Dict[str, str], resource_type: str = None, region: str = None) -> Dict[str, Any]:
        """
        Validate tags against policies.
        Returns dict with validation results.
        """
        policies = self.list_policies(active_only=True)
        
        results = {
            "is_valid": True,
            "missing_required": [],
            "invalid_values": [],
            "warnings": []
        }
        
        for policy in policies:
            # Check if policy applies to this resource
            if not policy.applies_to_resource(resource_type or "*", region):
                continue
            
            tag_value = tags.get(policy.tag_key)
            
            # Check required tags
            if policy.is_required and not tag_value:
                results["missing_required"].append({
                    "tag_key": policy.tag_key,
                    "enforcement": policy.enforcement_level,
                    "description": policy.description
                })
                results["is_valid"] = False
                continue
            
            # Validate value if tag is present
            if tag_value:
                is_valid, error_msg = policy.validate_value(tag_value)
                if not is_valid:
                    results["invalid_values"].append({
                        "tag_key": policy.tag_key,
                        "value": tag_value,
                        "error": error_msg,
                        "enforcement": policy.enforcement_level
                    })
                    if policy.is_required:
                        results["is_valid"] = False
                    else:
                        results["warnings"].append(f"{policy.tag_key}: {error_msg}")
        
        return results
    
    def get_compliance_stats(self, scanned_resources: List[Dict[str, Any]]) -> ComplianceStats:
        """
        Calculate compliance statistics from scanned resources.
        
        Args:
            scanned_resources: List of dicts with {resource_id, resource_type, tags, region}
        """
        policies = self.list_policies(active_only=True)
        total = len(scanned_resources)
        
        if total == 0:
            return ComplianceStats(
                total_resources=0,
                compliant_resources=0,
                non_compliant_resources=0,
                compliance_percentage=100.0,
                by_policy=[],
                by_resource_type=[],
                missing_tags_summary={}
            )
        
        compliant_count = 0
        policy_stats = {}
        resource_type_stats = {}
        missing_tags_count = {}
        
        # Initialize policy stats
        for policy in policies:
            if policy.is_required:
                policy_stats[policy.tag_key] = {
                    "tag_key": policy.tag_key,
                    "total_applicable": 0,
                    "compliant": 0,
                    "non_compliant": 0,
                    "compliance_percentage": 0.0
                }
        
        # Analyze each resource
        for resource in scanned_resources:
            tags = resource.get("tags", {})
            resource_type = resource.get("resource_type", "Unknown")
            region = resource.get("region")
            
            # Track by resource type
            if resource_type not in resource_type_stats:
                resource_type_stats[resource_type] = {
                    "resource_type": resource_type,
                    "total": 0,
                    "compliant": 0,
                    "compliance_percentage": 0.0
                }
            resource_type_stats[resource_type]["total"] += 1
            
            # Check compliance
            validation = self.validate_tags(tags, resource_type, region)
            is_compliant = validation["is_valid"]
            
            if is_compliant:
                compliant_count += 1
                resource_type_stats[resource_type]["compliant"] += 1
            
            # Track missing tags
            for missing in validation["missing_required"]:
                tag_key = missing["tag_key"]
                missing_tags_count[tag_key] = missing_tags_count.get(tag_key, 0) + 1
                
                if tag_key in policy_stats:
                    policy_stats[tag_key]["non_compliant"] += 1
            
            # Track policy compliance
            for policy_key in policy_stats.keys():
                if tags.get(policy_key):
                    policy_stats[policy_key]["compliant"] += 1
                policy_stats[policy_key]["total_applicable"] += 1
        
        # Calculate percentages
        for stats in policy_stats.values():
            if stats["total_applicable"] > 0:
                stats["compliance_percentage"] = (stats["compliant"] / stats["total_applicable"]) * 100
        
        for stats in resource_type_stats.values():
            if stats["total"] > 0:
                stats["compliance_percentage"] = (stats["compliant"] / stats["total"]) * 100
        
        return ComplianceStats(
            total_resources=total,
            compliant_resources=compliant_count,
            non_compliant_resources=total - compliant_count,
            compliance_percentage=(compliant_count / total * 100) if total > 0 else 100.0,
            by_policy=list(policy_stats.values()),
            by_resource_type=list(resource_type_stats.values()),
            missing_tags_summary=missing_tags_count
        )
