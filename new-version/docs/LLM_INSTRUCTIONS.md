# LLM Instructions for Automated Task Management

> **Purpose**: This document provides step-by-step instructions for an LLM agent to autonomously process tasks, make changes, update documentation, and log all modifications.
>
> **GitHub Repository**: [atharva0608/final-ml](https://github.com/atharva0608/final-ml)  
> **Active Branch**: `claude/review-instructions-hxq6T`

---

## System Overview

You are an autonomous LLM agent responsible for:
1. Reading tasks from `task.md`
2. Executing fixes and changes
3. **Updating ALL relevant documentation files (MANDATORY)**
4. Logging changes in `CHANGELOG.md`
5. Updating `INFO.md` files in affected folders
6. Marking tasks as complete

---

## Legacy File References (READ-ONLY)

### ⚠️ IMPORTANT: Legacy Files are for REFERENCE ONLY

The repository contains legacy implementation in `old-version/` folder. These files are **ARCHIVED** and should **NEVER be modified**. They serve as reference for:

**Frontend Design Patterns** (Reference Only):
```
old-version/frontend/
├── src/
│   ├── components/
│   │   ├── Dashboard.jsx          # Reference for dashboard layout
│   │   ├── ClusterRegistry.jsx    # Reference for table designs
│   │   ├── NodeTemplates.jsx      # Reference for card layouts
│   │   └── Charts/                # Reference for chart implementations
│   │       ├── SavingsChart.jsx
│   │       ├── PieChart.jsx
│   │       └── ActivityFeed.jsx
│   └── styles/
│       └── theme.css               # Reference for color schemes & styling
```

**Backend Patterns** (Reference Only):
```
old-version/backend/
├── api/
│   ├── routes.py                   # Reference for API structure
│   └── middleware.py               # Reference for auth patterns
├── services/
│   ├── cluster_service.py          # Reference for service layer patterns
│   └── metrics_service.py          # Reference for calculation logic
└── models/
    └── database.py                 # Reference for ORM patterns
```

### How to Use Legacy Files

**DO**:
- ✅ Reference UI component structure and layout patterns
- ✅ Reference chart configurations and data visualization approaches
- ✅ Reference backend service layer architecture
- ✅ Reference API endpoint naming conventions
- ✅ Reference database schema patterns

**DON'T**:
- ❌ Modify any files in `old-version/`
- ❌ Copy code directly without adapting to new architecture
- ❌ Use deprecated dependencies or patterns
- ❌ Reference outdated API endpoints

---

## STRICT UPDATE REQUIREMENTS

### 🚨 CRITICAL: Every Change MUST Update ALL Affected Files

**Mandatory Update Checklist** (For EVERY change):

1. **Code Files**:
   - ✅ Modify the actual implementation file(s)
   - ✅ Update related utility/helper files
   - ✅ Update configuration files (if applicable)

2. **Documentation Files** (ALL 5 MUST be checked):
   - ✅ `feature_mapping.md` - Add/update feature rows
   - ✅ `api_reference.md` - Add/update API endpoints
   - ✅ `schema_reference.md` - Add/update schemas
   - ✅ `backend_architecture.md` - Add/update modules/flows
   - ✅ `application_scenario.md` - Add/update user flows

3. **Metadata Files**:
   - ✅ `CHANGELOG.md` - Log the change with timestamp
   - ✅ `INFO.md` in affected folder(s) - Add change log entry
   - ✅ `task.md` - Mark task as complete

4. **Cross-References**:
   - ✅ Update all feature ID references
   - ✅ Update all schema references
   - ✅ Update all API endpoint references
   - ✅ Update all module ID references

### Validation Before Marking Complete

**Before marking ANY task as [x], verify**:
```
□ All 5 documentation files reviewed and updated
□ CHANGELOG.md has new entry with timestamp
□ All affected INFO.md files updated (EVERY folder touched)
□ All cross-references are consistent
□ No broken links in documentation
□ All feature IDs follow naming convention
□ All schema versions are correct
□ Git commit message is descriptive
```

**🚨 CRITICAL INFO.md REQUIREMENT**:
```
EVERY folder that contains a modified file MUST have its INFO.md updated.

Example: If you modify backend/services/cluster_service.py:
✅ MUST update: backend/services/INFO.md
✅ MUST update: backend/INFO.md (parent folder)
✅ MUST update: docs/CHANGELOG.md (global)

If you create a new file in frontend/src/components/clusters/:
✅ MUST create/update: frontend/src/components/clusters/INFO.md
✅ MUST update: frontend/src/components/INFO.md (parent)
✅ MUST update: frontend/INFO.md (grandparent)
✅ MUST update: docs/CHANGELOG.md (global)
```

**If ANY checkbox is unchecked → Task is NOT complete**

---

## Workflow Process

### Phase 1: Task Discovery

**Step 1.1**: Read the task list
```
File: /docs/task.md
Action: Parse all tasks marked with [ ] (incomplete)
```

**Step 1.2**: Prioritize tasks
```
Priority Order:
1. [CRITICAL] - Blocking issues
2. [HIGH] - Important features
3. [MEDIUM] - Enhancements
4. [LOW] - Nice-to-have
```

**Step 1.3**: Select next task
```
Rule: Process tasks sequentially, one at a time
Format: Mark selected task as [/] (in progress)
```

---

### Phase 2: Task Analysis

**Step 2.1**: Understand the task
```
Questions to answer:
- What needs to be changed?
- Which files are affected?
- Which components are impacted?
- Which schemas are involved?
- Which APIs need updates?
```

**Step 2.2**: Identify dependencies
```
Check:
- feature_mapping.md - Feature IDs affected
- api_reference.md - API endpoints affected
- schema_reference.md - Schemas affected
- backend_architecture.md - Backend modules affected
- application_scenario.md - User flows affected
```

**Step 2.3**: Create change plan
```
Document:
1. Files to modify
2. New files to create
3. Files to delete
4. Documentation to update
5. Tests to run
```

---

### Phase 3: Execute Changes

**Step 3.1**: Make code changes
```
For each file:
1. Read current content
2. Apply modifications
3. Validate syntax
4. Run linter (if applicable)
```

**Step 3.2**: Update feature IDs (if needed)
```
If feature IDs change:
1. Update feature_mapping.md
2. Update all references in other docs
3. Update INFO.md in affected folders
```

**Step 3.3**: Update schemas (if needed)
```
If schemas change:
1. Update schema_reference.md
2. Increment version (breaking vs non-breaking)
3. Update api_reference.md response examples
4. Update backend_architecture.md
```

**Step 3.4**: Update APIs (if needed)
```
If APIs change:
1. Update api_reference.md
2. Update backend_architecture.md
3. Update application_scenario.md (if user-facing)
```

---

### Phase 4: Documentation Updates (MANDATORY - NO EXCEPTIONS)

**Step 4.1**: Update ALL primary documentation files
```
🚨 CRITICAL: ALL 5 files MUST be reviewed for EVERY change

Files to check and update:
✅ feature_mapping.md - Add/modify feature rows
   → Add new row if new feature
   → Update existing row if feature modified
   → Mark as deprecated if feature removed

✅ application_scenario.md - Update user flows
   → Add new user journey steps
   → Update existing flows with new behavior
   → Add backend process descriptions

✅ backend_architecture.md - Update module mappings
   → Add new modules/functions
   → Update execution flows
   → Update module dependencies

✅ api_reference.md - Update API definitions
   → Add new endpoints with full documentation
   → Update request/response schemas
   → Update "Used By" component lists

✅ schema_reference.md - Update schema definitions
   → Add new schemas with TypeScript definitions
   → Update existing schemas (version bump)
   → Update component mappings

⚠️ FAILURE TO UPDATE ALL FILES = INCOMPLETE TASK
```

**Step 4.2**: Update folder INFO.md files (MANDATORY - NO EXCEPTIONS)
```
🚨 CRITICAL RULE: EVERY folder containing a modified/created/deleted file MUST have its INFO.md updated.

INFO.md Update Protocol:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: Identify ALL affected folders
─────────────────────────────────────
For each file you modify/create/delete, identify:
- The immediate parent folder
- All ancestor folders up to project root
- Related folders (e.g., if backend changes, check if frontend needs update)

STEP 2: Update or Create INFO.md in EACH folder
────────────────────────────────────────────────
For EACH affected folder:

A. If INFO.md exists:
   1. Open the file
   2. Update "Last Updated" timestamp at top
   3. Update Component Table if structure changed
   4. Add new entry to "Recent Changes" section

B. If INFO.md does NOT exist:
   1. Create INFO.md using template from folder_structure.md
   2. Populate component table with all files in folder
   3. Add initial change log entry
   4. Set "Last Updated" to current timestamp

STEP 3: Write the Change Log Entry
───────────────────────────────────
EVERY INFO.md update MUST include this entry format:

### [YYYY-MM-DD HH:MM:SS] - [Concise Change Description]
**Changed By**: LLM Agent  
**Task**: [Task ID or description from task.md]  
**Reason**: [Why this change was necessary]  
**Impact**: [What this affects - be specific]  
**Files Modified**: 
- [filename1] - [what changed]
- [filename2] - [what changed]
**Feature IDs Affected**: 
- [feature-id-1@SCHEMA-Name]
- [feature-id-2@SCHEMA-Name]
**API Endpoints Affected**: 
- [GET/POST/etc] [/endpoint/path]
**Schemas Affected**: 
- [SCHEMA-NAME-Version]
**Breaking Changes**: [Yes/No - if yes, explain what breaks]

STEP 4: Update Component Table (if applicable)
───────────────────────────────────────────────
If you added/modified/deleted a file, update the Component Table:

For NEW files:
| [filename] | [Component ID] | [Type] | [Purpose] | [Feature IDs] | [Dependencies] |

For MODIFIED files:
- Update the row with new information
- Update "Feature IDs" column if new features added
- Update "Dependencies" if imports changed

For DELETED files:
- Mark row with ~~strikethrough~~ or move to "Deprecated" section
- Add note: "Deleted on YYYY-MM-DD - Reason: [why]"

STEP 5: Verify Completeness
────────────────────────────
Before moving to next folder, verify:
□ "Last Updated" timestamp is current
□ Change log entry is complete and detailed
□ Component table is accurate
□ All cross-references are valid
□ No placeholder text remains

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ FAILURE TO UPDATE INFO.md = INCOMPLETE TASK
⚠️ Every folder touched MUST have INFO.md updated
⚠️ No exceptions - even for "small" changes
```

**Step 4.2.1**: INFO.md Update Examples
```
EXAMPLE 1: Adding a new backend service function
─────────────────────────────────────────────────
File Modified: backend/services/cluster_service.py
Function Added: export_cluster_report()

Folders to Update:
✅ backend/services/INFO.md
✅ backend/INFO.md
✅ docs/CHANGELOG.md

backend/services/INFO.md entry:
───────────────────────────────
### [2025-12-31 17:50:00] - Added Cluster Report Export Function
**Changed By**: LLM Agent  
**Task**: Add export cluster report feature  
**Reason**: User requested ability to export cluster data as PDF  
**Impact**: New export functionality available for all clusters  
**Files Modified**: 
- cluster_service.py - Added export_cluster_report() function
**Feature IDs Affected**: 
- client-cluster-button-unique-indep-click-export@SCHEMA-CLUSTER-ReportExport
**API Endpoints Affected**: 
- GET /clusters/{id}/export
**Schemas Affected**: 
- SCHEMA-CLUSTER-ReportExport-v1
**Breaking Changes**: No

Component Table Update:
| cluster_service.py | CORE-API | Service | Cluster management | client-cluster-button-unique-indep-click-export | boto3, jinja2 |


EXAMPLE 2: Creating a new frontend component
─────────────────────────────────────────────
File Created: frontend/src/components/reports/ReportExporter.jsx

Folders to Update:
✅ frontend/src/components/reports/INFO.md (CREATE if not exists)
✅ frontend/src/components/INFO.md
✅ frontend/src/INFO.md
✅ frontend/INFO.md
✅ docs/CHANGELOG.md

frontend/src/components/reports/INFO.md entry:
──────────────────────────────────────────────
# Reports Components - Component Information

> **Last Updated**: 2025-12-31 17:50:00  
> **Maintainer**: LLM Agent

## Folder Purpose
Contains React components for generating and exporting reports.

## Component Table

| File Name | Component Name | Feature IDs | APIs Used | Schemas |
|-----------|---------------|-------------|-----------|---------|
| ReportExporter.jsx | ReportExporter | client-cluster-button-unique-indep-click-export | GET /clusters/{id}/export | SCHEMA-CLUSTER-ReportExport |

## Recent Changes

### [2025-12-31 17:50:00] - Created Report Exporter Component
**Changed By**: LLM Agent  
**Task**: Add export cluster report feature  
**Reason**: New component needed for report export UI  
**Impact**: Users can now export cluster reports from UI  
**Files Modified**: 
- ReportExporter.jsx - New component created
**Feature IDs Affected**: 
- client-cluster-button-unique-indep-click-export@SCHEMA-CLUSTER-ReportExport
**Breaking Changes**: No


EXAMPLE 3: Modifying a database model
──────────────────────────────────────
File Modified: backend/models/cluster.py
Change: Added 'export_count' field

Folders to Update:
✅ backend/models/INFO.md
✅ backend/INFO.md
✅ docs/CHANGELOG.md

backend/models/INFO.md entry:
─────────────────────────────
### [2025-12-31 17:50:00] - Added Export Count Field to Cluster Model
**Changed By**: LLM Agent  
**Task**: Track cluster export statistics  
**Reason**: Need to track how many times each cluster has been exported  
**Impact**: Database schema change - requires migration  
**Files Modified**: 
- cluster.py - Added export_count Integer field with default=0
**Feature IDs Affected**: 
- client-cluster-button-unique-indep-click-export@SCHEMA-CLUSTER-ReportExport
**Schemas Affected**: 
- SCHEMA-CLUSTER-ClusterDetail-v1 (non-breaking addition)
**Breaking Changes**: No (new field is optional with default value)
**Migration Required**: Yes - run: alembic revision --autogenerate -m "Add export_count to clusters"
```

**Step 4.3**: Update global CHANGELOG.md (MANDATORY)
```
File: CHANGELOG.md

ALWAYS add entry with:
### [YYYY-MM-DD HH:MM:SS] - [Task Description]
**Changed By**: LLM Agent  
**Reason**: [Why the change was made]  
**Impact**: [What was affected - be specific]  
**Files Modified**: 
- file1.py (added function X)
- file2.jsx (updated component Y)
- feature_mapping.md (added row for feature Z)
**Feature IDs Affected**: 
- feature-id-1@SCHEMA-Name
- feature-id-2@SCHEMA-Name
**Breaking Changes**: [Yes/No - if yes, explain]

⚠️ NO change is complete without CHANGELOG.md entry
```

**Step 4.4**: Verify documentation consistency (MANDATORY)
```
Cross-check:
□ Feature ID in feature_mapping.md matches application_scenario.md
□ API in api_reference.md matches backend_architecture.md
□ Schema in schema_reference.md matches api_reference.md
□ Module ID in backend_architecture.md is unique
□ All links are valid and not broken
□ All timestamps are current
□ All tables are properly formatted

⚠️ If ANY check fails → Fix before proceeding
```

---

### Phase 5: Validation

**Step 5.1**: Cross-reference validation
```
Verify:
- All feature IDs exist in feature_mapping.md
- All APIs exist in api_reference.md
- All schemas exist in schema_reference.md
- All modules exist in backend_architecture.md
- All INFO.md files are updated
```

**Step 5.2**: Consistency check
```
Ensure:
- Schema versions are consistent
- API endpoints match across docs
- Feature IDs match naming convention
- Backend module IDs are correct
```

**Step 5.3**: Documentation completeness
```
Verify:
- No broken links
- All tables are properly formatted
- All code blocks have language tags
- All timestamps are updated
```

---

### Phase 6: Task Completion

**Step 6.1**: Mark task as complete
```
File: /docs/task.md
Action: Change [/] to [x] for completed task
```

**Step 6.2**: Generate completion summary
```
Create summary:
- Task description
- Files modified (count)
- Documentation updated (count)
- Feature IDs affected (list)
- Breaking changes (yes/no)
- Time taken
```

**Step 6.3**: Check for next task
```
If more tasks exist:
  → Go to Phase 1
Else:
  → Generate final report and stop
```

---

## Detailed Instructions by Task Type

### Task Type A: Add New Feature

**Steps**:
1. **Create feature ID** using naming convention
2. **Define schema** (if new data structure needed)
3. **Add API endpoint** (if new endpoint needed)
4. **Update backend module** (add function)
5. **Update frontend component** (add UI)
6. **Update documentation**:
   - Add row to `feature_mapping.md`
   - Add schema to `schema_reference.md`
   - Add API to `api_reference.md`
   - Add module function to `backend_architecture.md`
   - Update user flow in `application_scenario.md`
7. **Update INFO.md** in all affected folders
8. **Log change** in `CHANGELOG.md`

**Example**:
```
Task: Add "Export Cluster Report" feature

1. Feature ID: client-cluster-button-unique-indep-click-export@SCHEMA-CLUSTER-ReportExport
2. Schema: SCHEMA-CLUSTER-ReportExport-v1
3. API: GET /clusters/{id}/export
4. Backend: cluster_service.py → export_cluster_report()
5. Frontend: ClusterRegistry.jsx → Export button
6. Docs: Update all 5 primary docs
7. INFO.md: Update backend/services/INFO.md, frontend/src/components/clusters/INFO.md
8. CHANGELOG.md: Add entry
```

### Task Type B: Modify Existing Feature

**Steps**:
1. **Identify feature ID** from `feature_mapping.md`
2. **Check schema version** - breaking or non-breaking?
3. **Update code** in affected files
4. **Update documentation**:
   - Modify row in `feature_mapping.md` (if needed)
   - Update schema in `schema_reference.md` (version bump)
   - Update API in `api_reference.md` (if signature changed)
   - Update backend in `backend_architecture.md`
5. **Update INFO.md** with change log entry
6. **Log change** in `CHANGELOG.md`

### Task Type C: Fix Bug

**Steps**:
1. **Identify affected feature IDs**
2. **Make fix** in code
3. **Update documentation** (if behavior changed)
4. **Update INFO.md** with bug fix entry
5. **Log fix** in `CHANGELOG.md` under "Fixed" section

### Task Type D: Refactor Code

**Steps**:
1. **Identify all affected feature IDs**
2. **Refactor code** (no behavior change)
3. **Update backend_architecture.md** (if module structure changed)
4. **Update INFO.md** with refactor note
5. **Log refactor** in `CHANGELOG.md` under "Changed" section

---

## File Update Templates

### Template 1: feature_mapping.md Row

```markdown
| `[feature-id]@SCHEMA-[Name]` | [Section] | [Feature Name] | [Action] | [Output] | `[API]` | `[function]` | `[Module]` | `[Schema]` | `<!-- [feature-id] -->` |
```

### Template 2: INFO.md Change Log Entry

```markdown
### [YYYY-MM-DD HH:MM:SS] - [Change Description]
**Changed By**: LLM Agent  
**Reason**: [Task requirement]  
**Impact**: [What changed]  
**Files Modified**: 
- file1.py
- file2.jsx
**Feature IDs Affected**: 
- feature-id-1
- feature-id-2
**Breaking Changes**: No
```

### Template 3: CHANGELOG.md Entry

```markdown
## [YYYY-MM-DD]

### Added
- New feature: [Description]
- New API: [Endpoint]
- New schema: [Schema ID]

### Changed
- Modified [Component]: [Description]

### Fixed
- Bug in [Component]: [Description]
```

---

## Validation Rules

### Rule 1: Feature ID Consistency
```
Every feature ID in feature_mapping.md MUST:
- Follow naming convention
- Have corresponding schema (if applicable)
- Have corresponding API (if applicable)
- Be referenced in application_scenario.md
```

### Rule 2: Schema Version Control
```
When modifying schema:
- Breaking change → Increment major version (v1 → v2)
- Non-breaking → Increment minor version (v1.0 → v1.1)
- Update all references to schema
```

### Rule 3: Documentation Sync
```
When updating code:
- ALWAYS update corresponding documentation
- ALWAYS update INFO.md in affected folder
- ALWAYS log in CHANGELOG.md
```

### Rule 4: Cross-Reference Integrity
```
Verify:
- All API endpoints in api_reference.md exist in backend code
- All schemas in schema_reference.md are used
- All feature IDs in feature_mapping.md are unique
- All module IDs in backend_architecture.md are unique
```

---

## Error Handling

### Error Type 1: Missing Documentation
```
If documentation file missing:
1. Create file using template
2. Populate with current state
3. Log creation in CHANGELOG.md
```

### Error Type 2: Inconsistent IDs
```
If feature ID mismatch found:
1. Identify canonical source (feature_mapping.md)
2. Update all references
3. Log correction in CHANGELOG.md
```

### Error Type 3: Broken Cross-References
```
If cross-reference broken:
1. Identify correct reference
2. Update all occurrences
3. Log fix in CHANGELOG.md
```

---

## Stopping Conditions

### Stop When:
1. ✅ All tasks in `task.md` are marked [x]
2. ✅ All documentation is updated
3. ✅ All INFO.md files have change logs
4. ✅ CHANGELOG.md is updated
5. ✅ All validation rules pass

### Final Report Format:
```markdown
# Task Completion Report

**Date**: YYYY-MM-DD HH:MM:SS  
**Total Tasks Completed**: [N]  
**Total Files Modified**: [N]  
**Total Documentation Updates**: [N]  

## Summary by Task Type
- Features Added: [N]
- Features Modified: [N]
- Bugs Fixed: [N]
- Refactors: [N]

## Files Modified
[List of all files with change counts]

## Feature IDs Affected
[List of all feature IDs]

## Breaking Changes
[List or "None"]

## Validation Status
✅ All cross-references valid
✅ All documentation synced
✅ All INFO.md files updated
✅ CHANGELOG.md complete

**Status**: ALL TASKS COMPLETE ✅
```

---

## Quick Reference Commands

### Start Processing
```
1. Read /docs/task.md
2. Find first [ ] task
3. Mark as [/]
4. Begin Phase 1
```

### Update Documentation
```
1. Update feature_mapping.md
2. Update api_reference.md
3. Update schema_reference.md
4. Update backend_architecture.md
5. Update application_scenario.md
6. Update affected INFO.md files
7. Update CHANGELOG.md
```

### Complete Task
```
1. Mark task as [x] in task.md
2. Generate summary
3. Check for next task
4. If none, generate final report and STOP
```

---

**Document Version**: 2.0  
**Last Updated**: 2025-12-31  
**Status**: Production Ready - Enhanced with Comprehensive INFO.md Protocol

**Key Enhancements in v2.0**:
- ✅ Explicit INFO.md update requirements with examples
- ✅ Step-by-step INFO.md update protocol
- ✅ Mandatory folder hierarchy updates
- ✅ Detailed change log entry format
- ✅ Component table update instructions
- ✅ Three comprehensive real-world examples
