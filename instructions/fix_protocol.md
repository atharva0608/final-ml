# Fix Protocol

## Purpose

This document defines the **mandatory step-by-step process** for fixing bugs and implementing features.

---

## Bug Fix Protocol

### Step 1: Problem Identification

1. Read the problem description from `/problems/problems_log.md`
2. Verify the problem ID (format: `P-YYYY-MM-DD-NNN`)
3. Check if problem is marked as `Fixed` or `Reopened`
4. If `Fixed`, **STOP** and investigate why it reoccurred

### Step 2: Pre-Fix Verification

1. Check `/progress/fixed_issues_log.md`:
   - Has this been fixed before?
   - What was the previous solution?
   - Why might it have regressed?

2. Check `/progress/regression_guard.md`:
   - Are there any "Do Not Touch" zones related to this?
   - What are the constraints?

3. Read relevant `info.md` in affected modules:
   - Understand current implementation
   - Identify dependencies

### Step 3: Root Cause Analysis

1. Identify the **actual** root cause (not just symptoms)
2. Document your findings in `/problems/problems_log.md`:
   ```
   ### Problem ID: P-2025-12-25-001
   **Root Cause**: [Description]
   **Affected Files**: [List]
   **Impact Radius**: [Components affected]
   ```

### Step 4: Solution Design

1. Check `/index/feature_index.md` for existing similar functionality
2. Design solution that:
   - Fixes the root cause
   - Doesn't break existing functionality
   - Follows existing patterns
   - Minimizes change radius

3. Verify solution against `/scenarios/` flows

### Step 5: Implementation

1. Apply the fix
2. **DO NOT**:
   - Create duplicate functions
   - Override existing fixes
   - Introduce new dependencies without documentation

3. **DO**:
   - Follow existing code patterns
   - Add comments explaining "why", not "what"
   - Handle edge cases

### Step 6: Verification

1. Test the fix locally
2. Verify related functionality still works
3. Check `/scenarios/` flows are not broken

### Step 7: Documentation (MANDATORY)

Update ALL of the following:

#### 7.1 Module Info
Update `info.md` in affected module:
```markdown
## Recent Changes

### 2025-12-25: Fixed P-2025-12-25-001
- **Problem**: [Brief description]
- **Solution**: [What was changed]
- **Files Modified**: [List]
- **Verification**: [How to verify fix]
```

#### 7.2 Fixed Issues Log
Add entry to `/progress/fixed_issues_log.md`:
```markdown
## P-2025-12-25-001: [Problem Title]
**Date**: 2025-12-25
**Fixed By**: LLM Session [ID]
**Root Cause**: [Detailed explanation]
**Files Changed**:
- `path/to/file1.py`
- `path/to/file2.js`

**Behavior Change**:
- Before: [What happened]
- After: [What happens now]

**Verification Method**:
1. [Step 1]
2. [Step 2]

**Impact Radius**: [List of affected components]
**Related Scenarios**: [Link to scenarios/]
```

#### 7.3 Recent Changes
Update `/index/recent_changes.md`:
```markdown
### 2025-12-25
- **P-2025-12-25-001**: Fixed [brief]
  - Files: [list]
  - Impact: [brief]
```

#### 7.4 Problems Log
Update status in `/problems/problems_log.md`:
```markdown
### P-2025-12-25-001: [Title]
**Status**: Fixed
**Fixed Date**: 2025-12-25
**Fix Reference**: See `/progress/fixed_issues_log.md` entry
```

#### 7.5 Scenarios (if behavior changed)
Update relevant files in `/scenarios/` if user-facing behavior changed

### Step 8: Commit

1. Commit with format:
   ```
   fix(module): P-2025-12-25-001 - [Brief description]

   Root cause: [Summary]
   Solution: [Summary]
   Files: [List]

   References:
   - /problems/problems_log.md#P-2025-12-25-001
   - /progress/fixed_issues_log.md#P-2025-12-25-001
   ```

2. Push to feature branch (never directly to main)

---

## Feature Implementation Protocol

### Step 1: Requirement Analysis

1. Read the feature request
2. Check `/index/feature_index.md`:
   - Does similar functionality exist?
   - Can we extend existing features?

3. Check `/scenarios/` for related flows

### Step 2: Design

1. Design API/schema/UI following existing patterns
2. Document expected behavior in `/scenarios/`
3. Identify all affected modules

### Step 3: Implementation

1. Follow same implementation rules as bug fixes
2. Add comprehensive comments
3. Update all relevant `info.md` files

### Step 4: Documentation

1. Add feature to `/index/feature_index.md`:
   ```markdown
   ### [Feature Name]
   **Module**: [module-name]
   **API Endpoints**: [list]
   **Database Tables**: [list]
   **Dependencies**: [list]
   **Scenario**: See `/scenarios/[name]_flow.md`
   ```

2. Create scenario file in `/scenarios/`
3. Update module `info.md`
4. Update `/index/recent_changes.md`

### Step 5: Testing & Commit

Same as bug fix protocol

---

## Rollback Protocol

If a fix causes issues:

1. **DO NOT DELETE** the fix log entry
2. Update `/problems/problems_log.md` status to `Reopened`
3. Add new problem entry for the regression
4. Document what went wrong in `/progress/regression_guard.md`

---

_Last Updated: 2025-12-25_
_Authority Level: HIGHEST_
