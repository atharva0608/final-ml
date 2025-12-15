# Sandbox Mode - Integration Complete! 🎉

**Date**: 2025-12-15
**Feature**: Sandbox Mode with Real Backend APIs
**Status**: ✅ Integrated and Ready for Testing

---

## 📋 Summary

Successfully integrated Sandbox Mode with real backend APIs, connecting the React frontend to FastAPI backend endpoints for safe, ephemeral testing of AWS Spot Instance optimization.

---

## 🏗️ Components Implemented

### Backend (FastAPI)

1. **Database Schema** (`database/schema_sandbox.sql`)
   - `sandbox_sessions`: Ephemeral test sessions with encrypted AWS credentials
   - `sandbox_actions`: Action logs (AMI creation, spot launches, etc.)
   - `sandbox_savings`: Projected savings analytics
   - Auto-cleanup indexes for expired sessions

2. **Encryption Utilities** (`backend/utils/crypto.py`)
   - Fernet symmetric encryption for AWS credentials
   - Encrypt/decrypt functions for access keys and secret keys
   - Environment-based encryption key management

3. **Sandbox API** (`backend/api/sandbox.py`)
   - `POST /api/v1/sandbox/sessions` - Create sandbox session
   - `GET /api/v1/sandbox/sessions/{id}` - Get session details
   - `POST /api/v1/sandbox/sessions/{id}/evaluate` - Evaluate instance
   - `GET /api/v1/sandbox/sessions/{id}/actions` - Get action logs
   - `GET /api/v1/sandbox/sessions/{id}/savings` - Get savings report
   - `DELETE /api/v1/sandbox/sessions/{id}` - End session

4. **Main Application** (`backend/main.py`)
   - FastAPI app with CORS middleware
   - Health check endpoint
   - Sandbox router integration
   - Instance evaluation endpoint (placeholder)

### Frontend (React + Vite)

1. **API Service** (`frontend/src/services/api.js`)
   - Centralized API client with error handling
   - All sandbox endpoints exposed as async functions
   - Health check and direct evaluation endpoints

2. **Updated Components**
   - **SandboxDashboard.jsx**: Now uses real APIs instead of mocks
     - Creates sessions via `api.createSandboxSession()`
     - Monitors session expiration
     - Triggers real evaluations
     - Fetches live savings data
   - **SandboxLayout.jsx**: Displays session details (time remaining)
   - **SandboxSetup.jsx**: Collects AWS credentials for session creation

---

## 🔄 Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SANDBOX MODE FLOW                         │
└─────────────────────────────────────────────────────────────┘

1. User Launches Sandbox
   ├─> Frontend: SandboxSetup collects instance details + AWS credentials
   ├─> API: POST /api/v1/sandbox/sessions
   ├─> Backend: Creates session, encrypts credentials, generates temp user
   └─> Response: { session_id, temp_username, temp_password, expires_at }

2. Session Monitoring
   ├─> Frontend: Polls GET /api/v1/sandbox/sessions/{id} every 60s
   ├─> Backend: Returns session details + time_remaining_minutes
   └─> Auto-expires when TTL reached

3. Trigger Evaluation
   ├─> Frontend: User clicks "Trigger Price Drop"
   ├─> API: POST /api/v1/sandbox/sessions/{id}/evaluate
   ├─> Backend: Runs decision pipeline (TODO: integrate with decision_engine_v2)
   ├─> Response: { decision, reason, crash_probability, projected_savings }
   └─> Frontend: Animates blue/green visualization + updates logs

4. End Session
   ├─> Frontend: User clicks "Eject" or session expires
   ├─> API: DELETE /api/v1/sandbox/sessions/{id}
   ├─> Backend: Marks session inactive, triggers cleanup
   └─> Cleanup: Stop spot instances, restart original (TODO: implement)
```

---

## 🚀 Quick Start

### Backend Setup

```bash
# Navigate to backend
cd backend

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env and set:
# - ENCRYPTION_KEY (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# - ENV=TEST
# - API_PORT=8000

# Run backend
python main.py
# OR
uvicorn main:app --reload --port 8000
```

Backend will be available at: **http://localhost:8000**
API docs (Swagger): **http://localhost:8000/docs**

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Set environment variables
cp .env.example .env
# Edit .env and set:
# - VITE_API_URL=http://localhost:8000

# Run development server
npm run dev
```

Frontend will be available at: **http://localhost:5173**

### Testing

1. **Health Check**:
   ```bash
   curl http://localhost:8000/health
   ```

2. **Create Sandbox Session**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/sandbox/sessions \
     -H "Content-Type: application/json" \
     -d '{
       "instance_id": "i-1234567890abcdef0",
       "instance_type": "c5.large",
       "availability_zone": "ap-south-1a",
       "aws_access_key": "AKIA...",
       "aws_secret_key": "...",
       "aws_region": "ap-south-1"
     }'
   ```

3. **Navigate to Sandbox**:
   - Open http://localhost:5173/sandbox
   - Fill in instance details and AWS credentials
   - Click "Launch Sandbox"
   - Trigger evaluation and watch real-time logs

---

## 📝 Configuration

### Backend Environment Variables

```env
# Decision Engine
ENV=TEST
API_HOST=0.0.0.0
API_PORT=8000

# Sandbox Mode
ENCRYPTION_KEY=<generated_fernet_key>

# ML Model (optional for testing)
RISK_MODEL_PATH=../models/production/family_stress_model.pkl
STATIC_DATA_PATH=./data/static_intelligence.json

# AWS (for evaluation)
AWS_REGION=ap-south-1
```

### Frontend Environment Variables

```env
# API URL
VITE_API_URL=http://localhost:8000
```

---

## 🔐 Security Considerations

1. **Credential Encryption**:
   - AWS credentials encrypted with Fernet (symmetric encryption)
   - Encryption key stored in environment variable
   - Credentials never logged or exposed in responses

2. **Session Isolation**:
   - Ephemeral sessions (2-hour TTL)
   - Separate database tables with CASCADE DELETE
   - Temporary usernames/passwords generated per session

3. **CORS**:
   - Currently allows all origins (`allow_origins=['*']`)
   - **TODO**: Restrict in production to frontend domain

4. **Input Validation**:
   - Pydantic models validate all inputs
   - Clear error messages without sensitive info leakage

---

## 🚧 TODO / Future Work

### Critical (MVP)

- [ ] **Integrate with Decision Engine V2**: Connect `/evaluate` endpoint to `decision_engine_v2.DecisionPipeline`
- [ ] **Implement SandboxActuator**: Blue/green switching with real boto3 calls
- [ ] **Implement Cleanup Job**: Background job to clean expired sessions and stop instances
- [ ] **Database Integration**: Replace in-memory storage with PostgreSQL

### Important

- [ ] **Add Authentication**: Require login before creating sandbox sessions
- [ ] **Rate Limiting**: Max 5 active sessions per user
- [ ] **WebSocket Support**: Real-time log streaming instead of polling
- [ ] **Metrics Dashboard**: Prometheus/Grafana for sandbox usage

### Nice-to-Have

- [ ] **Session Pause/Resume**: Allow pausing sandbox session
- [ ] **Cost Estimation**: Show estimated AWS costs before session creation
- [ ] **Export Reports**: Download session report as PDF
- [ ] **Multi-Instance Support**: Test with multiple instances

---

## 🎯 Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Database Schema | ✅ Ready | Created, not applied yet |
| Crypto Utils | ✅ Working | Fernet encryption active |
| Sandbox API | ✅ Working | Mock responses, ready for integration |
| Frontend API Service | ✅ Working | All endpoints exposed |
| SandboxDashboard | ✅ Working | Uses real APIs |
| Backend Integration | ⚠️ Partial | API routes ready, decision engine not connected |
| Authentication | ❌ Not Started | Currently no auth required |
| Cleanup Jobs | ❌ Not Started | Manual cleanup required |

---

## 📊 API Endpoints Summary

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| GET | `/health` | Health check | ✅ Working |
| POST | `/api/v1/evaluate` | Evaluate instance (non-sandbox) | ⚠️ Mock |
| POST | `/api/v1/sandbox/sessions` | Create sandbox session | ✅ Working |
| GET | `/api/v1/sandbox/sessions/{id}` | Get session details | ✅ Working |
| POST | `/api/v1/sandbox/sessions/{id}/evaluate` | Evaluate in sandbox | ⚠️ Mock |
| GET | `/api/v1/sandbox/sessions/{id}/actions` | Get action logs | ⚠️ Mock |
| GET | `/api/v1/sandbox/sessions/{id}/savings` | Get savings report | ⚠️ Mock |
| DELETE | `/api/v1/sandbox/sessions/{id}` | End sandbox session | ✅ Working |

---

## 🐛 Known Issues

1. **In-Memory Storage**: Sessions stored in dictionary, lost on restart
   - **Fix**: Implement PostgreSQL integration

2. **No Cleanup**: Expired sessions not automatically cleaned
   - **Fix**: Implement APScheduler background job

3. **No Real AWS Calls**: Evaluation returns mocks
   - **Fix**: Integrate SandboxActuator with boto3

4. **No Authentication**: Anyone can create sessions
   - **Fix**: Add JWT auth with user/role checks

---

## 📚 Documentation References

- **Backend Architecture**: `BACKEND_ARCHITECTURE.md`
- **Platform Overview**: `PLATFORM_README.md`
- **Frontend Components**: `frontend/src/components/Sandbox/`
- **API Documentation**: http://localhost:8000/docs (when running)

---

## ✅ Testing Checklist

- [x] Backend health check works
- [x] Sandbox session creation returns valid response
- [x] Frontend connects to backend without errors
- [x] Sandbox setup modal appears
- [x] Session expiration countdown works
- [ ] Real AWS evaluation works (pending integration)
- [ ] Blue/green switching works (pending SandboxActuator)
- [ ] Cleanup job removes expired sessions (pending implementation)

---

**Next Steps**: Integrate Decision Engine V2 with Sandbox API and implement SandboxActuator for real AWS operations.

