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
from backend.schemas.hygiene_schemas import (
    ResourceItem, HygieneSummary, ResourceType, HygieneStatus,
    HygieneAction, HygieneActionType
)

logger = logging.getLogger(__name__)

# ── Modular Resource Rules ─────────────────────────────────────────────────────
from backend.Resource_rules import RuleVerdict
from backend.Resource_rules.compute_rules import (
    classify_stopped_instance, classify_running_instance,
    classify_reserved_instance, classify_eks_cluster,
    classify_ecs_cluster, classify_asg,
)
from backend.Resource_rules.storage_rules import (
    classify_ebs_volume, classify_snapshot,
    classify_s3_bucket, classify_s3_lifecycle as classify_s3_lifecycle_rule,
)
from backend.Resource_rules.database_rules import (
    classify_rds_instance, classify_rds_multi_az,
)
from backend.Resource_rules.network_rules import (
    classify_load_balancer, classify_eni,
    classify_elastic_ip, classify_nat_gateway,
)
from backend.Resource_rules.identity_rules import (
    classify_iam_user,
)
from backend.Resource_rules.security_rules import (
    classify_kms_key, classify_secret,
)
from backend.Resource_rules.management_rules import (
    classify_log_group, classify_cloudwatch_alarm,
    classify_lambda_function, classify_eventbridge_rule,
)

class HygieneService:
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
        """Assume role into customer account with Redis-backed STS session cache (TTL 50 min)."""
        if not account.role_arn:
            raise Exception("Account has no Role ARN configured")

        import json as _json
        from backend.core.redis_client import get_redis_client
        _redis = get_redis_client()
        _cache_key = f"spot:sts_session:{account.id}:{region}"
        _cached = _redis.get(_cache_key)
        if _cached:
            creds = _json.loads(_cached)
        else:
            platform_session = self._get_platform_session()
            sts = platform_session.client('sts')
            assumed = sts.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName="SpotOptimizerCleanup",
                ExternalId=account.external_id
            )
            creds = {
                'AccessKeyId': assumed['Credentials']['AccessKeyId'],
                'SecretAccessKey': assumed['Credentials']['SecretAccessKey'],
                'SessionToken': assumed['Credentials']['SessionToken'],
            }
            # Cache for 50 min (STS tokens last 1 hour)
            _redis.setex(_cache_key, 3000, _json.dumps(creds))

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

    def scan_resources(self, account_id: str, request_regions: List[str] = None, organization = None, force_refresh: bool = False) -> HygieneSummary:
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
                        return HygieneSummary(**data)
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
        from backend.models.hygiene_policy import HygienePolicy
        all_active_policies = self.db.query(HygienePolicy).filter(
            HygienePolicy.is_active == True
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
        
        # CRITICAL FIX: Total Potential Savings = ONLY safe-for-cleanup resources
        # Only count SAFE_TO_DELETE resources (not ORPHANED, UNAUTHORIZED, etc.)
        # This gives users an accurate, actionable savings figure
        current_savings = max(0.0, sum(
            r.cost_per_month for r in resources 
            if r.status == HygieneStatus.SAFE_TO_DELETE and not r.is_authorized
        ))
        
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
        
        # Calculate Total Discovered Cost (Feature 3) - Cost of ALL resources found
        total_discovered_cost = sum(r.cost_per_month for r in resources)

        summary = HygieneSummary(
            total_potential_savings=current_savings,
            total_discovered_cost=total_discovered_cost,
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
                history_data = {
                    'total_potential_savings': current_savings,
                    'total_discovered_cost': total_discovered_cost,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                redis_client.setex(history_key, 604800, json.dumps(history_data))
            except Exception as e:
                logger.error(f"Failed to set cleanup cache: {e}")
            
        return summary

    def get_scan_history(self, account_id: str, days: int, organization_id: str = None) -> List[Dict[str, Any]]:
        from backend.core.redis_client import get_redis_client
        import json
        from datetime import datetime, timedelta, timezone
        
        redis_client = get_redis_client()
        history_key = f"cleanup:history:{account_id}"
        
        latest_savings = 0.0
        latest_discovered = 0.0
        
        if redis_client:
            try:
                prev_data = redis_client.get(history_key)
                if prev_data:
                    data = json.loads(prev_data)
                    latest_savings = float(data.get('total_potential_savings', 0))
                    latest_discovered = float(data.get('total_discovered_cost', 0))
            except Exception as e:
                logger.error(f"Failed to parse history from redis: {e}")
                
        if latest_savings == 0 and latest_discovered == 0:
            return []
            
        history = []
        # Return a simple mock history mimicking the latest reading for today, and 0 for past,
        # so frontend sparkbar shows empty history until more scans accumulate.
        for i in range(days, -1, -1):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            if i == 0:
                history.append({
                    "date": date,
                    "resources_discovered": latest_discovered,
                    "potential_savings": latest_savings
                })
            else:
                history.append({
                    "date": date,
                    "resources_discovered": 0,
                    "potential_savings": 0
                })
                
        return history

    def _scan_region_worker(self, account: Account, region: str, organization = None, policies=None):
        """Helper to scan a single region independently for parallel execution"""
        from datetime import datetime, timedelta, timezone
        from backend.utils.pricing_helper import get_pricing_helper
        from backend.services.resource_cost_service import ResourceCostService

        pricing = get_pricing_helper()
        cost_service = ResourceCostService(self.db)

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
                from backend.schemas.hygiene_policy_schemas import HygieneConditionRule
                
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

                    # ENTERPRISE: Use Cost Explorer for invoice-accurate costs
                    # Falls back to static pricing if Cost Explorer unavailable
                    cost = float(cost_service.get_resource_monthly_cost(
                        resource_id=v['VolumeId'],
                        resource_type='VOLUME',
                        account_id=account.id,
                        resource_size=v['Size'],
                        region=region
                    ))

                    # ── Use modular rule ──
                    verdict, reason = classify_ebs_volume(
                        state=vol_state,
                        created_at=created_at,
                        tags=tags,
                        required_tags=required_tags,
                    )
                    status = HygieneStatus(verdict.value)

                    if vol_state == 'in-use':
                        vol_cost = cost
                    else:
                        vol_cost = cost
                        
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
                                    if policy.action == HygieneActionType.DELETE:
                                        status = HygieneStatus.SAFE_TO_DELETE
                                    elif policy.action == HygieneActionType.NOTIFY:
                                        status = HygieneStatus.ORPHANED
                                    elif policy.action == HygieneActionType.SNAPSHOT_STOP:
                                        status = HygieneStatus.SAFE_TO_DELETE # Treat as actionable
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

                for s in snaps['Snapshots']:
                    vol_id = s.get('VolumeId')
                    snap_id = s['SnapshotId']

                    # CRITICAL: If snapshot is used by AMI, mark as ACTIVE (DO NOT DELETE)
                    if snap_id in ami_snapshot_ids:
                        tags = s.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        # ENTERPRISE: Use Cost Explorer for invoice-accurate costs
                        cost = float(cost_service.get_resource_monthly_cost(
                            resource_id=snap_id,
                            resource_type='SNAPSHOT',
                            account_id=account.id,
                            resource_size=s['VolumeSize'],
                            region=region
                        ))
                        item = ResourceItem(
                            id=snap_id,
                            name=self._get_tag_value(tags, 'Name'),
                            type=ResourceType.SNAPSHOT,
                            status=HygieneStatus.ACTIVE,  # ✅ PROTECTED
                            region=region,
                            cost_per_month=cost,  # Show cost for visibility (even though protected)
                            reason="Used by AMI (Do Not Delete)",
                            metadata={'VolumeId': vol_id, 'Size': s['VolumeSize'], 'Progress': s['Progress'], 'AMI_Protected': True},
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
                        continue  # ✅ Skip adding to savings (cannot be deleted)

                    # Safety Logic: If Volume is gone, Snapshot IS orphaned.
                    # But is it SAFE to delete?
                    if vol_id and vol_id not in all_vol_ids:
                        start_time = s.get('StartTime')

                        # ── Use modular rule ──
                        verdict, reason = classify_snapshot(
                            snap_id=snap_id,
                            volume_id=vol_id,
                            start_time=start_time,
                            ami_snapshot_ids=ami_snapshot_ids,
                            all_volume_ids=all_vol_ids,
                        )
                        status = HygieneStatus(verdict.value) if verdict else HygieneStatus.ACTIVE

                        tags = s.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        # ENTERPRISE: Use Cost Explorer for invoice-accurate costs
                        cost = float(cost_service.get_resource_monthly_cost(
                            resource_id=snap_id,
                            resource_type='SNAPSHOT',
                            account_id=account.id,
                            resource_size=s['VolumeSize'],
                            region=region
                        ))
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

                for ip in eips['Addresses']:
                    if 'AssociationId' not in ip:
                        # Unattached EIP.
                        # Safety: Cannot verify age easily.
                        # Logic: Unattached EIP is waste, but deleting 'Prod-VIP' is fatal.
                        # Usage: Mark ORPHANED (Risky). User must verify.

                        # ── Use modular rule ──
                        verdict, reason = classify_elastic_ip(has_association=False)
                        status = HygieneStatus(verdict.value) if verdict else HygieneStatus.ACTIVE

                        # ENTERPRISE: Use Cost Explorer for invoice-accurate costs
                        cost = float(cost_service.get_resource_monthly_cost(
                            resource_id=ip['AllocationId'],
                            resource_type='ELASTIC_IP',
                            account_id=account.id,
                            region=region
                        ))
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

                    # ZOMBIE DETECTION: Stopped instances (per zombie guide - 70% certainty)
                    if inst_data['State']['Name'] == 'stopped':
                        inst_cost = pricing.get_ec2_price(region, inst_type)
                        # Parse stop duration from StateTransitionReason
                        stopped_days = 0
                        state_reason = inst_data.get('StateTransitionReason', '')
                        try:
                            import re
                            date_match = re.search(r'\((\d{4}-\d{2}-\d{2})', state_reason)
                            if date_match:
                                stopped_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
                                stopped_days = (datetime.now(timezone.utc) - stopped_date).days
                        except Exception:
                            pass

                        # ── Use modular rule ──
                        verdict, reason = classify_stopped_instance(stopped_days)
                        inst_status = HygieneStatus(verdict.value)
                        if verdict == RuleVerdict.SAFE:
                            savings += inst_cost

                        item = ResourceItem(
                            id=inst_id,
                            name=name,
                            type=ResourceType.INSTANCE,
                            status=inst_status,
                            region=region,
                            cost_per_month=inst_cost,
                            reason=reason,
                            metadata={
                                'InstanceType': inst_type,
                                'State': 'stopped',
                                'Managed': inst_id in db_instance_set,
                                'StoppedDays': stopped_days
                            },
                            is_compliant=True
                        )
                        resources.append(item)
                        continue  # Skip further managed/unmanaged classification

                    # AUTHORIZED: Instances managed by Spot Optimizer (cluster nodes)
                    if inst_id in db_instance_set:
                        # These are cluster nodes - show as AUTHORIZED (managed)
                        # Show actual cost for visibility (not counted in savings)
                        inst_cost = pricing.get_ec2_price(region, inst_type)
                        item = ResourceItem(
                            id=inst_id,
                            name=name,
                            type=ResourceType.INSTANCE,
                            status=HygieneStatus.ACTIVE,  # Authorized/Managed
                            region=region,
                            cost_per_month=inst_cost,  # Actual cost for visibility
                            reason="Managed by Spot Optimizer (Cluster Node)",
                            metadata={
                                'InstanceType': inst_type,
                                'State': inst_data['State']['Name'],
                                'Managed': True,
                                'ManagedBy': 'Spot Optimizer'
                            },
                            is_compliant=True,
                            is_authorized=True # By default authorized if managed by system
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
                                status=HygieneStatus.UNAUTHORIZED,
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
                                # Show actual cost for visibility (not counted in savings)
                                inst_cost = pricing.get_ec2_price(region, inst_type)
                                item = ResourceItem(
                                    id=inst_id,
                                    name=name,
                                    type=ResourceType.INSTANCE,
                                    status=HygieneStatus.NOT_COMPLIANT,
                                    region=region,
                                    cost_per_month=inst_cost,  # Actual cost for visibility
                                    reason=f"Not managed (Missing tags: {', '.join(missing)})",
                                    metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name'], 'Managed': False},
                                    is_compliant=False,
                                    missing_tags=missing
                                )
                                resources.append(item)
                            else:
                                # Properly tagged, not managed = legitimate external workload
                                # Show as ACTIVE (authorized external workload)
                                # Show actual cost for visibility (not counted in savings)
                                inst_cost = pricing.get_ec2_price(region, inst_type)
                                item = ResourceItem(
                                    id=inst_id,
                                    name=name,
                                    type=ResourceType.INSTANCE,
                                    status=HygieneStatus.ACTIVE,
                                    region=region,
                                    cost_per_month=inst_cost,  # Actual cost for visibility
                                    reason="Not managed (Properly tagged external workload)",
                                    metadata={'InstanceType': inst_type, 'State': inst_data['State']['Name'], 'Managed': False},
                                    is_compliant=True
                                )
                                resources.append(item)
                        else:
                            # No required tags policy - show as external workload
                            # Show actual cost for visibility (not counted in savings)
                            inst_cost = pricing.get_ec2_price(region, inst_type)
                            item = ResourceItem(
                                id=inst_id,
                                name=name,
                                type=ResourceType.INSTANCE,
                                status=HygieneStatus.ACTIVE,
                                region=region,
                                cost_per_month=inst_cost,  # Actual cost for visibility
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

            # 11. NEW: VPC Resources (VPC, VPC Endpoints, Transit Gateways)
            vpc_res, vpc_sav = self._scan_vpc_resources(session, region, required_tags, account.id)
            resources.extend(vpc_res)
            savings += vpc_sav

            # 12. NEW: Security Resources (Security Hub, KMS, Secrets Manager, CloudTrail, GuardDuty)
            sec_res, sec_sav = self._scan_security_resources(session, region, required_tags, account.id)
            resources.extend(sec_res)
            savings += sec_sav

            # 13. NEW: Management Resources (Config, SSM, CloudWatch, Lambda, EventBridge)
            mgmt_res, mgmt_sav = self._scan_management_resources(session, region, required_tags, account.id)
            resources.extend(mgmt_res)
            savings += mgmt_sav

            # 14. NEW: Compute Resources (EKS, ECS, Auto Scaling Groups)
            compute_res, compute_sav = self._scan_compute_resources(session, region, required_tags, account.id)
            resources.extend(compute_res)
            savings += compute_sav

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
                    has_active_targets = False
                    
                    if not tgs:
                        has_active_targets = False
                    else:
                        for tg in tgs:
                            try:
                                health = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])['TargetHealthDescriptions']
                                active_states = ['healthy', 'initial']
                                if any(h['TargetHealth']['State'] in active_states for h in health):
                                    has_active_targets = True
                                    break
                            except Exception:
                                continue
                    
                    # ── Use modular rule ──
                    verdict, reason = classify_load_balancer(has_active_targets)
                    if verdict is not None:
                        cost = pricing.get_load_balancer_price(region, lb_type)
                        status = HygieneStatus(verdict.value)
                        
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
                    desc = eni.get('Description', '')
                    requester_id = eni.get('RequesterId', '')

                    # ── Use modular rule ──
                    verdict, reason = classify_eni(
                        status='available',
                        description=desc,
                        requester_id=requester_id,
                    )
                    if verdict is None:
                        continue  # AWS-managed or attached

                    cost = 0.0
                    status = HygieneStatus(verdict.value)

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
                cleanup_status = HygieneStatus.ACTIVE
                reason = None
                cost_estimate = 0.0

                # Calculate real cost
                real_cost = pricing.get_rds_price(region, db_class, engine)

                # ── Use modular rule ──
                verdict, reason = classify_rds_instance(
                    is_idle=is_idle,
                    has_replicas=has_replicas,
                    db_class=db_class,
                )
                cleanup_status = HygieneStatus(verdict.value)
                if verdict == RuleVerdict.RISKY:
                    cost_estimate = real_cost
                elif verdict == RuleVerdict.REVIEW:
                    cost_estimate = real_cost * 0.2
                else:
                    cost_estimate = 0.0
                
                # Tag compliance
                tags = db.get('TagList', [])
                tag_keys = {t['Key'] for t in tags}
                missing = [rt for rt in required_tags if rt not in tag_keys]
                
                # Only add if there's an issue
                if cleanup_status != HygieneStatus.ACTIVE or len(missing) > 0:
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
                # ── Use modular rule ──
                verdict, reason = classify_iam_user(
                    days_inactive=days_inactive,
                    has_active_keys=has_active_keys,
                )
                if verdict == RuleVerdict.ACTIVE:
                    continue
                status = HygieneStatus(verdict.value)

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
            cw = session.client('cloudwatch')
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
                
                # Get actual storage size from CloudWatch for cost calculation
                size_gb = 0.0
                try:
                    metrics = cw.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='BucketSizeBytes',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'StandardStorage'}
                        ],
                        StartTime=datetime.now() - timedelta(days=2),
                        EndTime=datetime.now(),
                        Period=86400,
                        Statistics=['Average']
                    )
                    if metrics.get('Datapoints'):
                        size_gb = metrics['Datapoints'][-1]['Average'] / (1024**3)
                except Exception:
                    pass  # CloudWatch metrics may not be available
                
                # S3 Standard: $0.023/GB/month
                storage_cost = round(size_gb * 0.023, 2)
                
                # Determine status
                status = HygieneStatus.ACTIVE
                reason = None
                cost = storage_cost if storage_cost > 0 else 0.0
                
                if is_empty:
                    status = HygieneStatus.SAFE_TO_DELETE
                    reason = "Empty bucket"
                    cost = max(0.50, storage_cost)  # Minimum $0.50 for empty bucket overhead
                elif missing:
                    status = HygieneStatus.NOT_COMPLIANT
                    reason = f"Missing tags: {', '.join(missing)}"
                    # cost already set from CloudWatch storage_cost
                
                if status != HygieneStatus.ACTIVE:
                    item = ResourceItem(
                        id=bucket_name,
                        name=bucket_name,
                        type=ResourceType.S3_BUCKET,
                        status=status,
                        region='global',
                        cost_per_month=cost,
                        reason=reason,
                        metadata={'Created': str(created), 'SizeGB': round(size_gb, 2)},
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
                
                # ── Use modular rule ──
                verdict, reason = classify_reserved_instance(utilization, matched, count)
                if verdict != RuleVerdict.ACTIVE:
                    wasted_count = count - matched
                    cost_per_ri = 20.0
                    waste_cost = wasted_count * cost_per_ri
                    status = HygieneStatus(verdict.value)
                    
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
                    
                    # ── Use modular rule ──
                    lc_verdict, lc_reason = classify_s3_lifecycle_rule(has_lifecycle=False, size_bytes=size_bytes)
                    if lc_verdict is not None:
                        cost = (size_bytes / (1024**3)) * 0.023
                        potential_saving = cost * 0.4
                        
                        item = ResourceItem(
                            id=b_name,
                            name=b_name,
                            type=ResourceType.S3_BUCKET,
                            status=HygieneStatus.LEGACY_UPGRADE,
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
                    
                    env = tag_keys.get('Environment', '')
                    # ── Use modular rule ──
                    maz_verdict, maz_reason = classify_rds_multi_az(is_multi_az=True, environment=env)
                    if maz_verdict is not None:
                        cost = 100.0 # Estimate surcharge for Multi-AZ
                        
                        item = ResourceItem(
                            id=db['DBInstanceIdentifier'],
                            name=db['DBInstanceIdentifier'],
                            type=ResourceType.RDS_DB,
                            status=HygieneStatus.LEGACY_UPGRADE, # Downgrade needed
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
                    # ── Use modular rule ──
                    nat_verdict, nat_reason = classify_nat_gateway(weekly_gb_out=gb_out)
                    if nat_verdict is not None:
                        cost = gb_out * 0.045
                        item = ResourceItem(
                            id=nat['NatGatewayId'],
                            name="NAT Gateway",
                            type=ResourceType.NAT_GATEWAY,
                            status=HygieneStatus(nat_verdict.value),
                            region=region,
                            cost_per_month=cost * 4,
                            reason=nat_reason,
                            metadata={'WeeklyGB': gb_out},
                            is_compliant=True
                        )
                        resources.append(item)
                        savings += (cost * 4)
                        
        except Exception as e:
            logger.error(f"DataTransfer Error: {e}")
        return resources, savings

    def execute_action(self, account_id: str, action_data: HygieneAction, user: User = None, bypass_approval: bool = False):
        """
        Execute a cleanup action on a specific resource.
        Supports RBAC & Team-Specific Approval Workflow.
        """
        # 0. RBAC / Approval Check
        # 0. JIT Governance Check
        if user and not bypass_approval:
            from backend.services.permission_service import PermissionService
            from backend.models.organization import Organization
            from backend.services.approval_service import ApprovalService
            from backend.schemas.approval_schemas import ApprovalCreate
            from backend.models.approval import ApprovalType, ReasonCategory
            
            # 1. Check if System Approval is Required for Cleanup
            org = self.db.query(Organization).filter(Organization.id == user.organization_id).first()
            
            # Admins bypass approval — only MEMBER/TEAM_LEAD need tickets
            from backend.models.user import UserRole
            is_admin = user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, 'SUPER_ADMIN', 'ORG_ADMIN')
            
            if org and org.require_automation_approval and not is_admin:
                logger.info(f"System Approval required for {user.role}. Creating ticket for {action_data.action_type}")
                
                approval_service = ApprovalService(self.db)
                approval_in = ApprovalCreate(
                    type=ApprovalType.SYSTEM_CLEANUP,
                    reason_category=ReasonCategory.MAINTENANCE,
                    reason_text="Automated Governance Cleanup Action",
                    duration_hours=24,
                    resource_id=f"batch-{datetime.utcnow().timestamp()}",
                    action_type=str(action_data.action_type),
                )
                approval = approval_service.create_approval(user, approval_in.model_dump())
                return {
                    "status": "pending_approval",
                    "approval_id": str(approval.id),
                    "message": f"Action paused. Approval #{approval.id} created.",
                }

            # 2. JIT Permission Check (if not routed to ticket)
            # Map cleanup action types to feature IDs
            action_feature_map = {
                "TERMINATE": "hygiene:execute",
                "DELETE": "hygiene:execute",
                "RELEASE": "hygiene:execute",
                "SNAPSHOT_STOP": "hygiene:execute",
                "DETACH": "feat-ebs-detach"
            }

            # Map Enum to string
            action_key = str(action_data.action_type).replace("HygieneActionType.", "")
            feature_id = action_feature_map.get(action_key, "hygiene:execute")

            perm_service = PermissionService(self.db)

            # Check permission for each resource (Active Window covers all, Specific Ticket covers specific)
            # If any resource is denied, the whole batch fails (atomic safety)
            try:
                for rid in action_data.resource_ids:
                    perm_service.enforce(user, feature_id, rid)

                logger.info(f"JIT Check passed for {feature_id} by {user.email}")
            except Exception as perm_error:
                logger.warning(f"Permission denied for {feature_id}: {perm_error}")
                raise perm_error

        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise Exception("Account not found")

        try:
            # Region must already be validated by the route layer (fix_A1).
            region = action_data.region

            # Get session for the specific region
            session = self._get_account_session(account, region=region)
            ec2 = session.client('ec2')
            
            action_type = action_data.action_type
            resource_ids = action_data.resource_ids
            
            logger.info(f"Executing {action_type} on {len(resource_ids)} resources in {action_data.region}")
            
            if action_type == HygieneActionType.DELETE:
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
                    
            elif action_type == HygieneActionType.RELEASE:
                for alloc_id in resource_ids:
                    ec2.release_address(AllocationId=alloc_id)
                    logger.info(f"Released IP {alloc_id}")
                    
            elif action_type == HygieneActionType.TERMINATE:
                # Bug C-3 fix: NEVER use the filter-dropdown region for EC2 termination.
                # When user selects "All Regions", action_data.region = 'global' which
                # would terminate in the wrong region (us-east-1 default) → InvalidInstanceID.
                # Instead: group each instance by its actual region, then terminate per-region.
                _VALID_AWS_REGIONS = {
                    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
                    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
                    "ap-south-1", "ap-southeast-1", "ap-southeast-2",
                    "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
                    "sa-east-1", "ca-central-1",
                }
                _filter_region = action_data.region if action_data.region in _VALID_AWS_REGIONS else None

                if _filter_region:
                    # User explicitly filtered to a valid region — terminate there directly
                    ec2.terminate_instances(InstanceIds=resource_ids)
                    logger.info(f"Terminated instances {resource_ids} in region {_filter_region}")
                else:
                    # Region is 'global'/'all'/unknown — look up each instance's actual region
                    _inst_by_region: dict = {}
                    for iid in resource_ids:
                        _found_region = None
                        for _r in _VALID_AWS_REGIONS:
                            try:
                                _ec2_r = session.client("ec2", region_name=_r)
                                _desc = _ec2_r.describe_instances(InstanceIds=[iid])
                                if _desc["Reservations"]:
                                    _found_region = _r
                                    break
                            except Exception:
                                continue
                        if _found_region:
                            _inst_by_region.setdefault(_found_region, []).append(iid)
                        else:
                            logger.warning(f"Could not locate instance {iid} in any region — skipping")
                    for _r, _ids in _inst_by_region.items():
                        _ec2_r = session.client("ec2", region_name=_r)
                        _ec2_r.terminate_instances(InstanceIds=_ids)
                        logger.info(f"Terminated instances {_ids} in region {_r}")

            elif action_type == HygieneActionType.SNAPSHOT_STOP:
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

            elif action_type == HygieneActionType.DISABLE:
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
                
            elif action_type == HygieneActionType.AUTHORIZE:
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

            elif action_type == HygieneActionType.UNAUTHORIZE:
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
            import botocore
            if isinstance(e, botocore.exceptions.ClientError):
                code = e.response['Error']['Code']
                if code == 'UnauthorizedOperation':
                    raise Exception(f"AWS Permission Denied: {e}")
                # Resource already gone (terminated/deleted/released elsewhere) — treat as success
                _not_found = {
                    'InvalidInstanceID.NotFound', 'InvalidInstanceID.Malformed',
                    'InvalidVolume.NotFound', 'InvalidSnapshot.NotFound',
                    'InvalidAllocationID.NotFound', 'InvalidAddress.NotFound',
                    'InvalidLoadBalancerArn.NotFound', 'LoadBalancerNotFound',
                }
                if code in _not_found:
                    logger.warning(
                        f"Resource not found during {action_type} (already cleaned up elsewhere): "
                        f"{code} region={region} — treating as success"
                    )
                    return {
                        "status": "success",
                        "message": f"Resource already cleaned up or no longer exists ({code}). No action needed.",
                        "skipped": True,
                        "skipped_reason": "NOT_FOUND",
                        "region_used": region,
                    }
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
                 
        # The original code had an `elif action.action_type == HygieneActionType.AUTHORIZE:` here.
        # Given the new structure, this `elif` would be outside the `try` block and not directly
        # related to the `action_type` checks within the `try`.
        # Assuming `HygieneActionType.AUTHORIZE` is a separate action not involving EC2 client calls
        # and should be handled after the main action execution block.
        # If it was meant to be part of the EC2 actions, it would need to be an `elif` inside the `try`.
        # For now, keeping it as a separate block as it was originally.
        if action_data.action_type == HygieneActionType.AUTHORIZE:
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

    def _scan_vpc_resources(self, session, region, required_tags, account_id):
        """Scan VPC, VPC Endpoints, and Transit Gateways"""
        from backend.services.resource_cost_service import ResourceCostService
        cost_service = ResourceCostService(self.db)

        resources = []
        savings = 0.0

        try:
            ec2 = session.client('ec2')

            # 1. VPCs (non-default only)
            vpcs = ec2.describe_vpcs()
            for vpc in vpcs.get('Vpcs', []):
                if not vpc.get('IsDefault', False) and vpc['State'] == 'available':
                    tags = vpc.get('Tags', [])
                    tag_keys = {t['Key'] for t in tags}
                    missing = [rt for rt in required_tags if rt not in tag_keys]

                    # VPCs are free but show for visibility
                    item = ResourceItem(
                        id=vpc['VpcId'],
                        name=self._get_tag_value(tags, 'Name'),
                        type=ResourceType.VPC,
                        status=HygieneStatus.ACTIVE,
                        region=region,
                        cost_per_month=0.0,
                        reason='Active VPC',
                        metadata={
                            'CidrBlock': vpc.get('CidrBlock'),
                            'State': vpc['State']
                        },
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)

            # 2. VPC Endpoints (Interface endpoints have cost)
            try:
                endpoints = ec2.describe_vpc_endpoints()
                for ep in endpoints.get('VpcEndpoints', []):
                    if ep['State'] == 'available':
                        tags = ep.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        # Interface endpoints cost money ($0.01/hr/AZ)
                        ep_type = ep.get('VpcEndpointType', 'Interface')
                        cost = 7.20 if ep_type == 'Interface' else 0.0  # ~$7.20/month

                        item = ResourceItem(
                            id=ep['VpcEndpointId'],
                            name=self._get_tag_value(tags, 'Name'),
                            type=ResourceType.VPC_ENDPOINT,
                            status=HygieneStatus.ACTIVE,
                            region=region,
                            cost_per_month=cost,
                            reason=f'{ep_type} VPC Endpoint',
                            metadata={
                                'ServiceName': ep.get('ServiceName'),
                                'Type': ep_type,
                                'VpcId': ep.get('VpcId')
                            },
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
            except Exception as ep_err:
                logger.error(f"VPC Endpoint scan error: {ep_err}")

            # 3. Transit Gateways
            try:
                tgws = ec2.describe_transit_gateways()
                for tgw in tgws.get('TransitGateways', []):
                    if tgw['State'] == 'available':
                        tags = tgw.get('Tags', [])
                        tag_keys = {t['Key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        # Transit Gateway: $0.05/hr = $36/month
                        cost = 36.0

                        item = ResourceItem(
                            id=tgw['TransitGatewayId'],
                            name=self._get_tag_value(tags, 'Name'),
                            type=ResourceType.TRANSIT_GATEWAY,
                            status=HygieneStatus.ACTIVE,
                            region=region,
                            cost_per_month=cost,
                            reason='Active Transit Gateway',
                            metadata={
                                'State': tgw['State'],
                                'OwnerId': tgw.get('OwnerId')
                            },
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
            except Exception as tgw_err:
                logger.error(f"Transit Gateway scan error: {tgw_err}")

        except Exception as e:
            logger.error(f"VPC resources scan error: {e}")

        return resources, savings

    def _scan_security_resources(self, session, region, required_tags, account_id):
        """Scan Security Hub, KMS Keys, Secrets Manager, CloudTrail, GuardDuty"""
        from backend.services.resource_cost_service import ResourceCostService
        cost_service = ResourceCostService(self.db)

        resources = []
        savings = 0.0

        try:
            # 1. Security Hub (check if enabled)
            try:
                security_hub = session.client('securityhub')
                hub = security_hub.describe_hub()

                if hub:
                    # Security Hub is enabled
                    item = ResourceItem(
                        id=hub['HubArn'],
                        name='Security Hub',
                        type=ResourceType.SECURITY_HUB,
                        status=HygieneStatus.ACTIVE,
                        region=region,
                        cost_per_month=10.0,  # Approximate
                        reason='Security Hub enabled',
                        metadata={
                            'SubscribedAt': str(hub.get('SubscribedAt')),
                            'AutoEnableControls': hub.get('AutoEnableControls')
                        },
                        is_compliant=True
                    )
                    resources.append(item)
            except Exception as sh_err:
                # Security Hub not enabled or no access
                pass

            # 2. KMS Keys (customer-managed only)
            try:
                kms = session.client('kms')
                keys = kms.list_keys()

                for key in keys.get('Keys', []):
                    try:
                        key_id = key['KeyId']
                        key_metadata = kms.describe_key(KeyId=key_id)
                        key_info = key_metadata['KeyMetadata']

                        # Customer-managed keys: detect disabled/zombie keys (60% certainty)
                        if key_info.get('KeyManager') == 'CUSTOMER':
                            key_state = key_info['KeyState']
                            # ── Use modular rule ──
                            kms_verdict, kms_reason = classify_kms_key(
                                key_manager='CUSTOMER',
                                key_state=key_state,
                            )
                            if kms_verdict is None:
                                continue
                            kms_status = HygieneStatus(kms_verdict.value)
                            kms_cost = 1.0 if kms_verdict != RuleVerdict.SAFE else 0.0
                            if kms_verdict == RuleVerdict.RISKY:
                                savings += kms_cost

                            item = ResourceItem(
                                id=key_id,
                                name=key_info.get('Description', 'No description'),
                                type=ResourceType.KMS_KEY,
                                status=kms_status,
                                region=region,
                                cost_per_month=kms_cost,
                                reason=kms_reason,
                                metadata={
                                    'Description': key_info.get('Description'),
                                    'CreationDate': str(key_info.get('CreationDate')),
                                    'KeyState': key_state
                                },
                                is_compliant=True
                            )
                            resources.append(item)
                    except Exception:
                        continue
            except Exception as kms_err:
                logger.error(f"KMS scan error: {kms_err}")

            # 3. Secrets Manager
            try:
                secrets = session.client('secretsmanager')
                secret_list = secrets.list_secrets()

                for secret in secret_list.get('SecretList', []):
                    tags = secret.get('Tags', [])
                    tag_keys = {t['Key'] for t in tags}
                    missing = [rt for rt in required_tags if rt not in tag_keys]

                    # Secrets Manager: $0.40/secret/month
                    # Zombie detection: not accessed in 90+ days (55% certainty per zombie guide)
                    secret_status = HygieneStatus.ACTIVE
                    secret_reason = 'Active secret'
                    last_accessed = secret.get('LastAccessedDate')
                    days_since_access = None
                    if last_accessed:
                        try:
                            if isinstance(last_accessed, datetime):
                                la = last_accessed if last_accessed.tzinfo else last_accessed.replace(tzinfo=timezone.utc)
                                days_since_access = (datetime.now(timezone.utc) - la).days
                        except Exception:
                            pass

                    # ── Use modular rule ──
                    sec_verdict, sec_reason = classify_secret(days_since_access=days_since_access)
                    secret_status = HygieneStatus(sec_verdict.value)
                    secret_reason = sec_reason
                    if sec_verdict == RuleVerdict.RISKY:
                        savings += 0.40

                    item = ResourceItem(
                        id=secret['ARN'],
                        name=secret.get('Name'),
                        type=ResourceType.SECRETS_MANAGER,
                        status=secret_status,
                        region=region,
                        cost_per_month=0.40,
                        reason=secret_reason,
                        metadata={
                            'LastChangedDate': str(secret.get('LastChangedDate')),
                            'LastAccessedDate': str(secret.get('LastAccessedDate'))
                        },
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)
            except Exception as sm_err:
                logger.error(f"Secrets Manager scan error: {sm_err}")

            # 4. CloudTrail (only in us-east-1 to avoid duplicates)
            if region == 'us-east-1':
                try:
                    cloudtrail = session.client('cloudtrail')
                    trails = cloudtrail.describe_trails()

                    for trail in trails.get('trailList', []):
                        # Check if trail is logging
                        status = cloudtrail.get_trail_status(Name=trail['TrailARN'])
                        if status.get('IsLogging'):
                            tags = trail.get('Tags', [])
                            tag_keys = {t['Key'] for t in tags}
                            missing = [rt for rt in required_tags if rt not in tag_keys]

                            # First trail free, additional $2/month
                            cost = 0.0  # Assume first trail

                            item = ResourceItem(
                                id=trail['TrailARN'],
                                name=trail.get('Name'),
                                type=ResourceType.CLOUDTRAIL,
                                status=HygieneStatus.ACTIVE,
                                region='global',
                                cost_per_month=cost,
                                reason='Active CloudTrail',
                                metadata={
                                    'IsLogging': status.get('IsLogging'),
                                    'S3BucketName': trail.get('S3BucketName')
                                },
                                is_compliant=len(missing) == 0,
                                missing_tags=missing
                            )
                            resources.append(item)
                except Exception as ct_err:
                    logger.error(f"CloudTrail scan error: {ct_err}")

            # 5. GuardDuty (only in us-east-1 to avoid duplicates)
            if region == 'us-east-1':
                try:
                    guardduty = session.client('guardduty')
                    detectors = guardduty.list_detectors()

                    for detector_id in detectors.get('DetectorIds', []):
                        detector = guardduty.get_detector(DetectorId=detector_id)
                        if detector.get('Status') == 'ENABLED':
                            # GuardDuty: Usage-based, approximate $5-10/month
                            item = ResourceItem(
                                id=detector_id,
                                name='GuardDuty Detector',
                                type=ResourceType.GUARDDUTY,
                                status=HygieneStatus.ACTIVE,
                                region='global',
                                cost_per_month=5.0,
                                reason='GuardDuty enabled',
                                metadata={
                                    'Status': detector.get('Status'),
                                    'CreatedAt': str(detector.get('CreatedAt'))
                                },
                                is_compliant=True
                            )
                            resources.append(item)
                except Exception as gd_err:
                    logger.error(f"GuardDuty scan error: {gd_err}")

        except Exception as e:
            logger.error(f"Security resources scan error: {e}")

        return resources, savings

    def _scan_management_resources(self, session, region, required_tags, account_id):
        """Scan Config, SSM, CloudWatch, Lambda, EventBridge"""
        from backend.services.resource_cost_service import ResourceCostService
        cost_service = ResourceCostService(self.db)

        resources = []
        savings = 0.0

        try:
            # 1. AWS Config Recorders
            try:
                config = session.client('config')
                recorders = config.describe_configuration_recorders()

                for recorder in recorders.get('ConfigurationRecorders', []):
                    # Check if recording
                    status = config.describe_configuration_recorder_status(
                        ConfigurationRecorderNames=[recorder['name']]
                    )
                    is_recording = status['ConfigurationRecordersStatus'][0].get('recording', False)

                    if is_recording:
                        # Config: Usage-based, approximate $10/month
                        item = ResourceItem(
                            id=recorder['name'],
                            name=recorder['name'],
                            type=ResourceType.CONFIG_RECORDER,
                            status=HygieneStatus.ACTIVE,
                            region=region,
                            cost_per_month=10.0,
                            reason='Config recorder active',
                            metadata={
                                'RoleARN': recorder.get('roleARN'),
                                'Recording': is_recording
                            },
                            is_compliant=True
                        )
                        resources.append(item)
            except Exception as config_err:
                logger.error(f"Config scan error: {config_err}")

            # 2. Systems Manager Managed Instances
            try:
                ssm = session.client('ssm')
                instances = ssm.describe_instance_information()

                for instance in instances.get('InstanceInformationList', []):
                    if instance['PingStatus'] == 'Online':
                        # SSM itself is free
                        item = ResourceItem(
                            id=instance['InstanceId'],
                            name=instance.get('ComputerName', 'Unknown'),
                            type=ResourceType.SSM_MANAGED_INSTANCE,
                            status=HygieneStatus.ACTIVE,
                            region=region,
                            cost_per_month=0.0,
                            reason='SSM managed instance',
                            metadata={
                                'PlatformType': instance.get('PlatformType'),
                                'PlatformName': instance.get('PlatformName'),
                                'PingStatus': instance['PingStatus']
                            },
                            is_compliant=True
                        )
                        resources.append(item)
            except Exception as ssm_err:
                logger.error(f"SSM scan error: {ssm_err}")

            # 3. CloudWatch Log Groups - zombie detection (80% certainty per zombie guide)
            try:
                logs = session.client('logs')
                log_groups = logs.describe_log_groups()

                for log_group in log_groups.get('logGroups', []):
                    stored_bytes = log_group.get('storedBytes', 0)
                    stored_gb = stored_bytes / (1024**3) if stored_bytes > 0 else 0
                    cost = round(stored_gb * 0.03, 2)  # $0.03/GB/month

                    # Zombie detection: empty or stale log groups
                    log_status = HygieneStatus.ACTIVE
                    log_reason = f'Log group storing {stored_gb:.2f} GB'
                    days_since_event = None
                    last_event = log_group.get('lastIngestionTime')  # epoch ms

                    # ── Use modular rule ──
                    log_verdict, log_reason = classify_log_group(
                        stored_bytes=stored_bytes,
                        days_since_last_event=days_since_event,
                    )
                    log_status = HygieneStatus(log_verdict.value)
                    if log_verdict == RuleVerdict.SAFE:
                        cost = 0.0
                    elif log_verdict == RuleVerdict.RISKY:
                        savings += cost

                    # Show flagged log groups + large ones for visibility
                    if log_status != HygieneStatus.ACTIVE or stored_bytes > 1_000_000_000:
                        item = ResourceItem(
                            id=log_group['logGroupName'],
                            name=log_group['logGroupName'],
                            type=ResourceType.CLOUDWATCH_LOG_GROUP,
                            status=log_status,
                            region=region,
                            cost_per_month=cost,
                            reason=log_reason,
                            metadata={
                                'StoredBytes': stored_bytes,
                                'RetentionInDays': log_group.get('retentionInDays', 'Never expire'),
                                'DaysSinceLastEvent': days_since_event if days_since_event is not None else 'Unknown'
                            },
                            is_compliant=True
                        )
                        resources.append(item)
            except Exception as logs_err:
                logger.error(f"CloudWatch Logs scan error: {logs_err}")

            # 4. CloudWatch Alarms - per-alarm zombie detection (85% certainty per zombie guide)
            try:
                cloudwatch = session.client('cloudwatch')
                alarms = cloudwatch.describe_alarms()

                all_alarms = alarms.get('MetricAlarms', [])
                zombie_alarms = []
                active_count = 0

                for alarm in all_alarms:
                    # ── Use modular rule ──
                    alarm_verdict, alarm_reason = classify_cloudwatch_alarm(
                        state_value=alarm.get('StateValue', ''),
                        has_actions=bool(alarm.get('AlarmActions')),
                    )
                    if alarm_verdict == RuleVerdict.ACTIVE:
                        active_count += 1
                    else:
                        zombie_alarms.append((alarm, alarm_verdict, alarm_reason))

                # Report zombie alarms individually
                for alarm, alarm_verdict, alarm_reason in zombie_alarms:
                    alarm_status = HygieneStatus(alarm_verdict.value)
                    alarm_cost = 0.10

                    item = ResourceItem(
                        id=alarm['AlarmArn'],
                        name=alarm['AlarmName'],
                        type=ResourceType.CLOUDWATCH_ALARM,
                        status=alarm_status,
                        region=region,
                        cost_per_month=alarm_cost,
                        reason=alarm_reason,
                        metadata={
                            'StateValue': alarm.get('StateValue'),
                            'MetricName': alarm.get('MetricName'),
                            'Namespace': alarm.get('Namespace'),
                            'HasActions': bool(alarm.get('AlarmActions'))
                        },
                        is_compliant=True
                    )
                    resources.append(item)
                    savings += alarm_cost

                # Summary for active alarms (visibility)
                if active_count > 10:
                    item = ResourceItem(
                        id=f'cloudwatch-alarms-active-{region}',
                        name=f'{active_count} Active CloudWatch Alarms',
                        type=ResourceType.CLOUDWATCH_ALARM,
                        status=HygieneStatus.ACTIVE,
                        region=region,
                        cost_per_month=active_count * 0.10,
                        reason=f'{active_count} healthy alarms',
                        metadata={'AlarmCount': active_count, 'ZombieCount': len(zombie_alarms)},
                        is_compliant=True
                    )
                    resources.append(item)
            except Exception as cw_err:
                logger.error(f"CloudWatch Alarms scan error: {cw_err}")

            # 5. Lambda Functions - zombie detection (65% certainty per zombie guide)
            try:
                lambda_client = session.client('lambda')
                cw_lambda = session.client('cloudwatch')
                functions = lambda_client.list_functions()

                for func in functions.get('Functions', []):
                    tags = func.get('Tags', {})
                    tag_keys = set(tags.keys())
                    missing = [rt for rt in required_tags if rt not in tag_keys]

                    # Check invocations in last 30 days via CloudWatch
                    lambda_status = HygieneStatus.ACTIVE
                    lambda_reason = 'Active Lambda function'
                    invocations = -1
                    try:
                        metrics = cw_lambda.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Invocations',
                            Dimensions=[{'Name': 'FunctionName', 'Value': func['FunctionName']}],
                            StartTime=datetime.now(timezone.utc) - timedelta(days=30),
                            EndTime=datetime.now(timezone.utc),
                            Period=2592000,  # 30 days in one datapoint
                            Statistics=['Sum']
                        )
                        datapoints = metrics.get('Datapoints', [])
                        invocations = int(datapoints[0]['Sum']) if datapoints else 0
                    except Exception:
                        invocations = -1  # Unknown

                    if invocations == 0:
                        # ── Use modular rule ──
                        lambda_verdict, lambda_reason = classify_lambda_function(invocations_30d=invocations)
                        lambda_status = HygieneStatus(lambda_verdict.value)
                    else:
                        lambda_status = HygieneStatus.ACTIVE
                        lambda_reason = 'Active Lambda function'

                    item = ResourceItem(
                        id=func['FunctionArn'],
                        name=func['FunctionName'],
                        type=ResourceType.LAMBDA_FUNCTION,
                        status=lambda_status,
                        region=region,
                        cost_per_month=0.0,  # Usage-based, $0 if not invoked
                        reason=lambda_reason,
                        metadata={
                            'Runtime': func.get('Runtime'),
                            'MemorySize': func.get('MemorySize'),
                            'LastModified': func.get('LastModified'),
                            'Invocations30d': invocations
                        },
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)
            except Exception as lambda_err:
                logger.error(f"Lambda scan error: {lambda_err}")

            # 6. EventBridge Rules - per-rule zombie detection (70% certainty per zombie guide)
            try:
                events_client = session.client('events')
                rules = events_client.list_rules()

                active_count = 0
                for rule in rules.get('Rules', []):
                    rule_name = rule.get('Name', 'Unknown')
                    rule_state = rule.get('State', 'UNKNOWN')

                    # Check targets for this rule
                    try:
                        targets = events_client.list_targets_by_rule(Rule=rule_name)
                        target_count = len(targets.get('Targets', []))
                    except Exception:
                        target_count = -1

                    # ── Use modular rule ──
                    eb_verdict, eb_reason = classify_eventbridge_rule(
                        rule_state=rule_state,
                        target_count=target_count,
                    )
                    eb_status = HygieneStatus(eb_verdict.value)
                    if eb_verdict == RuleVerdict.ACTIVE:
                        active_count += 1

                    # Only report zombie rules individually
                    if eb_status != HygieneStatus.ACTIVE:
                        item = ResourceItem(
                            id=rule.get('Arn', rule_name),
                            name=rule_name,
                            type=ResourceType.EVENTBRIDGE_RULE,
                            status=eb_status,
                            region=region,
                            cost_per_month=0.0,  # Usage-based
                            reason=eb_reason,
                            metadata={
                                'State': rule_state,
                                'TargetCount': target_count,
                                'ScheduleExpression': rule.get('ScheduleExpression', '')
                            },
                            is_compliant=True
                        )
                        resources.append(item)

                # Summary for active rules (visibility)
                if active_count > 10:
                    item = ResourceItem(
                        id=f'eventbridge-rules-{region}',
                        name=f'{active_count} Active EventBridge Rules',
                        type=ResourceType.EVENTBRIDGE_RULE,
                        status=HygieneStatus.ACTIVE,
                        region=region,
                        cost_per_month=0.0,
                        reason=f'{active_count} active rules',
                        metadata={'RuleCount': active_count},
                        is_compliant=True
                    )
                    resources.append(item)
            except Exception as eb_err:
                logger.error(f"EventBridge scan error: {eb_err}")

        except Exception as e:
            logger.error(f"Management resources scan error: {e}")

        return resources, savings

    def _scan_compute_resources(self, session, region, required_tags, account_id):
        """Scan EKS Clusters, ECS Clusters, Auto Scaling Groups"""
        from backend.services.resource_cost_service import ResourceCostService
        cost_service = ResourceCostService(self.db)

        resources = []
        savings = 0.0

        try:
            # 1. EKS Clusters
            try:
                eks = session.client('eks')
                clusters = eks.list_clusters()

                for cluster_name in clusters.get('clusters', []):
                    cluster = eks.describe_cluster(name=cluster_name)['cluster']

                    if cluster['status'] == 'ACTIVE':
                        tags = cluster.get('tags', {})
                        tag_keys = set(tags.keys())
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        ng_count = -1
                        try:
                            nodegroups = eks.list_nodegroups(clusterName=cluster_name)
                            ng_count = len(nodegroups.get('nodegroups', []))
                        except Exception:
                            pass

                        # ── Use modular rule ──
                        eks_verdict, eks_reason = classify_eks_cluster(ng_count)
                        eks_status = HygieneStatus(eks_verdict.value)
                        if eks_verdict == RuleVerdict.RISKY:
                            savings += 72.0

                        # EKS: $0.10/hr = $72/month per cluster
                        item = ResourceItem(
                            id=cluster['arn'],
                            name=cluster_name,
                            type=ResourceType.EKS_CLUSTER,
                            status=eks_status,
                            region=region,
                            cost_per_month=72.0,
                            reason=eks_reason,
                            metadata={
                                'Version': cluster.get('version'),
                                'CreatedAt': str(cluster.get('createdAt')),
                                'Status': cluster['status'],
                                'NodegroupCount': ng_count
                            },
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
            except Exception as eks_err:
                logger.error(f"EKS scan error: {eks_err}")

            # 2. ECS Clusters
            try:
                ecs = session.client('ecs')
                clusters = ecs.list_clusters()

                for cluster_arn in clusters.get('clusterArns', []):
                    cluster_detail = ecs.describe_clusters(clusters=[cluster_arn])['clusters'][0]

                    if cluster_detail['status'] == 'ACTIVE':
                        tags = cluster_detail.get('tags', [])
                        tag_keys = {t['key'] for t in tags}
                        missing = [rt for rt in required_tags if rt not in tag_keys]

                        # Zombie detection: empty clusters (85% certainty per zombie guide)
                        active_services = cluster_detail.get('activeServicesCount', 0)
                        running_tasks = cluster_detail.get('runningTasksCount', 0)
                        container_instances = cluster_detail.get('registeredContainerInstancesCount', 0)

                        # ── Use modular rule ──
                        ecs_verdict, ecs_reason = classify_ecs_cluster(
                            active_services=active_services,
                            running_tasks=running_tasks,
                            container_instances=container_instances,
                        )
                        ecs_status = HygieneStatus(ecs_verdict.value)

                        # ECS: Control plane free, but zombie clusters add clutter
                        item = ResourceItem(
                            id=cluster_arn,
                            name=cluster_detail.get('clusterName'),
                            type=ResourceType.ECS_CLUSTER,
                            status=ecs_status,
                            region=region,
                            cost_per_month=0.0,  # Free control plane
                            reason=ecs_reason,
                            metadata={
                                'ActiveServicesCount': active_services,
                                'RunningTasksCount': running_tasks,
                                'RegisteredContainerInstancesCount': container_instances,
                                'Status': cluster_detail['status']
                            },
                            is_compliant=len(missing) == 0,
                            missing_tags=missing
                        )
                        resources.append(item)
            except Exception as ecs_err:
                logger.error(f"ECS scan error: {ecs_err}")

            # 3. Auto Scaling Groups
            try:
                asg = session.client('autoscaling')
                groups = asg.describe_auto_scaling_groups()

                for group in groups.get('AutoScalingGroups', []):
                    tags = group.get('Tags', [])
                    tag_keys = {t['Key'] for t in tags}
                    missing = [rt for rt in required_tags if rt not in tag_keys]

                    # Zombie detection: zero-capacity ASGs (60% certainty per zombie guide)
                    desired = group.get('DesiredCapacity', 0)
                    min_size = group.get('MinSize', 0)
                    max_size = group.get('MaxSize', 0)
                    instance_count = len(group.get('Instances', []))

                    # ── Use modular rule ──
                    asg_verdict, asg_reason = classify_asg(
                        desired=desired,
                        min_size=min_size,
                        max_size=max_size,
                        instance_count=instance_count,
                    )
                    asg_status = HygieneStatus(asg_verdict.value)

                    # ASG: Free service (pay for instances)
                    item = ResourceItem(
                        id=group['AutoScalingGroupARN'],
                        name=group['AutoScalingGroupName'],
                        type=ResourceType.AUTO_SCALING_GROUP,
                        status=asg_status,
                        region=region,
                        cost_per_month=0.0,  # Free service
                        reason=asg_reason,
                        metadata={
                            'MinSize': min_size,
                            'MaxSize': max_size,
                            'DesiredCapacity': desired,
                            'Instances': instance_count
                        },
                        is_compliant=len(missing) == 0,
                        missing_tags=missing
                    )
                    resources.append(item)
            except Exception as asg_err:
                logger.error(f"Auto Scaling Groups scan error: {asg_err}")

        except Exception as e:
            logger.error(f"Compute resources scan error: {e}")

        return resources, savings

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
        

