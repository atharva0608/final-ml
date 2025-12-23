"""
Client Onboarding API Routes

Self-service wizard for clients to connect their AWS accounts securely.
Generates CloudFormation templates and verifies cross-account access.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import json
import uuid
import boto3
from botocore.exceptions import ClientError

from database.connection import get_db
from database.models import Account
from utils.system_logger import logger
from api.auth import get_current_active_user as get_current_user
from workers.discovery_worker import run_initial_discovery

router = APIRouter(
    prefix="",
    tags=["onboarding"]
)


class ConnectionVerification(BaseModel):
    role_arn: str


@router.post('/create')
async def create_onboarding_request(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Creates a new onboarding request with unique ExternalID

    Returns the ExternalID that will be used in the CloudFormation template.
    """
    try:
        # Generate unique ExternalID
        external_id = f"spot-optimizer-{uuid.uuid4()}"

        # Generate unique temporary account_id to avoid constraint violation
        # Use UUID prefix so it's unique until real AWS account ID is provided
        temp_account_id = f"pending-{uuid.uuid4().hex[:12]}"

        # Create placeholder account record
        new_account = Account(
            user_id=current_user.id,
            account_name=f"Pending Setup - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            account_id=temp_account_id,  # Unique temp ID, will be updated after verification
            external_id=external_id,
            role_arn="pending",  # Will be updated after verification
            region='us-east-1',  # Default, can be changed later
            is_active=False  # Will be activated after verification
        )

        db.add(new_account)
        db.commit()
        db.refresh(new_account)

        logger.info(
            f'New onboarding request created with ExternalID: {external_id}',
            extra={'component': 'OnboardingAPI', 'user_id': current_user.id}
        )

        return {
            'id': str(new_account.id),
            'external_id': external_id,
            'status': 'pending_setup',
            'created_at': new_account.created_at.isoformat()
        }

    except Exception as e:
        db.rollback()
        logger.error(
            f'Failed to create onboarding request: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/template/{account_id}')
async def get_cloudformation_template(
    account_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns CloudFormation template with client's ExternalID injected

    This template creates an IAM role that trusts our AWS account
    and can be assumed for cross-account resource management.
    """
    try:
        # Get account record
        account = db.query(Account).filter(Account.id == account_id).first()

        if not account:
            raise HTTPException(status_code=404, detail='Account not found')

        # Get our AWS account ID (from environment or config)
        # In production, this should come from environment variable
        our_aws_account_id = "123456789012"  # TODO: Replace with actual account ID

        # CloudFormation template
        template = {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Description": "Spot Optimizer Cross-Account Access Role",
            "Resources": {
                "SpotOptimizerRole": {
                    "Type": "AWS::IAM::Role",
                    "Properties": {
                        "RoleName": "SpotOptimizerCrossAccountRole",
                        "AssumeRolePolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {
                                        "AWS": f"arn:aws:iam::{our_aws_account_id}:root"
                                    },
                                    "Action": "sts:AssumeRole",
                                    "Condition": {
                                        "StringEquals": {
                                            "sts:ExternalId": account.external_id
                                        }
                                    }
                                }
                            ]
                        },
                        "ManagedPolicyArns": [],
                        "Policies": [
                            {
                                "PolicyName": "SpotOptimizerAccess",
                                "PolicyDocument": {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "ec2:Describe*",
                                                "ec2:CreateTags",
                                                "ec2:DeleteTags",
                                                "ec2:RunInstances",
                                                "ec2:TerminateInstances",
                                                "ec2:StopInstances",
                                                "ec2:StartInstances",
                                                "ec2:CreateSnapshot",
                                                "ec2:DeleteSnapshot",
                                                "ec2:RequestSpotInstances",
                                                "ec2:CancelSpotInstanceRequests"
                                            ],
                                            "Resource": "*"
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": "iam:PassRole",
                                            "Resource": "*",
                                            "Condition": {
                                                "StringLike": {
                                                    "iam:PassedToService": "ec2.amazonaws.com"
                                                }
                                            }
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": "iam:CreateServiceLinkedRole",
                                            "Resource": "*",
                                            "Condition": {
                                                "StringLike": {
                                                    "iam:AWSServiceName": "spot.amazonaws.com"
                                                }
                                            }
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "autoscaling:Describe*",
                                                "autoscaling:AttachInstances",
                                                "autoscaling:DetachInstances",
                                                "autoscaling:SetDesiredCapacity",
                                                "autoscaling:UpdateAutoScalingGroup"
                                            ],
                                            "Resource": "*"
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "eks:DescribeCluster",
                                                "eks:ListClusters",
                                                "eks:DescribeNodegroup"
                                            ],
                                            "Resource": "*"
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "pricing:GetProducts"
                                            ],
                                            "Resource": "*"
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            },
            "Outputs": {
                "RoleARN": {
                    "Description": "ARN of the created IAM role",
                    "Value": {"Fn::GetAtt": ["SpotOptimizerRole", "Arn"]}
                }
            }
        }

        logger.info(
            f'CloudFormation template generated for account {account_id}',
            extra={'component': 'OnboardingAPI', 'account_id': account_id}
        )

        return {
            'template': template,
            'external_id': account.external_id,
            'instructions': {
                'step_1': 'Copy this template to a file (e.g., spot-optimizer-role.json)',
                'step_2': 'Open AWS CloudFormation console in your AWS account',
                'step_3': 'Create new stack and upload the template',
                'step_4': 'After stack creation, copy the RoleARN from Outputs tab',
                'step_5': 'Return here and paste the RoleARN to verify connection'
            }
        }

    except Exception as e:
        logger.error(
            f'Failed to generate CloudFormation template: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/{account_id}/verify')
async def verify_connection(
    account_id: str,
    verification: ConnectionVerification,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Verifies cross-account access by attempting STS AssumeRole

    Phase 1: Synchronous IAM role verification (< 2 seconds)
    Phase 2: Asynchronous resource discovery (background task)

    Tests that we can successfully assume the role created by the
    CloudFormation stack in the client's AWS account, then triggers
    background discovery of EC2 instances and EKS clusters.
    """
    try:
        # Get account record
        account = db.query(Account).filter(Account.id == account_id).first()

        if not account:
            raise HTTPException(status_code=404, detail='Account not found')

        logger.info(
            f'Verifying connection for account {account_id} with role {verification.role_arn}',
            extra={'component': 'OnboardingAPI', 'account_id': account_id}
        )

        # Attempt to assume role (synchronous verification)
        sts_client = boto3.client('sts')

        try:
            response = sts_client.assume_role(
                RoleArn=verification.role_arn,
                RoleSessionName='SpotOptimizerVerification',
                ExternalId=account.external_id,
                DurationSeconds=900  # 15 minutes
            )

            # Get AWS account ID from assumed role credentials
            assumed_sts = boto3.client(
                'sts',
                aws_access_key_id=response['Credentials']['AccessKeyId'],
                aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                aws_session_token=response['Credentials']['SessionToken']
            )

            identity = assumed_sts.get_caller_identity()
            client_aws_account_id = identity['Account']

            # Update account record with verified information
            # Status: 'connected' = credentials verified, discovery pending
            # Status: 'active' = discovery complete, dashboard unlocked
            account.role_arn = verification.role_arn
            account.account_id = client_aws_account_id
            account.status = 'connected'  # Will transition to 'active' after discovery
            account.account_name = f"AWS Account {client_aws_account_id}"
            account.is_active = False  # Will be set to True after discovery

            db.commit()

            logger.info(
                f'Connection verified successfully for account {client_aws_account_id}, starting discovery',
                extra={
                    'component': 'OnboardingAPI',
                    'account_id': account_id,
                    'aws_account_id': client_aws_account_id
                }
            )

            # Trigger asynchronous resource discovery (runs in background)
            background_tasks.add_task(run_initial_discovery, account.id)

            return {
                'status': 'connected',
                'aws_account_id': client_aws_account_id,
                'role_arn': verification.role_arn,
                'verified_at': datetime.utcnow().isoformat(),
                'message': 'Credentials verified! Scanning your AWS resources in the background...',
                'discovery_status': 'in_progress'
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.warning(
                f'Connection verification failed: {error_code} - {error_message}',
                extra={'component': 'OnboardingAPI', 'account_id': account_id}
            )

            # Provide helpful error messages
            if error_code == 'AccessDenied':
                detail = 'Access denied. Please check that the CloudFormation stack was created successfully and the ExternalID matches.'
            elif error_code == 'InvalidClientTokenId':
                detail = 'Invalid role ARN. Please verify the ARN copied from CloudFormation outputs.'
            else:
                detail = f'Verification failed: {error_message}'

            return {
                'status': 'failed',
                'error': detail,
                'error_code': error_code
            }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            f'Connection verification error: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{account_id}/discovery')
async def get_discovery_status(
    account_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Returns resource discovery status for connected account

    Shows counts of discovered EKS clusters, ASGs, and instances.
    """
    try:
        # Get account record
        account = db.query(Account).filter(Account.id == account_id).first()

        if not account:
            raise HTTPException(status_code=404, detail='Account not found')

        # Return discovery status based on account status
        if account.status == 'pending':
            return {
                'status': 'not_started',
                'message': 'Account setup not completed'
            }
        elif account.status == 'connected':
            return {
                'status': 'in_progress',
                'message': 'Scanning AWS resources...',
                'account_status': account.status
            }
        elif account.status == 'failed':
            error_details = account.account_metadata.get('last_error', 'Unknown error') if account.account_metadata else 'Unknown error'
            return {
                'status': 'failed',
                'message': f'Discovery failed: {error_details}',
                'error': error_details,
                'account_status': account.status
            }
        elif account.status != 'active':
            return {
                'status': 'unknown',
                'message': f'Account in unexpected state: {account.status}',
                'account_status': account.status
            }

        # Query actual discovered resources from database
        from database.models import Instance

        instance_count = db.query(Instance).filter(
            Instance.account_id == account.id
        ).count()

        authorized_count = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.auth_status == 'authorized'
        ).count()

        unauthorized_count = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.auth_status == 'unauthorized'
        ).count()

        # Get scan metadata from account
        scan_metadata = account.account_metadata or {}
        last_scan = scan_metadata.get('last_scan', datetime.utcnow().isoformat())
        regions_scanned = scan_metadata.get('regions_scanned', [account.region or 'us-east-1'])

        return {
            'status': 'completed',
            'account_id': account.account_id,
            'account_status': account.status,
            'resources': {
                'ec2_instances': instance_count,
                'authorized_instances': authorized_count,
                'unauthorized_instances': unauthorized_count,
                'optimizable_instances': authorized_count  # All authorized instances are optimizable
            },
            'scan_info': {
                'last_scan': last_scan,
                'regions_scanned': regions_scanned,
                'instances_discovered': scan_metadata.get('instances_discovered', instance_count)
            },
            'message': f'Discovery complete! Found {instance_count} EC2 instances.'
        }

    except Exception as e:
        logger.error(
            f'Failed to get discovery status: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/{account_id}/rediscover')
async def trigger_rediscovery(
    account_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Manually trigger re-discovery of AWS resources for an active account

    This can be used to refresh instance data on-demand or periodically.
    Only works for accounts that have already completed initial discovery.
    """
    try:
        account = db.query(Account).filter(Account.id == account_id).first()

        if not account:
            raise HTTPException(status_code=404, detail='Account not found')

        if account.status != 'active':
            raise HTTPException(
                status_code=400,
                detail=f'Account must be in active status to re-discover. Current status: {account.status}'
            )

        logger.info(
            f'Triggering re-discovery for account {account.account_name}',
            extra={'component': 'OnboardingAPI', 'account_id': account_id}
        )

        # Import rediscovery function
        from workers.discovery_worker import trigger_rediscovery

        # Trigger background task
        background_tasks.add_task(trigger_rediscovery, account.id)

        return {
            'status': 'triggered',
            'message': 'Re-discovery started in background',
            'account_id': account.account_id,
            'timestamp': datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f'Failed to trigger rediscovery: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/{account_id}/dashboard-summary')
async def get_client_dashboard_summary(
    account_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get comprehensive dashboard summary for client after discovery

    Returns all key metrics and counts for displaying on client dashboard:
    - Total instances discovered
    - Breakdown by authorization status
    - Breakdown by lifecycle (on-demand vs spot)
    - Breakdown by state (running, stopped, etc.)
    - Regions covered
    - Potential cost savings
    - Last scan information
    """
    try:
        from database.models import Instance
        from sqlalchemy import func

        # Get account
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail='Account not found')

        # Check if discovery is complete
        if account.status == 'pending':
            return {
                'status': 'pending',
                'message': 'Cloud connection not yet initiated',
                'account_status': account.status
            }
        elif account.status == 'connected':
            return {
                'status': 'discovering',
                'message': 'Scanning AWS resources in progress...',
                'account_status': account.status,
                'progress': 'Discovery worker is running in background'
            }
        elif account.status == 'failed':
            error_msg = account.account_metadata.get('last_error', 'Unknown error') if account.account_metadata else 'Unknown error'
            return {
                'status': 'failed',
                'message': f'Discovery failed: {error_msg}',
                'account_status': account.status,
                'error': error_msg
            }

        # Account is 'active' - fetch comprehensive data

        # Total instances
        total_instances = db.query(Instance).filter(
            Instance.account_id == account.id
        ).count()

        # By authorization status
        authorized_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.auth_status == 'authorized'
        ).count()

        unauthorized_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.auth_status == 'unauthorized'
        ).count()

        # By lifecycle
        on_demand_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.lifecycle == 'on-demand'
        ).count()

        spot_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.lifecycle == 'spot'
        ).count()

        # By state
        running_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.state == 'running'
        ).count()

        stopped_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.state == 'stopped'
        ).count()

        # Active instances (running or pending)
        active_instances = db.query(Instance).filter(
            Instance.account_id == account.id,
            Instance.is_active == True
        ).count()

        # Get unique regions
        regions = db.query(Instance.region).filter(
            Instance.account_id == account.id
        ).distinct().all()
        unique_regions = [r[0] for r in regions if r[0]]

        # Get instance type distribution (top 5)
        instance_type_counts = db.query(
            Instance.instance_type,
            func.count(Instance.id).label('count')
        ).filter(
            Instance.account_id == account.id
        ).group_by(Instance.instance_type).order_by(
            func.count(Instance.id).desc()
        ).limit(5).all()

        instance_types = [
            {'type': itype, 'count': count}
            for itype, count in instance_type_counts
        ]

        # Estimate cost savings potential (simplified)
        # Assume 70% savings on spot vs on-demand for authorized instances
        optimizable_count = authorized_instances
        estimated_monthly_savings = optimizable_count * 50  # $50 per instance/month avg

        # Get scan metadata
        scan_metadata = account.account_metadata or {}
        last_scan = scan_metadata.get('last_scan', account.updated_at.isoformat())
        instances_discovered = scan_metadata.get('instances_discovered', total_instances)

        return {
            'status': 'active',
            'account_status': account.status,
            'account_info': {
                'aws_account_id': account.account_id,
                'account_name': account.account_name,
                'region': account.region,
                'created_at': account.created_at.isoformat(),
                'last_updated': account.updated_at.isoformat()
            },
            'discovery_info': {
                'last_scan': last_scan,
                'instances_discovered': instances_discovered,
                'regions_scanned': unique_regions,
                'scan_status': 'completed'
            },
            'instance_counts': {
                'total': total_instances,
                'active': active_instances,
                'running': running_instances,
                'stopped': stopped_instances,
                'authorized': authorized_instances,
                'unauthorized': unauthorized_instances,
                'on_demand': on_demand_instances,
                'spot': spot_instances,
                'optimizable': optimizable_count
            },
            'cost_analysis': {
                'estimated_monthly_savings': round(estimated_monthly_savings, 2),
                'optimizable_instances': optimizable_count,
                'current_spot_usage': spot_instances,
                'potential_spot_candidates': on_demand_instances
            },
            'instance_distribution': {
                'by_type': instance_types,
                'by_region': unique_regions
            },
            'next_steps': {
                'authorize_instances': unauthorized_instances > 0,
                'start_optimization': authorized_instances > 0,
                'configure_clusters': total_instances > 0
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f'Failed to get dashboard summary: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))
