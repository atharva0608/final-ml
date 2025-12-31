# System Index Files

## Purpose

System maps and indexes for navigating the codebase without reading every file.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH

---

## Files

### system_index.md
**Purpose**: High-level architecture map
**Status**: AUTHORITATIVE

**Contents**:
- System architecture diagram
- Major component descriptions
- Data flow diagrams
- Deployment architecture
- Key directories

**When to Read**: Understanding overall system structure

---

### feature_index.md ⭐ CRITICAL
**Purpose**: Complete catalog of all features
**Status**: AUTHORITATIVE

**Contents**:
- 11+ documented features
- API endpoints for each feature
- Database tables
- Frontend components
- Dependencies
- Scenarios

**When to Read**: BEFORE implementing any new feature (anti-duplication)

**Recent Updates**:
- 2025-12-25: Added multi-account support feature
- 2025-12-25: Added account management endpoints
- 2025-12-25: Added polling feature

---

### dependency_index.md
**Purpose**: Component dependency mapping and change impact analysis
**Status**: AUTHORITATIVE

**Contents**:
- Dependency graph for 9+ components
- "Depends On" relationships
- "Depended By" relationships
- Impact radius (CRITICAL/HIGH/MEDIUM/LOW)
- Cascade delete relationships
- Change impact matrix

**When to Read**: BEFORE modifying any component to understand impact

**Critical Dependencies**:
- Authentication System (CRITICAL impact)
- Account Management (HIGH impact)
- Discovery Worker (HIGH impact)

---

### recent_changes.md
**Purpose**: Chronological timeline of all changes
**Status**: CURRENT

**Contents**:
- Changes by date (newest first)
- Module affected
- Impact radius
- Files changed
- Reference to fix logs

**When to Read**: Understanding recent system changes

**Update Frequency**: After EVERY commit

---

## Usage

### Finding Existing Functionality

```
1. Check feature_index.md
   ↓
2. Locate module name
   ↓
3. Read module's info.md
   ↓
4. Read specific source files
```

### Understanding Impact of Change

```
1. Identify component in dependency_index.md
   ↓
2. Review "Depended By" section
   ↓
3. Check impact radius
   ↓
4. Plan testing accordingly
```

### Checking Recent Work

```
1. Read recent_changes.md
   ↓
2. Identify related changes
   ↓
3. Check for conflicts
```

---

## Recent Changes

### 2025-12-25: Initial Index Creation
**Files Created**: 4 index files
**Entries Documented**:
- 11 features in feature_index.md
- 9 components in dependency_index.md
- 3 days of changes in recent_changes.md

**Reason**: Establish system navigation structure
**Impact**: Enables LLM to find functionality without searching
**Authority**: HIGH

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Use for system navigation_
