# Backend Executor Module

## Purpose

Execution layer for implementing optimization actions on AWS resources.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### base.py
**Purpose**: Base executor class and interfaces
**Lines**: ~120
**Key Classes**:
- `BaseExecutor` - Abstract base class for all executors
- Defines standard execution interface

**Methods**:
- `execute()` - Execute an action
- `validate()` - Pre-execution validation
- `rollback()` - Rollback mechanism for failed executions

**Dependencies**: abc (Abstract Base Classes)
**Recent Changes**: None recent

### aws_agentless.py
**Purpose**: AWS resource manipulation without requiring agents on instances
**Lines**: ~300
**Key Classes**:
- `AWSAgentlessExecutor(BaseExecutor)` - Execute AWS API-based actions

**Capabilities**:
- Instance stop/start/terminate
- Instance type modification (resize)
- Tag management
- Snapshot creation
- EBS volume optimization

**Security**:
- Uses IAM role credentials from Account table
- Validates permissions before execution
- Audit logging for all actions

**Dependencies**:
- boto3 (AWS SDK)
- backend/database/models.py (Account, Instance)
- backend/utils/crypto.py (credential decryption)

**Recent Changes**:
- 2025-12-23: Updated error handling for edge cases

### __init__.py
**Purpose**: Package initialization and exports
**Exports**: BaseExecutor, AWSAgentlessExecutor

---

## Execution Flow

```
Optimization Recommendation
   ↓
[Validate Action] (base.py)
   ↓
[Check AWS Permissions]
   ↓
[Decrypt Credentials] (if needed)
   ↓
[Execute via AWS API] (aws_agentless.py)
   ↓
[Update Database] (Instance status)
   ↓
[Log Action] (SystemLog)
   ↓
[Return Result]
```

---

## Supported Actions

### Instance Lifecycle
- **Stop**: Stop running instances (reversible)
- **Start**: Start stopped instances
- **Terminate**: Delete instances (irreversible, requires confirmation)

### Instance Optimization
- **Resize**: Change instance type (e.g., t3.large → t3.medium)
- **Volume Optimization**: Resize EBS volumes, change volume types

### Management
- **Tagging**: Add/update/remove instance tags
- **Snapshot**: Create EBS snapshots before changes

---

## Safety Mechanisms

1. **Pre-execution Validation**: Check instance state, permissions
2. **Dry-run Mode**: AWS dry-run API calls to verify before execution
3. **Rollback Support**: Ability to revert changes
4. **Confirmation Required**: Critical actions require explicit confirmation
5. **Audit Trail**: All executions logged to SystemLog

---

## Dependencies

### Depends On:
- boto3 (AWS SDK)
- backend/database/models.py
- backend/utils/crypto.py
- backend/auth/ (for user context)

### Depended By:
- backend/api/ (action endpoints)
- backend/jobs/ (automated optimization jobs)
- Frontend action buttons

**Impact Radius**: HIGH (executes real AWS changes)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing executor logic
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

### 2025-12-23: Error Handling Enhancement
**Files Changed**: aws_agentless.py
**Reason**: Improve handling of AWS API rate limits and edge cases
**Impact**: More robust execution with better error messages
**Reference**: Legacy documentation

---

## Usage

### Execute Instance Stop
```python
from backend.executor.aws_agentless import AWSAgentlessExecutor

executor = AWSAgentlessExecutor(account_id, credentials)
result = executor.execute({
    "action": "stop",
    "instance_id": "i-1234567890abcdef0"
})
```

### Execute Instance Resize
```python
result = executor.execute({
    "action": "resize",
    "instance_id": "i-1234567890abcdef0",
    "new_type": "t3.medium"
})
```

---

## Security Considerations

1. **Credential Protection**: Credentials decrypted only in memory, never logged
2. **Permission Validation**: Verify IAM permissions before execution
3. **User Authorization**: Verify user owns the account
4. **Action Logging**: All actions logged with user ID, timestamp, details
5. **Rate Limiting**: Respect AWS API rate limits

---

## Known Issues

### None

Executor module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Executes real AWS changes_
