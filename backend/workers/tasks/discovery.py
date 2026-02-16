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
    if not account.role_arn or not account.external_id:
        logger.warning(f"[WORK-DISC-01] Account {account.aws_account_id} missing role_arn or external_id, skipping")
        return {"clusters_found": 0, "instances_found": 0}
    
    try:
        # Assume IAM role via STS using platform credentials
        sts_client = _get_platform_sts_client(db)
        assumed_role = sts_client.assume_role(
            RoleArn=account.role_arn,
            RoleSessionName=f"SpotOptimizer-Discovery-{account.id}",
            ExternalId=account.external_id
        )

        credentials = assumed_role['Credentials']

        # Create AWS clients with assumed credentials
        ec2_client = boto3.client(
            'ec2',
            region_name=account.region or 'us-east-1',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

        eks_client = boto3.client(
            'eks',
            region_name=account.region or 'us-east-1',
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

        # Scan EKS clusters
        clusters_found = scan_eks_clusters(account, eks_client, db, credentials)

        # Scan EC2 instances
        instances_found = scan_ec2_instances(account, ec2_client, db)

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


def scan_eks_clusters(account: Account, eks_client, db: Session, credentials: Dict[str, str]) -> int:
    """
    Scan EKS clusters in the account

    Returns:
        Number of clusters found
    """
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
                    ce = boto3.client(
                        'ce',
                        region_name=account.region or 'us-east-1',
                        aws_access_key_id=credentials['AccessKeyId'],
                        aws_secret_access_key=credentials['SecretAccessKey'],
                        aws_session_token=credentials['SessionToken']
                    )
                    
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
            teaser_data = analyze_cluster_potential(
                cluster_name, 
                account.region or 'us-east-1', 
                ec2_client=boto3.client(
                    'ec2', 
                    region_name=cluster_data.get('arn').split(':')[3] if cluster_data.get('arn') else account.region,
                    aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken']
                ),
                credentials=credentials
            )
            potential_savings = teaser_data['potential_savings_monthly']
            logger.info(f"[Teaser] Cluster {cluster_name}: Potential Savings=${potential_savings:.2f}, OD Nodes={teaser_data['on_demand_node_count']}")

            # Fallback: Calculate cluster cost from instance pricing if Cost Explorer failed
            if total_cost == 0.0:
                logger.info(f"[WORK-DISC-01] Cost Explorer returned $0 for {cluster_name}, calculating from instance prices...")
                pricing_helper = get_pricing_helper()

                # Get all instances for this cluster
                cluster_instances_filter = [
                    {'Name': f'tag:kubernetes.io/cluster/{cluster_name}', 'Values': ['owned']},
                    {'Name': 'instance-state-name', 'Values': ['running']}
                ]

                instance_pages = ec2_client.get_paginator('describe_instances').paginate(Filters=cluster_instances_filter)
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

            # Check if cluster already exists
            existing = db.query(Cluster).filter(
                Cluster.account_id == account.id,
                Cluster.name == cluster_name
            ).first()

            if existing:
                # Update existing cluster metadata (but don't change status if it's ACTIVE)
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

        # --- Cleanup Logic: Remove clusters deleted from AWS ---
        # Get all clusters in DB for this account
        db_clusters = db.query(Cluster).filter(
            Cluster.account_id == account.id
        ).all()

        # Find clusters that exist in DB but NOT in AWS anymore
        discovered_cluster_names = set(cluster_names)
        clusters_to_cleanup = []

        for db_cluster in db_clusters:
            if db_cluster.name not in discovered_cluster_names:
                # Cluster not found in AWS
                # Check if agent is also offline (no heartbeat for 10+ minutes)
                if db_cluster.last_heartbeat:
                    minutes_since_heartbeat = (datetime.utcnow() - db_cluster.last_heartbeat).total_seconds() / 60
                    if minutes_since_heartbeat > 10:
                        clusters_to_cleanup.append(db_cluster)
                        logger.info(
                            f"[WORK-DISC-01] Cluster {db_cluster.name} not found in AWS "
                            f"and agent offline for {minutes_since_heartbeat:.1f} mins. "
                            f"Marking for cleanup."
                        )
                else:
                    # No heartbeat ever recorded, safe to cleanup
                    clusters_to_cleanup.append(db_cluster)
                    logger.info(
                        f"[WORK-DISC-01] Cluster {db_cluster.name} not found in AWS "
                        f"and never had agent connection. Marking for cleanup."
                    )

        # Remove clusters from database
        for cluster in clusters_to_cleanup:
            logger.info(f"[WORK-DISC-01] Removing deleted cluster: {cluster.name} (ID: {cluster.id})")

            # Also remove associated instances
            from backend.models.instance import Instance
            instances_deleted = db.query(Instance).filter(
                Instance.cluster_id == cluster.id
            ).delete()

            logger.info(f"[WORK-DISC-01] Removed {instances_deleted} instances for cluster {cluster.name}")

            # Remove the cluster
            db.delete(cluster)

        if clusters_to_cleanup:
            db.commit()
            logger.info(f"[WORK-DISC-01] Cleaned up {len(clusters_to_cleanup)} deleted clusters")

        return len(cluster_names)

    except ClientError as e:
        logger.error(f"[WORK-DISC-01] Failed to scan EKS clusters: {str(e)}")
        return 0


def scan_ec2_instances(account: Account, ec2_client, db: Session) -> int:
    """
    Scan EC2 instances in the account

    Returns:
        Number of instances found
    """
    try:
        # Get pricing helper for instance price calculation
        pricing_helper = get_pricing_helper()

        # Describe all instances using paginator
        paginator = ec2_client.get_paginator('describe_instances')
        instance_count = 0

        for page in paginator.paginate():
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

                    # Find associated cluster (via tags)
                    tags = instance_data.get('Tags', [])
                    cluster_name = None
                    for tag in tags:
                        if tag.get('Key') == 'eks:cluster-name':
                            cluster_name = tag.get('Value')
                            break

                    cluster_id = None
                    if cluster_name:
                        cluster = db.query(Cluster).filter(
                            Cluster.account_id == account.id,
                            Cluster.name == cluster_name
                        ).first()
                        if cluster:
                            cluster_id = cluster.id

                    # Check if instance already exists
                    existing = db.query(Instance).filter(
                        Instance.instance_id == instance_id
                    ).first()

                    if existing:
                        # Update existing instance
                        existing.account_id = account.id  # Ensure account_id is set
                        existing.cluster_id = cluster_id  # Update cluster_id (may be None for standalone)
                        existing.instance_type = instance_type
                        existing.lifecycle = lifecycle
                        existing.az = az
                        existing.price = hourly_price  # Store HOURLY price (converted from monthly)
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
                            memory_util=None
                        )
                        db.add(new_instance)

                    instance_count += 1

            db.commit()

        logger.info(f"[WORK-DISC-01] Found {instance_count} EC2 instances")
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
