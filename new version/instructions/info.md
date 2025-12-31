# LLM Governance Instructions

## Purpose

Mandatory rules and protocols for all LLM sessions. **MUST be read before any code changes.**

**Last Updated**: 2025-12-25
**Authority Level**: HIGHEST

---

## Files

### master_rules.md ⚠️ MANDATORY
**Purpose**: Core principles and non-negotiable behavior
**Authority**: HIGHEST
**Status**: ACTIVE

**Key Sections**:
1. Single Source of Truth - Never duplicate functionality
2. Anti-Regression Protocol - Never override fixes
3. State-Aware Engineering - Always verify current state
4. Documentation Discipline - Always update metadata

**Mandatory Workflow** (7 steps):
1. Read master_rules.md
2. Check /problems/problems_log.md
3. Verify /progress/fixed_issues_log.md
4. Consult /index/feature_index.md
5. Read affected module info.md
6. Make the change
7. Update ALL metadata files

**When to Read**: BEFORE every code change

---

### fix_protocol.md
**Purpose**: Step-by-step bug fix process
**Authority**: HIGHEST
**Status**: ACTIVE

**Protocol Steps** (8 steps):
1. Problem Identification
2. Pre-Fix Verification
3. Root Cause Analysis
4. Solution Design
5. Implementation
6. Verification
7. Documentation (MANDATORY)
8. Commit

**Documentation Requirements**:
- Update module info.md
- Add entry to /progress/fixed_issues_log.md
- Update /index/recent_changes.md
- Update /problems/problems_log.md status
- Update /scenarios/ if behavior changed

**When to Use**: When fixing any bug or issue

---

### search_policy.md
**Purpose**: Where and how to search before coding
**Authority**: HIGHEST
**Status**: ACTIVE

**Search Priority Order**:
1. Control Plane (instructions/, index/, progress/, problems/)
2. Module info.md files
3. Scenario files
4. Source code (LAST)

**Forbidden Patterns**:
- Grep-first approach
- Assumption-based search
- Blind file reads
- Recursive exploration
- Reading /docs/legacy/ for current state

**When to Use**: Before searching for any functionality

---

### anti_duplication.md
**Purpose**: Prevent duplicate implementations
**Authority**: HIGHEST
**Status**: ACTIVE

**Core Rule**: "If functionality exists, extend it. Never recreate."

**Duplication Detection Checklist**:
- [ ] Checked /index/feature_index.md?
- [ ] Read relevant module info.md?
- [ ] Grepped for similar functions?
- [ ] Checked database models?
- [ ] Reviewed existing APIs?
- [ ] Looked for similar components?

**Allowed Exceptions**:
1. Different domains (must document)
2. Different layers (DB vs API models)
3. Performance optimization (must justify)
4. Legacy migration (must have sunset date)

**When to Use**: Before implementing ANY new functionality

---

### update_policy.md
**Purpose**: Metadata update requirements
**Authority**: HIGHEST
**Status**: ACTIVE

**Core Rule**: "Every code change MUST update at least 3 metadata files."

**Mandatory Updates** (Bug Fix):
1. Module info.md
2. /progress/fixed_issues_log.md
3. /index/recent_changes.md
4. /problems/problems_log.md (status update)
5. /scenarios/ (if behavior changed)

**Mandatory Updates** (Feature):
1. Module info.md
2. /index/feature_index.md
3. /index/dependency_index.md
4. /index/recent_changes.md
5. /scenarios/ (new scenario file)

**When to Use**: After EVERY code change

---

## File Hierarchy (Authority)

**When conflicts occur, trust in this order:**

1. **HIGHEST**: `/instructions/` files (this folder)
2. **HIGH**: `/progress/` state files
3. **MEDIUM**: `/index/` mapping files
4. **MEDIUM**: Module `info.md` files
5. **LOW**: Code comments

---

## Usage Workflow

### For LLM Sessions

```
1. ALWAYS read master_rules.md first
   ↓
2. Identify task type (bug fix / feature / refactor)
   ↓
3. Follow appropriate protocol:
   - Bug fix → fix_protocol.md
   - Search → search_policy.md
   - New feature → anti_duplication.md
   - Any change → update_policy.md
   ↓
4. Execute with discipline
   ↓
5. Update all metadata files
   ↓
6. Commit with proper references
```

---

## Enforcement

### Violations

Any LLM session that:
- Skips reading master_rules.md
- Creates duplicate functionality
- Modifies protected zones without checks
- Doesn't update metadata

**Result**: Changes MUST be reverted

---

## Recent Changes

### 2025-12-25: Initial Creation
**Reason**: Establish LLM governance structure
**Impact**: All future LLM sessions
**Files Created**: 5 instruction files
**Authority Established**: HIGHEST

---

_Last Updated: 2025-12-25_
_Authority: HIGHEST - Violation results in STOP_
