"""
Governance Service - Automated Policy Enforcement (Feature 4)
"""
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from backend.models.organization import Organization
from backend.models.account import Account
from backend.models.audit_log import AuditLog
from backend.services.cleanup_service import CleanupService
from backend.schemas.cleanup_schemas import CleanupAction, CleanupActionType

logger = logging.getLogger(__name__)


class GovernanceService:
    """
    Feature 4: Automated Governance / Policy-as-Code
    Automatically executes cleanup actions based on organization policies.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_default_policies(self) -> Dict[str, Any]:
        """Default governance policy configuration"""
        return {
            "auto_release_orphaned_ips": {"enabled": False, "threshold_days": 7},
            "auto_delete_orphaned_volumes": {"enabled": False, "threshold_days": 30},
            "auto_delete_orphaned_snapshots": {"enabled": False, "threshold_days": 30},
            "auto_flag_untagged_resources": {"enabled": True, "required_tags": ["Owner", "Environment"]}
        }
    
    def get_organization_policies(self, organization_id: str) -> Dict[str, Any]:
        """Get merged policies for an organization"""
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            return self.get_default_policies()
        
        # Merge default with org-specific overrides
        policies = self.get_default_policies()
        if org.governance_config:
            for key, value in org.governance_config.items():
                if key in policies:
                    policies[key].update(value)
        
        return policies
    
    def run_automated_cleanup(self, organization_id: str, account_id: str) -> List[Dict[str, Any]]:
        """
        Execute automated cleanup based on governance policies.
        Called by a scheduled worker or manually by Admin.
        Returns list of actions taken.
        """
        org = self.db.query(Organization).filter(Organization.id == organization_id).first()
        if not org or not org.is_governance_enabled:
            logger.info(f"Governance disabled for org {organization_id}")
            return []
        
        policies = self.get_organization_policies(organization_id)
        cleanup_svc = CleanupService(self.db)
        actions_taken = []
        
        # Scan resources
        try:
            scan_result = cleanup_svc.scan_resources(account_id, organization=org)
        except Exception as e:
            logger.error(f"Governance scan failed: {e}")
            return []
        
        now = datetime.now(timezone.utc)
        
        # Process each policy
        for resource in scan_result.resources:
            action_taken = None
            
            # Policy: Auto-release Elastic IPs
            if (resource.type.value == "ELASTIC_IP" and 
                policies["auto_release_orphaned_ips"]["enabled"]):
                action_taken = self._execute_autopilot_action(
                    cleanup_svc, account_id, resource, CleanupActionType.RELEASE, org.id
                )
            
            # Policy: Auto-delete Orphaned Volumes (older than threshold)
            elif (resource.type.value == "VOLUME" and 
                  resource.status.value in ["ORPHANED", "SAFE_TO_DELETE"] and
                  policies["auto_delete_orphaned_volumes"]["enabled"]):
                threshold_days = policies["auto_delete_orphaned_volumes"]["threshold_days"]
                created_str = resource.metadata.get("Created", "")
                if self._is_older_than(created_str, threshold_days):
                    action_taken = self._execute_autopilot_action(
                        cleanup_svc, account_id, resource, CleanupActionType.DELETE, org.id
                    )
            
            # Policy: Auto-delete Orphaned Snapshots
            elif (resource.type.value == "SNAPSHOT" and 
                  resource.status.value in ["ORPHANED", "SAFE_TO_DELETE"] and
                  policies["auto_delete_orphaned_snapshots"]["enabled"]):
                threshold_days = policies["auto_delete_orphaned_snapshots"]["threshold_days"]
                # Snapshots use StartTime in metadata or status based check
                if resource.status.value == "SAFE_TO_DELETE":  # Already verified >30 days
                    action_taken = self._execute_autopilot_action(
                        cleanup_svc, account_id, resource, CleanupActionType.DELETE, org.id
                    )
            
            if action_taken:
                actions_taken.append(action_taken)
        
        return actions_taken
    
    def _execute_autopilot_action(self, cleanup_svc: CleanupService, account_id: str, 
                                   resource, action_type: CleanupActionType, org_id: str) -> Dict[str, Any]:
        """Execute action as System Autopilot and log to audit"""
        try:
            action = CleanupAction(
                resource_ids=[resource.id],
                action_type=action_type,
                region=resource.region
            )
            
            # Bypass approval - this is autopilot
            result = cleanup_svc.execute_action(account_id, action, user=None, bypass_approval=True)
            
            # Log to Audit with "System Autopilot" actor
            audit_entry = AuditLog(
                actor="System Autopilot",
                actor_type="SYSTEM",
                event=f"AUTO_{action_type.value}",
                resource_type=resource.type.value,
                resource_id=resource.id,
                outcome="SUCCESS" if result.get("status") == "success" else "FAILED",
                organization_id=org_id,
                details={
                    "region": resource.region,
                    "cost_saved": resource.cost_per_month,
                    "policy": f"auto_{resource.type.value.lower()}"
                }
            )
            self.db.add(audit_entry)
            self.db.commit()
            
            logger.info(f"[Autopilot] Executed {action_type} on {resource.id}")
            return {
                "resource_id": resource.id,
                "action": action_type.value,
                "status": result.get("status"),
                "cost_saved": resource.cost_per_month
            }
            
        except Exception as e:
            logger.error(f"[Autopilot] Failed to execute {action_type} on {resource.id}: {e}")
            return {
                "resource_id": resource.id,
                "action": action_type.value,
                "status": "failed",
                "error": str(e)
            }
    
    def _is_older_than(self, date_str: str, days: int) -> bool:
        """Check if a date string represents a time older than N days ago"""
        try:
            # Handle ISO format or simple date strings
            if 'T' in date_str:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                dt = datetime.strptime(date_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)
            
            threshold = datetime.now(timezone.utc) - timedelta(days=days)
            return dt < threshold
        except Exception:
            return False


def get_governance_service(db: Session) -> GovernanceService:
    """Factory function for GovernanceService"""
    return GovernanceService(db)
