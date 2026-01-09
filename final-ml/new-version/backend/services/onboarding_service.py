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
TEMPLATE_BUCKET_URL = "https://your-public-bucket.s3.amazonaws.com" # Replace with real bucket
READ_ONLY_TEMPLATE_URL = f"{TEMPLATE_BUCKET_URL}/read-only-role.yaml"
FULL_ACCESS_TEMPLATE_URL = f"{TEMPLATE_BUCKET_URL}/full-access-role.yaml"
TRUSTED_ROLE_ARN = "arn:aws:iam::123456789012:role/SpotOptimizerBackendRole" # Replace with real ARN

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
            "param_TrustedRoleARN": TRUSTED_ROLE_ARN
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

def get_onboarding_service(db: Session = None):
    return OnboardingService(db)
