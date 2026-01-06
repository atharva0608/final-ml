# Spot Optimizer Platform

AWS Spot Instance Optimization for Kubernetes Clusters

## Overview

The Spot Optimizer Platform is a comprehensive solution for managing and optimizing AWS Spot instances in Kubernetes clusters. It provides intelligent cost optimization, automated node management, hibernation scheduling, and detailed metrics tracking.

## Features

### Core Functionality
- **AWS Account Integration**: Link multiple AWS accounts with cross-account IAM roles
- **Cluster Discovery**: Automatic discovery of EKS and self-managed Kubernetes clusters
- **Node Templates**: Define instance type families, architectures, and optimization strategies
- **Spot Optimization**: Intelligent spot instance selection with fallback to on-demand
- **Hibernation Scheduling**: Weekly schedules with pre-warming capabilities
- **Audit Logging**: Immutable audit trail for compliance
- **Metrics & Dashboard**: Real-time KPIs, cost tracking, and savings analysis

### Authentication & Security
- JWT-based authentication with access and refresh tokens
- Bcrypt password hashing (12 rounds default)
- Role-based access control (CLIENT, SUPER_ADMIN)
- API key authentication for Kubernetes Agent
- CORS configuration for secure web access

## Tech Stack

### Backend
- **Framework**: FastAPI 0.109.0
- **Database**: PostgreSQL 13+ with Alembic migrations
- **ORM**: SQLAlchemy 2.0
- **Caching**: Redis 6+
- **Task Queue**: Celery with Redis broker
- **Authentication**: JWT (python-jose)
- **Validation**: Pydantic 2.0

### Frontend (Planned)
- **Framework**: React 18
- **Routing**: React Router DOM 6
- **HTTP Client**: Axios
- **Charts**: Recharts

## Project Structure

```
new-version/
├── main.py                          # Application entry point
├── alembic.ini                      # Alembic configuration
├── requirements.txt                 # Python dependencies
├── package.json                     # Node.js dependencies
├── .env.example                     # Environment variable template
├── backend/
│   ├── api/                         # FastAPI route modules
│   │   ├── auth_routes.py          # Authentication endpoints
│   │   ├── template_routes.py      # Node template endpoints
│   │   └── audit_routes.py         # Audit log endpoints
│   ├── services/                    # Business logic layer
│   │   ├── auth_service.py         # Authentication service
│   │   ├── template_service.py     # Template management
│   │   ├── account_service.py      # AWS account linking
│   │   └── audit_service.py        # Audit logging
│   ├── models/                      # SQLAlchemy models (13 models)
│   ├── schemas/                     # Pydantic schemas (73 schemas)
│   └── core/                        # Core utilities
│       ├── config.py               # Configuration management
│       ├── crypto.py               # Cryptography utilities
│       ├── validators.py           # Custom validators
│       ├── exceptions.py           # Custom exceptions
│       ├── dependencies.py         # FastAPI dependencies
│       ├── logger.py               # Structured logging
│       └── api_gateway.py          # FastAPI application
├── migrations/                      # Alembic migrations
│   ├── versions/
│   │   ├── 001_initial_schema.py   # Complete schema
│   │   └── 002_seed_data.py        # Default data
│   └── env.py                      # Alembic environment
└── docs/
    └── CHANGELOG.md                # Comprehensive changelog
```

## Installation

### Quick Start with Docker (Recommended)

The easiest way to get started is using Docker with the provided start script:

**Prerequisites:**
- Docker Desktop (includes Docker Compose)
- 4GB+ RAM available
- 10GB+ disk space

**Quick Start:**

```bash
cd new-version

# First time setup - builds images, runs migrations, starts all services
./start.sh fresh
```

That's it! The platform will be available at:
- **Frontend**: http://localhost
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

**Common Commands:**

```bash
# Start services
./start.sh up

# Check service health
./start.sh status

# View logs
./start.sh logs              # All services
./start.sh logs backend      # Specific service

# Stop services
./start.sh down

# Rebuild after code changes
./start.sh build

# Access container shell
./start.sh shell backend
./start.sh shell frontend

# Run database migrations
./start.sh migrate

# Get help
./start.sh help
```

### Manual Installation (Development)

If you prefer to run services individually without Docker:

**Prerequisites:**
- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Node.js 18+ (for frontend)

**Setup:**

1. **Clone and navigate**
   ```bash
   cd new-version
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Required environment variables**
   ```bash
   # Database
   DATABASE_URL=postgresql://postgres:password@localhost:5432/spot_optimizer

   # Redis
   REDIS_URL=redis://localhost:6379/0

   # JWT
   JWT_SECRET_KEY=your-super-secret-key-change-this-in-production

   # AWS (optional for development)
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   AWS_REGION=us-east-1
   ```

6. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

7. **Start the application**
   ```bash
   python main.py
   ```

   The API will be available at `http://localhost:8000`

## API Documentation

When running in development mode, interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Register new user
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user profile
- `POST /api/v1/auth/change-password` - Change password
- `POST /api/v1/auth/logout` - Logout

### Node Templates
- `GET /api/v1/templates` - List templates
- `GET /api/v1/templates/{id}` - Get template details
- `POST /api/v1/templates` - Create template
- `PATCH /api/v1/templates/{id}` - Update template
- `DELETE /api/v1/templates/{id}` - Delete template
- `POST /api/v1/templates/{id}/set-default` - Set as default

### Audit Logs
- `GET /api/v1/audit` - Query audit logs
- `GET /api/v1/audit/{id}` - Get audit log details

### Health Check
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed health with dependencies

## Default Credentials

After running migrations, a default super admin account is created:
- **Email**: admin@spotoptimizer.com
- **Password**: admin123

**⚠️ IMPORTANT**: Change this password immediately in production!

## Database Schema

The platform uses 13 database models:
- **users**: User accounts
- **accounts**: AWS account connections
- **clusters**: Kubernetes clusters
- **instances**: EC2 instances
- **node_templates**: Instance selection templates
- **cluster_policies**: Optimization policies
- **hibernation_schedules**: Weekly hibernation schedules
- **audit_logs**: Immutable audit trail
- **ml_models**: ML model registry
- **optimization_jobs**: Optimization run tracking
- **lab_experiments**: A/B testing experiments
- **agent_actions**: Kubernetes action queue
- **api_keys**: Agent authentication tokens

## Development

### Running in Development Mode
```bash
# Auto-reload enabled in development
ENVIRONMENT=development python main.py
```

### Running Tests
```bash
pytest
```

### Code Quality
```bash
# Linting
flake8 backend/

# Type checking
mypy backend/

# Formatting
black backend/
```

## Production Deployment

### Using Docker

1. **Build images**
   ```bash
   docker-compose build
   ```

2. **Start services**
   ```bash
   docker-compose up -d
   ```

Services:
- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Environment Variables for Production

```bash
ENVIRONMENT=production
DEBUG=False
JWT_SECRET_KEY=<strong-secret-key>
DATABASE_URL=<production-database-url>
REDIS_URL=<production-redis-url>
CORS_ORIGINS=["https://app.yourdom ain.com"]
```

## Architecture

### Hybrid Routing
The platform uses a hybrid routing architecture:
- **AWS Actions**: Direct execution via boto3 (terminate, launch, detach)
- **Kubernetes Actions**: Queued for Agent execution (evict, cordon, drain, label)

### Agent Communication
- Kubernetes Agent polls for pending actions
- Agent executes K8s operations locally
- Results reported back to platform
- API key authentication with SHA-256 hashing

## Security

- Passwords hashed with bcrypt (12 rounds)
- JWT tokens with configurable expiration
- CORS origin whitelist
- API rate limiting (100 req/min)
- SQL injection protection via SQLAlchemy
- Input validation via Pydantic
- Structured logging for audit trail

## Contributing

This project follows a phased implementation approach:
- Phase 1-4: ✅ Complete (Foundation, Database, Core, Auth)
- Phase 5-9: 🚧 In Progress (Cluster, Templates, Policies)
- Phase 10-15: 📋 Planned (Metrics, Audit, Admin, Frontend, Testing)

## License

Proprietary - All Rights Reserved

## Support

For questions or issues, please contact the development team.

---

**Version**: 1.0.0
**Last Updated**: 2025-12-31
