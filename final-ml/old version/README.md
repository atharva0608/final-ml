# Cloud Cost Optimizer - AWS Spot Instance Management Platform

A production-ready platform for optimizing AWS costs through intelligent Spot instance management, ML-powered risk prediction, and automated workload consolidation.

## 🚀 Features

### Core Capabilities
- **ML-Powered Risk Prediction**: Predicts Spot instance interruption probability using LightGBM models
- **Intelligent Workload Consolidation**: Bin packing algorithm for optimal resource utilization
- **Right-Sizing Engine**: CloudWatch metrics analysis for instance optimization recommendations
- **Lab & Production Modes**: Separate environments for testing and production workloads
- **Real-Time Monitoring**: Live operations dashboard with decision flow visualization
- **Model Governance**: Complete ML model lifecycle management (Candidate → Graduated → Archived)

### Security & Compliance
- Role-based access control (Admin/Client)
- AWS AssumeRole with ExternalID for cross-account access
- Kubernetes safety protocols with tag validation
- Audit logging for all critical operations

## 📋 Prerequisites

- Docker & Docker Compose
- AWS Account with appropriate IAM permissions
- (Optional) Kubernetes cluster for K8s optimization features

## 🏃 Quick Start with Docker

### 1. Clone the Repository
```bash
git clone <repository-url>
cd final-ml
```

### 2. Start All Services
```bash
docker-compose up -d
```

This will start:
- **PostgreSQL** database on port 5432
- **Redis** cache on port 6379
- **Backend API** on http://localhost:8000
- **Frontend** on http://localhost:3000

### 3. Access the Application

Open your browser and navigate to:
- **Frontend**: http://localhost:3000
- **API Documentation**: http://localhost:8000/docs

### 4. Login

**Admin Account:**
- Username: `admin`
- Password: `admin`

**Client Account:**
- Username: `client`
- Password: `client`

## 🔧 Manual Setup (Without Docker)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## 🗄️ Database Configuration

Docker setup automatically configures PostgreSQL.

For manual setup, create `backend/.env`:
```env
DATABASE_URL=postgresql://spotadmin:spotpass123@localhost:5432/spot_optimizer
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-super-secret-jwt-key
ENABLE_TEST_USERS=true
```

## 📚 API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🏗️ Architecture

```
Frontend (React) → Backend (FastAPI) → Database (PostgreSQL) + Cache (Redis)
```

## 📦 Production Deployment

```bash
docker-compose -f docker-compose.yml up -d
```

Set `ENABLE_TEST_USERS=false` in production.

## 🐛 Troubleshooting

### Backend won't start
```bash
docker-compose logs backend
```

### Frontend won't connect
Check `VITE_API_URL` in frontend/.env

### Database connection errors
```bash
docker-compose down -v
docker-compose up -d
```

---

**Version**: 3.1  
**Test Credentials**: admin/admin, client/client
