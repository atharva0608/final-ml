"""
Cryptography Utilities

Encryption, decryption, hashing, and token generation utilities

Phase 6 Enhancement: AES-256-GCM encryption for AWS STS credentials
Enterprise Guardrails:
- AES-256-GCM authenticated encryption
- Unique nonce per encryption operation
- NEVER log decrypted credentials
- Auto-generate encryption key from JWT_SECRET_KEY if not configured
"""
import hashlib
import secrets
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
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

    # Convert datetime to Unix timestamp (integer) for JWT standard compliance
    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(datetime.utcnow().timestamp())
    })

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

    # Convert datetime to Unix timestamp (integer) for JWT standard compliance
    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "type": "refresh"
    })

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


# ============================================================================
# Phase 6: AES-256-GCM Encryption for STS Credentials
# ============================================================================

# Derive encryption key from JWT secret (or use dedicated key in production)
_ENCRYPTION_KEY = None

def _get_encryption_key() -> bytes:
    """
    Get or derive the AES-256 encryption key

    In production, use a dedicated CREDENTIAL_ENCRYPTION_KEY environment variable.
    For development, derive from JWT_SECRET_KEY.

    Returns:
        32-byte AES-256 key
    """
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        # Try to get dedicated encryption key from environment
        dedicated_key = os.getenv('CREDENTIAL_ENCRYPTION_KEY')

        if dedicated_key:
            # Use dedicated key (must be 32 bytes base64-encoded)
            try:
                _ENCRYPTION_KEY = base64.b64decode(dedicated_key)
                if len(_ENCRYPTION_KEY) != 32:
                    raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be 32 bytes")
            except Exception as e:
                raise ValueError(f"Invalid CREDENTIAL_ENCRYPTION_KEY: {e}")
        else:
            # Derive from JWT_SECRET_KEY using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'spot-optimizer-credential-salt',  # Fixed salt for deterministic key
                iterations=100000,
            )
            _ENCRYPTION_KEY = kdf.derive(settings.JWT_SECRET_KEY.encode())

    return _ENCRYPTION_KEY


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential string using AES-256-GCM

    Enterprise Guardrails:
    - AES-256-GCM authenticated encryption
    - Unique 12-byte nonce per encryption
    - Returns base64-encoded: nonce + ciphertext + tag

    Args:
        plaintext: Credential to encrypt (access key, secret key, session token)

    Returns:
        Base64-encoded encrypted credential (safe to store in database)

    Raises:
        ValueError: If encryption fails
    """
    try:
        # Get encryption key
        key = _get_encryption_key()

        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Generate random 12-byte nonce (NEVER reuse!)
        nonce = os.urandom(12)

        # Encrypt with authentication
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

        # Combine nonce + ciphertext and base64 encode
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode('ascii')

    except Exception as e:
        # NEVER log the plaintext in error messages!
        raise ValueError(f"Credential encryption failed: {type(e).__name__}")


def decrypt_credential(encrypted_credential: str) -> str:
    """
    Decrypt an AES-256-GCM encrypted credential

    Enterprise Guardrails:
    - NEVER log the decrypted result
    - Verify authentication tag
    - Constant-time comparison for tag verification

    Args:
        encrypted_credential: Base64-encoded encrypted credential

    Returns:
        Decrypted plaintext credential

    Raises:
        ValueError: If decryption or authentication fails
    """
    try:
        # Get encryption key
        key = _get_encryption_key()

        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Decode from base64
        encrypted_data = base64.b64decode(encrypted_credential)

        # Extract nonce (first 12 bytes) and ciphertext (rest)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        # Decrypt and verify authentication tag
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode('utf-8')

    except Exception as e:
        # NEVER log the encrypted data or decrypted result!
        raise ValueError(f"Credential decryption failed: {type(e).__name__}")


def generate_credential_encryption_key() -> str:
    """
    Generate a new random 32-byte AES-256 key for production use

    Usage:
        export CREDENTIAL_ENCRYPTION_KEY=$(python -c "from backend.core.crypto import generate_credential_encryption_key; print(generate_credential_encryption_key())")

    Returns:
        Base64-encoded 32-byte key
    """
    key = os.urandom(32)
    return base64.b64encode(key).decode('ascii')


def redact_credential(credential: str, show_chars: int = 4) -> str:
    """
    Redact a credential for safe logging

    Args:
        credential: Credential to redact
        show_chars: Number of characters to show at the end

    Returns:
        Redacted credential (e.g., "****xyz123")
    """
    if not credential or len(credential) <= show_chars:
        return "****"

    return "*" * (len(credential) - show_chars) + credential[-show_chars:]
