# Scripts Module

## Purpose

Installation, deployment, and utility scripts for the application.

**Last Updated**: 2025-12-26
**Authority Level**: MEDIUM-HIGH

---

## Files

### install.sh ⭐ PRIMARY SETUP
**Purpose**: Main installation script for the entire application
**Lines**: ~280
**Capabilities**:
- Install system dependencies (Python, Node.js, PostgreSQL)
- Set up Python virtual environment
- Install Python packages (pip install -r requirements.txt)
- Install Node.js packages (npm install)
- Database initialization
- Environment variable setup

**Usage**:
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

**Platforms**: Linux (Ubuntu/Debian), macOS

**Dependencies**: bash, curl, sudo access

**Recent Changes**: None recent

### setup.sh
**Purpose**: Comprehensive setup wizard with interactive prompts
**Lines**: ~1,200
**Capabilities**:
- Interactive configuration wizard
- Database setup and migration
- AWS credential configuration
- Environment file generation (.env)
- Service account setup
- Initial admin user creation

**Usage**:
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

**Interactive Prompts**:
1. Database connection details
2. JWT secret key
3. Encryption key
4. AWS credentials (optional)
5. Admin username/password

**Dependencies**: bash, python, psql, openssl

**Recent Changes**: None recent

### setup_env.sh
**Purpose**: Quick environment variable setup
**Lines**: ~110
**Capabilities**:
- Generate .env file from template
- Set secure random secrets
- Configure database URL
- Set API base URL

**Usage**:
```bash
./scripts/setup_env.sh
```

**Generates**: `.env` file with all required variables

**Dependencies**: bash, openssl (for random secret generation)

**Recent Changes**: None recent

### deploy.sh
**Purpose**: Production deployment script
**Lines**: ~220
**Capabilities**:
- Build frontend (npm run build)
- Run database migrations
- Restart backend services
- Clear application cache
- Health check after deployment

**Usage**:
```bash
./scripts/deploy.sh [environment]
# ./scripts/deploy.sh production
# ./scripts/deploy.sh staging
```

**Deployment Steps**:
1. Backup database
2. Pull latest code (git pull)
3. Install dependencies
4. Run migrations
5. Build frontend
6. Restart services (systemd or supervisor)
7. Verify health checks

**Dependencies**: bash, systemd or supervisor, git

**Recent Changes**: None recent

### deploy_docker.sh
**Purpose**: Docker-based deployment
**Lines**: ~90
**Capabilities**:
- Build Docker images
- Push to container registry
- Deploy containers
- Configure networking

**Usage**:
```bash
./scripts/deploy_docker.sh
```

**Docker Services**:
- Backend API container
- Frontend container (nginx + static files)
- PostgreSQL container (if used)
- Redis container (if used)

**Dependencies**: docker, docker-compose

**Recent Changes**: None recent

### cleanup.sh
**Purpose**: Clean up temporary files and logs
**Lines**: ~280
**Capabilities**:
- Remove old log files (>30 days)
- Clear Python cache (__pycache__)
- Remove build artifacts
- Clean up old database backups
- Remove orphaned containers (if Docker)

**Usage**:
```bash
./scripts/cleanup.sh
```

**Safe to Run**: Yes (only removes temporary files)

**Dependencies**: bash, find

**Recent Changes**: None recent

### requirements_ml.txt
**Purpose**: Python dependencies specifically for ML training
**Lines**: ~10
**Contents**:
- scikit-learn
- pandas
- numpy
- xgboost or lightgbm
- matplotlib
- scipy

**Usage**:
```bash
pip install -r scripts/requirements_ml.txt
```

**When to Use**: Only for ML model training, not for production backend

### README_ML_TRAINING.md
**Purpose**: Documentation for ML model training process
**Lines**: ~240
**Contents**:
- ML training workflow
- Data preparation steps
- Model training commands
- Model evaluation process
- Model deployment steps

**Reference**: Read before training ML models

---

## Common Usage Patterns

### First-Time Setup
```bash
# 1. Install dependencies
./scripts/install.sh

# 2. Run setup wizard
./scripts/setup.sh

# 3. Start services
# (varies by deployment method)
```

### Deployment Workflow
```bash
# Standard deployment
./scripts/deploy.sh production

# Docker deployment
./scripts/deploy_docker.sh

# After deployment
./scripts/cleanup.sh
```

### ML Model Training
```bash
# Install ML dependencies
pip install -r scripts/requirements_ml.txt

# Read training guide
cat scripts/README_ML_TRAINING.md

# Train models (see ml-model/ folder)
python ml-model/family_stress_model.py
```

---

## Dependencies

### Depends On:
- bash
- Python 3.8+
- Node.js 18+
- PostgreSQL
- Git
- Docker (for deploy_docker.sh)
- systemd or supervisor (for service management)

### Depended By:
- **CRITICAL**: All deployment processes
- CI/CD pipelines (if implemented)
- Developer onboarding

**Impact Radius**: HIGH (affects deployment and setup)

---

## Recent Changes

### 2025-12-25: Governance Structure Establishment
**Files Changed**: None (metadata only)
**Reason**: Document existing scripts
**Impact**: No code changes, documentation baseline
**Reference**: `/index/recent_changes.md`

---

## Script Permissions

All scripts should be executable:
```bash
chmod +x scripts/*.sh
```

---

## Environment Variables Required

### Backend (.env)
```env
DATABASE_URL=postgresql://user:pass@localhost/dbname
JWT_SECRET_KEY=<random-secret>
ENCRYPTION_KEY=<fernet-key>
PYTHONPATH=/path/to/project
```

### Frontend (.env)
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

---

## Troubleshooting

### Installation Issues
```bash
# Check logs
tail -f /var/log/install.log

# Verify dependencies
python --version  # Should be 3.8+
node --version    # Should be 18+
psql --version    # Should be 12+
```

### Deployment Issues
```bash
# Check service status
systemctl status your-backend-service
systemctl status nginx

# View logs
journalctl -u your-backend-service -f
```

---

## Known Issues

### None

Scripts module is stable as of 2025-12-25.

---

## TODO / Improvements

1. **CI/CD Integration**: Add GitHub Actions or GitLab CI scripts
2. **Health Checks**: More comprehensive post-deployment checks
3. **Rollback Script**: Automated rollback on deployment failure
4. **Monitoring Setup**: Integrate with Prometheus/Grafana setup

---

_Last Updated: 2025-12-25_
_Authority: MEDIUM-HIGH - Deployment and setup_
