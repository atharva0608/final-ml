"""
Cleanup Service

Business logic for Resource Hygiene & Cleanup operations.
Scans AWS accounts across ALL regions to identify orphaned resources.
"""
import boto3
from typing import List, Dict, Any, Set
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError

from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.instance import Instance
from backend.models.user import User
from backend.schemas.cleanup_schemas import (
    CleanupSummary,
    ResourceItem,
    ResourceType,
    CleanupStatus,
    CleanupAction,
    CleanupActionResponse,
    ActionType
)
from backend.core.exceptions import ResourceNotFoundError, ValidationError
from backend.core.logger import StructuredLogger

logger = StructuredLogger(__name__)


class CleanupService:
    """Service for scanning and cleaning orphaned AWS resources across all regions"""

    # AWS pricing estimates (monthly, USD)
    PRICING = {
        # EC2 instances (average t3.medium equivalent)
        'instance': Decimal('30.00'),
        # EBS volumes (per GB)
        'volume_per_gb': Decimal('0.10'),
        # Snapshots (per GB)
        'snapshot_per_gb': Decimal('0.05'),
        # Elastic IP (unassociated)
        'elastic_ip': Decimal('3.60')
    }

    def __init__(self, db: Session):
        self.db = db

    def _get_aws_credentials(self, account: Account) -> Dict[str, str]:
        """
        Get temporary AWS credentials using STS assume_role

        Args:
            account: Account model with role_arn and external_id

        Returns:
            Dict with AccessKeyId, SecretAccessKey, SessionToken

        Raises:
            ValidationError: If account credentials are invalid or missing
        """
        if not account.role_arn or not account.external_id:
            raise ValidationError("Account is missing AWS credentials (role_arn or external_id)")

        try:
            sts = boto3.client('sts')
            assumed = sts.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName="SpotOptimizerCleanup",
                ExternalId=account.external_id
            )
            return assumed['Credentials']
        except ClientError as e:
            logger.error(f"Failed to assume role for account {account.id}: {str(e)}")
            raise ValidationError(f"Failed to authenticate with AWS: {str(e)}")

    def _get_aws_client(self, credentials: Dict[str, str], service_name: str, region: str):
        """
        Create AWS service client with temporary credentials for specific region

        Args:
            credentials: AWS credentials from STS assume_role
            service_name: AWS service (ec2, sts, etc.)
            region: AWS region name

        Returns:
            Boto3 client for the specified service and region
        """
        return boto3.client(
            service_name,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region
        )

    def _get_enabled_regions(self, credentials: Dict[str, str]) -> List[str]:
        """
        Get list of all enabled AWS regions for the account

        Args:
            credentials: AWS credentials from STS assume_role

        Returns:
            List of enabled region names (e.g., ['us-east-1', 'eu-west-1', ...])
        """
        try:
            # Use us-east-1 as the default region to query for all regions
            ec2_global = self._get_aws_client(credentials, 'ec2', 'us-east-1')
            regions_response = ec2_global.describe_regions(
                Filters=[{'Name': 'opt-in-status', 'Values': ['opt-in-not-required', 'opted-in']}]
            )
            return [region['RegionName'] for region in regions_response['Regions']]
        except ClientError as e:
            logger.warning(f"Failed to get enabled regions, falling back to default: {str(e)}")
            # Fallback to common regions if we can't query
            return ['us-east-1', 'us-west-2', 'eu-west-1']

    def _get_managed_instance_ids(self, account_id: str) -> Set[str]:
        """
        Get set of instance IDs that are managed by our system (part of clusters)

        Args:
            account_id: Account UUID

        Returns:
            Set of AWS instance IDs (e.g., {'i-1234567890abcdef0', ...})
        """
        instances = self.db.query(Instance).join(Cluster).filter(
            Cluster.account_id == account_id
        ).all()
        return {instance.instance_id for instance in instances}

    def _scan_unauthorized_instances(
        self,
        credentials: Dict[str, str],
        regions: List[str],
        managed_instance_ids: Set[str]
    ) -> List[ResourceItem]:
        """
        Scan all regions for EC2 instances that are not part of managed clusters

        Args:
            credentials: AWS credentials
            regions: List of regions to scan
            managed_instance_ids: Set of instance IDs we manage

        Returns:
            List of unauthorized instance ResourceItems
        """
        unauthorized = []

        for region in regions:
            try:
                ec2 = self._get_aws_client(credentials, 'ec2', region)

                # Get all running and stopped instances
                response = ec2.describe_instances(
                    Filters=[
                        {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
                    ]
                )

                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        instance_id = instance['InstanceId']

                        # Skip if this instance is managed by us
                        if instance_id in managed_instance_ids:
                            continue

                        # Extract name from tags
                        name = None
                        for tag in instance.get('Tags', []):
                            if tag['Key'] == 'Name':
                                name = tag['Value']
                                break

                        state = instance['State']['Name']
                        instance_type = instance['InstanceType']

                        # Estimate cost (this is a rough estimate)
                        cost = self.PRICING['instance']

                        unauthorized.append(ResourceItem(
                            id=instance_id,
                            name=name or instance_id,
                            type=ResourceType.INSTANCE,
                            status=CleanupStatus.STOPPED if state == 'stopped' else CleanupStatus.ORPHANED,
                            cost_per_month=cost,
                            region=region,
                            is_authorized=False,
                            metadata={
                                'instance_type': instance_type,
                                'state': state,
                                'launch_time': instance['LaunchTime'].isoformat() if 'LaunchTime' in instance else None
                            },
                            discovered_at=datetime.utcnow()
                        ))

            except ClientError as e:
                logger.warning(f"Failed to scan instances in region {region}: {str(e)}")
                continue

        return unauthorized

    def _scan_orphaned_volumes(
        self,
        credentials: Dict[str, str],
        regions: List[str]
    ) -> List[ResourceItem]:
        """
        Scan all regions for unattached EBS volumes

        Args:
            credentials: AWS credentials
            regions: List of regions to scan

        Returns:
            List of orphaned volume ResourceItems
        """
        orphaned = []

        for region in regions:
            try:
                ec2 = self._get_aws_client(credentials, 'ec2', region)

                # Get all available (unattached) volumes
                response = ec2.describe_volumes(
                    Filters=[
                        {'Name': 'status', 'Values': ['available']}
                    ]
                )

                for volume in response['Volumes']:
                    volume_id = volume['VolumeId']
                    size_gb = volume['Size']
                    volume_type = volume['VolumeType']

                    # Extract name from tags
                    name = None
                    for tag in volume.get('Tags', []):
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break

                    # Calculate cost based on size
                    cost = Decimal(str(size_gb)) * self.PRICING['volume_per_gb']

                    orphaned.append(ResourceItem(
                        id=volume_id,
                        name=name or volume_id,
                        type=ResourceType.VOLUME,
                        status=CleanupStatus.UNATTACHED,
                        cost_per_month=cost,
                        region=region,
                        is_authorized=False,
                        metadata={
                            'size_gb': size_gb,
                            'volume_type': volume_type,
                            'create_time': volume['CreateTime'].isoformat() if 'CreateTime' in volume else None
                        },
                        discovered_at=datetime.utcnow()
                    ))

            except ClientError as e:
                logger.warning(f"Failed to scan volumes in region {region}: {str(e)}")
                continue

        return orphaned

    def _scan_zombie_snapshots(
        self,
        credentials: Dict[str, str],
        regions: List[str]
    ) -> List[ResourceItem]:
        """
        Scan all regions for snapshots whose source volumes no longer exist

        Args:
            credentials: AWS credentials
            regions: List of regions to scan

        Returns:
            List of zombie snapshot ResourceItems
        """
        zombies = []

        for region in regions:
            try:
                ec2 = self._get_aws_client(credentials, 'ec2', region)

                # Get all snapshots owned by this account
                response = ec2.describe_snapshots(OwnerIds=['self'])

                # Get all existing volume IDs in this region
                volumes_response = ec2.describe_volumes()
                existing_volume_ids = {vol['VolumeId'] for vol in volumes_response['Volumes']}

                for snapshot in response['Snapshots']:
                    snapshot_id = snapshot['SnapshotId']
                    volume_id = snapshot.get('VolumeId')

                    # Check if source volume still exists
                    if volume_id and volume_id not in existing_volume_ids:
                        size_gb = snapshot['VolumeSize']

                        # Extract name from tags
                        name = None
                        for tag in snapshot.get('Tags', []):
                            if tag['Key'] == 'Name':
                                name = tag['Value']
                                break

                        # Calculate cost based on size
                        cost = Decimal(str(size_gb)) * self.PRICING['snapshot_per_gb']

                        zombies.append(ResourceItem(
                            id=snapshot_id,
                            name=name or snapshot_id,
                            type=ResourceType.SNAPSHOT,
                            status=CleanupStatus.ORPHANED,
                            cost_per_month=cost,
                            region=region,
                            is_authorized=False,
                            metadata={
                                'size_gb': size_gb,
                                'state': snapshot['State'],
                                'start_time': snapshot['StartTime'].isoformat() if 'StartTime' in snapshot else None,
                                'source_volume_id': volume_id
                            },
                            discovered_at=datetime.utcnow()
                        ))

            except ClientError as e:
                logger.warning(f"Failed to scan snapshots in region {region}: {str(e)}")
                continue

        return zombies

    def _scan_unused_elastic_ips(
        self,
        credentials: Dict[str, str],
        regions: List[str]
    ) -> List[ResourceItem]:
        """
        Scan all regions for Elastic IPs not associated with any instance

        Args:
            credentials: AWS credentials
            regions: List of regions to scan

        Returns:
            List of unused Elastic IP ResourceItems
        """
        unused = []

        for region in regions:
            try:
                ec2 = self._get_aws_client(credentials, 'ec2', region)

                # Get all Elastic IPs
                response = ec2.describe_addresses()

                for address in response['Addresses']:
                    # Check if the IP is not associated with any instance
                    if 'AssociationId' not in address:
                        allocation_id = address.get('AllocationId', 'unknown')
                        public_ip = address.get('PublicIp', 'unknown')

                        # Extract name from tags
                        name = None
                        for tag in address.get('Tags', []):
                            if tag['Key'] == 'Name':
                                name = tag['Value']
                                break

                        unused.append(ResourceItem(
                            id=allocation_id,
                            name=name or public_ip,
                            type=ResourceType.ELASTIC_IP,
                            status=CleanupStatus.UNATTACHED,
                            cost_per_month=self.PRICING['elastic_ip'],
                            region=region,
                            is_authorized=False,
                            metadata={
                                'public_ip': public_ip,
                                'domain': address.get('Domain', 'vpc')
                            },
                            discovered_at=datetime.utcnow()
                        ))

            except ClientError as e:
                logger.warning(f"Failed to scan Elastic IPs in region {region}: {str(e)}")
                continue

        return unused

    def scan_resources(self, account_id: str, user_id: str) -> CleanupSummary:
        """
        Scan AWS account across ALL regions for orphaned resources

        Args:
            account_id: Account UUID to scan
            user_id: User performing the scan

        Returns:
            CleanupSummary with all orphaned resources and potential savings

        Raises:
            ResourceNotFoundError: If account not found or user doesn't have access
            ValidationError: If account credentials are invalid
        """
        # Verify account exists and user has access
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)

        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == user.organization_id
        ).first()

        if not account:
            raise ResourceNotFoundError("Account", account_id)

        logger.info(f"Starting multi-region cleanup scan for account {account_id}")

        # Get AWS credentials
        credentials = self._get_aws_credentials(account)

        # Get all enabled regions
        regions = self._get_enabled_regions(credentials)
        logger.info(f"Scanning {len(regions)} regions: {', '.join(regions)}")

        # Get managed instance IDs from database
        managed_instance_ids = self._get_managed_instance_ids(account_id)

        # Scan each resource type across all regions
        instances = self._scan_unauthorized_instances(credentials, regions, managed_instance_ids)
        volumes = self._scan_orphaned_volumes(credentials, regions)
        snapshots = self._scan_zombie_snapshots(credentials, regions)
        elastic_ips = self._scan_unused_elastic_ips(credentials, regions)

        # Calculate total savings potential
        total_savings = sum(
            item.cost_per_month
            for items in [instances, volumes, snapshots, elastic_ips]
            for item in items
        )

        logger.info(
            f"Cleanup scan completed for account {account_id}: "
            f"{len(instances)} instances, {len(volumes)} volumes, "
            f"{len(snapshots)} snapshots, {len(elastic_ips)} IPs, "
            f"${float(total_savings):.2f} potential savings"
        )

        return CleanupSummary(
            account_id=account_id,
            account_name=account.aws_account_id,
            total_savings_potential=total_savings,
            unauthorized_instances_count=len(instances),
            orphaned_volumes_count=len(volumes),
            zombie_snapshots_count=len(snapshots),
            unused_ips_count=len(elastic_ips),
            scanned_regions=regions,
            instances=instances,
            volumes=volumes,
            snapshots=snapshots,
            elastic_ips=elastic_ips,
            scanned_at=datetime.utcnow()
        )

    def execute_action(
        self,
        action: CleanupAction,
        account_id: str,
        user_id: str
    ) -> CleanupActionResponse:
        """
        Execute cleanup action on selected resources

        Args:
            action: CleanupAction with resource IDs and action type
            account_id: Account UUID
            user_id: User performing the action

        Returns:
            CleanupActionResponse with results

        Raises:
            ResourceNotFoundError: If account not found or user doesn't have access
            ValidationError: If action or parameters are invalid
        """
        # Verify account exists and user has access
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ResourceNotFoundError("User", user_id)

        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == user.organization_id
        ).first()

        if not account:
            raise ResourceNotFoundError("Account", account_id)

        logger.info(
            f"Executing cleanup action: {action.action_type} on "
            f"{len(action.resource_ids)} {action.resource_type}(s) "
            f"for account {account_id}"
        )

        # Get AWS credentials
        credentials = self._get_aws_credentials(account)

        affected_resources = []
        failed_resources = []
        errors = []

        # Execute action based on type
        for resource_id in action.resource_ids:
            try:
                if action.action_type == ActionType.AUTHORIZE:
                    # For now, we just track this as successful
                    # In production, you'd update a database table tracking authorized resources
                    affected_resources.append(resource_id)
                    logger.info(f"Authorized resource {resource_id}")

                elif action.action_type == ActionType.TERMINATE:
                    if action.resource_type != ResourceType.INSTANCE:
                        raise ValidationError("TERMINATE action only valid for instances")
                    # Extract region from resource ID or use all regions
                    # For simplicity, try common regions
                    success = False
                    for region in self._get_enabled_regions(credentials):
                        try:
                            ec2 = self._get_aws_client(credentials, 'ec2', region)
                            ec2.terminate_instances(InstanceIds=[resource_id])
                            affected_resources.append(resource_id)
                            success = True
                            logger.info(f"Terminated instance {resource_id} in {region}")
                            break
                        except ClientError:
                            continue
                    if not success:
                        failed_resources.append(resource_id)
                        errors.append(f"Instance {resource_id} not found in any region")

                elif action.action_type == ActionType.DELETE:
                    if action.resource_type == ResourceType.VOLUME:
                        success = False
                        for region in self._get_enabled_regions(credentials):
                            try:
                                ec2 = self._get_aws_client(credentials, 'ec2', region)
                                ec2.delete_volume(VolumeId=resource_id)
                                affected_resources.append(resource_id)
                                success = True
                                logger.info(f"Deleted volume {resource_id} in {region}")
                                break
                            except ClientError:
                                continue
                        if not success:
                            failed_resources.append(resource_id)
                            errors.append(f"Volume {resource_id} not found in any region")

                    elif action.resource_type == ResourceType.SNAPSHOT:
                        success = False
                        for region in self._get_enabled_regions(credentials):
                            try:
                                ec2 = self._get_aws_client(credentials, 'ec2', region)
                                ec2.delete_snapshot(SnapshotId=resource_id)
                                affected_resources.append(resource_id)
                                success = True
                                logger.info(f"Deleted snapshot {resource_id} in {region}")
                                break
                            except ClientError:
                                continue
                        if not success:
                            failed_resources.append(resource_id)
                            errors.append(f"Snapshot {resource_id} not found in any region")
                    else:
                        raise ValidationError(f"DELETE action not valid for {action.resource_type}")

                elif action.action_type == ActionType.RELEASE:
                    if action.resource_type != ResourceType.ELASTIC_IP:
                        raise ValidationError("RELEASE action only valid for Elastic IPs")
                    success = False
                    for region in self._get_enabled_regions(credentials):
                        try:
                            ec2 = self._get_aws_client(credentials, 'ec2', region)
                            ec2.release_address(AllocationId=resource_id)
                            affected_resources.append(resource_id)
                            success = True
                            logger.info(f"Released Elastic IP {resource_id} in {region}")
                            break
                        except ClientError:
                            continue
                    if not success:
                        failed_resources.append(resource_id)
                        errors.append(f"Elastic IP {resource_id} not found in any region")
                else:
                    raise ValidationError(f"Unknown action type: {action.action_type}")

            except Exception as e:
                failed_resources.append(resource_id)
                errors.append(f"{resource_id}: {str(e)}")
                logger.error(f"Failed to execute action on {resource_id}: {str(e)}")

        success = len(failed_resources) == 0

        logger.info(
            f"Cleanup action completed: {len(affected_resources)} succeeded, "
            f"{len(failed_resources)} failed"
        )

        return CleanupActionResponse(
            success=success,
            affected_resources=affected_resources,
            failed_resources=failed_resources,
            errors=errors,
            executed_at=datetime.utcnow()
        )


def get_cleanup_service(db: Session) -> CleanupService:
    """Dependency injection for CleanupService"""
    return CleanupService(db)
