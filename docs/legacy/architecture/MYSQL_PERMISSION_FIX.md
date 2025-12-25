# MySQL InnoDB Permission Error Fix

## Problem

Users experiencing MySQL InnoDB permission errors in Docker:

```
[ERROR] [MY-012592] [InnoDB] Operating system error number 13 in a file operation.
[ERROR] [MY-012595] [InnoDB] The error means mysqld does not have the access rights to the directory.
[ERROR] [MY-012894] [InnoDB] Unable to open './#innodb_redo/#ib_redo9' (error: 11).
```

## Root Cause

The original `setup.sh` used a **bind mount** (`-v /home/ubuntu/mysql-data:/var/lib/mysql`) which causes permission conflicts:

| Issue | Description |
|-------|-------------|
| Host ownership | `/home/ubuntu/mysql-data` owned by root or ubuntu user (UID 1000) |
| Container user | MySQL runs as `mysql` user (UID 999) inside container |
| Permission mismatch | Container can't write to host directory with wrong ownership |
| InnoDB redo logs | Specifically affected: `#innodb_redo` and `#innodb_temp` directories |

## Solution

We've fixed this in THREE ways:

### 1. Updated setup.sh (Permanent Fix)

**Changed from bind mount to Docker volume:**

```bash
# OLD (bind mount - causes issues):
-v /home/ubuntu/mysql-data:/var/lib/mysql

# NEW (Docker volume - automatic permissions):
-v spot-mysql-data:/var/lib/mysql
```

**Why Docker volumes are better:**
- ✅ Docker manages permissions automatically
- ✅ MySQL container user gets correct ownership
- ✅ No manual permission fixing needed
- ✅ More portable across systems
- ✅ Better performance
- ✅ Easier backup and restore

### 2. Migration Script (For Existing Installations)

**Script:** `scripts/migrate_to_docker_volume.sh`

**What it does:**
1. Detects current MySQL setup (bind mount or volume)
2. Exports existing database to backup
3. Creates new Docker volume
4. Recreates container with Docker volume
5. Imports data from backup
6. Verifies no permission errors
7. Backs up old bind mount directory

**Usage:**
```bash
cd /home/ubuntu/final-ml
sudo ./scripts/migrate_to_docker_volume.sh
```

**Safe to run:**
- ✅ Backs up existing data before migration
- ✅ Skips if already using Docker volume
- ✅ Can be re-run if it fails
- ✅ Preserves all databases and users

### 3. Permission Fix Script (Quick Fix Without Migration)

**Script:** `scripts/fix_mysql_permissions.sh`

**What it does:**
1. Stops MySQL container
2. Fixes permissions from inside container
3. Restarts MySQL with clean state
4. Verifies no more errors

**Usage:**
```bash
cd /home/ubuntu/final-ml
sudo ./scripts/fix_mysql_permissions.sh
```

**When to use:**
- Quick fix without migrating to Docker volume
- Temporary solution if migration can't be done immediately
- After manual file system changes

## Deployment Instructions

### For New Installations:

**Just run the updated setup script:**
```bash
cd /home/ubuntu/final-ml
git pull origin claude/restructure-project-files-01LApGgohR1kUwktsXZWprsr
sudo ./scripts/setup.sh
```

The new `setup.sh` automatically uses Docker volumes (no permission issues).

### For Existing Installations (Recommended):

**Step 1: Pull latest changes**
```bash
cd /home/ubuntu/final-ml
git fetch origin
git pull origin claude/restructure-project-files-01LApGgohR1kUwktsXZWprsr
```

**Step 2: Migrate to Docker volume**
```bash
sudo ./scripts/migrate_to_docker_volume.sh
```

**Step 3: Reimport schema (fixes SQL syntax errors too)**
```bash
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql
```

**Step 4: Verify database**
```bash
./scripts/test_database.sh
```

**Step 5: Restart backend**
```bash
sudo systemctl restart spot-optimizer-backend
sudo systemctl status spot-optimizer-backend
```

### Alternative: Quick Fix (Without Migration):

**If you can't migrate right now:**
```bash
cd /home/ubuntu/final-ml
git pull origin claude/restructure-project-files-01LApGgohR1kUwktsXZWprsr
sudo ./scripts/fix_mysql_permissions.sh
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql
sudo systemctl restart spot-optimizer-backend
```

## Verification

### Check for Permission Errors:

```bash
# Should show NO "Operating system error number 13"
docker logs spot-mysql --tail 50 | grep -i error
```

### Check MySQL Status:

```bash
docker ps | grep spot-mysql
# Should show: Up X minutes (healthy)
```

### Check Volume Type:

```bash
docker inspect spot-mysql --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}Type: {{.Type}}, Source: {{.Source}}{{end}}{{end}}'
```

**Expected after migration:**
```
Type: volume, Source: spot-mysql-data
```

### Check Backend Connection:

```bash
curl http://localhost:5000/health
# Should return: {"status": "healthy"}
```

## Understanding Docker Volumes vs Bind Mounts

### Bind Mount (Old, Problematic):

```bash
-v /home/ubuntu/mysql-data:/var/lib/mysql
     ↑                          ↑
  Host path                  Container path
(ownership issues)          (needs UID 999)
```

**Problems:**
- Host directory owned by wrong user
- Container can't write
- Manual permission fixes needed
- Platform-specific paths

### Docker Volume (New, Automatic):

```bash
-v spot-mysql-data:/var/lib/mysql
     ↑                  ↑
  Volume name       Container path
(Docker manages)  (automatic permissions)
```

**Benefits:**
- Docker sets correct permissions
- Platform-independent
- Better performance
- Easier backup/restore
- No manual fixes needed

## Troubleshooting

### Issue: "Container won't start after migration"

**Solution:**
```bash
# Check logs
docker logs spot-mysql --tail 100

# If permission errors still exist
docker exec spot-mysql chown -R mysql:mysql /var/lib/mysql
docker restart spot-mysql
```

### Issue: "Database is empty after migration"

**Solution:**
```bash
# Check if backup exists
ls -lh /tmp/mysql_backup_*.sql

# Reimport backup
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' < /tmp/mysql_backup_*.sql

# Or reimport fresh schema
docker exec -i spot-mysql mysql -u root -p'SpotOptimizer2024!' spot_optimizer < database/schema.sql
```

### Issue: "Still seeing permission errors"

**Solution:**
```bash
# Run permission fix script
sudo ./scripts/fix_mysql_permissions.sh

# If that doesn't work, recreate with fresh volume
docker stop spot-mysql
docker rm spot-mysql
docker volume rm spot-mysql-data
docker volume create spot-mysql-data

# Recreate container (copy command from setup.sh lines 379-395)
# Then reimport schema
```

### Issue: "Want to restore old bind mount"

**Solution:**
```bash
# Find backup directory
ls -la /home/ubuntu/ | grep mysql-data.backup

# Stop container
docker stop spot-mysql
docker rm spot-mysql

# Remove volume
docker volume rm spot-mysql-data

# Restore old bind mount
sudo mv /home/ubuntu/mysql-data.backup.* /home/ubuntu/mysql-data

# Recreate with bind mount (use old setup.sh command)
```

## Files Changed

| File | Changes | Purpose |
|------|---------|---------|
| `scripts/setup.sh` | Changed bind mount to Docker volume (line 388) | Prevent future permission issues |
| `scripts/migrate_to_docker_volume.sh` | New script | Migrate existing installations |
| `scripts/fix_mysql_permissions.sh` | New script | Quick permission fix |
| `database/schema.sql` | Fixed COMMENT syntax, added missing tables | Fix SQL errors |

## Performance Impact

| Aspect | Bind Mount | Docker Volume |
|--------|-----------|---------------|
| Write performance | Slower (goes through filesystem layers) | Faster (optimized by Docker) |
| Permission issues | Common (manual fixes needed) | Rare (automatic management) |
| Portability | Platform-specific paths | Platform-independent |
| Backup | Complex (filesystem-level) | Simple (docker volume commands) |
| Maintenance | Manual permission fixes | Automatic |

## Backup and Restore with Docker Volumes

### Backup Volume:

```bash
# Create backup
docker run --rm \
  -v spot-mysql-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/mysql-backup-$(date +%Y%m%d).tar.gz /data

# Backup size
ls -lh mysql-backup-*.tar.gz
```

### Restore Volume:

```bash
# Stop MySQL
docker stop spot-mysql

# Restore
docker run --rm \
  -v spot-mysql-data:/data \
  -v $(pwd):/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/mysql-backup-YYYYMMDD.tar.gz -C /"

# Start MySQL
docker start spot-mysql
```

## Summary

✅ **Root cause:** Bind mount permission mismatch between host and container users
✅ **Permanent fix:** Use Docker volumes (updated in `setup.sh`)
✅ **Migration path:** Run `migrate_to_docker_volume.sh` for existing installs
✅ **Quick fix:** Run `fix_mysql_permissions.sh` without migration
✅ **Verification:** Check logs for "Operating system error number 13" (should be none)
✅ **Benefits:** No more manual permission fixes, better performance, easier maintenance

## Additional Resources

- [Docker Volumes Documentation](https://docs.docker.com/storage/volumes/)
- [MySQL Docker Image](https://hub.docker.com/_/mysql)
- [InnoDB Redo Log Configuration](https://dev.mysql.com/doc/refman/8.0/en/innodb-redo-log.html)
