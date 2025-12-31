"""
Structured Logging Configuration

Centralized logging setup with structured JSON logging
"""
import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime
import json
from backend.core.config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON

        Args:
            record: Log record

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Text formatter for human-readable logs"""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logging() -> None:
    """
    Configure application logging

    Sets up structured JSON logging in production, text logging in development
    """
    # Get log level from settings
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers = []

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Set formatter based on environment
    if settings.LOG_FORMAT == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance for a module

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class StructuredLogger:
    """
    Structured logger with context support

    Provides methods for logging with structured fields
    """

    def __init__(self, name: str):
        """
        Initialize structured logger

        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ) -> None:
        """
        Log with structured fields

        Args:
            level: Log level
            message: Log message
            extra_fields: Additional structured fields
            exc_info: Include exception info
        """
        extra = {"extra_fields": extra_fields} if extra_fields else {}
        self.logger.log(level, message, extra=extra, exc_info=exc_info)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with structured fields"""
        self._log(logging.DEBUG, message, kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message with structured fields"""
        self._log(logging.INFO, message, kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with structured fields"""
        self._log(logging.WARNING, message, kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log error message with structured fields"""
        self._log(logging.ERROR, message, kwargs, exc_info)

    def critical(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log critical message with structured fields"""
        self._log(logging.CRITICAL, message, kwargs, exc_info)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback"""
        self._log(logging.ERROR, message, kwargs, exc_info=True)


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_id: Optional[str] = None
) -> None:
    """
    Log HTTP request

    Args:
        method: HTTP method
        path: Request path
        status_code: Response status code
        duration_ms: Request duration in milliseconds
        user_id: Optional user ID
    """
    logger = StructuredLogger("api")
    logger.info(
        "HTTP request",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        user_id=user_id
    )


def log_database_query(
    query: str,
    duration_ms: float,
    rows_affected: int = 0
) -> None:
    """
    Log database query

    Args:
        query: SQL query (sanitized)
        duration_ms: Query duration in milliseconds
        rows_affected: Number of rows affected
    """
    logger = StructuredLogger("database")
    logger.debug(
        "Database query",
        query=query,
        duration_ms=duration_ms,
        rows_affected=rows_affected
    )


def log_aws_api_call(
    service: str,
    operation: str,
    duration_ms: float,
    success: bool,
    error: Optional[str] = None
) -> None:
    """
    Log AWS API call

    Args:
        service: AWS service name
        operation: API operation name
        duration_ms: Call duration in milliseconds
        success: Whether call succeeded
        error: Optional error message
    """
    logger = StructuredLogger("aws")
    logger.info(
        "AWS API call",
        service=service,
        operation=operation,
        duration_ms=duration_ms,
        success=success,
        error=error
    )


def log_optimization_job(
    job_id: str,
    cluster_id: str,
    status: str,
    duration_ms: Optional[float] = None,
    recommendations: Optional[int] = None
) -> None:
    """
    Log optimization job

    Args:
        job_id: Job UUID
        cluster_id: Cluster UUID
        status: Job status
        duration_ms: Job duration in milliseconds
        recommendations: Number of recommendations generated
    """
    logger = StructuredLogger("optimization")
    logger.info(
        "Optimization job",
        job_id=job_id,
        cluster_id=cluster_id,
        status=status,
        duration_ms=duration_ms,
        recommendations=recommendations
    )


def log_audit_event(
    event: str,
    actor_id: str,
    actor_name: str,
    resource: str,
    resource_type: str,
    outcome: str,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log audit event

    Args:
        event: Event type
        actor_id: Actor UUID
        actor_name: Actor name or email
        resource: Resource identifier
        resource_type: Resource type
        outcome: Event outcome (SUCCESS or FAILURE)
        details: Optional additional details
    """
    logger = StructuredLogger("audit")
    logger.info(
        "Audit event",
        event=event,
        actor_id=actor_id,
        actor_name=actor_name,
        resource=resource,
        resource_type=resource_type,
        outcome=outcome,
        **details if details else {}
    )


# Initialize logging on module import
setup_logging()
