# Scripts - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains automation scripts for AWS infrastructure management and deployment operations. Scripts are organized into AWS-specific boto3 scripts and deployment/setup scripts.

---

## Module Structure

| Subfolder | Script Type | Purpose | Script Count | Key Script IDs |
|-----------|------------|---------|--------------|----------------|
| aws/ | AWS Infrastructure | boto3 scripts for EC2, ASG, Spot Fleet management | 4 scripts | SCRIPT-* |
| deployment/ | Deployment | Deployment and server setup automation | 2 scripts | DEPLOY-* |

---

## Component Table

| Subfolder | File Count | Status | Dependencies | Called By |
|-----------|-----------|--------|--------------|-----------|
| aws/ | 0 | Pending | boto3, AWS credentials | CORE-EXEC (Action Executor) |
| deployment/ | 0 | Pending | Docker, docker-compose, git | CI/CD Pipeline, Manual deployment |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Scripts Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for automation scripts
**Impact**: Created scripts directory with aws/ and deployment/ subdirectories
**Files Modified**:
- Created scripts/aws/
- Created scripts/deployment/
- Created scripts/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- AWS scripts are called by `backend/core/action_executor.py` (CORE-EXEC)
- Deployment scripts depend on Docker configurations in `/docker`

### External Dependencies
- **AWS SDK**: boto3
- **Container**: Docker, docker-compose
- **Version Control**: git
- **Shell**: bash
- **Utilities**: curl, jq (for deployment scripts)

---

## AWS Scripts Overview (`aws/`)

### Planned Scripts:

1. **terminate_instance.py** (SCRIPT-TERM-01)
   - Gracefully drains Kubernetes node
   - Checks PodDisruptionBudgets
   - Terminates EC2 instance
   - Supports DryRun mode

2. **launch_spot.py** (SCRIPT-SPOT-01)
   - Creates Spot Fleet requests
   - Validates capacity requirements
   - Supports diversification strategies
   - Supports DryRun mode

3. **detach_volume.py** (SCRIPT-VOL-01)
   - Waits for volume unmount
   - Detaches EBS volumes safely
   - Supports DryRun mode

4. **update_asg.py** (SCRIPT-ASG-01)
   - Updates Auto Scaling Group configuration
   - Validates min/max/desired capacity
   - Supports DryRun mode
   - Used by hibernation feature

---

## Deployment Scripts Overview (`deployment/`)

### Planned Scripts:

1. **deploy.sh**
   - Pulls latest code from repository
   - Builds Docker images
   - Runs database migrations
   - Starts services with docker-compose
   - Performs health checks
   - Rolls back on failure

2. **setup.sh**
   - Initial server setup
   - Installs Docker and docker-compose
   - Configures firewall rules
   - Sets up SSL certificates (Let's Encrypt)
   - Creates service users
   - Configures environment variables

---

## Script Execution Guidelines

### AWS Scripts:
1. **Authentication**: All scripts use IAM role assumption via STS
2. **Error Handling**: All scripts implement comprehensive error handling
3. **Logging**: All actions are logged with timestamps
4. **DryRun Mode**: All scripts support `--dry-run` flag for testing
5. **Rollback**: All scripts implement rollback logic on failure

### Deployment Scripts:
1. **Idempotency**: Scripts can be run multiple times safely
2. **Health Checks**: Verify service health after deployment
3. **Backup**: Create backup before major changes
4. **Logging**: All actions logged to deployment log file
5. **Notifications**: Send notifications on success/failure

---

## Safety Features

### DryRun Mode:
- All AWS scripts support `--dry-run` flag
- Logs what would happen without making changes
- Used by SAFE_MODE in backend

### Validation:
- All scripts validate inputs before execution
- Check for required permissions
- Verify resource existence
- Confirm destructive operations

### Audit Trail:
- All script executions logged to backend `audit_logs` table
- Includes actor, timestamp, action, and result
- Immutable audit records

---

## Testing Requirements

- Unit tests for all script functions
- Integration tests with mocked AWS responses
- DryRun tests for all AWS operations
- Deployment tests in staging environment
- Rollback scenario tests
