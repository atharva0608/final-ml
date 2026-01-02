"""
Discovery Worker (WORK-DISC-01)
Scans AWS accounts for EC2 instances and EKS clusters every 5 minutes
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
from celery import Task
from sqlalchemy.orm import Session
import boto3
from botocore.exceptions import ClientError

from backend.workers import app
from backend.core.database import get_db
from backend.models.account import Account
from backend.models.cluster import Cluster
from backend.models.instance import Instance
from backend.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


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
            Account.status.in_(['active', 'scanning'])
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

            except Exception as e:
                logger.error(f"[WORK-DISC-01] Failed to scan account {account.id}: {str(e)}")
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

    try:
        # Assume IAM role via STS
        sts_client = boto3.client('sts')
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
        clusters_found = scan_eks_clusters(account, eks_client, db)

        # Scan EC2 instances
        instances_found = scan_ec2_instances(account, ec2_client, db)

        # Update account status
        if account.status == 'scanning':
            account.status = 'active'
            db.commit()

    except ClientError as e:
        logger.error(f"[WORK-DISC-01] AWS error scanning account {account.id}: {str(e)}")
        raise

    return {
        "clusters_found": clusters_found,
        "instances_found": instances_found
    }


def scan_eks_clusters(account: Account, eks_client, db: Session) -> int:
    """
    Scan EKS clusters in the account

    Returns:
        Number of clusters found
    """
    try:
        # List all clusters
        response = eks_client.list_clusters()
        cluster_names = response.get('clusters', [])

        logger.info(f"[WORK-DISC-01] Found {len(cluster_names)} EKS clusters")

        for cluster_name in cluster_names:
            # Get cluster details
            cluster_info = eks_client.describe_cluster(name=cluster_name)
            cluster_data = cluster_info['cluster']

            # Check if cluster already exists
            existing = db.query(Cluster).filter(
                Cluster.account_id == account.id,
                Cluster.name == cluster_name
            ).first()

            if existing:
                # Update existing cluster
                existing.status = cluster_data.get('status', 'ACTIVE')
                existing.k8s_version = cluster_data.get('version')
                existing.api_endpoint = cluster_data.get('endpoint')
                existing.updated_at = datetime.utcnow()
            else:
                # Create new cluster
                new_cluster = Cluster(
                    account_id=account.id,
                    name=cluster_name,
                    region=account.region or 'us-east-1',
                    vpc_id=cluster_data.get('resourcesVpcConfig', {}).get('vpcId'),
                    api_endpoint=cluster_data.get('endpoint'),
                    k8s_version=cluster_data.get('version'),
                    status='DISCOVERED'
                )
                db.add(new_cluster)

            db.commit()

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
        # Describe all instances
        response = ec2_client.describe_instances()
        instance_count = 0

        for reservation in response.get('Reservations', []):
            for instance_data in reservation.get('Instances', []):
                instance_id = instance_data.get('InstanceId')
                instance_type = instance_data.get('InstanceType')
                lifecycle = instance_data.get('InstanceLifecycle', 'on-demand').upper()
                az = instance_data.get('Placement', {}).get('AvailabilityZone')

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
                    existing.instance_type = instance_type
                    existing.lifecycle = lifecycle
                    existing.az = az
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new instance
                    new_instance = Instance(
                        cluster_id=cluster_id,
                        instance_id=instance_id,
                        instance_type=instance_type,
                        lifecycle=lifecycle,
                        az=az,
                        price=None,  # Will be updated by pricing collector
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
