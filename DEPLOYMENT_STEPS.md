# AWS Spot Optimizer - Complete Deployment Guide

## All Fixes Applied ✅

### Issues Fixed:

1. ✅ **SQL Syntax Error (Line 66)** - COMMENT statements moved before semicolons
2. ✅ **Backend Import Error** - database_utils imports removed (functions in backend.py)
3. ✅ **Missing Tables** - Added 5 required tables (pricing_submissions_raw, data_processing_jobs, etc.)
4. ✅ **MySQL Permission Errors** - Migrated from bind mount to Docker volume

### Commits Pushed:

```
7909d90 - Fix MySQL InnoDB permission errors with Docker volumes
c936bb5 - Comprehensive schema.sql fixes for MySQL 8.0 compatibility
9e16e3d - Remove database_utils import statements after consolidation
7658791 - Add missing semicolons to all CREATE TABLE statements
f277065 - Correct database credentials and add diagnostic script
```

---

## Deployment on Production Server

### Step 1: Pull Latest Code

```bash
cd /home/ubuntu/final-ml
git fetch origin
git pull origin claude/restructure-project-files-01LApGgohR1kUwktsXZWprsr
```

**What this gets you:**
- Fixed schema.sql (no more line 66 error)
- Fixed backend.py (no more import errors)
- MySQL permission fix scripts
- Updated setup.sh (uses Docker volumes)

---

### Step 2: Fix MySQL Permissions (Choose One Method)

#### Method A: Migrate to Docker Volume (Recommended)

**Best for:** Long-term fix, no more permission issues

```bash
cd /home/ubuntu/final-ml
sudo ./scripts/migrate_to_docker_volume.sh
```

**What it does:**
- Exports your current database
- Creates Docker volume (spot-mysql-data)
- Recreates MySQL container with proper volume
- Imports your data back
- Backs up old bind mount directory

**Time:** 2-3 minutes

#### Method B: Quick Permission Fix (Keep Bind Mount)

**Best for:** Quick fix without changing setup

```bash
cd /home/ubuntu/final-ml
sudo ./scripts/fix_mysql_permissions.sh
```

**What it does:**
- Fixes permissions inside container
- Restarts MySQL cleanly
- Verifies connections work

**Time:** 30 seconds

**Note:** You may need to run this periodically if using bind mount.

---

### Step 3: Reimport Database Schema

This fixes all SQL syntax errors and adds missing tables:

```bash
# Drop and recreate database (clean start)
docker exec spot-mysql mysql -u root -p'SpotOptimizer2024!' -e "DROP DATABASE IF EXISTS spot_optimizer; CREATE DATABASE spot_optimizer;"

# Import schema
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql

# Recreate user and grants
docker exec spot-mysql mysql -u root -p'SpotOptimizer2024!' -e "
    CREATE USER IF NOT EXISTS 'spotuser'@'%' IDENTIFIED BY 'SpotUser2024!';
    CREATE USER IF NOT EXISTS 'spotuser'@'localhost' IDENTIFIED BY 'SpotUser2024!';
    CREATE USER IF NOT EXISTS 'spotuser'@'172.18.%' IDENTIFIED BY 'SpotUser2024!';
    GRANT ALL PRIVILEGES ON spot_optimizer.* TO 'spotuser'@'%';
    GRANT ALL PRIVILEGES ON spot_optimizer.* TO 'spotuser'@'localhost';
    GRANT ALL PRIVILEGES ON spot_optimizer.* TO 'spotuser'@'172.18.%';
    FLUSH PRIVILEGES;
"
```

**Expected output:**
- No syntax errors
- 35 tables created
- 4 views created
- 11 procedures created

---

### Step 4: Verify Database

```bash
cd /home/ubuntu/final-ml
./scripts/test_database.sh
```

**Expected output:**
```
✓ MySQL container is running
✓ Root can connect
✓ User 'spotuser' can connect
✓ Found 35 tables
✓ Python can connect! Found 35 tables
✅ Database diagnostics complete!
```

---

### Step 5: Verify No MySQL Permission Errors

```bash
docker logs spot-mysql --tail 50 | grep -i "error"
```

**Expected:** No "Operating system error number 13" errors

If you still see errors, run:
```bash
sudo ./scripts/fix_mysql_permissions.sh
```

---

### Step 6: Restart Backend Service

```bash
sudo systemctl restart spot-optimizer-backend
```

Wait 5 seconds, then check status:

```bash
sudo systemctl status spot-optimizer-backend
```

**Expected output:**
```
● spot-optimizer-backend.service - AWS Spot Optimizer Backend
   Active: active (running)
   ...
```

---

### Step 7: Check Backend Logs

```bash
sudo journalctl -u spot-optimizer-backend -n 50 --no-pager
```

**Should NOT see:**
- ❌ "ModuleNotFoundError: No module named 'database_utils'"
- ❌ "ERROR 1064 (42000) at line 66"
- ❌ "Operating system error number 13"

**SHOULD see:**
- ✅ "Smart Emergency Fallback System initialized"
- ✅ "Flask app running"
- ✅ Database connection established

---

### Step 8: Test Backend API

```bash
curl http://localhost:5000/health
```

**Expected:**
```json
{"status": "healthy"}
```

Test API endpoints:
```bash
# Get system health
curl http://localhost:5000/api/system/health

# Get clients (should be empty array or existing data)
curl http://localhost:5000/api/clients
```

---

### Step 9: Check Frontend

Open browser to: `http://100.28.125.108/`

**Expected:**
- ✅ Dashboard loads
- ✅ No connection errors in console
- ✅ Backend API calls work

---

## Verification Checklist

Run this comprehensive check:

```bash
echo "=== MySQL Status ==="
docker ps | grep spot-mysql

echo ""
echo "=== MySQL Volume Type ==="
docker inspect spot-mysql --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}Type: {{.Type}}, Source: {{.Source}}{{end}}{{end}}'

echo ""
echo "=== Permission Errors (should be 0) ==="
docker logs spot-mysql --tail 100 2>&1 | grep -c "Operating system error number 13" || echo "0"

echo ""
echo "=== Database Tables ==="
docker exec spot-mysql mysql -u spotuser -p'SpotUser2024!' spot_optimizer -e "SHOW TABLES;" | wc -l
echo "Expected: 36 lines (35 tables + header)"

echo ""
echo "=== Backend Status ==="
systemctl is-active spot-optimizer-backend

echo ""
echo "=== Backend Health ==="
curl -s http://localhost:5000/health | jq '.' 2>/dev/null || curl http://localhost:5000/health

echo ""
echo "=== Recent Backend Errors ==="
sudo journalctl -u spot-optimizer-backend -n 20 --no-pager | grep -i error || echo "No errors"
```

**All checks should pass!**

---

## Troubleshooting

### Backend Won't Start

**Check logs:**
```bash
sudo journalctl -u spot-optimizer-backend -n 100 --no-pager
```

**Common issues:**

1. **Module import errors:**
   ```bash
   # Verify no database_utils imports
   grep -n "from database_utils import" /home/ubuntu/spot-optimizer/backend/backend.py
   # Should return nothing
   ```

2. **Database connection errors:**
   ```bash
   # Test connection
   ./scripts/test_database.sh
   ```

3. **Missing requirements:**
   ```bash
   cd /home/ubuntu/spot-optimizer/backend
   source venv/bin/activate
   pip install -r requirements.txt
   ```

### MySQL Permission Errors Persist

```bash
# Method 1: Run fix script again
sudo ./scripts/fix_mysql_permissions.sh

# Method 2: Recreate container with Docker volume
docker stop spot-mysql
docker rm spot-mysql
docker volume rm spot-mysql-data 2>/dev/null || true
docker volume create spot-mysql-data

# Recreate container (copy from setup.sh lines 379-395)
docker run -d \
    --name spot-mysql \
    --network spot-network \
    --restart unless-stopped \
    -e MYSQL_ROOT_PASSWORD="SpotOptimizer2024!" \
    -e MYSQL_DATABASE="spot_optimizer" \
    -e MYSQL_USER="spotuser" \
    -e MYSQL_PASSWORD="SpotUser2024!" \
    -p 3306:3306 \
    -v spot-mysql-data:/var/lib/mysql \
    mysql:8.0 \
    --default-authentication-plugin=mysql_native_password \
    --character-set-server=utf8mb4 \
    --collation-server=utf8mb4_unicode_ci \
    --max_connections=200 \
    --innodb_buffer_pool_size=256M \
    --innodb_log_buffer_size=16M

# Wait 20 seconds
sleep 20

# Reimport schema
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql
```

### Database Tables Missing

```bash
# Count tables
docker exec spot-mysql mysql -u spotuser -p'SpotUser2024!' spot_optimizer -e "SHOW TABLES;" | wc -l

# If less than 35 tables, reimport
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql
```

### Frontend Can't Connect to Backend

```bash
# Check backend is running
curl http://localhost:5000/health

# Check Nginx config
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Check Nginx logs
sudo tail -50 /var/log/nginx/error.log
```

---

## What Changed

### Files Modified:

| File | Change | Impact |
|------|--------|---------|
| `database/schema.sql` | Fixed COMMENT syntax, added 5 tables | No more line 66 error, all backend tables exist |
| `backend/backend.py` | Removed database_utils imports | No more ModuleNotFoundError |
| `scripts/setup.sh` | Use Docker volume instead of bind mount | No more permission errors (new installs) |
| `scripts/migrate_to_docker_volume.sh` | NEW | Migrate existing installs to Docker volume |
| `scripts/fix_mysql_permissions.sh` | NEW | Quick fix for permission errors |
| `docs/MYSQL_PERMISSION_FIX.md` | NEW | Comprehensive permission fix guide |

### Database Changes:

**Added Tables:**
1. `pricing_submissions_raw` - Raw pricing before deduplication
2. `data_processing_jobs` - Batch processing tracking
3. `instance_switches` - Quick switch logging
4. `pricing_snapshots_interpolated` - Gap-filled data
5. `pricing_snapshots_ml` - ML predictions

**Total Tables:** 35 (was 30)
**Total Views:** 4
**Total Procedures:** 11
**Total Events:** 4

---

## Performance Improvements

### Docker Volume vs Bind Mount:

| Aspect | Bind Mount (Old) | Docker Volume (New) |
|--------|-----------------|---------------------|
| Permissions | Manual fixes needed | Automatic |
| Performance | Slower | Faster |
| Portability | System-specific | Universal |
| Errors | Frequent | Rare |
| Maintenance | High | Low |

---

## Success Indicators

After deployment, you should see:

✅ **MySQL Logs:** No "Operating system error number 13"
✅ **Backend Logs:** No import or database errors
✅ **Backend API:** `curl http://localhost:5000/health` returns `{"status": "healthy"}`
✅ **Database:** 35 tables present
✅ **Frontend:** Dashboard loads without errors
✅ **Docker Volume:** `docker volume ls` shows `spot-mysql-data`

---

## Quick Command Reference

```bash
# Pull latest code
cd /home/ubuntu/final-ml && git pull

# Fix MySQL permissions (choose one)
sudo ./scripts/migrate_to_docker_volume.sh        # Permanent fix
sudo ./scripts/fix_mysql_permissions.sh           # Quick fix

# Reimport schema
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql

# Test database
./scripts/test_database.sh

# Restart services
sudo systemctl restart spot-optimizer-backend
sudo systemctl restart nginx

# Check status
sudo systemctl status spot-optimizer-backend
curl http://localhost:5000/health
docker logs spot-mysql --tail 20
```

---

## Support

If issues persist after following this guide:

1. **Check all logs:**
   ```bash
   # Backend
   sudo journalctl -u spot-optimizer-backend -n 100 --no-pager

   # MySQL
   docker logs spot-mysql --tail 100

   # Nginx
   sudo tail -100 /var/log/nginx/error.log
   ```

2. **Verify all fixes applied:**
   ```bash
   cd /home/ubuntu/final-ml
   git log --oneline -5
   # Should show commit 7909d90 or later
   ```

3. **Run comprehensive diagnostics:**
   ```bash
   ./scripts/test_database.sh
   python3 test_imports.py  # If test_imports.py exists in repo
   ```

---

## Summary

✅ **All syntax errors fixed** in schema.sql (COMMENT placement, semicolons)
✅ **All import errors fixed** in backend.py (database_utils removed)
✅ **All missing tables added** (5 new tables for backend operations)
✅ **MySQL permissions fixed** (Docker volume migration available)
✅ **Scripts provided** for easy deployment and troubleshooting
✅ **Documentation complete** with step-by-step guides

**Estimated deployment time:** 5-10 minutes

Your system should be fully operational after following these steps! 🎉
