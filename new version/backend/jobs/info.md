# Backend Jobs Module

## Purpose

Scheduled jobs, background tasks, and automated maintenance operations.

**Last Updated**: 2025-12-25
**Authority Level**: MEDIUM-HIGH

---

## Files

### scheduler.py
**Purpose**: Job scheduling and cron-like functionality
**Lines**: ~170
**Key Components**:
- `JobScheduler` - Main scheduler class
- Cron job definitions
- Job execution tracking

**Scheduled Jobs**:
- **Midnight Health Check**: Runs at 00:00 UTC daily
- **Waste Scanner**: Runs every 6 hours
- **Cleanup Job**: Runs daily at 02:00 UTC
- **Security Enforcer**: Runs every hour

**Dependencies**:
- APScheduler or similar scheduling library
- All job modules (cleanup, waste_scanner, security_enforcer)

**Recent Changes**: None recent

### waste_scanner.py
**Purpose**: Automated detection of wasted AWS resources
**Lines**: ~400
**Key Functions**:
- `scan_idle_instances()` - Find instances with low utilization
- `scan_stopped_instances()` - Find long-stopped instances
- `scan_unattached_volumes()` - Find orphaned EBS volumes
- `scan_old_snapshots()` - Find outdated snapshots
- `generate_waste_report()` - Compile findings

**Waste Detection Criteria**:
- CPU < 5% for 7+ days
- Memory < 10% for 7+ days
- Instance stopped for 30+ days
- Unattached volumes for 14+ days
- Snapshots older than 90 days

**Dependencies**:
- backend/database/models.py
- backend/decision_engine/scoring.py
- boto3 (for CloudWatch metrics)

**Recent Changes**: None recent

### security_enforcer.py
**Purpose**: Automated security compliance checks
**Lines**: ~280
**Key Functions**:
- `check_unencrypted_volumes()` - Find unencrypted EBS volumes
- `check_public_instances()` - Find publicly accessible instances
- `check_security_groups()` - Overly permissive security groups
- `check_outdated_amis()` - Old/vulnerable AMIs
- `enforce_tagging_policy()` - Ensure required tags

**Security Rules**:
- All EBS volumes must be encrypted
- No instances should have public IPs (unless tagged "public-allowed")
- No security groups with 0.0.0.0/0 ingress on sensitive ports
- Instances must have required tags: "Owner", "Environment", "CostCenter"

**Dependencies**:
- backend/database/models.py
- boto3
- backend/logic/risk_manager.py

**Recent Changes**: None recent

### cleanup.py
**Purpose**: Database and resource cleanup operations
**Lines**: ~80
**Key Functions**:
- `cleanup_old_logs()` - Remove system logs older than 90 days
- `cleanup_completed_onboarding()` - Remove old onboarding requests
- `cleanup_orphaned_records()` - Remove orphaned database records

**Cleanup Rules**:
- System logs: Keep 90 days
- Onboarding requests: Delete after 24 hours if completed
- Orphaned instances: Flag for review if account deleted

**Dependencies**: backend/database/models.py

**Recent Changes**: None recent

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: JobScheduler, all job functions

---

## Job Execution Flow

```
Scheduler Triggers (cron)
   ↓
[Job Start] (scheduler.py)
   ↓
[Execute Job Logic] (specific job file)
   ↓
[Query Database / AWS]
   ↓
[Process Results]
   ↓
[Update Database]
   ↓
[Generate Reports/Notifications]
   ↓
[Log Completion]
```

---

## Job Schedule

| Job | Frequency | Time (UTC) | Purpose |
|-----|-----------|------------|---------|
| Health Check | Daily | 00:00 | Update instance metrics |
| Waste Scanner | Every 6h | 00:00, 06:00, 12:00, 18:00 | Find waste |
| Security Enforcer | Hourly | Every :00 | Security compliance |
| Cleanup | Daily | 02:00 | Database cleanup |

---

## Dependencies

### Depends On:
- APScheduler (or similar)
- backend/database/models.py
- backend/decision_engine/
- backend/logic/risk_manager.py
- backend/utils/component_health_checks.py
- boto3 (for AWS API calls)

### Depended By:
- Dashboard (displays waste findings)
- Security reports
- System health monitoring

**Impact Radius**: MEDIUM-HIGH (affects automated operations)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing job system
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Usage

### Manual Job Execution
```python
from backend.jobs.waste_scanner import scan_idle_instances

# Run manually (for testing)
results = scan_idle_instances()
```

### Register New Job
```python
from backend.jobs.scheduler import JobScheduler

scheduler = JobScheduler()
scheduler.add_job(
    func=my_job_function,
    trigger='cron',
    hour=3,
    minute=0
)
```

---

## Monitoring

### Job Execution Logs
All jobs log to SystemLog table:
- Start time
- Completion time
- Results count
- Errors (if any)

### Failed Job Handling
- Retry 3 times with exponential backoff
- Log failure to SystemLog
- Send notification (if configured)

---

## Known Issues

### None

Jobs module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM-HIGH - Automated operations_
