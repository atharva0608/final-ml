"""
Discovery Worker (WORK-DISC-01)
Scans AWS accounts for EC2 instances and EKS clusters every 5 minutes
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from celery import Task
from sqlalchemy.orm import Session
import boto3
from botocore.exceptions import ClientError

from backend.workers import app
from backend.models.base import get_db
from backend.models.account import Account, AccountStatus
from backend.models.cluster import Cluster, ClusterStatus
from backend.models.instance import Instance, InstanceLifecycle
from backend.models.system_config import SystemConfig
from backend.models.system_config import SystemConfig
from backend.core.redis_client import get_redis_client
from backend.utils.pricing_helper import get_pricing_helper

logger = logging.getLogger(__name__)


def analyze_cluster_potential(cluster_name: str, region: str, ec2_client, credentials=None) -> Dict[str, Any]:
    """
    Perform a 'Shallow Scan' to estimate potential savings by moving On-Demand nodes to Spot.
    
    Returns:
        {
            'potential_savings_monthly': float,
            'on_demand_node_count': int,
            'spot_node_count': int,
            'inventory_summary': dict
        }
    """
    try:
        # 1. Start Analysis
        pricing = get_pricing_helper()
        
        # 2. Get all instances belonging to this cluster
        # Heuristic: EKS nodes usually have tag 'kubernetes.io/cluster/<name>' = 'owned'
        paginator = ec2_client.get_paginator('describe_instances')
        iterator = paginator.paginate(
            Filters=[
                {'Name': f'tag:kubernetes.io/cluster/{cluster_name}', 'Values': ['owned']},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        on_demand_nodes = []
        spot_nodes = []
        
        for page in iterator:
            for reservation in page['Reservations']:
                for instance in reservation['Instances']:
                    lc = instance.get('InstanceLifecycle', 'on-demand')
                    itype = instance.get('InstanceType')
                    az = instance.get('Placement', {}).get('AvailabilityZone')
                    
                    node_info = {'id': instance['InstanceId'], 'type': itype, 'az': az}
                    
                    if lc == 'spot':
                        spot_nodes.append(node_info)
                    else:
                        on_demand_nodes.append(node_info)

        # 3. Calculate Savings for On-Demand Nodes
        total_monthly_savings = 0.0
        
        # Cache spot prices to avoid spamming API
        spot_price_cache = {} # (type, az) -> price
        
        for node in on_demand_nodes:
            itype = node['type']
            az = node['az']
            
            # Get On-Demand Price
            od_price_monthly = pricing.get_ec2_price(region, itype)
            od_price_hourly = od_price_monthly / 730.0
            
            # Get Spot Price (Real-time market data)
            spot_price_hourly = 0.0
            cache_key = (itype, az)
            
            if cache_key in spot_price_cache:
                spot_price_hourly = spot_price_cache[cache_key]
            else:
                try:
                    # Get recent spot price (last 1 hour)
                    history = ec2_client.describe_spot_price_history(
                        InstanceTypes=[itype],
                        ProductDescriptions=['Linux/UNIX'],
                        AvailabilityZone=az,
                        StartTime=datetime.utcnow() - timedelta(hours=1),
                        MaxResults=1
                    )
                    if history['SpotPriceHistory']:
                        spot_price_hourly = float(history['SpotPriceHistory'][0]['SpotPrice'])
                        spot_price_cache[cache_key] = spot_price_hourly
                    else:
                        # Fallback: Assume 60% savings if no history
                        spot_price_hourly = od_price_hourly * 0.4 
                        spot_price_cache[cache_key] = spot_price_hourly
                except Exception as e:
                    logger.warning(f"Failed to fetch spot price for {itype} in {az}: {e}")
                    spot_price_hourly = od_price_hourly * 0.4 # Fallback
            
            # Add Buffer (we reserve 20% buffer in calculations usually, 
            # but for Teaser we show raw potential. Let's be conservative: 10% buffer)
            # Savings = (OD - Spot) * Hours
            # conservative_spot = spot * 1.1 ? No, let's show "Potential" (Optimistic but real)
            savings_hourly = max(0, od_price_hourly - spot_price_hourly)
            total_monthly_savings += (savings_hourly * 730)

        return {
            'potential_savings_monthly': round(total_monthly_savings, 2),
            'on_demand_node_count': len(on_demand_nodes),
            'spot_node_count': len(spot_nodes),
            'inventory_summary': {
                'total': len(on_demand_nodes) + len(spot_nodes),
                'by_type': list(set(n['type'] for n in on_demand_nodes))
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing potential for {cluster_name}: {e}", exc_info=True)
        return {
            'potential_savings_monthly': 0.0,
            'on_demand_node_count': 0,
            'spot_node_count': 0,
            'inventory_summary': {'error': str(e)}
        }



def _make_boto3_client(service: str, region: str, credentials):
    """
    Create a boto3 client, using assumed-role credentials when available
    or falling back to the env/instance-profile credential chain.
    """
    if credentials:
        return boto3.client(
            service,
            region_name=region,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
    return boto3.client(service, region_name=region)


def _get_platform_sts_client(db: Session):
    """
    Get an STS client using platform credentials stored in SystemConfig.
    This allows the discovery worker to assume roles in customer accounts.
    """
    access_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
    secret_key = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
    region = db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
    
    region_name = region.value if region and region.value else 'us-east-1'
    
    if access_key and secret_key and access_key.value and secret_key.value:
        logger.info("[WORK-DISC-01] Using platform credentials from SystemConfig")
        return boto3.client(
            'sts',
            aws_access_key_id=access_key.value,
            aws_secret_access_key=secret_key.value,
            region_name=region_name
        )
    else:
        # Fallback to environment variables / instance profile
        logger.warning("[WORK-DISC-01] Platform credentials not found in SystemConfig, falling back to env/instance profile")
        return boto3.client('sts', region_name=region_name)



@app.task(bind=True, name="workers.discovery.scan_all_accounts")
def discovery_worker_loop(self: Task) -> Dict[str, Any]:
    """
    Main discovery loop - scans all active AWS accounts

    Scheduled to run every 5 minutes via Celery Beat

    Returns:
        {
            "accounts_scanned": 5,
            "clusters_found": 12,
            "instances_found": 145,
            "duration_seconds": 23.5
        }
    """
    start_time = datetime.utcnow()
    logger.info(f"[WORK-DISC-01] Starting discovery worker loop")

    db = next(get_db())
    redis_client = get_redis_client()

    try:
        # Query all active accounts
        accounts = db.query(Account).filter(
            Account.status.in_([AccountStatus.ACTIVE, AccountStatus.SCANNING])
        ).all()

        logger.info(f"[WORK-DISC-01] Found {len(accounts)} active accounts to scan")

        total_clusters = 0
        total_instances = 0

        for account in accounts:
            try:
                # Scan this account
                result = scan_account(account, db, redis_client)
                total_clusters += result['clusters_found']
                total_instances += result['instances_found']
                
                # Update sync status on SUCCESS (Heartbeat feature)
                from backend.models.account import SyncStatus
                account.last_sync_at = datetime.utcnow()
                account.sync_status = SyncStatus.HEALTHY
                account.sync_error = None
                db.commit()

            except Exception as e:
                logger.error(f"[WORK-DISC-01] Failed to scan account {account.id}: {str(e)}")
                # Update sync status on FAILURE (Heartbeat feature)
                from backend.models.account import SyncStatus
                account.sync_status = SyncStatus.FAILED
                account.sync_error = str(e)[:500]  # Limit error message length
                db.commit()
                continue


        # ── Stale agent-node cleanup ─────────────────────────────────────
        # Instances created by the in-cluster agent (via /metrics) have
        # account_id=NULL and are invisible to the per-account stale-mark
        # pass above.  If an agent-reported node hasn't been updated in
        # 10 minutes it is almost certainly terminated (the agent sends
        # metrics every ~30s).  Mark it terminated so the UI stops
        # showing ghost nodes.
        try:
            _agent_stale_cutoff = datetime.utcnow() - timedelta(minutes=10)
            _agent_stale = db.query(Instance).filter(
                Instance.account_id.is_(None),
                Instance.state == 'running',
                Instance.updated_at < _agent_stale_cutoff,
            ).all()
            _agent_stale_count = 0
            for _as in _agent_stale:
                _as.state = 'terminated'
                _as.updated_at = datetime.utcnow()
                _agent_stale_count += 1
                logger.info(
                    f"[WORK-DISC-01] Marking agent-reported node "
                    f"{_as.instance_id or _as.node_name} as terminated "
                    f"(no metrics update for >10 min)"
                )
            if _agent_stale_count:
                db.commit()
                logger.info(
                    f"[WORK-DISC-01] Marked {_agent_stale_count} stale "
                    f"agent-reported node(s) as terminated"
                )
        except Exception as _agent_stale_err:
            logger.warning(
                f"[WORK-DISC-01] Agent stale-node cleanup failed: "
                f"{_agent_stale_err}"
            )

        duration = (datetime.utcnow() - start_time).total_seconds()

        result = {
            "accounts_scanned": len(accounts),
            "clusters_found": total_clusters,
            "instances_found": total_instances,
            "duration_seconds": round(duration, 1)
        }

        logger.info(
            f"[WORK-DISC-01] Discovery complete: {total_clusters} clusters, "
            f"{total_instances} instances in {duration:.1f}s"
        )

        return result

    finally:
        db.close()

# Alias for app.py compatibility
run_discovery = discovery_worker_loop


def scan_account(account: Account, db: Session, redis_client) -> Dict[str, int]:
    """
    Scan a single AWS account

    Args:
        account: Account object with AWS credentials
        db: Database session
        redis_client: Redis client

    Returns:
        {"clusters_found": 3, "instances_found": 45}
    """
    logger.info(f"[WORK-DISC-01] Scanning account {account.aws_account_id}")

    clusters_found = 0
    instances_found = 0

    # Validate account has required fields
    if not account.role_arn:
        logger.warning(f"[WORK-DISC-01] Account {account.aws_account_id} missing role_arn, skipping")
        return {"clusters_found": 0, "instances_found": 0}

    try:
        # Assume IAM role via STS using platform credentials
        sts_client = _get_platform_sts_client(db)

        # Build assume_role kwargs — ExternalId is required by trust policy but must not be empty
        assume_kwargs = {
            'RoleArn': account.role_arn,
            'RoleSessionName': f"SpotOptimizer-Discovery-{account.id}",
        }
        if account.external_id:
            assume_kwargs['ExternalId'] = account.external_id

        credentials = None
        try:
            assumed_role = sts_client.assume_role(**assume_kwargs)
            credentials = assumed_role['Credentials']
            logger.info(f"[WORK-DISC-01] Successfully assumed role for account {account.aws_account_id}")
        except ClientError as assume_err:
            error_code = assume_err.response['Error']['Code']
            if error_code in ('AccessDenied', 'AccessDeniedException'):
                # Check if same-account scenario — if so, fall back to env credentials directly
                try:
                    caller = sts_client.get_caller_identity()
                    _arn_parts = (account.role_arn or '').split(':')
                    role_account_id = _arn_parts[4] if len(_arn_parts) > 4 else ''
                    if caller['Account'] == role_account_id:
                        logger.warning(
                            f"[WORK-DISC-01] AssumeRole AccessDenied for same-account role "
                            f"({account.aws_account_id}). Falling back to env credentials directly. "
                            f"To fix permanently: attach sts:AssumeRole policy to your IAM user for "
                            f"role {account.role_arn}"
                        )
                        # credentials=None signals callers below to use boto3 default credential chain
                        credentials = None
                    else:
                        raise  # Cross-account failure — cannot bypass
                except Exception:
                    raise assume_err
            else:
                raise

        # Scan EKS clusters across ALL major regions (not just the account's home region)
        # EKS clusters can be in any region regardless of the account's configured region
        ALL_EKS_REGIONS = [
            "ap-south-1", "ap-southeast-1", "ap-southeast-2",
            "ap-northeast-1", "ap-northeast-2",
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "eu-west-1", "eu-west-2", "eu-central-1",
            "ca-central-1", "sa-east-1",
        ]
        # Put account's configured region first so it's found quickly
        account_region = account.region or 'us-east-1'
        regions_to_scan = [account_region] + [r for r in ALL_EKS_REGIONS if r != account_region]

        clusters_found = 0
        all_discovered_names: set = set()
        for scan_region in regions_to_scan:
            try:
                if credentials:
                    eks_client = boto3.client(
                        'eks',
                        region_name=scan_region,
                        aws_access_key_id=credentials['AccessKeyId'],
                        aws_secret_access_key=credentials['SecretAccessKey'],
                        aws_session_token=credentials['SessionToken']
                    )
                else:
                    eks_client = boto3.client('eks', region_name=scan_region)
                count, names = scan_eks_clusters(account, eks_client, db, credentials, region_override=scan_region)
                clusters_found += count
                all_discovered_names.update(names)
            except Exception as region_err:
                logger.debug(f"[WORK-DISC-01] Region {scan_region} not accessible: {region_err}")
                continue

        # Run cleanup ONCE after all regions — avoids false-positives for cross-region clusters
        _cleanup_deleted_clusters(account, db, all_discovered_names)

        # Scan EC2 instances across ALL regions we checked for EKS clusters
        instances_found = 0
        for scan_region in regions_to_scan:
            try:
                if credentials:
                    ec2_client = boto3.client(
                        'ec2',
                        region_name=scan_region,
                        aws_access_key_id=credentials['AccessKeyId'],
                        aws_secret_access_key=credentials['SecretAccessKey'],
                        aws_session_token=credentials['SessionToken']
                    )
                else:
                    ec2_client = boto3.client('ec2', region_name=scan_region)
                
                count = scan_ec2_instances(account, ec2_client, db)
                instances_found += count
            except Exception as region_err:
                logger.debug(f"[WORK-DISC-01] EC2 Region {scan_region} not accessible: {region_err}")
                continue

        # Update account status
        if account.status == AccountStatus.SCANNING:
            account.status = AccountStatus.ACTIVE
            db.commit()

    except ClientError as e:
        logger.error(f"[WORK-DISC-01] AWS error scanning account {account.id}: {str(e)}")
        raise

    return {
        "clusters_found": clusters_found,
        "instances_found": instances_found
    }


def scan_eks_clusters(account: Account, eks_client, db: Session, credentials: Dict[str, str], region_override: str = None) -> tuple:
    """
    Scan EKS clusters in a specific region.

    Returns:
        (count, list_of_cluster_names) — cleanup is handled by the caller after all regions
    """
    scan_region = region_override or account.region or 'us-east-1'
    try:
        # List all clusters using paginator
        paginator = eks_client.get_paginator('list_clusters')
        cluster_names = []
        for page in paginator.paginate():
            cluster_names.extend(page.get('clusters', []))

        logger.info(f"[WORK-DISC-01] Found {len(cluster_names)} EKS clusters")

        for cluster_name in cluster_names:
            # Get cluster details
            cluster_info = eks_client.describe_cluster(name=cluster_name)
            cluster_data = cluster_info['cluster']

            # --- Cost Insights ---
            total_cost = 0.0
            potential_savings = 0.0

            # Optimizing Cost Explorer Calls (Once per 24h)
            should_update_cost = True
            
            existing = db.query(Cluster).filter(
                Cluster.account_id == account.id,
                Cluster.name == cluster_name
            ).first()

            if existing and existing.last_cost_update:
                if (datetime.utcnow() - existing.last_cost_update).total_seconds() < 86400:
                    should_update_cost = False
                    # Preserve existing values if strictly necessary, but model update logic handles it
                    total_cost = float(existing.monthly_cost or 0)
                    potential_savings = float(existing.estimated_savings or 0)
                    logger.info(f"[WORK-DISC-01] Skipping cost update for {cluster_name} (Updated < 24h ago)")

            try:
                if should_update_cost:
                    # Initialize Cost Explorer
                    ce = _make_boto3_client('ce', account.region or 'us-east-1', credentials)
                    
                    # Get cost for last 30 days
                    end_date = datetime.utcnow().date()
                    start_date = end_date.replace(day=1) # Simplified to start of month for now
                    
                    # Format dates
                    start_str = start_date.strftime('%Y-%m-%d')
                    end_str = end_date.strftime('%Y-%m-%d')
                    
                    # Fetch cost associated with this cluster (by tag)
                    cost_response = ce.get_cost_and_usage(
                        TimePeriod={'Start': start_str, 'End': end_str},
                        Granularity='MONTHLY',
                        Metrics=['UnblendedCost'],
                        Filter={
                            'Tags': {
                                'Key': 'eks:cluster-name',
                                'Values': [cluster_name]
                            }
                        }
                    )
                    
                    # Extract cost
                    if cost_response['ResultsByTime']:
                        amount = cost_response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
                        total_cost = float(amount)
                        
                        # Heuristic: 40% savings potential on Spot
                        # potential_savings = total_cost * 0.40
                        # REPLACED BY SHALLOW SCAN (Phase 2)
                        pass
                        
                    logger.info(f"[WORK-DISC-01] Cluster {cluster_name}: Cost=${total_cost:.2f}")

            except Exception as e:
                logger.warning(f"[WORK-DISC-01] Failed to fetch costs for {cluster_name}: {e}")

            # --- Shallow Scan for Teaser (Real Savings) ---
            cluster_region = cluster_data.get('arn').split(':')[3] if cluster_data.get('arn') else scan_region
            teaser_data = analyze_cluster_potential(
                cluster_name,
                cluster_region,
                ec2_client=_make_boto3_client('ec2', cluster_region, credentials),
                credentials=credentials
            )
            potential_savings = teaser_data['potential_savings_monthly']
            logger.info(f"[Teaser] Cluster {cluster_name}: Potential Savings=${potential_savings:.2f}, OD Nodes={teaser_data['on_demand_node_count']}")

            # Fallback: Calculate cluster cost from instance pricing if Cost Explorer failed
            if total_cost == 0.0:
                logger.info(f"[WORK-DISC-01] Cost Explorer returned $0 for {cluster_name}, calculating from instance prices...")
                pricing_helper = get_pricing_helper()

                # Create EC2 client for instance pricing calculation
                pricing_region = cluster_data.get('arn').split(':')[3] if cluster_data.get('arn') else (account.region or 'us-east-1')
                ec2_client_pricing = _make_boto3_client('ec2', pricing_region, credentials)

                # Get all instances for this cluster
                cluster_instances_filter = [
                    {'Name': f'tag:kubernetes.io/cluster/{cluster_name}', 'Values': ['owned']},
                    {'Name': 'instance-state-name', 'Values': ['running']}
                ]

                instance_pages = ec2_client_pricing.get_paginator('describe_instances').paginate(Filters=cluster_instances_filter)
                cluster_monthly_cost = 0.0

                for page in instance_pages:
                    for reservation in page['Reservations']:
                        for inst in reservation['Instances']:
                            inst_type = inst.get('InstanceType')
                            inst_price = pricing_helper.get_ec2_price(account.region or 'us-east-1', inst_type)
                            cluster_monthly_cost += inst_price
                            logger.debug(f"[WORK-DISC-01] Adding {inst_type}: ${inst_price:.2f}")

                total_cost = cluster_monthly_cost
                logger.info(f"[WORK-DISC-01] Calculated cluster cost from instances: ${total_cost:.2f}/month")

            # Check if cluster already exists — use ARN as primary key (globally unique),
            # then fall back to (account_id, name) for backward compatibility.
            _cluster_arn = cluster_data.get('arn')
            existing = None
            if _cluster_arn:
                existing = db.query(Cluster).filter(
                    Cluster.arn == _cluster_arn
                ).first()
            if not existing:
                existing = db.query(Cluster).filter(
                    Cluster.account_id == account.id,
                    Cluster.name == cluster_name
                ).first()

            if existing:
                # If cluster was dismissed earlier, auto-revive when it is seen in AWS again.
                if getattr(existing, 'is_dismissed', False):
                    existing.is_dismissed = False
                    if existing.agent_installed == 'Y' and existing.last_heartbeat:
                        existing.status = ClusterStatus.ACTIVE
                    else:
                        existing.status = ClusterStatus.DISCOVERED
                    logger.info(
                        f"[WORK-DISC-01] Revived dismissed cluster {cluster_name} "
                        f"({existing.id}) after AWS rediscovery"
                    )

                # If cluster was DEGRADED (missing from AWS previously), restore it
                if existing.status == ClusterStatus.DEGRADED:
                    if existing.agent_installed == 'Y' and existing.last_heartbeat:
                        existing.status = ClusterStatus.ACTIVE
                    else:
                        existing.status = ClusterStatus.DISCOVERED
                    logger.info(f"[WORK-DISC-01] Cluster {cluster_name} restored from DEGRADED → {existing.status.value}")

                # Update existing cluster metadata (but don't change status if it's ACTIVE)
                # Sync ARN and name in case either changed (e.g., ARN found via name lookup)
                if _cluster_arn and existing.arn != _cluster_arn:
                    existing.arn = _cluster_arn
                if existing.name != cluster_name:
                    existing.name = cluster_name
                existing.version = cluster_data.get('version')
                existing.endpoint = cluster_data.get('endpoint')
                existing.ca_data = cluster_data.get('certificateAuthority', {}).get('data')
                existing.monthly_cost = int(total_cost)
                existing.estimated_savings = int(potential_savings)
                
                # Update Teaser Fields
                existing.potential_savings_monthly = teaser_data['potential_savings_monthly']
                existing.on_demand_node_count = teaser_data['on_demand_node_count']
                existing.spot_count = teaser_data['spot_node_count'] # Mapping to existing field + new concept
                existing.inventory_summary = teaser_data['inventory_summary']
                existing.last_assessed = datetime.utcnow()
                
                existing.updated_at = datetime.utcnow()
                # Self-healing: Update region if missing
                if not existing.region and cluster_data.get('arn'):
                    existing.region = cluster_data.get('arn').split(':')[3]
                    
                if should_update_cost:
                    existing.last_cost_update = datetime.utcnow()
            else:
                # If this ARN was previously dismissed, revive the same row.
                _dismissed = db.query(Cluster).filter(
                    Cluster.account_id == account.id,
                    Cluster.arn == cluster_data.get('arn'),
                    Cluster.is_dismissed == True,
                ).first()
                if _dismissed:
                    _dismissed.is_dismissed = False
                    _dismissed.name = cluster_name
                    _dismissed.version = cluster_data.get('version')
                    _dismissed.endpoint = cluster_data.get('endpoint')
                    _dismissed.ca_data = cluster_data.get('certificateAuthority', {}).get('data')
                    _dismissed.region = (
                        cluster_data.get('arn').split(':')[3]
                        if cluster_data.get('arn') else (account.region or 'us-east-1')
                    )
                    _dismissed.monthly_cost = int(total_cost)
                    _dismissed.estimated_savings = int(potential_savings)
                    _dismissed.potential_savings_monthly = teaser_data['potential_savings_monthly']
                    _dismissed.on_demand_node_count = teaser_data['on_demand_node_count']
                    _dismissed.spot_count = teaser_data['spot_node_count']
                    _dismissed.inventory_summary = teaser_data['inventory_summary']
                    _dismissed.last_assessed = datetime.utcnow()
                    _dismissed.updated_at = datetime.utcnow()
                    _dismissed.status = (
                        ClusterStatus.ACTIVE
                        if _dismissed.agent_installed == 'Y' and _dismissed.last_heartbeat
                        else ClusterStatus.DISCOVERED
                    )
                    if should_update_cost:
                        _dismissed.last_cost_update = datetime.utcnow()
                    existing = _dismissed
                    logger.info(
                        f"[WORK-DISC-01] Revived previously dismissed ARN for "
                        f"{cluster_name} ({_dismissed.id})"
                    )
                else:

                    # Create new cluster with DISCOVERED status
                    import uuid
                    new_cluster = Cluster(
                        id=str(uuid.uuid4()),
                        account_id=account.id,
                        name=cluster_name,
                        arn=cluster_data.get('arn'),
                        region=cluster_data.get('arn').split(':')[3] if cluster_data.get('arn') else (account.region or 'us-east-1'),
                        endpoint=cluster_data.get('endpoint'),
                        ca_data=cluster_data.get('certificateAuthority', {}).get('data'),
                        version=cluster_data.get('version'),
                        status=ClusterStatus.DISCOVERED,

                        monthly_cost=int(total_cost),
                        estimated_savings=int(potential_savings),

                        # Teaser Fields
                        potential_savings_monthly=teaser_data['potential_savings_monthly'],
                        on_demand_node_count=teaser_data['on_demand_node_count'],
                        spot_count=teaser_data['spot_node_count'],
                        inventory_summary=teaser_data['inventory_summary'],
                        last_assessed=datetime.utcnow(),

                        last_cost_update=datetime.utcnow() if should_update_cost else None
                    )
                    db.add(new_cluster)

            db.commit()

            # §2.3 (changes.md): Set discovery last-updated key per cluster so the
            # auto_rebalancer can skip cycles where DB data is older than 5 minutes.
            # TTL=600s: if discovery stops running, the key expires and rebalancer
            # falls back to acting on DB data (fail-open, not fail-closed).
            try:
                from backend.core.redis_client import get_redis_client as _get_disc_redis
                _disc_redis = _get_disc_redis()
                if _disc_redis:
                    _synced_id = existing.id if existing else new_cluster.id
                    _disc_redis.setex(
                        f"spot:discovery_last_updated:{_synced_id}",
                        600,
                        datetime.utcnow().isoformat(),
                    )
            except Exception:
                pass

        # Return count + names; cleanup runs in scan_account after ALL regions are scanned
        return len(cluster_names), cluster_names

    except ClientError as e:
        logger.error(f"[WORK-DISC-01] Failed to scan EKS clusters: {str(e)}")
        return 0, []


def _cleanup_deleted_clusters(account: Account, db: Session, all_discovered_names: set) -> None:
    """
    Handle clusters from the DB that no longer exist in AWS across ALL regions.
    - Agent-installed clusters → set DEGRADED (preserve data, show warning in UI)
    - Non-agent clusters without user action → delete (auto-clear noise)
    - Dismissed clusters → skip entirely
    Must be called once after all regions have been scanned.
    """
    db_clusters = db.query(Cluster).filter(Cluster.account_id == account.id).all()
    clusters_to_delete = []
    clusters_to_degrade = []

    for db_cluster in db_clusters:
        # Skip dismissed clusters — user already removed them
        if getattr(db_cluster, 'is_dismissed', False):
            continue

        # Skip clusters that were found in AWS
        if db_cluster.name in all_discovered_names:
            continue

        # Grace period: never touch clusters created < 60 minutes ago
        if db_cluster.created_at:
            minutes_since_created = (datetime.utcnow() - db_cluster.created_at).total_seconds() / 60
            if minutes_since_created < 60:
                logger.info(
                    f"[WORK-DISC-01] Cluster {db_cluster.name} not in AWS but only "
                    f"{minutes_since_created:.1f} mins old — skipping cleanup."
                )
                continue

        # ── Agent-installed clusters → DEGRADED (don't delete) ──
        if db_cluster.agent_installed == 'Y':
            if db_cluster.status != ClusterStatus.DEGRADED:
                clusters_to_degrade.append(db_cluster)
                logger.info(
                    f"[WORK-DISC-01] Agent cluster {db_cluster.name} not found in AWS "
                    f"— marking DEGRADED (preserving data)."
                )
            continue

        # ── Non-agent clusters → auto-clear ──
        # Small grace: keep if heartbeat within last 10 min (unlikely for non-agent but safe)
        if db_cluster.last_heartbeat:
            minutes_since_heartbeat = (datetime.utcnow() - db_cluster.last_heartbeat).total_seconds() / 60
            if minutes_since_heartbeat <= 10:
                continue

        clusters_to_delete.append(db_cluster)
        logger.info(f"[WORK-DISC-01] Non-agent cluster {db_cluster.name} not in AWS — scheduling deletion.")

    # Apply DEGRADED status
    for cluster in clusters_to_degrade:
        cluster.status = ClusterStatus.DEGRADED
        cluster.updated_at = datetime.utcnow()
        logger.info(f"[WORK-DISC-01] Set cluster {cluster.name} to DEGRADED")

    # Delete non-agent orphan clusters
    for cluster in clusters_to_delete:
        from backend.models.instance import Instance
        db.query(Instance).filter(Instance.cluster_id == cluster.id).delete()
        db.delete(cluster)
        logger.info(f"[WORK-DISC-01] Removed non-agent cluster: {cluster.name}")

    if clusters_to_degrade or clusters_to_delete:
        db.commit()


def scan_ec2_instances(account: Account, ec2_client, db: Session) -> int:
    """
    Scan EC2 instances in the account

    Returns:
        Number of instances found
    """
    try:
        # Get pricing helper for instance price calculation
        pricing_helper = get_pricing_helper()

        # RC3: Redis client for consecutive-OD downgrade guard
        try:
            _rc3_redis = get_redis_client()
        except Exception:
            _rc3_redis = None
        _RC3_THRESHOLD = 3  # require N consecutive OD scans before allowing SPOT→OD downgrade
        _RC3_TTL = 1800     # Redis key TTL: 30 min (3 × 10 min discovery cycle)

        # Describe RUNNING instances only — non-running instances are irrelevant
        # for node visualization and can clutter the DB with stale records.
        paginator = ec2_client.get_paginator('describe_instances')
        instance_count = 0
        # RC4 fix: track every instance_id seen this scan.
        # After the loop we mark any DB record NOT in this set as terminated,
        # so ghost "running" records disappear automatically.
        _seen_instance_ids: set = set()

        for page in paginator.paginate(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
        ):
            for reservation in page.get('Reservations', []):
                for instance_data in reservation.get('Instances', []):
                    instance_id = instance_data.get('InstanceId')
                    instance_type = instance_data.get('InstanceType')
                    # AWS returns 'spot' or None (for on-demand), normalize to enum
                    raw_lifecycle = instance_data.get('InstanceLifecycle', 'on-demand')
                    lifecycle = InstanceLifecycle.SPOT if raw_lifecycle == 'spot' else InstanceLifecycle.ON_DEMAND
                    az = instance_data.get('Placement', {}).get('AvailabilityZone')

                    # Calculate instance price (uses fallback if AWS pricing API unavailable)
                    # Note: pricing_helper returns MONTHLY price, but we store HOURLY price in database
                    try:
                        monthly_price = pricing_helper.get_ec2_price(account.region or 'us-east-1', instance_type)
                        hourly_price = monthly_price / 730.0  # Convert monthly to hourly
                        logger.debug(f"[WORK-DISC-01] Instance {instance_id} ({instance_type}): ${monthly_price:.2f}/month (${hourly_price:.4f}/hour)")
                    except Exception as e:
                        logger.warning(f"[WORK-DISC-01] Failed to get pricing for {instance_type}: {e}")
                        monthly_price = 50.00  # Ultimate fallback
                        hourly_price = monthly_price / 730.0

                    # Find associated cluster and platform tags
                    tags = instance_data.get('Tags', [])
                    cluster_name = None
                    launched_by = None
                    for tag in tags:
                        key = tag.get('Key', '')
                        val = tag.get('Value', '')
                        
                        if key == 'eks:cluster-name':
                            cluster_name = val
                        elif key.startswith('kubernetes.io/cluster/') and not cluster_name:
                            cluster_name = key.replace('kubernetes.io/cluster/', '')
                        elif key in ('spot-optimizer:launched-by', 'spot-optimizer/launched-by'):
                            launched_by = val
                            
                        # If we have both, we can break early, but let's just loop through all tags (usually <10)

                    cluster_id = None
                    if cluster_name:
                        cluster = db.query(Cluster).filter(
                            Cluster.account_id == account.id,
                            Cluster.name == cluster_name
                        ).first()
                        if cluster:
                            cluster_id = cluster.id

                    # Track for stale-mark logic (RC4 fix)
                    _seen_instance_ids.add(instance_id)

                    # Check if instance already exists
                    # Issue #11: lock row before updating lifecycle/state fields
                    existing = db.query(Instance).filter(
                        Instance.instance_id == instance_id
                    ).with_for_update().first()

                    if existing:
                        # Update existing instance
                        existing.account_id = account.id  # Ensure account_id is set
                        existing.cluster_id = cluster_id  # Update cluster_id (may be None for standalone)
                        existing.instance_type = instance_type
                        # RC3 guard: smarter SPOT→OD downgrade using Redis consecutive-count.
                        # AWS omits InstanceLifecycle for both OD instances AND for some
                        # Karpenter-provisioned spot nodes. A single OD observation is not
                        # conclusive. We require _RC3_THRESHOLD (3) consecutive scans that
                        # return OD (or omit lifecycle) before allowing a SPOT→OD downgrade.
                        # A confirmed SPOT reading resets the counter immediately.
                        #
                        # SPOT ASSERTION GUARD: If the auto-rebalancer pre-registered this
                        # instance as spot (spot:asserted_spot:{instance_id} in Redis with 5m TTL),
                        # override the AWS API response and treat as SPOT for the assertion window.
                        # This prevents newly-launched spot instances from being downgraded to OD
                        # while AWS API is still propagating the InstanceLifecycle field.
                        if lifecycle != InstanceLifecycle.SPOT and _rc3_redis:
                            try:
                                _assert_key = f"spot:asserted_spot:{instance_id}"
                                if _rc3_redis.exists(_assert_key):
                                    lifecycle = InstanceLifecycle.SPOT
                            except Exception:
                                pass
                        #
                        # Counter key: "rc3:od_streak:{instance_id}"  (int, TTL=30 min)
                        _rc3_key = f"rc3:od_streak:{instance_id}"
                        if lifecycle == InstanceLifecycle.SPOT:
                            # Confirmed SPOT — reset streak counter and update lifecycle
                            if _rc3_redis:
                                try:
                                    _rc3_redis.delete(_rc3_key)
                                except Exception:
                                    pass
                            existing.lifecycle = lifecycle
                        elif existing.lifecycle == InstanceLifecycle.ON_DEMAND:
                            # Already OD — always update (no downgrade risk).
                            # Issue #10 / Task 2.2: Also reset RC3 streak counter on
                            # confirmed OD read. Without this, a stale counter can persist
                            # across lifecycle transitions (OD→SPOT→OD) and either fire
                            # prematurely or expire silently without triggering downgrade.
                            if _rc3_redis:
                                try:
                                    _rc3_redis.delete(_rc3_key)
                                except Exception:
                                    pass
                            existing.lifecycle = lifecycle
                        elif existing.lifecycle == InstanceLifecycle.SPOT:
                            # Potential SPOT→OD downgrade — use consecutive-count gate
                            _allow_downgrade = False
                            if _rc3_redis:
                                try:
                                    _streak = _rc3_redis.incr(_rc3_key)
                                    _rc3_redis.expire(_rc3_key, _RC3_TTL)
                                    if int(_streak) >= _RC3_THRESHOLD:
                                        _allow_downgrade = True
                                        _rc3_redis.delete(_rc3_key)
                                        logger.info(
                                            f"[discovery] RC3: allowing SPOT→OD downgrade for "
                                            f"{instance_id} after {_streak} consecutive OD observations"
                                        )
                                    else:
                                        logger.debug(
                                            f"[discovery] RC3: deferring SPOT→OD downgrade for "
                                            f"{instance_id} (streak {_streak}/{_RC3_THRESHOLD})"
                                        )
                                except Exception:
                                    pass  # Redis error — keep SPOT (safe default)
                            else:
                                # No Redis — fall back to single-observation (old behaviour)
                                _allow_downgrade = True
                            if _allow_downgrade:
                                existing.lifecycle = lifecycle
                        else:
                            # lifecycle is None in DB — always accept whatever AWS returned
                            existing.lifecycle = lifecycle
                        existing.az = az
                        existing.state = 'running'  # Confirm still running (was seen in scan)
                        existing.price = hourly_price  # Store HOURLY price (converted from monthly)
                        existing.launched_by = launched_by  # Update platform tag
                        existing.updated_at = datetime.utcnow()
                    else:
                        # Create new instance
                        new_instance = Instance(
                            account_id=account.id,  # Direct account link for standalone instances
                            cluster_id=cluster_id,  # May be None for standalone instances
                            instance_id=instance_id,
                            instance_type=instance_type,
                            lifecycle=lifecycle,
                            az=az,
                            price=hourly_price,  # Store HOURLY price (converted from monthly)
                            cpu_util=None,  # Will be updated by metrics collection
                            memory_util=None,
                            launched_by=launched_by
                        )
                        db.add(new_instance)

                    instance_count += 1

            db.commit()

        logger.info(f"[WORK-DISC-01] Found {instance_count} EC2 instances")

        # ── RC4 fix: mark stale DB instances as terminated ────────────────────
        # Any instance that was NOT seen in this scan but is still state='running'
        # in the DB must have been terminated in AWS.  Mark it terminated so the
        # dedup + visualization code stops showing it as a live node.
        try:
            # Issue #11: lock rows before bulk state change to prevent dual-mark
            _stale_qs = db.query(Instance).filter(
                Instance.account_id == account.id,
                Instance.state == 'running',
            ).with_for_update().all()
            _stale_count = 0
            for _s in _stale_qs:
                if (
                    _s.instance_id
                    and _s.instance_id.startswith('i-')  # only real EC2 IDs
                    and _s.instance_id not in _seen_instance_ids
                ):
                    _s.state = 'terminated'
                    _s.updated_at = datetime.utcnow()
                    _stale_count += 1
                    logger.info(
                        f"[WORK-DISC-01] Marking {_s.instance_id} as terminated "
                        f"(not found in running EC2 scan)"
                    )
            if _stale_count:
                db.commit()
                logger.info(
                    f"[WORK-DISC-01] Marked {_stale_count} ghost instance(s) as terminated"
                )
        except Exception as _stale_err:
            logger.warning(f"[WORK-DISC-01] Stale-mark pass failed: {_stale_err}")

        # ── Clean up terminated instances older than 30 min ───────────────────
        try:
            _cutoff = datetime.utcnow() - timedelta(minutes=5)
            _terminated = db.query(Instance).filter(
                Instance.account_id == account.id,
                Instance.state == 'terminated',
                Instance.updated_at <= _cutoff,
            ).all()
            if _terminated:
                for _t in _terminated:
                    db.delete(_t)
                db.commit()
                logger.info(f"[WORK-DISC-01] Deleted {len(_terminated)} terminated instance(s) (>30min old)")
        except Exception as _cleanup_err:
            logger.warning(f"[WORK-DISC-01] Terminated instance cleanup failed: {_cleanup_err}")

        return instance_count

    except ClientError as e:
        logger.error(f"[WORK-DISC-01] Failed to scan EC2 instances: {str(e)}")
        return 0


@app.task(name="workers.discovery.stream_progress")
def stream_discovery_status(account_id: str) -> Dict[str, Any]:
    """
    Stream discovery progress updates (for WebSocket)

    Args:
        account_id: Account UUID

    Returns:
        Progress status
    """
    # This would stream to WebSocket in production
    # For now, return static progress
    return {
        "account_id": account_id,
        "status": "in_progress",
        "progress": 75,
        "clusters_found": 3,
        "instances_found": 45
    }
