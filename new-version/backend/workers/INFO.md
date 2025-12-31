# Workers - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains Celery background workers for asynchronous task processing including AWS discovery, optimization, hibernation scheduling, and report generation.

---

## Component Table

| File Name | Worker ID | Schedule | Purpose | Dependencies | Status |
|-----------|-----------|----------|---------|--------------|--------|
| discovery_worker.py | WORK-DISC-01 | Every 5 minutes | Discover AWS resources (EC2, EKS) | boto3, models/cluster.py, models/instance.py | Pending |
| optimizer_worker.py | WORK-OPT-01 | Manual trigger | Run optimization pipeline | modules/spot_optimizer.py, core/decision_engine.py | Pending |
| hibernation_worker.py | WORK-HIB-01 | Every 1 minute | Check hibernation schedules and execute | models/hibernation_schedule.py, scripts/aws/update_asg.py | Pending |
| report_worker.py | WORK-RPT-01 | Weekly (cron) | Generate and email weekly reports | services/metrics_service.py, SendGrid/SES | Pending |
| event_processor.py | WORK-EVT-01 | High priority queue | Process cluster events (Spot interruptions, OOMKilled) | modules/risk_tracker.py, Redis pub/sub | Pending |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Workers Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for background workers
**Impact**: Created backend/workers/ directory for Celery tasks
**Files Modified**:
- Created backend/workers/
- Created backend/workers/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- `backend/services/` - Business logic
- `backend/modules/` - Intelligence modules
- `backend/models/` - Database models
- `backend/core/` - Core components
- `scripts/aws/` - AWS automation scripts

### External Dependencies
- Celery (task queue)
- Redis (message broker)
- boto3 (AWS SDK)
- SQLAlchemy (database)

---

## Worker Configurations

### discovery_worker.py (WORK-DISC-01):
- **Schedule**: Every 5 minutes (Celery Beat)
- **Purpose**: Discover new EC2 instances and EKS clusters
- **Process**:
  1. Query active AWS accounts from database
  2. Assume IAM role for each account
  3. Call `ec2.describe_instances()` and `eks.list_clusters()`
  4. Calculate diff with previous state
  5. UPSERT instances table
  6. Fetch CloudWatch metrics
  7. Stream progress via WebSocket
- **Concurrency**: 1 worker (to avoid duplicate scans)

### optimizer_worker.py (WORK-OPT-01):
- **Schedule**: Manual trigger via POST /clusters/{id}/optimize
- **Purpose**: Execute optimization pipeline
- **Process**:
  1. Read cluster policies from database
  2. Call MOD-SPOT-01.detect_opportunities()
  3. Call MOD-AI-01.predict_interruption_risk()
  4. Pass to CORE-DECIDE for conflict resolution
  5. Execute action plan via CORE-EXEC
  6. Update optimization_job status
  7. Notify user via WebSocket
- **Concurrency**: 5 workers (parallel optimizations)

### hibernation_worker.py (WORK-HIB-01):
- **Schedule**: Every 1 minute (Celery Beat)
- **Purpose**: Enforce hibernation schedules
- **Process**:
  1. Query hibernation schedules from database
  2. Convert timezone to UTC
  3. Check current time against schedule matrix (168 elements)
  4. Trigger sleep/wake via scripts/aws/update_asg.py
  5. Handle pre-warm logic (30 minutes before wake)
  6. Log actions to audit_logs
- **Concurrency**: 1 worker (sequential execution)

### report_worker.py (WORK-RPT-01):
- **Schedule**: Weekly (every Monday at 9 AM)
- **Purpose**: Generate weekly savings reports
- **Process**:
  1. Aggregate savings data for last 7 days
  2. Generate HTML email template
  3. Send via SendGrid or AWS SES
  4. Log email delivery status
- **Concurrency**: 2 workers (parallel email sending)

### event_processor.py (WORK-EVT-01):
- **Schedule**: High priority queue (immediate processing)
- **Purpose**: Process cluster events in real-time (powers Hive Mind)
- **Process**:
  1. Receive events from Agent via POST /clusters/{id}/metrics
  2. Process events by type:
     - **Spot Interruption**: Call SVC-RISK-GLB.flag_risky_pool()
     - **OOMKilled**: Trigger MOD-SIZE-01 for right-sizing
     - **Node Not Ready**: Check if Spot interruption
     - **Pod Pending**: Check insufficient resources
  3. Deduplicate events using Redis
  4. Emit WebSocket notifications
  5. Update optimization_job if applicable
- **Concurrency**: 10 workers (events must be processed fast)
- **Critical**: Must process interruptions within milliseconds to protect all clients

---

## Celery Configuration

### Task Routing:
```python
CELERY_ROUTES = {
    'workers.discovery_worker': {'queue': 'discovery'},
    'workers.optimizer_worker': {'queue': 'optimization'},
    'workers.hibernation_worker': {'queue': 'hibernation'},
    'workers.report_worker': {'queue': 'reports'},
    'workers.event_processor': {'queue': 'events', 'priority': 10},
}
```

### Beat Schedule:
```python
CELERY_BEAT_SCHEDULE = {
    'discover-aws-resources': {
        'task': 'workers.discovery_worker',
        'schedule': crontab(minute='*/5'),
    },
    'check-hibernation-schedules': {
        'task': 'workers.hibernation_worker',
        'schedule': crontab(minute='*'),
    },
    'send-weekly-reports': {
        'task': 'workers.report_worker',
        'schedule': crontab(day_of_week=1, hour=9, minute=0),
    },
}
```

---

## Monitoring and Alerting

- Track task execution duration
- Alert if discovery worker takes > 5 minutes
- Alert if event processor latency > 1 second
- Alert if worker queue depth > 100
- Monitor worker memory and CPU usage
- Track task failure rate

---

## Error Handling

- Retry failed tasks with exponential backoff
- Maximum 3 retries per task
- Log all errors to centralized logging
- Send alerts for critical failures
- Implement circuit breaker for external API calls
