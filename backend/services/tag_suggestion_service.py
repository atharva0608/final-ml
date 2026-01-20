"""
Tag Suggestion Service
Provides intelligent tag suggestions based on patterns and common practices
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import re

from backend.models.organization import Organization
from backend.schemas.tag_management_schemas import TagSuggestion


class TagSuggestionService:
    """Service for generating tag suggestions"""
    
    def __init__(self, db: Session, organization_id: str):
        self.db = db
        self.organization_id = organization_id
    
    def suggest_tags_for_resource(
        self,
        resource_name: str,
        resource_type: str,
        region: str,
        account_id: str,
        existing_tags: Dict[str, str] = None
    ) -> List[TagSuggestion]:
        """Generate tag suggestions for a resource"""
        suggestions = []
        existing_tags = existing_tags or {}
        
        # Environment detection from name
        env_suggestion = self._detect_environment(resource_name)
        if env_suggestion and "Environment" not in existing_tags:
            suggestions.append(env_suggestion)
        
        # Owner suggestion from account
        owner_suggestion = self._suggest_owner(account_id)
        if owner_suggestion and "Owner" not in existing_tags:
            suggestions.append(owner_suggestion)
        
        # Application detection from name
        app_suggestion = self._detect_application(resource_name)
        if app_suggestion and "Application" not in existing_tags:
            suggestions.append(app_suggestion)
        
        # Cost Center suggestion
        cc_suggestion = self._suggest_cost_center(resource_type)
        if cc_suggestion and "CostCenter" not in existing_tags:
            suggestions.append(cc_suggestion)
        
        return suggestions
    
    def _detect_environment(self, resource_name: str) -> Optional[TagSuggestion]:
        """Detect environment from resource name"""
        name_lower = resource_name.lower()
        
        patterns = {
            "production": ["prod", "production", "prd"],
            "staging": ["staging", "stg", "stage"],
            "development": ["dev", "develop", "development"],
            "testing": ["test", "qa", "uat"],
            "demo": ["demo", "sandbox"]
        }
        
        for env, keywords in patterns.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return TagSuggestion(
                        key="Environment",
                        value=env.capitalize(),
                        confidence=0.85,
                        reason=f"Detected '{keyword}' in resource name",
                        source="pattern"
                    )
        
        return None
    
    def _suggest_owner(self, account_id: str) -> Optional[TagSuggestion]:
        """Suggest owner based on account"""
        # In a real implementation, this could query account metadata
        # For now, return a generic suggestion
        return TagSuggestion(
            key="Owner",
            value="team-infrastructure",
            confidence=0.60,
            reason="Default owner for this AWS account",
            source="account"
        )
    
    def _detect_application(self, resource_name: str) -> Optional[TagSuggestion]:
        """Detect application name from resource naming pattern"""
        # Extract application name from patterns like: app-backend-prod-1
        match = re.match(r'^([a-z\-]+)-(?:backend|frontend|api|db|cache)', resource_name, re.I)
        if match:
            app_name = match.group(1)
            return TagSuggestion(
                key="Application",
                value=app_name,
                confidence=0.75,
                reason=f"Extracted from resource naming pattern",
                source="pattern"
            )
        
        return None
    
    def _suggest_cost_center(self, resource_type: str) -> Optional[TagSuggestion]:
        """Suggest cost center based on resource type"""
        # This would ideally come from organizational data
        cost_center_map = {
            "RDS": "CC-DATABASE",
            "S3": "CC-STORAGE",
            "EC2": "CC-COMPUTE"
        }
        
        cc = cost_center_map.get(resource_type)
        if cc:
            return TagSuggestion(
                key="CostCenter",
                value=cc,
                confidence=0.50,
                reason=f"Common cost center for {resource_type} resources",
                source="common"
            )
        
        return None
