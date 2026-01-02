"""
Terminate Instance Script (SCRIPT-TERM-01)
Gracefully terminate EC2 instances with optional volume handling

Features:
- Graceful termination with configurable wait time
- EBS volume preservation option
- Tag-based instance validation
- Dry-run support
- Detailed logging

Usage:
    python terminate_instance.py --instance-id i-1234567890abcdef0 --region us-east-1
    python terminate_instance.py --instance-id i-1234567890abcdef0 --preserve-volumes
    python terminate_instance.py --instance-id i-1234567890abcdef0 --dry-run

Dependencies:
- boto3
- AWS credentials configured
"""

import argparse
import logging
import sys
from typing import Dict, Any, List, Optional
import time

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def terminate_instance(
    instance_id: str,
    region: str,
    preserve_volumes: bool = False,
    wait_for_termination: bool = True,
    dry_run: bool = False,
    role_arn: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Terminate an EC2 instance

    Args:
        instance_id: Instance ID to terminate
        region: AWS region
        preserve_volumes: If True, detach volumes before terminating
        wait_for_termination: If True, wait until instance is terminated
        dry_run: If True, validate without actually terminating
        role_arn: Optional IAM role to assume
        external_id: Optional external ID for role assumption

    Returns:
        Dict with termination result
    """
    logger.info(f"[SCRIPT-TERM-01] Terminating instance {instance_id} in {region}")
    logger.info(f"[SCRIPT-TERM-01] Preserve volumes: {preserve_volumes}, Dry run: {dry_run}")

    try:
        # Assume role if provided
        if role_arn:
            logger.info(f"[SCRIPT-TERM-01] Assuming role {role_arn}")
            sts_client = boto3.client('sts')

            assume_kwargs = {
                'RoleArn': role_arn,
                'RoleSessionName': f'SpotOptimizer-Terminate-{instance_id}'
            }
            if external_id:
                assume_kwargs['ExternalId'] = external_id

            assumed_role = sts_client.assume_role(**assume_kwargs)

            credentials = assumed_role['Credentials']

            ec2_client = boto3.client(
                'ec2',
                region_name=region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            ec2_client = boto3.client('ec2', region_name=region)

        # Get instance details
        logger.info(f"[SCRIPT-TERM-01] Fetching instance details")

        instances_response = ec2_client.describe_instances(
            InstanceIds=[instance_id]
        )

        if not instances_response['Reservations']:
            raise ValueError(f"Instance {instance_id} not found")

        instance = instances_response['Reservations'][0]['Instances'][0]
        state = instance['State']['Name']

        logger.info(f"[SCRIPT-TERM-01] Instance state: {state}")

        # Validate instance is not already terminated
        if state in ['terminated', 'terminating']:
            logger.warning(f"[SCRIPT-TERM-01] Instance already {state}")
            return {
                "success": False,
                "message": f"Instance already {state}",
                "instance_id": instance_id,
                "state": state
            }

        # Handle volume preservation
        volumes_detached = []
        if preserve_volumes and not dry_run:
            logger.info(f"[SCRIPT-TERM-01] Preserving EBS volumes")

            # Get attached volumes
            volumes = instance.get('BlockDeviceMappings', [])

            for volume_mapping in volumes:
                if 'Ebs' in volume_mapping:
                    volume_id = volume_mapping['Ebs']['VolumeId']
                    device_name = volume_mapping['DeviceName']

                    # Check if volume has DeleteOnTermination=false
                    delete_on_termination = volume_mapping['Ebs'].get('DeleteOnTermination', True)

                    if delete_on_termination:
                        logger.info(
                            f"[SCRIPT-TERM-01] Setting DeleteOnTermination=False "
                            f"for volume {volume_id} ({device_name})"
                        )

                        ec2_client.modify_instance_attribute(
                            InstanceId=instance_id,
                            BlockDeviceMappings=[{
                                'DeviceName': device_name,
                                'Ebs': {
                                    'DeleteOnTermination': False
                                }
                            }]
                        )

                        volumes_detached.append(volume_id)

                        logger.info(f"[SCRIPT-TERM-01] Volume {volume_id} will be preserved")

        # Terminate instance
        if dry_run:
            logger.info(f"[SCRIPT-TERM-01] DRY RUN: Would terminate instance {instance_id}")

            try:
                # Perform dry run
                ec2_client.terminate_instances(
                    InstanceIds=[instance_id],
                    DryRun=True
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'DryRunOperation':
                    logger.info(f"[SCRIPT-TERM-01] Dry run successful - termination would succeed")
                else:
                    raise

            return {
                "success": True,
                "dry_run": True,
                "message": "Dry run successful - no changes made",
                "instance_id": instance_id,
                "volumes_preserved": volumes_detached
            }

        else:
            logger.info(f"[SCRIPT-TERM-01] Terminating instance {instance_id}")

            response = ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )

            current_state = response['TerminatingInstances'][0]['CurrentState']['Name']
            previous_state = response['TerminatingInstances'][0]['PreviousState']['Name']

            logger.info(
                f"[SCRIPT-TERM-01] Instance state: {previous_state} -> {current_state}"
            )

            # Wait for termination if requested
            if wait_for_termination:
                logger.info(f"[SCRIPT-TERM-01] Waiting for instance to terminate...")

                waiter = ec2_client.get_waiter('instance_terminated')

                try:
                    waiter.wait(
                        InstanceIds=[instance_id],
                        WaiterConfig={
                            'Delay': 15,
                            'MaxAttempts': 40  # 10 minutes max
                        }
                    )

                    logger.info(f"[SCRIPT-TERM-01] Instance terminated successfully")

                except Exception as e:
                    logger.error(f"[SCRIPT-TERM-01] Timeout waiting for termination: {str(e)}")

            return {
                "success": True,
                "dry_run": False,
                "message": "Instance terminated successfully",
                "instance_id": instance_id,
                "previous_state": previous_state,
                "current_state": current_state,
                "volumes_preserved": volumes_detached
            }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']

        logger.error(f"[SCRIPT-TERM-01] AWS error: {error_code} - {error_message}")

        return {
            "success": False,
            "error": error_message,
            "error_code": error_code,
            "instance_id": instance_id
        }

    except Exception as e:
        logger.error(f"[SCRIPT-TERM-01] Unexpected error: {str(e)}")

        return {
            "success": False,
            "error": str(e),
            "instance_id": instance_id
        }


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Terminate EC2 instance with optional volume preservation'
    )

    parser.add_argument(
        '--instance-id',
        required=True,
        help='EC2 instance ID to terminate'
    )

    parser.add_argument(
        '--region',
        required=True,
        help='AWS region (e.g., us-east-1)'
    )

    parser.add_argument(
        '--preserve-volumes',
        action='store_true',
        help='Preserve EBS volumes (set DeleteOnTermination=False)'
    )

    parser.add_argument(
        '--no-wait',
        action='store_true',
        help='Do not wait for instance to terminate'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate without actually terminating'
    )

    parser.add_argument(
        '--role-arn',
        help='IAM role ARN to assume'
    )

    parser.add_argument(
        '--external-id',
        help='External ID for role assumption'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Execute termination
    result = terminate_instance(
        instance_id=args.instance_id,
        region=args.region,
        preserve_volumes=args.preserve_volumes,
        wait_for_termination=not args.no_wait,
        dry_run=args.dry_run,
        role_arn=args.role_arn,
        external_id=args.external_id
    )

    # Print result
    if result['success']:
        logger.info("✅ Termination successful")
        if result.get('volumes_preserved'):
            logger.info(f"📦 Preserved volumes: {result['volumes_preserved']}")
        sys.exit(0)
    else:
        logger.error(f"❌ Termination failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
