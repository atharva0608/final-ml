# Fix Report - 2025-12-22

## Backend Issues Identified & Fixed

### 1. "Death Loop" & Backend Crash
- **Error**: Circular import between `system_logger.py` and `component_health_checks.py`.
- **Fix**: Implemented `ComponentHealthEvaluator` class in `component_health_checks.py` to break the dependency and provide the expected interface.

### 2. Orphaned Users (Signup Bug)
- **Error**: User signup created a `User` record but no `Account` record, causing dashboard failures.
- **Fix**: Updated `api/auth.py` to automatically create a default `Account` for every new user.

### 3. Background Worker Silence
- **Error**: Exceptions in `discovery_worker.py` could be swallowed or fail to update the DB status properly.
- **Fix**: Added robust error handling with explicit DB rollbacks and fresh session creation for error logging.

## Frontend Bug Fixes

### 4. `createUser` TypeError
- **Error**: `TypeError: $e.createUser is not a function` when adding clients.
- **Root Cause**: `ClientManagement.jsx` calls `api.createUser`, but `services/api.js` only exports `createClient`.
- **Fix**: Updated `services/api.js` to export `createUser` (alias for `createClient`).

### 5. 403 Forbidden on Health Check
- **Error**: Client users see 403 errors for `/api/v1/admin/health/overview`.
- **Root Cause**: The frontend attempts to fetch system overview stats for all users, but the endpoint is Admin-only.
- **Fix**: Modified `LiveOperations.jsx` to respect `clientMode` and skip Admin API calls.

## Lab Mode & Model Workflow Features

### 6. Actions Cleanup (User Feedback)
- **Requirement**: "Accept" and "Test" should be simple. No popups. Dropdown selection is already available in instance details.
- **Fix**:
    - **Removed "Test" Modal**: The "Accept & Test" button is now just **"Accept"**.
    - **Accept Logic**: Clicking "Accept" provides feedback (alert) that the model is available for lab testing, but does not force a modal.
    - **Availability**: "Candidate" models remain available in the instance details dropdown automatically.

### 7. Global Controls - Active Model Logic
- **Requirement**:
    - Show the *current* active production model explicitly.
    - **Granular Control**: Active model display should NOT update until "Apply Changes" is clicked.
    - **Visibility**: Graduated models should NOT appear in the dropdown until "Enable for Prod" is clicked in the Lab.
- **Fix**:
    - **Current Active Model Block**: Added a highlighted block showing the real active model (Name, Version, ID).
    - **Pending State**: The dropdown now controls a local "pending" selection. The "Current Active Model" block does not change until you click **Apply Changes**.
    - **Dropdown Filtering**: The dropdown only lists models that have been explicitly **Enabled**.

## Client Dashboard Refinement

### 9. Unified Dashboard Structure
- **Requirement**: Clients should see a dashboard similar to Admin's "Node Fleet" but scoped to their resources, plus a "Cloud Connect" section.
- **Fix**:
    - **Dashboard Layout**: Updated sidebar for Clients to show:
        1.  **Client Dashboard** (Overview of resources).
        2.  **Cloud Connect** (Onboarding).
        3.  **Profile** (Settings).
    - **NodeFleet Integration**: Modified `NodeFleet.jsx` to support a `clientMode`.
        - It now renders the specific client's detail view directly (skipping the "All Clients" list).
        - It uses the logged-in client's data instead of fetching all clients.
    - **App Routing**: Wired up `App.jsx` to direct the "dashboard" view to this Client-Scoped Node Fleet and "connect" to the Onboarding wizard.

### 10. Strict Model Lifecycle Enforcement (New Feature)
- **Requirement**: "Upload -> Candidate -> Accept -> Testing -> Graduate -> Enable -> Production" workflow with strict visibility gates.
- **Fix**:
    - **New Statuses**: Added `TESTING` and `ENABLED` to Backend Enum.
    - **Routes**: Added `accept` and `enable` endpoints to `lab.py`.
    - **Governance UI**: "Accept" moves Candidate -> Testing.
    - **Experiments UI**: Testing models show "Graduate". Graduated models show "Enable".
    - **Lab Controls**: Dropdowns filter out Candidates (must be accepted).
    - **Prod Controls**: Dropdowns filter out Graduated (must be enabled).

### 11. Client Dashboard Robustness (Crash Fixes)
- **Error**: `TypeError: e.map is not a function` in "Unregistered Instances".
- **Root Cause**: Backend API returns `{ instances: [...] }` object, but Frontend expected an array directly. Also, strict typing issues where state might default to object.
- **Fix**:
    - **Data Parsing**: Corrected API response handling to extract `data.instances`.
    - **Defensive Coding**: Added `Array.isArray()` checks before all `.map()` operations in `NodeFleet.jsx` (Clusters and Unregistered tabs).
    - **Property Mapping**: Fixed `snake_case` vs `camelCase` mismatches for `nodeCount` and `instanceType`.

### 12. Activate Model 404 Guard & Controls Repair
- **Problem**: clicking "Apply Changes" or external triggers could invoke `PUT /lab/models//activate` (empty ID), causing a 404 crash.
- **Fix**:
    - **Frontend Guard**: Added `if (!modelId) return;` to `setActiveProdModelId` in `ModelContext.jsx`, preventing invalid API calls at the source.
    - **UI Repair**: Overwrote `Controls.jsx` to fix corruption and ensure the "Apply Changes" button is disabled when no model valid is selected.
    - **Verification**: Code confirms the guard is present.
