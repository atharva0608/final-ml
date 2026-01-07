"""
Authentication API Routes

Endpoints for user signup, login, token refresh, and password management
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.schemas.auth_schemas import (
    SignupRequest,
    LoginRequest,
    TokenResponse,
    LoginResponse,
    UserProfile,
    PasswordChangeRequest,
)
from backend.services.auth_service import get_auth_service, AuthService
from backend.core.dependencies import get_current_user, get_current_user_context
from backend.core.logger import StructuredLogger
from backend.models.user import User
from backend.schemas.auth_schemas import UserContext

logger = StructuredLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Create a new user account and return authentication tokens"
)
def signup(
    signup_data: SignupRequest,
    db: Session = Depends(get_db)
) -> LoginResponse:
    """
    Register a new user

    Args:
        signup_data: User signup data (email, password)
        db: Database session

    Returns:
        TokenResponse with access token

    Raises:
        409: Email already exists
        422: Validation error
    """
    auth_service = get_auth_service(db)
    user, tokens = auth_service.signup(signup_data)

    logger.info(
        "User signup successful",
        user_id=user.id,
        email=user.email
    )

    # Create UserContext
    user_context = UserContext(
        user_id=user.id,
        email=user.email,
        role=user.role.value
    )

    # Combine tokens and user data
    response = LoginResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
        user=user_context
    )

    return response


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User login",
    description="Authenticate user with email and password"
)
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
) -> LoginResponse:
    """
    Authenticate user and return tokens

    Args:
        login_data: Login credentials (email, password)
        db: Database session

    Returns:
        TokenResponse with access token

    Raises:
        401: Invalid credentials
    """
    auth_service = get_auth_service(db)
    user, tokens = auth_service.login(login_data)

    logger.info(
        "User login successful",
        user_id=user.id,
        email=user.email
    )

    # Create UserContext
    user_context = UserContext(
        user_id=user.id,
        email=user.email,
        role=user.role.value
    )

    # Combine tokens and user data
    response = LoginResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        refresh_token=tokens.refresh_token,
        user=user_context
    )

    return response


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Generate new access token using refresh token"
)
def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Refresh access token

    Args:
        refresh_token: Refresh token
        db: Database session

    Returns:
        TokenResponse with new access token

    Raises:
        401: Invalid or expired refresh token
    """
    auth_service = get_auth_service(db)
    tokens = auth_service.refresh_token(refresh_token)

    logger.info("Access token refreshed")

    return tokens


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current user profile",
    description="Get profile information for authenticated user"
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> UserProfile:
    """
    Get current user profile

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        UserProfile with user information

    Raises:
        401: Not authenticated
    """
    auth_service = get_auth_service(db)
    profile = auth_service.get_user_profile(current_user.id)

    return profile


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Change password for authenticated user"
)
def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    """
    Change user password

    Args:
        password_data: Old and new passwords
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        401: Invalid old password
        422: Validation error
    """
    auth_service = get_auth_service(db)
    auth_service.change_password(current_user.id, password_data)

    logger.info(
        "Password changed",
        user_id=current_user.id
    )

    return {"message": "Password changed successfully"}


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description="Logout current user (client-side token removal)"
)
def logout(
    user_context: UserContext = Depends(get_current_user_context)
) -> dict:
    """
    Logout user

    Note: This endpoint primarily serves as a marker for client-side logout.
    In a stateless JWT system, actual logout is handled client-side by
    removing the token. For production, consider implementing token
    blacklisting using Redis.

    Args:
        user_context: Current user context

    Returns:
        Success message
    """
    logger.info(
        "User logout",
        user_id=user_context.user_id
    )

    return {"message": "Logged out successfully"}
