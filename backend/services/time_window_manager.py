"""
Time-Aware Optimization Windows
===============================
Manages optimization windows (business hours vs off-hours) to control
aggressiveness and reduce operational risk.
"""

import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class TimeWindowManager:
    """
    Decision layer for timing-based policy overrides.
    Example: 
    - Business Peak (09:00 - 18:00): Conservative (high savings threshold, low batch size)
    - Off-Peak (00:00 - 06:00): Aggressive (low savings threshold, high batch size)
    - Maintenance Window: Freeze all optimizations
    """

    def __init__(self, cluster_id: str, timezone: str = "UTC"):
        self.cluster_id = cluster_id
        self.tz = pytz.timezone(timezone)

    def get_current_window_mode(self) -> str:
        """
        Returns 'aggressive', 'conservative', or 'freeze'.
        """
        now = datetime.now(self.tz)
        hour = now.hour
        weekday = now.weekday() # 0 = Monday, 6 = Sunday

        # 1. Maintenance Window (Manual Override via Redis)
        # This allows operators to freeze optimizations globally or per cluster.
        # if self.redis.get(f"spot:freeze:{self.cluster_id}"): return "freeze"

        # 2. Weekend Aggressiveness (Safe for most dev/stg workloads)
        if weekday >= 5: # Saturday/Sunday
            return "aggressive"

        # 3. Business Hours (Peak Traffic)
        if 9 <= hour < 18:
            return "conservative"

        # 4. Nightly Aggressiveness (Batch window)
        if 0 <= hour < 6:
            return "aggressive"

        # 5. Default
        return "normal"

    def apply_policy_overrides(self, current_config: dict) -> dict:
        """
        Adjusts optimization parameters based on the current window.
        """
        mode = self.get_current_window_mode()
        
        if mode == "conservative":
            current_config["max_batch_size"] = 1
            current_config["min_savings_threshold"] = 25.0 # Higher bar for disruption
            current_config["pdb_respect_strict"] = True
        elif mode == "aggressive":
            current_config["max_batch_size"] = 5
            current_config["min_savings_threshold"] = 5.0  # Move for even small gains
            current_config["pdb_respect_strict"] = False # Allow closer to PDB limits
        elif mode == "freeze":
            current_config["max_batch_size"] = 0
            
        return current_config
