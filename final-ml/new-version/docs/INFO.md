# Documentation - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains all project documentation including feature mappings, API references, schemas, backend architecture, and application scenarios. This is the single source of truth for the Spot Optimizer platform documentation.

---

## Component Table

| File Name | Component ID | Type | Purpose | Version | Dependencies |
|-----------|-------------|------|---------|---------|--------------|
| feature_mapping.md | DOC-FEAT-MAP | Documentation | Master feature table with 131 features | 1.0 | None |
| application_scenario.md | DOC-APP-SCEN | Documentation | User journey narratives across 8 phases | 1.0 | feature_mapping.md |
| backend_architecture.md | DOC-BACKEND-ARCH | Documentation | Backend modules & execution flows (15 modules) | 1.0 | api_reference.md |
| api_reference.md | DOC-API-REF | Documentation | Complete API catalog (78 endpoints) | 1.0 | schema_reference.md |
| schema_reference.md | DOC-SCHEMA-REF | Documentation | Data schemas (25 schemas) | 1.0 | None |
| folder_structure.md | DOC-FOLDER-STRUCT | Documentation | Repository structure and organization | 1.0 | None |
| README_DOCUMENTATION.md | DOC-README | Documentation | Documentation system guide | 1.0 | None |
| LLM_INSTRUCTIONS.md | DOC-LLM-INSTR | Documentation | Automated task workflow instructions | 2.0 | task.md |
| CHANGELOG.md | DOC-CHANGELOG | Documentation | Global change log for all modifications | 1.0 | None |
| description.md | DOC-DESC-MD | Documentation | Markdown functional specification | 1.0 | None |
| description.txt | DOC-DESC-TXT | Documentation | Original functional specification | 1.0 | None |
| backenddecription.txt | DOC-BACKEND-DESC | Documentation | Backend description | 1.0 | None |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Documentation Structure Created
**Changed By**: LLM Agent
**Reason**: Organize project documentation into structured folder system
**Impact**: All documentation files moved from root to docs/ folder
**Files Modified**:
- Moved 12 documentation files to docs/ folder
- Created docs/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- None (documentation is self-contained)

### External Dependencies
- Markdown rendering engine (for viewing .md files)
- Git (for version control)

---

## Maintenance Guidelines

1. **Always update CHANGELOG.md** when making any code changes
2. **Update feature_mapping.md** when adding/modifying features
3. **Update api_reference.md** when adding/modifying API endpoints
4. **Update schema_reference.md** when adding/modifying data schemas
5. **Update backend_architecture.md** when adding/modifying backend modules
6. **Update application_scenario.md** when changing user flows

---

## Cross-Reference Rules

- All Feature IDs in feature_mapping.md must exist in application_scenario.md
- All API endpoints in api_reference.md must exist in backend_architecture.md
- All schemas in schema_reference.md must be referenced in api_reference.md
- All module IDs in backend_architecture.md must be unique
