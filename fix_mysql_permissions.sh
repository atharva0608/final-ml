#!/bin/bash
# ==============================================================================
# Fix MySQL Permission Issues on EC2
# ==============================================================================

echo "Fixing MySQL Docker container permission issues..."

# Stop backend service
echo "1. Stopping backend service..."
sudo systemctl stop spot-optimizer-backend

# Stop MySQL container
echo "2. Stopping MySQL container..."
docker stop spot-mysql

# Fix permissions on MySQL data directory
echo "3. Fixing permissions on /home/ubuntu/mysql-data..."
sudo chown -R 999:999 /home/ubuntu/mysql-data

# Start MySQL container
echo "4. Starting MySQL container..."
docker start spot-mysql

# Wait for MySQL to stabilize
echo "5. Waiting for MySQL to initialize (30 seconds)..."
sleep 30

# Verify MySQL is working
echo "6. Verifying MySQL connection..."
if docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SELECT 1;" spot_optimizer > /dev/null 2>&1; then
    echo "✓ MySQL is working correctly"
else
    echo "✗ MySQL connection failed - may need more time to start"
fi

# Start backend service
echo "7. Starting backend service..."
sudo systemctl start spot-optimizer-backend

# Wait for backend to start
sleep 5

# Check backend status
echo "8. Checking backend status..."
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo "✓ Backend is running"
else
    echo "✗ Backend may still be starting..."
fi

echo ""
echo "Fix completed! Check MySQL logs:"
echo "  docker logs --tail 50 spot-mysql"
echo ""
echo "The InnoDB permission errors should be gone."
