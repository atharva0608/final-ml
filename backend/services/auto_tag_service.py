"""
Auto-Tag Service
Executes automated tagging rules with dynamic value resolution
"""
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import logging
import os

logger = logging.getLogger(__name__)

from backend.models.auto_tag_rule import AutoTagRule, RunMode, ValueSourceType, OverrideBehavior, ResourceScope
from backend.models.account import Account
from backend.models.user import User
from backend.models.organization import Organization
from backend.services.tag_management_service import TagManagementService
from backend.schemas.auto_tag_schemas import (
    RuleTestResult, RuleExecutionResult, TagPreviewRequest, TagPreviewResponse,
    AvailableVariable, AvailableVariablesResponse, ValueSourceType as SchemaValueSourceType
)
from backend.schemas.tag_management_schemas import ResourceTagUpdate


# System tag that identifies resources managed by this platform
SYSTEM_TAG_KEY = "ManagedBy"
SYSTEM_TAG_VALUE = "SpotOptimizer"


class AutoTagService:
    """Service for managing and executing auto-tag rules with dynamic value resolution"""
    
    def __init__(self, db: Session, organization_id: str):
        self.db = db
        self.organization_id = organization_id
        self.tag_mgmt_service = TagManagementService(db, organization_id)
    
    def generate_tags(
        self,
        resource_type: str,
        resource_name: Optional[str] = None,
        region: Optional[str] = None,
        user: Optional[User] = None,
        rule_ids: Optional[List[str]] = None,
        include_system_tags: bool = True
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Generate resolved tags for a resource based on active rules.
        This is the central "Generator" function for the Smart Auto-Tag system.
        
        Args:
            resource_type: Type of resource (EC2, S3, RDS, etc.)
            resource_name: Optional resource name for pattern matching
            region: AWS region
            user: User context for dynamic value resolution
            rule_ids: Specific rule IDs to apply (all active if None)
            include_system_tags: Whether to inject ManagedBy system tag
        
        Returns:
            Tuple of (resolved_tags_dict, list_of_applied_rule_names)
        """
        final_tags = {}
        applied_rules = []
        
        # Get applicable rules
        if rule_ids:
            rules = self.db.query(AutoTagRule).filter(
                AutoTagRule.id.in_(rule_ids),
                AutoTagRule.organization_id == self.organization_id,
                AutoTagRule.is_active == True
            ).order_by(AutoTagRule.priority).all()
        else:
            rules = self.list_rules(active_only=True)
        
        # Get organization for context
        org = self.db.query(Organization).filter(
            Organization.id == self.organization_id
        ).first()
        
        for rule in rules:
            # Check if rule matches this resource
            if resource_name and not rule.matches_resource(resource_type, resource_name, region):
                continue
            
            # Check resource scope
            if not self._matches_resource_scope(resource_type, rule.resource_scope):
                continue
            
            applied_rules.append(rule.name)
            
            # Apply static tags
            if rule.tags_to_apply:
                for key, value in rule.tags_to_apply.items():
                    if key not in final_tags or rule.override_behavior == OverrideBehavior.OVERWRITE.value:
                        final_tags[key] = value
            
            # Apply dynamic tags
            if rule.dynamic_tags:
                for key, config in rule.dynamic_tags.items():
                    if key not in final_tags or rule.override_behavior == OverrideBehavior.OVERWRITE.value:
                        resolved_value = self._resolve_dynamic_value(config, user, org)
                        if resolved_value:
                            final_tags[key] = resolved_value
        
        # Inject system tags if enabled
        if include_system_tags and any(r.inject_system_tags for r in rules if r.name in applied_rules):
            final_tags[SYSTEM_TAG_KEY] = SYSTEM_TAG_VALUE
        
        return final_tags, applied_rules
    
    def _resolve_dynamic_value(
        self,
        config: Dict[str, Any],
        user: Optional[User],
        org: Optional[Organization]
    ) -> Optional[str]:
        """Resolve a dynamic tag value based on its source type"""
        source = config.get("source", "static")
        
        if source == ValueSourceType.STATIC.value:
            return config.get("static_value", "")
        
        elif source == ValueSourceType.USER_EMAIL.value:
            return user.email if user else "unknown@user"
        
        elif source == ValueSourceType.USER_ID.value:
            return user.id if user else "unknown"
        
        elif source == ValueSourceType.USER_NAME.value:
            return user.full_name if user and user.full_name else (user.email.split("@")[0] if user else "unknown")
        
        elif source == ValueSourceType.ORG_ID.value:
            return org.id if org else self.organization_id
        
        elif source == ValueSourceType.ORG_NAME.value:
            return org.name if org else "Unknown Org"
        
        elif source == ValueSourceType.CREATION_DATE.value:
            return datetime.utcnow().strftime("%Y-%m-%d")
        
        elif source == ValueSourceType.CREATION_TIME.value:
            return datetime.utcnow().isoformat()
        
        elif source == ValueSourceType.ENV_VARIABLE.value:
            env_var_name = config.get("env_var_name", "")
            return os.environ.get(env_var_name, f"${{{env_var_name}}}")
        
        return None
    
    def _matches_resource_scope(self, resource_type: str, scope: str) -> bool:
        """Check if resource type matches the scope filter"""
        if scope == ResourceScope.ALL.value or not scope:
            return True
        
        compute_types = ["EC2", "ECS", "LAMBDA", "EKS"]
        storage_types = ["S3", "EBS", "EFS", "GLACIER"]
        database_types = ["RDS", "DYNAMODB", "ELASTICACHE", "REDSHIFT"]
        network_types = ["VPC", "ELB", "ALB", "NLB", "ENI", "EIP", "NAT"]
        
        if scope == ResourceScope.COMPUTE_ONLY.value:
            return resource_type.upper() in compute_types
        elif scope == ResourceScope.STORAGE_ONLY.value:
            return resource_type.upper() in storage_types
        elif scope == ResourceScope.DATABASE_ONLY.value:
            return resource_type.upper() in database_types
        elif scope == ResourceScope.NETWORK_ONLY.value:
            return resource_type.upper() in network_types
        
        return True
    
    def get_available_variables(self) -> AvailableVariablesResponse:
        """Get list of available dynamic variables for the UI"""
        variables = [
            AvailableVariable(
                name="User Email",
                source_type=SchemaValueSourceType.USER_EMAIL,
                description="Email of the user creating the resource",
                example_value="user@company.com"
            ),
            AvailableVariable(
                name="User ID",
                source_type=SchemaValueSourceType.USER_ID,
                description="Unique ID of the user",
                example_value="usr-abc123"
            ),
            AvailableVariable(
                name="User Name",
                source_type=SchemaValueSourceType.USER_NAME,
                description="Full name of the user",
                example_value="John Doe"
            ),
            AvailableVariable(
                name="Organization ID",
                source_type=SchemaValueSourceType.ORG_ID,
                description="ID of the organization",
                example_value="org-xyz789"
            ),
            AvailableVariable(
                name="Organization Name",
                source_type=SchemaValueSourceType.ORG_NAME,
                description="Name of the organization",
                example_value="Acme Corp"
            ),
            AvailableVariable(
                name="Creation Date",
                source_type=SchemaValueSourceType.CREATION_DATE,
                description="Date when resource is created (YYYY-MM-DD)",
                example_value=datetime.utcnow().strftime("%Y-%m-%d")
            ),
            AvailableVariable(
                name="Creation Timestamp",
                source_type=SchemaValueSourceType.CREATION_TIME,
                description="Full ISO timestamp of resource creation",
                example_value=datetime.utcnow().isoformat()
            ),
            AvailableVariable(
                name="Environment Variable",
                source_type=SchemaValueSourceType.ENV_VARIABLE,
                description="Value from a server environment variable",
                example_value="${ENV_NAME}"
            ),
        ]
        return AvailableVariablesResponse(variables=variables)
    
    def preview_tags(self, request: TagPreviewRequest, user: Optional[User] = None) -> TagPreviewResponse:
        """Preview what tags would be generated for a resource"""
        tags, applied_rules = self.generate_tags(
            resource_type=request.resource_type,
            resource_name=request.resource_name,
            region=request.region,
            user=user,
            rule_ids=request.rule_ids,
            include_system_tags=True
        )
        
        return TagPreviewResponse(
            tags=tags,
            applied_rules=applied_rules,
            system_tags_injected=SYSTEM_TAG_KEY in tags
        )
    
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
