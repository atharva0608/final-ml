"""
Update Auto Scaling Group Script (SCRIPT-ASG-01)
Update AWS Auto Scaling Group parameters

Features:
- Update desired/min/max capacity
- Update launch template version
- Suspend/resume scaling processes
- Dry-run support

Usage:
    python update_asg.py --asg-name my-asg --desired-capacity 5 --region us-east-1
    python update_asg.py --asg-name my-asg --min 2 --max 10 --desired 5
    python update_asg.py --asg-name my-asg --suspend-processes Launch,Terminate
    python update_asg.py --asg-name my-asg --dry-run

Dependencies:
- boto3
"""

import argparse
import logging
import sys
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def update_asg(
    asg_name: str,
    region: str,
    desired_capacity: Optional[int] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    launch_template_version: Optional[str] = None,
    suspend_processes: Optional[List[str]] = None,
    resume_processes: Optional[List[str]] = None,
    dry_run: bool = False,
    role_arn: Optional[str] = None,
    external_id: Optional[str] = None
) -> Dict[str, Any]:
    """Update Auto Scaling Group configuration"""
    logger.info(f"[SCRIPT-ASG-01] Updating ASG {asg_name} in {region}")

    try:
        # Get ASG client
        if role_arn:
            sts_client = boto3.client('sts')
            assumed_role = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f'SpotOptimizer-UpdateASG-{asg_name}',
                ExternalId=external_id
            )
            credentials = assumed_role['Credentials']
            asg_client = boto3.client(
                'autoscaling', region_name=region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        else:
            asg_client = boto3.client('autoscaling', region_name=region)

        # Get current ASG configuration
        response = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )

        if not response['AutoScalingGroups']:
            raise ValueError(f"ASG {asg_name} not found")

        asg = response['AutoScalingGroups'][0]
        current_desired = asg['DesiredCapacity']
        current_min = asg['MinSize']
        current_max = asg['MaxSize']

        logger.info(f"[SCRIPT-ASG-01] Current: min={current_min}, desired={current_desired}, max={current_max}")

        if dry_run:
            logger.info(f"[SCRIPT-ASG-01] DRY RUN: Would update ASG {asg_name}")
            if desired_capacity is not None:
                logger.info(f"[SCRIPT-ASG-01]   Desired capacity: {current_desired} -> {desired_capacity}")
            if min_size is not None:
                logger.info(f"[SCRIPT-ASG-01]   Min size: {current_min} -> {min_size}")
            if max_size is not None:
                logger.info(f"[SCRIPT-ASG-01]   Max size: {current_max} -> {max_size}")
            return {"success": True, "dry_run": True, "message": "Dry run successful"}

        # Build update parameters
        update_params = {'AutoScalingGroupName': asg_name}
        has_updates = False

        if desired_capacity is not None:
            update_params['DesiredCapacity'] = desired_capacity
            has_updates = True
            logger.info(f"[SCRIPT-ASG-01] Setting desired capacity to {desired_capacity}")

        if min_size is not None:
            update_params['MinSize'] = min_size
            has_updates = True
            logger.info(f"[SCRIPT-ASG-01] Setting min size to {min_size}")

        if max_size is not None:
            update_params['MaxSize'] = max_size
            has_updates = True
            logger.info(f"[SCRIPT-ASG-01] Setting max size to {max_size}")

        if launch_template_version:
            update_params['LaunchTemplate'] = {
                'LaunchTemplateId': asg['LaunchTemplate']['LaunchTemplateId'],
                'Version': launch_template_version
            }
            has_updates = True
            logger.info(f"[SCRIPT-ASG-01] Updating launch template version to {launch_template_version}")

        # Update ASG
        if has_updates:
            asg_client.update_auto_scaling_group(**update_params)
            logger.info(f"[SCRIPT-ASG-01] ASG updated successfully")

        # Suspend processes
        if suspend_processes:
            logger.info(f"[SCRIPT-ASG-01] Suspending processes: {', '.join(suspend_processes)}")
            asg_client.suspend_processes(
                AutoScalingGroupName=asg_name,
                ScalingProcesses=suspend_processes
            )

        # Resume processes
        if resume_processes:
            logger.info(f"[SCRIPT-ASG-01] Resuming processes: {', '.join(resume_processes)}")
            asg_client.resume_processes(
                AutoScalingGroupName=asg_name,
                ScalingProcesses=resume_processes
            )

        return {
            "success": True,
            "asg_name": asg_name,
            "previous": {
                "desired": current_desired,
                "min": current_min,
                "max": current_max
            },
            "updated": {
                "desired": desired_capacity or current_desired,
                "min": min_size or current_min,
                "max": max_size or current_max
            }
        }

    except ClientError as e:
        logger.error(f"[SCRIPT-ASG-01] AWS error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"[SCRIPT-ASG-01] Error: {e}")
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description='Update Auto Scaling Group')
    parser.add_argument('--asg-name', required=True, help='ASG name')
    parser.add_argument('--region', required=True, help='AWS region')
    parser.add_argument('--desired-capacity', type=int, help='Desired capacity')
    parser.add_argument('--min', type=int, help='Minimum size')
    parser.add_argument('--max', type=int, help='Maximum size')
    parser.add_argument('--launch-template-version', help='Launch template version')
    parser.add_argument('--suspend-processes', help='Comma-separated processes to suspend')
    parser.add_argument('--resume-processes', help='Comma-separated processes to resume')
    parser.add_argument('--dry-run', action='store_true', help='Dry run')
    parser.add_argument('--role-arn', help='IAM role ARN')
    parser.add_argument('--external-id', help='External ID')

    args = parser.parse_args()

    suspend = args.suspend_processes.split(',') if args.suspend_processes else None
    resume = args.resume_processes.split(',') if args.resume_processes else None

    result = update_asg(
        asg_name=args.asg_name,
        region=args.region,
        desired_capacity=args.desired_capacity,
        min_size=args.min,
        max_size=args.max,
        launch_template_version=args.launch_template_version,
        suspend_processes=suspend,
        resume_processes=resume,
        dry_run=args.dry_run,
        role_arn=args.role_arn,
        external_id=args.external_id
    )

    if result['success']:
        logger.info("✅ ASG updated successfully")
        if not result.get('dry_run'):
            logger.info(f"📊 Previous: {result['previous']}")
            logger.info(f"📊 Updated: {result['updated']}")
        sys.exit(0)
    else:
        logger.error(f"❌ Update failed: {result.get('error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
