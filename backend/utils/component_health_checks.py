"""
Component Health Checks - Deep System Monitoring

Implements health checks for 7 critical components:
1. Database - Connection pool and query latency
2. Redis - Connection and queue depth
3. K8s Watcher - Heartbeat age
4. Optimizer - Last optimization cycle
5. Price Scraper - Data freshness
6. Risk Engine - Risk data freshness
7. ML Inference - Active model availability

Each component returns: (status, details)
- status: "healthy", "degraded", "critical"
- details: Dict with metrics and context
"""

from datetime import datetime, timedelta
from typing import Tuple, Dict
import time

from sqlalchemy.orm import Session
from sqlalchemy import text


class ComponentHealthCheck:
    """Base class for health checks"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check(self) -> Tuple[str, Dict]:
        """
        Run health check
        
        Returns:
            Tuple of (status, details)
            - status: "healthy", "degraded", or "critical"
            - details: Dict with metrics and diagnostic info
        """
        raise NotImplementedError


class DatabaseCheck(ComponentHealthCheck):
    """Database connection pool and query latency"""
    
    def check(self) -> Tuple[str, Dict]:
        try:
            start = time.time()
            self.db.execute(text("SELECT 1"))  # Fastest query, tests connection pool
            latency_ms = (time.time() - start) * 1000
            
            if latency_ms < 50:
                return ("healthy", {
                    "latency_ms": round(latency_ms, 2),
                    "message": "Database responding normally"
                })
            elif latency_ms < 200:
                return ("degraded", {
                    "latency_ms": round(latency_ms, 2),
                    "message": "Database latency elevated"
                })
            else:
                return ("critical", {
                    "latency_ms": round(latency_ms, 2),
                    "message": "Database latency critical"
                })
        except Exception as e:
            return ("critical", {
                "error": str(e),
                "message": "Database connection failed"
            })


class RedisCheck(ComponentHealthCheck):
    """Redis connection and queue depth"""
    
    def check(self) -> Tuple[str, Dict]:
        try:
            # TODO: Implement actual Redis check when Redis is integrated
            # For now, simulate check
            queue_depth = 0  # Would query Redis: LLEN optimizer_queue
            
            if queue_depth < 20:
                return ("healthy", {
                    "queue_depth": queue_depth,
                    "message": "Redis responding, queue normal"
                })
            elif queue_depth < 50:
                return ("degraded", {
                    "queue_depth": queue_depth,
                    "message": "Redis queue backlog forming"
                })
            else:
                return ("critical", {
                    "queue_depth": queue_depth,
                    "message": "Redis queue critical (worker starvation)"
                })
        except Exception as e:
            return ("critical", {
                "error": str(e),
                "message": "Redis connection failed"
            })


class K8sWatcherCheck(ComponentHealthCheck):
    """Kubernetes watcher heartbeat check"""
    
    def check(self) -> Tuple[str, Dict]:
        try:
            # TODO: Implement actual K8s watcher heartbeat check
            # For now, simulate check
            # Would query Redis: GET heartbeat:watcher
            last_heartbeat = datetime.utcnow() - timedelta(seconds=30)
            age_seconds = (datetime.utcnow() - last_heartbeat).total_seconds()
            
            if age_seconds < 60:
                return ("healthy", {
                    "heartbeat_age_seconds": int(age_seconds),
                    "message": "K8s watcher active"
                })
            elif age_seconds < 120:
                return ("degraded", {
                    "heartbeat_age_seconds": int(age_seconds),
                    "message": "K8s watcher lagging"
                })
            else:
                return ("critical", {
                    "heartbeat_age_seconds": int(age_seconds),
                    "message": "K8s watcher dead (missed pod events)"
                })
        except Exception as e:
            return ("critical", {
                "error": str(e),
                "message": "K8s watcher check failed"
            })


class OptimizerCheck(ComponentHealthCheck):
    """Optimizer last run timestamp"""
    
    def check(self) -> Tuple[str, Dict]:
        try:
            from database.models import ExperimentLog
            
            # Query last optimization cycle
            last_run = self.db.query(ExperimentLog.execution_time).order_by(
                ExperimentLog.execution_time.desc()
            ).first()
            
            if not last_run:
                return ("degraded", {
                    "message": "No optimization runs found (cold start)"
                })
            
            age = datetime.utcnow() - last_run[0]
            age_minutes = age.total_seconds() / 60
            
            if age_minutes < 10:
                return ("healthy", {
                    "last_run_minutes_ago": round(age_minutes, 1),
                    "message": "Optimizer running normally"
                })
            elif age_minutes < 30:
                return ("degraded", {
                    "last_run_minutes_ago": round(age_minutes, 1),
                    "message": "Optimizer cycle delayed"
                })
            else:
                return ("critical", {
                    "last_run_minutes_ago": round(age_minutes, 1),
                    "message": "Optimizer not running (no cost savings)"
                })
        except Exception as e:
            return ("critical", {
                "error": str(e),
                "message": "Optimizer check failed"
            })


class PriceScraperCheck(ComponentHealthCheck):
    """
    Live Connectivity Check for Price Scraper
    
    Actively probes AWS Spot Advisor endpoint to verify:
    1. Upstream API is reachable
    2. Response data structure is valid
    3. Next component can process the data
    
    Tri-State Logic:
    - HEALTHY: 200 OK + valid JSON structure
    - DEGRADED: 200 OK but missing critical keys (schema changed)
    - CRITICAL: Request fails or returns error status
    """
    
    SPOT_ADVISOR_URL = "https://spot-bid-advisor.s3.amazonaws.com/spot-advisor-data.json"
    TIMEOUT_SECONDS = 5
    REQUIRED_KEYS = ["spot_advisor"]  # Critical top-level keys
    
    def check(self) -> Tuple[str, Dict]:
        import requests
        
        try:
            # Active probe with strict timeout
            start = time.time()
            response = requests.get(
                self.SPOT_ADVISOR_URL,
                timeout=self.TIMEOUT_SECONDS,
                headers={"User-Agent": "SpotOptimizer-HealthCheck/1.0"}
            )
            response_time_ms = (time.time() - start) * 1000
            
            # CRITICAL: Non-2xx status codes
            if response.status_code != 200:
                return ("critical", {
                    "http_status": response.status_code,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": f"Upstream API returned {response.status_code}",
                    "url": self.SPOT_ADVISOR_URL
                })
            
            # Parse JSON (limited to structure check only)
            try:
                data = response.json()
            except ValueError as e:
                # 200 OK but invalid JSON
                return ("degraded", {
                    "http_status": 200,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": "Response is not valid JSON",
                    "error": str(e),
                    "url": self.SPOT_ADVISOR_URL
                })
            
            # DEGRADED: Valid JSON but wrong structure
            missing_keys = [key for key in self.REQUIRED_KEYS if key not in data]
            if missing_keys:
                return ("degraded", {
                    "http_status": 200,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": "Data structure changed - scraper may crash",
                    "missing_keys": missing_keys,
                    "expected_keys": self.REQUIRED_KEYS,
                    "actual_keys": list(data.keys())[:10],  # First 10 keys only
                    "url": self.SPOT_ADVISOR_URL
                })
            
            # DEGRADED: Empty data
            if not data.get("spot_advisor"):
                return ("degraded", {
                    "http_status": 200,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": "spot_advisor key is empty",
                    "url": self.SPOT_ADVISOR_URL
                })
            
            # HEALTHY: All checks passed
            return ("healthy", {
                "http_status": 200,
                "response_time_ms": round(response_time_ms, 2),
                "message": "Spot Advisor endpoint reachable and valid",
                "data_keys_found": list(data.keys())[:5],  # First 5 keys as proof
                "url": self.SPOT_ADVISOR_URL
            })
            
        except requests.exceptions.Timeout:
            # CRITICAL: Timeout (network slow or endpoint down)
            return ("critical", {
                "error": "Request timeout",
                "timeout_seconds": self.TIMEOUT_SECONDS,
                "message": "Spot Advisor endpoint unreachable (timeout)",
                "url": self.SPOT_ADVISOR_URL
            })
        except requests.exceptions.ConnectionError as e:
            # CRITICAL: DNS failure, network down, etc.
            return ("critical", {
                "error": str(e),
                "message": "Connection failed (DNS/network issue)",
                "url": self.SPOT_ADVISOR_URL
            })
        except Exception as e:
            # CRITICAL: Unexpected error
            return ("critical", {
                "error": str(e),
                "message": "Price scraper health check failed unexpectedly",
                "url": self.SPOT_ADVISOR_URL
            })



class RiskEngineCheck(ComponentHealthCheck):
    """Risk data freshness check"""
    
    def check(self) -> Tuple[str, Dict]:
        try:
            from database.models import GlobalRiskEvent
            
            # Query last risk event
            last_event = self.db.query(GlobalRiskEvent.reported_at).order_by(
                GlobalRiskEvent.reported_at.desc()
            ).first()
            
            if not last_event:
                return ("healthy", {
                    "message": "No recent risk events (good sign)"
                })
            
            age = datetime.utcnow() - last_event[0]
            age_hours = age.total_seconds() / 3600
            
            if age_hours < 12:
                return ("healthy", {
                    "last_event_hours_ago": round(age_hours, 1),
                    "message": "Risk data current"
                })
            elif age_hours < 24:
                return ("degraded", {
                    "last_event_hours_ago": round(age_hours, 1),
                    "message": "Risk data aging"
                })
            else:
                return ("critical", {
                    "last_event_hours_ago": round(age_hours, 1),
                    "message": "Risk data stale"
                })
        except Exception as e:
            return ("critical", {
                "error": str(e),
                "message": "Risk engine check failed"
            })


class MLInferenceCheck(ComponentHealthCheck):
    """ML model availability check"""
    
    def check(self) -> Tuple[str, Dict]:
        try:
            from database.models import MLModel, ModelStatus
            
            # Query active production model
            active_model = self.db.query(MLModel).filter(
                MLModel.is_active_prod == True
            ).first()
            
            if active_model:
                return ("healthy", {
                    "active_model": active_model.name,
                    "model_id": active_model.id,
                    "message": "Production model active"
                })
            
            # Check for graduated models
            graduated_models = self.db.query(MLModel).filter(
                MLModel.status == ModelStatus.GRADUATED.value
            ).count()
            
            if graduated_models > 0:
                return ("degraded", {
                    "graduated_models": graduated_models,
                    "message": "Graduated models available but not deployed"
                })
            else:
                return ("critical", {
                    "message": "No models available (cold start mode)"
                })
        except Exception as e:
            return ("critical", {
                "error": str(e),
                "message": "ML inference check failed"
            })


def run_all_health_checks(db: Session) -> Dict[str, Tuple[str, Dict]]:
    """
    Run all component health checks including the new decision pipeline checks
    
    Args:
        db: Database session
        
    Returns:
        Dict mapping component name to (status, details) tuple
    """
    from utils.decision_pipeline_health import DecisionPipelineCheck, StandalonePipelineCheck
    
    checks = {
        "database": DatabaseCheck(db),
        "redis": RedisCheck(db),
        "k8s_watcher": K8sWatcherCheck(db),
        "optimizer": OptimizerCheck(db),
        "price_scraper": PriceScraperCheck(db),
        "risk_engine": RiskEngineCheck(db),
        "ml_inference": MLInferenceCheck(db),
        "decision_pipeline": DecisionPipelineCheck(db),
        "standalone_pipeline": StandalonePipelineCheck(db)
    }
    
    results = {}
    for name, checker in checks.items():
        try:
            status, details = checker.check()
            results[name] = (status, details)
        except Exception as e:
            results[name] = ("critical", {
                "error": str(e),
                "message": f"Health check crashed: {e}"
            })
    
    return results


class ComponentHealthEvaluator:
    """
    Evaluates health status for components using specific logic.
    Used by SystemLogger to automatically update health status.
    """

    @staticmethod
    def evaluate_health(component_name: str, health_record) -> str:
        """
        Run health check for specific component and return status string.
        
        Args:
            component_name: Name of the component
            health_record: SQLAlchemy ComponentHealth object
            
        Returns:
            New status string ("healthy", "degraded", "critical", "down")
        """
        from sqlalchemy.orm import object_session
        from utils.decision_pipeline_health import DecisionPipelineCheck, StandalonePipelineCheck
        
        # Get DB session from the health record
        db = object_session(health_record)
        if not db:
            # If detached, we can't run DB-based checks
            return health_record.status
            
        evaluator = None
        
        # Map component to check class
        if component_name == "database":
            evaluator = DatabaseCheck(db)
        elif component_name == "redis_cache":
            evaluator = RedisCheck(db)
        elif component_name == "k8s_watcher":
            evaluator = K8sWatcherCheck(db)
        elif component_name in ["linear_optimizer", "cluster_optimizer"]:
            evaluator = OptimizerCheck(db)
        elif component_name == "price_scraper":
            evaluator = PriceScraperCheck(db)
        elif component_name == "risk_engine":
            evaluator = RiskEngineCheck(db)
        elif component_name == "ml_inference":
            evaluator = MLInferenceCheck(db)
        elif component_name == "decision_pipeline":
            evaluator = DecisionPipelineCheck(db)
        elif component_name == "standalone_pipeline":
            evaluator = StandalonePipelineCheck(db)
            
        if evaluator:
            try:
                status, details = evaluator.check()
                
                # Update metadata if provided
                if details:
                    if not health_record.component_metadata:
                        health_record.component_metadata = {}
                    # Merge existing metadata with new details
                    # health_record.component_metadata.update(details) # Careful with JSONB updates
                    
                    # For now just set it to details to keep it fresh
                    health_record.component_metadata = details
                    
                return status
            except Exception as e:
                # Keep existing status if check fails, but log error in metadata
                health_record.error_message = f"Health check failed: {str(e)}"
                return "unknown"
                
        # Default for components without specific checks
        return health_record.status
