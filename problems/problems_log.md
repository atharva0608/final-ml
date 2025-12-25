# Problems Log

## Purpose

Immutable ledger of all problems discovered. **NEVER delete entries.**

**Last Updated**: 2025-12-25

---

## Problem ID Format

`P-YYYY-MM-DD-NNN`

Example: `P-2025-12-25-001`

---

## Active Problems

### None

All known problems have been fixed.

---

## Fixed Problems

### P-2025-12-25-003: Delete Account Returns HTTP 204 Without Body

**Status**: ✅ Fixed
**Reported**: 2025-12-25
**Fixed**: 2025-12-25
**Severity**: MEDIUM

**Description**:
DELETE `/client/accounts/{account_id}` endpoint was not explicitly setting status code, causing FastAPI to return HTTP 204 (No Content). HTTP 204 forbids response bodies, but the function was returning JSON. This caused frontend to receive network/parsing errors.

**Observed Behavior**:
- Backend successfully deleted account
- Frontend received network error: "Unexpected end of JSON"
- User saw error message despite successful deletion

**Expected Behavior**:
- DELETE returns HTTP 200 with JSON confirmation
- Frontend can parse success message
- User sees success confirmation

**Root Cause**:
Missing explicit `status_code` parameter in route decorator

**Fix Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-003`

---

### P-2025-12-25-002: Dashboard Shows Zero Data After Fresh Connection

**Status**: ✅ Fixed
**Reported**: 2025-12-25
**Fixed**: 2025-12-25
**Severity**: HIGH

**Description**:
After connecting a new AWS account and completing discovery, the dashboard displayed "$0 Cost", "0% Usage", and no metrics. Data would appear only after midnight cron job ran.

**Observed Behavior**:
- User connects AWS account
- Discovery completes successfully
- Dashboard loads but shows all zeros
- User thinks system is broken
- Data populates after midnight

**Expected Behavior**:
- Dashboard shows live data immediately after discovery
- Metrics populate within seconds of completion
- User sees value immediately

**Root Cause**:
Health check system only triggered by cron job (midnight). Discovery worker completed but didn't trigger metric calculation.

**Fix Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-002`

---

### P-2025-12-25-001: AWS Account Takeover Vulnerability

**Status**: ✅ Fixed
**Reported**: 2025-12-25
**Fixed**: 2025-12-25
**Severity**: CRITICAL (Security)

**Description**:
CloudFormation onboarding flow lacked global uniqueness check for AWS Account IDs. A malicious user could connect another user's AWS account, potentially gaining access to their resources.

**Observed Behavior**:
- User A connects AWS Account X via credentials
- User B connects same AWS Account X via CloudFormation
- Both users can access same AWS resources
- Data mixing / security breach

**Expected Behavior**:
- AWS Account IDs are globally unique
- Second connection attempt returns HTTP 409 Conflict
- Only original user retains access

**Root Cause**:
Inconsistent security checks between connection methods. Credentials flow had uniqueness check, CloudFormation flow didn't.

**Fix Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`

---

## Historical Problems (Pre-Governance)

### Session Token Expiration (2025-11-26)

**Status**: ✅ Fixed
**Severity**: HIGH

**Description**: Login tokens expired after 5 minutes instead of 24 hours
**Fix**: Updated token expiration in auth.py
**Reference**: `/docs/legacy/fixes/BACKEND_FIXES_2025-11-26.md`

### Client Status Display (2025-11-25)

**Status**: ✅ Fixed
**Severity**: MEDIUM

**Description**: New client account status not displaying
**Fix**: Updated dashboard rendering logic
**Reference**: `/docs/legacy/fixes/FIX_SUMMARY_2025-11-25.md`

### Session Cookie Handling (2025-11-23)

**Status**: ✅ Fixed
**Severity**: MEDIUM

**Description**: Session cookies not persisting correctly
**Fix**: Updated SameSite and secure flags
**Reference**: `/docs/legacy/fixes/SESSION_FIXES_2025-11-23.md`

---

## Reopened Problems

### None

No problems have regressed since fixes were applied.

---

## Won't Fix / By Design

### None currently

---

## Problem Statistics

**Total Problems Logged**: 6 (3 post-governance + 3 historical)
**Fixed**: 6 (100%)
**Active**: 0
**Reopened**: 0
**Won't Fix**: 0

**By Severity**:
- CRITICAL: 1 (security)
- HIGH: 2 (user experience)
- MEDIUM: 3 (functional issues)
- LOW: 0

**By Category**:
- Security: 1
- Protocol/API: 1
- Data/Metrics: 1
- Authentication: 2
- UI/Display: 1

---

## Problem Discovery Sources

1. Code analysis - 3 problems
2. User reports - 0 (hypothetical)
3. Automated tests - 0 (no CI yet)
4. Security review - 1 problem

---

## Prevention Measures

### Implemented

1. **Governance Structure** (2025-12-25)
   - Prevents duplicate implementations
   - Forces metadata updates
   - Enforces regression guards

2. **Global Uniqueness Checks** (2025-12-25)
   - AWS Account IDs
   - User emails
   - Usernames

3. **Explicit Status Codes** (2025-12-25)
   - All routes declare status codes
   - No implicit defaults

### Planned

1. **Automated Tests**
   - Regression test suite
   - Integration tests
   - Security tests

2. **CI/CD Pipeline**
   - Automated testing
   - Linting
   - Security scanning

---

_Last Updated: 2025-12-25_
_Authority: HIGHEST (never delete entries)_
