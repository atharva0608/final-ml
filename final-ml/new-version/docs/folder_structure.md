# Folder Structure Reference

> **Purpose**: This document defines the current and expected folder structure for the Spot Optimizer platform repository, including mandatory `INFO.md` files in each directory for component tracking and change logging.
>
> **GitHub Repository**: [atharva0608/final-ml](https://github.com/atharva0608/final-ml)  
> **Branch**: `claude/aws-dual-mode-connectivity-fvlS3`

---

## Table of Contents
1. [Current Folder Structure](#current-folder-structure)
2. [Expected Folder Structure](#expected-folder-structure)
3. [Mandatory INFO.md Requirements](#mandatory-infomd-requirements)
4. [Folder-Level Documentation Standards](#folder-level-documentation-standards)
5. [Change Logging Protocol](#change-logging-protocol)

---

## Current Folder Structure

**GitHub Repository Structure**:

```
atharva0608/final-ml (GitHub)
│
├── README.md                               # Repository README
│
├── old-version/                            # Legacy implementation (archived)
│   └── [legacy files]
│
└── new-version/                            # 🎯 ACTIVE DEVELOPMENT (Root for all new work)
    │
    ├── feature_mapping.md                 # Master feature table (131 features)
    ├── application_scenario.md            # User journey narratives (8 phases)
    ├── backend_architecture.md            # Backend modules & flows (15 modules)
    ├── api_reference.md                   # Complete API catalog (78 endpoints)
    ├── schema_reference.md                # Data schemas (25 schemas)
    ├── folder_structure.md                # This file
    ├── README_DOCUMENTATION.md            # Documentation system guide
    ├── LLM_INSTRUCTIONS.md                # Automated task workflow
    ├── CHANGELOG.md                       # Global change log
    ├── task.md                            # Task management file
    │
    ├── description.txt                    # Original functional spec
    ├── description.md                     # Markdown functional spec
    └── backenddecription.txt              # Backend description
```

**Note**: All documentation files are currently in `new-version/` root. They will be organized into the expected structure below.

---

## Expected Folder Structure

### Complete Repository Structure (Starting from new-version/)

```
new-version/                                # 🎯 ROOT DIRECTORY
│
├── docs/                                   # 📚 All Documentation
│   ├── INFO.md                            # Folder info + component table
│   ├── feature_mapping.md                 # Master feature table
│   ├── application_scenario.md            # User journey narratives
│   ├── backend_architecture.md            # Backend modules & flows
│   ├── api_reference.md                   # Complete API catalog
│   ├── schema_reference.md                # Data schemas
│   ├── folder_structure.md                # This file
│   ├── README_DOCUMENTATION.md            # Documentation guide
│   ├── CHANGELOG.md                       # Global change log
│   └── LLM_INSTRUCTIONS.md                # Automated task instructions
│
├── backend/                               # 🔧 Backend Services
│   ├── INFO.md                            # Backend overview + module table
│   │
│   ├── api/                               # REST API endpoints
│   │   ├── INFO.md
│   │   ├── auth_routes.py
│   │   ├── cluster_routes.py
│   │   ├── template_routes.py
│   │   ├── policy_routes.py
│   │   ├── hibernation_routes.py
│   │   ├── audit_routes.py
│   │   ├── admin_routes.py
│   │   └── lab_routes.py
│   │
│   ├── services/                          # Business logic layer
│   │   ├── INFO.md
│   │   ├── auth_service.py
│   │   ├── cluster_service.py
│   │   ├── template_service.py
│   │   ├── policy_service.py
│   │   ├── hibernation_service.py
│   │   ├── metrics_service.py
│   │   ├── audit_service.py
│   │   └── admin_service.py
│   │
│   ├── workers/                           # Background workers (Celery)
│   │   ├── INFO.md
│   │   ├── discovery_worker.py           # WORK-DISC-01
│   │   ├── optimizer_worker.py           # WORK-OPT-01
│   │   ├── hibernation_worker.py         # WORK-HIB-01
│   │   └── report_worker.py              # WORK-RPT-01
│   │
│   ├── modules/                           # Intelligence modules
│   │   ├── INFO.md
│   │   ├── spot_optimizer.py             # MOD-SPOT-01
│   │   ├── bin_packer.py                 # MOD-PACK-01
│   │   ├── rightsizer.py                 # MOD-SIZE-01
│   │   ├── ml_model_server.py            # MOD-AI-01
│   │   ├── risk_tracker.py               # SVC-RISK-GLB
│   │   └── model_validator.py            # MOD-VAL-01
│   │
│   ├── scrapers/                          # Data collection services
│   │   ├── INFO.md
│   │   ├── spot_advisor_scraper.py       # SVC-SCRAPE-01
│   │   └── pricing_collector.py          # SVC-PRICE-01
│   │
│   ├── core/                              # Core system components
│   │   ├── INFO.md
│   │   ├── decision_engine.py            # CORE-DECIDE
│   │   ├── action_executor.py            # CORE-EXEC
│   │   └── api_gateway.py                # CORE-API
│   │
│   ├── models/                            # Database models (SQLAlchemy)
│   │   ├── INFO.md
│   │   ├── user.py
│   │   ├── account.py
│   │   ├── cluster.py
│   │   ├── instance.py
│   │   ├── node_template.py
│   │   ├── cluster_policy.py
│   │   ├── hibernation_schedule.py
│   │   ├── audit_log.py
│   │   └── ml_model.py
│   │
│   ├── schemas/                           # Pydantic schemas
│   │   ├── INFO.md
│   │   ├── auth_schemas.py
│   │   ├── cluster_schemas.py
│   │   ├── template_schemas.py
│   │   ├── policy_schemas.py
│   │   ├── metric_schemas.py
│   │   └── audit_schemas.py
│   │
│   └── utils/                             # Utility functions
│       ├── INFO.md
│       ├── crypto.py
│       ├── validators.py
│       └── helpers.py
│
├── frontend/                              # ⚛️ React Frontend
│   ├── INFO.md
│   │
│   ├── src/
│   │   ├── INFO.md
│   │   │
│   │   ├── components/                   # Reusable UI components
│   │   │   ├── INFO.md
│   │   │   ├── auth/
│   │   │   │   ├── INFO.md
│   │   │   │   ├── LoginPage.jsx
│   │   │   │   └── AuthGateway.jsx
│   │   │   │
│   │   │   ├── dashboard/
│   │   │   │   ├── INFO.md
│   │   │   │   ├── Dashboard.jsx
│   │   │   │   ├── KPICard.jsx
│   │   │   │   └── ActivityFeed.jsx
│   │   │   │
│   │   │   ├── clusters/
│   │   │   │   ├── INFO.md
│   │   │   │   ├── ClusterRegistry.jsx
│   │   │   │   └── ClusterDetailDrawer.jsx
│   │   │   │
│   │   │   ├── templates/
│   │   │   │   ├── INFO.md
│   │   │   │   ├── NodeTemplates.jsx
│   │   │   │   └── TemplateWizard.jsx
│   │   │   │
│   │   │   ├── policies/
│   │   │   │   ├── INFO.md
│   │   │   │   └── OptimizationPolicies.jsx
│   │   │   │
│   │   │   ├── hibernation/
│   │   │   │   ├── INFO.md
│   │   │   │   └── Hibernation.jsx
│   │   │   │
│   │   │   ├── audit/
│   │   │   │   ├── INFO.md
│   │   │   │   └── AuditLogs.jsx
│   │   │   │
│   │   │   ├── settings/
│   │   │   │   ├── INFO.md
│   │   │   │   ├── Settings.jsx
│   │   │   │   └── CloudIntegrations.jsx
│   │   │   │
│   │   │   └── admin/
│   │   │       ├── INFO.md
│   │   │       ├── AdminDashboard.jsx
│   │   │       ├── TheLab.jsx
│   │   │       └── SystemHealth.jsx
│   │   │
│   │   ├── services/                     # API client services
│   │   │   ├── INFO.md
│   │   │   ├── api.js
│   │   │   ├── authService.js
│   │   │   ├── clusterService.js
│   │   │   └── metricsService.js
│   │   │
│   │   ├── hooks/                        # Custom React hooks
│   │   │   ├── INFO.md
│   │   │   ├── useAuth.js
│   │   │   ├── useClusters.js
│   │   │   └── useMetrics.js
│   │   │
│   │   ├── utils/                        # Frontend utilities
│   │   │   ├── INFO.md
│   │   │   ├── formatters.js
│   │   │   └── validators.js
│   │   │
│   │   └── App.jsx                       # Root component
│   │
│   └── public/
│       └── index.html
│
├── scripts/                               # 🔨 Automation Scripts
│   ├── INFO.md
│   │
│   ├── aws/                              # AWS boto3 scripts
│   │   ├── INFO.md
│   │   ├── terminate_instance.py         # SCRIPT-TERM-01
│   │   ├── launch_spot.py                # SCRIPT-SPOT-01
│   │   ├── detach_volume.py              # SCRIPT-VOL-01
│   │   └── update_asg.py                 # SCRIPT-ASG-01
│   │
│   └── deployment/
│       ├── INFO.md
│       ├── deploy.sh
│       └── setup.sh
│
├── config/                                # ⚙️ Configuration Files
│   ├── INFO.md
│   ├── database.py
│   ├── redis.py
│   └── celery.py
│
├── .github/                               # 🤖 GitHub Actions
│   ├── workflows/
│   │   ├── ci.yml
│   │   └── deploy.yml
│   └── PULL_REQUEST_TEMPLATE.md
│
├── docker/                                # 🐳 Docker Configuration
│   ├── INFO.md
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
│
├── .env.example                           # Environment variables template
├── requirements.txt                       # Python dependencies
├── package.json                           # Node.js dependencies
└── README.md                              # Project README
```

**Note**: This structure starts from `new-version/` as the root. The old `final-ml/` folder in the parent directory is kept for legacy reference but not actively maintained.

---

## Mandatory INFO.md Requirements

### Every Folder MUST Contain INFO.md

**Purpose**: Track all files, components, IDs, and changes within each directory

### INFO.md Template

```markdown
# [Folder Name] - Component Information

> **Last Updated**: YYYY-MM-DD HH:MM:SS  
> **Maintainer**: [Name/Team]

---

## Folder Purpose
[Brief description of what this folder contains and its role in the system]

---

## Component Table

| File Name | Component/Module ID | Type | Purpose | Feature IDs | Dependencies |
|-----------|-------------------|------|---------|-------------|--------------|
| example.py | MOD-SPOT-01 | Module | Spot optimization logic | client-cluster-button-reuse-dep-click-opt | Redis, boto3 |

---

## Recent Changes

### [YYYY-MM-DD] - [Change Description]
**Changed By**: [Name]  
**Reason**: [Why the change was made]  
**Impact**: [What was affected]  
**Files Modified**: [List of files]  
**Feature IDs Affected**: [List of IDs]  
**Breaking Changes**: [Yes/No - Description if yes]  

---

## Dependencies

### Internal Dependencies
- [List of other folders/modules this depends on]

### External Dependencies
- [List of third-party libraries]

---

## API Endpoints (if applicable)
- `GET /example` - [Description]

---

## Schemas Used (if applicable)
- `SCHEMA-EXAMPLE-Name-v1` - [Description]
```

---

## Folder-Level Documentation Standards

### 1. Backend Folders

**backend/api/INFO.md** Example:
```markdown
# API Routes - Component Information

## Component Table

| File Name | Module ID | Endpoints | Schemas | Feature IDs |
|-----------|-----------|-----------|---------|-------------|
| auth_routes.py | CORE-API | POST /api/auth/signup, POST /api/auth/token | SCHEMA-AUTH-SignupRequest, SCHEMA-AUTH-TokenResponse | any-auth-form-reuse-dep-submit-signup, any-auth-form-reuse-dep-submit-signin |
| cluster_routes.py | CORE-API | GET /clusters, POST /clusters/connect | SCHEMA-CLUSTER-ClusterList, SCHEMA-CLUSTER-AgentCmd | client-cluster-table-unique-indep-view-list, client-cluster-button-reuse-dep-click-connect |
```

### 2. Frontend Folders

**frontend/src/components/dashboard/INFO.md** Example:
```markdown
# Dashboard Components - Component Information

## Component Table

| File Name | Component Name | Feature IDs | APIs Used | Schemas |
|-----------|---------------|-------------|-----------|---------|
| Dashboard.jsx | Dashboard | client-home-kpi-reuse-indep-view-spend, client-home-chart-unique-indep-view-proj | GET /metrics/kpi, GET /metrics/projection | SCHEMA-METRIC-KPISet, SCHEMA-METRIC-ChartData |
| KPICard.jsx | KPICard | client-home-kpi-reuse-indep-view-spend | N/A | SCHEMA-METRIC-KPISet |
```

### 3. Scripts Folders

**scripts/aws/INFO.md** Example:
```markdown
# AWS Scripts - Component Information

## Component Table

| File Name | Script ID | AWS APIs | Purpose | Called By |
|-----------|-----------|----------|---------|-----------|
| terminate_instance.py | SCRIPT-TERM-01 | ec2.terminate_instances() | Gracefully drains and terminates node | CORE-EXEC |
| launch_spot.py | SCRIPT-SPOT-01 | ec2.request_spot_fleet() | Requests Spot Fleet | CORE-EXEC |
```

---

## Change Logging Protocol

### When to Log Changes

**ALWAYS log when**:
- Adding new files
- Modifying existing files
- Deleting files
- Changing component IDs
- Updating schemas
- Modifying APIs
- Changing dependencies

### Change Log Entry Format

```markdown
### [2025-12-31 17:15] - Added Parallel Model Testing Feature
**Changed By**: DevOps Team  
**Reason**: Support A/B testing of ML models in production  
**Impact**: 
- Added new API endpoints: POST /lab/parallel, WS /lab/stream/{id}
- Created new schema: SCHEMA-LAB-ABTestConfig-v1
- Updated TheLab.jsx component
**Files Modified**: 
- backend/api/lab_routes.py
- backend/modules/ml_model_server.py
- frontend/src/components/admin/TheLab.jsx
**Feature IDs Affected**: 
- admin-lab-form-reuse-dep-config-parallel@SCHEMA-LAB-ABTestConfig
- admin-lab-chart-unique-indep-view-abtest@SCHEMA-LAB-ABResults
**Breaking Changes**: No
```

### Global CHANGELOG.md

**Location**: `/docs/CHANGELOG.md`

**Format**:
```markdown
# Global Change Log

## [2025-12-31]

### Added
- Parallel Model Testing feature in The Lab
- New schema: SCHEMA-LAB-ABTestConfig-v1
- API endpoints: POST /lab/parallel, WS /lab/stream/{id}

### Changed
- Updated TheLab.jsx to support A/B testing UI
- Enhanced ml_model_server.py with parallel test logic

### Fixed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Security
- N/A
```

---

## Automated Maintenance Rules

### 1. File Creation
When creating a new file:
1. Update parent folder's `INFO.md` component table
2. Add entry to global `CHANGELOG.md`
3. Update relevant documentation files (feature_mapping.md, api_reference.md, etc.)

### 2. File Modification
When modifying a file:
1. Add change log entry to folder's `INFO.md`
2. Update "Last Updated" timestamp
3. Update affected feature IDs in documentation
4. Update global `CHANGELOG.md`

### 3. File Deletion
When deleting a file:
1. Mark as deleted in folder's `INFO.md`
2. Update global `CHANGELOG.md`
3. Remove from all documentation references
4. Archive feature IDs (mark as deprecated)

---

## Folder Structure Validation

### Required Folders
- ✅ `/docs` - Documentation
- ✅ `/backend` - Backend services
- ✅ `/frontend` - React frontend
- ✅ `/scripts` - Automation scripts
- ✅ `/config` - Configuration
- ✅ `/docker` - Docker files

### Required Files in Each Folder
- ✅ `INFO.md` - Component tracking
- ✅ At least one source file

### Validation Script
```bash
#!/bin/bash
# validate_structure.sh
# Run from new-version/ directory

find . -type d -not -path "*/node_modules/*" -not -path "*/.git/*" | while read dir; do
  if [ ! -f "$dir/INFO.md" ]; then
    echo "❌ Missing INFO.md in: $dir"
  fi
done
```

---

## Migration Guide

### Organizing Documentation into Expected Structure

**Current State**: All documentation files are in `new-version/` root  
**Target State**: Organized into `docs/` folder with proper backend/frontend structure

**Step 1**: Create folder structure (from repository root)
```bash
cd new-version/
mkdir -p docs backend/{api,services,workers,modules,scrapers,core,models,schemas,utils}
mkdir -p frontend/src/{components/{auth,dashboard,clusters,templates,policies,hibernation,audit,settings,admin},services,hooks,utils}
mkdir -p scripts/{aws,deployment} config docker
```

**Step 2**: Move documentation files to docs/ folder
```bash
mv *.md docs/
# Keep task.md in root for easy access
mv docs/task.md .
```

**Step 3**: Create INFO.md in each folder
```bash
find . -type d -not -path "*/node_modules/*" -not -path "*/.git/*" -exec touch {}/INFO.md \;
```

**Step 4**: Populate INFO.md files using template (see section above)

**Step 5**: Commit and push changes
```bash
git add .
git commit -m "Organize documentation into folder structure"
git push origin claude/aws-dual-mode-connectivity-fvlS3
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-31  
**Status**: Expected Structure Defined
