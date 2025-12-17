#!/bin/bash
set -e

echo "🚀 Initializing Docker Deployment..."
echo "=================================="

# 1. Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: Docker Compose is not installed"
    exit 1
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
docker-compose down -v

# 4. Build and Start Services
echo ""
echo "🏗️  Building and Starting Services..."
docker-compose up -d --build

# 5. Wait for database to be ready
echo ""
echo "⏳ Waiting for database to be ready..."
timeout=60
counter=0
until docker-compose exec -T db pg_isready -U spotadmin -d spot_optimizer > /dev/null 2>&1; do
    counter=$((counter + 1))
    if [ $counter -gt $timeout ]; then
        echo "❌ Database failed to start within ${timeout} seconds"
        docker-compose logs db
        exit 1
    fi
    echo "  Waiting... ($counter/$timeout)"
    sleep 1
done
echo "✓ Database is ready"

# 6. Run Database Migrations and Seeding
echo ""
echo "🌱 Initializing database..."
docker-compose exec -T backend python -c "
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
docker-compose ps
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
echo "  docker-compose logs -f [service]"
echo "  Available services: db, redis, backend, frontend"
echo ""
echo "🛑 Stop Services:"
echo "  docker-compose down"
echo ""
