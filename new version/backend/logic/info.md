# Backend Logic Module - Complete Implementation Reference

## Purpose

Business logic for ML model lifecycle management and global spot pool risk intelligence (hive immunity system).

**Last Updated**: 2025-12-25 (Comprehensive Enhancement)
**Authority Level**: HIGH (Critical business logic)
**Total Files**: 3 Python files
**Total Lines**: ~690

---

## Complete Module Reference

### 1. risk_manager.py - GLOBAL SPOT POOL INTELLIGENCE (392 lines) ⭐ CRITICAL

**Purpose**: "Herd Immunity" for spot optimization - one client's failure protects everyone

**Core Concept**: When ANY client experiences a spot interruption in PRODUCTION, that pool is flagged globally for 15 days, protecting ALL clients from using it.

---

#### RiskManager Class - Lines 21-377

**Initialization** (line 32):
```python
risk_mgr = RiskManager(db)
```

**Constants**:
- `POISON_DURATION_DAYS = 15` (line 30)

---

### Key Methods - Legacy Pattern (SpotPoolRisk Table)

#### is_pool_poisoned(region, az, instance_type) - Lines 41-86
**Purpose**: THE GATEKEEPER - Check if pool should be avoided

**Complete Flow**:
```
1. Query SpotPoolRisk table
   WHERE region=region AND availability_zone=az AND instance_type=type
   ↓
2. IF no record exists:
   → Return False (pool is safe)
   ↓
3. IF record exists but is_poisoned=False:
   → Return False (pool is safe)
   ↓
4. IF record exists and is_poisoned=True:
   → Check if poison_expires_at > now
   ↓
5. IF poison expired:
   → Auto-cleanup: Set is_poisoned=False
   → Commit to database
   → Return False (pool is safe)
   ↓
6. ELSE:
   → Return True (pool is POISONED - avoid!)
```

**Usage in Pipelines**:
```python
# In linear_optimizer.py, cluster_optimizer.py, kubernetes_optimizer.py
if risk_mgr.is_pool_poisoned(region, az, instance_type):
    # Skip this pool entirely, choose different candidate
    continue
```

**Database Operations**:
- **READ**: `spot_pool_risks` (SELECT with composite key)
- **UPDATE**: `spot_pool_risks` (auto-cleanup if expired)

---

#### mark_pool_as_poisoned(...) - Lines 88-153
**Purpose**: Flag a pool as dangerous for 15 days

**Parameters**:
- `region`: AWS region (e.g., 'us-east-1')
- `availability_zone`: AZ (e.g., 'us-east-1a')
- `instance_type`: Instance type (e.g., 'c5.large')
- `triggering_customer_id`: UUID of account that had interruption
- `metadata`: Additional context (event type, price spike, etc.)

**Complete Flow**:
```
1. Calculate expiry: now + 15 days
   ↓
2. Query SpotPoolRisk for existing record
   ↓
3A. IF record exists:
    → UPDATE is_poisoned=True
    → INCREMENT interruption_count
    → UPDATE last_interruption=now
    → UPDATE poisoned_at=now
    → UPDATE poison_expires_at=expiry
    → UPDATE triggering_customer_id
    → UPDATE metadata
    ↓
3B. IF record does NOT exist:
    → INSERT new SpotPoolRisk
    → SET is_poisoned=True
    → SET interruption_count=1
    → SET last_interruption=now
    → SET poisoned_at=now
    → SET poison_expires_at=expiry
    → SET triggering_customer_id
    → SET metadata
    ↓
4. Commit to database
   ↓
5. Print warning:
   "⚠️  Pool {region}/{az}/{type} marked as POISONED until {expiry}"
```

**Database Operations**:
- **UPSERT**: `spot_pool_risks` (INSERT or UPDATE)

**Called By**:
- `handle_interruption_signal()` (line 155)
- `workers/event_processor.py` (external)

---

#### handle_interruption_signal(...) - Lines 155-211 ⚠️ CRITICAL
**Purpose**: Process interruption from AWS EventBridge with Production check

**Critical Logic - Production vs Lab Mode**:
```python
# Line 190 - THE CRITICAL CHECK
if account.environment_type != 'PROD':
    print("Lab Mode interruption - NOT poisoning pool")
    return None  # Ignore Lab failures

# Line 194 - Production interruption
print("🚨 PRODUCTION INTERRUPTION detected")
# → Poison the pool globally
```

**Why This Matters**:
- **Lab Mode**: Experiments expected to fail, don't poison pools
- **Production Mode**: Real customer impact, protect everyone

**Complete Flow**:
```
1. Receive interruption signal from AWS EventBridge
   → Extract: region, az, instance_type, account_id, event_type
   ↓
2. Query Account table WHERE account_id = aws_account_id
   ↓
3. IF account NOT found:
   → Log warning: "Unknown account - ignoring"
   → Return None
   ↓
4. Check account.environment_type
   ↓
5A. IF environment_type != 'PROD' (Lab Mode):
    → Log: "Lab Mode interruption - NOT poisoning pool"
    → Return None (Lab failures don't affect global risk)
    ↓
5B. IF environment_type == 'PROD' (Production):
    → Log: "🚨 PRODUCTION INTERRUPTION detected"
    → Create metadata dict (event_type, account_id, timestamp)
    → Call mark_pool_as_poisoned()
    → Return SpotPoolRisk record
```

**Database Operations**:
- **READ**: `accounts` (check environment_type)
- **UPSERT**: `spot_pool_risks` (via mark_pool_as_poisoned)

**Called By**:
- AWS EventBridge → Lambda → This method
- `workers/event_processor.py` (wrapper)

---

#### get_poisoned_pools(region=None) - Lines 213-244
**Purpose**: List all currently poisoned pools

**Features**:
- Optional region filter
- Auto-cleanup of expired poisons

**Database Operations**:
- **READ**: `spot_pool_risks` WHERE is_poisoned=True
- **UPDATE**: Auto-cleanup expired pools

---

#### cleanup_expired_poisons() - Lines 246-275
**Purpose**: Periodic cleanup job (run daily)

**Query**:
```sql
SELECT * FROM spot_pool_risks
WHERE is_poisoned = TRUE
  AND poison_expires_at < NOW()
```

**Actions**:
- Set `is_poisoned=False`
- Clear `poisoned_at` and `poison_expires_at`
- Print count: "🧹 Cleaned up {count} expired poison flags"

**Should Run**: Daily cron job

---

### New Pattern: Global Risk Events (Append-Only Log)

#### register_risk_event(...) - Lines 281-339 ⭐ NEW PATTERN
**Purpose**: Write-only fast path for event logging (no queries)

**Performance**: ~1ms (just INSERT, no SELECTs)

**Parameters**:
- `db`: Database session
- `pool_id`: Format 'us-east-1a:c5.large' (az:type)
- `event_type`: 'rebalance_notice' or 'termination_notice'
- `client_id`: UUID of client
- `metadata`: Additional context

**Complete Flow**:
```
1. Parse pool_id: 'us-east-1a:c5.large'
   → availability_zone = 'us-east-1a'
   → instance_type = 'c5.large'
   → region = 'us-east-1' (extract from AZ)
   ↓
2. Calculate timestamps:
   → reported_at = now
   → expires_at = now + 15 days
   ↓
3. Create GlobalRiskEvent record:
   → pool_id, region, availability_zone, instance_type
   → event_type, reported_at, expires_at
   → source_client_id, event_metadata
   ↓
4. INSERT into global_risk_events (NO queries!)
   ↓
5. Commit and refresh
   ↓
6. Return created event
```

**Database Operations**:
- **INSERT ONLY**: `global_risk_events` (append-only, no updates)

**Advantages over Legacy Pattern**:
- ✅ No queries (faster)
- ✅ Never updates existing data (write-only)
- ✅ Scales to millions of events
- ✅ Full history preserved (good for ML training)

**Called By**:
- `workers/event_processor.py:79` (rebalance notice handler)
- `workers/event_processor.py:198` (termination notice handler)

---

#### is_pool_safe(pool_id) - Lines 341-376 ⭐ READ-ONLY FAST PATH
**Purpose**: Check if pool is safe (complement to register_risk_event)

**Performance**: <5ms even with millions of events (indexed query)

**Parameters**:
- `db`: Database session
- `pool_id`: Format 'us-east-1a:c5.large'

**Returns**:
- Tuple: `(is_safe: bool, active_events: List[GlobalRiskEvent])`

**Query**:
```sql
SELECT * FROM global_risk_events
WHERE pool_id = 'us-east-1a:c5.large'
  AND expires_at > NOW()
```

**Logic**:
```python
is_safe = len(active_events) == 0
```

**Usage**:
```python
is_safe, events = RiskManager.is_pool_safe(db, 'us-east-1a:c5.large')
if not is_safe:
    print(f"Pool poisoned: {len(events)} active disruptions")
    # Skip this pool, choose different candidate
```

**Database Operations**:
- **READ**: `global_risk_events` (indexed on pool_id, expires_at)

---

### Pattern Comparison

| Feature | Legacy (SpotPoolRisk) | New (GlobalRiskEvent) |
|---------|----------------------|----------------------|
| **Write Speed** | Slow (UPSERT, query first) | Fast (INSERT only, ~1ms) |
| **Read Speed** | Fast (single record) | Fast (indexed query) |
| **History** | Overwrites (count only) | Full history preserved |
| **Cleanup** | Manual UPDATE | Auto-expiry via query filter |
| **ML Training** | Limited data | Rich event history |
| **Scalability** | Good (single record per pool) | Excellent (millions of events) |

**Current Usage**:
- Legacy: Still in use, documented above
- New: Used by `workers/event_processor.py` (lines 79, 198)

---

## 2. model_registry.py - ML MODEL LIFECYCLE (299 lines)

**Purpose**: Manage ML model lifecycle from upload to production deployment

**Model Status Flow**:
```
CANDIDATE → TESTING → GRADUATED → ENABLED (is_active_prod=True) → ARCHIVED
```

**Constraint**: Only ONE model can have `is_active_prod=True` at a time

---

### Key Functions

#### scan_and_register_models(db, user_id) - Lines 37-100
**Purpose**: Scan `ml-models/` directory for new .pkl files

**Complete Flow**:
```
1. Check if ml-models/ directory exists
   → If not: Create it
   ↓
2. Find all *.pkl files in directory
   ↓
3. For each .pkl file:
   ↓
   3a. Check if already registered in database
       Query MLModel WHERE name = filename
       ↓
   3b. IF already exists:
       → Increment existing_count
       → Continue to next file
       ↓
   3c. IF new file:
       → Calculate SHA256 hash (file integrity)
       → CREATE MLModel record:
         - name = filename
         - file_path = absolute path
         - file_hash = SHA256
         - status = CANDIDATE
         - is_active_prod = False
         - uploaded_by = user_id
       → INSERT into database
       → Increment new_count
       → Log success
   ↓
4. Commit all new models
   ↓
5. Return (new_count, existing_count)
```

**Database Operations**:
- **READ**: `ml_models` (check if exists)
- **INSERT**: `ml_models` (new models)

**File Integrity**: SHA256 hash ensures model file hasn't been tampered with

---

#### graduate_model(db, model_id, user_id) - Lines 103-147
**Purpose**: Promote model from CANDIDATE to GRADUATED

**Validation**:
- Model must exist
- Can't already be GRADUATED
- Can't be ARCHIVED (no resurrection)

**Actions**:
- Set `status = GRADUATED`
- Set `graduated_at = now`
- Commit and log

**Database Operations**:
- **READ**: `ml_models` (fetch model)
- **UPDATE**: `ml_models` (set status)

---

#### set_production_model(db, model_id, user_id) - Lines 150-205 ⚠️ CRITICAL
**Purpose**: Activate model for production use (enforces single-active rule)

**Critical Constraint**: Only ONE model can have `is_active_prod=True`

**Complete Flow**:
```
1. Query MLModel WHERE id = model_id
   ↓
2. Validate model exists
   ↓
3. Validate model.status == GRADUATED
   → MUST be graduated before production deployment
   ↓
4. Find currently active model:
   Query MLModel WHERE is_active_prod = True
   ↓
5. IF currently active model exists:
   → Deactivate it: is_active_prod = False
   → Log: "Deactivated previous production model"
   ↓
6. Activate new model:
   → Set is_active_prod = True
   → Set deployed_at = now
   ↓
7. Commit changes
   ↓
8. Log success: "Production model activated"
```

**Database Operations**:
- **READ**: `ml_models` (fetch target model)
- **READ**: `ml_models` (find currently active)
- **UPDATE**: `ml_models` (deactivate old, activate new)

**Atomic Operation**: Both updates in single transaction (enforces constraint)

---

#### get_active_production_model(db) - Lines 208-223
**Purpose**: Get the currently active production model

**Query**:
```sql
SELECT * FROM ml_models
WHERE is_active_prod = TRUE
  AND status = 'GRADUATED'
LIMIT 1
```

**Returns**: `MLModel` instance or `None`

**Used By**:
- `/backend/pipelines/linear_optimizer.py` (load model for inference)
- `/backend/ai/` modules (ML prediction)

---

#### archive_model(db, model_id, user_id) - Lines 226-270
**Purpose**: Mark model as deprecated/removed

**Validation**:
- Can't archive if `is_active_prod=True` (deactivate first)

**Actions**:
- Set `status = ARCHIVED`
- Set `is_active_prod = False` (safety)
- Log previous status

---

#### Helper Functions

**get_models_by_status(db, status)** - Line 273: List all models with specific status

**get_model_by_name(db, model_name)** - Line 287: Find model by filename

---

## Database Table Dependencies

### SpotPoolRisk Table (Legacy Pattern)
**Composite Key**: (region, availability_zone, instance_type)

**Fields Used**:
- `is_poisoned` (Boolean) - Pool currently dangerous?
- `interruption_count` (Integer) - How many times interrupted
- `last_interruption` (DateTime) - When last interruption occurred
- `poisoned_at` (DateTime) - When poison flag was set
- `poison_expires_at` (DateTime) - When poison will expire (15 days)
- `triggering_customer_id` (UUID) - Who experienced the interruption
- `metadata` (JSONB) - Event details

**Referenced By**:
- `is_pool_poisoned()` (READ)
- `mark_pool_as_poisoned()` (UPSERT)
- `handle_interruption_signal()` (UPSERT via mark_pool_as_poisoned)
- `get_poisoned_pools()` (READ, UPDATE)
- `cleanup_expired_poisons()` (READ, UPDATE)

---

### GlobalRiskEvent Table (New Pattern)
**Primary Key**: `id` (auto-increment)
**Indexes**: `pool_id`, `expires_at`

**Fields Used**:
- `pool_id` (String) - Format: 'us-east-1a:c5.large'
- `region`, `availability_zone`, `instance_type` (parsed from pool_id)
- `event_type` (String) - 'rebalance_notice' or 'termination_notice'
- `reported_at` (DateTime) - When event occurred
- `expires_at` (DateTime) - When event expires (15 days)
- `source_client_id` (UUID) - Who reported the event
- `event_metadata` (JSONB) - Additional context

**Referenced By**:
- `register_risk_event()` (INSERT)
- `is_pool_safe()` (READ)

**Append-Only**: Never updates existing records, only INSERTs

---

### MLModel Table
**Primary Key**: `id` (auto-increment)
**Unique Constraint**: `name` (filename)

**Fields Used**:
- `name` (String) - Filename (e.g., "v2_aggressive_risk.pkl")
- `file_path` (String) - Absolute path to .pkl file
- `file_hash` (String) - SHA256 hash for integrity
- `status` (Enum) - CANDIDATE/TESTING/GRADUATED/ENABLED/ARCHIVED
- `is_active_prod` (Boolean) - **Only ONE can be True**
- `uploaded_by`, `graduated_at`, `deployed_at` (tracking)

**Referenced By**:
- All model_registry.py functions
- `/backend/ai/` modules (model loading)
- `/backend/pipelines/` (ML inference)

---

### Account Table
**Used For**: Environment type check (PROD vs Lab)

**Field Used**:
- `environment_type` (String) - 'PROD' or 'LAB'

**Referenced By**:
- `handle_interruption_signal()` (line 181) - Critical Production check

---

## API Endpoints Using This Module

### Risk Manager APIs

**None directly** - RiskManager is used internally by:
- `workers/event_processor.py` (handles AWS EventBridge events)
- `pipelines/*.py` (check pool safety before launching instances)

---

### Model Registry APIs

**Likely endpoints** (check `/backend/api/governance_routes.py`):
- `POST /ml/models/scan` → `scan_and_register_models()`
- `POST /ml/models/{id}/graduate` → `graduate_model()`
- `POST /ml/models/{id}/activate` → `set_production_model()`
- `GET /ml/models/active` → `get_active_production_model()`
- `POST /ml/models/{id}/archive` → `archive_model()`

---

## Frontend Components Using This Module

### Risk Manager
**Indirect usage** - No direct UI interaction
- Dashboard shows poisoned pools (if implemented)
- Risk warnings displayed to users

### Model Registry
**Likely components** (check `/frontend/src/components/Lab/`):
- `ModelGovernance.jsx` - Model lifecycle management UI
- Shows models by status (CANDIDATE, TESTING, GRADUATED, etc.)
- "Graduate Model" button → calls graduate API
- "Activate for Production" button → calls activate API

---

## Worker Integration

### event_processor.py Uses RiskManager

**Rebalance Notice Handler** (line 79):
```python
RiskManager.register_risk_event(
    db=db,
    pool_id=pool_id,
    event_type='rebalance_notice',
    client_id=str(instance.account.user_id),
    metadata={'instance_id': instance_id, 'timestamp': ...}
)
```

**Termination Notice Handler** (line 198):
```python
RiskManager.register_risk_event(
    db=db,
    pool_id=pool_id,
    event_type='termination_notice',
    client_id=str(instance.account.user_id),
    metadata={'instance_id': instance_id, 'warning_time': '2min'}
)
```

---

### Pipelines Use RiskManager

**linear_optimizer.py**, **cluster_optimizer.py**, **kubernetes_optimizer.py**:
```python
risk_mgr = RiskManager(db)

for candidate in candidate_pools:
    if risk_mgr.is_pool_poisoned(region, az, instance_type):
        # Skip poisoned pool
        continue

    # Pool is safe, proceed with optimization
```

**Alternative (new pattern)**:
```python
is_safe, events = RiskManager.is_pool_safe(db, pool_id)
if not is_safe:
    # Skip pool
    continue
```

---

## Protected Zones

### None Currently

No protected zones in this module (yet), but consider these critical:

**Candidates for Protection**:
1. **15-day poison duration** (line 30) - Changing this affects global risk model
2. **Production check** (line 190) - Critical security logic
3. **Single active model constraint** (line 180) - Prevents multiple models in prod

**Recommendation**: Add to `/progress/regression_guard.md` if modified

---

## Recent Changes

### 2025-12-25: Documentation Enhancement
**Files Changed**: info.md (this file)
**Reason**: Comprehensive documentation with actual implementation details
**Impact**: Better LLM understanding of risk management and model lifecycle
**Code Changes**: None

---

## Performance Characteristics

### Legacy Pattern (SpotPoolRisk)
- **Write**: ~5-10ms (query + upsert)
- **Read**: ~2-5ms (indexed query on composite key)
- **Cleanup**: Batch operation, ~50-100ms for 1000 expired pools

### New Pattern (GlobalRiskEvent)
- **Write**: ~1ms (insert only, no queries)
- **Read**: ~2-5ms (indexed query on pool_id, expires_at)
- **Cleanup**: Auto-expiry via query filter (no manual cleanup needed)

### Model Registry
- **Scan**: ~100-500ms (filesystem scan + hash calculation)
- **Graduate**: ~5ms (single update)
- **Activate**: ~10ms (2 updates in transaction)

---

## Monitoring

### Check Poisoned Pools
```sql
SELECT region, availability_zone, instance_type,
       interruption_count, poisoned_at, poison_expires_at
FROM spot_pool_risks
WHERE is_poisoned = TRUE
ORDER BY poisoned_at DESC;
```

### Check Active Risk Events
```sql
SELECT pool_id, event_type, reported_at, expires_at, source_client_id
FROM global_risk_events
WHERE expires_at > NOW()
ORDER BY reported_at DESC
LIMIT 100;
```

### Check Model Status
```sql
SELECT name, status, is_active_prod, uploaded_at, graduated_at, deployed_at
FROM ml_models
ORDER BY uploaded_at DESC;
```

### Verify Single Active Model Constraint
```sql
SELECT COUNT(*) FROM ml_models WHERE is_active_prod = TRUE;
-- Should always return 0 or 1, NEVER > 1
```

---

## Testing

### Test Risk Manager
```python
from backend.logic.risk_manager import RiskManager

db = SessionLocal()
risk_mgr = RiskManager(db)

# Test poisoning
risk_mgr.mark_pool_as_poisoned(
    region='us-east-1',
    availability_zone='us-east-1a',
    instance_type='c5.large'
)

# Test check
is_poisoned = risk_mgr.is_pool_poisoned('us-east-1', 'us-east-1a', 'c5.large')
assert is_poisoned == True

# Test new pattern
event = RiskManager.register_risk_event(
    db=db,
    pool_id='us-east-1a:c5.large',
    event_type='rebalance_notice'
)

is_safe, events = RiskManager.is_pool_safe(db, 'us-east-1a:c5.large')
assert is_safe == False
assert len(events) == 1
```

### Test Model Registry
```python
from backend.logic.model_registry import (
    scan_and_register_models,
    graduate_model,
    set_production_model,
    get_active_production_model
)

db = SessionLocal()

# Scan for models
new, existing = scan_and_register_models(db)

# Graduate first model
models = db.query(MLModel).filter(MLModel.status == 'CANDIDATE').all()
graduate_model(db, models[0].id)

# Activate for production
set_production_model(db, models[0].id)

# Verify
active = get_active_production_model(db)
assert active.id == models[0].id
assert active.is_active_prod == True
```

---

_Last Updated: 2025-12-25 (Complete Implementation Documentation)_
_Authority: HIGH - Critical business logic for risk management and model lifecycle_
