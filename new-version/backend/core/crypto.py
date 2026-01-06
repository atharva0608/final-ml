"""
Cryptography Utilities

Encryption, decryption, hashing, and token generation utilities
"""
import hashlib
import secrets
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from backend.core.config import settings


# Password hashing context (bcrypt)
# Using lazy initialization to avoid issues with settings loading
_pwd_context = None

def get_pwd_context():
    """Get or create the password hashing context"""
    global _pwd_context
    if _pwd_context is None:
        _pwd_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=getattr(settings, 'BCRYPT_ROUNDS', 12)
        )
    return _pwd_context


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return get_pwd_context().hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        return get_pwd_context().verify(plain_password, hashed_password)
    except Exception as e:
        # Handle any bcrypt verification errors gracefully
        print(f"Password verification error: {e}")
        return False


def generate_api_key(prefix: str = "sk-") -> tuple[str, str, str]:
    """
    Generate a secure API key

    Args:
        prefix: API key prefix (default: "sk-")

    Returns:
        Tuple of (full_key, key_hash, key_prefix)
        - full_key: The actual API key to give to user (store this nowhere!)
        - key_hash: SHA-256 hash to store in database
        - key_prefix: First 8 chars for display purposes
    """
    # Generate secure random key (32 bytes = 64 hex chars)
    random_part = secrets.token_hex(32)
    full_key = f"{prefix}{random_part}"

    # Hash the key for storage
    key_hash = hash_api_key(full_key)

    # Extract prefix for display
    key_prefix = full_key[:8]

    return (full_key, key_hash, key_prefix)


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA-256

    Args:
        api_key: The API key to hash

    Returns:
        SHA-256 hash of the key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token

    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time (default: from settings)

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    # Encode token
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token

    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time (default: from settings)

    Returns:
        Encoded JWT refresh token
    """
    to_encode = data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )

    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})

    # Encode token
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and verify a JWT token

    Args:
        token: JWT token to decode

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def generate_reset_token(length: int = 32) -> str:
    """
    Generate a secure password reset token

    Args:
        length: Token length in bytes

    Returns:
        URL-safe token string
    """
    return secrets.token_urlsafe(length)


def generate_verification_code(length: int = 6) -> str:
    """
    Generate a numeric verification code

    Args:
        length: Code length (default: 6 digits)

    Returns:
        Numeric verification code
    """
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def hash_data(data: str) -> str:
    """
    Hash arbitrary data using SHA-256

    Args:
        data: Data to hash

    Returns:
        SHA-256 hash hex string
    """
    return hashlib.sha256(data.encode()).hexdigest()


def verify_token_type(token: str, expected_type: str) -> bool:
    """
    Verify the type of a JWT token

    Args:
        token: JWT token
        expected_type: Expected token type (e.g., "refresh", "access")

    Returns:
        True if token type matches, False otherwise
    """
    payload = decode_token(token)
    if not payload:
        return False

    token_type = payload.get("type", "access")  # Default to access if not specified
    return token_type == expected_type


def generate_secure_random_string(length: int = 32) -> str:
    """
    Generate a cryptographically secure random string

    Args:
        length: Length in bytes

    Returns:
        Random hex string
    """
    return secrets.token_hex(length)


def constant_time_compare(a: str, b: str) -> bool:
    """
    Compare two strings in constant time to prevent timing attacks

    Args:
        a: First string
        b: Second string

    Returns:
        True if strings are equal, False otherwise
    """
    return secrets.compare_digest(a, b)
