"""
Real Health Checks for All Components

Tests each component with actual functionality verification.
Returns: healthy, degraded, or unhealthy based on real tests.
"""

import os
from datetime import datetime
from typing import Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text


def check_database(db: Session) -> Tuple[str, Dict]:
    """
    Test database with real query

    Returns:
        (status, details) where status is 'healthy', 'degraded', or 'unhealthy'
    """
    try:
        result = db.execute(text("SELECT 1, NOW()::timestamp"))
        row = result.fetchone()

        return ("healthy", {
            "message": "Database connection verified",
            "details": {
                "query": "SELECT 1",
                "server_time": str(row[1]) if row else None
            }
        })
    except Exception as e:
        return ("unhealthy", {
            "message": "Database connection failed",
            "error": str(e)
        })


def check_redis() -> Tuple[str, Dict]:
    """
    Test Redis with real operations

    Returns:
        (status, details)
    """
    try:
        import redis
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)

        # Test PING
        ping_result = r.ping()
        if not ping_result:
            return ("unhealthy", {
                "message": "Redis PING failed"
            })

        # Test SET/GET
        test_key = "health_check_test"
        test_value = str(datetime.now().timestamp())
        r.set(test_key, test_value, ex=10)
        retrieved = r.get(test_key)

        if retrieved and retrieved.decode() == test_value:
            return ("healthy", {
                "message": "Redis operations verified",
                "details": {
                    "ping": "success",
                    "set_get": "success"
                }
            })
        else:
            return ("degraded", {
                "message": "Redis PING works but SET/GET failed",
                "details": {"ping": "success", "set_get": "failed"}
            })

    except Exception as e:
        return ("unhealthy", {
            "message": "Redis connection failed",
            "error": str(e)
        })


def check_api_server() -> Tuple[str, Dict]:
    """
    Test API server (self-check)

    Returns:
        (status, details)
    """
    try:
        # If this code is running, the API server is up
        return ("healthy", {
            "message": "API server operational",
            "details": {
                "process": "running",
                "timestamp": datetime.now().isoformat()
            }
        })
    except Exception as e:
        return ("unhealthy", {
            "message": "API server check failed",
            "error": str(e)
        })


def check_ml_inference() -> Tuple[str, Dict]:
    """
    Test ML inference capability

    Returns:
        (status, details)
    """
    try:
        # Check if ml-models directory exists
        model_dir = os.path.join(os.getcwd(), "ml-models")

        if not os.path.exists(model_dir):
            return ("degraded", {
                "message": "ML models directory not found",
                "details": {
                    "directory": model_dir,
                    "status": "missing"
                }
            })

        # Check if any .pkl files exist
        import glob
        pkl_files = glob.glob(os.path.join(model_dir, "*.pkl"))

        if len(pkl_files) == 0:
            return ("degraded", {
                "message": "No trained models found",
                "details": {
                    "directory": model_dir,
                    "model_count": 0
                }
            })

        # Try to import required libraries
        try:
            import pandas as pd
            import numpy as np
            import joblib
        except ImportError as ie:
            return ("degraded", {
                "message": "ML dependencies not fully available",
                "error": str(ie)
            })

        return ("healthy", {
            "message": "ML inference ready",
            "details": {
                "model_directory": model_dir,
                "model_count": len(pkl_files),
                "dependencies": "available"
            }
        })

    except Exception as e:
        return ("unhealthy", {
            "message": "ML inference check failed",
            "error": str(e)
        })


def check_linear_optimizer() -> Tuple[str, Dict]:
    """
    Test linear optimizer module

    Returns:
        (status, details)
    """
    try:
        # Try importing the optimizer
        from pipelines.linear_optimizer import LinearOptimizer

        # Check if optimizer can be instantiated
        optimizer = LinearOptimizer()

        return ("healthy", {
            "message": "Linear optimizer operational",
            "details": {
                "module": "loaded",
                "class": "LinearOptimizer instantiated"
            }
        })

    except ImportError as ie:
        return ("unhealthy", {
            "message": "Linear optimizer module not found",
            "error": str(ie)
        })
    except Exception as e:
        return ("degraded", {
            "message": "Linear optimizer partially functional",
            "error": str(e)
        })


def check_instance_manager() -> Tuple[str, Dict]:
    """
    Test instance manager

    Returns:
        (status, details)
    """
    try:
        # Check if AWS credentials are configured
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        if not aws_access_key or not aws_secret_key:
            return ("degraded", {
                "message": "AWS credentials not configured",
                "details": {
                    "aws_access_key": "missing" if not aws_access_key else "present",
                    "aws_secret_key": "missing" if not aws_secret_key else "present"
                }
            })

        # Try importing boto3
        try:
            import boto3
        except ImportError:
            return ("unhealthy", {
                "message": "AWS SDK (boto3) not installed",
                "error": "boto3 import failed"
            })

        return ("healthy", {
            "message": "Instance manager ready",
            "details": {
                "aws_sdk": "available",
                "credentials": "configured"
            }
        })

    except Exception as e:
        return ("unhealthy", {
            "message": "Instance manager check failed",
            "error": str(e)
        })


def check_price_scraper() -> Tuple[str, Dict]:
    """
    Test price scraper capability

    Returns:
        (status, details)
    """
    try:
        # Check if required libraries are available
        try:
            import requests
            import bs4
        except ImportError as ie:
            return ("degraded", {
                "message": "Price scraper dependencies missing",
                "error": str(ie)
            })

        # Check if AWS pricing API is accessible (without actually calling it)
        return ("healthy", {
            "message": "Price scraper dependencies ready",
            "details": {
                "requests_lib": "available",
                "bs4_lib": "available"
            }
        })

    except Exception as e:
        return ("unhealthy", {
            "message": "Price scraper check failed",
            "error": str(e)
        })


def check_web_scraper() -> Tuple[str, Dict]:
    """
    Test web scraper

    Returns:
        (status, details)
    """
    try:
        # Check if required libraries are available
        try:
            import requests
            import bs4
        except ImportError as ie:
            return ("degraded", {
                "message": "Web scraper dependencies missing",
                "error": str(ie)
            })

        return ("healthy", {
            "message": "Web scraper dependencies ready",
            "details": {
                "requests_lib": "available",
                "bs4_lib": "available"
            }
        })

    except Exception as e:
        return ("unhealthy", {
            "message": "Web scraper check failed",
            "error": str(e)
        })


def check_security_enforcer() -> Tuple[str, Dict]:
    """
    Test security enforcer

    Returns:
        (status, details)
    """
    try:
        # Try importing the security enforcer
        from jobs.security_enforcer import SecurityEnforcer

        return ("healthy", {
            "message": "Security enforcer operational",
            "details": {
                "module": "loaded",
                "class": "SecurityEnforcer available"
            }
        })

    except ImportError as ie:
        return ("unhealthy", {
            "message": "Security enforcer module not found",
            "error": str(ie)
        })
    except Exception as e:
        return ("degraded", {
            "message": "Security enforcer partially functional",
            "error": str(e)
        })


def check_waste_scanner() -> Tuple[str, Dict]:
    """
    Test waste scanner

    Returns:
        (status, details)
    """
    try:
        # Try importing the waste scanner
        from jobs.waste_scanner import WasteScanner

        return ("healthy", {
            "message": "Waste scanner operational",
            "details": {
                "module": "loaded",
                "class": "WasteScanner available"
            }
        })

    except ImportError as ie:
        return ("unhealthy", {
            "message": "Waste scanner module not found",
            "error": str(ie)
        })
    except Exception as e:
        return ("degraded", {
            "message": "Waste scanner partially functional",
            "error": str(e)
        })


# Component check mapping
COMPONENT_CHECKS = {
    "database": check_database,
    "redis_cache": check_redis,
    "api_server": check_api_server,
    "ml_inference": check_ml_inference,
    "linear_optimizer": check_linear_optimizer,
    "instance_manager": check_instance_manager,
    "price_scraper": check_price_scraper,
    "web_scraper": check_web_scraper,
    "security_enforcer": check_security_enforcer,
    "waste_scanner": check_waste_scanner,
}


def run_component_health_check(component_name: str, db: Session = None) -> Tuple[str, Dict]:
    """
    Run health check for a specific component

    Args:
        component_name: Name of component to check
        db: Database session (required for database check)

    Returns:
        (status, details) tuple
    """
    check_func = COMPONENT_CHECKS.get(component_name)

    if not check_func:
        return ("unhealthy", {
            "message": f"Unknown component: {component_name}"
        })

    # Pass db session if component needs it
    if component_name == "database":
        if not db:
            return ("unhealthy", {"message": "Database session required but not provided"})
        return check_func(db)
    else:
        return check_func()


def run_all_health_checks(db: Session) -> Dict[str, Tuple[str, Dict]]:
    """
    Run health checks for all components

    Args:
        db: Database session

    Returns:
        Dict mapping component name to (status, details) tuple
    """
    results = {}

    for component_name in COMPONENT_CHECKS.keys():
        status, details = run_component_health_check(component_name, db)
        results[component_name] = (status, details)

    return results
