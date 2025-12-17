"""
Authentication API Endpoints

User registration, login, and profile management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from datetime import datetime

from database.connection import get_db
from database.models import User, UserRole
from auth.jwt import create_access_token, get_current_active_user
from auth.password import hash_password, verify_password

router = APIRouter()


# Request/Response Models
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., max_length=100)


class UserLogin(BaseModel):
    identifier: str = Field(..., description="Username or email")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserProfile(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    active_sessions_count: int


# Endpoints
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user

    Creates a new user account and returns an access token.

    Args:
        user_data: User registration data
        db: Database session

    Returns:
        Access token and user info

    Raises:
        HTTPException: If email or username already exists
    """
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered"
        )

    # Create new user
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=UserRole.USER.value,
        is_active=True,
        created_at=datetime.utcnow()
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate access token
    access_token = create_access_token({"sub": new_user.email})

    return TokenResponse(
        access_token=access_token,
        user={
            "id": str(new_user.id),
            "email": new_user.email,
            "username": new_user.username,
            "full_name": new_user.full_name,
            "role": new_user.role,
        }
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    User login

    Authenticate user and return access token.
    Supports login with either username or email.

    Args:
        credentials: Login credentials (username/email and password)
        db: Database session

    Returns:
        Access token and user info

    Raises:
        HTTPException: If credentials are invalid
    """
    # Find user by username OR email
    user = db.query(User).filter(
        (User.username == credentials.identifier) | (User.email == credentials.identifier)
    ).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    # Generate access token
    access_token = create_access_token({"sub": user.email})

    return TokenResponse(
        access_token=access_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        }
    )


@router.get("/profile", response_model=UserProfile)
async def get_profile(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """
    Get current user profile

    Args:
        current_user: Authenticated user from JWT token
        db: Database session

    Returns:
        User profile data
    """
    # Count active sandbox sessions
    # TODO: Implement SandboxSession model
    # from database.models import SandboxSession
    # active_sessions = db.query(SandboxSession).filter(
    #     SandboxSession.user_id == current_user.id,
    #     SandboxSession.is_active == True
    # ).count()
    active_sessions = 0  # Temporary: no rate limiting

    return UserProfile(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        active_sessions_count=active_sessions
    )


@router.get("/verify")
async def verify_token(current_user: User = Depends(get_current_active_user)):
    """
    Verify JWT token

    Simple endpoint to check if token is valid.

    Args:
        current_user: Authenticated user

    Returns:
        Success message
    """
    return {
        "valid": True,
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "role": current_user.role
        }
    }
