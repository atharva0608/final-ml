"""Encryption utilities for storing AWS credentials"""

from cryptography.fernet import Fernet
import os

# Load encryption key from environment
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')

if not ENCRYPTION_KEY:
    # Generate a new key if not set (for development only)
    print("⚠️  WARNING: ENCRYPTION_KEY not set in environment. Using generated key (NOT SECURE for production)")
    ENCRYPTION_KEY = Fernet.generate_key().decode()

fernet = Fernet(ENCRYPTION_KEY.encode())


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential (e.g., AWS secret key)"""
    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a credential"""
    decrypted = fernet.decrypt(ciphertext.encode())
    return decrypted.decode()


def decrypt_credentials(access_key_enc: str, secret_key_enc: str) -> dict:
    """Decrypt AWS credentials for boto3"""
    return {
        'aws_access_key_id': decrypt_credential(access_key_enc),
        'aws_secret_access_key': decrypt_credential(secret_key_enc)
    }
