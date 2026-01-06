# Troubleshooting Guide

This document covers common issues and their solutions for the Spot Optimizer Platform.

## Table of Contents
1. [CORS Errors](#cors-errors)
2. [Login Page Issues](#login-page-issues)
3. [Container Restart Loops](#container-restart-loops)
4. [Database Connection Issues](#database-connection-issues)

---

## CORS Errors

### Symptom
```
Access to XMLHttpRequest at 'http://localhost:8000/api/v1/auth/login' from origin 'http://localhost'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present
```

### Cause
The backend hasn't loaded the updated CORS configuration from the `.env` file.

### Solution

**Option 1: Restart the backend (Quick)**
```bash
cd new-version
./start.sh restart
```

**Option 2: Full restart with fresh configuration**
```bash
cd new-version
./start.sh down
./start.sh up
```

### Verification
Check backend logs to see loaded CORS origins:
```bash
./start.sh logs backend | grep cors_origins
```

You should see:
```
"cors_origins": ["http://localhost:3000", "http://localhost", "http://localhost:80", "http://localhost:8000"]
```

### Configuration
The CORS origins are configured in `.env`:
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost,http://localhost:80,http://localhost:8000
```

---

## Login Page Issues

### Issue 1: Dashboard Shows Instead of Login Page

**Symptom**: After opening `http://localhost`, you see the dashboard instead of the login page.

**Cause**: Stale JWT tokens in browser localStorage from previous sessions.

**Solution**: The application now automatically validates tokens on startup. If you still see this issue:

1. **Automatic Fix (Recommended)**: Rebuild frontend with token validation:
   ```bash
   cd new-version
   docker compose -f docker/docker-compose.yml build frontend
   ./start.sh restart
   ```

2. **Manual Fix**: Clear browser localStorage:
   - Open browser DevTools (F12)
   - Go to Application/Storage tab
   - Find "Local Storage" → `http://localhost`
   - Delete `auth-storage` key
   - Refresh page

### Issue 2: 403 Forbidden on Login

**Symptom**: Login form submits but returns 403 error.

**Causes & Solutions**:

1. **CORS not configured**: See [CORS Errors](#cors-errors) section above

2. **Backend not ready**: Wait for backend to be fully started
   ```bash
   ./start.sh status
   ```
   Both backend and frontend should show "✅ Healthy"

3. **Database migration not run**:
   ```bash
   ./start.sh migrate
   ./start.sh restart
   ```

---

## Container Restart Loops

### Symptom
Services continuously restarting when you run `./start.sh status` or `docker compose ps`

### Diagnosis
Check logs for the failing service:
```bash
# Check which service is restarting
./start.sh status

# View logs for specific service
./start.sh logs backend
./start.sh logs celery-worker
```

### Common Causes

#### 1. Import Errors (ModuleNotFoundError, ImportError)

**Solution**: Ensure all code is synced from the correct branch
```bash
git pull origin claude/review-instructions-hxq6T
./start.sh build  # Rebuild images with latest code
./start.sh up
```

#### 2. Database Not Ready

**Solution**: Ensure postgres is healthy before starting other services
```bash
./start.sh down
./start.sh up  # This script waits for postgres to be ready
```

#### 3. Missing Environment Variables

**Solution**: Check .env file has all required variables
```bash
grep -E "^(DATABASE_URL|REDIS_URL|JWT_SECRET_KEY)=" .env
```

If any are missing, update `.env`:
```bash
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/spot_optimizer
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=dev-secret-key-change-in-production-use-random-64-char-string
```

Then restart:
```bash
./start.sh restart
```

---

## Database Connection Issues

### Issue 1: "Connection Refused" to Postgres

**Symptom**: Backend logs show:
```
could not connect to server: Connection refused
```

**Solution**:
```bash
# Ensure postgres is running
./start.sh status

# If postgres is down, start it
./start.sh up
```

### Issue 2: Migration Errors

**Symptom**:
```
alembic.util.exc.CommandError: Can't locate revision identified by...
```

**Solution**: Reset migrations
```bash
# Stop all services
./start.sh down

# Remove volumes (WARNING: Deletes all data)
docker compose -f docker/docker-compose.yml down -v

# Fresh start
./start.sh fresh
```

---

## Quick Health Check

Run these commands to verify everything is working:

```bash
# 1. Check all services are running
./start.sh status

# 2. Check backend health endpoint
curl http://localhost:8000/health

# 3. Check frontend is serving
curl -I http://localhost

# 4. Check backend logs for errors
./start.sh logs backend | tail -50

# 5. Test login (should return 401 or 422, not CORS error)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'
```

---

## Getting Help

If issues persist:

1. **Collect logs**:
   ```bash
   ./start.sh logs > logs.txt
   ```

2. **Check service status**:
   ```bash
   ./start.sh status > status.txt
   ```

3. **Check environment**:
   ```bash
   cat .env > env.txt  # Remove sensitive values before sharing!
   ```

4. **Report the issue** with the collected information

---

## Clean Slate

If all else fails, start completely fresh:

```bash
# WARNING: This deletes all data and containers
./start.sh clean  # Type 'y' to confirm

# Fresh installation
./start.sh fresh

# Verify everything is working
./start.sh status
```

---

## Default Credentials

After fresh installation, use these credentials:

- **Email**: `admin@spotoptimizer.com`
- **Password**: `admin123`

⚠️ **Change these immediately in production!**
