#!/bin/bash
set -e

# Get the directory where this script is located and navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🚀 Initializing Docker Deployment..."
echo "=================================="
echo "📁 Project Root: $PROJECT_ROOT"
echo ""

# 1. Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Error: Docker Compose is not installed"
    exit 1
fi

# Use 'docker compose' or 'docker-compose' depending on what's available
if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# 2. Create .env if missing
if [ ! -f backend/.env ]; then
    echo "⚠️  Creating default backend/.env..."
    cat > backend/.env << 'ENVEOF'
DATABASE_URL=postgresql://spotadmin:spotpass123@db:5432/spot_optimizer
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=change-this-in-production-$(openssl rand -hex 32)
ENABLE_TEST_USERS=true
ENVIRONMENT=production
LOG_LEVEL=INFO
ENVEOF
    echo "✓ Created backend/.env"
fi

# 3. Stop and remove existing containers
echo ""
echo "🛑 Stopping old services..."
$COMPOSE_CMD down -v

# 4. Build and Start Services
echo ""
echo "🏗️  Building and Starting Services..."
$COMPOSE_CMD up -d --build

# 5. Wait for database to be ready
echo ""
echo "⏳ Waiting for database to be ready..."
timeout=60
counter=0
until $COMPOSE_CMD exec -T db pg_isready -U spotadmin -d spot_optimizer > /dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
        echo "❌ Database failed to start within ${timeout} seconds"
        $COMPOSE_CMD logs db
        exit 1
    fi
    echo "  Waiting... ($counter/$timeout)"
    sleep 1
done
echo "✓ Database is ready"

# 6. Run Database Migrations and Seeding
echo ""
echo "🌱 Initializing database..."
$COMPOSE_CMD exec -T backend python -c "
from database.connection import init_db, seed_test_users
print('Creating tables...')
init_db()
print('Seeding test users...')
seed_test_users()
print('✓ Database initialized')
" || echo "⚠️  Database initialization failed (may already be initialized)"

# 7. Show status
echo ""
echo "=================================="
echo "✅ Deployment Complete!"
echo "=================================="
echo ""
echo "📊 Service Status:"
$COMPOSE_CMD ps
echo ""
echo "🌐 Access Points:"
echo "  - Frontend: http://localhost:80"
echo "  - Backend API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
echo "🔑 Test Credentials:"
echo "  - Admin: admin / admin"
echo "  - Client: client / client"
echo ""
echo "📝 View Logs:"
echo "  $COMPOSE_CMD logs -f [service]"
echo "  Available services: db, redis, backend, frontend"
echo ""
echo "🛑 Stop Services:"
echo "  $COMPOSE_CMD down"
echo ""
