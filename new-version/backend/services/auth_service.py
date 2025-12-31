"""
Authentication Service

Business logic for user authentication, signup, login, and token management
"""
from typing import Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.models.user import User, UserRole
from backend.schemas.auth_schemas import (
    SignupRequest,
    LoginRequest,
    TokenResponse,
    UserProfile,
    PasswordChangeRequest,
)
from backend.core.crypto import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
)
from backend.core.exceptions import (
    InvalidCredentialsError,
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
    ValidationError,
)
from backend.core.logger import StructuredLogger
from backend.core.config import settings

logger = StructuredLogger(__name__)


class AuthService:
    """Authentication service for user management and token operations"""

    def __init__(self, db: Session):
        """
        Initialize authentication service

        Args:
            db: Database session
        """
        self.db = db

    def signup(self, signup_data: SignupRequest) -> Tuple[User, TokenResponse]:
        """
        Register a new user

        Args:
            signup_data: Signup request data

        Returns:
            Tuple of (User, TokenResponse)

        Raises:
            ResourceAlreadyExistsError: If email already exists
        """
        # Check if user already exists
        existing_user = self.db.query(User).filter(
            User.email == signup_data.email.lower()
        ).first()

        if existing_user:
            logger.warning(
                "Signup attempt with existing email",
                email=signup_data.email
            )
            raise ResourceAlreadyExistsError(
                "User",
                signup_data.email,
                "An account with this email already exists"
            )

        # Hash password
        password_hash = hash_password(signup_data.password)

        # Create new user
        new_user = User(
            email=signup_data.email.lower(),
            password_hash=password_hash,
            role=UserRole.CLIENT,  # Default role
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)

        logger.info(
            "New user registered",
            user_id=new_user.id,
            email=new_user.email
        )

        # Generate tokens
        tokens = self._generate_tokens(new_user)

        return new_user, tokens

    def login(self, login_data: LoginRequest) -> Tuple[User, TokenResponse]:
        """
        Authenticate user and generate tokens

        Args:
            login_data: Login request data

        Returns:
            Tuple of (User, TokenResponse)

        Raises:
            InvalidCredentialsError: If credentials are invalid
        """
        # Find user by email
        user = self.db.query(User).filter(
            User.email == login_data.email.lower()
        ).first()

        if not user:
            logger.warning(
                "Login attempt with non-existent email",
                email=login_data.email
            )
            raise InvalidCredentialsError()

        # Verify password
        if not verify_password(login_data.password, user.password_hash):
            logger.warning(
                "Login attempt with invalid password",
                user_id=user.id,
                email=user.email
            )
            raise InvalidCredentialsError()

        logger.info(
            "User logged in successfully",
            user_id=user.id,
            email=user.email
        )

        # Generate tokens
        tokens = self._generate_tokens(user)

        return user, tokens

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Generate new access token from refresh token

        Args:
            refresh_token: Refresh token

        Returns:
            New TokenResponse

        Raises:
            InvalidCredentialsError: If refresh token is invalid
        """
        from backend.core.crypto import decode_token, verify_token_type

        # Verify token type
        if not verify_token_type(refresh_token, "refresh"):
            logger.warning("Invalid token type for refresh")
            raise InvalidCredentialsError("Invalid refresh token")

        # Decode token
        payload = decode_token(refresh_token)
        if not payload:
            logger.warning("Failed to decode refresh token")
            raise InvalidCredentialsError("Invalid or expired refresh token")

        # Get user
        user_id = payload.get("sub")
        user = self.db.query(User).filter(User.id == user_id).first()

        if not user:
            logger.warning(
                "Refresh token for non-existent user",
                user_id=user_id
            )
            raise InvalidCredentialsError("User not found")

        logger.info(
            "Access token refreshed",
            user_id=user.id
        )

        # Generate new access token only
        access_token = create_access_token(
            data={"sub": user.id, "email": user.email, "role": user.role.value}
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    def get_user_profile(self, user_id: str) -> UserProfile:
        """
        Get user profile

        Args:
            user_id: User UUID

        Returns:
            UserProfile

        Raises:
            ResourceNotFoundError: If user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()

        if not user:
            raise ResourceNotFoundError("User", user_id)

        return UserProfile(
            id=user.id,
            email=user.email,
            role=user.role.value,
            created_at=user.created_at
        )

    def change_password(
        self,
        user_id: str,
        password_data: PasswordChangeRequest
    ) -> bool:
        """
        Change user password

        Args:
            user_id: User UUID
            password_data: Password change request

        Returns:
            True if successful

        Raises:
            ResourceNotFoundError: If user not found
            InvalidCredentialsError: If old password is incorrect
        """
        user = self.db.query(User).filter(User.id == user_id).first()

        if not user:
            raise ResourceNotFoundError("User", user_id)

        # Verify old password
        if not verify_password(password_data.old_password, user.password_hash):
            logger.warning(
                "Password change attempt with incorrect old password",
                user_id=user.id
            )
            raise InvalidCredentialsError("Current password is incorrect")

        # Hash new password
        new_password_hash = hash_password(password_data.new_password)

        # Update password
        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()

        self.db.commit()

        logger.info(
            "Password changed successfully",
            user_id=user.id
        )

        return True

    def _generate_tokens(self, user: User) -> TokenResponse:
        """
        Generate access and refresh tokens for user

        Args:
            user: User model

        Returns:
            TokenResponse with access and refresh tokens
        """
        # Create access token
        access_token = create_access_token(
            data={
                "sub": user.id,
                "email": user.email,
                "role": user.role.value
            }
        )

        # Create refresh token
        refresh_token = create_refresh_token(
            data={
                "sub": user.id,
                "email": user.email
            }
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )


def get_auth_service(db: Session) -> AuthService:
    """
    Get authentication service instance

    Args:
        db: Database session

    Returns:
        AuthService instance
    """
    return AuthService(db)
