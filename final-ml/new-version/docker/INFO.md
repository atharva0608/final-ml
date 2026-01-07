# Docker - Component Information

> **Last Updated**: 2026-01-02 13:30:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
Contains Docker configuration files including Dockerfiles for backend and frontend services, and docker-compose configuration for local development and deployment orchestration.

---

## Component Table

| File Name | Type | Purpose | Base Image | Exposed Ports | Status |
|-----------|------|---------|------------|---------------|--------|
| Dockerfile.backend | Dockerfile | Backend service container | python:3.11-slim | 8000 | ✅ Complete |
| Dockerfile.frontend | Dockerfile | Frontend service container | node:18-alpine, nginx:alpine | 80, 443 | ✅ Complete |
| nginx.conf | Config | Nginx configuration for frontend | N/A | N/A | ✅ Complete |
| docker-compose.yml | Compose | Multi-container orchestration | N/A | Multiple | ✅ Complete |

---

## Recent Changes

### [2026-01-02 14:45:00] - Critical Fix: index.html Not Found - Incorrect Directory Structure
**Changed By**: LLM Agent
**Reason**: Fix frontend Docker build failure due to incorrect directory structure
**Impact**: Frontend Docker image can now find all required files and build successfully
**Files Modified**:
- Updated docker/Dockerfile.frontend (changed COPY command to copy contents correctly)
- Updated task.md with Issue #11 documentation
- Updated docker/INFO.md (this file)
**Problem**: `COPY frontend/ ./frontend/` created wrong structure - react-scripts expected /app/public/ but got /app/frontend/public/
**Solution**: Changed to `COPY frontend/. ./` to copy contents of frontend/ directly into /app
**Explanation**:
  - Before: /app/package.json + /app/frontend/public/index.html (BROKEN)
  - After: /app/package.json + /app/public/index.html (CORRECT)
  - react-scripts looks for files relative to package.json location
**Feature IDs Affected**: N/A (Infrastructure fix)
**Breaking Changes**: No
**Severity**: Critical - Frontend build completely failed with "index.html not found" error

### [2026-01-02 14:30:00] - Critical Fix: react-scripts Not Found - npm install --production Issue
**Changed By**: LLM Agent
**Reason**: Fix frontend Docker build failure due to missing devDependencies
**Impact**: Frontend Docker image can now build React production bundle successfully
**Files Modified**:
- Updated docker/Dockerfile.frontend (removed --production flag from npm install)
- Updated task.md with Issue #10 documentation
- Updated docker/INFO.md (this file)
**Problem**: `npm install --production` excluded devDependencies like react-scripts needed for build
**Solution**: Changed to `npm install` to include all dependencies in builder stage
**Rationale**: Multi-stage build - devDependencies only in builder, final image still small (nginx + static files)
**Feature IDs Affected**: N/A (Infrastructure fix)
**Breaking Changes**: No
**Severity**: Critical - Frontend build completely failed without this fix

### [2026-01-02 14:15:00] - Critical Fix: npm ci Failure in Dockerfile.frontend
**Changed By**: LLM Agent
**Reason**: Fix frontend Docker build failure due to missing package-lock.json
**Impact**: Frontend Docker image now builds successfully
**Files Modified**:
- Updated docker/Dockerfile.frontend (changed npm ci to npm install)
- Updated task.md with Issue #9 documentation
- Updated docker/INFO.md (this file)
**Problem**: `npm ci` requires package-lock.json but repository doesn't have one
**Solution**: Changed to `npm install --production` which works with or without lock file
**Feature IDs Affected**: N/A (Infrastructure fix)
**Breaking Changes**: No
**Severity**: Critical - Frontend couldn't build without this fix

### [2026-01-02 13:30:00] - Critical Fix: Docker Compose Path Configuration
**Changed By**: LLM Agent
**Reason**: Fix start.sh to correctly reference docker/docker-compose.yml path
**Impact**: Application now starts all 6 services instead of failing
**Files Modified**:
- Updated start.sh with `-f docker/docker-compose.yml` flag for all docker-compose commands (15 occurrences)
- Added EXTRA PROBLEMS & FIXES LOG section to task.md
- Updated docker/INFO.md (this file)
**Problem**: start.sh was using bare `docker-compose` commands without file path
**Solution**: Added `-f docker/docker-compose.yml` to all commands (up, down, restart, logs, build, clean, migrate, shell, test, ps)
**Feature IDs Affected**: N/A (Infrastructure fix)
**Breaking Changes**: No
**Severity**: Critical - Application wouldn't start without this fix

### [2025-12-31 12:40:00] - Docker Configuration Completed
**Changed By**: LLM Agent
**Reason**: Complete Phase 1.4 - Docker configuration for all services
**Impact**: Production-ready Docker setup for local development and deployment
**Files Modified**:
- Created docker/Dockerfile.backend (multi-stage build with health checks)
- Created docker/Dockerfile.frontend (multi-stage build with Nginx)
- Created docker/nginx.conf (SPA routing, API proxy, security headers)
- Created docker/docker-compose.yml (6 services: postgres, redis, backend, celery-worker, celery-beat, frontend)
- Updated docker/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

### [2025-12-31 12:36:00] - Initial Docker Structure Created
**Changed By**: LLM Agent
**Reason**: Create organized folder structure for Docker configuration
**Impact**: Created docker directory for containerization files
**Files Modified**:
- Created docker/
- Created docker/INFO.md (this file)
**Feature IDs Affected**: N/A (Infrastructure setup)
**Breaking Changes**: No

---

## Dependencies

### Internal Dependencies
- Dockerfile.backend depends on backend/ source code
- Dockerfile.frontend depends on frontend/ source code
- docker-compose.yml orchestrates all services

### External Dependencies
- **Container Runtime**: Docker 20.10+
- **Orchestration**: docker-compose 2.0+
- **Base Images**: python:3.11-slim, node:18-alpine, nginx:alpine
- **Database**: postgres:13-alpine
- **Cache**: redis:6-alpine

---

## Docker Configuration Overview

### 1. Dockerfile.backend (Planned)
```dockerfile
# Multi-stage build for backend
# Stage 1: Dependencies
FROM python:3.11-slim AS builder
# Install system dependencies
# Copy requirements.txt
# Install Python packages

# Stage 2: Runtime
FROM python:3.11-slim
# Copy installed packages from builder
# Copy backend source code
# Set working directory
# Create non-root user
# Expose port 8000
# Health check configuration
# Entrypoint: uvicorn

# Environment Variables:
# - DATABASE_URL
# - REDIS_URL
# - CELERY_BROKER_URL
# - JWT_SECRET_KEY
# - AWS_REGION
```

### 2. Dockerfile.frontend (Planned)
```dockerfile
# Multi-stage build for frontend
# Stage 1: Build
FROM node:18-alpine AS builder
# Copy package.json
# Install dependencies
# Copy frontend source
# Build production bundle

# Stage 2: Serve
FROM nginx:alpine
# Copy built files from builder
# Copy nginx configuration
# Expose port 80
# Health check configuration
# Entrypoint: nginx

# Environment Variables:
# - REACT_APP_API_URL
# - REACT_APP_WS_URL
```

### 3. docker-compose.yml (Planned)
```yaml
# Services:
# - postgres: PostgreSQL database
# - redis: Redis cache and message broker
# - backend: FastAPI application
# - celery-worker: Celery worker for async tasks
# - celery-beat: Celery beat scheduler
# - frontend: React application (Nginx)

# Networks:
# - app-network: Internal network for all services

# Volumes:
# - postgres_data: PostgreSQL data persistence
# - redis_data: Redis data persistence (optional)

# Environment Variables loaded from .env file
```

---

## Docker Compose Services

### Database Service (`postgres`):
- Image: `postgres:13-alpine`
- Volume: `postgres_data:/var/lib/postgresql/data`
- Port: `5432:5432`
- Health Check: `pg_isready`
- Environment: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

### Cache Service (`redis`):
- Image: `redis:6-alpine`
- Volume: `redis_data:/data` (optional)
- Port: `6379:6379`
- Health Check: `redis-cli ping`
- Command: `redis-server --appendonly yes`

### Backend Service (`backend`):
- Build: `../backend` with `Dockerfile.backend`
- Port: `8000:8000`
- Depends On: `postgres`, `redis`
- Environment: From `.env` file
- Restart: `unless-stopped`

### Celery Worker Service (`celery-worker`):
- Build: `../backend` with `Dockerfile.backend`
- Command: `celery -A backend.workers worker -l info`
- Depends On: `postgres`, `redis`, `backend`
- Environment: From `.env` file
- Restart: `unless-stopped`

### Celery Beat Service (`celery-beat`):
- Build: `../backend` with `Dockerfile.backend`
- Command: `celery -A backend.workers beat -l info`
- Depends On: `postgres`, `redis`, `backend`
- Environment: From `.env` file
- Restart: `unless-stopped`

### Frontend Service (`frontend`):
- Build: `../frontend` with `Dockerfile.frontend`
- Port: `80:80`, `443:443`
- Depends On: `backend`
- Environment: `REACT_APP_API_URL=http://backend:8000`
- Restart: `unless-stopped`

---

## Docker Best Practices

### 1. Multi-Stage Builds:
- Reduce final image size
- Separate build and runtime dependencies
- Improve build caching

### 2. Security:
- Run containers as non-root user
- Use minimal base images (alpine)
- Scan images for vulnerabilities
- Keep images updated

### 3. Health Checks:
- Define health checks for all services
- Use appropriate intervals and timeouts
- Fail fast on unhealthy containers

### 4. Resource Limits:
- Set memory limits for all services
- Configure CPU limits to prevent resource exhaustion
- Monitor container resource usage

### 5. Networking:
- Use Docker networks for service communication
- Minimize exposed ports
- Use environment variables for service discovery

---

## Local Development

### Start all services:
```bash
docker-compose -f docker/docker-compose.yml up -d
# OR use the start.sh script (recommended):
./start.sh
```

### View logs:
```bash
docker-compose -f docker/docker-compose.yml logs -f
# OR use the start.sh script:
./start.sh logs
```

### Stop all services:
```bash
docker-compose -f docker/docker-compose.yml down
# OR use the start.sh script:
./start.sh down
```

### Rebuild after code changes:
```bash
docker-compose -f docker/docker-compose.yml up -d --build
# OR use the start.sh script:
./start.sh build && ./start.sh up
```

### Access services:
- Frontend: http://localhost:80
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

---

## Production Deployment

- Use Docker Swarm or Kubernetes for orchestration
- Separate docker-compose files for dev/staging/production
- Use secrets management for sensitive data
- Configure SSL/TLS certificates
- Set up monitoring and logging
- Implement automated backups
- Configure autoscaling

---

## Testing Requirements

- Build tests for all Dockerfiles
- Health check validation tests
- docker-compose smoke tests
- Container security scanning
- Image size optimization validation
