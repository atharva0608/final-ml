"""
Cloud Discovery Worker

Asynchronous worker that scans AWS accounts for EC2 instances and EKS clusters.
Runs as a background task after IAM role verification succeeds.

Flow:
1. Assume client's IAM role using STS
2. Scan EC2 instances across regions
3. Identify EKS clusters from tags
4. Upsert findings into database
5. Update account status from 'connected' to 'active'
"""

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from typing import Optional, Dict, List
import logging

from database.connection import SessionLocal
from database.models import Account, Instance
from utils.system_logger import SystemLogger

logger = logging.getLogger("worker.discovery")


def get_assumed_session(role_arn: str, external_id: str, region: str = 'us-east-1'):
    """
    Assume client's IAM role and return boto3 session

    Args:
        role_arn: IAM Role ARN to assume
        external_id: External ID for role assumption
        region: AWS region for session

    Returns:
        boto3.Session with assumed role credentials

    Raises:
        ClientError: If role assumption fails
    """
    try:
        sts = boto3.client('sts', region_name=region)
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="AtharvaDiscoveryWorker",
            ExternalId=external_id,
            DurationSeconds=3600  # 1 hour
        )

        creds = response['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=region
        )
    except ClientError as e:
        logger.error(f"Failed to assume role {role_arn}: {e}")
        raise


def scan_ec2_instances(session: boto3.Session, account_id: int, db: Session, region: str = 'us-east-1') -> int:
    """
    Scan EC2 instances in the specified region

    Args:
        session: Boto3 session with assumed credentials
        account_id: Database account ID
        db: Database session
        region: AWS region to scan

    Returns:
        Number of instances discovered
    """
    instance_count = 0

    try:
        ec2 = session.client('ec2', region_name=region)

        # Scan running and pending instances
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'instance-state-name', 'Values': ['running', 'pending', 'stopping', 'stopped']}
            ]
        )

        for reservation in response.get('Reservations', []):
            for inst_data in reservation.get('Instances', []):
                instance_id = inst_data.get('InstanceId')
                instance_type = inst_data.get('InstanceType')
                launch_time = inst_data.get('LaunchTime')
                state = inst_data.get('State', {}).get('Name', 'unknown')
                lifecycle = inst_data.get('InstanceLifecycle', 'on-demand')

                # Extract tags
                tags = {t['Key']: t['Value'] for t in inst_data.get('Tags', [])}

                # Identify cluster association from tags
                cluster_name = (
                    tags.get('kubernetes.io/cluster/name') or
                    tags.get('eks:cluster-name') or
                    tags.get('eks:nodegroup-name') or
                    tags.get('aws:autoscaling:groupName')
                )

                # Determine authorization status from tags
                managed_by = tags.get('ManagedBy', '').lower()
                auth_status = 'authorized' if managed_by == 'spotoptimizer' else 'unauthorized'

                # Check if instance already exists
                existing = db.query(Instance).filter(
                    Instance.instance_id == instance_id
                ).first()

                if existing:
                    # Update existing instance
                    existing.instance_type = instance_type
                    existing.region = region
                    existing.state = state
                    existing.lifecycle = lifecycle
                    existing.auth_status = auth_status
                    existing.updated_at = datetime.utcnow()

                    # Update metadata with tags
                    if not existing.instance_metadata:
                        existing.instance_metadata = {}
                    existing.instance_metadata.update({
                        'tags': tags,
                        'cluster_hint': cluster_name,
                        'last_discovered': datetime.utcnow().isoformat()
                    })
                else:
                    # Create new instance record
                    new_instance = Instance(
                        instance_id=instance_id,
                        account_id=account_id,
                        instance_type=instance_type,
                        region=region,
                        state=state,
                        lifecycle=lifecycle,
                        auth_status=auth_status,
                        is_active=(state in ['running', 'pending']),
                        launched_at=launch_time,
                        instance_metadata={
                            'tags': tags,
                            'cluster_hint': cluster_name,
                            'discovered_at': datetime.utcnow().isoformat(),
                            'availability_zone': inst_data.get('Placement', {}).get('AvailabilityZone'),
                            'vpc_id': inst_data.get('VpcId'),
                            'subnet_id': inst_data.get('SubnetId')
                        }
                    )
                    db.add(new_instance)
                    instance_count += 1

        db.commit()
        return instance_count

    except ClientError as e:
        logger.error(f"EC2 API error in region {region}: {e}")
        db.rollback()
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error while saving instances: {e}")
        db.rollback()
        raise


def run_initial_discovery(account_db_id: int):
    """
    Main discovery worker function - runs as FastAPI background task

    This function:
    1. Retrieves account details from database
    2. Assumes the client's IAM role
    3. Scans EC2 instances across configured regions
    4. Updates database with findings
    5. Transitions account status from 'connected' to 'active'

    Args:
        account_db_id: Database ID of the account to scan
    """
    db = SessionLocal()
    sys_logger = None

    try:
        # 1. Get Account Details
        account = db.query(Account).filter(Account.id == account_db_id).first()
        if not account:
            logger.error(f"Account {account_db_id} not found in database")
            return

        # Initialize system logger
        sys_logger = SystemLogger('discovery', db=db)
        sys_logger.info(
            f"Starting discovery for account {account.account_name} (AWS Account: {account.account_id})",
            details={'account_id': account_db_id, 'aws_account_id': account.account_id}
        )

        # 2. Validate account is in correct state
        if account.status not in ['connected', 'pending']:
            sys_logger.warning(
                f"Account status is '{account.status}', expected 'connected' or 'pending'",
                details={'account_id': account_db_id}
            )
            return

        # 3. Assume IAM Role
        try:
            session = get_assumed_session(
                role_arn=account.role_arn,
                external_id=account.external_id,
                region=account.region or 'us-east-1'
            )
        except ClientError as e:
            sys_logger.error(
                f"Failed to assume role: {e}",
                details={'account_id': account_db_id, 'role_arn': account.role_arn}
            )
            account.status = 'failed'
            account.updated_at = datetime.utcnow()
            if not account.account_metadata:
                account.account_metadata = {}
            account.account_metadata['last_error'] = str(e)
            account.account_metadata['last_error_time'] = datetime.utcnow().isoformat()
            db.commit()
            return

        # 4. Scan Resources
        total_instances = 0
        regions_to_scan = [account.region] if account.region else ['us-east-1']

        for region in regions_to_scan:
            try:
                count = scan_ec2_instances(session, account_db_id, db, region)
                total_instances += count
                sys_logger.info(
                    f"Scanned region {region}: found {count} instances",
                    details={'region': region, 'instance_count': count}
                )
            except Exception as e:
                sys_logger.error(
                    f"Failed to scan region {region}: {e}",
                    details={'region': region, 'error': str(e)}
                )
                # Continue scanning other regions even if one fails
                continue

        # 5. Update Account Status
        account.status = 'active'  # Unlock client dashboard
        account.is_active = True
        account.updated_at = datetime.utcnow()

        # Update metadata
        if not account.account_metadata:
            account.account_metadata = {}
        account.account_metadata.update({
            'last_scan': datetime.utcnow().isoformat(),
            'instances_discovered': total_instances,
            'regions_scanned': regions_to_scan,
            'scan_status': 'completed'
        })

        db.commit()

        sys_logger.success(
            f"Discovery completed successfully: {total_instances} instances found",
            details={
                'account_id': account_db_id,
                'total_instances': total_instances,
                'regions': regions_to_scan
            }
        )

        logger.info(f"✅ Discovery Complete for Account {account_db_id}: {total_instances} instances")

    except Exception as e:
        logger.error(f"Discovery worker failed for account {account_db_id}: {e}", exc_info=True)

        # Update account to failed state
        try:
            account = db.query(Account).filter(Account.id == account_db_id).first()
            if account:
                account.status = 'failed'
                account.updated_at = datetime.utcnow()
                if not account.account_metadata:
                    account.account_metadata = {}
                account.account_metadata['last_error'] = str(e)
                account.account_metadata['last_error_time'] = datetime.utcnow().isoformat()
                db.commit()

                if sys_logger:
                    sys_logger.error(
                        f"Discovery failed: {e}",
                        details={'account_id': account_db_id, 'error': str(e)}
                    )
        except Exception as commit_error:
            logger.error(f"Failed to update account status: {commit_error}")

    finally:
        db.close()
        if sys_logger:
            sys_logger.close()


def trigger_rediscovery(account_db_id: int):
    """
    Trigger a re-scan of an existing account

    This can be called periodically or on-demand to refresh instance data.
    Unlike initial discovery, this doesn't change account status.

    Args:
        account_db_id: Database ID of the account to re-scan
    """
    db = SessionLocal()
    sys_logger = SystemLogger('discovery', db=db)

    try:
        account = db.query(Account).filter(Account.id == account_db_id).first()
        if not account or account.status != 'active':
            sys_logger.warning(
                f"Cannot re-scan account {account_db_id}: not in active state",
                details={'account_id': account_db_id}
            )
            return

        sys_logger.info(
            f"Starting re-discovery for account {account.account_name}",
            details={'account_id': account_db_id}
        )

        # Assume role and scan
        session = get_assumed_session(
            role_arn=account.role_arn,
            external_id=account.external_id,
            region=account.region or 'us-east-1'
        )

        total_instances = scan_ec2_instances(
            session,
            account_db_id,
            db,
            account.region or 'us-east-1'
        )

        # Update metadata only (don't change status)
        if not account.account_metadata:
            account.account_metadata = {}
        account.account_metadata['last_scan'] = datetime.utcnow().isoformat()
        account.account_metadata['last_scan_count'] = total_instances
        account.updated_at = datetime.utcnow()
        db.commit()

        sys_logger.success(
            f"Re-discovery completed: {total_instances} instances",
            details={'account_id': account_db_id, 'instance_count': total_instances}
        )

    except Exception as e:
        sys_logger.error(
            f"Re-discovery failed: {e}",
            details={'account_id': account_db_id, 'error': str(e)}
        )
    finally:
        db.close()
        sys_logger.close()
