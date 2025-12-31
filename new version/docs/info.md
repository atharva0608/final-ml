# Documentation Module

## Purpose

Legacy documentation and historical reference materials.

**Last Updated**: 2025-12-25
**Authority Level**: LOW (legacy) / ARCHIVAL

---

## Structure

```
docs/
└── legacy/
    ├── architecture/
    ├── fixes/
    └── notes/
```

---

## Folders

### legacy/
**Purpose**: Historical documentation from pre-governance era
**Authority**: LOW (superseded by governance structure)
**Status**: ARCHIVAL (read-only, no updates)

**Contents**:
- Old architecture diagrams
- Historical fix notes
- Development notes
- Legacy design docs

**When to Read**:
- Understanding historical context
- Investigating old decisions
- Reference for legacy patterns

**When to Update**: NEVER (archived)

**Superseded By**:
- `/index/` - System architecture and features
- `/progress/` - Current state and fixes
- `/scenarios/` - User flows and business logic
- `/instructions/` - Governance rules

### legacy/architecture/
**Purpose**: Old architecture documentation
**Contents**: Legacy architecture diagrams, design notes
**Status**: ARCHIVAL

### legacy/fixes/
**Purpose**: Historical fix documentation
**Contents**: Pre-governance bug fix notes
**Status**: ARCHIVAL (superseded by `/progress/fixed_issues_log.md`)

**Files Moved Here** (2025-12-25):
- BACKEND_FIXES_2025-11-26.md
- FIX_SUMMARY_2025-11-25.md
- SESSION_FIXES_2025-11-23.md
- And 30+ other legacy docs

### legacy/notes/
**Purpose**: Development notes and miscellaneous docs
**Contents**: Random notes, TODO lists, brainstorming
**Status**: ARCHIVAL

---

## Migration History

### 2025-12-25: Legacy Migration
**Action**: Moved 34 files from root to `/docs/legacy/`
**Reason**: Clean separation between legacy and authoritative docs
**Impact**: Cleaner repository structure
**Reference**: `/index/recent_changes.md`

**Files Moved**:
- All .md and .txt files from root
- Old fix logs
- Historical notes
- Legacy architecture docs

---

## Authority Hierarchy

**DO NOT use docs/legacy/ as authoritative source**

Use this hierarchy instead:
1. **Instructions** (`/instructions/`) - Governance rules
2. **Index** (`/index/`) - System maps and features
3. **Progress** (`/progress/`) - Current state and fixes
4. **Problems** (`/problems/`) - Issue tracking
5. **Scenarios** (`/scenarios/`) - User flows
6. **docs/legacy/** - Historical reference only

---

## Dependencies

### Depends On:
- Nothing (archived)

### Depended By:
- Historical research only
- Reference for understanding old patterns

**Impact Radius**: LOW (archival only)

---

## Recent Changes

### 2025-12-25: Initial Legacy Documentation Archive
**Files Moved**: 34 files to legacy folders
**Reason**: Establish clean governance structure
**Impact**: Clear separation between legacy and current docs
**Reference**: `/index/recent_changes.md`

---

## Usage

### Accessing Legacy Docs
```
# For historical reference only
ls docs/legacy/fixes/
cat docs/legacy/architecture/old-design.md
```

### DO NOT
- ❌ Update files in docs/legacy/
- ❌ Use as authoritative source
- ❌ Reference in new code
- ❌ Create new files here

### DO
- ✓ Read for historical context
- ✓ Reference in governance docs (if explaining history)
- ✓ Keep as archival record

---

## Known Issues

### None

Documentation module is stable as of 2025-12-25.

---

_Last Updated: 2025-12-25_
_Authority: LOW - Archival documentation_
