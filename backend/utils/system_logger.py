"""
System Logger - Centralized Logging for All Components

Provides easy-to-use logging for all system components with
automatic health status tracking.

Usage:
    from utils.system_logger import SystemLogger, Component

    logger = SystemLogger(Component.WEB_SCRAPER)

    with logger.operation("Fetching spot advisor data"):
        # Your code here
        data = fetch_spot_advisor()
        logger.info("Fetched 100 spot pools")
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from contextlib import contextmanager
import time

from database.system_logs import SystemLog, ComponentHealth, ComponentType, LogLevel, ComponentStatus
from database.connection import get_db
from sqlalchemy.orm import Session


class Component:
    """Component type constants"""
    WEB_SCRAPER = ComponentType.WEB_SCRAPER.value
    PRICE_SCRAPER = ComponentType.PRICE_SCRAPER.value
    DATABASE = ComponentType.DATABASE.value
    LINEAR_OPTIMIZER = ComponentType.LINEAR_OPTIMIZER.value
    ML_INFERENCE = ComponentType.ML_INFERENCE.value
    INSTANCE_MANAGER = ComponentType.INSTANCE_MANAGER.value
    REDIS_CACHE = ComponentType.REDIS_CACHE.value
    API_SERVER = ComponentType.API_SERVER.value


class SystemLogger:
    """Centralized system logger with health tracking"""

    def __init__(self, component: str, db: Optional[Session] = None):
        """
        Initialize system logger

        Args:
            component: Component name (use Component constants)
            db: Optional database session (will create new if not provided)
        """
        self.component = component
        self.db = db
        self._should_close_db = False

        if not self.db:
            self.db = next(get_db())
            self._should_close_db = True

    def _ensure_health_record(self):
        """Ensure component health record exists"""
        health = self.db.query(ComponentHealth).filter(
            ComponentHealth.component == self.component
        ).first()

        if not health:
            health = ComponentHealth(
                component=self.component,
                status=ComponentStatus.UNKNOWN.value,
                success_count_24h=0,
                failure_count_24h=0
            )
            self.db.add(health)
            self.db.commit()

        return health

    def _log(self, level: str, message: str, details: Optional[Dict[str, Any]] = None,
             execution_time_ms: Optional[int] = None, success: Optional[str] = None):
        """
        Internal log method

        Args:
            level: Log level (debug, info, warning, error, critical)
            message: Log message
            details: Additional context as JSON
            execution_time_ms: Execution time in milliseconds
            success: "success" or "failure"
        """
        try:
            log = SystemLog(
                component=self.component,
                level=level,
                message=message,
                details=details or {},
                execution_time_ms=execution_time_ms,
                success=success,
                timestamp=datetime.utcnow()
            )
            self.db.add(log)
            self.db.commit()

            # Update health status
            self._update_health(success, execution_time_ms)

        except Exception as e:
            # If logging fails, print to console but don't crash
            print(f"[SystemLogger] Failed to log: {e}")
            if self.db:
                self.db.rollback()

    def _update_health(self, success: Optional[str], execution_time_ms: Optional[int]):
        """Update component health metrics"""
        try:
            health = self._ensure_health_record()

            health.last_check = datetime.utcnow()

            if success == "success":
                health.last_success = datetime.utcnow()
                health.success_count_24h += 1
                health.status = ComponentStatus.HEALTHY.value
                health.error_message = None

            elif success == "failure":
                health.last_failure = datetime.utcnow()
                health.failure_count_24h += 1

                # Determine status based on failure rate
                total = health.success_count_24h + health.failure_count_24h
                failure_rate = health.failure_count_24h / total if total > 0 else 0

                if failure_rate > 0.5:
                    health.status = ComponentStatus.DOWN.value
                elif failure_rate > 0.2:
                    health.status = ComponentStatus.DEGRADED.value

            # Update average execution time
            if execution_time_ms:
                if health.avg_execution_time_ms:
                    # Rolling average
                    health.avg_execution_time_ms = int(
                        (health.avg_execution_time_ms * 0.8) + (execution_time_ms * 0.2)
                    )
                else:
                    health.avg_execution_time_ms = execution_time_ms

            self.db.commit()

        except Exception as e:
            print(f"[SystemLogger] Failed to update health: {e}")
            if self.db:
                self.db.rollback()

    def debug(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log debug message"""
        self._log(LogLevel.DEBUG.value, message, details)

    def info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log info message"""
        self._log(LogLevel.INFO.value, message, details)

    def warning(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log warning message"""
        self._log(LogLevel.WARNING.value, message, details)

    def error(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log error message"""
        self._log(LogLevel.ERROR.value, message, details, success="failure")

        # Update health error message
        try:
            health = self._ensure_health_record()
            health.error_message = message
            self.db.commit()
        except Exception:
            pass

    def critical(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log critical message"""
        self._log(LogLevel.CRITICAL.value, message, details, success="failure")

        # Mark component as down
        try:
            health = self._ensure_health_record()
            health.status = ComponentStatus.DOWN.value
            health.error_message = message
            self.db.commit()
        except Exception:
            pass

    def success(self, message: str, execution_time_ms: Optional[int] = None,
                details: Optional[Dict[str, Any]] = None):
        """Log successful operation"""
        self._log(LogLevel.INFO.value, message, details, execution_time_ms, "success")

    def failure(self, message: str, execution_time_ms: Optional[int] = None,
                details: Optional[Dict[str, Any]] = None):
        """Log failed operation"""
        self._log(LogLevel.ERROR.value, message, details, execution_time_ms, "failure")

    @contextmanager
    def operation(self, operation_name: str):
        """
        Context manager for tracking operation execution

        Usage:
            with logger.operation("Fetch spot prices"):
                # Your code here
                data = fetch_data()

        Automatically logs success/failure and execution time
        """
        start_time = time.time()
        error = None

        try:
            self.info(f"Starting: {operation_name}")
            yield

        except Exception as e:
            error = e
            raise

        finally:
            execution_time_ms = int((time.time() - start_time) * 1000)

            if error:
                self.failure(
                    f"Failed: {operation_name}",
                    execution_time_ms=execution_time_ms,
                    details={"error": str(error), "error_type": type(error).__name__}
                )
            else:
                self.success(
                    f"Completed: {operation_name}",
                    execution_time_ms=execution_time_ms
                )

    def cleanup_old_logs(self, days: int = 7):
        """
        Clean up logs older than N days

        Args:
            days: Number of days to keep (default: 7)
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            deleted = self.db.query(SystemLog).filter(
                SystemLog.timestamp < cutoff
            ).delete()
            self.db.commit()
            self.info(f"Cleaned up {deleted} old logs (older than {days} days)")
        except Exception as e:
            self.error(f"Failed to cleanup old logs: {e}")

    def reset_24h_counters(self):
        """Reset 24-hour success/failure counters"""
        try:
            health = self._ensure_health_record()
            health.success_count_24h = 0
            health.failure_count_24h = 0
            self.db.commit()
        except Exception as e:
            print(f"[SystemLogger] Failed to reset counters: {e}")

    def __del__(self):
        """Cleanup database session if we created it"""
        if self._should_close_db and self.db:
            try:
                self.db.close()
            except Exception:
                pass


# Convenience function for quick logging
def log_component_event(component: str, level: str, message: str,
                        details: Optional[Dict[str, Any]] = None,
                        success: Optional[str] = None):
    """
    Quick logging without creating a logger instance

    Args:
        component: Component name
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        details: Additional context
        success: "success" or "failure"
    """
    logger = SystemLogger(component)
    logger._log(level, message, details, success=success)
