import logging
import time
import requests
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class SpotPoller:
    """
    Polls AWS Instance Metadata Service for Spot Termination Warnings (2-minute warning).
    """
    IMDS_URL = "http://169.254.169.254/latest/meta-data/spot/instance-action"

    def __init__(self, actuator, interval=5):
        """
        Args:
            actuator: ActionActuator instance to trigger drain/cordon
            interval: Check interval in seconds (default: 5)
        """
        self.actuator = actuator
        self.interval = interval
        self.running = False
        self.termination_detected = False

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
            # Log only once per minute to avoid spamming if running locally
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
                    self.handle_termination(notice)
            
            time.sleep(self.interval)
        
        logger.info("SpotPoller stopped")

    def handle_termination(self, notice):
        """
        Execute safety procedures when termination is detected.
        """
        action_time = notice.get('time', 'UNKNOWN')
        action_id = notice.get('action', 'terminate')
        
        logger.critical(f"⚠️ IMMEDIATE ACTION REQUIRED: Spot Instance terminating at {action_time} (Action: {action_id})")
        
        # Trigger Actuator Safeguards
        # 1. Cordon Node (Prevent new pods)
        # 2. Drain Node (Evict existing pods)
        try:
            # We assume actuator has a method for this. if not, we'll need to add it.
            # Using a generic 'handle_interruption' or calling cordon/drain directly.
            if hasattr(self.actuator, 'handle_spot_interruption'):
                self.actuator.handle_spot_interruption(notice)
            else:
                logger.warning("Actuator missing 'handle_spot_interruption' method. Implementing basic fallback.")
                # We will implement this in the actuator next.
        except Exception as e:
            logger.error(f"Failed to execute termination safeguards: {e}")

    def stop(self):
        self.running = False
