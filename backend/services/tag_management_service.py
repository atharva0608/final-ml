"""
Tag Management Service
Handles AWS tag operations (read/write) via boto3
"""
from typing import List, Dict, Optional, Any
import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

from backend.models.account import Account
from backend.services.tag_policy_service import TagPolicyService
from backend.schemas.tag_management_schemas import (
    ResourceTagUpdate,
    BulkTagUpdate,
    ResourceTagsResponse,
    BulkTagResult,
    TagSuggestion
)


class TagManagementService:
    """Service for managing AWS resource tags"""
    
    def __init__(self, db: Session, organization_id: str):
        self.db = db
        self.organization_id = organization_id
        self.policy_service = TagPolicyService(db, organization_id)
    
    def _get_boto3_client(self, service: str, account_id: str, region: str = "us-east-1"):
        """Get boto3 client for AWS service"""
        # Get account credentials
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == self.organization_id
        ).first()
        
        if not account or not account.role_arn:
            raise ValueError(f"Account {account_id} not found or not configured")
        
        # Assume role
        sts = boto3.client('sts')
        _assume_kwargs = {
            "RoleArn": account.role_arn,
            "RoleSessionName": f"TagManagement-{service}-{account_id[:8]}"
        }
        if getattr(account, 'external_id', None):
            _assume_kwargs["ExternalId"] = account.external_id
        assumed_role = sts.assume_role(**_assume_kwargs)
        
        credentials = assumed_role['Credentials']
        
        # Create service client
        client = boto3.client(
            service,
            region_name=region,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
        
        return client
    
    def get_resource_tags(self, resource_type: str, resource_id: str, account_id: str, region: str = "us-east-1") -> ResourceTagsResponse:
        """Get current tags for a resource"""
        tags = {}
        
        try:
            if resource_type == "EC2":
                ec2 = self._get_boto3_client("ec2", account_id, region)
                response = ec2.describe_tags(
                    Filters=[
                        {"Name": "resource-id", "Values": [resource_id]}
                    ]
                )
                tags = {tag["Key"]: tag["Value"] for tag in response.get("Tags", [])}
            
            elif resource_type == "EBS":
                ec2 = self._get_boto3_client("ec2", account_id, region)
                response = ec2.describe_volumes(VolumeIds=[resource_id])
                if response["Volumes"]:
                    tags = {tag["Key"]: tag["Value"] for tag in response["Volumes"][0].get("Tags", [])}
            
            elif resource_type == "S3":
                s3 = self._get_boto3_client("s3", account_id, region)
                try:
                    response = s3.get_bucket_tagging(Bucket=resource_id)
                    tags = {tag["Key"]: tag["Value"] for tag in response.get("TagSet", [])}
                except ClientError as e:
                    if e.response['Error']['Code'] != 'NoSuchTagSet':
                        raise
            
            elif resource_type == "RDS":
                rds = self._get_boto3_client("rds", account_id, region)
                # Construct ARN
                arn = f"arn:aws:rds:{region}:{account_id}:db:{resource_id}"
                response = rds.list_tags_for_resource(ResourceName=arn)
                tags = {tag["Key"]: tag["Value"] for tag in response.get("TagList", [])}
        
        except Exception as e:
            logger.error(f"Error getting tags for {resource_type}/{resource_id}: {e}")
            raise
        
        # Check compliance
        validation = self.policy_service.validate_tags(tags, resource_type, region)
        
        return ResourceTagsResponse(
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            current_tags=tags,
            missing_required_tags=[ missing["tag_key"] for missing in validation["missing_required"]],
            is_compliant=validation["is_valid"],
            suggestions=[]  # Populated by TagSuggestionService
        )
    
    def update_resource_tags(
        self,
        resource_type: str,
        resource_id: str,
        account_id: str,
        update_data: ResourceTagUpdate,
        region: str = "us-east-1"
    ) -> Dict[str, Any]:
        """Update tags on a single resource"""
        try:
            tags_to_apply = update_data.tags
            
            # Validate tags against policies
            validation = self.policy_service.validate_tags(tags_to_apply, resource_type, region)
            
            if resource_type == "EC2":
                ec2 = self._get_boto3_client("ec2", account_id, region)
                ec2.create_tags(
                    Resources=[resource_id],
                    Tags=[{"Key": k, "Value": v} for k, v in tags_to_apply.items()]
                )
                
                # Propagate to related resources if requested
                if update_data.propagate_to_related:
                    self._propagate_ec2_tags(ec2, resource_id, tags_to_apply)
            
            elif resource_type == "EBS":
                ec2 = self._get_boto3_client("ec2", account_id, region)
                ec2.create_tags(
                    Resources=[resource_id],
                    Tags=[{"Key": k, "Value": v} for k, v in tags_to_apply.items()]
                )
            
            elif resource_type == "S3":
                s3 = self._get_boto3_client("s3", account_id, region)
                
                # Get existing tags if not overwriting
                existing_tags = {}
                if not update_data.overwrite_existing:
                    try:
                        response = s3.get_bucket_tagging(Bucket=resource_id)
                        existing_tags = {tag["Key"]: tag["Value"] for tag in response.get("TagSet", [])}
                    except ClientError:
                        pass
                
                # Merge tags
                merged_tags = {**existing_tags, **tags_to_apply}
                
                s3.put_bucket_tagging(
                    Bucket=resource_id,
                    Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in merged_tags.items()]}
                )
            
            elif resource_type == "RDS":
                rds = self._get_boto3_client("rds", account_id, region)
                arn = f"arn:aws:rds:{region}:{account_id}:db:{resource_id}"
                rds.add_tags_to_resource(
                    ResourceName=arn,
                    Tags=[{"Key": k, "Value": v} for k, v in tags_to_apply.items()]
                )
            
            return {
                "success": True,
                "resource_id": resource_id,
                "tags_applied": tags_to_apply,
                "validation": validation
            }
        
        except Exception as e:
            logger.error(f"Error updating tags for {resource_type}/{resource_id}: {e}")
            return {
                "success": False,
                "resource_id": resource_id,
                "error": str(e)
            }
    
    def bulk_update_tags(
        self,
        account_id: str,
        bulk_data: BulkTagUpdate
    ) -> BulkTagResult:
        """Apply tags to multiple resources"""
        results = {
            "total_requested": len(bulk_data.resource_ids),
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "failed_resources": []
        }
        
        for resource_id in bulk_data.resource_ids:
            try:
                # For bulk operations, create ResourceTagUpdate
                update = ResourceTagUpdate(
                    tags=bulk_data.tags,
                    propagate_to_related=False,  # Too risky for bulk
                    overwrite_existing=(bulk_data.operation_mode == "replace")
                )
                
                result = self.update_resource_tags(
                    bulk_data.resource_type,
                    resource_id,
                    account_id,
                    update,
                    bulk_data.region or "us-east-1"
                )
                
                if result["success"]:
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                    results["failed_resources"].append({
                        "resource_id": resource_id,
                        "error": result.get("error", "Unknown error")
                    })
            
            except Exception as e:
                logger.error(f"Error in bulk tagging {resource_id}: {e}")
                results["failed"] += 1
                results["failed_resources"].append({
                    "resource_id": resource_id,
                    "error": str(e)
                })
        
        return BulkTagResult(
            total_requested=results["total_requested"],
            successful=results["successful"],
            failed=results["failed"],
            skipped=results["skipped"],
            failed_resources=results["failed_resources"],
            operation_mode=bulk_data.operation_mode,
            tags_applied=bulk_data.tags
        )
    
    def _propagate_ec2_tags(self, ec2_client, instance_id: str, tags: Dict[str, str]):
        """Propagate tags from EC2 instance to its volumes and snapshots"""
        try:
            # Get volumes attached to instance
            response = ec2_client.describe_volumes(
                Filters=[
                    {"Name": "attachment.instance-id", "Values": [instance_id]}
                ]
            )
            
            volume_ids = [vol["VolumeId"] for vol in response.get("Volumes", [])]
            
            if volume_ids:
                ec2_client.create_tags(
                    Resources=volume_ids,
                    Tags=[{"Key": k, "Value": v} for k, v in tags.items()]
                )
                logger.info(f"Propagated tags to {len(volume_ids)} volumes")
        
        except Exception as e:
            logger.warning(f"Failed to propagate tags: {e}")
