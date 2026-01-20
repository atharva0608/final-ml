"""
Auto-Tag Service
Executes automated tagging rules
"""
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

from backend.models.auto_tag_rule import AutoTagRule, RunMode
from backend.models.account import Account
from backend.services.tag_management_service import TagManagementService
from backend.schemas.auto_tag_schemas import RuleTestResult, RuleExecutionResult
from backend.schemas.tag_management_schemas import ResourceTagUpdate


class AutoTagService:
    """Service for managing and executing auto-tag rules"""
    
    def __init__(self, db: Session, organization_id: str):
        self.db = db
        self.organization_id = organization_id
        self.tag_mgmt_service = TagManagementService(db, organization_id)
    
    def create_rule(self, rule_data: Dict[str, Any], created_by: str) -> AutoTagRule:
        """Create a new auto-tag rule"""
        rule = AutoTagRule(
            organization_id=self.organization_id,
            created_by=created_by,
            **rule_data
        )
        
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        
        return rule
    
    def get_rule(self, rule_id: str) -> Optional[AutoTagRule]:
        """Get a specific rule"""
        return self.db.query(AutoTagRule).filter(
            AutoTagRule.id == rule_id,
            AutoTagRule.organization_id == self.organization_id
        ).first()
    
    def list_rules(self, active_only: bool = True) -> List[AutoTagRule]:
        """List all rules for the organization"""
        query = self.db.query(AutoTagRule).filter(
            AutoTagRule.organization_id == self.organization_id
        )
        
        if active_only:
            query = query.filter(AutoTagRule.is_active == True)
        
        return query.order_by(AutoTagRule.priority).all()
    
    def test_rule(self, rule_id: str, account_id: str) -> RuleTestResult:
        """Test a rule to preview which resources would match"""
        import time
        start_time = time.time()
        
        rule = self.get_rule(rule_id)
        if not rule:
            raise ValueError(f"Rule {rule_id} not found")
        
        matched_resources = []
        
        # Get account
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == self.organization_id
        ).first()
        
        if not account or not account.role_arn:
            raise ValueError(f"Account {account_id} not found or not configured")
        
        # Scan resources based on rule criteria
        for resource_type in rule.resource_types:
            resources = self._scan_resources_of_type(
                resource_type,
                account,
                rule.regions or ["us-east-1"]
            )
            
            for resource in resources:
                if rule.matches_resource(
                    resource_type,
                    resource["name"],
                    resource.get("region")
                ):
                    matched_resources.append({
                        "resource_id": resource["id"],
                        "resource_name": resource["name"],
                        "resource_type": resource_type,
                        "region": resource.get("region"),
                        "current_tags": resource.get("tags", {})
                    })
        
        would_tag = len([r for r in matched_resources if r["current_tags"] != rule.tags_to_apply])
        
        return RuleTestResult(
            rule_id=rule.id,
            rule_name=rule.name,
            matched_resources=matched_resources,
            match_count=len(matched_resources),
            would_tag_count=would_tag,
            sample_resources=matched_resources[:10]  # Limit to 10 for preview
        )
    
    def execute_rule(self, rule_id: str, account_id: str) -> RuleExecutionResult:
        """Execute an auto-tag rule"""
        import time
        start_time = time.time()
        
        rule = self.get_rule(rule_id)
        if not rule or not rule.is_active:
            raise ValueError(f"Rule {rule_id} not found or inactive")
        
        # Test first to get matches
        test_result = self.test_rule(rule_id, account_id)
        
        tagged_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []
        
        # Apply tags to matched resources
        for resource in test_result.matched_resources:
            try:
                # Skip if tags are already correct
                if resource["current_tags"] == rule.tags_to_apply:
                    skipped_count += 1
                    continue
                
                # Apply tags
                update = ResourceTagUpdate(
                    tags=rule.tags_to_apply,
                    propagate_to_related=False,
                    overwrite_existing=False  # Merge by default
                )
                
                result = self.tag_mgmt_service.update_resource_tags(
                    resource["resource_type"],
                    resource["resource_id"],
                    account_id,
                    update,
                    resource.get("region", "us-east-1")
                )
                
                if result["success"]:
                    tagged_count += 1
                else:
                    failed_count += 1
                    errors.append(f"{resource['resource_id']}: {result.get('error', 'Unknown error')}")
            
            except Exception as e:
                failed_count += 1
                errors.append(f"{resource['resource_id']}: {str(e)}")
                logger.error(f"Error executing rule {rule_id} on {resource['resource_id']}: {e}")
        
        # Update rule statistics
        rule.last_run_at = datetime.utcnow()
        rule.last_run_matched = test_result.match_count
        rule.last_run_tagged = tagged_count
        rule.total_resources_tagged += tagged_count
        self.db.commit()
        
        execution_time = time.time() - start_time
        
        return RuleExecutionResult(
            rule_id=rule.id,
            rule_name=rule.name,
            matched_resources=test_result.match_count,
            tagged_resources=tagged_count,
            failed_resources=failed_count,
            skipped_resources=skipped_count,
            execution_time_seconds=execution_time,
            errors=errors[:20]  # Limit error list
        )
    
    def _scan_resources_of_type(
        self,
        resource_type: str,
        account: Account,
        regions: List[str]
    ) ->  List[Dict[str, Any]]:
        """Scan AWS account for resources of a specific type"""
        resources = []
        
        # Assume role
        sts = boto3.client('sts')
        try:
            assumed_role = sts.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=f"AutoTag-{resource_type}-{account.id[:8]}"
            )
            credentials = assumed_role['Credentials']
        except Exception as e:
            logger.error(f"Failed to assume role: {e}")
            return []
        
        for region in regions:
            if region == "*":
                region = "us-east-1"  # Default region
            
            try:
                if resource_type == "EC2":
                    ec2 = boto3.client(
                        'ec2',
                        region_name=region,
                        aws_access_key_id=credentials['AccessKeyId'],
                        aws_secret_access_key=credentials['SecretAccessKey'],
                        aws_session_token=credentials['SessionToken']
                    )
                    
                    response = ec2.describe_instances()
                    for reservation in response.get('Reservations', []):
                        for instance in reservation.get('Instances', []):
                            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                            resources.append({
                                "id": instance['InstanceId'],
                                "name": tags.get('Name', instance['InstanceId']),
                                "region": region,
                                "tags": tags
                            })
                
                elif resource_type == "EBS":
                    ec2 = boto3.client(
                        'ec2',
                        region_name=region,
                        aws_access_key_id=credentials['AccessKeyId'],
                        aws_secret_access_key=credentials['SecretAccessKey'],
                        aws_session_token=credentials['SessionToken']
                    )
                    
                    response = ec2.describe_volumes()
                    for volume in response.get('Volumes', []):
                        tags = {tag['Key']: tag['Value'] for tag in volume.get('Tags', [])}
                        resources.append({
                            "id": volume['VolumeId'],
                            "name": tags.get('Name', volume['VolumeId']),
                            "region": region,
                            "tags": tags
                        })
            
            except Exception as e:
                logger.error(f"Error scanning {resource_type} in {region}: {e}")
                continue
        
        return resources
