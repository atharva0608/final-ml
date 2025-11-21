#!/bin/bash
# Test database connectivity and show actual credentials

echo "==================================================================="
echo "AWS Spot Optimizer - Database Connection Diagnostics"
echo "==================================================================="
echo ""

# Get actual credentials from setup script
REPO_DIR="/home/ubuntu/final-ml"
if [ ! -f "$REPO_DIR/scripts/setup.sh" ]; then
    REPO_DIR="$(pwd)"
fi

DB_ROOT_PASSWORD="SpotOptimizer2024!"
DB_USER="spotuser"
DB_PASSWORD="SpotUser2024!"
DB_NAME="spot_optimizer"

echo "📋 Configuration:"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
echo "   Password: $DB_PASSWORD"
echo "   Root Password: $DB_ROOT_PASSWORD"
echo ""

echo "🔍 Testing MySQL container..."
if docker ps | grep -q spot-mysql; then
    echo "   ✓ MySQL container is running"
else
    echo "   ✗ MySQL container is NOT running!"
    echo "   Start it with: docker start spot-mysql"
    exit 1
fi
echo ""

echo "🔍 Testing root connection..."
if docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -e "SELECT 1;" > /dev/null 2>&1; then
    echo "   ✓ Root can connect"
else
    echo "   ✗ Root cannot connect with password: $DB_ROOT_PASSWORD"
    echo "   You may need to reset the root password"
fi
echo ""

echo "🔍 Testing user connection..."
if docker exec spot-mysql mysql -u "$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1;" "$DB_NAME" > /dev/null 2>&1; then
    echo "   ✓ User '$DB_USER' can connect"
else
    echo "   ✗ User '$DB_USER' cannot connect"
    echo "   Attempting to create/fix user..."

    docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -e "
        DROP USER IF EXISTS '$DB_USER'@'%';
        DROP USER IF EXISTS '$DB_USER'@'localhost';
        DROP USER IF EXISTS '$DB_USER'@'172.18.%';
        CREATE USER '$DB_USER'@'%' IDENTIFIED BY '$DB_PASSWORD';
        CREATE USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
        CREATE USER '$DB_USER'@'172.18.%' IDENTIFIED BY '$DB_PASSWORD';
        GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'%';
        GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
        GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'172.18.%';
        FLUSH PRIVILEGES;
    " 2>&1 | grep -v "Warning"

    # Test again
    if docker exec spot-mysql mysql -u "$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1;" "$DB_NAME" > /dev/null 2>&1; then
        echo "   ✓ User created and can now connect!"
    else
        echo "   ✗ Still cannot connect. Check MySQL logs"
        exit 1
    fi
fi
echo ""

echo "🔍 Checking database tables..."
TABLE_COUNT=$(docker exec spot-mysql mysql -u "$DB_USER" -p"$DB_PASSWORD" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null || echo "0")
echo "   Found $TABLE_COUNT tables"

if [ "$TABLE_COUNT" -eq 0 ]; then
    echo "   ⚠️  No tables found! Schema needs to be imported"
    echo "   Run: docker exec -i spot-mysql mysql -u root -p'$DB_ROOT_PASSWORD' $DB_NAME < database/schema.sql"
fi
echo ""

echo "🔍 Testing backend can connect..."
cd "$REPO_DIR/backend" 2>/dev/null || cd /home/ubuntu/spot-optimizer/backend 2>/dev/null || {
    echo "   ✗ Backend directory not found!"
    exit 1
}

if [ -f "venv/bin/python" ]; then
    cat > test_db.py << 'PYEOF'
import mysql.connector
import os

try:
    conn = mysql.connector.connect(
        host='127.0.0.1',
        user='spotuser',
        password='SpotUser2024!',
        database='spot_optimizer',
        port=3306
    )
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='spot_optimizer'")
    count = cursor.fetchone()[0]
    print(f"   ✓ Python can connect! Found {count} tables")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"   ✗ Python cannot connect: {e}")
    exit(1)
PYEOF

    ./venv/bin/python test_db.py
    rm test_db.py
else
    echo "   ⚠️  Virtual environment not set up yet"
fi
echo ""

echo "==================================================================="
echo "✅ Database diagnostics complete!"
echo "==================================================================="
echo ""
echo "To start backend manually with correct credentials:"
echo "  cd /home/ubuntu/spot-optimizer/backend"
echo "  source venv/bin/activate"
echo "  export DB_PASSWORD='SpotUser2024!'"
echo "  python backend.py"
echo ""
