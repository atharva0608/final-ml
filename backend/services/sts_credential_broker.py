"""
STS Credential Broker Service - Phase 6 JIT Security

Just-In-Time AWS credential brokering using STS AssumeRole.

Enterprise Guardrails:
- Maximum session duration: 900 seconds (15 minutes)
- Auto-refresh at 80% lifetime (12 minutes)
- AES-256-GCM encryption at rest
- NEVER log decrypted credentials
- Audit all credential requests
- Clock drift safety window: 2 minutes

Architecture:
1. User requests JIT access (creates Approval)
2. Admin approves → triggers STS AssumeRole
3. Broker stores encrypted credentials in credential_cache
4. Background task auto-refreshes before expiration
5. On approval expiration → revoke all associated credentials
"""
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import logging

from backend.models.credential_cache import CredentialCache
from backend.models.account import Account
from backend.models.approval import Approval, ApprovalStatus
from backend.models.audit_log import AuditLog
from backend.core.crypto import encrypt_credential, decrypt_credential, redact_credential
from backend.core.exceptions import ResourceNotFoundError, ForbiddenError
from backend.core.config import settings

logger = logging.getLogger(__name__)

# Enterprise constants
MAX_SESSION_DURATION_SECONDS = 900  # 15 minutes (hard limit)
ROTATION_THRESHOLD_PERCENTAGE = 0.8  # Refresh at 80% lifetime (12 min for 15-min sessions)
CLOCK_DRIFT_SAFETY_SECONDS = 120  # 2-minute safety buffer for clock drift


class STSCredentialBroker:
    """
    STS Temporary Credential Broker

    Manages AWS STS AssumeRole credentials with encryption and auto-rotation.
    """

    def __init__(self, db: Session):
        self.db = db

    def request_credentials(
        self,
        user_id: str,
        account_id: str,
        approval_id: Optional[str] = None,
        session_duration_seconds: int = MAX_SESSION_DURATION_SECONDS,
        session_name_suffix: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Request temporary AWS credentials via STS AssumeRole

        Enterprise Guardrails:
        - Enforces max 15-minute session duration
        - Validates active JIT approval if approval_id provided
        - Encrypts all credentials with AES-256-GCM
        - Audits credential request
        - NEVER logs decrypted credentials

        Args:
            user_id: User requesting credentials
            account_id: AWS account to assume role in
            approval_id: Optional JIT approval ID (required for production)
            session_duration_seconds: Session duration (max 900 seconds)
            session_name_suffix: Optional suffix for session name

        Returns:
            Dict with metadata (NOT decrypted credentials):
            {
                "credential_id": "...",
                "expires_at": "...",
                "rotation_threshold_at": "...",
                "role_arn": "...",
                "session_name": "..."
            }

        Raises:
            ResourceNotFoundError: Account not found
            ForbiddenError: No active approval or expired
            ValueError: Invalid session duration or STS failure
        """
        # Validate session duration (max 15 minutes)
        if session_duration_seconds > MAX_SESSION_DURATION_SECONDS:
            raise ValueError(
                f"Session duration {session_duration_seconds}s exceeds maximum {MAX_SESSION_DURATION_SECONDS}s (15 minutes)"
            )

        # Get account
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ResourceNotFoundError("Account", account_id)

        # Validate approval if provided
        if approval_id:
            approval = self.db.query(Approval).filter(Approval.id == approval_id).first()
            if not approval:
                raise ResourceNotFoundError("Approval", approval_id)

            if approval.user_id != user_id:
                raise ForbiddenError("Approval belongs to different user")

            if approval.status != ApprovalStatus.APPROVED_ACTIVE:
                raise ForbiddenError(f"Approval status is {approval.status}, not APPROVED_ACTIVE")

            now = datetime.now(timezone.utc)
            if approval.expires_at and approval.expires_at <= now:
                raise ForbiddenError("Approval has expired")

        # Check for existing valid credentials
        existing = self._get_valid_credential(user_id, account_id)
        if existing:
            logger.info(f"Reusing existing credential {existing.id} for user {user_id}")
            return self._credential_metadata(existing)

        # Assume role via STS
        try:
            credentials_data = self._assume_role(
                account=account,
                user_id=user_id,
                session_duration_seconds=session_duration_seconds,
                session_name_suffix=session_name_suffix
            )
        except Exception as e:
            logger.error(f"STS AssumeRole failed for account {account_id}: {type(e).__name__}")
            self._audit_credential_request(
                user_id=user_id,
                account_id=account_id,
                approval_id=approval_id,
                success=False,
                error=str(e)
            )
            raise ValueError(f"STS AssumeRole failed: {type(e).__name__}")

        # Encrypt credentials
        try:
            encrypted_access_key = encrypt_credential(credentials_data["AccessKeyId"])
            encrypted_secret_key = encrypt_credential(credentials_data["SecretAccessKey"])
            encrypted_session_token = encrypt_credential(credentials_data["SessionToken"])
        except Exception as e:
            logger.error(f"Credential encryption failed: {type(e).__name__}")
            raise ValueError(f"Credential encryption failed: {type(e).__name__}")

        # Calculate rotation threshold (80% of lifetime)
        issued_at = datetime.now(timezone.utc)
        expires_at = credentials_data["Expiration"]
        lifetime_seconds = (expires_at - issued_at).total_seconds()
        rotation_threshold_seconds = lifetime_seconds * ROTATION_THRESHOLD_PERCENTAGE
        rotation_threshold_at = issued_at + timedelta(seconds=rotation_threshold_seconds)

        # Store in database
        session_name = credentials_data["SessionName"]
        credential_cache = CredentialCache(
            account_id=account_id,
            user_id=user_id,
            approval_id=approval_id,
            encrypted_access_key=encrypted_access_key,
            encrypted_secret_key=encrypted_secret_key,
            encrypted_session_token=encrypted_session_token,
            role_arn=account.role_arn or f"arn:aws:iam::{account.aws_account_id}:role/SpotOptimizerRole",
            session_name=session_name,
            region=account.region or settings.AWS_REGION,
            issued_at=issued_at,
            expires_at=expires_at,
            rotation_threshold_at=rotation_threshold_at,
            is_active='true',
            access_count=0
        )

        self.db.add(credential_cache)
        self.db.commit()
        self.db.refresh(credential_cache)

        # Audit successful credential request
        self._audit_credential_request(
            user_id=user_id,
            account_id=account_id,
            approval_id=approval_id,
            success=True,
            credential_id=str(credential_cache.id)
        )

        logger.info(
            f"Issued STS credentials {credential_cache.id} for user {user_id}, "
            f"expires at {expires_at.isoformat()}"
        )

        return self._credential_metadata(credential_cache)

    def get_credentials(self, user_id: str, account_id: str) -> Dict[str, str]:
        """
        Get decrypted AWS credentials for use

        Enterprise Guardrails:
        - NEVER log decrypted credentials
        - Updates last_accessed_at and access_count
        - Raises error if credential expired or invalid

        Args:
            user_id: User ID
            account_id: Account ID

        Returns:
            Dict with decrypted credentials:
            {
                "aws_access_key_id": "...",
                "aws_secret_access_key": "...",
                "aws_session_token": "...",
                "region": "..."
            }

        Raises:
            ResourceNotFoundError: No valid credentials found
        """
        credential = self._get_valid_credential(user_id, account_id)
        if not credential:
            raise ResourceNotFoundError(
                "CredentialCache",
                f"No valid credentials for user {user_id} and account {account_id}"
            )

        # Decrypt credentials (NEVER log these!)
        try:
            aws_access_key_id = decrypt_credential(credential.encrypted_access_key)
            aws_secret_access_key = decrypt_credential(credential.encrypted_secret_key)
            aws_session_token = decrypt_credential(credential.encrypted_session_token)
        except Exception as e:
            logger.error(f"Credential decryption failed for {credential.id}: {type(e).__name__}")
            raise ValueError(f"Credential decryption failed: {type(e).__name__}")

        # Update access tracking
        credential.last_accessed_at = datetime.utcnow()
        credential.access_count += 1
        self.db.commit()

        logger.info(
            f"Retrieved credentials {credential.id} for user {user_id} "
            f"(access count: {credential.access_count})"
        )

        return {
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "aws_session_token": aws_session_token,
            "region": credential.region
        }

    def rotate_credential(self, credential_id: str) -> bool:
        """
        Rotate a credential by requesting new STS credentials

        Called by background task when credential reaches rotation threshold.

        Args:
            credential_id: Credential cache ID

        Returns:
            True if rotation successful, False otherwise
        """
        credential = self.db.query(CredentialCache).filter(
            CredentialCache.id == credential_id
        ).first()

        if not credential:
            logger.warning(f"Credential {credential_id} not found for rotation")
            return False

        if not credential.is_valid():
            logger.info(f"Credential {credential_id} is invalid, skipping rotation")
            return False

        try:
            # Request new credentials with same parameters
            self.request_credentials(
                user_id=credential.user_id,
                account_id=credential.account_id,
                approval_id=credential.approval_id,
                session_duration_seconds=MAX_SESSION_DURATION_SECONDS
            )

            # Revoke old credential after successful rotation
            self.revoke_credential(credential_id, revoked_by_system=True)

            logger.info(f"Successfully rotated credential {credential_id}")
            return True

        except Exception as e:
            logger.error(f"Credential rotation failed for {credential_id}: {type(e).__name__}")
            return False

    def revoke_credential(self, credential_id: str, revoked_by: Optional[str] = None, revoked_by_system: bool = False) -> bool:
        """
        Revoke a credential immediately

        Args:
            credential_id: Credential cache ID
            revoked_by: User ID who revoked (optional)
            revoked_by_system: If True, system-initiated revocation

        Returns:
            True if revoked successfully
        """
        credential = self.db.query(CredentialCache).filter(
            CredentialCache.id == credential_id
        ).first()

        if not credential:
            return False

        credential.is_active = 'false'
        credential.revoked_at = datetime.utcnow()
        credential.revoked_by = revoked_by or ('system' if revoked_by_system else None)

        self.db.commit()

        logger.info(f"Revoked credential {credential_id} by {credential.revoked_by}")
        return True

    def revoke_approval_credentials(self, approval_id: str) -> int:
        """
        Revoke all credentials associated with an approval

        Called when approval is revoked or expires.

        Args:
            approval_id: Approval ID

        Returns:
            Number of credentials revoked
        """
        credentials = self.db.query(CredentialCache).filter(
            CredentialCache.approval_id == approval_id,
            CredentialCache.is_active == 'true'
        ).all()

        count = 0
        for credential in credentials:
            if self.revoke_credential(str(credential.id), revoked_by_system=True):
                count += 1

        logger.info(f"Revoked {count} credentials for approval {approval_id}")
        return count

    def cleanup_expired_credentials(self) -> int:
        """
        Cleanup expired credentials

        Called by background task to mark expired credentials as inactive.

        Returns:
            Number of credentials cleaned up
        """
        now = datetime.utcnow()
        expired = self.db.query(CredentialCache).filter(
            CredentialCache.is_active == 'true',
            CredentialCache.expires_at <= now
        ).all()

        count = 0
        for credential in expired:
            credential.is_active = 'false'
            count += 1

        self.db.commit()

        if count > 0:
            logger.info(f"Cleaned up {count} expired credentials")

        return count

    def get_credentials_needing_rotation(self) -> list:
        """
        Get credentials that need rotation

        Returns:
            List of credential IDs needing rotation
        """
        now = datetime.utcnow()
        credentials = self.db.query(CredentialCache).filter(
            CredentialCache.is_active == 'true',
            CredentialCache.rotation_threshold_at <= now,
            CredentialCache.expires_at > now  # Not yet expired
        ).all()

        return [str(c.id) for c in credentials]

    # ========================================================================
    # Private helper methods
    # ========================================================================

    def _assume_role(
        self,
        account: Account,
        user_id: str,
        session_duration_seconds: int,
        session_name_suffix: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Assume AWS IAM role via STS

        Enterprise Guardrails:
        - Validates AWS response Expiration field (not local TTL math)
        - Subtracts 2-minute safety window for clock drift
        - NEVER logs credentials

        Args:
            account: AWS account object
            user_id: User ID for session name
            session_duration_seconds: Session duration
            session_name_suffix: Optional session name suffix

        Returns:
            Dict with credentials and metadata from AWS:
            {
                "AccessKeyId": "...",
                "SecretAccessKey": "...",
                "SessionToken": "...",
                "Expiration": datetime,
                "SessionName": "..."
            }

        Raises:
            ClientError: AWS STS error
            ValueError: Invalid response
        """
        # Generate session name
        session_name = f"spot-optimizer-{user_id[:8]}"
        if session_name_suffix:
            session_name += f"-{session_name_suffix}"

        # Truncate to AWS limit (64 chars)
        session_name = session_name[:64]

        # Create STS client
        sts_client = boto3.client('sts', region_name=account.region or settings.AWS_REGION)

        # AssumeRole request
        role_arn = account.role_arn or f"arn:aws:iam::{account.aws_account_id}:role/SpotOptimizerRole"

        assume_role_params = {
            "RoleArn": role_arn,
            "RoleSessionName": session_name,
            "DurationSeconds": session_duration_seconds
        }

        # Add external ID if configured
        if account.external_id:
            assume_role_params["ExternalId"] = account.external_id

        # Call STS AssumeRole
        response = sts_client.assume_role(**assume_role_params)

        # Extract credentials
        creds = response["Credentials"]

        # Enterprise Guardrail: Validate AWS response Expiration field
        # Subtract 2-minute safety window for clock drift
        expiration_from_aws = creds["Expiration"]

        # Ensure expiration is timezone-aware
        if expiration_from_aws.tzinfo is None:
            expiration_from_aws = expiration_from_aws.replace(tzinfo=timezone.utc)

        # Apply clock drift safety window
        safe_expiration = expiration_from_aws - timedelta(seconds=CLOCK_DRIFT_SAFETY_SECONDS)

        logger.info(
            f"STS AssumeRole successful: role={role_arn}, session={session_name}, "
            f"expires={safe_expiration.isoformat()}"
        )

        return {
            "AccessKeyId": creds["AccessKeyId"],
            "SecretAccessKey": creds["SecretAccessKey"],
            "SessionToken": creds["SessionToken"],
            "Expiration": safe_expiration,  # Use safe expiration
            "SessionName": session_name
        }

    def _get_valid_credential(self, user_id: str, account_id: str) -> Optional[CredentialCache]:
        """
        Get a valid (active and not expired) credential

        Args:
            user_id: User ID
            account_id: Account ID

        Returns:
            CredentialCache object or None
        """
        now = datetime.utcnow()
        credential = self.db.query(CredentialCache).filter(
            CredentialCache.user_id == user_id,
            CredentialCache.account_id == account_id,
            CredentialCache.is_active == 'true',
            CredentialCache.expires_at > now
        ).order_by(CredentialCache.expires_at.desc()).first()

        return credential

    def _credential_metadata(self, credential: CredentialCache) -> Dict[str, Any]:
        """
        Get credential metadata (NOT decrypted credentials)

        Safe to return to caller for display purposes.

        Args:
            credential: CredentialCache object

        Returns:
            Dict with metadata
        """
        return {
            "credential_id": str(credential.id),
            "expires_at": credential.expires_at.isoformat(),
            "rotation_threshold_at": credential.rotation_threshold_at.isoformat(),
            "role_arn": credential.role_arn,
            "session_name": credential.session_name,
            "region": credential.region,
            "is_active": credential.is_active == 'true',
            "access_count": credential.access_count
        }

    def _audit_credential_request(
        self,
        user_id: str,
        account_id: str,
        approval_id: Optional[str],
        success: bool,
        credential_id: Optional[str] = None,
        error: Optional[str] = None
    ):
        """
        Audit credential request

        Args:
            user_id: User ID
            account_id: Account ID
            approval_id: Approval ID
            success: Whether request succeeded
            credential_id: Credential ID if successful
            error: Error message if failed
        """
        try:
            audit = AuditLog(
                user_id=user_id,
                action="sts_credential_request",
                resource_type="CredentialCache",
                resource_id=credential_id or account_id,
                status="success" if success else "failure",
                details={
                    "account_id": account_id,
                    "approval_id": approval_id,
                    "credential_id": credential_id,
                    "error": error
                }
            )
            self.db.add(audit)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to audit credential request: {e}")
