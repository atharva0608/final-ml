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
from .optimization import trigger_manual_optimization, optimize_cluster
from .hibernation_worker import (
    hibernation_scheduler_loop,
    manual_sleep_cluster,
    manual_wake_cluster
)
from .report_worker import (
    generate_weekly_report,
    generate_monthly_report,
    export_savings_to_csv
)
from .event_processor import (
    process_event,
    replay_event,
    cleanup_old_events
)

__all__ = [
    # Discovery worker
    "discovery_worker_loop",
    "stream_discovery_status",

    # Optimization worker
    "trigger_manual_optimization",
    "optimize_cluster",

    # Hibernation worker
    "hibernation_scheduler_loop",
    "manual_sleep_cluster",
    "manual_wake_cluster",

    # Report worker
    "generate_weekly_report",
    "generate_monthly_report",
    "export_savings_to_csv",

    # Event processor
    "process_event",
    "replay_event",
    "cleanup_old_events",
]
