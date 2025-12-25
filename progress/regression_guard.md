# Regression Guard

## Purpose

Explicit "DO NOT TOUCH" zones and regression prevention rules.

**Last Updated**: 2025-12-25

---

## Critical Rules

### 🚫 NEVER Modify Without Explicit Approval

These components have been debugged extensively and MUST NOT be changed casually.

---

## 1. Authentication Token Generation

**Location**: `backend/api/auth.py`
**Function**: `create_access_token()`

**Protected Behavior**:
- Token expiration: **24 hours** (fixed 2025-11-26)
- JWT signing algorithm: HS256
- Token structure: `{"sub": username, "exp": timestamp}`

**Why Protected**:
- Token expiration was previously 5 minutes (bug)
- Fix took multiple iterations
- Breaking this affects ALL authenticated users

**If You MUST Modify**:
1. Read `/progress/fixed_issues_log.md` - Token expiration fix
2. Update `/progress/fixed_issues_log.md` with your change
3. Add regression test
4. Verify all auth flows still work

---

## 2. Global AWS Account Uniqueness Check

**Location**:
- `backend/api/onboarding_routes.py:505-520` (CloudFormation)
- `backend/api/onboarding_routes.py:163-179` (Credentials)

**Protected Behavior**:
- AWS Account IDs MUST be globally unique
- HTTP 409 Conflict if account already claimed
- Allow re-connection for same user

**Why Protected**:
- Critical security vulnerability if removed (P-2025-12-25-001)
- Prevents account takeover attacks
- Took multiple sessions to get right

**If You MUST Modify**:
1. **DO NOT** remove uniqueness check
2. **DO NOT** weaken security
3. **DO** preserve HTTP 409 response
4. **DO** test with multiple users

---

## 3. Credential Encryption

**Location**: `backend/utils/crypto.py`
**Functions**: `encrypt_credential()`, `decrypt_credential()`

**Protected Behavior**:
- Algorithm: AES-256 (Fernet)
- Key source: Environment variable `ENCRYPTION_KEY`
- Must decrypt old credentials

**Why Protected**:
- Changing algorithm breaks existing encrypted credentials
- Migration required if modification needed
- Security-critical

**If You MUST Modify**:
1. **NEVER** change without migration plan
2. **ALWAYS** preserve backward compatibility
3. **ALWAYS** security review required
4. **ALWAYS** test decryption of existing data

---

## 4. Discovery Worker Status Transitions

**Location**: `backend/workers/discovery_worker.py`
**Lines**: 261-320 (status update logic)

**Protected Behavior**:
- `pending` → `connected` (never directly; via onboarding API)
- `connected` → `active` (on successful discovery)
- `connected` → `failed` (on discovery error)

**Why Protected**:
- Dashboard depends on these exact status values
- AuthGateway routing depends on status
- Frontend polling depends on transitions

**If You MUST Modify**:
1. Update `/index/feature_index.md` - Discovery Worker
2. Update `/scenarios/resource_discovery_flow.md`
3. Update frontend polling logic
4. Verify dashboard empty states

---

## 5. DELETE Endpoint Status Code

**Location**: `backend/api/client_routes.py:84`

**Protected Behavior**:
```python
@router.delete("/accounts/{account_id}", status_code=200)
```

**Why Protected**:
- HTTP 204 forbids response body (P-2025-12-25-003)
- Frontend expects JSON confirmation
- HTTP standard compliance

**If You MUST Modify**:
1. **NEVER** use HTTP 204 with response body
2. **ALWAYS** return JSON on success
3. **ALWAYS** test frontend parsing

---

## 6. Account Cascade Delete

**Location**: `backend/api/client_routes.py:121`

**Protected Behavior**:
```python
# Delete related instances (cascade will handle experiment logs if configured)
db.query(Instance).filter(Instance.account_id == account.id).delete()
```

**Why Protected**:
- Prevents orphaned instance records
- Must happen BEFORE account deletion
- No automatic rollback

**If You MUST Modify**:
1. Ensure cascade is comprehensive
2. Test with real data
3. Consider backup/restore mechanism
4. Update documentation

---

## 7. AuthGateway Routing Logic

**Location**: `frontend/src/components/AuthGateway.jsx:10-30`

**Protected Behavior**:
- Checks `/client/accounts` on mount
- Redirects to `/onboarding/setup` if empty
- Redirects to `/client` if accounts exist

**Why Protected**:
- Prevents blank dashboard pages
- Prevents infinite redirect loops
- Critical for user experience

**If You MUST Modify**:
1. Test both states (accounts / no accounts)
2. Verify no redirect loops
3. Handle API errors gracefully
4. Update `/scenarios/auth_flow.md`

---

## Forbidden Patterns

### ❌ NEVER Do These

#### 1. Remove Uniqueness Checks
```python
# ❌ FORBIDDEN
# Don't remove this check to "simplify" code
existing = db.query(Account).filter(Account.account_id == aws_id).first()
if existing and existing.user_id != current_user.id:
    raise HTTPException(409, "Conflict")
```

#### 2. Change Encryption Algorithm Without Migration
```python
# ❌ FORBIDDEN
# This breaks all existing encrypted credentials
def encrypt_credential(data):
    return new_algorithm(data)  # Old credentials can't be decrypted!
```

#### 3. Modify Token Expiration Without Testing
```python
# ❌ FORBIDDEN
# This was previously set to 5 minutes (bug)
expires_delta = timedelta(minutes=5)  # Don't change without thorough testing
```

#### 4. Skip Ownership Verification
```python
# ❌ FORBIDDEN
# Don't assume user owns the resource
account = db.query(Account).filter(Account.id == account_id).first()
# MUST verify: account.user_id == current_user.id
```

---

## Safe Modification Zones

### ✅ You CAN Modify These

#### 1. Health Check Logic
**Location**: `backend/utils/component_health_checks.py`
**Why Safe**: Monitoring only, doesn't affect core functionality

#### 2. Polling Interval
**Location**: `frontend/src/components/ClientSetup.jsx:206`
**Why Safe**: UX enhancement, not critical

#### 3. Log Messages
**Location**: Anywhere (logger.info, logger.error)
**Why Safe**: Documentation only

#### 4. UI Styling
**Location**: Frontend className, CSS
**Why Safe**: Visual only

---

## Regression Test Checklist

Before deploying ANY change to protected zones:

- [ ] Read relevant entry in `/progress/fixed_issues_log.md`
- [ ] Understand why previous fix was needed
- [ ] Verify your change doesn't reintroduce bug
- [ ] Test with multiple users (if multi-user relevant)
- [ ] Test error cases
- [ ] Update all metadata files
- [ ] Add regression test if possible

---

## Emergency Rollback Procedures

If a regression is detected:

### Step 1: Immediate Mitigation
```bash
git revert <commit-sha>
git push origin <branch>
```

### Step 2: Documentation
1. Update `/problems/problems_log.md` - Mark as "Reopened"
2. Add new problem entry for regression
3. Update `/progress/fixed_issues_log.md` - DO NOT delete original fix

### Step 3: Root Cause Analysis
1. Why did regression occur?
2. Was regression guard not followed?
3. What additional protection is needed?

### Step 4: Re-Fix
1. Address root cause
2. Add stronger regression guard
3. Add automated test if possible

---

## Regression History

### None Detected (Since Governance)

No regressions have occurred since implementing this governance structure (2025-12-25).

---

_Last Updated: 2025-12-25_
_Authority: HIGHEST - Violation results in STOP_

