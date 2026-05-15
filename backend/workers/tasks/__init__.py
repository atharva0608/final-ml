"""
Celery Worker Tasks - Phase 5 Implementation

This package contains all background worker tasks for the Spot Optimizer platform.

Workers:
- discovery: AWS account and cluster discovery (every 5 min)
- optimization: Optimization job processing
- events: Real-time event processing (Hive Mind)
- hibernation: Sleep/wake schedule checking (every 1 min)
- reports: Weekly report generation
"""

from .discovery import discovery_worker_loop, stream_discovery_status
# P4: optimization.py moved to temp-bin/DEPRECATED_optimization.py — not scheduled in beat
from .hibernation_worker import (
    execute_hibernation_scheduler,
    execute_hibernation,
    execute_wake,
    execute_prewarm
)
# P4: report_worker.py moved to temp-bin/DEPRECATED_report_worker.py — not scheduled in beat
# P4: event_processor.py moved to temp-bin/DEPRECATED_event_processor.py — not scheduled in beat

__all__ = [
    # Discovery worker
    "discovery_worker_loop",
    "stream_discovery_status",

    # Hibernation worker
    "execute_hibernation_scheduler",
    "execute_hibernation",
    "execute_wake",
    "execute_prewarm",

]
