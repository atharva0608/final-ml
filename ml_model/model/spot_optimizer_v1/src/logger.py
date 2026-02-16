"""
Centralized logging configuration for Spot Optimizer project.

Usage:
    from src.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Starting preprocessing")
    logger.debug("Detailed calculation info")
    logger.warning("High memory usage detected")
    logger.error("Failed to load data")
"""
import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "spot_optimizer", level: int = logging.INFO, log_file: str = None, console: bool = True
) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name (usually __name__ from calling module)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
        console: Whether to also log to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Format: timestamp - level - module - message
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get or create a logger with default configuration.

    Args:
        name: Logger name (use __name__ from calling module)
        level: Logging level (default: INFO)

    Returns:
        Configured logger
    """
    return setup_logger(name, level=level, console=True)


# SageMaker-specific logging setup
def setup_sagemaker_logger(name: str = "sagemaker_job", level: int = logging.INFO) -> logging.Logger:
    """
    Configure logger for SageMaker jobs.
    Logs to both console (CloudWatch) and file (preserved in output).

    Args:
        name: Logger name
        level: Logging level

    Returns:
        Configured logger for SageMaker environment
    """
    # Check if running in SageMaker
    sagemaker_output_dir = Path("/opt/ml/output")

    if sagemaker_output_dir.exists():
        # SageMaker environment - log to file
        log_file = sagemaker_output_dir / "job.log"
        return setup_logger(name, level=level, log_file=str(log_file), console=True)
    else:
        # Local environment
        return setup_logger(name, level=level, console=True)
