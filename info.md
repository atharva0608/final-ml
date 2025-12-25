# Spot Optimizer Platform - Master Navigation & LLM Memory System

## 🎯 Purpose

This is the **MASTER NAVIGATION** document for the entire spot optimizer platform. Start here to understand the complete system architecture, locate any functionality, and navigate the LLM memory system.

**Last Updated**: 2025-12-25 (Comprehensive LLM Memory System)
**Authority Level**: MASTER INDEX
**Total Modules**: 37 documented modules with info.md files

---

## 📋 What This Platform Does

Multi-tenant AWS spot instance optimization platform with ML-powered decision making, zero-downtime failover, and cost optimization.

**Core Value Proposition**:
- **40-60% AWS cost savings** through intelligent spot instance usage
- **< 60 seconds monthly downtime** (SLA target)
- **Zero-downtime spot interruption handling** via replica system
- **ML-powered crash prediction** (5 model governance pipeline)
- **Multi-account AWS management** with dual authentication modes

**Key Features** (11+ documented):
- Multi-account AWS onboarding (CloudFormation + Access Keys)
- Real-time resource discovery across regions
- ML-powered spot instance recommendations
- Zero-downtime spot interruption handling
- Hive intelligence (global risk tracking)
- Cost waste detection and cleanup
- SLA accountability tracking
- Model governance pipeline
- Approval workflow for high-risk actions

---

## 🗺️ LLM Memory System Architecture

### Three-Layer Knowledge Structure

```
┌─────────────────────────────────────────────────────────────┐
│                  LAYER 1: GOVERNANCE                        │
│                  (Authority: HIGHEST)                        │
├─────────────────────────────────────────────────────────────┤
│  /instructions/  - Mandatory rules & protocols              │
│  /index/         - System maps & feature catalog            │
│  /progress/      - State tracking & fixes log               │
│  /problems/      - Active problem tracking                  │
│  /scenarios/     - User flows & integration scenarios       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  LAYER 2: MODULE DOCUMENTATION              │
│                  (Authority: HIGH)                           │
├─────────────────────────────────────────────────────────────┤
│  Each folder has info.md with:                              │
│  - Purpose & responsibility                                 │
│  - File-by-file documentation                               │
│  - Inter-dependencies (Depends On / Depended By)            │
│  - Recent changes with reasons                              │
│  - API/Database/Frontend mappings                           │
│  - Line numbers for critical functions                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  LAYER 3: SOURCE CODE                       │
│                  (Authority: MEDIUM)                         │
├─────────────────────────────────────────────────────────────┤
│  Actual implementation files                                │
│  - Read ONLY after consulting layers 1 & 2                 │
│  - Use info.md to locate specific files                    │
│  - Never search code first                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start for LLM Sessions

### MANDATORY First Steps (Read These First!)

```
1. READ: /instructions/master_rules.md (HIGHEST AUTHORITY)
   → Core principles, mandatory workflow, anti-regression protocol

2. READ: /instructions/search_policy.md
   → Where to search BEFORE touching code

3. CHECK: /problems/problems_log.md
   → Active issues that need attention

4. CHECK: /progress/fixed_issues_log.md
   → Recently fixed issues (DON'T BREAK THESE!)

5. CONSULT: /index/feature_index.md
   → Find existing functionality (anti-duplication)

6. READ: Relevant module info.md files
   → Understand module before modifying
```

**NEVER skip step 1**. Violating master_rules.md = changes must be reverted.

---

## 📁 Complete Directory Map

### 🔒 Governance & Control Plane (Authority: HIGHEST)

#### `/instructions/` - LLM Governance Rules
**Purpose**: Mandatory protocols for ALL LLM sessions
**Files**:
- `master_rules.md` ⚠️ MANDATORY - Core principles, mandatory workflow
- `fix_protocol.md` - 8-step bug fix process
- `search_policy.md` - Search priority order
- `anti_duplication.md` - Prevent duplicate implementations
- `update_policy.md` - Metadata update requirements

**When to Read**: BEFORE any code change
**Authority**: HIGHEST (violation = STOP)

---

#### `/index/` - System Maps & Catalogs
**Purpose**: Navigate system without reading all files
**Files**:
- `system_index.md` - High-level architecture diagrams
- `feature_index.md` ⭐ CRITICAL - Complete feature catalog (11+ features)
- `dependency_index.md` - Component dependencies & impact analysis
- `recent_changes.md` - Chronological change timeline

**When to Read**: Finding functionality, understanding dependencies
**Authority**: HIGH (authoritative source)

---

#### `/progress/` - State Tracking
**Purpose**: Track fixes, issues, and regression guards
**Files**:
- `fixed_issues_log.md` - All fixes with Problem IDs (P-YYYY-MM-DD-NNN)
- `regression_guard.md` - Protected zones (NEVER modify without review)
- `problems_log.md` - Active & fixed problems status

**When to Read**: Before fixing bugs, checking recent work
**Authority**: HIGH (state of record)

---

#### `/problems/` - Problem Intake
**Purpose**: User-reported problem tracking
**Files**:
- `new_problem` - Active problem inbox (user adds, LLM processes)
- `problems_log.md` - Complete problem history

**When to Read**: Session start (check for new problems)
**Authority**: HIGH (user-facing)

---

#### `/scenarios/` - User Flows & Integration
**Purpose**: End-to-end user scenarios and flows
**Files**:
- `client_onboarding_flow.md` - Complete onboarding journey
- `multi_account_management.md` - Multiple AWS account handling
- `ml_experiment_flow.md` - Lab mode experiment workflow
- Plus 3+ additional scenario files

**When to Read**: Understanding user experience, testing flows
**Authority**: MEDIUM (behavioral documentation)

---

### 💻 Backend Application (Authority: HIGH for modules)

#### `/backend/` - FastAPI Backend Application
**Purpose**: REST API, workers, business logic
**Structure**:
```
backend/
├── api/              ⭐ REST API Endpoints (530 lines doc)
│   └── 14 route files, 20+ endpoints documented
├── workers/          ⭐ Background Workers (764 lines doc)
│   ├── discovery_worker.py (444 lines) - AWS resource discovery
│   ├── health_monitor.py (146 lines) - System health monitoring
│   ├── optimizer_task.py (308 lines) - Pipeline router
│   └── event_processor.py (446 lines) - Spot interruption handling
├── database/         ⭐ Database Models (222 lines doc)
│   └── models.py - 10 models + 4 enums (14 classes, 485 lines)
├── utils/            ⭐ Shared Utilities (319 lines doc)
│   ├── crypto.py (35 lines) - AES-256 encryption ⚠️ PROTECTED
│   ├── system_logger.py (329 lines) - Structured logging
│   └── component_health_checks.py (545 lines) - Health monitoring
├── ai/              - ML model integration
├── auth/            - Authentication & JWT
├── decision_engine/ - Decision-making logic
├── executor/        - Task execution engine
├── jobs/            - Scheduled jobs
├── logic/           - Business logic
├── ml_models/       - ML model definitions
├── pipelines/       - Data processing pipelines (LINEAR/CLUSTER/K8S)
└── websocket/       - WebSocket real-time updates
```

**Entry Point**: `main.py` (FastAPI app)
**Documentation**: Each subfolder has comprehensive `info.md`

**Critical Modules Enhanced**:
- ✅ `api/info.md` - 530 lines, all 20+ endpoints with flows
- ✅ `database/info.md` - 222 lines, complete schema
- ✅ `workers/info.md` - 764 lines, 4 workers fully documented
- ✅ `utils/info.md` - 319 lines, encryption, logging, health checks

**Modules Needing Enhancement**:
- ⏳ `ai/info.md` - ML integration
- ⏳ `auth/info.md` - Authentication
- ⏳ `decision_engine/info.md` - Decision logic
- ⏳ `executor/info.md` - Task execution
- ⏳ `jobs/info.md` - Scheduled jobs
- ⏳ `logic/info.md` - Business logic
- ⏳ `pipelines/info.md` - Data pipelines
- ⏳ `websocket/info.md` - Real-time updates

---

### 🎨 Frontend Application (Authority: HIGH for modules)

#### `/frontend/` - React 18 SPA
**Purpose**: User interface for clients, admins, and lab users
**Structure**:
```
frontend/
├── src/
│   ├── components/   ⭐ React Components (800 lines doc)
│   │   ├── ClientSetup.jsx - AWS onboarding (9 buttons documented)
│   │   ├── AuthGateway.jsx - Role-based routing
│   │   └── Lab/ - Lab mode components
│   ├── pages/        - Page-level components
│   ├── services/     - API client functions
│   ├── context/      - React Context providers
│   ├── layouts/      - Page layouts
│   ├── lib/          - Utility libraries
│   ├── config/       - Configuration
│   └── assets/       - Static assets
└── public/           - Public static files
```

**Entry Point**: `App.jsx`
**Routing**: React Router v6

**Critical Modules Enhanced**:
- ✅ `components/info.md` - 800 lines, complete button/API/DB flows

**Modules Needing Enhancement**:
- ⏳ `services/info.md` - API client layer
- ⏳ `context/info.md` - State management
- ⏳ `pages/info.md` - Page components
- ⏳ `layouts/info.md` - Layout components
- ⏳ `config/info.md` - Configuration
- ⏳ `lib/info.md` - Utility functions
- ⏳ `assets/info.md` - Static assets
- ⏳ `components/Lab/info.md` - Lab mode UI

---

### 🗄️ Database & Infrastructure

#### `/database/` - Database Root
**Purpose**: Migration scripts and database setup
**Files**:
- `migrations/` - Alembic migration scripts
- `init_db.sql` - Initial schema setup

**See Also**: `/backend/database/` for ORM models (10 models documented)

---

#### `/ml-model/` - ML Model Storage
**Purpose**: Trained ML model files and artifacts
**Models**:
- Model governance: CANDIDATE → TESTING → GRADUATED → ENABLED → ARCHIVED
- File integrity: SHA256 hash validation
- Active prod model: Only ONE with `is_active_prod=True`

---

#### `/scraper/` - Spot Price Scraper
**Purpose**: Fetch real-time AWS spot price data
**Target**: AWS Spot Instance Advisor data
**Frequency**: Hourly updates
**Storage**: Price data for ML training

---

#### `/scripts/` - Utility Scripts
**Purpose**: Deployment, migration, and maintenance scripts
**Examples**:
- Database initialization
- Migration runners
- Data seeding
- Cleanup jobs

---

## 🔗 Inter-Module Dependencies

### Critical Dependency Chains

```
User Authentication (auth/)
  ↓
Account Management (api/client_routes.py, api/onboarding_routes.py)
  ↓
Discovery Worker (workers/discovery_worker.py)
  ↓
Database Models (database/models.py: Account, Instance)
  ↓
Dashboard Display (frontend/components/ClientSetup.jsx)
```

```
Frontend Button Click
  ↓
API Endpoint (backend/api/*.py)
  ↓
Background Worker (backend/workers/*.py)
  ↓
Database Update (backend/database/models.py)
  ↓
Frontend Polling (3-second interval)
  ↓
UI Update
```

**Complete Dependency Map**: See `/index/dependency_index.md`

---

## 📊 Database Schema Overview

### 10 Core Models (Complete documentation: `/backend/database/info.md`)

1. **User** - Authentication with RBAC (10 fields)
2. **Account** ⭐ CRITICAL - AWS connections with dual auth (16 fields)
   - Status flow: `pending` → `connected` → `active`
3. **Instance** - EC2 tracking with K8s awareness (17 fields)
4. **ExperimentLog** - ML experiments (17 fields)
5. **MLModel** - Model governance (14 fields)
6. **WasteResource** - Cost optimization (12 fields)
7. **SpotPoolRisk** - Hive intelligence (11 fields)
8. **ApprovalRequest** - High-risk gates (13 fields)
9. **GlobalRiskEvent** - Disruption log (9 fields)
10. **DowntimeLog** - SLA tracking (9 fields)

**Cascade Delete Chain**:
```
User DELETE → Account DELETE → Instance DELETE → ExperimentLog DELETE
```

**Protected Operations**:
- Global uniqueness: One AWS account_id → One user only
- Status transitions: Must follow exact flow
- Encryption: AES-256 for AWS credentials

---

## 🔐 Security & Protected Zones

### CRITICAL Protected Code (⚠️ NEVER modify without security review)

1. **Credential Encryption** (`/backend/utils/crypto.py`)
   - Algorithm: AES-256 (Fernet)
   - Functions: `encrypt_credential()`, `decrypt_credential()`
   - Migration required if algorithm changes

2. **Authentication System** (`/backend/auth/`)
   - JWT token generation
   - Password hashing (Bcrypt, 12 rounds)
   - Session management (24-hour expiration)

3. **Global Uniqueness Check** (`/backend/api/onboarding_routes.py:495`)
   - Prevents AWS account takeover
   - One account_id per user (database constraint + API check)

4. **Status Transitions** (multiple files)
   - Account: `pending` → `connected` → `active`
   - Dashboard depends on exact values

**Complete Protected Zones**: See `/progress/regression_guard.md`

---

## 🛠️ Development Workflows

### Bug Fix Workflow

```
1. Read /instructions/fix_protocol.md
   ↓
2. Check /problems/problems_log.md for Problem ID
   ↓
3. Review /progress/regression_guard.md (protected zones)
   ↓
4. Read affected module's info.md
   ↓
5. Implement fix
   ↓
6. Update metadata files:
   - Module info.md (recent changes)
   - /progress/fixed_issues_log.md (add entry)
   - /index/recent_changes.md (timeline)
   - /problems/problems_log.md (mark fixed)
   ↓
7. Commit with Problem ID: "fix(module): description (P-YYYY-MM-DD-NNN)"
```

---

### Feature Development Workflow

```
1. Read /instructions/master_rules.md
   ↓
2. Check /index/feature_index.md (anti-duplication)
   ↓
3. Check /index/dependency_index.md (impact analysis)
   ↓
4. Read affected module's info.md
   ↓
5. Implement feature
   ↓
6. Update metadata files:
   - Module info.md (file section, recent changes)
   - /index/feature_index.md (add new feature)
   - /index/dependency_index.md (add dependencies)
   - /index/recent_changes.md (timeline)
   - /scenarios/ (create new scenario file)
   ↓
7. Commit with clear message: "feat(module): description"
```

---

### Search Workflow (MANDATORY Order)

```
1. /index/feature_index.md - Find feature location
   ↓
2. Module info.md - Understand module structure
   ↓
3. /scenarios/ - Check user flows
   ↓
4. Source code - Read specific files (LAST RESORT)
```

**NEVER**:
- ❌ Grep source code first
- ❌ Search blindly without consulting indexes
- ❌ Read /docs/legacy/ for current state (outdated)
- ❌ Make assumptions about file locations

---

## 📈 System Metrics & Monitoring

### Performance Benchmarks

**Workers**:
- Discovery: 30-60 seconds (typical AWS account with 100 instances)
- Health Checks: < 1 second per check
- Optimizer (LINEAR): 2-5 seconds per instance
- Optimizer (CLUSTER): 10-30 seconds per ASG
- Event Processing: < 500ms per event

**API Response Times** (target):
- Authentication: < 200ms
- Resource listing: < 500ms
- Discovery trigger: < 100ms (non-blocking)

**Database**:
- Connection pool: 10 connections
- Query timeout: 30 seconds
- Health check latency: < 100ms (healthy), < 500ms (degraded)

---

## 🎯 Problem Tracking System

### Problem ID Format: `P-YYYY-MM-DD-NNN`

**Example**: `P-2025-12-25-003` (3rd problem on Dec 25, 2025)

**Workflow**:
1. User adds problem to `/problems/new_problem` file
2. LLM reads on session start
3. LLM assigns next Problem ID
4. LLM adds to `/problems/problems_log.md` as "Active"
5. LLM investigates and fixes
6. LLM removes from `/problems/new_problem`
7. LLM updates `/problems/problems_log.md` → "Fixed"
8. LLM adds to `/progress/fixed_issues_log.md` with details

**Recent Fixes**:
- P-2025-12-25-003: DELETE endpoint HTTP 200 vs 204
- P-2025-12-25-002: Dashboard $0 until midnight cron
- P-2025-12-25-001: Global uniqueness security vulnerability

---

## 📚 Documentation Hierarchy (When Conflicts Occur)

**Trust in this order**:

1. **HIGHEST**: `/instructions/` - Mandatory rules
2. **HIGH**: `/progress/` - State of record
3. **HIGH**: `/index/` - Authoritative maps
4. **HIGH**: Module `info.md` files - Module documentation
5. **MEDIUM**: `/scenarios/` - Behavioral documentation
6. **MEDIUM**: Source code - Implementation details
7. **LOW**: Code comments - Inline notes
8. **DEPRECATED**: `/docs/legacy/` - Historical only (DO NOT USE for current state)

---

## 🔄 Recent Major Changes (Last 7 Days)

### 2025-12-25: Comprehensive Documentation Enhancement
- ✅ Enhanced backend/api/info.md (530 lines, 20+ endpoints)
- ✅ Enhanced frontend/components/info.md (800 lines, 9 buttons)
- ✅ Enhanced backend/database/info.md (222 lines, 10 models)
- ✅ Enhanced backend/workers/info.md (764 lines, 4 workers)
- ✅ Created comprehensive LLM memory system
- ✅ Established info.md standard across all 37 modules

### 2025-12-25: Critical Bug Fixes
- Fixed HTTP 204 → 200 on DELETE endpoint (P-2025-12-25-003)
- Fixed dashboard data population (P-2025-12-25-002)
- Fixed global uniqueness check (P-2025-12-25-001)

### 2025-12-25: LLM Governance Structure
- Created `/instructions/` with 5 mandatory protocol files
- Created `/index/` with 4 system map files
- Created `/progress/` with fix logs and regression guards
- Created `/problems/` with problem intake workflow

**Complete Timeline**: See `/index/recent_changes.md`

---

## 🚦 Status Dashboard

### Documentation Coverage

**✅ Comprehensive (500+ lines)**:
- backend/api/info.md (530 lines)
- frontend/src/components/info.md (800 lines)
- backend/workers/info.md (764 lines)

**✅ Complete (200+ lines)**:
- backend/database/info.md (222 lines)
- backend/utils/info.md (319 lines)

**⏳ Basic (< 200 lines, needs enhancement)**:
- backend/ai/info.md
- backend/auth/info.md
- backend/decision_engine/info.md
- backend/executor/info.md
- backend/jobs/info.md
- backend/logic/info.md
- backend/pipelines/info.md
- backend/websocket/info.md
- frontend/src/services/info.md
- frontend/src/context/info.md
- frontend/src/pages/info.md
- Plus 15+ other modules

**Target**: All modules at 200+ lines with complete flows, dependencies, and examples

---

## 🎓 Learning Path for New LLM Sessions

### First 5 Minutes

```
1. Read THIS file (/info.md)
   → Understand complete system architecture

2. Read /instructions/master_rules.md
   → Learn mandatory protocols

3. Scan /index/feature_index.md
   → Know what features exist

4. Check /problems/problems_log.md
   → See active issues

5. Review /progress/fixed_issues_log.md
   → Don't break recent fixes
```

### Before Any Code Change

```
1. Consult /index/feature_index.md
   → Is this duplicate?

2. Read module's info.md
   → Understand module structure

3. Check /progress/regression_guard.md
   → Is this protected?

4. Review /index/dependency_index.md
   → What's the impact radius?
```

### After Any Code Change

```
1. Update module's info.md
   → Document what changed and why

2. Update /index/recent_changes.md
   → Add to timeline

3. Update /progress/ or /index/ as appropriate
   → Keep metadata current

4. Commit with proper format
   → Include references (Problem ID, etc.)
```

---

## 🔍 Quick Reference

### Find Functionality
→ `/index/feature_index.md`

### Understand Dependencies
→ `/index/dependency_index.md`

### Check Recent Work
→ `/index/recent_changes.md`

### See Active Problems
→ `/problems/problems_log.md`

### Review Protected Zones
→ `/progress/regression_guard.md`

### Learn Protocols
→ `/instructions/master_rules.md`

### Understand User Flows
→ `/scenarios/` folder

### Navigate Backend
→ `/backend/info.md` → submodule info.md

### Navigate Frontend
→ `/frontend/info.md` → submodule info.md

### Check Database Schema
→ `/backend/database/info.md`

---

## 📞 Support & Resources

### For Development Questions
1. Check module's `info.md` file
2. Review relevant scenario in `/scenarios/`
3. Consult `/index/feature_index.md`

### For Bug Fixes
1. Read `/instructions/fix_protocol.md`
2. Check `/problems/problems_log.md` for Problem ID
3. Follow 8-step protocol

### For New Features
1. Read `/instructions/anti_duplication.md`
2. Check `/index/feature_index.md` first
3. Plan dependencies via `/index/dependency_index.md`

---

## 🎯 Success Criteria

An LLM session is successful when:

✅ **Read master_rules.md before any code change**
✅ **Consulted feature_index.md to avoid duplication**
✅ **Read affected module's info.md before modification**
✅ **Checked regression_guard.md for protected zones**
✅ **Updated all required metadata files after changes**
✅ **Committed with proper format and references**
✅ **All tests passing**
✅ **No regression in protected zones**

---

## 📖 Glossary

- **Control Plane**: Governance files (instructions/, index/, progress/, problems/)
- **Module**: A folder with info.md (e.g., backend/api/, frontend/components/)
- **Problem ID**: Format P-YYYY-MM-DD-NNN for tracking fixes
- **Protected Zone**: Code that MUST NOT be modified without security review
- **Regression Guard**: Protection against breaking recently fixed code
- **Authority Level**: HIGHEST (instructions/) → HIGH (index/, progress/) → MEDIUM (scenarios/) → LOW (comments)
- **info.md Contract**: Every non-empty folder has comprehensive info.md

---

_Last Updated: 2025-12-25 (Master Navigation & LLM Memory System)_
_Authority: MASTER INDEX - Start here for all navigation_
_Total Documentation: 37 modules with info.md files_
_Next Steps: Continue enhancing remaining 25+ modules to comprehensive standard_
