# Backend - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains all backend services including API routes, business logic services, background workers, intelligence modules, data scrapers, core system components, database models, Pydantic schemas, and utility functions for the Spot Optimizer platform.

---

## Module Structure

| Subfolder | Module Type | Purpose | Components Count | Key Module IDs |
|-----------|------------|---------|-----------------|----------------|
| api/ | REST API Routes | HTTP endpoint handlers | 8 routes files | CORE-API |
| services/ | Business Logic | Service layer for business operations | 8 service files | SVC-* |
| workers/ | Background Jobs | Celery workers for async tasks | 4 worker files | WORK-* |
| modules/ | Intelligence | AI/ML optimization modules | 6 module files | MOD-* |
| scrapers/ | Data Collection | AWS data collection services | 2 scraper files | SVC-SCRAPE-*, SVC-PRICE-* |
| core/ | Core System | Core decision and execution engines | 3 core files | CORE-* |
| models/ | Database Models | SQLAlchemy ORM models | 9+ model files | MODEL-* |
| schemas/ | Pydantic Schemas | Request/Response validation schemas | 7+ schema files | SCHEMA-* |
| utils/ | Utilities | Helper functions and utilities | 3+ util files | UTIL-* |

---

## Component Table

| Subfolder | File Count | Status | Dependencies |
|-----------|-----------|--------|--------------|
| api/ | 0 | Pending | services/, schemas/ |
| services/ | 0 | Pending | models/, schemas/, modules/ |
| workers/ | 0 | Pending | services/, modules/, scrapers/ |
| modules/ | 0 | Pending | models/, utils/ |
| scrapers/ | 0 | Pending | boto3, requests |
| core/ | 0 | Pending | services/, modules/, workers/ |
| models/ | 0 | Pending | SQLAlchemy |
| schemas/ | 0 | Pending | Pydantic |
| utils/ | 0 | Pending | None |

---

## Recent Changes

### [2025-12-31 12:36:00] - Initial Backend Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for backend components
**Impact**: Created 9 subdirectories for backend organization
**Files Modified**:
- Created backend/api/
- Created backend/services/
- Created backend/workers/
- Created backend/modules/
- Created backend/scrapers/
- Created backend/core/
- Created backend/models/
- Created backend/schemas/
- Created backend/utils/
- Created backend/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- All services depend on models/ and schemas/
- Workers depend on services/ and modules/
- Core components depend on services/ and modules/
- API routes depend on services/ and schemas/

### External Dependencies
- **Framework**: FastAPI, Uvicorn
- **ORM**: SQLAlchemy, Alembic
- **Validation**: Pydantic
- **Async Tasks**: Celery, Redis
- **AWS SDK**: boto3
- **ML**: scikit-learn, pandas, numpy
- **Security**: bcrypt, PyJWT
- **HTTP**: requests

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         API Layer (CORE-API)                 │
│                     (FastAPI Routes in api/)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    Service Layer                             │
│              (Business Logic in services/)                   │
└─────┬────────────────────────────────────────┬──────────────┘
      │                                        │
┌─────▼───────────┐                  ┌────────▼──────────────┐
│  Core Systems   │                  │  Intelligence Modules │
│  (core/)        │                  │  (modules/)           │
│  - CORE-DECIDE  │                  │  - MOD-SPOT-01        │
│  - CORE-EXEC    │                  │  - MOD-PACK-01        │
└─────────────────┘                  │  - MOD-SIZE-01        │
                                     │  - MOD-AI-01          │
                                     └───────────────────────┘
      │
┌─────▼──────────────────────────────────────────────────────┐
│                    Data Layer                                │
│              (SQLAlchemy Models in models/)                  │
│              (Pydantic Schemas in schemas/)                  │
└──────────────────────────────────────────────────────────────┘
      │
┌─────▼──────────────────────────────────────────────────────┐
│                Background Workers (Celery)                   │
│              (workers/)                                      │
│  - WORK-DISC-01 (Discovery)                                 │
│  - WORK-OPT-01 (Optimizer)                                  │
│  - WORK-HIB-01 (Hibernation)                                │
│  - WORK-RPT-01 (Reports)                                    │
└──────────────────────────────────────────────────────────────┘
```

---

## Development Guidelines

1. **API Routes**: All routes in `api/` should delegate to services in `services/`
2. **Service Layer**: Business logic goes in `services/`, never in routes
3. **Workers**: Background tasks use Celery workers in `workers/`
4. **Intelligence**: ML/optimization logic goes in `modules/`
5. **Data Models**: SQLAlchemy models in `models/`, Pydantic schemas in `schemas/`
6. **Utilities**: Shared helper functions in `utils/`

---

## Testing Requirements

- Unit tests for all services
- Integration tests for API endpoints
- Worker task tests with mocked dependencies
- Module tests with sample data
- Minimum 80% code coverage required
