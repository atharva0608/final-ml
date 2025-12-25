# Backend API Routes

## Purpose

REST API endpoints for all platform functionality including authentication, client management, admin operations, and AWS integration.

**Last Updated**: 2025-12-25

---

## Files

### auth.py
**Purpose**: Authentication and authorization
**Lines**: ~200
**Endpoints**:
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/me` - Get current user

**Key Functions**:
- `create_access_token()` - Generate JWT token (24-hour expiration)
- `get_current_active_user()` - Dependency for protected routes
- `verify_password()` - Password verification

**Dependencies**:
- python-jose (JWT)
- passlib (bcrypt)
- database/models.py (User model)

**Recent Changes**:
- 2025-11-26: Fixed token expiration (was 5 minutes, now 24 hours)

**Reference**: `/scenarios/auth_flow.md`

---

### client_routes.py
**Purpose**: Client dashboard and account management
**Lines**: ~400
**Endpoints**:
- `GET /client/accounts` - List connected AWS accounts
- `DELETE /client/accounts/{id}` - Disconnect account
- `GET /client/dashboard` - Dashboard data
- `GET /client/summary` - Lightweight summary

**Key Functions**:
- `get_connected_accounts()` - List accounts (line 42)
- `disconnect_account()` - Delete account with cascade (line 85)
- `get_client_dashboard()` - Aggregate dashboard data (line 147)

**Dependencies**:
- database/models.py (Account, Instance, ExperimentLog)
- utils/system_logger.py

**Recent Changes**:
- 2025-12-25: Added DELETE endpoint with HTTP 200 status code
- 2025-12-25: Added `setup_required` flag to dashboard response
- 2025-12-25: Added `/accounts` endpoint for multi-account support

**Reference**: `/index/feature_index.md#account-management`

---

### onboarding_routes.py
**Purpose**: AWS account connection workflows
**Lines**: ~900
**Endpoints**:
- `POST /onboarding/create` - Create onboarding request
- `GET /onboarding/template/{id}` - CloudFormation template
- `POST /onboarding/{id}/verify` - Verify IAM role
- `POST /onboarding/connect/credentials` - Connect with access keys
- `GET /onboarding/{id}/discovery` - Discovery status
- `POST /onboarding/{id}/rediscover` - Trigger re-scan

**Key Functions**:
- `create_onboarding_request()` - Generate External ID (line 41)
- `get_cloudformation_template()` - Generate IAM template (line 274)
- `verify_connection()` - Verify CloudFormation setup (line 453)
- `connect_with_credentials()` - Direct credential connection (line 94)

**Dependencies**:
- boto3 (AWS SDK)
- utils/crypto.py (encryption)
- workers/discovery_worker.py (background tasks)

**Recent Changes**:
- 2025-12-25: Added global uniqueness check for AWS Account IDs (security fix)
- 2025-12-25: Added `connection_method` field to track IAM role vs credentials

**Reference**: `/scenarios/client_onboarding_flow.md`

---

### admin.py
**Purpose**: Admin operations and system management
**Lines**: ~700
**Endpoints**:
- Admin dashboard
- User management
- System monitoring
- Configuration

**Key Functions**:
- Admin-only operations
- System health checks
- User CRUD operations

**Dependencies**:
- database/models.py
- auth.py (admin role verification)

**Recent Changes**: None recent

---

### lab.py
**Purpose**: ML model experimentation and lab features
**Lines**: ~800
**Endpoints**:
- Model training
- Experiment tracking
- Model comparison

**Key Functions**:
- ML model management
- Experiment logging
- Performance tracking

**Dependencies**:
- ai/ module
- ml_models/ module

**Recent Changes**: None recent

---

### metrics_routes.py
**Purpose**: Metrics and analytics
**Lines**: ~500
**Endpoints**:
- System metrics
- Usage analytics
- Performance data

**Key Functions**:
- Metrics aggregation
- Analytics queries

**Dependencies**:
- database/models.py

**Recent Changes**: None recent

---

### ai_routes.py
**Purpose**: AI/ML API endpoints
**Lines**: ~600
**Endpoints**:
- Model inference
- Prediction requests

**Key Functions**:
- AI model serving
- Prediction processing

**Dependencies**:
- ai/ module

**Recent Changes**: None recent

---

### governance_routes.py
**Purpose**: Governance and approval workflows
**Lines**: ~350
**Endpoints**:
- Approval requests
- Governance policies

**Key Functions**:
- Approval management
- Policy enforcement

**Dependencies**:
- database/models.py

**Recent Changes**: None recent

---

### pipeline_routes.py
**Purpose**: Data pipeline management
**Lines**: ~200
**Endpoints**:
- Pipeline execution
- Pipeline status

**Key Functions**:
- Pipeline orchestration

**Dependencies**:
- pipelines/ module

**Recent Changes**: None recent

---

### websocket_routes.py
**Purpose**: WebSocket connections for real-time updates
**Lines**: ~100
**Endpoints**:
- WebSocket connections

**Key Functions**:
- Real-time data streaming

**Dependencies**:
- websocket/ module

**Recent Changes**: None recent

---

### approval_routes.py, storage_routes.py, waste_routes.py
**Purpose**: Specialized feature endpoints
**Lines**: ~200 each

**Recent Changes**: None recent

---

## API Design Patterns

### Authentication
All protected routes use:
```python
current_user: User = Depends(get_current_active_user)
```

### Database Sessions
All routes use:
```python
db: Session = Depends(get_db)
```

### Error Handling
```python
try:
    # Operation
except HTTPException:
    raise
except Exception as e:
    logger.error(...)
    raise HTTPException(status_code=500, detail=str(e))
```

---

## Recent Changes Summary

### 2025-12-25
1. **client_routes.py**:
   - Added DELETE `/accounts/{id}` endpoint (HTTP 200)
   - Added GET `/accounts` endpoint
   - Added `setup_required` flag

2. **onboarding_routes.py**:
   - Added global uniqueness check (security)
   - Added `connection_method` tracking

**Reason**: Multi-account support and security improvements
**Impact**: HIGH - All client flows affected
**Reference**: `/progress/fixed_issues_log.md`

### 2025-11-26
1. **auth.py**:
   - Fixed token expiration (5min → 24hr)

**Reason**: User experience - sessions expired too quickly
**Impact**: CRITICAL - All authenticated users
**Reference**: `/docs/legacy/fixes/BACKEND_FIXES_2025-11-26.md`

---

## Testing

### Manual Testing
```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -d '{"username":"test", "password":"test"}'

# List accounts (with token)
curl http://localhost:8000/client/accounts \
  -H "Authorization: Bearer {token}"
```

### Automated Tests
```bash
pytest tests/api/
```

---

## Dependencies

**Requires**:
- FastAPI framework
- Database connection
- Authentication system
- Background workers

**Required By**:
- Frontend application
- External integrations

---

## Security Notes

### Protected Endpoints
All endpoints except `/auth/login` require authentication.

### Role-Based Access
- Client endpoints: `role=client`
- Admin endpoints: `role=admin`

### Input Validation
All endpoints use Pydantic models for request validation.

---

_Last Updated: 2025-12-25_
_See: `/index/feature_index.md` for complete API catalog_
