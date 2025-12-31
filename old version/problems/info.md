# Problems Tracking Module

## Purpose

Immutable ledger of all problems discovered, active, and fixed.

**Last Updated**: 2025-12-25
**Authority Level**: HIGHEST

---

## Files

### problems_log.md ⭐ IMMUTABLE LEDGER
**Purpose**: Complete record of all problems ever discovered
**Authority**: HIGHEST
**Status**: APPEND-ONLY (NEVER delete entries)

**Contents**:
- **Active Problems** - Currently unfixed issues
- **Fixed Problems** - Resolved issues with fix references
- **Reopened Problems** - Regressions
- **Won't Fix / By Design** - Intentional behaviors
- **Problem Statistics** - Metrics and trends

**Problem ID Format**: `P-YYYY-MM-DD-NNN`
- Example: `P-2025-12-25-001`
- Chronological and unique
- Never reused

**Entry Structure**:
```markdown
### P-YYYY-MM-DD-NNN: [Problem Title]

**Status**: 🔴 Active / ✅ Fixed / 🔄 Reopened
**Reported**: YYYY-MM-DD
**Fixed**: YYYY-MM-DD (if fixed)
**Severity**: CRITICAL / HIGH / MEDIUM / LOW

**Description**: [What's wrong]
**Observed Behavior**: [What actually happens]
**Expected Behavior**: [What should happen]
**Root Cause**: [Why it happens]
**Fix Reference**: [Link to fixed_issues_log.md entry]
```

**When to Read**:
- Before starting any work (avoid duplicating effort)
- When encountering similar issues
- Understanding problem patterns

**When to Update**:
- **IMMEDIATELY** when discovering any problem
- When fixing a problem (move to Fixed section)
- When problem reopens (add to Reopened section)
- NEVER delete entries (even after fixing)

**⚠️ IMMUTABLE**: This is the permanent problem record

**Reference**: `/progress/fixed_issues_log.md`

### new_problem (TO BE CREATED)
**Purpose**: Active problem inbox for new issues
**Authority**: HIGH
**Status**: WORKING FILE

**Format**:
```markdown
## Problem: [Short Title]
**Reported**: YYYY-MM-DD HH:MM
**Severity**: [CRITICAL/HIGH/MEDIUM/LOW]
**Component**: [Which part of system]

**Description**:
[Detailed description]

**Steps to Reproduce**:
1. [Step 1]
2. [Step 2]

**Expected**: [What should happen]
**Actual**: [What actually happens]

**Additional Context**:
- Error messages
- Screenshots
- Logs

---
```

**Workflow**:
1. User adds new problem to `new_problem` file
2. LLM assigns Problem ID (P-YYYY-MM-DD-NNN)
3. LLM adds to problems_log.md
4. LLM investigates and fixes
5. LLM removes fixed portion from `new_problem`
6. LLM updates problems_log.md (mark as fixed)
7. LLM adds to fixed_issues_log.md

**Benefits**:
- User can see how many problems remain
- User can track fix progress
- LLM has clear work queue
- Problems are never lost

---

## Problem Lifecycle

```
User Reports Problem
   ↓
[Add to new_problem file]
   ↓
[LLM assigns P-ID]
   ↓
[Add to problems_log.md as Active]
   ↓
[LLM investigates root cause]
   ↓
[LLM implements fix]
   ↓
[Remove from new_problem]
   ↓
[Update problems_log.md → Fixed]
   ↓
[Add detailed fix to fixed_issues_log.md]
   ↓
[Add regression guard if needed]
```

---

## Problem Severity Levels

### CRITICAL
- Security vulnerabilities
- Data loss risks
- System crashes
- Authentication failures
- **Action**: Fix immediately

### HIGH
- Major functionality broken
- User experience severely impacted
- Data inconsistency
- **Action**: Fix within 24 hours

### MEDIUM
- Functionality degraded
- Workaround available
- UI issues
- **Action**: Fix within 1 week

### LOW
- Minor inconveniences
- Cosmetic issues
- Nice-to-have improvements
- **Action**: Fix when time permits

---

## Dependencies

### Depends On:
- User problem reports
- Automated monitoring (when implemented)
- Code analysis

### Depended By:
- **CRITICAL**: Fix workflow
- progress/fixed_issues_log.md
- progress/regression_guard.md
- index/recent_changes.md

**Impact Radius**: CRITICAL (tracks all system issues)

---

## Recent Changes

### 2025-12-25: Initial Problems Structure Creation
**Files Created**: problems_log.md (new_problem to be created)
**Reason**: Establish immutable problem tracking
**Impact**: Provides permanent problem history
**Reference**: Initial governance structure

**Current Statistics**:
- Total Problems Logged: 6 (3 post-governance + 3 historical)
- Fixed: 6 (100%)
- Active: 0
- Reopened: 0

---

## Usage

### Reporting New Problem
```
1. User adds to new_problem file:
   ## Problem: Login fails with 500 error
   **Reported**: 2025-12-25 14:30
   **Severity**: HIGH
   ...

2. LLM processes:
   - Assigns P-2025-12-25-004
   - Adds to problems_log.md
   - Investigates
   - Fixes
   - Removes from new_problem
   - Documents fix
```

### Checking Problem Status
```
1. Read problems_log.md
2. Search for problem description or P-ID
3. Check status: Active / Fixed / Reopened
4. Read fix reference if fixed
```

---

## Authority Hierarchy

1. **problems_log.md** - HIGHEST (immutable ledger)
2. **new_problem** - HIGH (active work queue)

**NEVER delete from problems_log.md** - It's the permanent record

---

## Known Issues

### None

Problems module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: HIGHEST - Immutable problem ledger_
