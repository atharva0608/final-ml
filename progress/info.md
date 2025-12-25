# Progress Tracking Module

## Purpose

Current system state, fixed issues log, and regression guards.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### progress_tracker.md ⭐ CURRENT STATE
**Purpose**: Current state of the entire system
**Authority**: HIGH
**Status**: CURRENT

**Contents**:
- Overall system status (stable/in-progress/broken)
- Component status for all major modules
- Current work in progress
- Technical debt tracking
- Deployment readiness checklist

**When to Read**:
- Start of any session (understand current state)
- Before making changes (know what's stable/broken)
- Planning new work (understand constraints)

**When to Update**:
- After EVERY commit
- When component status changes
- When new technical debt identified
- When deployment status changes

**Reference**: `/index/recent_changes.md`

### fixed_issues_log.md ⭐ HISTORICAL RECORD
**Purpose**: Complete immutable history of all bug fixes
**Authority**: HIGHEST
**Status**: APPEND-ONLY (never delete entries)

**Contents**:
- All fixed issues with P-YYYY-MM-DD-NNN IDs
- Problem description
- Root cause analysis
- Fix description
- Files changed (with line numbers)
- Impact analysis
- Prevention measures added

**When to Read**:
- Before modifying protected zones
- Understanding why code exists
- Investigating similar bugs
- Before removing "weird" code

**When to Update**:
- IMMEDIATELY after fixing any bug
- When reopening an issue
- When adding regression guards

**⚠️ NEVER DELETE ENTRIES**: This is the permanent historical record

**Reference**: `/progress/regression_guard.md`, `/problems/problems_log.md`

### regression_guard.md ⭐ CRITICAL
**Purpose**: Protected zones and "DO NOT TOUCH" rules
**Authority**: HIGHEST
**Status**: ENFORCED

**Contents**:
- 7 protected zones with explicit rules
- Authentication token generation
- AWS account uniqueness checks
- Credential encryption
- Discovery worker status transitions
- DELETE endpoint status codes
- Account cascade deletes
- AuthGateway routing logic

**When to Read**:
- **BEFORE** modifying any existing code
- When encountering "strange" code
- Before "simplifying" or "cleaning up" code

**When to Update**:
- When fixing a bug (add new protected zone)
- When identifying regression risk
- After security fixes

**⚠️ VIOLATION RESULTS IN STOP**: Do not proceed if regression guard violated

**Reference**: `/instructions/master_rules.md`, `/progress/fixed_issues_log.md`

---

## Usage Workflow

### At Session Start
```
1. Read progress_tracker.md
   ↓
2. Understand current system state
   ↓
3. Check component statuses
   ↓
4. Note any in-progress work
```

### Before Making Changes
```
1. Read regression_guard.md
   ↓
2. Check if code is protected
   ↓
3. If protected → Read fixed_issues_log.md
   ↓
4. Understand why protection exists
   ↓
5. Proceed with extreme caution or ask for approval
```

### After Fixing Bug
```
1. Add entry to fixed_issues_log.md
   ↓
2. Update progress_tracker.md (component status)
   ↓
3. Add regression guard (if needed)
   ↓
4. Update problems_log.md (mark as fixed)
   ↓
5. Update index/recent_changes.md
```

---

## Dependencies

### Depends On:
- Git history (for tracking changes)
- Problem IDs from problems_log.md
- Feature index (for component names)

### Depended By:
- **CRITICAL**: All LLM sessions (understand state)
- All developers (know what's stable)
- Bug fix workflow
- Change impact analysis

**Impact Radius**: CRITICAL (affects all development)

---

## Recent Changes

### 2025-12-25: Initial Progress Structure Creation
**Files Created**: 3 progress files
**Reason**: Establish engineering memory and regression prevention
**Impact**: Provides persistent context across LLM sessions
**Reference**: Initial governance structure

---

## File Relationships

```
problems_log.md (All problems discovered)
   ↓
[Bug Fix Process]
   ↓
fixed_issues_log.md (How it was fixed)
   ↓
regression_guard.md (Prevent regression)
   ↓
progress_tracker.md (Current state)
```

---

## Authority Hierarchy

1. **regression_guard.md** - HIGHEST (must follow)
2. **fixed_issues_log.md** - HIGHEST (never delete)
3. **progress_tracker.md** - HIGH (current source of truth)

In case of conflict: regression_guard > fixed_issues > progress_tracker

---

## Known Issues

### None

Progress module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Engineering memory_
