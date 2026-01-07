# Update Policy

## Purpose

Defines **what must be updated** and **when** to maintain system integrity.

---

## The Metadata Update Contract

### Core Rule

> **"Every code change MUST update at least 3 metadata files."**

Why? Because code without documentation is **dead knowledge** to future LLM sessions.

---

## Mandatory Updates by Change Type

### Bug Fix Updates

When fixing a bug, **MUST** update:

#### 1. Module `info.md` (Local Contract)
Location: Same directory as modified file

Add to "Recent Changes" section:
```markdown
## Recent Changes

### 2025-12-25: Fixed P-2025-12-25-001 - [Brief Title]
**Problem**: [One sentence description]
**Solution**: [One sentence what changed]
**Files Modified**:
- `file1.py:123-145`
- `file2.js:67-89`

**Behavior Change**:
- Before: [What happened]
- After: [What happens now]

**Verification**: Run `pytest tests/test_module.py::test_case`
**Related Scenario**: `/scenarios/auth_flow.md#login-failure`
```

#### 2. `/progress/fixed_issues_log.md` (Global Fix History)
Add complete entry:
```markdown
## P-2025-12-25-001: [Full Problem Title]

**Date**: 2025-12-25
**Fixed By**: LLM Session [ID]

**Root Cause**:
[Detailed explanation of why bug occurred]

**Files Changed**:
- `backend/api/auth.py:123-145` - Fixed token validation
- `frontend/src/services/api.js:67-89` - Updated error handling

**Behavior Change**:
**Before**: Login token expired after 5 minutes
**After**: Login token expires after 24 hours

**Verification Method**:
1. Login as test user
2. Wait 6 minutes
3. Verify token still valid
4. Wait 25 hours
5. Verify token expired

**Impact Radius**:
- Authentication system
- User sessions
- API middleware

**Related Scenarios**:
- `/scenarios/auth_flow.md#token-refresh`

**Dependencies Affected**:
- None (isolated change)

**Rollback Instructions**:
If this causes issues, revert commits: [sha1], [sha2]
```

#### 3. `/index/recent_changes.md` (Timeline)
Add brief entry:
```markdown
## 2025-12-25

### P-2025-12-25-001: Fixed token expiration bug
**Module**: backend/api/auth
**Impact**: Authentication system
**Files**: 2 files changed
**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`
```

#### 4. `/problems/problems_log.md` (Status Update)
Update problem status:
```markdown
### P-2025-12-25-001: Login Token Expires Too Soon
**Status**: ✅ Fixed
**Fixed Date**: 2025-12-25
**Fix Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`
```

#### 5. `/scenarios/` (If Behavior Changed)
Update relevant scenario:
```markdown
## Token Lifecycle

### As of 2025-12-25 (P-2025-12-25-001 fix):
- Token expiration: **24 hours** (was 5 minutes)
- Refresh window: 1 hour before expiration
- Auto-refresh: Enabled
```

---

### Feature Implementation Updates

When adding a feature, **MUST** update:

#### 1. Module `info.md`
Add to "Features" section:
```markdown
## Features

### Account Management
**Endpoints**:
- `GET /client/accounts` - List connected accounts
- `DELETE /client/accounts/{id}` - Disconnect account

**Added**: 2025-12-25
**Scenario**: `/scenarios/account_management_flow.md`
```

#### 2. `/index/feature_index.md`
Add complete feature entry:
```markdown
### Account Management (Multi-Account Support)

**Module**: backend/api/client_routes
**Added**: 2025-12-25

**API Endpoints**:
- `GET /client/accounts` - List accounts
- `DELETE /client/accounts/{id}` - Delete account

**Database Tables**:
- `accounts` (existing, extended)

**Frontend Components**:
- `ClientSetup.jsx` (modified)
- `AuthGateway.jsx` (new)

**Dependencies**:
- Requires: Authentication system
- Required by: Dashboard, Profile

**Scenario**: `/scenarios/account_management_flow.md`

**Key Functions**:
- `get_connected_accounts()` - backend/api/client_routes.py:42
- `disconnect_account()` - backend/api/client_routes.py:85

**Business Logic**:
Users can connect multiple AWS accounts. Each account is validated globally to prevent conflicts.
```

#### 3. `/index/dependency_index.md`
Update dependency graph:
```markdown
### Account Management
**Depends On**:
- Authentication (`/api/auth`)
- Database Models (`Account`, `Instance`)

**Depended By**:
- Client Dashboard
- Profile View
- AuthGateway routing

**Impact Radius**: High (affects all client flows)
```

#### 4. `/scenarios/account_management_flow.md` (New File)
Create detailed scenario:
```markdown
# Account Management Flow

## User Story
As a client, I want to connect multiple AWS accounts...

## Happy Path
1. User logs in
2. AuthGateway checks `/client/accounts`
3. If accounts exist → redirect to /client
4. If no accounts → redirect to /onboarding/setup

## Edge Cases
1. AWS account already connected to different user → HTTP 409
2. Network failure during deletion → Rollback transaction

## Security
- User ownership verification on all operations
- Global uniqueness check for AWS account IDs

## Testing
[Detailed test scenarios]
```

#### 5. `/index/recent_changes.md`
```markdown
## 2025-12-25

### Feature: Multi-Account Support
**Module**: backend/api + frontend
**Impact**: All client flows
**Files**: 12 files changed
**Reference**: `/index/feature_index.md#account-management`
```

---

### Refactoring Updates

When refactoring, **MUST** update:

#### 1. Module `info.md`
```markdown
## Recent Changes

### 2025-12-25: Refactored authentication middleware
**Reason**: Reduce code duplication
**Changes**: Consolidated 3 auth functions into 1
**Files**: `auth.py`, `middleware.py`
**Behavior**: No change (refactor only)
**Tests**: All tests still pass
```

#### 2. `/index/dependency_index.md`
Update if dependencies changed

#### 3. `/index/recent_changes.md`
```markdown
### Refactor: Authentication middleware consolidation
**Impact**: Internal only (no behavior change)
**Files**: 2 files
```

---

## Update Timing

### When to Update

**IMMEDIATELY** after code change:
- Module `info.md`
- `/progress/fixed_issues_log.md`
- `/index/recent_changes.md`

**BEFORE** committing:
- All metadata files
- All cross-references
- All affected scenarios

**BEFORE** pushing:
- Verify all links work
- Verify all Problem IDs reference correctly

---

## Update Verification Checklist

Before committing, verify:

- [ ] Module `info.md` updated
- [ ] `/progress/fixed_issues_log.md` has entry (if fix)
- [ ] `/index/recent_changes.md` has entry
- [ ] `/problems/problems_log.md` status updated (if fix)
- [ ] `/index/feature_index.md` updated (if feature)
- [ ] `/index/dependency_index.md` updated (if dependencies changed)
- [ ] `/scenarios/` updated (if behavior changed)
- [ ] All cross-references are correct
- [ ] All links are valid
- [ ] Problem IDs follow format (P-YYYY-MM-DD-NNN)

**If ANY checkbox is unchecked, DO NOT COMMIT.**

---

## Update Conflicts

### If Metadata Contradicts Code

**Resolution Order**:
1. Check `/instructions/master_rules.md` - What should be true?
2. Update code to match master rules
3. Update metadata to match corrected code

### If Multiple Metadata Files Conflict

**Authority Hierarchy**:
1. `/instructions/` (highest)
2. `/progress/fixed_issues_log.md`
3. `/index/`
4. Module `info.md`
5. Code comments (lowest)

Align all files with highest authority source.

---

## Automation Helpers

### Update Templates

Templates available in `/instructions/templates/`:
- `info_md_template.md`
- `fix_log_template.md`
- `scenario_template.md`

### Verification Scripts

```bash
# Check all metadata files are updated
./scripts/verify_metadata.sh

# Find broken cross-references
./scripts/check_links.sh

# Validate Problem ID format
./scripts/validate_problem_ids.sh
```

---

## Emergency Updates

If you discover metadata is **severely** out of sync:

1. **STOP** all development
2. Document gap in `/problems/problems_log.md`
3. Create sync task
4. Update all metadata before proceeding
5. Add entry to `/progress/regression_guard.md` to prevent recurrence

**Never build on incorrect foundation.**

---

_Last Updated: 2025-12-25_
_Authority Level: HIGHEST_
