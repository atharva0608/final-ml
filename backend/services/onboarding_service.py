import uuid
import boto3
from sqlalchemy.orm import Session
from fastapi import HTTPException
from botocore.exceptions import ClientError
from backend.models.user import User
from backend.models.onboarding import OnboardingState, OnboardingStep, ConnectionMode
from backend.core.config import settings
import urllib.parse

# Constants
import os
TEMPLATE_BUCKET_URL = "https://your-public-bucket.s3.amazonaws.com" # Replace with real bucket
READ_ONLY_TEMPLATE_URL = f"{TEMPLATE_BUCKET_URL}/read-only-role.yaml"
FULL_ACCESS_TEMPLATE_URL = f"{TEMPLATE_BUCKET_URL}/full-access-role.yaml"

def get_platform_account_id():
    """Get Platform Account ID - Auto-detect if not configured"""
    # 1. Try environment variable first
    env_id = os.getenv("PLATFORM_AWS_ACCOUNT_ID")
    if env_id and env_id != "123456789012":
        return env_id
    
    # 2. Auto-detect via STS
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        return identity.get('Account', 'NOT_CONFIGURED')
    except Exception:
        return 'NOT_CONFIGURED'

PLATFORM_ACCOUNT_ID = get_platform_account_id()  # Cache at module load

class OnboardingService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_state(self, user_id: str) -> OnboardingState:
        state = self.db.query(OnboardingState).filter(OnboardingState.user_id == user_id).first()
        if not state:
            state = OnboardingState(
                user_id=user_id,
                external_id=str(uuid.uuid4()), # Generate secure random ID
                current_step=OnboardingStep.WELCOME
            )
            self.db.add(state)
            self.db.commit()
            self.db.refresh(state)
        return state

    def get_cloudformation_deep_link(self, user_id: str, mode: ConnectionMode) -> str:
        state = self.get_or_create_state(user_id)
        
        # Select Template
        template_url = READ_ONLY_TEMPLATE_URL if mode == ConnectionMode.READ_ONLY else FULL_ACCESS_TEMPLATE_URL
        stack_name = f"SpotOptimizer-Connection-{state.external_id[:8]}"
        
        # Parameters
        params = {
            "stackName": stack_name,
            "templateURL": template_url,
            "param_ExternalId": state.external_id,
            "param_PlatformAccountId": PLATFORM_ACCOUNT_ID
        }
        
        # Build URL
        base_url = "https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review"
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"

    def verify_role_connection(self, user_id: str, role_arn: str) -> bool:
        state = self.get_or_create_state(user_id)
        
        try:
            # Attempt to Assume Role using the specific ExternalId
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
                region_name='us-east-1'
            )
            
            response = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"OnboardingVerify-{user_id}",
                ExternalId=state.external_id
            )
            
            # If successful, credentials are in response['Credentials']
            # We can do a quick test call like listing costs to verify permissions
            
            # Update State
            state.aws_role_arn = role_arn
            state.current_step = OnboardingStep.VERIFYING
            # Extract Account ID from Role ARN if possible or from AssumeRoleUser
            # arn:aws:iam::123456789012:role/...
            account_id = role_arn.split(":")[4]
            state.aws_account_id = account_id
            
            self.db.commit()
            return True
            
        except ClientError as e:
            print(f"Verification Failed: {e}")
            return False

    def complete_onboarding(self, user_id: str):
        state = self.get_or_create_state(user_id)
        user = self.db.query(User).filter(User.id == user_id).first()
        
        state.current_step = OnboardingStep.COMPLETED
        user.onboarding_completed = True
        self.db.commit()

    def get_template(self, user_id: str, mode: ConnectionMode) -> str:
        state = self.get_or_create_state(user_id)
        return self.get_template_by_external_id(state.external_id, mode)

    def get_template_by_external_id(self, external_id: str, mode: ConnectionMode) -> str:
        # Validate existence (optional but good for security)
        # state = self.db.query(OnboardingState).filter(OnboardingState.external_id == external_id).first()
        # if not state: raise HTTPException(404, "Invalid External ID")

        policy_document = ""
        if mode == ConnectionMode.READ_ONLY:
            policy_document = """
                Version: '2012-10-17'
                Statement:
                  - Effect: Allow
                    Action:
                      - 'ec2:Describe*'
                      - 'cloudwatch:GetMetricData'
                      - 'cloudwatch:GetMetricStatistics'
                      - 'autoscaling:Describe*'
                      - 'eks:Describe*'
                      - 'eks:List*'
                      - 'rds:Describe*'
                      - 'rds:List*'
                      - 's3:GetBucket*'
                      - 's3:ListBucket'
                      - 's3:ListAllMyBuckets'
                      - 's3:GetBucketTagging'
                      - 's3:GetBucketLocation'
                      - 's3:GetLifecycleConfiguration'
                      - 'iam:ListUsers'
                      - 'iam:GetUser'
                      - 'iam:ListAccessKeys'
                      - 'elasticloadbalancing:Describe*'
                      - 'ce:GetCostAndUsage'
                    Resource: '*'
            """
        else:
            policy_document = """
                Version: '2012-10-17'
                Statement:
                  - Effect: Allow
                    Action: '*'
                    Resource: '*'
            """

        yaml_template = f"""
AWSTemplateFormatVersion: '2010-09-09'
Description: 'SpotOptimizer - Cross Account Access Role'
Parameters:
  ExternalId:
    Type: String
    Description: 'The Unique External ID provided by SpotOptimizer'
    Default: '{external_id}'
  PlatformAccountId:
    Type: String
    Description: 'The AWS Account ID of the SpotOptimizer Platform to trust'
    Default: '{PLATFORM_ACCOUNT_ID}'

Resources:
  SpotOptimizerRole:
    Type: 'AWS::IAM::Role'
    Properties:
      RoleName: !Sub 'SpotOptimizer-Access-Role-${{ExternalId}}'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Sub 'arn:aws:iam::${{PlatformAccountId}}:root'
            Action: 'sts:AssumeRole'
            Condition:
              StringEquals:
                'sts:ExternalId': !Ref ExternalId
      Policies:
        - PolicyName: 'SpotOptimizerPermissions'
          PolicyDocument: {policy_document}

Outputs:
  RoleArn:
    Description: 'The ARN of the created Role'
    Value: !GetAtt SpotOptimizerRole.Arn
"""
        return yaml_template.strip()

def get_onboarding_service(db: Session = None):
    return OnboardingService(db)
