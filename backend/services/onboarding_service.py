import uuid
import boto3
from sqlalchemy.orm import Session
from fastapi import HTTPException
from botocore.exceptions import ClientError
from backend.models.user import User
from backend.models.onboarding import OnboardingState, OnboardingStep, ConnectionMode
from backend.core.config import settings
import urllib.parse

from pathlib import Path

# Constants
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "aws"
# Note: URLs are now generated dynamically based on request host

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

    def get_cloudformation_deep_link(self, user_id: str, mode: ConnectionMode, base_url: str = "http://localhost:8000") -> str:
        state = self.get_or_create_state(user_id)
        
        # Select Template URL (Point to our own API)
        # base_url should come from the request
        template_url = f"{base_url}/api/v1/onboarding/template?external_id={state.external_id}&mode={mode.value}"
        
        stack_name = f"SpotOptimizer-Connection-{state.external_id[:8]}"
        
        # Parameters for CloudFormation Console
        # These pre-fill the parameters in the CFN wizard
        params = {
            "stackName": stack_name,
            "templateURL": template_url,
            "param_ExternalId": state.external_id,
            "param_PlatformAccountId": PLATFORM_ACCOUNT_ID
        }
        
        # Build URL
        cfn_base = "https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review"
        query_string = urllib.parse.urlencode(params)
        return f"{cfn_base}?{query_string}"

    def verify_role_connection(self, user_id: str, role_arn: str) -> bool:
        state = self.get_or_create_state(user_id)
        
        try:
            # Attempt to Assume Role using the specific ExternalId
            sts_client = boto3.client(
                'sts',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name='us-east-1'
            )
            
            response = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"OnboardingVerify-{user_id}",
                ExternalId=state.external_id
            )
            
            # Update State
            state.aws_role_arn = role_arn
            state.current_step = OnboardingStep.VERIFYING
            # Extract Account ID from Role ARN
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
        """
        Read the YAML template from disk and inject dynamic default values.
        """
        filename = "read-only-role.yaml" if mode == ConnectionMode.READ_ONLY else "full-access-role.yaml"
        file_path = TEMPLATE_DIR / filename
        
        if not file_path.exists():
            # Fallback for dev if file missing
             return f"Error: Template {filename} not found at {file_path}"

        content = file_path.read_text()
        
        # Inject Defaults (Optional, but good for manual downloads)
        # We replace the placeholder defaults with actual values
        # Note: The template MUST have Default: '...' for this to work neatly, 
        # or we rely on CFN params.
        # Since we just updated full-access-role.yaml to have defaults:
        
        # Replace ExternalId default
        # Looking for: Default: '{external_id}' (from old code) vs actual YAML.
        # Actually, simpler to just return the content. 
        # The Deep Link fills the params.
        # But if user downloads file, they have to likely fill it manually or we pre-fill here.
        
        # Let's simple string replace specific keys if present to be helpful
        # "Default: '123456789012'" -> "Default: 'REAL_ID'"
        
        content = content.replace("Default: '123456789012'", f"Default: '{PLATFORM_ACCOUNT_ID}'")
        
        # We don't have a placeholder for ExternalId in the file currently (it likely has no default or dummy).
        # But we can try to inject it if we want.
        # For now, relying on the URL params is safer and cleaner.
        
        return content

def get_onboarding_service(db: Session = None):
    return OnboardingService(db)
