"""
AWS Spot Optimizer - Authentication Module
===========================================
Authentication middleware for API endpoints
"""

import logging
from functools import wraps
from flask import request, jsonify

from backend.database_manager import execute_query
from backend.utils import log_system_event

logger = logging.getLogger(__name__)


def require_client_token(f):
    """Validate client token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '').strip()

        # Fallback to JSON body
        if not token:
            token = request.json.get('client_token') if request.json else None
            if token:
                token = token.strip()

        if not token:
            logger.warning(f"Missing client token - endpoint: {request.path}")
            return jsonify({'error': 'Missing client token'}), 401

        # Log token prefix for debugging (first 8 chars only)
        token_preview = f"{token[:8]}...{token[-4:]}" if len(token) > 12 else token[:8]

        # Check if client exists and is active
        client = execute_query(
            "SELECT id, name, is_active FROM clients WHERE client_token = %s",
            (token,),
            fetch_one=True
        )

        if not client:
            logger.warning(f"Invalid client token attempt - token: {token_preview}, endpoint: {request.path}")
            log_system_event('auth_failed', 'warning',
                           f'Invalid client token attempt for endpoint {request.path}')
            return jsonify({'error': 'Invalid client token'}), 401

        if not client['is_active']:
            logger.warning(f"Inactive client attempted access - client_id: {client['id']}, endpoint: {request.path}")
            log_system_event('auth_failed', 'warning',
                           f'Inactive client {client["id"]} attempted access',
                           client['id'])
            return jsonify({'error': 'Client account is not active'}), 403

        # Token is valid and client is active
        request.client_id = client['id']
        request.client_name = client['name']
        logger.debug(f"Token validated - client: {client['name']}, endpoint: {request.path}")
        return f(*args, **kwargs)

    return decorated_function
