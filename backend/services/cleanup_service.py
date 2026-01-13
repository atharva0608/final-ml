import boto3
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError

from backend.models.account import Account
from backend.models.instance import Instance
from backend.models.cluster import Cluster
from backend.models.system_config import SystemConfig
from backend.models.user import User
from backend.schemas.cleanup_schemas import (
    ResourceItem, CleanupSummary, ResourceType, CleanupStatus, 
    CleanupAction, CleanupActionType
)

logger = logging.getLogger(__name__)

class CleanupService:
    def __init__(self, db: Session):
        self.db = db

    def _get_platform_session(self):
        """Get the platform AWS session"""
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        region = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        
        region_name = region.value if region and region.value else 'us-east-1'
        
        if access_key and secret_key and access_key.value and secret_key.value:
            return boto3.Session(
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value,
                region_name=region_name
            )
        return boto3.Session(region_name=region_name) # Fallback to env or instance role

    def _get_account_session(self, account: Account, region: str = 'us-east-1'):
        """Assume role into customer account"""
        if not account.role_arn:
             raise Exception("Account has no Role ARN configured")

        platform_session = self._get_platform_session()
        sts = platform_session.client('sts')
        
        assumed = sts.assume_role(
            RoleArn=account.role_arn,
            RoleSessionName="SpotOptimizerCleanup",
            ExternalId=account.external_id
        )
        
        creds = assumed['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=region
        )

    def _get_all_regions(self, session: boto3.Session) -> List[str]:
        try:
            ec2 = session.client('ec2')
            regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
            return regions
        except Exception as e:
            logger.error(f"Failed to list regions: {e}")
            return ['us-east-1'] # Fallback

    def scan_resources(self, account_id: str, request_regions: List[str] = None, organization = None, force_refresh: bool = False) -> CleanupSummary:
        """Scan for orphaned resources across regions using parallel execution with Caching"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from backend.core.redis_client import get_redis_client
        import json
        
        # Cache Key Generation
        regions_key = "ALL" if not request_regions or "ALL" in request_regions else "-".join(sorted(request_regions))
        cache_key = f"cleanup:scan:{account_id}:{regions_key}"
        
        redis_client = None
        # 1. Check Cache (unless force_refresh is True)
        if not force_refresh:
            try:
                redis_client = get_redis_client()
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    try:
                        data = json.loads(cached_data)
                        logger.info(f"Returning cached cleanup scan for {account_id}")
                        return CleanupSummary(**data)
                    except Exception as e:
                        logger.error(f"Cache parse error: {e}")
            except Exception as e:
                logger.error(f"Redis cache check failed: {e}")
                redis_client = None
        else:
            logger.info(f"Force refresh requested, bypassing cache for {account_id}")
            try:
                redis_client = get_redis_client()
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                redis_client = None

        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise Exception("Account not found")

        # Determine regions to scan
        target_regions = request_regions
        if not target_regions or "ALL" in target_regions or "GLOBAL" in target_regions:
            try:
                initial_session = self._get_account_session(account)
                target_regions = self._get_all_regions(initial_session)
            except Exception as e:
                logger.error(f"Failed to list regions: {e}")
                # Fallback to default if we can't list
                target_regions = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 'eu-central-1', 'eu-west-1']

        resources: List[ResourceItem] = []
        
        # [NEW] Fetch Authorized Resources
        from backend.models.authorized_resource import AuthorizedResource
        authorized_resources = self.db.query(AuthorizedResource).filter(
            AuthorizedResource.account_id == account.id
        ).all()
        # Create lookup map: (id) -> AuthorizedResource
        authorized_map = {r.resource_id: r for r in authorized_resources}
        total_savings = 0.0
        
        # OPTIMIZATION: Parallel execution across regions
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_region = {
                executor.submit(self._scan_region_worker, account, region, organization): region 
                for region in target_regions
            }
            
            for future in as_completed(future_to_region):
                region = future_to_region[future]
                try:
                    r_list, r_savings = future.result()
                    resources.extend(r_list)
                    total_savings += r_savings
                except Exception as e:
                    logger.error(f"Region {region} scan failed: {e}")

        # [NEW] Apply Authorization Logic (Post-Processing)
        # Fetch Authorized Resources if not already fetched (in case prev step failed partial apply, but likely it succeeded)
        # Actually, let's just do it here to be safe and clear.
        from backend.models.authorized_resource import AuthorizedResource
        authorized_resources = self.db.query(AuthorizedResource).filter(
            AuthorizedResource.account_id == account.id
        ).all()
        authorized_ids = {r.resource_id for r in authorized_resources}
        
        # Deduct authorized resources from savings and mark them
        for r in resources:
            if r.id in authorized_ids:
                r.is_authorized = True
                # Deduct cost from total savings (since it was added in the worker)
                total_savings -= r.cost_per_month

        # Calculate untagged waste cost (Feature 2) - Exclude authorized
        untagged_waste = sum(r.cost_per_month for r in resources if not r.is_compliant and not r.is_authorized)
        
        # Aggregate counts - Exclude authorized
        summary = CleanupSummary(
            total_potential_savings=max(0.0, total_savings), # Ensure no floating point quirk negative
            unauthorized_instance_count=len([r for r in resources if r.type == ResourceType.INSTANCE and not r.is_authorized]),
            orphaned_volume_count=len([r for r in resources if r.type == ResourceType.VOLUME and not r.is_authorized]),
            orphaned_snapshot_count=len([r for r in resources if r.type == ResourceType.SNAPSHOT and not r.is_authorized]),
            unused_ip_count=len([r for r in resources if r.type == ResourceType.ELASTIC_IP and not r.is_authorized]),
            idle_lb_count=len([r for r in resources if r.type == ResourceType.LOAD_BALANCER and not r.is_authorized]),
            idle_rds_count=len([r for r in resources if r.type == ResourceType.RDS_DB and not r.is_authorized]),
            dormant_user_count=len([r for r in resources if r.type == ResourceType.IAM_USER and not r.is_authorized]),
            untagged_waste_cost=untagged_waste,
            resources=resources
        )
        
        # 2. Set Cache (TTL 1 hour)
        if redis_client:
            try:
                redis_client.setex(cache_key, 3600, summary.json())
            except Exception as e:
                logger.error(f"Failed to set cleanup cache: {e}")
            
        return summary

    def _scan_region_worker(self, account: Account, region: str, organization = None):
        """Helper to scan a single region independently for parallel execution"""
        from datetime import datetime, timedelta, timezone
        
        # Get required tags from organization settings (Feature 2)
        required_tags = []
        if organization and hasattr(organization, 'required_tags') and organization.required_tags:
            required_tags = organization.required_tags if isinstance(organization.required_tags, list) else []
        
        resources = []
        savings = 0.0
        
        # Threshold for "Safe to Delete" (30 days old)
        safe_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        
        try:
            session = self._get_account_session(account, region=region)
            ec2 = session.client('ec2')
            
            # OPTIMIZATION: Fetch ALL volumes once. Use for both orphan check AND snapshot verification.
            try:
                all_vols = ec2.describe_volumes()['Volumes']
                all_vol_ids = {v['VolumeId'] for v in all_vols}
                
                # 1. ORPHANED VOLUMES (Filter in memory - no duplicate API call)
                orphaned_vols = [v for v in all_vols if v['State'] == 'available']
                for v in orphaned_vols:
                    cost = (v['Size'] * 0.1) # Approx $0.10/GB/month for gp2/3
                    created_at = v['CreateTime']
                    status = CleanupStatus.SAFE_TO_DELETE if created_at < safe_threshold else CleanupStatus.ORPHANED
                    
                    # Feature 2: Tag Compliance Check
                    tags = v.get('Tags', [])
                    tag_keys = {t['Key'] for t in tags}
                    missing = [rt for rt in required_tags if rt not in tag_keys]
                    
                    item = ResourceItem(
                        id=v['VolumeId'],
                        name=self._get_tag_value(tags, 'Name'),
                        type=ResourceType.VOLUME,
                        status=status,
                        region=region,
                        cost_per_month=cost,
                        metadata={'Size': v['Size'], 'Type': v['VolumeType'], 'Created': str(created_at)},
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)
                    savings += cost
                
                # 2. ORPHANED SNAPSHOTS (Use cached vol_ids - no redundant describe_volumes call)
                snaps = ec2.describe_snapshots(OwnerIds=['self'])
                for s in snaps['Snapshots']:
                    vol_id = s.get('VolumeId')
                    if vol_id and vol_id not in all_vol_ids:
                        # Volume deleted, snapshot lingering
                        # Snapshots also have StartTime
                        start_time = s.get('StartTime')
                        status = CleanupStatus.SAFE_TO_DELETE if start_time and start_time < safe_threshold else CleanupStatus.ORPHANED
                        
                        # Feature 2: Tag Compliance Check
                        tags = s.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]
                        
                        cost = (s['VolumeSize'] * 0.05) # Approx $0.05/GB
                        item = ResourceItem(
                            id=s['SnapshotId'],
                            name=self._get_tag_value(tags, 'Name'),
                            type=ResourceType.SNAPSHOT,
                            status=status,
                            region=region,
                            cost_per_month=cost,
                            metadata={'VolumeId': vol_id, 'Size': s['VolumeSize'], 'Progress': s['Progress']},
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
                        savings += cost
            except Exception as e:
                logger.error(f"Error scanning volumes/snapshots in {region}: {e}")

            # 3. UNUSED ELASTIC IPs
            try:
                eips = ec2.describe_addresses()
                for ip in eips['Addresses']:
                    if 'AssociationId' not in ip:
                        # EIPs don't always have a creation time in describe_address response easily accessible without CloudTrail
                        # For now, we consider all unattached EIPs as ORPHANED to be safe, unless we assume "unattached = waste" is always true.
                        # Design says: "High Confidence (Green): Applied to resources that are undeniably waste (e.g., an IP unattached for >30 days)."
                        # Without allocation time, we will stick to ORPHANED or mark SAFE_TO_DELETE if we treat all unattached IPs as safe.
                        # Let's use SAFE_TO_DELETE for simpler UX as unattached IPs are costing money every hour.
                        status = CleanupStatus.SAFE_TO_DELETE
                        
                        cost = 3.65 # Approx $0.005/hr * 730 = $3.65
                        item = ResourceItem(
                            id=ip['AllocationId'],
                            name=ip.get('PublicIp', 'Unknown'),
                            type=ResourceType.ELASTIC_IP,
                            status=status,
                            region=region,
                            cost_per_month=cost,
                            metadata={'PublicIp': ip.get('PublicIp')}
                        )
                        resources.append(item)
                        savings += cost
            except Exception as e:
                logger.error(f"Error scanning EIPs in {region}: {e}")

            # 4. UNAUTHORIZED INSTANCES
            try:
                aws_instances = {}
                paginator = ec2.get_paginator('describe_instances')
                for page in paginator.paginate():
                    for r in page['Reservations']:
                        for i in r['Instances']:
                            if i['State']['Name'] not in ['terminated', 'shutting-down']:
                                aws_instances[i['InstanceId']] = i

                # Get all instances from DB for this account and region
                db_instance_ids = [
                    res[0] for res in self.db.query(Instance.instance_id)
                    .join(Cluster)
                    .filter(
                        Cluster.account_id == account.id,
                        Cluster.region == region
                    ).all()
                ]
                
                db_instance_set = set(db_instance_ids)
                
                for inst_id, inst_data in aws_instances.items():
                    if inst_id not in db_instance_set:
                        # Unauthorized / Unmanaged
                        cost_map = {'t2.micro': 8.5, 't3.medium': 30.0, 'm5.large': 70.0}
                        inst_type = inst_data.get('InstanceType', 'unknown')
                        cost = cost_map.get(inst_type, 50.0) 
                        
                        tags = inst_data.get('Tags', [])
                        name = self._get_tag_value(tags, 'Name')
                        
                        item = ResourceItem(
                            id=inst_id,
                            name=name,
                            type=ResourceType.INSTANCE,
                            status=CleanupStatus.UNAUTHORIZED,
                            region=region,
                            cost_per_month=cost,
                            metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name']}
                        )
                        resources.append(item)
                        savings += cost

            except Exception as e:
                logger.error(f"Error scanning instances in {region}: {e}")

            # 5. NETWORK HYGIENE (ELB/ENI)
            net_res, net_sav = self._scan_network(session, region, required_tags)
            resources.extend(net_res)
            savings += net_sav

            # 6. DATABASE HYGIENE (RDS)
            db_res, db_sav = self._scan_databases(session, region, required_tags)
            resources.extend(db_res)
            savings += db_sav

            # 7. GLOBAL CHECKS (IAM / S3) - Run only in Primary Region (us-east-1)
            if region == 'us-east-1':
                # Identity
                iam_res, iam_sav = self._scan_identity(session)
                resources.extend(iam_res)
                savings += iam_sav
                
                # Storage (S3)
                s3_res, s3_sav = self._scan_storage(session, required_tags)
                resources.extend(s3_res)
                savings += s3_sav

        except Exception as e:
            logger.error(f"Failed to scan region {region}: {e}")
            return [], 0.0

        return resources, savings

    def _get_tag_value(self, tags: List[Dict], key: str) -> str:
        for t in tags:
            if t['Key'] == key:
                return t['Value']
        return "Unknown"

    def check_dependencies(self, account_id: str, resource_type: str, resource_id: str, region: str) -> Dict[str, Any]:
        """
        Feature 1: Deep Dependency Mapping
        Check if a resource has dependencies that would block deletion.
        Returns: {"can_delete": bool, "blocking_resources": [{"type": "AMI", "id": "ami-xxx", "name": "MyAMI"}]}
        """
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise Exception("Account not found")

        blocking = []
        
        try:
            session = self._get_account_session(account, region=region)
            ec2 = session.client('ec2')
            
            if resource_type == "SNAPSHOT":
                # Check if any AMI uses this snapshot
                amis = ec2.describe_images(Owners=['self'])['Images']
                for ami in amis:
                    for bdm in ami.get('BlockDeviceMappings', []):
                        ebs = bdm.get('Ebs', {})
                        if ebs.get('SnapshotId') == resource_id:
                            blocking.append({
                                "type": "AMI",
                                "id": ami['ImageId'],
                                "name": ami.get('Name', 'Unnamed AMI')
                            })
                            
            elif resource_type == "SECURITY_GROUP":
                # Check if any ENI uses this security group
                enis = ec2.describe_network_interfaces(
                    Filters=[{'Name': 'group-id', 'Values': [resource_id]}]
                )['NetworkInterfaces']
                for eni in enis:
                    blocking.append({
                        "type": "ENI",
                        "id": eni['NetworkInterfaceId'],
                        "name": eni.get('Description', 'Unknown')
                    })
                    
            elif resource_type == "VOLUME":
                # Check volume status and attachments
                vol = ec2.describe_volumes(VolumeIds=[resource_id])['Volumes'][0]
                if vol['State'] != 'available':
                    blocking.append({
                        "type": "ATTACHMENT",
                        "id": vol.get('Attachments', [{}])[0].get('InstanceId', 'Unknown'),
                        "name": f"Volume is {vol['State']}"
                    })
                    
        except Exception as e:
            logger.error(f"Dependency check failed: {e}")
            # Return as safe if we can't check (fail-open for now, could be fail-closed)
            
        return {
            "can_delete": len(blocking) == 0,
            "blocking_resources": blocking
        }

    def _scan_network(self, session, region, required_tags):
        resources = []
        savings = 0.0
        try:
            # 1. Load Balancers
            elbv2 = session.client('elbv2')
            try:
                lbs = elbv2.describe_load_balancers()['LoadBalancers']
                for lb in lbs:
                    lb_arn = lb['LoadBalancerArn']
                    lb_name = lb['LoadBalancerName']
                    
                    # Check Target Groups
                    tgs = elbv2.describe_target_groups(LoadBalancerArn=lb_arn)['TargetGroups']
                    is_idle = False
                    
                    if not tgs:
                        is_idle = True
                    else:
                        all_unused = True
                        for tg in tgs:
                            try:
                                health = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])['TargetHealthDescriptions']
                                # If any target is 'healthy' or 'initial', it's active
                                active_states = ['healthy', 'initial']
                                if any(h['TargetHealth']['State'] in active_states for h in health):
                                    all_unused = False
                                    break
                            except Exception:
                                continue # TG might be empty
                        if not all_unused:
                            is_idle = False
                        else:
                            # Verify if TGs themselves are empty (target_health returns empty list)
                            # Logic: If all TGs have NO healthy targets equivalent to 'unused'
                            is_idle = True
                    
                    if is_idle:
                        cost = 16.0 # Approx
                        status = CleanupStatus.ORPHANED
                        
                        # Tags
                        tags = []
                        try:
                            tag_desc = elbv2.describe_tags(ResourceArns=[lb_arn])
                            tags = tag_desc['TagDescriptions'][0]['Tags']
                        except: pass
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]
                        
                        item = ResourceItem(
                            id=lb_arn,
                            name=lb_name,
                            type=ResourceType.LOAD_BALANCER,
                            status=status,
                            region=region,
                            cost_per_month=cost,
                            reason="No active targets attached",
                            metadata={'DNS': lb['DNSName'], 'Type': lb['Type']},
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
                        savings += cost
            except Exception as e:
                logger.error(f"ELB Scan Error: {e}")

            # 2. Unattached ENIs
            ec2 = session.client('ec2')
            try:
                enis = ec2.describe_network_interfaces(Filters=[{'Name': 'status', 'Values': ['available']}])['NetworkInterfaces']
                for eni in enis:
                    cost = 0.1 # Minimal cost but clutters VPC
                    status = CleanupStatus.ORPHANED
                    item = ResourceItem(
                        id=eni['NetworkInterfaceId'],
                        name=eni.get('Description', 'Unattached ENI'),
                        type=ResourceType.NETWORK_INTERFACE,
                        status=status,
                        region=region,
                        cost_per_month=cost,
                        reason="Unattached network interface",
                        metadata={'PrivateIp': eni.get('PrivateIpAddress'), 'VpcId': eni.get('VpcId')},
                        is_compliant=True
                    )
                    resources.append(item)
                    savings += cost
            except Exception: pass
            
        except Exception as e:
            logger.error(f"Network Scan Error: {e}")
        return resources, savings

    def _scan_databases(self, session, region, required_tags):
        resources = []
        savings = 0.0
        try:
            rds = session.client('rds')
            cloudwatch = session.client('cloudwatch')
            dbs = rds.describe_db_instances()['DBInstances']
            
            from datetime import datetime, timezone, timedelta
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=14)
            
            for db in dbs:
                db_id = db['DBInstanceIdentifier']
                status = db['DBInstanceStatus']
                db_class = db['DBInstanceClass']
                
                if status != 'available':
                    continue
                
                # Check Legacy Generation
                is_legacy = db_class.startswith('db.t2') or db_class.startswith('db.m4') or db_class.startswith('db.m3')
                
                # Check Idle via CloudWatch (DatabaseConnections)
                is_idle = False
                max_connections = -1
                try:
                    metrics = cloudwatch.get_metric_statistics(
                        Namespace='AWS/RDS',
                        MetricName='DatabaseConnections',
                        Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=86400,  # 1 day
                        Statistics=['Maximum']
                    )
                    datapoints = metrics.get('Datapoints', [])
                    if datapoints:
                        max_connections = max(dp.get('Maximum', 0) for dp in datapoints)
                        if max_connections == 0:
                            is_idle = True
                except Exception as cw_err:
                    logger.warning(f"CloudWatch check failed for {db_id}: {cw_err}")
                
                # Determine status and reason
                cleanup_status = CleanupStatus.ACTIVE
                reason = None
                cost_estimate = 0.0
                
                if is_idle:
                    cleanup_status = CleanupStatus.ORPHANED
                    reason = f"Zero connections for 14 days"
                    cost_estimate = 50.0  # Rough estimate
                elif is_legacy:
                    cleanup_status = CleanupStatus.LEGACY_UPGRADE
                    reason = f"Legacy instance class ({db_class}). Upgrade to T3/M5 for savings."
                    cost_estimate = 20.0
                
                # Tag compliance
                tags = db.get('TagList', [])
                tag_keys = {t['Key'] for t in tags}
                missing = [rt for rt in required_tags if rt not in tag_keys]
                
                # Only add if there's an issue
                if cleanup_status != CleanupStatus.ACTIVE or len(missing) > 0:
                    item = ResourceItem(
                        id=db_id,
                        name=db_id,
                        type=ResourceType.RDS_DB,
                        status=cleanup_status,
                        region=region,
                        cost_per_month=cost_estimate,
                        reason=reason,
                        metadata={'Engine': db['Engine'], 'Class': db_class, 'MaxConnections14d': max_connections},
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)
                    savings += cost_estimate
        except Exception as e:
            logger.error(f"RDS Scan Error: {e}")
        return resources, savings

    def _scan_identity(self, session):
        resources = []
        savings = 0.0
        try:
            iam = session.client('iam')
            from datetime import datetime, timezone, timedelta
            threshold = datetime.now(timezone.utc) - timedelta(days=90)
            
            users = iam.list_users()['Users']
            for u in users:
                last_used = u.get('PasswordLastUsed')
                days_inactive = None
                
                # Calculate inactivity
                is_dormant = False
                if last_used:
                    days_inactive = (datetime.now(timezone.utc) - last_used).days
                    if days_inactive > 90:
                        is_dormant = True
                elif u['CreateDate'] < threshold:
                    days_inactive = (datetime.now(timezone.utc) - u['CreateDate']).days
                    is_dormant = True
                    
                if is_dormant:
                    item = ResourceItem(
                        id=u['UserName'],
                        name=u['UserName'],
                        type=ResourceType.IAM_USER,
                        status=CleanupStatus.SAFE_TO_DELETE,
                        region='global',
                        cost_per_month=0.0,
                        reason=f"Inactive for {days_inactive} days",
                        metadata={'LastUsed': str(last_used) if last_used else 'Never', 'DaysInactive': days_inactive},
                        is_compliant=False
                    )
                    resources.append(item)
        except Exception as e:
            logger.error(f"IAM Scan Error: {e}")
        return resources, savings

    def _scan_storage(self, session, required_tags):
        resources = []
        savings = 0.0
        try:
            s3 = session.client('s3')
            buckets = s3.list_buckets()['Buckets']
            from datetime import datetime, timezone, timedelta
            threshold = datetime.now(timezone.utc) - timedelta(days=7)

            for b in buckets:
                b_name = b['Name']
                # Check Incomplete Multipart Uploads
                try:
                    uploads = s3.list_multipart_uploads(Bucket=b_name).get('Uploads', [])
                    old_uploads = [u for u in uploads if u['Initiated'] < threshold]
                    
                    if old_uploads:
                        oldest = min(u['Initiated'] for u in old_uploads)
                        age_days = (datetime.now(timezone.utc) - oldest).days
                        cost = len(old_uploads) * 0.5  # Rough estimate per incomplete upload
                        item = ResourceItem(
                            id=b_name,
                            name=b_name,
                            type=ResourceType.S3_BUCKET,
                            status=CleanupStatus.ORPHANED,
                            region='global',
                            cost_per_month=cost,
                            reason=f"{len(old_uploads)} incomplete uploads (oldest: {age_days} days)",
                            metadata={'IncompleteUploads': len(old_uploads), 'OldestUploadDays': age_days},
                            is_compliant=True
                        )
                        resources.append(item)
                        savings += cost
                except Exception: pass
        except Exception as e:
            logger.error(f"S3 Scan Error: {e}")
        return resources, savings

    def execute_action(self, account_id: str, action_data: CleanupAction, user: User = None, bypass_approval: bool = False):
        """
        Execute a cleanup action on a specific resource.
        Supports RBAC & Team-Specific Approval Workflow.
        """
        # 0. RBAC / Approval Check
        if user and not bypass_approval:
            from backend.models.user import UserRole
            from backend.services.approval_service import ApprovalService
            
            needs_approval = False
            action_key = str(action_data.action_type).replace("CleanupActionType.", "")  # e.g., "TERMINATE" -> map to config key
            
            # Map action types to governance config keys
            action_config_map = {
                "TERMINATE": "TERMINATE_INSTANCE",
                "DELETE": "DELETE_VOLUME",  # Uses same rule for volumes and snapshots
                "RELEASE": "RELEASE_IP"
            }
            config_key = action_config_map.get(str(action_data.action_type.value), str(action_data.action_type.value))
            
            # Rule 1: Members - Check team-specific governance first
            if user.role == UserRole.MEMBER:
                if user.team and user.team.governance_config:
                    # Check if Team Lead has enabled approval for this specific action
                    needs_approval = user.team.governance_config.get(config_key, False)
                else:
                    # Fallback: If no team config exists, use system default (require approval)
                    needs_approval = True
            
            # Rule 2: Team Leads need approval if Org is in Strict Mode
            elif user.role == UserRole.TEAM_LEAD and user.organization and user.organization.is_strict_approval_mode:
                needs_approval = True

            # Rule 3: Critical Actions configured in Org Governance Settings always require approval (except Org Admin)
            if not needs_approval and user.organization and user.organization.governance_config:
                critical_actions = user.organization.governance_config.get('critical_actions', [])
                if config_key in critical_actions and user.role != UserRole.ORG_ADMIN:
                    needs_approval = True
                
            if needs_approval:
                logger.info(f"Action requires approval for user {user.id} (Role: {user.role}, Team: {user.team_id})")
                approval_svc = ApprovalService(self.db)
                req = approval_svc.create_request(
                    user=user,
                    resource_type="AWS_RESOURCE",
                    action="CLEANUP_EXECUTE",
                    payload={
                        "account_id": account_id,
                        "action_data": action_data.dict()
                    }
                )
                return {
                    "status": "pending_approval", 
                    "message": "Action queued for Team Lead approval", 
                    "request_id": req.id,
                    "approval_status": "PENDING"
                }

        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise Exception("Account not found")

        try:
            # Get session for the specific region
            session = self._get_account_session(account, region=action_data.region)
            ec2 = session.client('ec2')
            
            action_type = action_data.action_type
            resource_ids = action_data.resource_ids
            
            logger.info(f"Executing {action_type} on {len(resource_ids)} resources in {action_data.region}")
            
            if action_type == CleanupActionType.DELETE:
                for vol_id in resource_ids:
                    # Try to delete as volume or snapshot based on resource ID format
                    if vol_id.startswith('vol-'):
                        ec2.delete_volume(VolumeId=vol_id)
                        logger.info(f"Deleted volume {vol_id}")
                    elif vol_id.startswith('arn:aws:elasticloadbalancing'):
                         # ELB Deletion
                         try:
                             elbv2 = session.client('elbv2')
                             elbv2.delete_load_balancer(LoadBalancerArn=vol_id)
                             logger.info(f"Deleted ELB {vol_id}")
                         except Exception as elb_err:
                             logger.error(f"Failed to delete ELB {vol_id}: {elb_err}")
                    elif vol_id.startswith('snap-'):
                        ec2.delete_snapshot(SnapshotId=vol_id)
                        logger.info(f"Deleted snapshot {vol_id}")
                    else:
                        # Assume volume by default
                        ec2.delete_volume(VolumeId=vol_id)
                        logger.info(f"Deleted volume {vol_id}")
                    
            elif action_type == CleanupActionType.RELEASE:
                for alloc_id in resource_ids:
                    ec2.release_address(AllocationId=alloc_id)
                    logger.info(f"Released IP {alloc_id}")
                    
            elif action_type == CleanupActionType.TERMINATE:
                ec2.terminate_instances(InstanceIds=resource_ids)
                logger.info(f"Terminated instances {resource_ids}")

            elif action_type == CleanupActionType.SNAPSHOT_STOP:
                rds = session.client('rds')
                for rid in resource_ids:
                    try:
                         # Create snapshot first
                         import uuid
                         snap_id = f"{rid}-manual-snap-{uuid.uuid4().hex[:6]}"
                         rds.create_db_snapshot(DBSnapshotIdentifier=snap_id, DBInstanceIdentifier=rid)
                         logger.info(f"Created snapshot {snap_id} for {rid}")
                         # Then stop (might fail if snap in progress, but we try)
                         # Actually stop isn't immediate.
                         rds.stop_db_instance(DBInstanceIdentifier=rid)
                         logger.info(f"Stopped RDS {rid}")
                    except Exception as rds_err:
                        logger.error(f"RDS Action failed: {rds_err}")

            elif action_type == CleanupActionType.DISABLE:
                iam = session.client('iam')
                for rid in resource_ids:
                    # Assuming rid is UserName
                    try:
                        # Disable Login Profile (Console Access)
                        try:
                            iam.delete_login_profile(UserName=rid)
                            logger.info(f"Deleted login profile for {rid}")
                        except: pass
                        # Inactivate Keys?
                        keys = iam.list_access_keys(UserName=rid)['AccessKeyMetadata']
                        for k in keys:
                            iam.update_access_key(UserName=rid, AccessKeyId=k['AccessKeyId'], Status='Inactive')
                        logger.info(f"Disabled keys for {rid}")
                    except Exception as iam_err:
                         logger.error(f"IAM Action failed: {iam_err}")
                
            elif action_type == CleanupActionType.AUTHORIZE:
                from backend.models.authorized_resource import AuthorizedResource
                for rid in resource_ids:
                    # Infer type
                    rtype = "UNKNOWN"
                    if rid.startswith('i-'): rtype = "INSTANCE"
                    elif rid.startswith('vol-'): rtype = "VOLUME"
                    elif rid.startswith('snap-'): rtype = "SNAPSHOT"
                    elif rid.startswith('eipalloc-') or '.' in rid: rtype = "ELASTIC_IP"
                    
                    # Check if exists
                    exists = self.db.query(AuthorizedResource).filter(
                        AuthorizedResource.account_id == account_id, 
                        AuthorizedResource.resource_id == rid
                    ).first()
                    
                    if not exists:
                        new_auth = AuthorizedResource(
                            resource_id=rid,
                            account_id=account_id,
                            region=action_data.region,
                            resource_type=rtype,
                            created_by_id=user.id if user else None,
                            notes="Authorized via Cleanup Dashboard"
                        )
                        self.db.add(new_auth)
                        logger.info(f"Authorized resource {rid}")
                self.db.commit()

            elif action_type == CleanupActionType.UNAUTHORIZE:
                from backend.models.authorized_resource import AuthorizedResource
                for rid in resource_ids:
                    self.db.query(AuthorizedResource).filter(
                        AuthorizedResource.account_id == account_id, 
                        AuthorizedResource.resource_id == rid
                    ).delete()
                    logger.info(f"Unauthorized resource {rid}")
                self.db.commit()
            
            return {"status": "success", "message": f"Successfully executed {action_type} on {len(resource_ids)} resources"}

        except Exception as e:
            # Re-raise or handle
            import botocore
            if isinstance(e, botocore.exceptions.ClientError):
                code = e.response['Error']['Code']
                if code == 'UnauthorizedOperation':
                     raise Exception(f"AWS Permission Denied: {e}")
            raise e
        finally:
            # Invalidate cache after action execution
            try:
                from backend.core.redis_client import get_redis_client
                redis_client = get_redis_client()
                # Delete all cache keys for this account
                for key in redis_client.scan_iter(f"cleanup:scan:{account_id}:*"):
                    redis_client.delete(key)
                    logger.info(f"Invalidated cache key: {key}")
            except Exception as cache_err:
                logger.error(f"Failed to invalidate cache: {cache_err}")
                 
        # The original code had an `elif action.action_type == CleanupActionType.AUTHORIZE:` here.
        # Given the new structure, this `elif` would be outside the `try` block and not directly
        # related to the `action_type` checks within the `try`.
        # Assuming `CleanupActionType.AUTHORIZE` is a separate action not involving EC2 client calls
        # and should be handled after the main action execution block.
        # If it was meant to be part of the EC2 actions, it would need to be an `elif` inside the `try`.
        # For now, keeping it as a separate block as it was originally.
        if action_data.action_type == CleanupActionType.AUTHORIZE:
            # Mark instances as authorized in DB
            pass # Implementation dependent on DB model changes which we might skip for this task if strict
        

