# System Index

## Purpose

High-level architectural map of the entire system.

**Last Updated**: 2025-12-25

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│  React SPA (Client & Admin Views)                          │
│  - Client Dashboard (AWS Account Management)               │
│  - Admin Dashboard (System Monitoring)                     │
│  - Authentication UI                                       │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/REST
┌────────────────────▼────────────────────────────────────────┐
│                        BACKEND                              │
│  FastAPI Application                                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ API Layer                                            │  │
│  │ - /api/auth - Authentication & Authorization         │  │
│  │ - /api/client - Client Dashboard & Account Mgmt     │  │
│  │ - /api/onboarding - AWS Account Connection          │  │
│  │ - /api/admin - Admin Operations                     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Workers (Background Tasks)                           │  │
│  │ - discovery_worker - AWS Resource Discovery         │  │
│  │ - health_monitor - System Health Checks             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Utils                                                │  │
│  │ - crypto - Credential encryption/decryption          │  │
│  │ - component_health_checks - Health check logic       │  │
│  │ - system_logger - Structured logging                │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │ SQL
┌────────────────────▼────────────────────────────────────────┐
│                      DATABASE                               │
│  MySQL/PostgreSQL                                           │
│  - users - User accounts (client & admin)                  │
│  - accounts - AWS Account connections                      │
│  - instances - EC2 Instance inventory                      │
│  - experiment_logs - Optimization history                  │
│  - downtime_logs - SLA tracking                            │
│  - system_logs - Application logs                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Major Components

### Frontend (`/frontend`)

**Technology**: React 18, React Router, Tailwind CSS

**Key Modules**:
- `src/components/` - Reusable UI components
- `src/layouts/` - Page layouts
- `src/services/` - API client
- `src/context/` - React Context (Auth, Model)

**Entry Points**:
- `src/App.jsx` - Main application routing
- `src/index.js` - React DOM entry

**Info**: See `frontend/src/info.md`

### Backend (`/backend`)

**Technology**: FastAPI, SQLAlchemy, Boto3

**Key Modules**:
- `api/` - REST API endpoints
- `workers/` - Background task workers
- `utils/` - Shared utilities
- `database/` - Database models & connection

**Entry Point**: `main.py`

**Info**: See `backend/info.md`

### Database (`/database`)

**Technology**: SQLAlchemy ORM

**Models**: See `database/models.py`

**Migrations**: Alembic (if configured)

**Schema Documentation**: `/docs/legacy/architecture/DATABASE_SCHEMA.md`

---

## Data Flow

### Client Login → Dashboard Flow

```
1. User enters credentials → /api/auth/login
2. Backend validates → returns JWT token
3. Frontend stores token → redirects based on role
4. Client role → AuthGateway checks /client/accounts
5. If accounts exist → /client dashboard
6. If no accounts → /onboarding/setup
```

See: `/scenarios/auth_flow.md`

### AWS Account Connection Flow

```
1. User chooses connection method (CloudFormation or Access Keys)
2. Frontend sends credentials → /api/onboarding/connect
3. Backend validates with AWS STS
4. Creates Account record (status: 'connected')
5. Triggers discovery_worker (background)
6. discovery_worker scans EC2 instances
7. Updates Account status → 'active'
8. Frontend polls /client/accounts
9. Status changes → shows dashboard with data
```

See: `/scenarios/client_onboarding_flow.md`

---

## Security Boundaries

### Authentication

- JWT tokens with 24-hour expiration
- HTTP-only cookies (optional)
- Password hashing: bcrypt

### Authorization

- Role-based access control (RBAC)
- Roles: `client`, `admin`, `super_admin`
- Route protection at API level

### AWS Credentials

- AES-256 encryption for access keys
- Never stored in plaintext
- CloudFormation IAM roles preferred

### Cross-Account Security

- External ID validation for IAM role assumption
- Global uniqueness check for AWS Account IDs
- Per-user account ownership validation

---

## Integration Points

### External Services

1. **AWS Services**
   - STS - AssumeRole for cross-account access
   - EC2 - Instance discovery
   - Pricing - Cost calculations

2. **Database**
   - Connection pooling via SQLAlchemy
   - Transaction management

3. **Background Tasks**
   - FastAPI BackgroundTasks
   - Discovery workers

---

## Deployment Architecture

```
┌─────────────┐
│   Nginx     │ ← Reverse proxy
│   (Port 80) │
└──────┬──────┘
       │
┌──────▼──────────────────┐
│   Frontend (Static)     │
│   Served by Nginx       │
└─────────────────────────┘

┌─────────────────────────┐
│   FastAPI Backend       │
│   (Port 8000)           │
│   Uvicorn ASGI Server   │
└──────┬──────────────────┘
       │
┌──────▼──────────────────┐
│   MySQL Database        │
│   (Port 3306)           │
└─────────────────────────┘
```

---

## Key Directories

```
/frontend
  /src
    /components       - React components
    /services         - API client
    /context          - Global state
    /layouts          - Page layouts

/backend
  /api                - API routes
    /auth.py          - Authentication
    /client_routes.py - Client dashboard
    /onboarding_routes.py - AWS connection
  /workers
    /discovery_worker.py - Resource discovery
    /health_monitor.py   - Health checks
  /utils              - Shared utilities
  /database
    /models.py        - SQLAlchemy models
    /connection.py    - DB connection

/database
  /models.py          - Database schema

/docs
  /legacy             - Historical documentation

/instructions         - LLM governance rules
/index                - System maps (this file)
/progress             - Current state & fixes
/problems             - Known issues
/scenarios            - User flows & business logic
```

---

## Configuration

### Environment Variables

See: `backend/.env.example`

Key variables:
- `DATABASE_URL` - Database connection string
- `JWT_SECRET_KEY` - Token signing secret
- `ENCRYPTION_KEY` - Credential encryption key
- `AWS_REGION` - Default AWS region

---

## Testing

### Backend Tests

Location: `backend/tests/`
Runner: `pytest`

### Frontend Tests

Location: `frontend/src/__tests__/`
Runner: `jest` (if configured)

---

## Monitoring

### Health Checks

Endpoint: `GET /api/health`

Components monitored:
- Database connectivity
- Redis (if enabled)
- Worker heartbeats

### Logging

- Structured logging via `utils/system_logger.py`
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Storage: Database (`system_logs` table) + console

---

_Last Updated: 2025-12-25_
