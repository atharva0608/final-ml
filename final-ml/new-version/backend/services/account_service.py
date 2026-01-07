"""
AWS Account Service

Business logic for managing AWS account connections
"""
from typing import List
from sqlalchemy.orm import Session
from backend.models.account import Account, AccountStatus
from backend.models.user import User
from backend.core.exceptions import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    AWSAuthenticationError,
)
from backend.core.validators import validate_aws_account_id, validate_aws_role_arn
from backend.core.logger import StructuredLogger
from datetime import datetime

logger = StructuredLogger(__name__)


class AccountService:
    """Service for AWS account management"""

    def __init__(self, db: Session):
        self.db = db

    def link_aws_account(
        self,
        user_id: str,
        aws_account_id: str,
        role_arn: str,
        external_id: str
    ) -> Account:
        """
        Link an AWS account to user

        Args:
            user_id: User UUID
            aws_account_id: 12-digit AWS account ID
            role_arn: IAM role ARN for cross-account access
            external_id: External ID for role assumption

        Returns:
            Account model

        Raises:
            ResourceAlreadyExistsError: If account already linked
            AWSAuthenticationError: If credentials invalid
        """
        # Validate formats
        if not validate_aws_account_id(aws_account_id):
            raise AWSAuthenticationError(f"Invalid AWS account ID format: {aws_account_id}")

        if not validate_aws_role_arn(role_arn):
            raise AWSAuthenticationError(f"Invalid IAM role ARN format: {role_arn}")

        # Check if already linked
        existing = self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.aws_account_id == aws_account_id
        ).first()

        if existing:
            raise ResourceAlreadyExistsError(
                "Account",
                aws_account_id,
                "This AWS account is already linked"
            )

        # Create account record
        account = Account(
            user_id=user_id,
            aws_account_id=aws_account_id,
            role_arn=role_arn,
            external_id=external_id,
            status=AccountStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        logger.info(
            "AWS account linked",
            account_id=account.id,
            user_id=user_id,
            aws_account_id=aws_account_id
        )

        # TODO: Trigger async worker to verify credentials and discover clusters
        # This would be done by a Celery task

        return account

    def list_accounts(self, user_id: str) -> List[Account]:
        """
        List all AWS accounts for user

        Args:
            user_id: User UUID

        Returns:
            List of Account models
        """
        accounts = self.db.query(Account).filter(
            Account.user_id == user_id
        ).order_by(Account.created_at.desc()).all()

        return accounts

    def get_account(self, account_id: str, user_id: str) -> Account:
        """
        Get specific AWS account

        Args:
            account_id: Account UUID
            user_id: User UUID

        Returns:
            Account model

        Raises:
            ResourceNotFoundError: If account not found
        """
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == user_id
        ).first()

        if not account:
            raise ResourceNotFoundError("Account", account_id)

        return account

    def update_account_status(
        self,
        account_id: str,
        status: AccountStatus
    ) -> Account:
        """
        Update account status

        Args:
            account_id: Account UUID
            status: New status

        Returns:
            Updated Account

        Raises:
            ResourceNotFoundError: If account not found
        """
        account = self.db.query(Account).filter(
            Account.id == account_id
        ).first()

        if not account:
            raise ResourceNotFoundError("Account", account_id)

        account.status = status
        account.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(account)

        logger.info(
            "Account status updated",
            account_id=account_id,
            status=status.value
        )

        return account

    def delete_account(self, account_id: str, user_id: str) -> bool:
        """
        Delete AWS account connection

        Args:
            account_id: Account UUID
            user_id: User UUID

        Returns:
            True if deleted

        Raises:
            ResourceNotFoundError: If account not found
        """
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == user_id
        ).first()

        if not account:
            raise ResourceNotFoundError("Account", account_id)

        # Cascading delete will remove associated clusters
        self.db.delete(account)
        self.db.commit()

        logger.info(
            "AWS account deleted",
            account_id=account_id,
            user_id=user_id
        )

        return True


def get_account_service(db: Session) -> AccountService:
    """Get account service instance"""
    return AccountService(db)
