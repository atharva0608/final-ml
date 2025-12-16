"""
Authentication Package

Contains JWT authentication, password hashing, and user management.
"""

from .jwt import create_access_token, decode_token, get_current_user, get_current_active_user
from .password import hash_password, verify_password
from .dependencies import require_role, check_rate_limit

__all__ = [
    'create_access_token',
    'decode_token',
    'get_current_user',
    'get_current_active_user',
    'hash_password',
    'verify_password',
    'require_role',
    'check_rate_limit',
]
