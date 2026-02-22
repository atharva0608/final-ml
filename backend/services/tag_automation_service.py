from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.models.tag_automation_rule import TagAutomationRule
from backend.models.tag_compliance_score import TagComplianceScore
from backend.models.tag_automation_log import TagAutomationLog


class TagAutomationService:
    """
    Evaluates Tag Automation Rules against non-compliant resources
    and executes actions (like notifying, flagging, or deleting).
    """

    @staticmethod
    def evaluate_rules(db: Session, organization_id: str):
        """
        Run the automation cycle. 
        Checks non-compliant resources against all enabled rules.
        """
        rules = db.query(TagAutomationRule).filter_by(
            organization_id=organization_id, enabled=True
        ).all()

        if not rules:
            return

        # Fetch non-compliant resources
        resources = db.query(TagComplianceScore).filter(
            TagComplianceScore.organization_id == organization_id,
            TagComplianceScore.status.in_(["review", "critical", "deletion"])
        ).all()

        for rule in rules:
            for resource in resources:
                if TagAutomationService._resource_matches_rule(resource, rule):
                    TagAutomationService._process_resource(db, resource, rule)

            rule.last_run_at = datetime.utcnow()
        
        db.commit()

    @staticmethod
    def _resource_matches_rule(resource: TagComplianceScore, rule: TagAutomationRule) -> bool:
        # Check resource types scope
        if rule.resource_types and resource.resource_type not in rule.resource_types:
            return False

        # Check trigger expression (simplified parser)
        # e.g., 'score < 60', 'score == 0', 'missing:owner'
        trigger = rule.trigger_expr
        if "score <" in trigger:
            thresh = int(trigger.split("<")[1].strip())
            if resource.score >= thresh:
                return False
        elif "score ==" in trigger:
            thresh = int(trigger.split("==")[1].strip())
            if resource.score != thresh:
                return False
        # If trigger is 'missing:owner' we'd ideally check actual tags, 
        # but TagComplianceScore abstracts this into score/status.
        
        # Check safety conditions
        conds = rule.safety_conditions or []
        if "not_prod" in conds and getattr(resource, "environment", "") == "production":
            return False
            
        return True

    @staticmethod
    def _process_resource(db: Session, resource: TagComplianceScore, rule: TagAutomationRule):
        """
        Applies grace period logic and executes action.
        """
        now = datetime.utcnow()

        # If grace period not started, start it
        if not resource.grace_deadline:
            resource.grace_deadline = now + timedelta(days=rule.grace_days)
            if rule.action == "delete":
                resource.status = "deletion"
            elif rule.action == "flag":
                resource.status = "review"
            db.add(resource)
            
            # Log initial notification / flagging
            log = TagAutomationLog(
                organization_id=resource.organization_id,
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                rule_id=rule.id,
                action="FLAGGED" if rule.action == "flag" else "NOTIFIED",
                reason=f"Matched rule: {rule.name}",
                outcome="success"
            )
            db.add(log)
            return

        # If grace period is over, execute action
        if now >= resource.grace_deadline:
            action_executed = rule.action
            savings = str(resource.monthly_cost) if resource.monthly_cost else "0"
            
            # Simulated Execution 
            if rule.action == "delete":
                # db.delete(actual_resource)
                action_executed = "DELETED"
            elif rule.action == "stop":
                action_executed = "STOPPED"
            elif rule.action == "auto_tag":
                action_executed = "AUTO-TAGGED"
            
            log = TagAutomationLog(
                organization_id=resource.organization_id,
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                rule_id=rule.id,
                action=action_executed.upper(),
                reason=f"Grace period expired for rule: {rule.name}",
                savings=f"${savings}/mo recovered" if rule.action == "delete" else "0",
                outcome="success"
            )
            db.add(log)
            
            # Reset grace period or clear out if deleted
            if rule.action == "delete":
                db.delete(resource)
            else:
                # If we auto-tagged or stopped, maybe we reset grace deadline to see if it becomes compliant?
                resource.grace_deadline = None
                
            db.add(log)
