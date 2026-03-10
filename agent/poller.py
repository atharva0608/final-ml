import logging
import os
import time
import requests
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class SpotPoller:
    """
    Polls AWS Instance Metadata Service for Spot Termination Warnings (2-minute warning).
    When a termination notice is detected, it:
    1. Notifies the backend (POST /api/v1/worker/spot-interruption)
    2. Triggers the actuator's cordon/drain safeguards
    """
    IMDS_URL = "http://169.254.169.254/latest/meta-data/spot/instance-action"
    IMDS_INSTANCE_ID_URL = "http://169.254.169.254/latest/meta-data/instance-id"
    IMDS_REBALANCE_URL = "http://169.254.169.254/latest/meta-data/events/recommendations/rebalance"

    def __init__(self, actuator, interval=5, backend_url=None, api_key=None,
                 cluster_id=None, node_name=None):
        """
        Args:
            actuator: ActionActuator instance to trigger drain/cordon
            interval: Check interval in seconds (default: 5)
            backend_url: Backend API URL for spot-interruption notification
            api_key: API key for backend auth
            cluster_id: Cluster ID for this agent
            node_name: Name of this node
        """
        self.actuator = actuator
        self.interval = interval
        self.running = False
        self.termination_detected = False
        self.rebalance_notified = False
        self.backend_url = backend_url or os.getenv('BACKEND_URL', '')
        self.api_key = api_key or os.getenv('API_KEY', '')
        self.cluster_id = cluster_id or os.getenv('CLUSTER_ID', '')
        self.node_name = node_name or os.getenv('NODE_NAME', '')
        self._instance_id = None

    def _get_instance_id(self):
        """Fetch instance ID from IMDS (cached after first call)."""
        if self._instance_id:
            return self._instance_id
        try:
            resp = requests.get(self.IMDS_INSTANCE_ID_URL, timeout=1)
            if resp.status_code == 200:
                self._instance_id = resp.text.strip()
                return self._instance_id
        except Exception:
            pass
        return ""

    def check_termination_notice(self):
        """
        Check IMDS for termination notice.
        Returns:
            Dict with action info if terminating, None otherwise.
        """
        try:
            # Short timeout is critical to not block the thread
            response = requests.get(self.IMDS_URL, timeout=1)
            
            if response.status_code == 200:
                data = response.json()
                logger.warning(f"🚨 SPOT TERMINATION DETECTED: {data}")
                return data
            elif response.status_code == 404:
                # Normal case: No termination scheduled
                return None
            else:
                logger.warning(f"Unexpected IMDS status: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException:
            # IMDS might not be reachable (e.g. not on AWS, or network issue)
            pass
        return None

    def check_rebalance_recommendation(self):
        """Check IMDS for EC2 rebalance recommendation (precursor to termination)."""
        try:
            response = requests.get(self.IMDS_REBALANCE_URL, timeout=1)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"[SpotPoller] Rebalance recommendation received: {data}")
                return data
            elif response.status_code == 404:
                return None
        except requests.exceptions.RequestException:
            pass
        return None

    def run(self):
        """
        Main polling loop.
        """
        self.running = True
        logger.info(f"SpotPoller started (Interval: {self.interval}s)")

        while self.running:
            if not self.termination_detected:
                notice = self.check_termination_notice()
                if notice:
                    self.termination_detected = True
                    self._notify_backend(notice)
                    self.handle_termination(notice)

            if not self.rebalance_notified and not self.termination_detected:
                rec = self.check_rebalance_recommendation()
                if rec:
                    self.rebalance_notified = True
                    self._notify_rebalance(rec)

            time.sleep(self.interval)
        
        logger.info("SpotPoller stopped")

    def _notify_backend(self, notice):
        """
        POST spot interruption alert to backend so it can create an
        emergency RebalancingAction. This is faster than SQS.
        """
        if not self.backend_url:
            logger.warning("[SpotPoller] No BACKEND_URL configured — skipping notification")
            return

        instance_id = self._get_instance_id()
        payload = {
            "cluster_id": self.cluster_id,
            "node_name": self.node_name,
            "instance_id": instance_id,
            "action": notice.get("action", "terminate"),
            "termination_time": notice.get("time"),
        }

        try:
            url = f"{self.backend_url.rstrip('/')}/api/v1/worker/spot-interruption"
            headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code == 200:
                logger.info(f"[SpotPoller] Backend notified of spot interruption: {resp.json()}")
            else:
                logger.warning(f"[SpotPoller] Backend notification failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"[SpotPoller] Failed to notify backend: {e}")

    def _notify_rebalance(self, notice):
        """POST rebalance recommendation to backend so it can proactively migrate this node."""
        if not self.backend_url:
            return
        instance_id = self._get_instance_id()
        payload = {
            "cluster_id": self.cluster_id,
            "node_name": self.node_name,
            "instance_id": instance_id,
            "action": "rebalance",
            "termination_time": notice.get("noticeTime"),
        }
        try:
            url = f"{self.backend_url.rstrip('/')}/api/v1/worker/rebalance-recommendation"
            headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
            resp = requests.post(url, json=payload, headers=headers, timeout=5)
            logger.info(f"[SpotPoller] Rebalance recommendation sent to backend ({resp.status_code})")
        except Exception as e:
            logger.error(f"[SpotPoller] Failed to notify rebalance: {e}")

    def handle_termination(self, notice):
        """
        Execute safety procedures when termination is detected.
        """
        action_time = notice.get('time', 'UNKNOWN')
        action_id = notice.get('action', 'terminate')
        
        logger.critical(f"⚠️ IMMEDIATE ACTION REQUIRED: Spot Instance terminating at {action_time} (Action: {action_id})")
        
        # Trigger Actuator Safeguards
        try:
            if hasattr(self.actuator, 'handle_spot_interruption'):
                self.actuator.handle_spot_interruption(notice)
            else:
                logger.warning("Actuator missing 'handle_spot_interruption' method. Implementing basic fallback.")
        except Exception as e:
            logger.error(f"Failed to execute termination safeguards: {e}")

    def stop(self):
        self.running = False

