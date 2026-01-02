"""
Launch Spot Instance Script (SCRIPT-SPOT-01)
Launch EC2 Spot instances with intelligent configuration

Features:
- Launch from EC2 Launch Template
- Multiple instance type fallback
- Availability zone selection
- Tag propagation
- Max price specification
- Dry-run support

Usage:
    python launch_spot.py --launch-template lt-123456 --instance-type m5.large --region us-east-1
    python launch_spot.py --ami ami-123456 --instance-type m5.large --subnet subnet-123 --region us-east-1
    python launch_spot.py --launch-template lt-123456 --instance-types m5.large,m5.xlarge --max-price 0.10

Dependencies:
- boto3
- AWS credentials configured
"""

import argparse
import logging
import sys
from typing import Dict, Any, List, Optional
import json
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


def launch_spot_instance(
    instance_types: List[str],
    region: str,
    availability_zone: Optional[str] = None,
    launch_template_id: Optional[str] = None,
    ami_id: Optional[str] = None,
    subnet_id: Optional[str] = None,
    security_group_ids: Optional[List[str]] = None,
    iam_instance_profile: Optional[str] = None,
    key_name: Optional[str] = None,
    user_data: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    max_price: Optional[float] = None,
    interruption_behavior: str = 'terminate',
    dry_run: bool = False,
    role_arn: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Launch EC2 Spot instance

    Args:
        instance_types: List of instance types (in order of preference)
        region: AWS region
        availability_zone: Optional AZ
        launch_template_id: Optional launch template ID
        ami_id: AMI ID (required if not using launch template)
        subnet_id: Subnet ID
        security_group_ids: List of security group IDs
        iam_instance_profile: IAM instance profile name or ARN
        key_name: SSH key pair name
        user_data: User data script
        tags: Resource tags
        max_price: Maximum Spot price (USD per hour)
        interruption_behavior: 'terminate' or 'stop' or 'hibernate'
        dry_run: If True, validate without launching
        role_arn: Optional IAM role to assume
        external_id: Optional external ID for role assumption

    Returns:
        Dict with launch result
    """
    logger.info(f"[SCRIPT-SPOT-01] Launching Spot instance in {region}")
    logger.info(f"[SCRIPT-SPOT-01] Instance types: {', '.join(instance_types)}")

    try:
        # Assume role if provided
        if role_arn:
            logger.info(f"[SCRIPT-SPOT-01] Assuming role {role_arn}")
            sts_client = boto3.client('sts')

            assume_kwargs = {
                'RoleArn': role_arn,
                'RoleSessionName': 'SpotOptimizer-LaunchSpot'
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

        # Build launch specification
        launch_spec = {}

        # Use launch template if provided
        if launch_template_id:
            logger.info(f"[SCRIPT-SPOT-01] Using launch template {launch_template_id}")

            launch_spec['LaunchTemplate'] = {
                'LaunchTemplateId': launch_template_id,
                'Version': '$Latest'
            }

        else:
            # Build launch spec from scratch
            if not ami_id:
                raise ValueError("ami_id is required when not using launch template")

            logger.info(f"[SCRIPT-SPOT-01] Using AMI {ami_id}")

            launch_spec['ImageId'] = ami_id

            if subnet_id:
                launch_spec['SubnetId'] = subnet_id

            if security_group_ids:
                launch_spec['SecurityGroupIds'] = security_group_ids

            if iam_instance_profile:
                launch_spec['IamInstanceProfile'] = {
                    'Name': iam_instance_profile
                }

            if key_name:
                launch_spec['KeyName'] = key_name

            if user_data:
                launch_spec['UserData'] = user_data

        # Set placement
        if availability_zone:
            if 'Placement' not in launch_spec:
                launch_spec['Placement'] = {}
            launch_spec['Placement']['AvailabilityZone'] = availability_zone

        # Build instance market options for Spot
        instance_market_options = {
            'MarketType': 'spot',
            'SpotOptions': {
                'SpotInstanceType': 'one-time',
                'InstanceInterruptionBehavior': interruption_behavior
            }
        }

        if max_price:
            instance_market_options['SpotOptions']['MaxPrice'] = str(max_price)
            logger.info(f"[SCRIPT-SPOT-01] Max Spot price: ${max_price}/hour")

        # Build tag specifications
        tag_specifications = []
        if tags:
            tag_list = [{'Key': k, 'Value': v} for k, v in tags.items()]

            tag_specifications.append({
                'ResourceType': 'instance',
                'Tags': tag_list
            })

            tag_specifications.append({
                'ResourceType': 'volume',
                'Tags': tag_list
            })

        # Try each instance type in order
        for instance_type in instance_types:
            logger.info(f"[SCRIPT-SPOT-01] Attempting to launch {instance_type}")

            try:
                # Build run instances parameters
                run_params = {
                    'MinCount': 1,
                    'MaxCount': 1,
                    'InstanceType': instance_type,
                    'InstanceMarketOptions': instance_market_options
                }

                # Add launch spec parameters
                if launch_template_id:
                    run_params['LaunchTemplate'] = launch_spec['LaunchTemplate']
                else:
                    run_params.update(launch_spec)

                if tag_specifications:
                    run_params['TagSpecifications'] = tag_specifications

                if dry_run:
                    run_params['DryRun'] = True

                # Launch instance
                if dry_run:
                    logger.info(f"[SCRIPT-SPOT-01] DRY RUN: Would launch {instance_type}")

                    try:
                        ec2_client.run_instances(**run_params)
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'DryRunOperation':
                            logger.info(f"[SCRIPT-SPOT-01] Dry run successful for {instance_type}")

                            return {
                                "success": True,
                                "dry_run": True,
                                "message": "Dry run successful - no instance launched",
                                "instance_type": instance_type
                            }
                        else:
                            logger.warning(f"[SCRIPT-SPOT-01] Dry run failed for {instance_type}: {e}")
                            continue

                else:
                    response = ec2_client.run_instances(**run_params)

                    # Get instance details
                    instance = response['Instances'][0]
                    instance_id = instance['InstanceId']
                    state = instance['State']['Name']

                    logger.info(f"[SCRIPT-SPOT-01] ✅ Launched instance {instance_id}")
                    logger.info(f"[SCRIPT-SPOT-01] Instance type: {instance_type}")
                    logger.info(f"[SCRIPT-SPOT-01] State: {state}")

                    return {
                        "success": True,
                        "dry_run": False,
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "state": state,
                        "availability_zone": instance.get('Placement', {}).get('AvailabilityZone'),
                        "private_ip": instance.get('PrivateIpAddress'),
                        "public_ip": instance.get('PublicIpAddress')
                    }

            except ClientError as e:
                error_code = e.response['Error']['Code']

                # Check for common Spot errors
                if error_code in ['InsufficientInstanceCapacity', 'SpotMaxPriceTooLow']:
                    logger.warning(
                        f"[SCRIPT-SPOT-01] Cannot launch {instance_type}: {error_code}"
                    )

                    # Try next instance type
                    if instance_type != instance_types[-1]:
                        logger.info(f"[SCRIPT-SPOT-01] Trying next instance type...")
                        continue
                    else:
                        raise

                else:
                    raise

        # If we got here, all instance types failed
        raise Exception("Failed to launch instance with any of the specified types")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']

        logger.error(f"[SCRIPT-SPOT-01] AWS error: {error_code} - {error_message}")

        return {
            "success": False,
            "error": error_message,
            "error_code": error_code
        }

    except Exception as e:
        logger.error(f"[SCRIPT-SPOT-01] Unexpected error: {str(e)}")

        return {
            "success": False,
            "error": str(e)
        }


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Launch EC2 Spot instance with intelligent fallback'
    )

    parser.add_argument(
        '--instance-types',
        required=True,
        help='Comma-separated list of instance types (e.g., m5.large,m5.xlarge)'
    )

    parser.add_argument(
        '--region',
        required=True,
        help='AWS region (e.g., us-east-1)'
    )

    parser.add_argument(
        '--availability-zone',
        help='Availability zone (e.g., us-east-1a)'
    )

    parser.add_argument(
        '--launch-template',
        help='Launch template ID'
    )

    parser.add_argument(
        '--ami',
        help='AMI ID (required if not using launch template)'
    )

    parser.add_argument(
        '--subnet',
        help='Subnet ID'
    )

    parser.add_argument(
        '--security-groups',
        help='Comma-separated security group IDs'
    )

    parser.add_argument(
        '--iam-profile',
        help='IAM instance profile name or ARN'
    )

    parser.add_argument(
        '--key-name',
        help='EC2 key pair name'
    )

    parser.add_argument(
        '--max-price',
        type=float,
        help='Maximum Spot price (USD per hour)'
    )

    parser.add_argument(
        '--interruption-behavior',
        choices=['terminate', 'stop', 'hibernate'],
        default='terminate',
        help='Spot interruption behavior'
    )

    parser.add_argument(
        '--tags',
        help='Tags as JSON (e.g., \'{"Name": "MyInstance", "Env": "prod"}\')'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate without actually launching'
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

    # Parse instance types
    instance_types = [t.strip() for t in args.instance_types.split(',')]

    # Parse security groups
    security_group_ids = None
    if args.security_groups:
        security_group_ids = [sg.strip() for sg in args.security_groups.split(',')]

    # Parse tags
    tags = None
    if args.tags:
        tags = json.loads(args.tags)

    # Execute launch
    result = launch_spot_instance(
        instance_types=instance_types,
        region=args.region,
        availability_zone=args.availability_zone,
        launch_template_id=args.launch_template,
        ami_id=args.ami,
        subnet_id=args.subnet,
        security_group_ids=security_group_ids,
        iam_instance_profile=args.iam_profile,
        key_name=args.key_name,
        tags=tags,
        max_price=args.max_price,
        interruption_behavior=args.interruption_behavior,
        dry_run=args.dry_run,
        role_arn=args.role_arn,
        external_id=args.external_id
    )

    # Print result
    if result['success']:
        logger.info("✅ Spot instance launched successfully")
        if not result.get('dry_run'):
            logger.info(f"📦 Instance ID: {result.get('instance_id')}")
            logger.info(f"📦 Instance Type: {result.get('instance_type')}")
        sys.exit(0)
    else:
        logger.error(f"❌ Launch failed: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
