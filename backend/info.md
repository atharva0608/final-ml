# Backend Module

## Purpose

FastAPI backend application providing REST APIs, background workers, and business logic for the spot optimizer platform.

**Last Updated**: 2025-12-25

---

## Directory Structure

```
backend/
├── api/              - REST API endpoints
├── workers/          - Background task workers
├── utils/            - Shared utilities
├── database/         - Database models and connection
├── ai/              - AI/ML model integration
├── auth/            - Authentication modules
├── decision_engine/ - Decision-making logic
├── executor/        - Task execution engine
├── jobs/            - Scheduled jobs
├── logic/           - Business logic
├── ml_models/       - ML model definitions
├── pipelines/       - Data processing pipelines
├── websocket/       - WebSocket handlers
├── main.py          - FastAPI application entry point
└── requirements.txt - Python dependencies
```

---

## Key Files

### main.py
**Purpose**: FastAPI application entry point
**Responsibilities**:
- Application initialization
- Route registration
- CORS configuration
- Middleware setup

**Dependencies**:
- FastAPI framework
- All API routers from `api/`
- Database connection

**Entry Point**: `uvicorn main:app --reload`

### requirements.txt
**Purpose**: Python package dependencies
**Last Updated**: 2025-11-26
**Key Packages**:
- fastapi
- uvicorn
- sqlalchemy
- boto3
- python-jose (JWT)
- passlib (password hashing)
- cryptography (encryption)

---

## Submodules

See individual `info.md` files in each subdirectory:
- `/backend/api/info.md` - API routes
- `/backend/workers/info.md` - Background workers
- `/backend/utils/info.md` - Utility functions
- `/backend/database/info.md` - Database models

---

## Recent Changes

### 2025-12-25: Governance Structure Implementation
**Files Added**: None (documentation only)
**Reason**: Established info.md structure for LLM governance
**Impact**: Documentation improvements

### 2025-12-25: Critical Bug Fixes
**Files Modified**:
- `api/client_routes.py` - DELETE endpoint status code fix
- `workers/discovery_worker.py` - Health check trigger
**Reason**: Fix HTTP protocol error and dashboard data population
**Impact**: Production stability improvements
**Reference**: `/progress/fixed_issues_log.md#P-2025-12-25-003`

### 2025-11-26: Session Management Fixes
**Files Modified**: `api/auth.py`
**Reason**: Token expiration was too short (5 minutes)
**Impact**: User experience improvement
**Reference**: `/docs/legacy/fixes/BACKEND_FIXES_2025-11-26.md`

---

## Configuration

### Environment Variables Required

```bash
DATABASE_URL=mysql://user:pass@localhost/dbname
JWT_SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here
AWS_REGION=us-east-1
```

See: `.env.example` for complete list

---

## Running the Backend

### Development
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Production
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Testing

### Run Tests
```bash
pytest tests/
```

### Test Coverage
```bash
pytest --cov=. tests/
```

---

## Dependencies

**Requires**:
- Python 3.9+
- MySQL or PostgreSQL database
- AWS credentials (for cloud operations)

**Required By**:
- Frontend (consumes REST APIs)
- Discovery workers (background tasks)

---

## Architecture Notes

### Request Flow
```
Client Request
  ↓
FastAPI Router (api/)
  ↓
Business Logic (logic/ or direct)
  ↓
Database (database/models.py)
  ↓
Response
```

### Background Tasks
```
API Endpoint triggers
  ↓
BackgroundTasks.add_task()
  ↓
Worker function (workers/)
  ↓
Updates database
```

---

_Last Updated: 2025-12-25_
_See: `/index/system_index.md` for high-level architecture_
