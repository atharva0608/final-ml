import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.account import Account, AccountStatus
from backend.models.user import User, UserRole
from backend.schemas.account_schemas import AccountCreate, AccountResponse

class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def _get_platform_client(self, service_name: str):
        """Get an AWS client using platform credentials from SystemConfig"""
        from backend.models.system_config import SystemConfig
        
        access_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_ACCESS_KEY").first()
        secret_key = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_SECRET").first()
        region = self.db.query(SystemConfig).filter(SystemConfig.key == "PLATFORM_AWS_REGION").first()
        
        region_name = region.value if region and region.value else 'us-east-1'
        
        if access_key and secret_key and access_key.value and secret_key.value:
            return boto3.client(
                service_name,
                aws_access_key_id=access_key.value,
                aws_secret_access_key=secret_key.value,
                region_name=region_name
            )
        else:
            # Check if we have env vars as fallback, otherwise raise friendly error
            import os
            if not os.getenv("AWS_ACCESS_KEY_ID"):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400, 
                    detail="Platform AWS Identity is not configured. Please set up Platform Credentials in Admin Settings first."
                )
            
            # Fallback to environment variables
            return boto3.client(service_name, region_name=region_name)

    def verify_connection(self, role_arn: str, external_id: str) -> bool:
        """Verify AWS connection by attempting to assume role"""
        try:
            sts = self._get_platform_client('sts')
            sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="SpotOptimizerVerify",
                ExternalId=external_id
            )
            return True
        except ClientError as e:
            raise HTTPException(400, f"AWS Connection Failed: {str(e)}")

    def list_accounts(self, user: "User") -> List[Account]:
        """
        List accounts based on RBAC:
        - Org Admin: All accounts in organization
        - Team Lead: All accounts owned by team members
        - Member: Only their own accounts
        """
        query = self.db.query(Account).filter(Account.organization_id == user.organization_id)
        
        if user.role == UserRole.ORG_ADMIN or user.role == UserRole.CLIENT:
            return query.all()
        
        elif user.role == UserRole.TEAM_LEAD:
            if not user.team_id:
                return query.filter(Account.user_id == user.id).all() # Fallback to own
            
            # Get all user IDs in the team
            team_members = self.db.query(User.id).filter(User.team_id == user.team_id).all()
            member_ids = [m.id for m in team_members]
            return query.filter(Account.user_id.in_(member_ids)).all()
            
        elif user.role == UserRole.MEMBER:
            return query.filter(Account.user_id == user.id).all()
            
        return []

    def get_account(self, account_id: str, organization_id: str) -> Account:
        """Get a specific account by ID"""
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.organization_id == organization_id
        ).first()
        if not account:
            raise HTTPException(404, "Account not found")
        return account

    def link_aws_account(
        self,
        organization_id: str,
        aws_account_id: str,
        role_arn: str,
        external_id: str,
        requester
    ) -> dict:
        """Link a new AWS account after verifying credentials"""
        from backend.models.user import UserRole
        from backend.models.approval import ApprovalRequest
        
        # Verify connection first
        self.verify_connection(role_arn, external_id)
        
        # Check if account already exists
        existing = self.db.query(Account).filter(
            Account.aws_account_id == aws_account_id,
            Account.organization_id == organization_id
        ).first()
        if existing:
            raise HTTPException(400, "Account already linked")

        # Determine Status
        status = AccountStatus.ACTIVE
        needs_approval = False
        
        if requester.role == UserRole.MEMBER:
            status = AccountStatus.PENDING_APPROVAL
            needs_approval = True

        account = Account(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            aws_account_id=aws_account_id,
            role_arn=role_arn,
            external_id=external_id,
            status=status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.db.add(account)
        self.db.commit()
        
        if needs_approval:
            approval_req = ApprovalRequest(
                organization_id=organization_id,
                requester_id=requester.id,
                resource_type="AWS_ACCOUNT",
                resource_id=account.id,
                action="CONNECT_ACCOUNT",
                execution_payload={} 
            )
            self.db.add(approval_req)
            self.db.commit()
            return {"status": "pending", "message": "Connection request sent to Team Lead", "account": account}

        self.db.refresh(account)
        return {"status": "success", "account": account}
    def delete_account(self, account_id: str, organization_id: str) -> bool:
        """Delete/unlink an AWS account"""
        account = self.get_account(account_id, organization_id)
        self.db.delete(account)
        self.db.commit()
        return True

    def validate_account(self, account_id: str, organization_id: str) -> Account:
        """Validate account credentials are still working"""
        account = self.get_account(account_id, organization_id)
        
        try:
            self.verify_connection(account.role_arn, account.external_id)
            account.status = AccountStatus.ACTIVE
            account.last_validated = datetime.utcnow()
            account.updated_at = datetime.utcnow()
            
            # Trigger discovery
            try:
                from backend.services.cluster_service import ClusterService
                cluster_service = ClusterService(self.db)
                # Pass organization_id as user_id for context, though currently unused
                cluster_service.discover_clusters(account.id, organization_id)
            except Exception as e:
                # Log but don't fail validation
                print(f"Discovery trigger failed: {e}")
                
        except HTTPException:
            account.status = AccountStatus.ERROR
            account.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(account)
        return account

    def set_default_account(self, account_id: str, organization_id: str) -> Account:
        """Set an account as the default for the organization"""
        # First, unset any existing default
        self.db.query(Account).filter(
            Account.organization_id == organization_id,
            Account.is_default == True
        ).update({"is_default": False})
        
        # Set this account as default
        account = self.get_account(account_id, organization_id)
        account.is_default = True
        account.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(account)
        return account

    def disconnect_account(self, account_id: str, organization_id: str) -> Account:
        """
        Disconnect AWS account - strips credentials but keeps historical data.
        This is safer than delete as it preserves cost/usage history.
        """
        account = self.get_account(account_id, organization_id)
        
        # Strip credentials (don't delete the record)
        account.role_arn = None
        account.external_id = None
        account.status = AccountStatus.DISCONNECTED
        account.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(account)
        return account

    # Legacy method for backwards compatibility
    def link_account(self, user_id: int, data: AccountCreate) -> Account:
        """Legacy link account method"""
        return self.link_aws_account(
            organization_id=str(user_id),  # Map user_id to org_id (simplified)
            aws_account_id=data.account_id,
            role_arn=data.role_arn,
            external_id=data.external_id
        )

def get_account_service(db: Session) -> AccountService:
    return AccountService(db)

