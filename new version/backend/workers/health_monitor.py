"""
Health Monitor Worker - State Transition Logging

Runs health checks every 30 seconds and tracks state transitions.

When a component transitions from healthy to degraded/critical:
- Automatically fetches last 15 logs from SystemLog table
- Creates alert with diagnostic context
- Reduces noise by only alerting on NEW issues

This provides auto-diagnostic context at the moment of failure.
"""

import time
from datetime import datetime
from typing import Dict, Tuple
import logging

from database.connection import SessionLocal
from database.models import SystemLog
from utils.component_health_checks import run_all_health_checks

logger = logging.getLogger("health_monitor")


class HealthMonitor:
    """Monitors component health and tracks state transitions"""
    
    def __init__(self):
        self.previous_states: Dict[str, str] = {}
        self.running = False
    
    def monitor_loop(self):
        """
        Main monitoring loop - runs continuously every 30 seconds
        
        Tracks state transitions and auto-captures diagnostic context
        when components degrade.
        """
        self.running = True
        logger.info("Health monitor started")
        
        while self.running:
            try:
                db = SessionLocal()
                
                # Run all health checks
                results = run_all_health_checks(db)
                
                # Check for state transitions
                for component_name, (current_status, details) in results.items():
                    previous_status = self.previous_states.get(component_name, "healthy")
                    
                    # Detect transition from healthy to unhealthy
                    if previous_status == "healthy" and current_status != "healthy":
                        self._handle_degradation(db, component_name, current_status, details)
                    
                    # Detect recovery
                    elif previous_status != "healthy" and current_status == "healthy":
                        logger.info(
                            f"✅ Component recovered: {component_name} "
                            f"({previous_status} → {current_status})"
                        )
                    
                    # Update state
                    self.previous_states[component_name] = current_status
                
                db.close()
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
            
            # Wait 30 seconds
            time.sleep(30)
    
    def _handle_degradation(
        self, 
        db, 
        component_name: str, 
        new_status: str, 
        details: Dict
    ):
        """
        Handle component degradation
        
        Auto-captures last 15 logs for diagnostic context
        """
        logger.warning(
            f"⚠️ Component degraded: {component_name} → {new_status}"
        )
        
        # Fetch last 15 logs for this component
        try:
            recent_logs = db.query(SystemLog).filter(
                SystemLog.component == component_name
            ).order_by(
                SystemLog.timestamp.desc()
            ).limit(15).all()
            
            log_summary = [
                f"{log.timestamp.isoformat()} [{log.log_level}] {log.message}"
                for log in recent_logs
            ]
            
            # Create alert (in production, would send to alerting system)
            alert = {
                "component": component_name,
                "status": new_status,
                "details": details,
                "timestamp": datetime.utcnow().isoformat(),
                "diagnostic_logs": log_summary
            }
            
            logger.error(
                f"ALERT: {component_name} degradation\n"
                f"Status: {new_status}\n"
                f"Details: {details}\n"
                f"Recent logs: {len(log_summary)} entries"
            )
            
            # TODO: Send to alerting system (PagerDuty, Slack, etc.)
            
        except Exception as e:
            logger.error(f"Failed to fetch diagnostic logs: {e}")
    
    def stop(self):
        """Stop the monitoring loop"""
        self.running = False
        logger.info("Health monitor stopped")


def start_health_monitor_background():
    """
    Start health monitor in background thread
    
    Called from main.py on startup
    """
    import threading
    
    monitor = HealthMonitor()
    thread = threading.Thread(target=monitor.monitor_loop, daemon=True)
    thread.start()
    
    logger.info("Health monitor background thread started")
    return monitor
