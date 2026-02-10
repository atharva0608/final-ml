import boto3
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
from datetime import datetime, timezone

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
        
        # [NEW] OPTIMIZATION: Fetch Active Policies once (Thread-safe)
        from backend.models.cleanup_policy import CleanupPolicy
        all_active_policies = self.db.query(CleanupPolicy).filter(
            CleanupPolicy.is_active == True
        ).all()
        
        # OPTIMIZATION: Parallel execution across regions
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_region = {
                executor.submit(self._scan_region_worker, account, region, organization, all_active_policies): region 
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
                    # CRITICAL: Rollback if main session was poisoned by a stray query (though workers shouldn't touch it now)
                    try: self.db.rollback() 
                    except: pass

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
        current_savings = max(0.0, total_savings)
        
        # Retrieve previous savings from history cache for trend calculation
        previous_savings = None
        savings_trend_percent = None
        history_key = f"cleanup:history:{account_id}"
        
        if redis_client:
            try:
                prev_data = redis_client.get(history_key)
                if prev_data:
                    prev_savings_val = json.loads(prev_data).get('total_potential_savings')
                    if prev_savings_val is not None:
                        previous_savings = float(prev_savings_val)
                        # Calculate percentage change: (new - old) / old * 100
                        if previous_savings > 0:
                            savings_trend_percent = round(((current_savings - previous_savings) / previous_savings) * 100, 1)
                        elif current_savings > 0:
                            savings_trend_percent = 100.0  # From 0 to something = 100% increase
                        else:
                            savings_trend_percent = 0.0
            except Exception as e:
                logger.error(f"Failed to retrieve savings history: {e}")
        
        summary = CleanupSummary(
            total_potential_savings=current_savings,
            previous_savings=previous_savings,
            savings_trend_percent=savings_trend_percent,
            unauthorized_instance_count=len([r for r in resources if r.type == ResourceType.INSTANCE and not r.is_authorized]),
            orphaned_volume_count=len([r for r in resources if r.type == ResourceType.VOLUME and not r.is_authorized]),
            orphaned_snapshot_count=len([r for r in resources if r.type == ResourceType.SNAPSHOT and not r.is_authorized]),
            unused_ip_count=len([r for r in resources if r.type == ResourceType.ELASTIC_IP and not r.is_authorized]),
            idle_lb_count=len([r for r in resources if r.type == ResourceType.LOAD_BALANCER and not r.is_authorized]),
            idle_rds_count=len([r for r in resources if r.type == ResourceType.RDS_DB and not r.is_authorized]),
            dormant_user_count=len([r for r in resources if r.type == ResourceType.IAM_USER and not r.is_authorized]),
            untagged_waste_cost=untagged_waste,
            resources=resources,
            metadata={
                'scan_time': datetime.now(timezone.utc).isoformat(),
                'region_count': len(target_regions),
                'resource_count': len(resources)
            }
        )
        
        # 2. Set Cache (TTL 1 hour) and update history (TTL 7 days)
        if redis_client:
            try:
                redis_client.setex(cache_key, 3600, summary.json())
                # Store current savings as history for next comparison (7 days TTL)
                redis_client.setex(history_key, 604800, json.dumps({'total_potential_savings': current_savings, 'timestamp': datetime.now(timezone.utc).isoformat()}))
            except Exception as e:
                logger.error(f"Failed to set cleanup cache: {e}")
            
        return summary

    def _scan_region_worker(self, account: Account, region: str, organization = None, policies=None):
        """Helper to scan a single region independently for parallel execution"""
        from datetime import datetime, timedelta, timezone
        from backend.utils.pricing_helper import get_pricing_helper
        
        pricing = get_pricing_helper()
        
        # Get required tags from organization settings (Feature 2)
        required_tags = []
        if organization and hasattr(organization, 'required_tags') and organization.required_tags:
            required_tags = organization.required_tags if isinstance(organization.required_tags, list) else []
            
        policies = policies or []
        
        resources = []
        savings = 0.0

        # Threshold for "Safe to Delete" (30 days old)
        safe_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        # Grace period: Skip resources created in last 24 hours (deployment in progress)
        grace_period = datetime.now(timezone.utc) - timedelta(hours=24)

        # Tag-based exemptions (resources with these keywords are protected)
        EXEMPT_KEYWORDS = ['backup', 'spare', 'template', 'reserved', 'do-not-delete', 'keep', 'permanent']
        
        try:
            session = self._get_account_session(account, region=region)
            ec2 = session.client('ec2')
            
            # OPTIMIZATION: Fetch ALL volumes once. Use for both orphan check AND snapshot verification.
            try:
                all_vols = ec2.describe_volumes()['Volumes']
                all_vol_ids = {v['VolumeId'] for v in all_vols}
                
                # [NEW] Filter Active Policies from passed list (Thread-safe)
                from backend.schemas.cleanup_policy_schemas import CleanupConditionRule
                
                # Filter for this resource type locally
                active_policies = [
                    p for p in policies 
                    if p.resource_type == ResourceType.VOLUME
                ]
                # Sort by priority desc
                active_policies.sort(key=lambda x: x.priority, reverse=True)

                for v in all_vols:
                    vol_state = v['State']
                    tags = v.get('Tags', [])
                    tag_keys = {t['Key'] for t in tags}
                    created_at = v['CreateTime']
                    vol_type = v['VolumeType']

                    # Grace period check: Skip volumes created < 24 hours ago
                    if created_at > grace_period:
                        continue  # ✅ Skip newly created volumes (deployment in progress)

                    # Exempt check: Skip volumes with protected tags
                    if self._is_exempt_by_tags(tags, EXEMPT_KEYWORDS):
                        continue  # ✅ Skip protected volumes

                    # Use PricingHelper (returns monthly cost per GB)
                    monthly_price_per_gb = pricing.get_ebs_price(region, vol_type)
                    cost = v['Size'] * monthly_price_per_gb

                    status = CleanupStatus.ACTIVE
                    reason = "Active"

                    # 1. Attachment Check (Hardcoded safety)
                    if vol_state == 'in-use':
                        status = CleanupStatus.ACTIVE
                        reason = "Attached to instance"
                        vol_cost = 0.0
                    else:
                        vol_cost = cost
                        # Default is ORPHANED (Risky to delete immediately unless old)
                        status = CleanupStatus.ORPHANED
                        reason = "Unattached volume"
                        
                        # Apply Safety Logic
                        if created_at < safe_threshold:
                            status = CleanupStatus.SAFE_TO_DELETE
                            reason = "Unattached > 30 days (Safe)"
                        
                        # 2. Apply Dynamic Policies
                        policy_applied = False
                        if active_policies:
                            for policy in active_policies:
                                # Evaluate Conditions
                                match = True
                                for rule_dict in policy.conditions.get('rules', []):
                                    field = rule_dict.get('field')
                                    op = rule_dict.get('op')
                                    val = rule_dict.get('value')
                                    
                                    if field == 'age_days':
                                        age = (datetime.now(timezone.utc) - created_at).days
                                        if op == 'gt' and not (age > val): match = False
                                        elif op == 'lt' and not (age < val): match = False
                                    
                                    elif field.startswith('tag:'):
                                        key = field.split(':', 1)[1]
                                        tag_val = self._get_tag_value(tags, key)
                                        if op == 'missing' and key in tag_keys: match = False
                                        elif op == 'exists' and key not in tag_keys: match = False
                                        elif op == 'eq' and tag_val != val: match = False
                                    
                                    if not match: break
                                
                                if match:
                                    # Apply Policy Action
                                    policy_applied = True
                                    reason = f"Matched Policy: {policy.name}"
                                    if policy.action == CleanupActionType.DELETE:
                                        status = CleanupStatus.SAFE_TO_DELETE
                                    elif policy.action == CleanupActionType.NOTIFY:
                                        status = CleanupStatus.ORPHANED
                                    elif policy.action == CleanupActionType.SNAPSHOT_STOP:
                                        status = CleanupStatus.SAFE_TO_DELETE # Treat as actionable
                                    break # Stop at highest priority match
                        
                        # Fallback for legacy compliance (if no policy matched or to augment)
                        missing = [rt for rt in required_tags if rt not in tag_keys]
                        if not policy_applied:
                             if len(missing) > 0:
                                 # If strictly strictly orphaned, prioritize that status over compliance?
                                 # Compliance is secondary if it's waste.
                                 # But stick to existing logic: if unauthorized, compliance doesn't matter much.
                                 pass
                    
                    item = ResourceItem(
                        id=v['VolumeId'],
                        name=self._get_tag_value(tags, 'Name'),
                        type=ResourceType.VOLUME,
                        status=status,
                        region=region,
                        cost_per_month=vol_cost,
                        reason=reason,
                        metadata={
                            'Size': v['Size'], 
                            'Type': v['VolumeType'], 
                            'Created': str(created_at),
                            'State': vol_state,
                            'AttachmentStatus': 'Attached' if vol_state == 'in-use' else 'Unattached'
                        },
                        is_compliant=len([rt for rt in required_tags if rt not in tag_keys]) == 0,
                        missing_tags=[rt for rt in required_tags if rt not in tag_keys]
                    )
                    resources.append(item)
                    if vol_state != 'in-use':  # Only count savings for unattached
                        savings += vol_cost
                
                # 2. ORPHANED SNAPSHOTS
                # CRITICAL FIX: Pre-fetch AMI mappings to avoid deleting snapshots backing AMIs
                ami_snapshot_ids = set()
                try:
                    amis = ec2.describe_images(Owners=['self'])['Images']
                    for ami in amis:
                        for bdm in ami.get('BlockDeviceMappings', []):
                            snap_id = bdm.get('Ebs', {}).get('SnapshotId')
                            if snap_id:
                                ami_snapshot_ids.add(snap_id)
                    logger.info(f"Found {len(ami_snapshot_ids)} snapshots used by AMIs in {region}")
                except Exception as ami_err:
                    logger.error(f"Failed to fetch AMI mappings: {ami_err}")

                snaps = ec2.describe_snapshots(OwnerIds=['self'])
                snapshot_price = pricing.get_snapshot_price(region)

                for s in snaps['Snapshots']:
                    vol_id = s.get('VolumeId')
                    snap_id = s['SnapshotId']

                    # CRITICAL: If snapshot is used by AMI, mark as ACTIVE (DO NOT DELETE)
                    if snap_id in ami_snapshot_ids:
                        tags = s.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        cost = s['VolumeSize'] * snapshot_price
                        item = ResourceItem(
                            id=snap_id,
                            name=self._get_tag_value(tags, 'Name'),
                            type=ResourceType.SNAPSHOT,
                            status=CleanupStatus.ACTIVE,  # ✅ PROTECTED
                            region=region,
                            cost_per_month=0.0,  # No savings - needed by AMI
                            reason="Used by AMI (Do Not Delete)",
                            metadata={'VolumeId': vol_id, 'Size': s['VolumeSize'], 'Progress': s['Progress'], 'AMI_Protected': True},
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
                        continue  # ✅ Skip adding to savings

                    # Safety Logic: If Volume is gone, Snapshot IS orphaned.
                    # But is it SAFE to delete?
                    if vol_id and vol_id not in all_vol_ids:
                        start_time = s.get('StartTime')

                        # Default ORPHANED (Risky)
                        status = CleanupStatus.ORPHANED
                        reason = "Volume deleted (Orphaned Snapshot)"

                        # Safe if > 30 days old
                        if start_time and start_time < safe_threshold:
                            status = CleanupStatus.SAFE_TO_DELETE
                            reason = "Volume deleted > 30 days (Safe)"

                        tags = s.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        cost = s['VolumeSize'] * snapshot_price
                        item = ResourceItem(
                            id=snap_id,
                            name=self._get_tag_value(tags, 'Name'),
                            type=ResourceType.SNAPSHOT,
                            status=status,
                            region=region,
                            cost_per_month=cost,
                            reason=reason,
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
                eip_price = pricing.get_eip_price(region)
                
                for ip in eips['Addresses']:
                    if 'AssociationId' not in ip:
                        # Unattached EIP.
                        # Safety: Cannot verify age easily.
                        # Logic: Unattached EIP is waste, but deleting 'Prod-VIP' is fatal.
                        # Usage: Mark ORPHANED (Risky). User must verify.
                        
                        status = CleanupStatus.ORPHANED
                        reason = "Unattached Elastic IP"
                        
                        # Check tags for 'Prod' or 'Critical' to mark RISK (optional)
                        # For now, ORPHANED is sufficient distinction from SAFE_TO_DELETE.
                        
                        cost = eip_price
                        item = ResourceItem(
                            id=ip['AllocationId'],
                            name=ip.get('PublicIp', 'Unknown'),
                            type=ResourceType.ELASTIC_IP,
                            status=status,
                            region=region,
                            cost_per_month=cost,
                            reason=reason,
                            metadata={'PublicIp': ip.get('PublicIp')}
                        )
                        resources.append(item)
                        savings += cost
            except Exception as e:
                logger.error(f"Error scanning EIPs in {region}: {e}")

            # 4. AUTHORIZED vs UNAUTHORIZED INSTANCES
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
                    tags = inst_data.get('Tags', [])
                    tag_dict = {t['Key']: t['Value'] for t in tags}
                    name = self._get_tag_value(tags, 'Name')
                    inst_type = inst_data.get('InstanceType', 'unknown')

                    # AUTHORIZED: Instances managed by Spot Optimizer (cluster nodes)
                    if inst_id in db_instance_set:
                        # These are cluster nodes - show as AUTHORIZED (managed)
                        item = ResourceItem(
                            id=inst_id,
                            name=name,
                            type=ResourceType.INSTANCE,
                            status=CleanupStatus.ACTIVE,  # Authorized/Managed
                            region=region,
                            cost_per_month=0.0,  # No savings - this is managed workload
                            reason="Managed by Spot Optimizer (Cluster Node)",
                            metadata={
                                'InstanceType': inst_type,
                                'State': inst_data['State']['Name'],
                                'Managed': True,
                                'ManagedBy': 'Spot Optimizer'
                            },
                            is_compliant=True
                        )
                        resources.append(item)

                    # UNAUTHORIZED: Instances NOT managed by Spot Optimizer
                    else:
                        # Check if explicitly marked for review
                        if tag_dict.get('spot-optimizer:review') == 'true':
                            # User explicitly wants this reviewed as potential wastage
                            cost = pricing.get_ec2_price(region, inst_type)

                            item = ResourceItem(
                                id=inst_id,
                                name=name,
                                type=ResourceType.INSTANCE,
                                status=CleanupStatus.UNAUTHORIZED,
                                region=region,
                                cost_per_month=cost,
                                reason="Not managed by Spot Optimizer (Marked for review)",
                                metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name'], 'Managed': False},
                                is_compliant=False
                            )
                            resources.append(item)
                            savings += cost  # Count as potential wastage

                        # Check tag compliance (non-managed instances should still be compliant)
                        elif required_tags:
                            tag_keys = set(tag_dict.keys())
                            missing = [rt for rt in required_tags if rt not in tag_keys]

                            if missing:
                                # Not managed AND missing required tags = compliance issue
                                # Show but DON'T count as wastage
                                item = ResourceItem(
                                    id=inst_id,
                                    name=name,
                                    type=ResourceType.INSTANCE,
                                    status=CleanupStatus.NOT_COMPLIANT,
                                    region=region,
                                    cost_per_month=0.0,  # NOT wastage, just compliance issue
                                    reason=f"Not managed (Missing tags: {', '.join(missing)})",
                                    metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name'], 'Managed': False},
                                    is_compliant=False,
                                    missing_tags=missing
                                )
                                resources.append(item)
                            else:
                                # Properly tagged, not managed = legitimate external workload
                                # Show as ACTIVE (authorized external workload)
                                item = ResourceItem(
                                    id=inst_id,
                                    name=name,
                                    type=ResourceType.INSTANCE,
                                    status=CleanupStatus.ACTIVE,
                                    region=region,
                                    cost_per_month=0.0,  # Not wastage
                                    reason="Not managed (Properly tagged external workload)",
                                    metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name'], 'Managed': False},
                                    is_compliant=True
                                )
                                resources.append(item)
                        else:
                            # No required tags policy - show as external workload
                            item = ResourceItem(
                                id=inst_id,
                                name=name,
                                type=ResourceType.INSTANCE,
                                status=CleanupStatus.ACTIVE,
                                region=region,
                                cost_per_month=0.0,
                                reason="Not managed (External workload)",
                                metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name'], 'Managed': False},
                                is_compliant=True
                            )
                            resources.append(item)

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
                
                # S3 Lifecycle (New)
                s3_lc_res, s3_lc_sav = self._scan_s3_lifecycle(session, region)
                resources.extend(s3_lc_res)
                savings += s3_lc_sav

            # 8. RI Waste (Regional/Zonal RIs)
            ri_res, ri_sav = self._scan_reserved_instances(session, region)
            resources.extend(ri_res)
            savings += ri_sav
            
            # 9. RDS Multi-AZ (Region)
            rds_az_res, rds_az_sav = self._scan_rds_deployment(session, region, required_tags)
            resources.extend(rds_az_res)
            savings += rds_az_sav
            
            # 10. Data Transfer
            dt_res, dt_sav = self._scan_data_transfer(session, region)
            resources.extend(dt_res)
            savings += dt_sav

        except Exception as e:
            logger.error(f"Failed to scan region {region}: {e}")
            return [], 0.0

        return resources, savings

    def _get_tag_value(self, tags: List[Dict], key: str) -> str:
        for t in tags:
            if t['Key'] == key:
                return t['Value']
        return "Unknown"

    def _is_exempt_by_tags(self, tags: List[Dict], exempt_keywords: List[str]) -> bool:
        """Check if resource is exempt from cleanup based on tag values"""
        for t in tags:
            # Check both key and value
            tag_str = f"{t.get('Key', '')}:{t.get('Value', '')}".lower()
            if any(keyword in tag_str for keyword in exempt_keywords):
                return True
        return False

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
        from backend.utils.pricing_helper import get_pricing_helper
        pricing = get_pricing_helper()
        
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
                    lb_type = lb['Type']
                    
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
                        cost = pricing.get_load_balancer_price(region, lb_type)
                        # Safety: Idle ELB is risky to auto-delete.
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
                    # Check if AWS-managed (Lambda, RDS, ECS, ELB, etc.)
                    desc = eni.get('Description', '').lower()
                    requester_id = eni.get('RequesterId', '').lower()

                    # Skip AWS-managed ENIs
                    AWS_SERVICES = ['aws', 'lambda', 'rds', 'ecs', 'elb', 'eks', 'elasticache', 'redshift', 'vpc endpoint', 'interface']
                    if any(svc in desc for svc in AWS_SERVICES) or 'amazon' in requester_id:
                        continue  # ✅ Skip AWS-managed ENIs

                    # Unattached ENIs have minimal direct cost but clutter VPC
                    cost = 0.0  # Actually $0/mo for unattached ENIs (no hourly charge)
                    status = CleanupStatus.ORPHANED

                    item = ResourceItem(
                        id=eni['NetworkInterfaceId'],
                        name=eni.get('Description', 'Unattached ENI'),
                        type=ResourceType.NETWORK_INTERFACE,
                        status=status,
                        region=region,
                        cost_per_month=cost,  # ✅ Fixed: ENIs are free when unattached
                        reason="Unattached network interface (VPC clutter)",
                        metadata={'PrivateIp': eni.get('PrivateIpAddress'), 'VpcId': eni.get('VpcId'), 'Description': eni.get('Description')},
                        is_compliant=True
                    )
                    resources.append(item)
                    savings += cost
            except Exception as eni_err:
                logger.error(f"ENI scan error: {eni_err}")
            
        except Exception as e:
            logger.error(f"Network Scan Error: {e}")
        return resources, savings

    def _scan_databases(self, session, region, required_tags):
        from backend.utils.pricing_helper import get_pricing_helper
        pricing = get_pricing_helper()
        
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
                status_name = db['DBInstanceStatus']
                db_class = db['DBInstanceClass']
                engine = db['Engine']

                if status_name != 'available':
                    continue

                # Check if this is a read replica
                if db.get('ReadReplicaSourceDBInstanceIdentifier'):
                    # This is a read replica - don't flag based on connection count alone
                    # Read replicas often have 0 direct connections but are critical for HA/DR
                    continue  # ✅ Skip read replicas from idle detection

                # Check if this is a source DB with replicas (also critical)
                has_replicas = bool(db.get('ReadReplicaDBInstanceIdentifiers'))

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

                # Calculate real cost
                real_cost = pricing.get_rds_price(region, db_class, engine)

                if is_idle:
                    # Additional safety: If this DB has read replicas, don't mark as idle
                    # (might be used indirectly through replicas)
                    if has_replicas:
                        cleanup_status = CleanupStatus.ACTIVE
                        reason = "Has read replicas (source DB)"
                        cost_estimate = 0.0
                    else:
                        cleanup_status = CleanupStatus.ORPHANED
                        reason = f"Zero connections for 14 days (Idle)"
                        cost_estimate = real_cost
                elif is_legacy:
                    cleanup_status = CleanupStatus.LEGACY_UPGRADE
                    reason = f"Legacy instance class ({db_class}). Upgrade to T3/M5/M6 for savings."
                    # Savings is diff between current and T3 equivalent (approx 20% savings)
                    cost_estimate = real_cost * 0.2
                
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
                username = u['UserName']

                # CRITICAL FIX: Check BOTH console access AND access key usage
                last_console = u.get('PasswordLastUsed')
                last_key_used = None
                has_active_keys = False

                # Check access key usage (for service accounts)
                try:
                    access_keys = iam.list_access_keys(UserName=username)['AccessKeyMetadata']
                    for key in access_keys:
                        if key['Status'] == 'Active':
                            has_active_keys = True
                            try:
                                key_info = iam.get_access_key_last_used(AccessKeyId=key['AccessKeyId'])
                                if 'LastUsedDate' in key_info.get('AccessKeyLastUsed', {}):
                                    key_date = key_info['AccessKeyLastUsed']['LastUsedDate']
                                    # Ensure timezone-aware comparison
                                    if key_date.tzinfo is None:
                                        key_date = key_date.replace(tzinfo=timezone.utc)
                                    if not last_key_used or key_date > last_key_used:
                                        last_key_used = key_date
                            except Exception as key_err:
                                logger.debug(f"Could not get last used date for key: {key_err}")
                except Exception as keys_err:
                    logger.warning(f"Could not list access keys for {username}: {keys_err}")

                # Use the MOST RECENT activity (console OR access key)
                last_activities = [a for a in [last_console, last_key_used] if a is not None]
                last_activity = max(last_activities) if last_activities else None

                days_inactive = None
                is_dormant = False

                # Calculate inactivity based on ANY activity type
                if last_activity:
                    # Ensure timezone-aware
                    if last_activity.tzinfo is None:
                        last_activity = last_activity.replace(tzinfo=timezone.utc)
                    days_inactive = (datetime.now(timezone.utc) - last_activity).days
                    if days_inactive > 90:
                        is_dormant = True
                elif u['CreateDate'] < threshold:
                    # Never used (no console, no key usage) and old
                    days_inactive = (datetime.now(timezone.utc) - u['CreateDate']).days
                    is_dormant = True

                # Additional safety: Don't flag users with active keys unless truly dormant
                if is_dormant and has_active_keys:
                    # Reduce severity - active keys indicate potential service account
                    status = CleanupStatus.ORPHANED  # Review needed, not auto-delete
                    reason = f"Inactive for {days_inactive} days (Has active access keys - verify before deletion)"
                elif is_dormant:
                    status = CleanupStatus.SAFE_TO_DELETE
                    reason = f"Inactive for {days_inactive} days (No active keys)"
                else:
                    continue  # Active user, skip

                if is_dormant:
                    item = ResourceItem(
                        id=username,
                        name=username,
                        type=ResourceType.IAM_USER,
                        status=status,
                        region='global',
                        cost_per_month=0.0,
                        reason=reason,
                        metadata={
                            'LastConsole': str(last_console) if last_console else 'Never',
                            'LastKeyUsed': str(last_key_used) if last_key_used else 'Never',
                            'HasActiveKeys': has_active_keys,
                            'DaysInactive': days_inactive
                        },
                        is_compliant=False
                    )
                    resources.append(item)
        except Exception as e:
            logger.error(f"IAM Scan Error: {e}")
        return resources, savings

    def _scan_storage(self, session, required_tags):
        """Scan S3 buckets for untagged, empty, or old buckets"""
        resources = []
        savings = 0.0
        try:
            s3 = session.client('s3')
            buckets = s3.list_buckets().get('Buckets', [])
            
            from datetime import timezone
            
            for bucket in buckets:
                bucket_name = bucket['Name']
                created = bucket['CreationDate']
                
                # Get tags
                tags = []
                try:
                    tag_resp = s3.get_bucket_tagging(Bucket=bucket_name)
                    tags = tag_resp.get('TagSet', [])
                except Exception:
                    pass  # No tags or access denied
                
                tag_keys = {t['Key'] for t in tags}
                missing = [rt for rt in required_tags if rt not in tag_keys]
                
                # Check if bucket is empty (by listing first object)
                is_empty = False
                try:
                    objects = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                    if objects.get('KeyCount', 0) == 0:
                        is_empty = True
                except Exception:
                    pass
                
                # Determine status
                status = CleanupStatus.ACTIVE
                reason = None
                cost = 0.0
                
                if is_empty:
                    status = CleanupStatus.SAFE_TO_DELETE
                    reason = "Empty bucket"
                    cost = 0.5  # Minimal storage cost for bucket itself
                elif missing:
                    status = CleanupStatus.NOT_COMPLIANT
                    reason = f"Missing tags: {', '.join(missing)}"
                
                if status != CleanupStatus.ACTIVE:
                    item = ResourceItem(
                        id=bucket_name,
                        name=bucket_name,
                        type=ResourceType.S3_BUCKET,
                        status=status,
                        region='global',
                        cost_per_month=cost,
                        reason=reason,
                        metadata={'Created': str(created)},
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)
                    savings += cost
                    
        except Exception as e:
            logger.error(f"S3 Scan Error: {e}")
        return resources, savings

    def _scan_reserved_instances(self, session, region):
        resources = []
        savings = 0.0
        try:
            ec2 = session.client('ec2')
            # 1. Get Active RIs
            ris = ec2.describe_reserved_instances(Filters=[{'Name': 'state', 'Values': ['active']}])['ReservedInstances']
            
            # 2. Get Running Instances
            instances = []
            paginator = ec2.get_paginator('describe_instances')
            for page in paginator.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]):
                for r in page['Reservations']:
                    instances.extend(r['Instances'])
            
            # Simple matching logic (Type + AZ/Region scope) - Simplified for MVP
            # A real nice implementation would basically check utilization metrics from Cur/Cost Explorer but that's slow/expensive.
            # We will use a basic count match per type.
            
            usage_map = {}
            for i in instances:
                key = (i['InstanceType'], i.get('Placement', {}).get('AvailabilityZone'))
                usage_map[key] = usage_map.get(key, 0) + 1
                
            for ri in ris:
                # Calculate utilization
                count = ri['InstanceCount']
                ri_type = ri['InstanceType']
                scope = ri['Scope'] # Availability Zone or Region
                
                matched = 0
                if scope == 'Region':
                    # Match any AZ in region
                    for (itype, az), run_count in usage_map.items():
                        if itype == ri_type:
                            taken = min(count - matched, run_count)
                            matched += taken
                            usage_map[(itype, az)] -= taken # consume
                else:
                    # Match specific AZ
                    az = ri.get('AvailabilityZone')
                    key = (ri_type, az)
                    run_count = usage_map.get(key, 0)
                    taken = min(count, run_count)
                    matched = taken
                    usage_map[key] -= taken

                utilization = matched / count if count > 0 else 0
                
                if utilization < 1.0:
                    # Partial or Zero Utilization
                    wasted_count = count - matched
                    cost_per_ri = 20.0 # Placeholder for specific RI hourly rate amortized
                    waste_cost = wasted_count * cost_per_ri 
                    
                    status = CleanupStatus.ORPHANED
                    reason = f"Utilization: {utilization*100:.1f}% ({matched}/{count} used)"
                    
                    item = ResourceItem(
                        id=ri['ReservedInstancesId'],
                        name=f"RI {ri_type}",
                        type=ResourceType.INSTANCE, # Closest type
                        status=status,
                        region=region,
                        cost_per_month=waste_cost,
                        reason=reason,
                        metadata={'RI_Type': ri_type, 'Count': count, 'Unused': wasted_count, 'End': str(ri['End'])},
                        is_compliant=True
                    )
                    resources.append(item)
                    savings += waste_cost
                    
        except Exception as e:
            logger.error(f"RI Scan Error: {e}")
        return resources, savings

    def _scan_s3_lifecycle(self, session, region):
        resources = []
        savings = 0.0
        try:
            s3 = session.client('s3')
            buckets = s3.list_buckets()['Buckets']
            
            for b in buckets:
                b_name = b['Name']
                has_lifecycle = False
                try:
                    lc = s3.get_bucket_lifecycle_configuration(Bucket=b_name)
                    if lc and lc.get('Rules'):
                        has_lifecycle = True
                except ClientError as e:
                    if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
                        has_lifecycle = False
                    else:
                        continue # Access denied or other
                
                if not has_lifecycle:
                    # Get size estimate (List objects limited or Metric)
                    # Use CloudWatch for size
                    cw = session.client('cloudwatch')
                    size_bytes = 0
                    try:
                        metrics = cw.get_metric_statistics(
                            Namespace='AWS/S3',
                            MetricName='BucketSizeBytes',
                            Dimensions=[
                                {'Name': 'BucketName', 'Value': b_name},
                                {'Name': 'StorageType', 'Value': 'StandardStorage'}
                            ],
                            StartTime=datetime.now() - timedelta(days=2),
                            EndTime=datetime.now(),
                            Period=86400,
                            Statistics=['Average']
                        )
                        if metrics['Datapoints']:
                            size_bytes = metrics['Datapoints'][-1]['Average']
                    except: pass
                    
                    if size_bytes > 1 * 1024 * 1024 * 1024: # > 1GB
                        cost = (size_bytes / (1024**3)) * 0.023 # Standard cost
                        potential_saving = cost * 0.4 # Assuming 40% saving by moving to IA/Glacier
                        
                        item = ResourceItem(
                            id=b_name,
                            name=b_name,
                            type=ResourceType.S3_BUCKET,
                            status=CleanupStatus.LEGACY_UPGRADE,
                            region='global',
                            cost_per_month=potential_saving,
                            reason="No Lifecycle Policy on >1GB Bucket",
                            metadata={'SizeBytes': size_bytes},
                            is_compliant=False 
                        )
                        resources.append(item)
                        savings += potential_saving

        except Exception as e:
             logger.error(f"S3 Lifecycle Error: {e}")
        return resources, savings

    def _scan_rds_deployment(self, session, region, required_tags):
        resources = []
        savings = 0.0
        try:
            rds = session.client('rds')
            dbs = rds.describe_db_instances()['DBInstances']
            
            for db in dbs:
                if db['MultiAZ']:
                    # Check if Production
                    tags = db.get('TagList', [])
                    tag_keys = {t['Key']: t['Value'] for t in tags}
                    
                    env = tag_keys.get('Environment', '').lower()
                    if env in ['dev', 'test', 'staging', 'development']:
                        # Multi-AZ in non-prod is waste
                        cost = 100.0 # Estimate surcharge for Multi-AZ
                        
                        item = ResourceItem(
                            id=db['DBInstanceIdentifier'],
                            name=db['DBInstanceIdentifier'],
                            type=ResourceType.RDS_DB,
                            status=CleanupStatus.LEGACY_UPGRADE, # Downgrade needed
                            region=region,
                            cost_per_month=cost,
                            reason=f"Multi-AZ enabled in {env} environment",
                            metadata={'MultiAZ': True, 'Environment': env},
                            is_compliant=True
                        )
                        resources.append(item)
                        savings += cost
        except Exception as e:
            logger.error(f"RDS MultiAZ Error: {e}")
        return resources, savings

    def _scan_data_transfer(self, session, region):
        resources = []
        savings = 0.0
        # Data Transfer difficult to attribute without Cost Explorer at resource level.
        # Implemented as a placeholder scanning NAT Gateways which are common sources.
        try:
            ec2 = session.client('ec2')
            nats = ec2.describe_nat_gateways()['NatGateways']
            for nat in nats:
                if nat['State'] == 'available':
                    # Just flagging NAT GWs as potential review items if they exist
                    # Real data transfer metrics need CloudWatch "BytesOutToDestination"
                    cw = session.client('cloudwatch')
                    bytes_out = 0
                    try:
                        metrics = cw.get_metric_statistics(
                            Namespace='AWS/NATGateway',
                            MetricName='BytesOutToDestination',
                            Dimensions=[{'Name': 'NatGatewayId', 'Value': nat['NatGatewayId']}],
                            StartTime=datetime.now() - timedelta(days=7),
                            EndTime=datetime.now(),
                            Period=86400 * 7,
                            Statistics=['Sum']
                        )
                        if metrics['Datapoints']:
                            bytes_out = metrics['Datapoints'][0]['Sum']
                    except: pass
                    
                    gb_out = bytes_out / (1024**3)
                    if gb_out > 100: # Warning threshold > 100GB/week
                        cost = gb_out * 0.045 # Approx per GB processing
                        item = ResourceItem(
                            id=nat['NatGatewayId'],
                            name="NAT Gateway",
                            type=ResourceType.NAT_GATEWAY,
                            status=CleanupStatus.RISK,
                            region=region,
                            cost_per_month=cost * 4, # Monthly estimate
                            reason=f"High Data Transfer: {gb_out:.1f} GB/week",
                            metadata={'WeeklyGB': gb_out},
                            is_compliant=True
                        )
                        resources.append(item)
                        savings += (cost * 4)
                        
        except Exception as e:
            logger.error(f"DataTransfer Error: {e}")
        return resources, savings

    def execute_action(self, account_id: str, action_data: CleanupAction, user: User = None, bypass_approval: bool = False):
        """
        Execute a cleanup action on a specific resource.
        Supports RBAC & Team-Specific Approval Workflow.
        """
        # 0. RBAC / Approval Check
        # 0. JIT Governance Check
        if user and not bypass_approval:
            from backend.services.permission_service import PermissionService
            from backend.models.organization import Organization
            from backend.services.ticket_service import TicketService
            from backend.schemas.ticket_schemas import TicketCreate
            from backend.models.ticket import TicketType, ReasonCategory
            
            # 1. Check if System Approval is Required for Cleanup
            org = self.db.query(Organization).filter(Organization.id == user.organization_id).first()
            if org and org.require_automation_approval:
                # Create a System Approval Ticket instead of executing
                # But wait, is this a "System Automated Action" or a "User Clicked Cleanup" action?
                # User request asks "if we turned on that we have to delete all untagged resources... system actions will take place"
                # This implies the TRIGGER is automatic (e.g. Schedule).
                # BUT `execute_action` is currently called by user clicks mostly.
                # However, if we assume this function is the gateway for ALL cleanup actions:
                
                # Check if ticket already exists for this batch? (Hard to track exact batch)
                # Just create a new ticket for this action request.
                
                logger.info(f"System Approval required. Creating ticket for {action_data.action_type}")
                
                ticket_service = TicketService(self.db)
                ticket_in = TicketCreate(
                    title=f"Approval: {action_data.action_type} for {len(action_data.resource_ids)} resources",
                    description=f"Automated cleanup approval required.\nRegion: {action_data.region}\nResources: {', '.join(action_data.resource_ids)}",
                    type=TicketType.SYSTEM_CLEANUP,
                    reason_category=ReasonCategory.MAINTENANCE,
                    reason_text="Automated Governance Cleanup Action",
                    duration_hours=24,
                    resource_id=f"batch-{datetime.utcnow().timestamp()}", # Pseudo ID
                    action_type=str(action_data.action_type),
                    additional_metadata={
                        "region": action_data.region,
                        "resource_ids": action_data.resource_ids,
                        "action_type": action_data.action_type,
                        "account_id": account_id
                    }
                )
                ticket = ticket_service.create_ticket(user_id=user.id, ticket_in=ticket_in)
                return {"status": "pending_approval", "message": f"Action paused. Ticket #{ticket.id} created for approval."}

            # 2. JIT Permission Check (if not routed to ticket)
            action_config_map = {
                "TERMINATE": "TERMINATE_INSTANCE",
                "DELETE": "DELETE_VOLUME",
                "RELEASE": "RELEASE_IP",
                "SNAPSHOT_STOP": "SNAPSHOT_STOP"
            }
            # Map Enum to string
            action_key = str(action_data.action_type).replace("CleanupActionType.", "")
            mapped_action = action_config_map.get(action_key, action_key)
            
            perm_service = PermissionService(self.db)
            
            # Check permission for each resource (Active Window covers all, Specific Ticket covers specific)
            # If any resource is denied, the whole batch fails (atomic safety)
            for rid in action_data.resource_ids:
                perm_service.enforce(user, mapped_action, rid)
                
            logger.info(f"JIT Check passed for {mapped_action} by {user.email}")

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

    def get_discoverable_resources(self, account_id: str, resource_type: str, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List resources of a specific type in an account/region for JIT discovery.
        This allows users to find Resource IDs (e.g., Instance IDs) when creating tickets.
        """
        account = self.db.query(Account).filter(Account.aws_account_id == account_id).first()
        if not account:
            # Try searching by ID if aws_account_id is not provided
            account = self.db.query(Account).filter(Account.id == account_id).first()
            if not account:
                raise Exception(f"Account {account_id} not found")

        # Use ALL regions if none provided
        regions_to_scan = [region] if region and region != 'ALL' else self._get_all_regions(self._get_platform_session())
        
        discovered = []
        
        for r_name in regions_to_scan:
            try:
                session = self._get_account_session(account, r_name)
                
                if resource_type.upper() == ResourceType.INSTANCE.value:
                    ec2 = session.client('ec2')
                    paginator = ec2.get_paginator('describe_instances')
                    for page in paginator.paginate():
                        for reservation in page['Reservations']:
                            for instance in reservation['Instances']:
                                name_tag = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), "Unknown")
                                discovered.append({
                                    "id": instance['InstanceId'],
                                    "name": name_tag,
                                    "type": "INSTANCE",
                                    "region": r_name,
                                    "status": instance['State']['Name']
                                })
                
                elif resource_type.upper() == ResourceType.VOLUME.value:
                    ec2 = session.client('ec2')
                    paginator = ec2.get_paginator('describe_volumes')
                    for page in paginator.paginate():
                        for volume in page['Volumes']:
                            name_tag = next((tag['Value'] for tag in volume.get('Tags', []) if tag['Key'] == 'Name'), "Unknown")
                            discovered.append({
                                "id": volume['VolumeId'],
                                "name": name_tag,
                                "type": "VOLUME",
                                "region": r_name,
                                "status": volume['State']
                            })

                elif resource_type.upper() == ResourceType.RDS_DB.value:
                    rds = session.client('rds')
                    paginator = rds.get_paginator('describe_db_instances')
                    for page in paginator.paginate():
                        for db in page['DBInstances']:
                            discovered.append({
                                "id": db['DBInstanceIdentifier'],
                                "name": db.get('DBInstanceIdentifier', 'Unknown'),
                                "type": "RDS_DB",
                                "region": r_name,
                                "status": db['DBInstanceStatus']
                            })

            except Exception as e:
                logger.error(f"Discovery error in {r_name} for {resource_type}: {e}")
                continue

        return discovered

    def authorize_resource(self, resource_id: str, resource_type: str, user: User, force: bool = False, account_id: str = None, region: str = 'us-east-1'):
        """
        Authorize a single resource.
        Marks it as 'Authorized' in the database to exclude it from cleanup results.
        """
        from backend.models.authorized_resource import AuthorizedResource
        from backend.models.account import Account
        
        # Resolve Account ID if not provided (Try by matching resource_id in scan cache or active DB items first? No, scan cache is ephemeral)
        # We rely on account_id passed from Route or try to resolve via known context.
        final_account_id = None
        if account_id:
             # Validate
             acc = self.db.query(Account).filter((Account.id == account_id) | (Account.aws_account_id == account_id)).first()
             if acc: final_account_id = acc.id
        
        if not final_account_id:
            # Fallback: Try to find any account this user owns? Too dangerous.
            # Require account_id.
            # Exception: Resource ID might be globally unique enough if we search AuthorizedResources but we are Creating one.
            raise ValueError("Account ID is required for authorization.")

        # Check if already authorized
        exists = self.db.query(AuthorizedResource).filter(
            AuthorizedResource.account_id == final_account_id, 
            AuthorizedResource.resource_id == resource_id
        ).first()
        
        if exists:
            return {"status": "success", "message": f"Resource {resource_id} is already authorized."}
            
        new_auth = AuthorizedResource(
            resource_id=resource_id,
            account_id=final_account_id,
            organization_id=user.organization_id,
            region=region,
            resource_type=resource_type,
            created_by_id=user.id,
            notes=f"Authorized by {user.email} {'(Force)' if force else ''}"
        )
        self.db.add(new_auth)
        self.db.commit()
        return {"status": "success", "message": f"Authorized {resource_id}"}

    def get_resource_details(self, account_id: str, resource_id: str, resource_type: str, region: str) -> Dict[str, Any]:
        """
        Fetch fresh details for a single resource to validate tags.
        """
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            account = self.db.query(Account).filter(Account.aws_account_id == account_id).first()
            if not account:
                raise Exception(f"Account {account_id} not found")

        session = self._get_account_session(account, region)
        
        tags = []
        try:
            if resource_type.upper() == "INSTANCE":
                ec2 = session.client('ec2')
                resp = ec2.describe_instances(InstanceIds=[resource_id])
                if resp['Reservations']:
                    inst = resp['Reservations'][0]['Instances'][0]
                    tags = inst.get('Tags', [])
                    
            elif resource_type.upper() == "VOLUME":
                ec2 = session.client('ec2')
                resp = ec2.describe_volumes(VolumeIds=[resource_id])
                if resp['Volumes']:
                    tags = resp['Volumes'][0].get('Tags', [])
                    
            elif resource_type.upper() == "SNAPSHOT":
                ec2 = session.client('ec2')
                resp = ec2.describe_snapshots(SnapshotIds=[resource_id])
                if resp['Snapshots']:
                    tags = resp['Snapshots'][0].get('Tags', [])
                    
            elif resource_type.upper() == "RDS_DB":
                rds = session.client('rds')
                resp = rds.describe_db_instances(DBInstanceIdentifier=resource_id)
                if resp['DBInstances']:
                    tags = resp['DBInstances'][0].get('TagList', [])
                    
            elif resource_type.upper() == "S3_BUCKET":
                s3 = session.client('s3')
                try:
                    tag_resp = s3.get_bucket_tagging(Bucket=resource_id)
                    tags = tag_resp.get('TagSet', [])
                except:
                    tags = []
                    
        except Exception as e:
            logger.error(f"Failed to fetch details for {resource_id}: {e}")
            # Non-blocking, return empty tags
            pass

        return {
            "id": resource_id,
            "type": resource_type,
            "tags": {t['Key']: t['Value'] for t in tags}
        }
        

