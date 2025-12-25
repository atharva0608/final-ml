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

- **ALWAYS** update `info.md` in affected modules
- **ALWAYS** update `/index/recent_changes.md` with changes
- **ALWAYS** cross-reference Problem IDs when fixing issues
- **NEVER** make silent changes

---

## Mandatory Workflow

Before any code change:

1. ✅ Read `/instructions/master_rules.md` (this file)
2. ✅ Read `/problems/problems_log.md` to understand known issues
3. ✅ Check `/progress/fixed_issues_log.md` to avoid regressions
4. ✅ Identify relevant entries in `/index/feature_index.md`
5. ✅ Read affected module's `info.md` files
6. ✅ Make the change
7. ✅ Update:
   - Module `info.md`
   - `/progress/fixed_issues_log.md` (if fixing)
   - `/index/recent_changes.md`
   - `/scenarios/` (if behavior changes)

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
