# info.md Inter-Dependency Map - Complete Cross-Reference

## Purpose

Complete dependency graph of all 37 info.md files showing how modules relate, reference each other, and form the complete LLM memory system.

**Last Updated**: 2025-12-25
**Authority Level**: HIGH
**Total Modules Mapped**: 37

---

## Master Navigation

**START HERE**: `/info.md` (Root Master Navigation)
- Authority: MASTER INDEX
- Purpose: Entry point for all LLM sessions
- References: ALL 37 info.md files
- Must Read: Before any session begins

---

## Layer 1: Governance & Control Plane (Authority: HIGHEST)

### `/instructions/info.md` - Mandatory Protocols
**Authority**: HIGHEST
**Depends On**: None (foundation layer)
**Referenced By**:
- `/info.md` (master navigation)
- All modules (mandatory reading before code changes)

**Key Dependencies**:
- `master_rules.md` → Defines mandatory workflow
  - References `/problems/problems_log.md` (step 2)
  - References `/progress/fixed_issues_log.md` (step 3)
  - References `/index/feature_index.md` (step 4)
  - References module `info.md` files (step 5)
- `fix_protocol.md` → Defines fix workflow
  - Updates module `info.md` (step 7)
  - Updates `/progress/fixed_issues_log.md` (step 7)
  - Updates `/index/recent_changes.md` (step 7)
  - Updates `/problems/problems_log.md` (step 7)
- `search_policy.md` → Defines search order
  - Priority 1: Control Plane (`/instructions/`, `/index/`, `/progress/`, `/problems/`)
  - Priority 2: Module `info.md` files
  - Priority 3: `/scenarios/`
  - Priority 4: Source code (LAST)

---

### `/index/info.md` - System Maps & Catalogs
**Authority**: HIGH
**Depends On**:
- `/instructions/master_rules.md` (authority definition)
- All module `info.md` files (source data for catalogs)

**Referenced By**:
- `/info.md` (master navigation)
- All modules (feature lookup, dependency analysis)

**Key Files**:
- `feature_index.md` → Complete feature catalog
  - Cross-references: API endpoints, database tables, frontend components
  - Sources data from: `/backend/api/info.md`, `/backend/database/info.md`, `/frontend/src/components/info.md`
- `dependency_index.md` → Component dependency graph
  - Maps: Which modules depend on which
  - Impact analysis for changes
  - Sources: All module `info.md` "Dependencies" sections
- `recent_changes.md` → Chronological timeline
  - Sources: All module `info.md` "Recent Changes" sections
  - Updated: After every commit

---

### `/progress/info.md` - State Tracking
**Authority**: HIGH
**Depends On**:
- All module `info.md` files (source of changes)

**Referenced By**:
- `/info.md` (master navigation)
- `/instructions/fix_protocol.md` (mandatory updates)
- All modules (check before modifying)

**Key Files**:
- `fixed_issues_log.md` → All fixes with Problem IDs
  - Referenced by: Module `info.md` "Recent Changes" sections
  - Format: P-YYYY-MM-DD-NNN
- `regression_guard.md` → Protected zones
  - References: Specific files and line numbers in modules
  - Critical references:
    - `/backend/utils/crypto.py:17,23` (encryption)
    - `/backend/api/onboarding_routes.py:495` (uniqueness check)
    - `/backend/database/models.py:39` (account_id unique constraint)
- `problems_log.md` → Active & fixed problems
  - Updated by: LLM sessions after fixes
  - Cross-references: `fixed_issues_log.md` entries

---

### `/problems/info.md` - Problem Intake
**Authority**: HIGH
**Depends On**: User input (problem reports)

**Referenced By**:
- `/info.md` (master navigation)
- `/instructions/master_rules.md` (step 2 of workflow)

**Key Files**:
- `new_problem` → Active inbox
  - Processed by: LLM at session start
  - Cleared after: Problem assigned ID and fixed
- `problems_log.md` → Complete history
  - Cross-references: `/progress/fixed_issues_log.md`

---

### `/scenarios/info.md` - User Flows
**Authority**: MEDIUM
**Depends On**:
- `/backend/api/info.md` (API endpoints used)
- `/backend/database/info.md` (database operations)
- `/frontend/src/components/info.md` (UI components)
- `/backend/workers/info.md` (background processes)

**Referenced By**:
- `/info.md` (master navigation)
- `/index/feature_index.md` (scenario references)

**Key Files**:
- `client_onboarding_flow.md` → Complete onboarding
  - References: `ClientSetup.jsx`, `onboarding_routes.py`, `discovery_worker.py`
- `multi_account_management.md` → Multiple AWS accounts
  - References: `client_routes.py`, `Account` model
- Plus 3+ additional scenario files

---

## Layer 2: Application Modules (Authority: HIGH)

### Backend Modules - Core Dependencies

#### `/backend/info.md` - Backend Root
**Authority**: HIGH
**Depends On**:
- All `/backend/*/info.md` submodules

**Referenced By**:
- `/info.md` (master navigation)
- `/index/system_index.md` (architecture)

**Submodules** (14 total):
- api/, workers/, database/, utils/ (✅ comprehensive)
- ai/, auth/, decision_engine/, executor/, jobs/, logic/, ml_models/, pipelines/, websocket/ (⏳ basic)

---

#### `/backend/api/info.md` ⭐ COMPREHENSIVE (530 lines)
**Authority**: HIGH
**Depends On**:
- `/backend/database/info.md` (models used: Account, Instance, User, etc.)
- `/backend/workers/info.md` (triggers: discovery_worker, optimizer_task)
- `/backend/utils/info.md` (uses: crypto.py, system_logger.py)
- `/backend/auth/info.md` (JWT authentication)

**Referenced By**:
- `/frontend/src/components/info.md` (API calls from buttons)
- `/frontend/src/services/info.md` (API client functions)
- `/scenarios/client_onboarding_flow.md` (endpoint usage)
- `/index/feature_index.md` (feature → endpoint mapping)

**Key Cross-References**:
- `DELETE /client/accounts/{id}` →
  - Database: `accounts` table (DELETE), `instances` (CASCADE)
  - Frontend: `ClientSetup.jsx:handleDisconnect()` (line ~270)
  - Protected: `/progress/regression_guard.md#5`
- `POST /client/onboarding/{id}/verify` →
  - Worker: `discovery_worker.py:run_initial_discovery()`
  - Database: `accounts` (UPDATE status='connected')
  - Frontend: `ClientSetup.jsx:verifyConnection()` (line ~84)

---

#### `/backend/database/info.md` ⭐ COMPREHENSIVE (222 lines)
**Authority**: CRITICAL (schema authority)
**Depends On**:
- None (foundation layer for data)

**Referenced By**:
- `/backend/api/info.md` (all API routes use models)
- `/backend/workers/info.md` (workers read/write models)
- `/backend/logic/info.md` (business logic operates on models)
- `/frontend/src/components/info.md` (UI reflects data structure)
- `/index/feature_index.md` (feature → table mapping)

**Key Models Referenced**:
- `Account` model →
  - APIs: `onboarding_routes.py`, `client_routes.py`
  - Worker: `discovery_worker.py` (status transitions)
  - Frontend: `ClientSetup.jsx` (all 9 buttons)
  - Protected: Global uniqueness constraint
- `Instance` model →
  - APIs: `client_routes.py`, `metrics_routes.py`
  - Worker: `discovery_worker.py` (INSERT discovered)
  - Frontend: `NodeFleet.jsx`, `InstanceFlow.jsx`

**Cascade Delete Chain**:
```
User DELETE
  → Referenced by: `/backend/api/admin.py`
  → Cascades to: Account (via `/backend/database/models.py:40`)
    → Cascades to: Instance (via `/backend/database/models.py:67`)
      → Cascades to: ExperimentLog (via `/backend/database/models.py:121`)
```

---

#### `/backend/workers/info.md` ⭐ COMPREHENSIVE (764 lines)
**Authority**: HIGH
**Depends On**:
- `/backend/database/info.md` (models: Account, Instance, DowntimeLog, GlobalRiskEvent)
- `/backend/utils/info.md` (uses: crypto.py, system_logger.py, component_health_checks.py)
- `/backend/logic/info.md` (uses: RiskManager)

**Referenced By**:
- `/backend/api/info.md` (triggers workers via BackgroundTasks)
- `/frontend/src/components/info.md` (polls for worker completion)
- `/scenarios/client_onboarding_flow.md` (discovery worker flow)

**Key Workers Cross-References**:
- `discovery_worker.py` →
  - Triggered by: `onboarding_routes.py:553,270`
  - Database: `accounts` (UPDATE status), `instances` (UPSERT)
  - Encryption: Uses `crypto.decrypt_credential()` for access keys
  - Frontend: `ClientSetup.jsx:startPollingAccountStatus()` polls every 3 seconds
- `event_processor.py` →
  - Triggered by: AWS EventBridge (external)
  - Database: `instances` (create replicas), `downtime_logs` (INSERT), `global_risk_events` (INSERT)
  - Logic: Uses `RiskManager.register_risk_event()`

---

#### `/backend/utils/info.md` ⭐ COMPREHENSIVE (319 lines)
**Authority**: CRITICAL (crypto.py), HIGH (others)
**Depends On**:
- `/backend/database/info.md` (models: SystemLog, ComponentHealth)

**Referenced By**:
- `/backend/api/info.md` (encryption, logging)
- `/backend/workers/info.md` (encryption, logging, health checks)
- `/backend/auth/info.md` (password hashing)
- ALL backend modules (logging is universal)

**Key Utilities Cross-References**:
- `crypto.py` ⚠️ PROTECTED →
  - Used by: `onboarding_routes.py:247` (encrypt before INSERT)
  - Used by: `discovery_worker.py:91-92` (decrypt for AWS calls)
  - Protected: `/progress/regression_guard.md#credential-encryption`
- `system_logger.py` →
  - Used by: ALL workers (discovery, health_monitor, event_processor)
  - Writes to: `system_logs` table, `component_health` table
- `component_health_checks.py` →
  - Called by: `health_monitor.py:48` (every 30 seconds)
  - Called by: `discovery_worker.py:335` (after completion)

---

#### `/backend/logic/info.md` ⏳ NEEDS ENHANCEMENT
**Authority**: HIGH
**Depends On**:
- `/backend/database/info.md` (models: SpotPoolRisk, GlobalRiskEvent, ApprovalRequest)

**Referenced By**:
- `/backend/workers/info.md` (event_processor uses RiskManager)
- `/backend/pipelines/info.md` (decision logic)
- `/backend/executor/info.md` (execution gates)

**Key Modules**:
- `risk_manager.py` → Global risk tracking (hive intelligence)
- `approval_engine.py` → High-risk action gates
- Business rules and decision logic

---

#### `/backend/pipelines/info.md` ⏳ NEEDS ENHANCEMENT
**Authority**: HIGH
**Depends On**:
- `/backend/database/info.md` (models: Instance, MLModel, ExperimentLog)
- `/backend/logic/info.md` (decision logic)
- `/backend/ai/info.md` (ML inference)

**Referenced By**:
- `/backend/workers/info.md` (optimizer_task routes to pipelines)

**Key Pipelines**:
- `linear_optimizer.py` → Lab mode single-instance
- `cluster_optimizer.py` → Batch ASG optimization
- `kubernetes_optimizer.py` → K8s-aware node optimization

---

### Frontend Modules - Core Dependencies

#### `/frontend/info.md` - Frontend Root
**Authority**: HIGH
**Depends On**:
- All `/frontend/src/*/info.md` submodules

**Referenced By**:
- `/info.md` (master navigation)
- `/index/system_index.md` (architecture)

---

#### `/frontend/src/components/info.md` ⭐ COMPREHENSIVE (800 lines)
**Authority**: HIGH
**Depends On**:
- `/frontend/src/services/info.md` (API client functions)
- `/frontend/src/context/info.md` (state management: AuthContext)
- `/backend/api/info.md` (API endpoints called)

**Referenced By**:
- `/backend/api/info.md` (which component calls which endpoint)
- `/scenarios/client_onboarding_flow.md` (UI flow documentation)
- `/index/feature_index.md` (feature → component mapping)

**Key Component Cross-References**:
- `ClientSetup.jsx` →
  - APIs: `POST /client/onboarding/create`, `DELETE /client/accounts/{id}`, `POST /client/onboarding/{id}/verify`, etc. (9 buttons documented)
  - Database: `accounts` (via API), `instances` (via discovery worker)
  - Context: Uses `AuthContext` for user data
  - Services: Uses `apiClient.js` functions
- `AuthGateway.jsx` →
  - Context: Depends on `AuthContext.isAuthenticated`
  - Database: Checks user role (via JWT token)
  - Routing: Role-based routing (/client, /admin, /lab)

---

#### `/frontend/src/services/info.md` ⏳ NEEDS ENHANCEMENT
**Authority**: MEDIUM
**Depends On**:
- `/backend/api/info.md` (API endpoint contracts)
- `/frontend/src/config/info.md` (API base URL)

**Referenced By**:
- `/frontend/src/components/info.md` (components use API client)
- `/frontend/src/pages/info.md` (pages use API client)

**Key Services**:
- `apiClient.js` → Axios instance with auth headers
- `auth.js` → Authentication API calls
- `client.js` → Client-specific API calls

---

## Layer 3: Infrastructure & Support (Authority: MEDIUM)

### `/database/info.md` - Database Root
**Depends On**:
- `/backend/database/info.md` (schema definition)

**Referenced By**:
- `/info.md` (master navigation)

**Key Files**:
- `migrations/` → Alembic migration scripts
- `init_db.sql` → Initial schema

---

### `/ml-model/info.md` - ML Model Storage
**Depends On**:
- `/backend/database/info.md` (MLModel table)
- `/backend/ai/info.md` (model loading)

**Referenced By**:
- `/backend/utils/info.md` (model_loader.py)
- `/backend/pipelines/info.md` (ML inference)

---

### `/scraper/info.md` - Spot Price Scraper
**Depends On**: External AWS Spot Instance Advisor

**Referenced By**:
- `/backend/pipelines/info.md` (price data source)
- `/backend/utils/info.md` (health checks verify freshness)

---

### `/scripts/info.md` - Utility Scripts
**Depends On**:
- `/backend/database/info.md` (database operations)

**Referenced By**:
- Deployment processes
- Maintenance tasks

---

## Critical Dependency Chains (Complete Flows)

### Chain 1: AWS Account Onboarding (8 modules involved)

```
/frontend/src/components/info.md (ClientSetup.jsx)
  → User clicks "Start CloudFormation Setup" button
  ↓
/frontend/src/services/info.md (apiClient.js)
  → POST /client/onboarding/create
  ↓
/backend/api/info.md (onboarding_routes.py:73)
  → Create pending account record
  ↓
/backend/database/info.md (Account model)
  → INSERT with status='pending', account_id='pending-{uuid}'
  ↓
[User deploys CloudFormation in AWS]
  ↓
/frontend/src/components/info.md (ClientSetup.jsx:verifyConnection)
  → User clicks "Verify Connection" button
  ↓
/backend/api/info.md (onboarding_routes.py:453)
  → POST /client/onboarding/{id}/verify
  → Calls AWS STS AssumeRole with ExternalID
  → Global uniqueness check ⚠️ PROTECTED
  → UPDATE Account: status='connected', account_id='123456789012'
  → Trigger discovery_worker (BackgroundTasks)
  ↓
/backend/workers/info.md (discovery_worker.py:229)
  → Scan AWS EC2 instances across regions
  → UPSERT instances table
  → UPDATE Account: status='active'
  → Trigger component_health_checks
  ↓
/backend/utils/info.md (component_health_checks.py:437)
  → Run all health checks
  → Return metrics
  ↓
/frontend/src/components/info.md (ClientSetup.jsx:startPollingAccountStatus)
  → Poll GET /client/onboarding/{id}/discovery every 3 seconds
  → Detect status='active'
  → Auto-redirect to /client dashboard
```

**Modules Involved**: 8
**Protected Zones**: 2 (global uniqueness, status transition)
**Database Tables**: 2 (accounts, instances)

---

### Chain 2: Spot Instance Interruption (Zero Downtime) (5 modules involved)

```
AWS EventBridge
  → Rebalance Notice event
  ↓
/backend/workers/info.md (event_processor.py:handle_rebalance_notice)
  → Extract pool_id="us-east-1a:c5.large"
  → Call RiskManager.register_risk_event()
  ↓
/backend/logic/info.md (RiskManager)
  → INSERT into global_risk_events
  → Flag pool as poisoned for 15 days
  ↓
/backend/workers/info.md (event_processor.py)
  → Launch replica in different AZ
  → INSERT Instance with is_replica=True, replica_expiry=now+6hr
  ↓
[2 hours later: Termination Notice OR 6hr timer expires]
  ↓
/backend/workers/info.md (event_processor.py:handle_termination_notice)
  → Check for replica
  → IF replica ready: Promote replica, mark primary terminated
    → downtime_seconds = 0 ✅
  → ELSE: Emergency launch, log downtime ⚠️
  ↓
/backend/database/info.md (DowntimeLog model)
  → INSERT if emergency launch (SLA tracking)
```

**Modules Involved**: 5
**Zero Downtime**: Achieved if replica ready
**SLA Impact**: Logged if emergency launch required

---

### Chain 3: ML Model Deployment (6 modules involved)

```
/backend/ml_models/info.md
  → Model trained and exported
  ↓
/ml-model/info.md
  → Model file stored with SHA256 hash
  ↓
/backend/database/info.md (MLModel table)
  → INSERT with status='CANDIDATE'
  ↓
[Testing phase]
  → UPDATE status='TESTING'
  → Run experiments
  ↓
/backend/database/info.md (ExperimentLog table)
  → INSERT experiment results
  ↓
[Graduation]
  → UPDATE status='GRADUATED' → 'ENABLED'
  → Set is_active_prod=True (only ONE can be True)
  ↓
/backend/pipelines/info.md (linear_optimizer.py)
  → Load active production model
  ↓
/backend/ai/info.md
  → Inference using enabled model
  ↓
/backend/database/info.md (ExperimentLog)
  → Log prediction decision
```

**Modules Involved**: 6
**Governance Flow**: CANDIDATE → TESTING → GRADUATED → ENABLED → ARCHIVED
**Constraint**: Only one `is_active_prod=True` at a time

---

## Protected Zones Cross-Reference Map

All protected zones are documented in `/progress/regression_guard.md`. Here's the cross-reference:

### Protected Zone 1: Credential Encryption
**Files Protected**:
- `/backend/utils/crypto.py:17` (encrypt_credential)
- `/backend/utils/crypto.py:23` (decrypt_credential)

**Referenced By**:
- `/backend/api/info.md` (uses encryption)
- `/backend/workers/info.md` (uses decryption)
- `/backend/utils/info.md` (documents protection)

**Reason**: MUST preserve backward compatibility for existing encrypted credentials

---

### Protected Zone 2: Global Uniqueness Check
**Files Protected**:
- `/backend/api/onboarding_routes.py:495` (uniqueness query)
- `/backend/database/models.py:39` (account_id UNIQUE constraint)

**Referenced By**:
- `/backend/api/info.md` (documents check)
- `/backend/database/info.md` (schema constraint)
- `/scenarios/client_onboarding_flow.md` (security note)

**Reason**: Prevents AWS account takeover (security vulnerability)

---

### Protected Zone 3: Status Transitions
**Files Protected**:
- `/backend/workers/discovery_worker.py:306` (connected → active)
- `/backend/database/models.py:43` (status field definition)

**Referenced By**:
- `/backend/workers/info.md` (documents transitions)
- `/backend/database/info.md` (status values)
- `/frontend/src/components/info.md` (UI depends on exact values)

**Reason**: Dashboard and AuthGateway depend on exact status values

---

### Protected Zone 4: DELETE Endpoint Status Code
**Files Protected**:
- `/backend/api/client_routes.py:84` (DELETE account, returns 200)

**Referenced By**:
- `/backend/api/info.md` (documents status code)
- `/frontend/src/components/info.md` (expects 200)
- `/progress/fixed_issues_log.md` (P-2025-12-25-003)

**Reason**: Frontend expects 200, not 204 (recent fix)

---

## Module Enhancement Status

### ✅ Comprehensive (500+ lines)
1. `/backend/api/info.md` (530 lines)
2. `/frontend/src/components/info.md` (800 lines)
3. `/backend/workers/info.md` (764 lines)

### ✅ Complete (200+ lines)
4. `/backend/database/info.md` (222 lines)
5. `/backend/utils/info.md` (319 lines)
6. `/info.md` (ROOT - 580+ lines)

### ⏳ Basic (< 200 lines, needs enhancement)
**Backend** (8 modules):
7. `/backend/ai/info.md`
8. `/backend/auth/info.md`
9. `/backend/decision_engine/info.md`
10. `/backend/executor/info.md`
11. `/backend/jobs/info.md`
12. `/backend/logic/info.md`
13. `/backend/pipelines/info.md`
14. `/backend/websocket/info.md`

**Frontend** (7 modules):
15. `/frontend/src/services/info.md`
16. `/frontend/src/context/info.md`
17. `/frontend/src/pages/info.md`
18. `/frontend/src/layouts/info.md`
19. `/frontend/src/config/info.md`
20. `/frontend/src/lib/info.md`
21. `/frontend/src/assets/info.md`
22. `/frontend/src/components/Lab/info.md`

**Infrastructure** (5 modules):
23. `/database/info.md`
24. `/database/migrations/info.md`
25. `/ml-model/info.md`
26. `/scraper/info.md`
27. `/scripts/info.md`

**Governance** (already comprehensive):
28. `/instructions/info.md` ✅
29. `/index/info.md` ✅
30. `/progress/info.md` ✅
31. `/problems/info.md` ✅
32. `/scenarios/info.md` ✅
33. `/docs/info.md`

**Root** (2 modules):
34. `/frontend/info.md`
35. `/frontend/public/info.md`
36. `/backend/info.md`

**TOTAL**: 37 info.md files
- Comprehensive: 6 files (16%)
- Needs Enhancement: 31 files (84%)

---

## Priority Enhancement Order (Based on Impact)

### Priority 1: HIGH IMPACT (Business Logic & Security)
1. `/backend/logic/info.md` - RiskManager, business rules
2. `/backend/auth/info.md` - Authentication, JWT, security
3. `/backend/pipelines/info.md` - LINEAR/CLUSTER/KUBERNETES pipelines

### Priority 2: MEDIUM IMPACT (Frontend Integration)
4. `/frontend/src/services/info.md` - API client layer
5. `/frontend/src/context/info.md` - State management
6. `/frontend/src/pages/info.md` - Page components

### Priority 3: MEDIUM IMPACT (Infrastructure)
7. `/database/info.md` - Migration scripts
8. `/ml-model/info.md` - Model storage
9. `/scraper/info.md` - Price scraper

### Priority 4: LOW IMPACT (Supporting Modules)
10. Remaining backend modules (ai, decision_engine, executor, jobs, websocket)
11. Remaining frontend modules (layouts, config, lib, assets, Lab)
12. Scripts and docs

---

## Cross-Reference Validation Checklist

When updating ANY info.md file, verify these cross-references:

✅ **Dependencies Section**:
- Lists all modules it depends on
- Each dependency has corresponding "Referenced By" in target module

✅ **Recent Changes Section**:
- References Problem ID if applicable (P-YYYY-MM-DD-NNN)
- Entry exists in `/index/recent_changes.md`
- Entry exists in `/progress/fixed_issues_log.md` (if fix)

✅ **API/Database/Frontend Mappings**:
- API endpoints reference: Backend file:line, Database tables, Frontend components
- Database models reference: APIs using them, Workers modifying them, Frontend displaying them
- Frontend components reference: API endpoints called, Database tables involved

✅ **Protected Zones**:
- If module has protected code, reference in `/progress/regression_guard.md`
- Protected zones documented in module's info.md

✅ **Scenarios**:
- If module is part of user flow, reference in `/scenarios/*.md`
- Scenario files reference module's info.md

---

_Last Updated: 2025-12-25_
_Authority: HIGH - Use for dependency analysis and impact assessment_
_Next Steps: Enhance remaining 31 modules to comprehensive standard_
