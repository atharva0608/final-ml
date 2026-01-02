# Core - Component Information

> **Last Updated**: 2026-01-02 15:30:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains core system components including the decision engine, action executor, and API gateway that orchestrate the entire platform.

---

## Component Table

| File Name | Component ID | Purpose | Key Functions | Dependencies | Status |
|-----------|-------------|---------|---------------|--------------|--------|
| config.py | CORE-CONFIG | Configuration management | settings, get_settings(), is_production() | pydantic-settings | Complete |
| crypto.py | CORE-CRYPTO | Cryptography utilities | hash_password(), create_access_token(), generate_api_key() | passlib, jose | Complete |
| validators.py | CORE-VALID | Custom validation functions | validate_aws_*(), validate_cluster_name(), validate_password_strength() | pytz, re | Complete |
| exceptions.py | CORE-EXCEPT | Custom exception classes | All custom exceptions | fastapi | Complete |
| dependencies.py | CORE-DEPS | FastAPI dependencies | get_current_user(), verify_cluster_ownership() | fastapi, models/* | Complete |
| logger.py | CORE-LOG | Structured logging | setup_logging(), StructuredLogger, log_*() | logging, json | Complete |
| decision_engine.py | CORE-DECIDE | Conflict resolution and decision making | evaluate_action_plan(), resolve_conflicts() | modules/*, services/* | ✅ Complete |
| action_executor.py | CORE-EXEC | Execute optimization actions via AWS/K8s | execute_action_plan(), execute_action() | scripts/aws/*, boto3, kubernetes | ✅ Complete |
| health_service.py | CORE-HEALTH | System health monitoring | check_overall_health(), check_readiness(), check_liveness() | database, redis, celery | ✅ Complete |
| api_gateway.py | CORE-API | FastAPI application and middleware | app, configure_cors(), configure_auth() | api/*, FastAPI | Complete |

---

## Recent Changes

### [2026-01-02 15:30:00] - Phase 7: Core System Components Implementation Complete
**Changed By**: LLM Agent
**Reason**: Complete all 3 core system components for Phase 7
**Impact**: Full core component implementation totaling ~1,400 lines of code
**Files Modified**:
- Created backend/core/decision_engine.py (~650 lines) - Central decision-making and conflict resolution
- Created backend/core/action_executor.py (~550 lines) - AWS/K8s action execution engine
- Created backend/core/health_service.py (~400 lines) - System health monitoring service
- Updated backend/core/INFO.md (this file)
**Feature IDs Affected**: CORE-DECIDE, CORE-EXEC, CORE-HEALTH
**Breaking Changes**: No
**Key Features Implemented**:
- Policy-based action validation with risk thresholds
- Multi-action conflict detection and resolution
- Action prioritization by urgency and savings impact
- Approval workflow integration
- Phased execution plans with delays
- AWS Spot instance replacement with STS role assumption
- Instance right-sizing and node consolidation
- Audit logging for all actions
- Comprehensive health checks (database, Redis, Celery, AWS, data freshness)
- Readiness and liveness probes for K8s
- System metrics collection

### [2025-12-31 12:36:00] - Initial Core Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for core system components
**Impact**: Created backend/core/ directory for orchestration components
**Files Modified**:
- Created backend/core/
- Created backend/core/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

### [2025-12-31 13:00:00] - Phase 3: Core Utilities Implemented
**Changed By**: LLM Agent
**Reason**: Complete Phase 3 - Implement foundational core utilities
**Impact**: Complete set of core utilities for configuration, security, validation, and logging
**Files Modified**:
- Created backend/core/__init__.py
- Created backend/core/config.py
- Created backend/core/crypto.py
- Created backend/core/validators.py
- Created backend/core/exceptions.py
- Created backend/core/dependencies.py
- Created backend/core/logger.py
**Feature IDs Affected**: N/A (Core infrastructure)
**Breaking Changes**: No

### [2025-12-31 13:05:00] - Phase 4: FastAPI Application Gateway
**Changed By**: LLM Agent
**Reason**: Complete FastAPI application with middleware and error handling
**Impact**: Production-ready FastAPI app with CORS, logging, exception handlers
**Files Modified**:
- Created backend/core/api_gateway.py
**Feature IDs Affected**: N/A (Core infrastructure)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- `backend/api/` - API routes
- `backend/services/` - Business logic
- `backend/modules/` - Intelligence modules
- `backend/workers/` - Background workers
- `backend/models/` - Database models
- `scripts/aws/` - AWS automation scripts

### External Dependencies
- **Framework**: FastAPI, Uvicorn
- **Middleware**: CORS, JWT authentication
- **Rate Limiting**: slowapi or custom
- **Logging**: Python logging, structlog

---

## Component Responsibilities

### decision_engine.py (CORE-DECIDE):
**Purpose**: Aggregate recommendations and resolve conflicts

**Key Function**: `resolve_conflicts()`

**Process**:
1. Receive recommendations from multiple modules:
   - MOD-SPOT-01: Spot instance suggestions
   - MOD-PACK-01: Pod migration plans
   - MOD-SIZE-01: Right-sizing recommendations
2. Apply priority rules:
   - **Stability > Savings** (never sacrifice stability)
   - Block deletions if replacement node is risky
   - Respect PodDisruptionBudgets
   - Enforce safety buffer (20% headroom)
3. Generate final action plan JSON:
   ```json
   {
     "actions": [
       {
         "type": "launch_spot",
         "instance_type": "c5.xlarge",
         "az": "us-east-1b",
         "count": 2
       },
       {
         "type": "evict_pod",
         "pod_name": "app-xyz-123",
         "namespace": "production",
         "grace_period": 30
       }
     ],
     "estimated_savings": 45.50,
     "risk_score": 0.15
   }
   ```

**Decision Rules**:
- Never terminate nodes with critical pods
- Never exceed max budget
- Always maintain minimum node count
- Prefer diversified instance types
- Avoid recently flagged Spot pools

---

### action_executor.py (CORE-EXEC):
**Purpose**: Execute optimization actions via hybrid AWS/Kubernetes routing

**Key Functions**:
- `execute_action_plan()`: Main orchestration
- `route_action_execution()`: Route to AWS or K8s layer
- `execute_aws_action()`: Direct AWS execution via boto3
- `queue_for_agent()`: Queue K8s actions for Agent

**Hybrid Routing Logic**:
```python
for action in action_plan['actions']:
    if action['type'] in ['terminate_instance', 'launch_spot', 'detach_volume', 'update_asg']:
        # AWS Layer - Execute directly via Boto3
        result = execute_aws_action(action)
    elif action['type'] in ['evict_pod', 'cordon_node', 'drain_node', 'label_node']:
        # Kubernetes Layer - Queue for Agent
        result = queue_for_agent(action)
```

**AWS Actions** (Direct execution):
- `terminate_instance` → `scripts/aws/terminate_instance.py`
- `launch_spot` → `scripts/aws/launch_spot.py`
- `detach_volume` → `scripts/aws/detach_volume.py`
- `update_asg` → `scripts/aws/update_asg.py`

**Kubernetes Actions** (Queued for Agent):
- `evict_pod` → Insert into `agent_action` table
- `cordon_node` → Insert into `agent_action` table
- `drain_node` → Insert into `agent_action` table
- `label_node` → Insert into `agent_action` table

**SAFE_MODE**:
- Check Redis flag: `SAFE_MODE`
- If `TRUE`, run all actions in DryRun mode
- Log what would happen without making changes
- Used for testing and validation

**Audit Trail**:
- All actions logged to `audit_logs` table
- Includes: actor, timestamp, action type, result, duration
- Immutable records for compliance

---

### api_gateway.py (CORE-API):
**Purpose**: FastAPI application configuration and middleware

**Responsibilities**:
- Create FastAPI app instance
- Configure CORS middleware
- Configure JWT authentication middleware
- Configure rate limiting
- Configure request/response logging
- Mount all API route modules
- Configure WebSocket routes
- Configure error handlers

**Middleware Stack**:
```
Request
  ↓
CORS Middleware
  ↓
Rate Limiting Middleware
  ↓
JWT Authentication Middleware
  ↓
Request Logging Middleware
  ↓
Route Handler (api/*)
  ↓
Response Logging Middleware
  ↓
Response
```

**CORS Configuration**:
```python
CORS(
    allow_origins=["http://localhost:3000", "https://app.spotoptimizer.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
```

**JWT Middleware**:
- Verify JWT token on protected routes
- Extract user context from token
- Check token blacklist (Redis)
- Inject user context into request state

**Rate Limiting**:
- 100 requests per minute per IP (default)
- 1000 requests per minute for authenticated users
- 10 requests per minute for auth endpoints
- Return 429 Too Many Requests on limit exceeded

**Error Handlers**:
- 400 Bad Request → Validation errors
- 401 Unauthorized → Missing/invalid token
- 403 Forbidden → Insufficient permissions
- 404 Not Found → Resource not found
- 429 Too Many Requests → Rate limit exceeded
- 500 Internal Server Error → Unhandled exceptions

**Health Check**:
- `GET /health` → `{"status": "healthy", "timestamp": "..."}`
- `GET /health/detailed` → Database, Redis, Celery status

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   CORE-API (api_gateway.py)              │
│              FastAPI + Middleware + Routes               │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┴────────────────┐
        │                                │
┌───────▼─────────┐           ┌─────────▼────────┐
│  CORE-DECIDE    │           │   Services       │
│ Decision Engine │◄──────────┤  Business Logic  │
└───────┬─────────┘           └──────────────────┘
        │                                ▲
        │ Action Plan                    │
        │                                │
┌───────▼─────────┐           ┌─────────┴────────┐
│   CORE-EXEC     │           │   Intelligence   │
│ Action Executor │◄──────────┤    Modules       │
└───────┬─────────┘           └──────────────────┘
        │
        ├─→ AWS Scripts (boto3)
        └─→ Agent Actions Queue (K8s)
```

---

## Testing Requirements

- Unit tests for decision engine logic
- Integration tests for action executor
- API gateway middleware tests
- End-to-end tests for complete flows
- Load tests for API gateway (1000 req/s)
- DryRun mode validation tests
