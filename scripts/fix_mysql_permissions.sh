#!/bin/bash
# Fix MySQL InnoDB Permission Errors
# Resolves: "Operating system error number 13" and "mysqld does not have access rights"

set -e

echo "=================================================================="
echo "MySQL Permission Fix Script"
echo "=================================================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
   echo "⚠️  This script should be run as root or with sudo"
   echo "   Run: sudo $0"
   exit 1
fi

# Check if MySQL container exists
if ! docker ps -a | grep -q spot-mysql; then
    echo "❌ MySQL container 'spot-mysql' not found!"
    echo "   Run setup.sh first to create the container"
    exit 1
fi

echo "Step 1: Stopping MySQL container..."
docker stop spot-mysql 2>/dev/null || true
echo "   ✓ Container stopped"
echo ""

echo "Step 2: Checking data directory permissions..."
if [ -d "/var/lib/docker/volumes/spot-mysql-data/_data" ]; then
    DATA_DIR="/var/lib/docker/volumes/spot-mysql-data/_data"
    echo "   Found Docker volume: $DATA_DIR"
elif docker volume inspect spot-mysql-data >/dev/null 2>&1; then
    DATA_DIR=$(docker volume inspect spot-mysql-data -f '{{.Mountpoint}}')
    echo "   Found Docker volume: $DATA_DIR"
else
    echo "   ⚠️  Docker volume 'spot-mysql-data' not found"
    echo "   Container may be using bind mount or different volume"
    DATA_DIR=""
fi

if [ -n "$DATA_DIR" ] && [ -d "$DATA_DIR" ]; then
    echo ""
    echo "Step 3: Current permissions:"
    ls -la "$DATA_DIR" | head -10
    echo ""

    echo "Step 4: Fixing permissions..."
    # MySQL inside container runs as user mysql (uid 999 typically)
    # But permissions should be fixed from inside container
    echo "   Starting container temporarily to fix permissions..."

    docker start spot-mysql
    sleep 5

    # Fix permissions from inside container
    docker exec spot-mysql bash -c "
        chown -R mysql:mysql /var/lib/mysql 2>/dev/null || true
        chmod -R 750 /var/lib/mysql 2>/dev/null || true

        # Fix redo log directory specifically
        if [ -d /var/lib/mysql/#innodb_redo ]; then
            chown -R mysql:mysql /var/lib/mysql/#innodb_redo
            chmod 750 /var/lib/mysql/#innodb_redo
        fi

        # Fix temp directory
        if [ -d /var/lib/mysql/#innodb_temp ]; then
            chown -R mysql:mysql /var/lib/mysql/#innodb_temp
            chmod 750 /var/lib/mysql/#innodb_temp
        fi
    "

    echo "   ✓ Permissions fixed"
else
    echo ""
    echo "Step 3: Data directory not accessible from host"
    echo "   Will fix from inside container..."

    docker start spot-mysql
    sleep 5

    docker exec spot-mysql bash -c "
        chown -R mysql:mysql /var/lib/mysql
        chmod -R 750 /var/lib/mysql

        if [ -d /var/lib/mysql/#innodb_redo ]; then
            chown -R mysql:mysql /var/lib/mysql/#innodb_redo
            chmod 750 /var/lib/mysql/#innodb_redo
        fi

        if [ -d /var/lib/mysql/#innodb_temp ]; then
            chown -R mysql:mysql /var/lib/mysql/#innodb_temp
            chmod 750 /var/lib/mysql/#innodb_temp
        fi
    "
    echo "   ✓ Permissions fixed"
fi

echo ""
echo "Step 5: Restarting MySQL container with clean state..."
docker restart spot-mysql
echo "   ✓ Container restarted"

echo ""
echo "Step 6: Waiting for MySQL to be ready..."
sleep 8

# Wait for MySQL to be fully ready
for i in {1..30}; do
    if docker exec spot-mysql mysqladmin ping -h localhost --silent 2>/dev/null; then
        echo "   ✓ MySQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "   ⚠️  MySQL didn't start in 30 seconds"
        echo "   Check logs: docker logs spot-mysql --tail 50"
        exit 1
    fi
    sleep 1
done

echo ""
echo "Step 7: Verifying no permission errors..."
ERRORS=$(docker logs spot-mysql --tail 100 2>&1 | grep -c "Operating system error number 13" || true)

if [ "$ERRORS" -eq 0 ]; then
    echo "   ✓ No permission errors found!"
else
    echo "   ⚠️  Still seeing $ERRORS permission errors"
    echo "   Recent errors:"
    docker logs spot-mysql --tail 20 2>&1 | grep "ERROR" || echo "   (No recent errors)"
fi

echo ""
echo "Step 8: Testing database connection..."
if docker exec spot-mysql mysql -u root -p'SpotOptimizer2024!' -e "SELECT 1;" >/dev/null 2>&1; then
    echo "   ✓ Root connection works"
else
    echo "   ❌ Root connection failed"
    exit 1
fi

if docker exec spot-mysql mysql -u spotuser -p'SpotUser2024!' -D spot_optimizer -e "SELECT 1;" >/dev/null 2>&1; then
    echo "   ✓ User connection works"
else
    echo "   ❌ User connection failed"
    echo "   Run: ./scripts/test_database.sh"
    exit 1
fi

echo ""
echo "=================================================================="
echo "✅ MySQL Permission Fix Complete!"
echo "=================================================================="
echo ""
echo "MySQL Status:"
docker ps | grep spot-mysql
echo ""
echo "To verify:"
echo "  docker logs spot-mysql --tail 20"
echo "  ./scripts/test_database.sh"
echo ""
