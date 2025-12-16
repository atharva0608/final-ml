"""
Client Onboarding API Routes

Self-service wizard for clients to connect their AWS accounts securely.
Generates CloudFormation templates and verifies cross-account access.
"""

from fastapi import APIRouter, Depends, HTTPException
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

        # Create placeholder account record
        new_account = Account(
            account_name=f"Pending Setup - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            account_id="pending",  # Will be updated after verification
            external_id=external_id,
            status='pending_setup',
            region='us-east-1',  # Default, can be changed later
            created_by=current_user.id
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
                                                "ec2:RunInstances",
                                                "ec2:TerminateInstances",
                                                "ec2:StopInstances",
                                                "ec2:StartInstances",
                                                "ec2:CreateSnapshot",
                                                "ec2:DeleteSnapshot"
                                            ],
                                            "Resource": "*"
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "autoscaling:Describe*",
                                                "autoscaling:AttachInstances",
                                                "autoscaling:DetachInstances",
                                                "autoscaling:SetDesiredCapacity"
                                            ],
                                            "Resource": "*"
                                        },
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "eks:DescribeCluster",
                                                "eks:ListClusters"
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Verifies cross-account access by attempting STS AssumeRole

    Tests that we can successfully assume the role created by the
    CloudFormation stack in the client's AWS account.
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

        # Attempt to assume role
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
            account.role_arn = verification.role_arn
            account.account_id = client_aws_account_id
            account.status = 'active'
            account.account_name = f"AWS Account {client_aws_account_id}"

            db.commit()

            logger.info(
                f'Connection verified successfully for account {client_aws_account_id}',
                extra={
                    'component': 'OnboardingAPI',
                    'account_id': account_id,
                    'aws_account_id': client_aws_account_id
                }
            )

            return {
                'status': 'connected',
                'aws_account_id': client_aws_account_id,
                'role_arn': verification.role_arn,
                'verified_at': datetime.utcnow().isoformat(),
                'message': 'Connection verified successfully! You can now start optimizing.'
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

        if account.status != 'active':
            return {
                'status': 'not_connected',
                'message': 'Account not yet connected'
            }

        # In a real implementation, this would query discovered resources
        # For now, return placeholder data
        # TODO: Integrate with actual discovery engine

        return {
            'status': 'discovered',
            'account_id': account.account_id,
            'resources': {
                'eks_clusters': 0,  # TODO: Query actual count
                'auto_scaling_groups': 0,  # TODO: Query actual count
                'ec2_instances': 0,  # TODO: Query actual count
                'optimizable_instances': 0  # TODO: Calculate eligible instances
            },
            'last_discovery': datetime.utcnow().isoformat(),
            'message': 'Resource discovery in progress. This may take a few minutes.'
        }

    except Exception as e:
        logger.error(
            f'Failed to get discovery status: {e}',
            extra={'component': 'OnboardingAPI', 'error': str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))
