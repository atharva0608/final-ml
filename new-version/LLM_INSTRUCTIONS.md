# LLM Instructions for Automated Task Management

> **Purpose**: This document provides step-by-step instructions for an LLM agent to autonomously process tasks, make changes, update documentation, and log all modifications.

---

## System Overview

You are an autonomous LLM agent responsible for:
1. Reading tasks from `task.md`
2. Executing fixes and changes
3. Updating all relevant documentation files
4. Logging changes in `CHANGELOG.md`
5. Updating `INFO.md` files in affected folders
6. Marking tasks as complete

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

### Phase 4: Documentation Updates

**Step 4.1**: Update primary documentation
```
Files to check and update:
✅ feature_mapping.md - Add/modify feature rows
✅ application_scenario.md - Update user flows
✅ backend_architecture.md - Update module mappings
✅ api_reference.md - Update API definitions
✅ schema_reference.md - Update schema definitions
```

**Step 4.2**: Update folder INFO.md files
```
For each affected folder:
1. Open INFO.md
2. Update component table
3. Add change log entry
4. Update "Last Updated" timestamp
5. List affected feature IDs
```

**Step 4.3**: Update global CHANGELOG.md
```
File: /docs/CHANGELOG.md

Add entry:
### [YYYY-MM-DD HH:MM:SS] - [Task Description]
**Changed By**: LLM Agent  
**Reason**: [Why]  
**Impact**: [What changed]  
**Files Modified**: [List]  
**Feature IDs Affected**: [List]  
**Breaking Changes**: [Yes/No]
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

**Document Version**: 1.0  
**Last Updated**: 2025-12-31  
**Status**: Ready for Automation
