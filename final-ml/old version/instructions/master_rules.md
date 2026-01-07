# Master Rules for LLM Engineering

## Mandatory Reading

**This document MUST be read before making any code changes.**

---

## Core Principles

### 1. Single Source of Truth

- **NEVER** create duplicate functionality
- **NEVER** create duplicate database tables, schemas, or APIs
- **ALWAYS** check if functionality exists before implementing
- If functionality exists, extend it—don't recreate it

### 2. Anti-Regression Protocol

- **NEVER** modify fixed logic without consulting `/progress/fixed_issues_log.md`
- **NEVER** override existing fixes
- **ALWAYS** check `/problems/problems_log.md` before implementing solutions
- If a bug was fixed, DO NOT reintroduce it

### 3. State-Aware Engineering

- **ALWAYS** consult `/progress/progress_tracker.md` for current system state
- **ALWAYS** update metadata after making changes
- **NEVER** assume previous state—verify it

### 4. Documentation Discipline

- **ALWAYS** update `info.md` in affected folders
- **ALWAYS** update `/index/recent_changes.md` with changes
- **ALWAYS** cross-reference Problem IDs when fixing issues
- **NEVER** make silent changes

### 5. info.md File Contract ⭐ NEW

- **EVERY folder** has an `info.md` file (except empty folders)
- **ALWAYS read** the folder's `info.md` before modifying files
- **ALWAYS update** the folder's `info.md` after changes
- **info.md contains**:
  - File-wise descriptions and purpose
  - Recent changes with dates
  - Reason for changes
  - Impact of changes
  - Dependencies

**Example**:
```
backend/api/info.md     - Describes all API route files
backend/workers/info.md - Describes all worker files
frontend/src/components/info.md - Describes all component files
```

---

## Mandatory Workflow

Before any code change:

1. ✅ Read `/instructions/master_rules.md` (this file)
2. ✅ Read `/problems/problems_log.md` to understand known issues
3. ✅ Check `/progress/fixed_issues_log.md` to avoid regressions
4. ✅ Identify relevant entries in `/index/feature_index.md`
5. ✅ **Read the folder's `info.md` file** (CRITICAL)
   - Located in same directory as files you'll modify
   - Contains file-wise details, recent changes, dependencies
   - Example: Modifying `backend/api/auth.py` → Read `backend/api/info.md`
6. ✅ Make the change
7. ✅ **Update the folder's `info.md`** (MANDATORY)
   - Add entry to "Recent Changes" section with:
     - Date (YYYY-MM-DD)
     - Files modified
     - Reason for change
     - Impact of change
   - Update file descriptions if purpose changed
8. ✅ Update global metadata:
   - `/progress/fixed_issues_log.md` (if fixing bug)
   - `/index/recent_changes.md` (always)
   - `/scenarios/` (if behavior changes)
9. ✅ **If fixing a problem from `/problems/new_problem`**:
   - Remove the fixed problem from `/problems/new_problem` file
   - Update `/problems/problems_log.md` status to "Fixed"
   - User can see remaining problems in `new_problem`

---

## Problem Intake Workflow ⭐ NEW

### User-Reported Problems

Users report new problems directly to `/problems/new_problem` file using the provided template.

**LLM Responsibilities**:
1. **Read `/problems/new_problem`** at session start
2. **Assign Problem ID**: P-YYYY-MM-DD-NNN
3. **Add to `/problems/problems_log.md`** as "Active"
4. **Investigate and fix** (follow Bug Fix Protocol)
5. **Remove from `/problems/new_problem`** (only the fixed portion)
6. **Update documentation** (fixed_issues_log.md, etc.)

**Benefits**:
- User has a clear problem inbox
- User can track fix progress
- No problems are lost
- Systematic problem resolution

**See**: `/instructions/fix_protocol.md#new-problem-intake-workflow`

---

## Forbidden Actions

### 🚫 NEVER:

- Delete or modify `/progress/fixed_issues_log.md` entries
- Create new APIs without checking `/index/feature_index.md`
- Duplicate database schemas
- Assume requirements—always verify
- Make changes without updating documentation
- Introduce security vulnerabilities (SQL injection, XSS, CSRF, etc.)
- Override fixed bugs
- Create "experimental" versions of existing features

---

## Required Actions

### ✅ ALWAYS:

- Check for existing implementations before creating new ones
- Update all metadata files after changes
- Reference Problem IDs in commit messages
- Cross-link related changes
- Validate against `/progress/regression_guard.md`
- Follow the fix protocol in `/instructions/fix_protocol.md`
- Maintain single source of truth

---

## Conflict Resolution

If you encounter conflicting information:

1. **Highest Authority**: `/instructions/` files
2. **Second**: `/progress/` state files
3. **Third**: `/index/` mapping files
4. **Fourth**: Module `info.md`
5. **Lowest**: Code comments

When in doubt, **ASK** before proceeding.

---

## Security Requirements

- NEVER commit secrets, API keys, or credentials
- ALWAYS validate user input
- ALWAYS use parameterized queries
- ALWAYS enforce authentication and authorization
- NEVER expose internal errors to users

---

## Version Control

- **Atomic commits**: One logical change per commit
- **Descriptive messages**: Reference Problem IDs and affected modules
- **No force pushes** to main/master branches
- **Always pull** before pushing

---

_Last Updated: 2025-12-25_
_Authority Level: HIGHEST_
