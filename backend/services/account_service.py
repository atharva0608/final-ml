import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.account import Account, AccountStatus
from backend.schemas.account_schemas import AccountCreate, AccountResponse

class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def verify_connection(self, role_arn: str, external_id: str) -> bool:
        """Verify AWS connection by attempting to assume role"""
        try:
            sts = boto3.client('sts')
            sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="SpotOptimizerVerify",
                ExternalId=external_id
            )
            return True
        except ClientError as e:
            raise HTTPException(400, f"AWS Connection Failed: {str(e)}")

    def list_accounts(self, organization_id: str) -> List[Account]:
        """List all accounts for an organization"""
        return self.db.query(Account).filter(
            Account.organization_id == organization_id
        ).all()

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
        external_id: str
    ) -> Account:
        """Link a new AWS account after verifying credentials"""
        # Verify connection first
        self.verify_connection(role_arn, external_id)
        
        # Check if account already exists
        existing = self.db.query(Account).filter(
            Account.aws_account_id == aws_account_id,
            Account.organization_id == organization_id
        ).first()
        if existing:
            raise HTTPException(400, "Account already linked")

        account = Account(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            aws_account_id=aws_account_id,
            role_arn=role_arn,
            external_id=external_id,
            status=AccountStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

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
