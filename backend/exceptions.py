"""
Custom Exception Classes for AWS Spot Optimizer Backend
=======================================================

This module defines custom exception classes for better error handling
and more informative error messages throughout the application.

All exceptions inherit from APIError base class which includes HTTP
status codes and error types for consistent API responses.

Author: AWS Spot Optimizer Team
Version: 1.0.0
"""


class APIError(Exception):
    """
    Base exception for all API errors.

    Attributes:
        status_code (int): HTTP status code for the error
        error_type (str): Error type identifier for client-side handling
        message (str): Human-readable error message
        details (dict): Optional additional error details
    """
    status_code = 500
    error_type = 'system_error'

    def __init__(self, message: str, details: dict = None):
        """
        Initialize API error.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error details
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self):
        """
        Convert exception to dictionary for JSON response.

        Returns:
            dict: Error information structured for API response
        """
        error_dict = {
            'success': False,
            'error': {
                'type': self.error_type,
                'message': self.message
            }
        }
        if self.details:
            error_dict['error']['details'] = self.details
        return error_dict


class ValidationError(APIError):
    """
    Raised when input validation fails.

    Examples:
        - Missing required fields
        - Invalid field formats
        - Out of range values
        - Business rule violations
    """
    status_code = 400
    error_type = 'validation_error'


class NotFoundError(APIError):
    """
    Raised when a requested resource is not found.

    Examples:
        - Agent not found
        - Replica not found
        - Pool not found
        - Client not found
    """
    status_code = 404
    error_type = 'not_found'


class AuthenticationError(APIError):
    """
    Raised when authentication fails.

    Examples:
        - Missing token
        - Invalid token
        - Expired token
    """
    status_code = 401
    error_type = 'authentication_error'


class AuthorizationError(APIError):
    """
    Raised when user lacks permission for an action.

    Examples:
        - Accessing another client's resources
        - Disabled client account
        - Operation not allowed in current state
    """
    status_code = 403
    error_type = 'authorization_error'


class DatabaseError(APIError):
    """
    Raised when database operations fail.

    Examples:
        - Connection failures
        - Query execution errors
        - Transaction failures
        - Constraint violations
    """
    status_code = 500
    error_type = 'database_error'


class ConfigurationError(APIError):
    """
    Raised when configuration is invalid or missing.

    Examples:
        - Missing environment variables
        - Invalid configuration values
        - Model loading failures
    """
    status_code = 500
    error_type = 'configuration_error'


class ResourceConflictError(APIError):
    """
    Raised when a resource conflict occurs.

    Examples:
        - Replica already exists
        - Agent already registered
        - Duplicate operation
    """
    status_code = 409
    error_type = 'resource_conflict'


class ExternalServiceError(APIError):
    """
    Raised when external service (AWS, etc.) fails.

    Examples:
        - AWS API failures
        - Instance launch failures
        - Snapshot creation failures
    """
    status_code = 502
    error_type = 'external_service_error'


class RateLimitError(APIError):
    """
    Raised when rate limits are exceeded.

    Examples:
        - Too many requests
        - Too many switches in timeframe
        - Quota exceeded
    """
    status_code = 429
    error_type = 'rate_limit_error'
