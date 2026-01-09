"""
Detach EBS Volume Script (SCRIPT-VOL-01)
Detach EBS volumes from EC2 instances

Features:
- Graceful volume detachment with force option
- Wait for detachment completion
- Create snapshot before detachment (optional)
- Dry-run support

Usage:
    python detach_volume.py --volume-id vol-123456 --region us-east-1
    python detach_volume.py --volume-id vol-123456 --force --snapshot
    python detach_volume.py --volume-id vol-123456 --dry-run

Dependencies:
- boto3
"""

import argparse
import logging
import sys
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def detach_volume(
    volume_id: str,
    region: str,
    force: bool = False,
    create_snapshot: bool = False,
    wait: bool = True,
    dry_run: bool = False,
    role_arn: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """Detach EBS volume from instance"""
    logger.info(f"[SCRIPT-VOL-01] Detaching volume {volume_id} in {region}")

    try:
        # Get EC2 client
        if role_arn:
            sts_client = boto3.client('sts')
            assumed_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f'SpotOptimizer-DetachVolume-{volume_id}',
                ExternalId=external_id
            )
            credentials = assumed_role['Credentials']
            ec2_client = boto3.client(
                'ec2', region_name=region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            ec2_client = boto3.client('ec2', region_name=region)

        # Get volume details
        volumes = ec2_client.describe_volumes(VolumeIds=[volume_id])
        if not volumes['Volumes']:
            raise ValueError(f"Volume {volume_id} not found")

        volume = volumes['Volumes'][0]
        state = volume['State']
        attachments = volume.get('Attachments', [])

        logger.info(f"[SCRIPT-VOL-01] Volume state: {state}")

        if state == 'available':
            return {"success": True, "message": "Volume already detached"}

        if not attachments:
            return {"success": True, "message": "Volume has no attachments"}

        attachment = attachments[0]
        instance_id = attachment['InstanceId']
        device = attachment['Device']

        logger.info(f"[SCRIPT-VOL-01] Attached to instance {instance_id} as {device}")

        # Create snapshot if requested
        snapshot_id = None
        if create_snapshot and not dry_run:
            logger.info(f"[SCRIPT-VOL-01] Creating snapshot before detachment")
            snapshot = ec2_client.create_snapshot(
                VolumeId=volume_id,
                Description=f"Snapshot before detaching from {instance_id}"
            )
            snapshot_id = snapshot['SnapshotId']
            logger.info(f"[SCRIPT-VOL-01] Created snapshot {snapshot_id}")

        # Detach volume
        if dry_run:
            logger.info(f"[SCRIPT-VOL-01] DRY RUN: Would detach volume {volume_id}")
            try:
                ec2_client.detach_volume(VolumeId=volume_id, DryRun=True)
            except ClientError as e:
                if e.response['Error']['Code'] == 'DryRunOperation':
                    return {"success": True, "dry_run": True, "message": "Dry run successful"}
                raise
        else:
            logger.info(f"[SCRIPT-VOL-01] Detaching volume...")
            ec2_client.detach_volume(VolumeId=volume_id, Force=force)

            if wait:
                logger.info(f"[SCRIPT-VOL-01] Waiting for detachment...")
                waiter = ec2_client.get_waiter('volume_available')
                waiter.wait(VolumeIds=[volume_id])
                logger.info(f"[SCRIPT-VOL-01] Volume detached successfully")

            return {
                "success": True,
                "volume_id": volume_id,
                "instance_id": instance_id,
                "device": device,
                "snapshot_id": snapshot_id
            }

    except ClientError as e:
        logger.error(f"[SCRIPT-VOL-01] AWS error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[SCRIPT-VOL-01] Error: {e}")
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description='Detach EBS volume')
    parser.add_argument('--volume-id', required=True, help='Volume ID')
    parser.add_argument('--region', required=True, help='AWS region')
    parser.add_argument('--force', action='store_true', help='Force detachment')
    parser.add_argument('--snapshot', action='store_true', help='Create snapshot before detaching')
    parser.add_argument('--no-wait', action='store_true', help='Do not wait for completion')
    parser.add_argument('--dry-run', action='store_true', help='Dry run')
    parser.add_argument('--role-arn', help='IAM role ARN')
    parser.add_argument('--external-id', help='External ID')

    args = parser.parse_args()

    result = detach_volume(
        volume_id=args.volume_id,
        region=args.region,
        force=args.force,
        create_snapshot=args.snapshot,
        wait=not args.no_wait,
        dry_run=args.dry_run,
        role_arn=args.role_arn,
        external_id=args.external_id
    )

    if result['success']:
        logger.info("✅ Volume detached successfully")
        sys.exit(0)
    else:
        logger.error(f"❌ Detachment failed: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
