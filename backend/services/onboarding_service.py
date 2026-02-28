import uuid
import boto3
from sqlalchemy.orm import Session
from fastapi import HTTPException
from botocore.exceptions import ClientError
from backend.models.user import User
from backend.models.onboarding import OnboardingState, OnboardingStep, ConnectionMode
import urllib.parse

from pathlib import Path

# Constants
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "aws"
# Note: URLs are now generated dynamically based on request host

# Sentinel used in CloudFormation templates when platform account is not yet configured
_CFN_DEFAULT_ACCOUNT_ID = '123456789012'

class OnboardingService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_platform_sts_client(self):
        """
        Return a boto3 STS client authenticated with platform credentials
        stored in the SystemConfig table (set via Super Admin UI).
        Never reads from environment variables directly.
        """
        from backend.models.system_config import SystemConfig
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        region_cfg = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        region = (region_cfg.value if region_cfg and region_cfg.value else 'us-east-1')

        if not (access_key and access_key.value and secret_key and secret_key.value):
            raise HTTPException(
                status_code=400,
                detail="Platform AWS Identity is not configured. "
                       "Go to Super Admin → Platform Identity and save your AWS credentials first."
            )

        return boto3.client(
            'sts',
            aws_access_key_id=access_key.value,
            aws_secret_access_key=secret_key.value,
            region_name=region
        )

    def _get_platform_account_id(self) -> str:
        """
        Return the platform AWS account ID from SystemConfig (Super Admin UI).
        Falls back to the CFN sentinel so the CloudFormation template still renders.
        """
        from backend.models.system_config import SystemConfig
        cfg = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCOUNT_ID").first()
        if cfg and cfg.value and cfg.value != _CFN_DEFAULT_ACCOUNT_ID:
            return cfg.value
        return _CFN_DEFAULT_ACCOUNT_ID

    def get_or_create_state(self, user_id: str) -> OnboardingState:
        state = self.db.query(OnboardingState).filter(OnboardingState.user_id == user_id).first()
        
        # Check for invalid external_id (legacy data cleanup)
        valid_uuid = True
        if state:
            try:
                val = uuid.UUID(state.external_id, version=4)
            except ValueError:
                valid_uuid = False
        
        if not state or not valid_uuid:
            new_id = str(uuid.uuid4())
            if state:
                state.external_id = new_id
                # Reset step if ID changes to force re-verify
                state.current_step = OnboardingStep.WELCOME 
            else:
                state = OnboardingState(
                    user_id=user_id,
                    external_id=new_id,
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
            "param_PlatformAccountId": self._get_platform_account_id()
        }
        
        # Build URL
        cfn_base = "https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review"
        query_string = urllib.parse.urlencode(params)
        return f"{cfn_base}?{query_string}"

    def verify_role_connection(self, user_id: str, role_arn: str) -> bool:
        state = self.get_or_create_state(user_id)

        try:
            # Assume Role using platform credentials from Super Admin UI (SystemConfig)
            sts_client = self._get_platform_sts_client()

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
            
            # --- CRITICAL FIX: Create/Update Account Record for Discovery Worker ---
            from backend.models.account import Account, AccountStatus
            
            # Get User to find Organization ID
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user or not user.organization_id:
                # Should not happen in normal flow, but handle gracefully
                print(f"User {user_id} has no organization, skipping account creation")
            else:
                existing_account = self.db.query(Account).filter(
                    Account.aws_account_id == account_id,
                    Account.organization_id == user.organization_id
                ).first()
                
                if existing_account:
                    # Update existing
                    existing_account.role_arn = role_arn
                    existing_account.external_id = state.external_id
                    existing_account.status = AccountStatus.SCANNING # Trigger scan
                    existing_account.user_id = user_id # Claim ownership if changed
                else:
                    # Create new
                    new_account = Account(
                        organization_id=user.organization_id,
                        user_id=user_id,
                        aws_account_id=account_id,
                        role_arn=role_arn,
                        external_id=state.external_id,
                        region='us-east-1', # Default
                        status=AccountStatus.SCANNING,
                        is_default=False
                    )
                    self.db.add(new_account)
            
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
        # filename = "read-only-role.yaml" if mode == ConnectionMode.READ_ONLY else "full-access-role.yaml"
        # FORCE FULL ACCESS for now to resolve debugging issues
        filename = "full-access-role.yaml"
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
        
        content = content.replace("Default: '123456789012'", f"Default: '{self._get_platform_account_id()}'")
        
        # We don't have a placeholder for ExternalId in the file currently (it likely has no default or dummy).
        # But we can try to inject it if we want.
        # For now, relying on the URL params is safer and cleaner.
        
        return content

def get_onboarding_service(db: Session = None):
    return OnboardingService(db)
