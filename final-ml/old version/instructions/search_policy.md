# Search Policy

## Purpose

Defines **where and how** the LLM should search for information before making code changes.

---

## Search Priority Order

When looking for functionality, **ALWAYS** search in this order:

### 1. Control Plane (Highest Priority)

**Check FIRST**:
1. `/instructions/master_rules.md` - Governance rules
2. `/problems/problems_log.md` - Known issues
3. `/progress/fixed_issues_log.md` - Historical fixes
4. `/index/feature_index.md` - Feature catalog
5. `/index/dependency_index.md` - Component relationships

**Why**: These files contain the authoritative state of the system.

### 2. Module Info Files

**Check SECOND**:
- `backend/api/info.md`
- `backend/workers/info.md`
- `backend/utils/info.md`
- `frontend/src/components/info.md`
- etc.

**Why**: These provide local module contracts and recent changes.

### 3. Scenario Files

**Check THIRD**:
- `/scenarios/auth_flow.md`
- `/scenarios/client_dashboard_flow.md`
- `/scenarios/failure_scenarios.md`

**Why**: These explain the "why" behind implementations.

### 4. Source Code

**Check LAST**:
- Actual implementation files
- Only after understanding high-level design

**Why**: Code shows "what" but not "why" or "intent".

---

## Forbidden Search Patterns

### 🚫 NEVER:

1. **Grep-first approach**: Don't search code before checking control plane
2. **Assumption-based search**: Don't assume location without verification
3. **Blind file reads**: Don't read files without consulting index first
4. **Recursive exploration**: Don't traverse directories randomly
5. **Outdated docs**: Don't read files in `/docs/legacy/` for current state

### ✅ ALWAYS:

1. **Index-driven search**: Use `/index/` to locate functionality
2. **Scenario-driven understanding**: Use `/scenarios/` to understand flows
3. **Problem-aware search**: Check `/problems/` before implementing fixes
4. **Progressive depth**: Start high-level, drill down only as needed

---

## Search Workflows

### Finding Existing Functionality

```
1. Check /index/feature_index.md
   ↓
2. Locate module name
   ↓
3. Read module's info.md
   ↓
4. Read specific source files mentioned
   ↓
5. Verify understanding against /scenarios/
```

### Understanding a Bug

```
1. Read /problems/problems_log.md
   ↓
2. Check if fixed: /progress/fixed_issues_log.md
   ↓
3. Identify affected modules from index
   ↓
4. Read module info.md
   ↓
5. Verify scenario in /scenarios/
   ↓
6. Read source code for details
```

### Implementing a Feature

```
1. Check if similar exists: /index/feature_index.md
   ↓
2. Read related scenarios: /scenarios/
   ↓
3. Identify extension points from module info.md
   ↓
4. Read source files for patterns
   ↓
5. Implement following existing patterns
```

---

## Keyword Search Strategy

### When to Use Grep/Search Tools

Use only after consulting control plane:

```bash
# ✅ GOOD: Targeted search after consulting index
# You know from /index/ that auth is in backend/api/auth.py
grep -r "def login" backend/api/auth.py

# 🚫 BAD: Blind search without context
grep -r "def login" .
```

### Search Scope Limits

**Allowed search scopes**:
- Specific modules identified by `/index/`
- Files listed in module `info.md`
- Files referenced in `/progress/fixed_issues_log.md`

**Forbidden search scopes**:
- Entire repository blindly
- `/docs/legacy/` for current implementation
- Third-party libraries for business logic

---

## Information Freshness

### Authoritative Sources (Current Truth)

- `/instructions/` - Governance
- `/index/` - System map
- `/progress/` - Current state
- `/problems/` - Known issues
- `/scenarios/` - Expected behavior
- Module `info.md` - Local contracts

### Historical/Reference Only

- `/docs/legacy/` - Old documentation
- Git history - Past decisions
- Comments in code - May be outdated

**Rule**: NEVER use historical sources for current implementation decisions.

---

## Search Anti-Patterns

### Anti-Pattern 1: The "Let Me Read Everything" Approach

❌ **Wrong**:
```
1. Read all files in backend/
2. Read all files in frontend/
3. Try to understand entire codebase
```

✅ **Correct**:
```
1. Read /index/feature_index.md
2. Identify relevant module
3. Read module's info.md
4. Read only necessary source files
```

### Anti-Pattern 2: The "Grep-Driven Development"

❌ **Wrong**:
```bash
grep -r "AWS" .
grep -r "account" .
grep -r "connect" .
```

✅ **Correct**:
```
1. Check /index/feature_index.md for "AWS account management"
2. Read /scenarios/client_onboarding_flow.md
3. Read backend/api/onboarding/info.md
4. Then read specific source files
```

### Anti-Pattern 3: The "Code Comment Oracle"

❌ **Wrong**: Trust code comments as source of truth

✅ **Correct**: Verify against control plane documentation

---

## Search Performance Optimization

### Minimize Context Window Usage

1. **Don't read entire files** - Use line offsets when possible
2. **Don't read all modules** - Only read what's referenced in index
3. **Don't traverse dependencies** - Use `/index/dependency_index.md` instead

### Efficient Search Pattern

```
High-level index (50 lines)
  ↓
Module info.md (100 lines)
  ↓
Specific function/class (50 lines)
  ↓
Related code (100 lines)
```

**Total**: ~300 lines vs reading entire modules (~10,000 lines)

---

## Emergency Search Protocol

If control plane is incomplete or contradictory:

1. **STOP** implementing
2. **DOCUMENT** the gap in `/problems/problems_log.md`
3. **ASK** for clarification
4. **UPDATE** control plane before proceeding

**Never guess. Never assume. Always verify.**

---

_Last Updated: 2025-12-25_
_Authority Level: HIGHEST_
