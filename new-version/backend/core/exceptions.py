"""
Custom Exceptions

Application-specific exception classes for error handling
"""
from typing import Optional, Dict, Any
from fastapi import status


class SpotOptimizerException(Exception):
    """Base exception for all application exceptions"""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


# Authentication & Authorization Exceptions

class AuthenticationError(SpotOptimizerException):
    """Raised when authentication fails"""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, details)


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid"""

    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(message)


class TokenExpiredError(AuthenticationError):
    """Raised when JWT token is expired"""

    def __init__(self, message: str = "Token has expired"):
        super().__init__(message)


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid"""

    def __init__(self, message: str = "Invalid or malformed token"):
        super().__init__(message)


class AuthorizationError(SpotOptimizerException):
    """Raised when authorization fails"""

    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_403_FORBIDDEN, details)


class InsufficientPermissionsError(AuthorizationError):
    """Raised when user lacks required permissions"""

    def __init__(self, message: str = "Insufficient permissions to perform this action"):
        super().__init__(message)


# Resource Exceptions

class ResourceNotFoundError(SpotOptimizerException):
    """Raised when a resource is not found"""

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        message: Optional[str] = None
    ):
        msg = message or f"{resource_type} with ID '{resource_id}' not found"
        super().__init__(msg, status.HTTP_404_NOT_FOUND, {"resource_type": resource_type, "resource_id": resource_id})


class ResourceAlreadyExistsError(SpotOptimizerException):
    """Raised when attempting to create a resource that already exists"""

    def __init__(
        self,
        resource_type: str,
        identifier: str,
        message: Optional[str] = None
    ):
        msg = message or f"{resource_type} with identifier '{identifier}' already exists"
        super().__init__(msg, status.HTTP_409_CONFLICT, {"resource_type": resource_type, "identifier": identifier})


class ResourceConflictError(SpotOptimizerException):
    """Raised when a resource operation conflicts with current state"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_409_CONFLICT, details)


# Validation Exceptions

class ValidationError(SpotOptimizerException):
    """Raised when data validation fails"""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if field:
            error_details["field"] = field
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, error_details)


class InvalidInputError(ValidationError):
    """Raised when input data is invalid"""

    def __init__(self, field: str, message: str):
        super().__init__(f"Invalid {field}: {message}", field)


# AWS Exceptions

class AWSError(SpotOptimizerException):
    """Base exception for AWS-related errors"""

    def __init__(self, message: str, service: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if service:
            error_details["service"] = service
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, error_details)


class AWSAuthenticationError(AWSError):
    """Raised when AWS authentication fails"""

    def __init__(self, message: str = "AWS authentication failed"):
        super().__init__(message)


class AWSResourceNotFoundError(AWSError):
    """Raised when AWS resource is not found"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            f"AWS {resource_type} '{resource_id}' not found",
            details={"resource_type": resource_type, "resource_id": resource_id}
        )


class AWSAccessDeniedError(AWSError):
    """Raised when AWS access is denied"""

    def __init__(self, message: str = "Access denied to AWS resource"):
        super().__init__(message)


class AWSRateLimitError(AWSError):
    """Raised when AWS rate limit is exceeded"""

    def __init__(self, service: str, message: str = "AWS API rate limit exceeded"):
        super().__init__(message, service)


# Cluster & Kubernetes Exceptions

class ClusterError(SpotOptimizerException):
    """Base exception for cluster-related errors"""

    def __init__(self, message: str, cluster_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        if cluster_id:
            error_details["cluster_id"] = cluster_id
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, error_details)


class ClusterNotFoundError(ResourceNotFoundError):
    """Raised when cluster is not found"""

    def __init__(self, cluster_id: str):
        super().__init__("Cluster", cluster_id)


class ClusterNotActiveError(ClusterError):
    """Raised when operation requires active cluster"""

    def __init__(self, cluster_id: str, current_status: str):
        super().__init__(
            f"Cluster is not active (current status: {current_status})",
            cluster_id,
            {"current_status": current_status}
        )


class AgentNotInstalledError(ClusterError):
    """Raised when Kubernetes Agent is not installed"""

    def __init__(self, cluster_id: str):
        super().__init__(
            "Kubernetes Agent is not installed on this cluster",
            cluster_id
        )


class AgentTimeoutError(ClusterError):
    """Raised when Agent fails to respond"""

    def __init__(self, cluster_id: str):
        super().__init__(
            "Kubernetes Agent failed to respond (timeout)",
            cluster_id
        )


# Database Exceptions

class DatabaseError(SpotOptimizerException):
    """Base exception for database errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails"""

    def __init__(self, message: str = "Database connection failed"):
        super().__init__(message)


class DatabaseIntegrityError(DatabaseError):
    """Raised when database integrity constraint is violated"""

    def __init__(self, message: str, constraint: Optional[str] = None):
        details = {"constraint": constraint} if constraint else None
        super().__init__(message, details)


# Optimization Exceptions

class OptimizationError(SpotOptimizerException):
    """Base exception for optimization-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)


class OptimizationJobNotFoundError(ResourceNotFoundError):
    """Raised when optimization job is not found"""

    def __init__(self, job_id: str):
        super().__init__("Optimization Job", job_id)


class OptimizationJobFailedError(OptimizationError):
    """Raised when optimization job fails"""

    def __init__(self, job_id: str, reason: str):
        super().__init__(
            f"Optimization job {job_id} failed: {reason}",
            {"job_id": job_id, "reason": reason}
        )


# Policy Exceptions

class PolicyError(SpotOptimizerException):
    """Base exception for policy-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)


class InvalidPolicyError(PolicyError):
    """Raised when policy configuration is invalid"""

    def __init__(self, message: str, validation_errors: Optional[list] = None):
        details = {"validation_errors": validation_errors} if validation_errors else None
        super().__init__(message, details)


# Rate Limiting Exceptions

class RateLimitError(SpotOptimizerException):
    """Raised when rate limit is exceeded"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None
    ):
        details = {"retry_after_seconds": retry_after} if retry_after else None
        super().__init__(message, status.HTTP_429_TOO_MANY_REQUESTS, details)


# External Service Exceptions

class ExternalServiceError(SpotOptimizerException):
    """Base exception for external service errors"""

    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        error_details = details or {}
        error_details["service"] = service
        super().__init__(message, status.HTTP_502_BAD_GATEWAY, error_details)


class EmailServiceError(ExternalServiceError):
    """Raised when email service fails"""

    def __init__(self, message: str = "Email service unavailable"):
        super().__init__("email", message)


class StripeError(ExternalServiceError):
    """Raised when Stripe API fails"""

    def __init__(self, message: str):
        super().__init__("stripe", message)


# File & Upload Exceptions

class FileError(SpotOptimizerException):
    """Base exception for file-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_400_BAD_REQUEST, details)


class FileTooLargeError(FileError):
    """Raised when uploaded file exceeds size limit"""

    def __init__(self, max_size_mb: int):
        super().__init__(
            f"File size exceeds maximum allowed size ({max_size_mb}MB)",
            {"max_size_mb": max_size_mb}
        )


class InvalidFileTypeError(FileError):
    """Raised when file type is not allowed"""

    def __init__(self, file_type: str, allowed_types: list):
        super().__init__(
            f"File type '{file_type}' not allowed. Allowed types: {', '.join(allowed_types)}",
            {"file_type": file_type, "allowed_types": allowed_types}
        )


# ML/Lab Exceptions

class MLModelError(SpotOptimizerException):
    """Base exception for ML model errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)


class MLModelNotFoundError(ResourceNotFoundError):
    """Raised when ML model is not found"""

    def __init__(self, model_id: str):
        super().__init__("ML Model", model_id)


class MLModelVersionConflictError(ResourceConflictError):
    """Raised when ML model version already exists"""

    def __init__(self, version: str):
        super().__init__(f"ML model version '{version}' already exists")


class InvalidModelError(MLModelError):
    """Raised when ML model file is invalid"""

    def __init__(self, message: str = "Invalid ML model file"):
        super().__init__(message)
