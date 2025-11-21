#!/bin/bash
# Migrate MySQL from bind mount to Docker volume
# This fixes permission errors by using Docker-managed volumes

set -e

echo "=================================================================="
echo "MySQL Migration: Bind Mount → Docker Volume"
echo "=================================================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
   echo "⚠️  This script should be run as root or with sudo"
   echo "   Run: sudo $0"
   exit 1
fi

DB_ROOT_PASSWORD="${1:-SpotOptimizer2024!}"
DB_USER="${2:-spotuser}"
DB_PASSWORD="${3:-SpotUser2024!}"
DB_NAME="${4:-spot_optimizer}"

echo "Configuration:"
echo "  Database: $DB_NAME"
echo "  Root Password: $DB_ROOT_PASSWORD"
echo "  User: $DB_USER"
echo ""

# Check if MySQL container exists
if ! docker ps -a | grep -q spot-mysql; then
    echo "❌ MySQL container 'spot-mysql' not found!"
    echo "   Nothing to migrate."
    exit 0
fi

echo "Step 1: Checking current MySQL setup..."
CURRENT_MOUNT=$(docker inspect spot-mysql --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Type}}:{{.Source}}{{end}}{{end}}' 2>/dev/null || echo "")

if [[ "$CURRENT_MOUNT" == "volume"* ]]; then
    echo "   ✓ Already using Docker volume: ${CURRENT_MOUNT#volume:}"
    echo "   No migration needed!"
    exit 0
fi

if [[ "$CURRENT_MOUNT" == "bind"* ]]; then
    BIND_PATH="${CURRENT_MOUNT#bind:}"
    echo "   Found bind mount: $BIND_PATH"
    echo "   Will migrate to Docker volume"
else
    echo "   ⚠️  Unknown mount type or no mount found"
    echo "   Proceeding with fresh Docker volume setup"
    BIND_PATH=""
fi

echo ""
echo "Step 2: Creating backup and Docker volume..."

# Create Docker volume
if ! docker volume inspect spot-mysql-data >/dev/null 2>&1; then
    docker volume create spot-mysql-data
    echo "   ✓ Created Docker volume: spot-mysql-data"
else
    echo "   ✓ Docker volume already exists: spot-mysql-data"
fi

# Export data if bind mount exists and has data
if [ -n "$BIND_PATH" ] && [ -d "$BIND_PATH" ] && [ "$(ls -A $BIND_PATH 2>/dev/null)" ]; then
    echo ""
    echo "Step 3: Exporting existing database..."

    # Make sure MySQL is running for export
    docker start spot-mysql 2>/dev/null || true
    sleep 5

    # Export all databases
    BACKUP_FILE="/tmp/mysql_backup_$(date +%Y%m%d_%H%M%S).sql"
    if docker exec spot-mysql mysqldump -u root -p"$DB_ROOT_PASSWORD" --all-databases --single-transaction --quick --lock-tables=false > "$BACKUP_FILE" 2>/dev/null; then
        echo "   ✓ Database exported to: $BACKUP_FILE"
        BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
        echo "   Backup size: $BACKUP_SIZE"
    else
        echo "   ⚠️  Database export failed, will do clean migration"
        BACKUP_FILE=""
    fi
else
    echo ""
    echo "Step 3: No existing data to export (clean setup)"
    BACKUP_FILE=""
fi

echo ""
echo "Step 4: Stopping and removing old container..."
docker stop spot-mysql 2>/dev/null || true
docker rm spot-mysql 2>/dev/null || true
echo "   ✓ Old container removed"

# Backup bind mount directory
if [ -n "$BIND_PATH" ] && [ -d "$BIND_PATH" ]; then
    BACKUP_DIR="${BIND_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
    mv "$BIND_PATH" "$BACKUP_DIR"
    echo "   ✓ Bind mount backed up to: $BACKUP_DIR"
fi

echo ""
echo "Step 5: Creating new MySQL container with Docker volume..."
docker run -d \
    --name spot-mysql \
    --network spot-network \
    --restart unless-stopped \
    -e MYSQL_ROOT_PASSWORD="$DB_ROOT_PASSWORD" \
    -e MYSQL_DATABASE="$DB_NAME" \
    -e MYSQL_USER="$DB_USER" \
    -e MYSQL_PASSWORD="$DB_PASSWORD" \
    -p 3306:3306 \
    -v spot-mysql-data:/var/lib/mysql \
    mysql:8.0 \
    --default-authentication-plugin=mysql_native_password \
    --character-set-server=utf8mb4 \
    --collation-server=utf8mb4_unicode_ci \
    --max_connections=200 \
    --innodb_buffer_pool_size=256M \
    --innodb_log_buffer_size=16M

echo "   ✓ New container created"

echo ""
echo "Step 6: Waiting for MySQL to initialize..."
sleep 15

for i in {1..30}; do
    if docker exec spot-mysql mysqladmin ping -h localhost --silent 2>/dev/null; then
        echo "   ✓ MySQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "   ❌ MySQL didn't start in 30 seconds"
        echo "   Check logs: docker logs spot-mysql"
        exit 1
    fi
    sleep 2
done

# Import data if we have a backup
if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
    echo ""
    echo "Step 7: Importing database from backup..."

    if docker exec -i spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" < "$BACKUP_FILE" 2>/dev/null; then
        echo "   ✓ Database imported successfully!"

        # Verify import
        TABLE_COUNT=$(docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null || echo "0")
        echo "   ✓ Found $TABLE_COUNT tables in database"

        # Clean up backup file
        rm "$BACKUP_FILE"
        echo "   ✓ Temporary backup file cleaned up"
    else
        echo "   ⚠️  Import failed. Backup saved at: $BACKUP_FILE"
        echo "   You can manually import: docker exec -i spot-mysql mysql -u root -p'$DB_ROOT_PASSWORD' < $BACKUP_FILE"
    fi
else
    echo ""
    echo "Step 7: No backup to import (will import schema from repository)"
fi

echo ""
echo "Step 8: Verifying permissions..."
ERRORS=$(docker logs spot-mysql --tail 50 2>&1 | grep -c "Operating system error number 13" || true)

if [ "$ERRORS" -eq 0 ]; then
    echo "   ✓ No permission errors!"
else
    echo "   ⚠️  Found $ERRORS permission errors - running fix..."
    docker exec spot-mysql bash -c "chown -R mysql:mysql /var/lib/mysql && chmod -R 750 /var/lib/mysql"
    docker restart spot-mysql
    sleep 5
    echo "   ✓ Permissions fixed and container restarted"
fi

echo ""
echo "Step 9: Testing connections..."
if docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -e "SELECT 1;" >/dev/null 2>&1; then
    echo "   ✓ Root connection works"
else
    echo "   ❌ Root connection failed"
fi

if docker exec spot-mysql mysql -u "$DB_USER" -p"$DB_PASSWORD" -D "$DB_NAME" -e "SELECT 1;" >/dev/null 2>&1; then
    echo "   ✓ User connection works"
else
    echo "   ⚠️  User connection failed (may need to reimport schema)"
fi

echo ""
echo "=================================================================="
echo "✅ Migration Complete!"
echo "=================================================================="
echo ""
echo "New setup:"
echo "  Container: spot-mysql"
echo "  Volume: spot-mysql-data (Docker-managed)"
echo "  Mount: /var/lib/mysql"
echo ""
echo "Next steps:"
echo "  1. Reimport schema: docker exec -i spot-mysql mysql -u root -p'$DB_ROOT_PASSWORD' $DB_NAME < database/schema.sql"
echo "  2. Test database: ./scripts/test_database.sh"
echo "  3. Restart backend: sudo systemctl restart spot-optimizer-backend"
echo ""
if [ -n "$BACKUP_DIR" ]; then
    echo "Old data backed up at: $BACKUP_DIR"
    echo "You can remove it after verifying everything works: sudo rm -rf $BACKUP_DIR"
    echo ""
fi
