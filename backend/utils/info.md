# Backend Utilities

## Purpose

Shared utility functions and helpers used across the backend application.

**Last Updated**: 2025-12-25

---

## Files

### crypto.py ⚠️ PROTECTED
**Purpose**: Credential encryption/decryption using AES-256
**Lines**: ~40
**Status**: CRITICAL - DO NOT MODIFY

**Key Functions**:
- `encrypt_credential(plaintext)` - Encrypt credentials
- `decrypt_credential(ciphertext)` - Decrypt credentials

**Algorithm**: AES-256 (Fernet)
**Key Source**: Environment variable `ENCRYPTION_KEY`

**Usage**:
```python
# Encrypt AWS credentials before storage
encrypted = encrypt_credential(secret_key)

# Decrypt for AWS API calls
plaintext = decrypt_credential(encrypted)
```

**⚠️ WARNING**:
- NEVER change encryption algorithm without migration plan
- Must preserve ability to decrypt existing credentials
- Security review required for any changes
- See: `/progress/regression_guard.md#credential-encryption`

**Recent Changes**: None (stable since initial implementation)

---

### component_health_checks.py
**Purpose**: Health check logic for all system components
**Lines**: ~500
**Status**: STABLE

**Key Functions**:
- `run_all_health_checks(db)` - Execute all health checks (line 437)
- `DatabaseCheck.check()` - Database latency test
- `RedisCheck.check()` - Redis connectivity
- `K8sWatcherCheck.check()` - K8s watcher heartbeat
- `OptimizerCheck.check()` - Optimizer last run
- `PriceScraperCheck.check()` - Price data freshness
- `RiskEngineCheck.check()` - Risk data age
- `MLInferenceCheck.check()` - Model availability

**Health Statuses**:
- `"healthy"` - Component operating normally
- `"degraded"` - Component slow or backlog forming
- `"critical"` - Component failed or unavailable

**Usage**:
```python
from utils.component_health_checks import run_all_health_checks

results = run_all_health_checks(db)
# Returns: {"database": ("healthy", {...}), "redis": ("degraded", {...}), ...}
```

**Dependencies**:
- database/models.py
- utils/decision_pipeline_health.py

**Recent Changes**:
- **2025-12-25**: Now triggered by discovery worker after completion
  - **Trigger Point**: workers/discovery_worker.py:335
  - **Impact**: Dashboard metrics populate immediately

**Reference**: `/index/feature_index.md#health-monitoring`

---

### system_logger.py
**Purpose**: Structured logging to database and console
**Lines**: ~300
**Status**: STABLE

**Key Classes**:
- `SystemLogger` - Structured logging with database persistence

**Usage**:
```python
from utils.system_logger import SystemLogger

logger = SystemLogger('component_name', db=db)
logger.info("Operation completed", details={"count": 10})
logger.error("Operation failed", details={"error": str(e)})
```

**Log Levels**:
- DEBUG, INFO, WARNING, ERROR, CRITICAL

**Storage**:
- Database: `system_logs` table
- Console: stdout

**Recent Changes**: None recent

---

### aws_session.py
**Purpose**: AWS session management and helpers
**Lines**: ~150
**Status**: STABLE

**Key Functions**:
- AWS session creation
- Credential management
- STS operations

**Dependencies**:
- boto3

**Recent Changes**: None recent

---

### decision_pipeline_health.py
**Purpose**: Health checks for decision pipeline components
**Lines**: ~200
**Status**: STABLE

**Key Functions**:
- Decision pipeline health monitoring
- Standalone pipeline checks

**Dependencies**:
- database/models.py

**Recent Changes**: None recent

---

### health_checks.py
**Purpose**: Legacy health check functions
**Lines**: ~300
**Status**: DEPRECATED - Use component_health_checks.py

**Note**: Kept for backward compatibility

**Recent Changes**: None recent

---

### model_loader.py
**Purpose**: ML model loading and caching
**Lines**: ~250
**Status**: STABLE

**Key Functions**:
- Model loading from storage
- Model caching
- Model version management

**Dependencies**:
- ml_models/ module

**Recent Changes**: None recent

---

### k8s_auth.py
**Purpose**: Kubernetes authentication and authorization
**Lines**: ~250
**Status**: STABLE

**Key Functions**:
- K8s cluster authentication
- Service account management
- RBAC helpers

**Dependencies**:
- kubernetes Python client

**Recent Changes**: None recent

---

## Usage Patterns

### Encryption (CRITICAL)
```python
# ALWAYS encrypt before storing
from utils.crypto import encrypt_credential, decrypt_credential

# Store
encrypted = encrypt_credential(aws_secret_key)
account.aws_secret_access_key = encrypted
db.commit()

# Retrieve
encrypted = account.aws_secret_access_key
plaintext = decrypt_credential(encrypted)
boto3_session = boto3.Session(
    aws_secret_access_key=plaintext
)
```

### Health Checks
```python
# Run all checks
from utils.component_health_checks import run_all_health_checks

results = run_all_health_checks(db)

# Check specific component
if results["database"][0] != "healthy":
    logger.warning("Database degraded")
```

### Logging
```python
# Structured logging
from utils.system_logger import SystemLogger

logger = SystemLogger('MyComponent', db=db)
logger.info("Process started", details={"user_id": 123})

try:
    # Operation
    pass
except Exception as e:
    logger.error("Process failed", details={"error": str(e)})
```

---

## Dependencies

**Requires**:
- cryptography (encryption)
- boto3 (AWS operations)
- sqlalchemy (database)

**Required By**:
- api/ (all routes)
- workers/ (all workers)
- Backend application

---

## Security Notes

### Encryption Keys

**CRITICAL**: NEVER commit `ENCRYPTION_KEY` to source control

**Setup**:
```bash
# Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Store in .env
echo "ENCRYPTION_KEY=your-key-here" >> .env
```

### Protected Functions

**⚠️ NEVER modify without reading**:
- `crypto.py:encrypt_credential()`
- `crypto.py:decrypt_credential()`

See: `/progress/regression_guard.md#credential-encryption`

---

## Recent Changes Summary

### 2025-12-25
**Files Changed**: None
**Documentation**: Added to governance structure

**component_health_checks.py Integration**:
- Now called by discovery_worker after completion
- Enables immediate dashboard data population
- Problem fixed: P-2025-12-25-002

---

## Testing

### Unit Tests
```bash
pytest tests/utils/
```

### Manual Testing
```python
# Test encryption
from utils.crypto import encrypt_credential, decrypt_credential

original = "test-secret"
encrypted = encrypt_credential(original)
decrypted = decrypt_credential(encrypted)
assert original == decrypted

# Test health checks
from utils.component_health_checks import run_all_health_checks
results = run_all_health_checks(db)
print(results)
```

---

_Last Updated: 2025-12-25_
_See: `/progress/regression_guard.md` for protected zones_
