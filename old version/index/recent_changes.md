# Recent Changes

## Purpose

Chronological timeline of all code changes for quick reference.

**Last Updated**: 2025-12-26

---

## 2025-12-26

### Feature: CSV Cost Export for Financial Reporting

**Commit**: TBD
**Module**: backend/api, frontend/src/services, frontend/src/components
**Impact**: Cost data analysis, financial reporting, external integrations
**Files**: 3 files modified, 3 documentation files updated

**Changes**:
Added CSV export functionality to export last 30 days of cost optimization data:

**Backend**:
- Added `GET /client/costs/export?format=csv` endpoint in `client_routes.py`
- Queries `experiment_logs` + `instances` tables (join)
- Filters last 30 days of cost data
- Generates CSV in-memory using `io.StringIO`
- Returns StreamingResponse with `text/csv` media type
- Includes summary row with total monthly projected savings
- Calculates monthly savings: hourly_savings × 730 hours/month

**Frontend**:
- Added `exportCostsCsv()` method to ApiClient in `services/api.js`
- Handles file download via blob creation and temporary DOM link
- Extracts filename from Content-Disposition header
- Default filename: `cost_savings_export_YYYY-MM-DD.csv`
- Added "Export CSV" button in NodeFleet.jsx Cost Savings Overview section
- Button with Download icon (lucide-react)
- Shows success/error alerts

**CSV Structure**:
```csv
Date,Instance ID,Instance Type,Availability Zone,Old Spot Price,New Spot Price,Hourly Savings,Monthly Projected,Decision,Reason
2025-12-26 10:30:00,i-abc123,t3.medium,us-east-1a,$0.0416,$0.0312,$0.0104,$7.59,SWITCH,Cost savings
...
TOTAL,,,,,,,$1234.56,,
```

**Files Modified**:
- `backend/api/client_routes.py` - Added CSV export endpoint (lines 383-531)
- `frontend/src/services/api.js` - Added exportCostsCsv() method (lines 150-185)
- `frontend/src/components/NodeFleet.jsx` - Added Export CSV button (lines 584-601)

**Documentation Updated**:
- `backend/api/info.md` - Added endpoint documentation
- `frontend/src/components/info.md` - Added button documentation
- `index/feature_index.md` - Added CSV Cost Export feature entry

**Use Cases**:
- Financial reporting and audit trails
- External analysis in Excel/Google Sheets
- Historical cost tracking
- Budget planning and forecasting

**Security**:
- Requires JWT authentication
- Only exports data for current user's accounts
- Backend validates ownership via account_id filter

**Reference**: New feature - CSV Cost Export

---

### Fix: Missing API Methods Breaking Model Upload (P-2025-12-26-007)

**Commit**: TBD
**Module**: frontend/src/services
**Impact**: Model upload, model governance, system monitoring
**Files**: 1 file modified

**Changes**:
Added 9 specialized methods to ApiClient class to fix TypeError crashes:
- `getModels()` - Fetch AI models list from `/v1/ai/list`
- `uploadModel(formData)` - Upload model files to `/v1/ai/upload`
- `acceptModel()`, `graduateModel()`, `enableModel()`, `activateModel()`, `rejectModel()` - Model governance
- `getSystemOverview()` - Fetch system health from `/v1/admin/health/overview`
- `getComponentLogs()` - Fetch component logs

**Console Errors Fixed**:
- `TypeError: ue.getSystemOverview is not a function`
- `TypeError: ue.getModels is not a function`
- `TypeError: ue.uploadModel is not a function`

**File Modified**:
- `frontend/src/services/api.js` - Added specialized methods to ApiClient class

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-26-007`

---

### Fix: Login Loop and TypeError Crashes (P-2025-12-26-004, 005, 006)

**Commit**: TBD
**Module**: frontend/src/services, frontend/src/components
**Impact**: All frontend components, API client, authentication flows
**Files**: 4 files changed (2 deleted, 2 modified)

**Changes**:
Fixed three interconnected frontend issues causing login loops and TypeError crashes:

1. **P-2025-12-26-006**: AuthGateway endpoint path fixed
   - Changed `/client/accounts` → `/v1/client/accounts`
   - Prevents 404 errors and login loops

2. **P-2025-12-26-005**: API client rewritten with axios-style interface
   - Added `.get()`, `.post()`, `.put()`, `.delete()` methods
   - Fixes `TypeError: de.get is not a function`
   - Maintains backward compatibility with named exports

3. **P-2025-12-26-004**: Removed conflicting API files
   - Deleted `api.jsx` and `apiClient.jsx`
   - Single source of truth: `api.js`
   - Consistent module resolution

**Files Modified**:
- `frontend/src/services/api.js` - Complete rewrite with axios interface
- `frontend/src/components/AuthGateway.jsx` - Fixed endpoint path
- `frontend/src/services/api.jsx` - DELETED
- `frontend/src/services/apiClient.jsx` - DELETED

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-26-006`

---

### Fix: Status Filter Excludes Pending Accounts (P-2025-12-26-003)

**Commit**: TBD
**Module**: backend/api
**Impact**: Account listing for all users, admin-created user experience
**Files**: 1 file changed

**Changes**:
Fixed GET `/client/accounts` to return ALL accounts regardless of status. Previously filtered out "pending" accounts, causing admin-created users to see empty account lists and onboarding forms even when placeholder accounts existed.

**Code Change**:
Removed status filter from client_routes.py:54 - now returns all accounts for user

**Investigation Results** (3 reported problems):
1. **P-2025-12-26-001: Zombie Database** ⚠️ Environment issue - schema definition is correct, user needs DB migration
2. **P-2025-12-26-002: Partial Commit Bug** ❌ Not a bug - code correctly uses single commit
3. **P-2025-12-26-003: Status Filter** ✅ FIXED - removed restrictive status filter

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-26-003`

---

### Investigation: UX Problem Reports - All Invalid or Already Fixed

**Session**: claude/aws-dual-mode-connectivity-fvlS3
**Module**: Investigation only (no code changes)
**Impact**: Problem intake process validation

**Investigation Results**:
Investigated 5 UX problems reported in `/problems/new_problem`. All were found to be invalid or already fixed in recent commits:

1. **"Orphan User" Problem** ✅ ALREADY FIXED
   - Admin user creation already creates placeholder Account (admin.py:725-744)
   - Fix includes comment: "CRITICAL FIX: Create placeholder account for client users to prevent 'Orphan' state"

2. **"Amnesiac Cloud Connect"** ✅ FEATURE EXISTS
   - ClientSetup already fetches accounts on mount (ClientSetup.jsx:299-301)
   - Proper loading states and error handling in place

3. **"Missing Feedback"** ✅ FEATURE EXISTS
   - Comprehensive connected accounts UI exists (ClientSetup.jsx:332-429)
   - Color-coded status badges, visual feedback panels, progress indicators

4. **"No Disconnect Option"** ✅ FEATURE EXISTS
   - DELETE endpoint: client_routes.py:84-119
   - Frontend handler: ClientSetup.jsx:270-288
   - UI button: ClientSetup.jsx:406-412
   - Fixed in P-2025-12-25-003 (returns HTTP 200)

5. **"UX Verdict"** ❌ BASED ON INVALID PROBLEMS

**Action Taken**: Removed invalid problems from `/problems/new_problem` and documented investigation findings.

**Reference**: All features documented in `/index/feature_index.md`

---

## 2025-12-25

### Fix: Critical bug fixes for delete endpoint and discovery workflow

**Commit**: 02d9f16
**Module**: backend/api, backend/workers
**Impact**: Delete operations, Dashboard data population
**Files**: 2 files changed

**Changes**:
1. DELETE `/client/accounts/{account_id}` now returns HTTP 200 (was implicit 204)
2. Discovery worker triggers health checks immediately after completion
3. Verified account takeover protection in both connection flows

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-003`

---

### Feature: Comprehensive Client Experience (CX) improvements

**Commit**: 8ee220c
**Module**: backend/api, frontend
**Impact**: All client workflows
**Files**: 3 files changed

**Changes**:
1. Added DELETE `/client/accounts/{account_id}` endpoint
2. Added global uniqueness check for AWS Account IDs (CloudFormation flow)
3. Implemented disconnect functionality in ClientSetup
4. Added live feedback polling (3-second interval)
5. Dashboard returns `setup_required` flag for empty state

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-002`

---

### Feature: Multi-account support with persistent connected state

**Commit**: 4e6e848
**Module**: backend/api, frontend
**Impact**: All client flows
**Files**: 4 files changed

**Changes**:
1. Created GET `/client/accounts` endpoint
2. Created AuthGateway component for smart routing
3. Updated App.jsx to use AuthGateway
4. Updated ClientSetup to support multiple accounts
5. Added account list view with "Add Account" button

**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-001`

---

## 2025-11-26

### Fix: Backend session and authentication issues

**Module**: backend/api/auth
**Files**: auth.py, middleware

**Changes**:
- Fixed session expiration bug
- Updated token validation logic

**Reference**: `/docs/legacy/fixes/BACKEND_FIXES_2025-11-26.md`

---

## 2025-11-25

### Fix: Client status and display issues

**Module**: backend/api, frontend
**Files**: Multiple

**Changes**:
- Fixed new client status not displaying correctly
- Updated dashboard rendering logic

**Reference**: `/docs/legacy/fixes/FIX_SUMMARY_2025-11-25.md`

---

## 2025-11-23

### Fix: Session management fixes

**Module**: backend/api
**Files**: auth.py, session management

**Changes**:
- Fixed session cookie handling
- Updated session expiration logic

**Reference**: `/docs/legacy/fixes/SESSION_FIXES_2025-11-23.md`

---

## Change Categories

### Severity Levels

**CRITICAL**: Breaking changes, security fixes, data loss prevention
**HIGH**: Major features, API changes, schema changes
**MEDIUM**: Feature enhancements, bug fixes
**LOW**: Refactoring, documentation, minor improvements

### Recent Breakdown

- **CRITICAL**: 1 change (delete endpoint HTTP protocol fix)
- **HIGH**: 3 changes (multi-account support, CX improvements, CSV export)
- **MEDIUM**: 3 changes (historical fixes)
- **LOW**: 0 changes

---

## Impact Summary (Last 30 Days)

### Backend API Changes
- 4 new endpoints added (including CSV export)
- 1 endpoint modified (status code fix)
- 0 endpoints deprecated

### Frontend Changes
- 1 new component (AuthGateway)
- 3 components significantly updated (ClientSetup, App.jsx, NodeFleet)
- 0 components removed
- 1 new API method (exportCostsCsv)

### Database Schema
- 0 tables added
- 0 tables modified
- 0 tables removed

### Workers/Background Tasks
- 1 worker modified (discovery_worker - health check trigger)
- 0 workers added
- 0 workers removed

---

## Breaking Changes (Last 30 Days)

### None

All changes have been backward compatible.

---

## Deprecated Features (Pending Removal)

### None currently

---

## Upcoming Changes (Planned)

### Pending Implementation

1. **Feature**: Email notifications for discovery completion
   - Status: Planned
   - Priority: LOW
   - Estimated: Q1 2026

2. **Feature**: Multi-region support for discovery
   - Status: Planned
   - Priority: MEDIUM
   - Estimated: Q1 2026

3. **Refactor**: Move polling logic to React Query
   - Status: Planned
   - Priority: LOW
   - Estimated: Q2 2026

---

## Rollback History

### None

No changes have been rolled back in the last 30 days.

---

_Last Updated: 2025-12-25_
_Updates: Automatic on every commit_
