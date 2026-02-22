from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.models.tag_scoring_config import TagScoringConfig
from backend.models.tag_template import TagTemplate
from backend.models.tag_policy import TagPolicy


class TagScoringService:
    """
    Service responsible for calculating the compliance score of a resource
    based on its tags, the organization's tag templates, scoring config, and policies.
    """

    def __init__(self, db: Session, organization_id: str):
        self.db = db
        self.organization_id = organization_id

    def calculate_score(
        self,
        resource_type: str,
        resource_tags: Dict[str, str]
    ) -> Tuple[int, str]:
        """
        Calculates compliance score (0-100) and returns a status 
        ('compliant', 'passing', 'review', 'critical')
        """
        # Fetch organization config
        config = self.db.query(TagScoringConfig).filter_by(organization_id=self.organization_id).first()
        mode = config.mode if config else "weighted"
        threshold = config.threshold if config else 60
        required_keys = config.required_keys if config else []

        # Find the most applicable template
        templates = self.db.query(TagTemplate).filter_by(organization_id=self.organization_id, is_active=True).all()
        
        # 1. Look for specific scope match
        matched_template = next((t for t in templates if resource_type in (t.scope or [])), None)
        # 2. Look for default if no specific match
        if not matched_template:
            matched_template = next((t for t in templates if t.is_default), None)
            
        # Fetch global policies
        policies = self.db.query(TagPolicy).filter_by(organization_id=self.organization_id, is_active=True).all()
        policy_map = {p.tag_key: p for p in policies}

        # If custom mode, only care about `required_keys`
        if mode == "custom":
            total_required = len(required_keys)
            if total_required == 0:
                score = 100
            else:
                present = sum(1 for k in required_keys if k in resource_tags and resource_tags.get(k))
                score = int((present / total_required) * 100)
            status = self._determine_status(score, threshold)
            return score, status

        # If no template, we can't do weighted or all-or-nothing properly based on templates.
        if not matched_template or not matched_template.tag_schema:
            return 100, "compliant"

        schema = matched_template.tag_schema
        # Schema is a list of dicts: {key, required, type, values, pattern, weight}
        
        if mode == "all":
            # All required tags must be present and valid.
            required_tags = [t for t in schema if t.get('required')]
            for t in required_tags:
                tag_key = t.get('key')
                if tag_key not in resource_tags or not resource_tags.get(tag_key):
                    return 0, "critical"
                
                # Check policy validation if exists
                if tag_key in policy_map:
                    is_valid, _ = policy_map[tag_key].validate_value(resource_tags.get(tag_key))
                    if not is_valid:
                        return 0, "critical"

            # Base score is 100 if required exist.
            score = 100
            status = self._determine_status(score, threshold)
            return score, status

        # mode == "weighted"
        total_weight = sum(t.get('weight', 10) for t in schema)
        if total_weight == 0:
            return 100, "compliant"

        earned_weight = 0
        for t in schema:
            tag_key = t.get('key')
            tag_weight = t.get('weight', 10)
            is_req = t.get('required', False)
            tag_val = resource_tags.get(tag_key)

            if tag_val:
                # Check validation
                valid = True
                if tag_key in policy_map:
                    is_valid, _ = policy_map[tag_key].validate_value(tag_val)
                    valid = is_valid
                
                if valid:
                    earned_weight += tag_weight
            elif is_req:
                # If a required tag is absent, we just don't get the points in weighted mode.
                pass
                
        score = int((earned_weight / total_weight) * 100)
        status = self._determine_status(score, threshold)
        
        return score, status

    def _determine_status(self, score: int, threshold: int) -> str:
        if score >= 90:
            return "compliant"
        elif score >= 70 and score >= threshold:
            return "passing"
        elif score >= threshold:
            return "passing" # For values between threshold and 70
        elif score > 0:
            return "review"
        else:
            return "critical"

    def compute_preview(self, mode: str, threshold: int, required_keys: list) -> list:
        """
        Compute scoring preview for 5 mock resources using the provided temporary settings.
        This provides live preview for the scoring engine UI.
        """
        mock_resources = [
            {"name": "web-prod-01", "id": "i-0abc123", "type": "EC2", "tags": {"environment": "production", "owner": "alice@corp.com", "cost-center": "CC-1042", "team": "platform"}},
            {"name": "worker-stg-03", "id": "i-0def456", "type": "EC2", "tags": {"environment": "staging"}},
            {"name": "postgres-prod", "id": "rds-prod", "type": "RDS", "tags": {"environment": "production", "owner": "dba@corp.com", "cost-center": "CC-2017", "backup-policy": "daily", "data-classification": "confidential"}},
        ]
        
        results = []
        for res in mock_resources:
            # Overwrite db config temporarily for this calculation by saving state or isolated method
            # For simplicity, we just use the calculation logic adapted for parameters.
            
            # Since calculate_score reads from db, we will temporarily alter the score config in memory or just use a simplified version for preview.
            # Real implementation would pass mode/threshold/keys to calculate_score. Let's do a direct calculation here for the preview.
            schema = [
                {"key": "environment", "required": True, "weight": 10},
                {"key": "owner", "required": False, "weight": 5},
                {"key": "cost-center", "required": True, "weight": 10},
                {"key": "team", "required": False, "weight": 5},
            ]
            
            score = 0
            if mode == "custom":
                total_req = len(required_keys)
                if total_req == 0:
                    score = 100
                else:
                    present = sum(1 for k in required_keys if k in res["tags"])
                    score = int((present / total_req) * 100)
            elif mode == "all":
                req_keys = [t["key"] for t in schema if t["required"]]
                if all(k in res["tags"] for k in req_keys):
                    score = 100
                else:
                    score = 0
            else: # weighted
                total_weight = sum(t["weight"] for t in schema)
                earned = 0
                for t in schema:
                    if t["key"] in res["tags"]:
                        earned += t["weight"]
                score = int((earned / total_weight) * 100) if total_weight > 0 else 100

            results.append({
                "resource_id": res["id"],
                "resource_name": res["name"],
                "resource_type": res["type"],
                "tags": res["tags"],
                "score": score,
                "status": self._determine_status(score, threshold)
            })
            
        return results
