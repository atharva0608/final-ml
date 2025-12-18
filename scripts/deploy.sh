#!/bin/bash
###############################################################################
# Cloud Cost Optimizer Platform - Docker Deployment Script
# Version: 4.0.0 (Docker Compose + FastAPI + PostgreSQL + React)
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

print_header "Cloud Cost Optimizer Platform - Deployment"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_info "Platform Version: 4.0.0"
print_info "Architecture: FastAPI + PostgreSQL + Redis + React + Nginx"
print_info "Project Root: $PROJECT_ROOT"
echo ""

# Step 1: Check if containers are running
print_info "Step 1: Checking existing containers..."
if docker compose ps | grep -q "Up"; then
    print_warning "Containers are currently running"
    read -p "Do you want to rebuild and restart? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Deployment cancelled"
        exit 0
    fi

    print_info "Stopping existing containers..."
    docker compose down
    print_success "Containers stopped"
else
    print_success "No running containers detected"
fi

# Step 2: Backup database (if exists)
print_info "Step 2: Backing up database..."
if docker ps -a | grep -q "spot_optimizer_db"; then
    BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
    docker exec spot_optimizer_db pg_dump -U spotadmin spot_optimizer > "/tmp/$BACKUP_FILE" 2>/dev/null || true
    if [ -f "/tmp/$BACKUP_FILE" ]; then
        print_success "Database backed up to: /tmp/$BACKUP_FILE"
    else
        print_warning "No existing database to backup"
    fi
else
    print_warning "No existing database container found (fresh install)"
fi

# Step 3: Clean up old images and volumes (optional)
print_info "Step 3: Cleaning up old resources..."
read -p "Remove old images and volumes? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose down -v 2>/dev/null || true
    docker system prune -f 2>/dev/null || true
    print_success "Old resources cleaned"
else
    print_info "Skipping cleanup (keeping existing volumes)"
fi

# Step 4: Build containers
print_info "Step 4: Building Docker images..."
print_warning "This may take 5-10 minutes on first build..."
if docker compose build --no-cache; then
    print_success "Docker images built successfully"
else
    print_error "Docker build failed"
    exit 1
fi

# Step 5: Start containers
print_info "Step 5: Starting containers..."
if docker compose up -d; then
    print_success "Containers started"
else
    print_error "Failed to start containers"
    exit 1
fi

# Step 6: Wait for services to be ready
print_info "Step 6: Waiting for services to initialize..."
echo -n "  Waiting for database"
for i in {1..30}; do
    if docker compose exec -T db pg_isready -U spotadmin -d spot_optimizer &>/dev/null; then
        echo ""
        print_success "Database ready"
        break
    fi
    echo -n "."
    sleep 1
done

echo -n "  Waiting for backend"
for i in {1..30}; do
    if curl -s http://localhost:8000/health &>/dev/null; then
        echo ""
        print_success "Backend ready"
        break
    fi
    echo -n "."
    sleep 1
done

echo -n "  Waiting for frontend"
for i in {1..15}; do
    if curl -s http://localhost:80 &>/dev/null; then
        echo ""
        print_success "Frontend ready"
        break
    fi
    echo -n "."
    sleep 1
done

# Step 7: Check container health
print_info "Step 7: Verifying container health..."
echo ""
docker compose ps
echo ""

# Count healthy containers
HEALTHY_COUNT=$(docker compose ps | grep -c "(healthy)" || echo "0")
TOTAL_CONTAINERS=$(docker compose ps | grep -c "Up" || echo "0")

if [ "$TOTAL_CONTAINERS" -eq 0 ]; then
    print_error "No containers are running!"
    print_info "Check logs with: docker compose logs"
    exit 1
fi

print_info "Container Status: $TOTAL_CONTAINERS running, $HEALTHY_COUNT healthy"

# Step 8: Test endpoints
print_info "Step 8: Testing API endpoints..."

# Test health endpoint
if curl -s http://localhost:8000/health | grep -q "ok"; then
    print_success "Backend health check: PASSED"
else
    print_warning "Backend health check: FAILED (may still be initializing)"
fi

# Test frontend
if curl -s http://localhost:80 | grep -q "html"; then
    print_success "Frontend health check: PASSED"
else
    print_warning "Frontend health check: FAILED"
fi

# Test System Monitor API
if curl -s http://localhost:8000/api/v1/admin/health/overview &>/dev/null; then
    print_success "System Monitor API: ACCESSIBLE"
else
    print_warning "System Monitor API: NOT ACCESSIBLE (authentication may be required)"
fi

print_header "Deployment Complete!"

echo ""
print_info "Service URLs:"
echo "  🌐 Frontend:        http://localhost"
echo "  🔧 Backend API:     http://localhost:8000"
echo "  📚 API Docs:        http://localhost:8000/docs"
echo "  🗄️  PostgreSQL:      localhost:5432"
echo "  📦 Redis:           localhost:6379"
echo ""

print_info "Default Credentials:"
echo "  👤 Username: admin"
echo "  🔑 Password: admin"
echo ""

print_info "Useful Commands:"
echo "  📊 View all logs:"
echo "     docker compose logs -f"
echo ""
echo "  🔍 View backend logs only:"
echo "     docker compose logs -f backend"
echo ""
echo "  🛑 Stop all containers:"
echo "     docker compose down"
echo ""
echo "  🔄 Restart containers:"
echo "     docker compose restart"
echo ""
echo "  📈 Check container status:"
echo "     docker compose ps"
echo ""
echo "  🧹 Clean restart (removes volumes):"
echo "     docker compose down -v && docker compose up -d"
echo ""

print_info "Health Check Commands:"
echo "  Backend:  curl http://localhost:8000/health"
echo "  Frontend: curl http://localhost:80"
echo "  Database: docker compose exec db pg_isready -U spotadmin"
echo ""

print_info "Platform Features:"
echo "  ✓ Real-time System Monitor (10 components)"
echo "  ✓ ML Model Upload & Management"
echo "  ✓ Live Operations Dashboard"
echo "  ✓ Node Fleet Management"
echo "  ✓ Client Management"
echo "  ✓ JWT Authentication"
echo "  ✓ Health Checks (3-tier: healthy/degraded/critical)"
echo "  ✓ Auto-created admin user"
echo ""

if [ "$HEALTHY_COUNT" -ge 3 ]; then
    print_success "Deployment successful! 🚀"
    print_success "Platform is ready to use at http://localhost"
else
    print_warning "Deployment completed with warnings"
    print_info "Some containers may not be healthy yet. Wait 1-2 minutes and check:"
    print_info "  docker compose ps"
fi
