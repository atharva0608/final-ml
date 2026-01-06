#!/bin/bash
# Spot Optimizer Platform - Docker Startup Script
# Generated: 2026-01-06
# Purpose: Bridges the gap between git repo and running Docker containers

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Spot Optimizer Platform - Startup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Function to wait for a service to be ready
wait_for_service() {
    local service=$1
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}⏳ Waiting for $service to be ready...${NC}"
    while [ $attempt -le $max_attempts ]; do
        if docker-compose -f docker/docker-compose.yml ps | grep -q "$service.*Up.*healthy\|$service.*Up"; then
            echo -e "${GREEN}✅ $service is ready${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo -e "\n${RED}❌ $service failed to become ready${NC}"
    return 1
}

# Function to validate environment variables
validate_env() {
    local required_vars=("DATABASE_URL" "REDIS_URL" "JWT_SECRET_KEY")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if ! grep -q "^${var}=" .env || grep -q "^${var}=$" .env; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo -e "${RED}❌ Missing required environment variables:${NC}"
        for var in "${missing_vars[@]}"; do
            echo -e "   - $var"
        done
        return 1
    fi
    return 0
}

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found.${NC}"
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}Creating from .env.example...${NC}"
        cp .env.example .env
        echo -e "${GREEN}✅ Created .env file${NC}"
    else
        echo -e "${RED}❌ .env.example not found. Cannot create .env file.${NC}"
        exit 1
    fi
    echo -e "${YELLOW}⚠️  Edit .env before proceeding for production use!${NC}"
    echo ""
fi

# Validate environment variables
echo -e "${BLUE}🔍 Validating environment configuration...${NC}"
if ! validate_env; then
    echo -e "${YELLOW}⚠️  Please update .env with required values${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Environment configuration valid${NC}"
echo ""

# Check if Docker is running
echo -e "${BLUE}🔍 Checking Docker status...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker and try again.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Check docker-compose version
echo -e "${BLUE}🔍 Checking docker-compose...${NC}"
if command_exists docker-compose; then
    COMPOSE_CMD="docker-compose"
    echo -e "${GREEN}✅ docker-compose found (v1 style)${NC}"
elif docker compose version > /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    echo -e "${GREEN}✅ docker compose found (v2 style)${NC}"
else
    echo -e "${RED}❌ docker-compose not found. Please install Docker Compose.${NC}"
    exit 1
fi
echo ""

# Parse command line arguments
MODE="${1:-up}"
DETACH="${2:--d}"

case "$MODE" in
    up)
        echo -e "${BLUE}🚀 Starting Spot Optimizer Platform...${NC}"
        echo ""

        # Check if images exist, build if needed
        echo -e "${BLUE}🔍 Checking Docker images...${NC}"
        if ! $COMPOSE_CMD -f docker/docker-compose.yml images | grep -q "backend\|frontend"; then
            echo -e "${YELLOW}⚠️  Docker images not found. Building...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build
            echo -e "${GREEN}✅ Docker images built${NC}"
        else
            echo -e "${GREEN}✅ Docker images found${NC}"
        fi
        echo ""

        # Start database and redis first
        echo -e "${BLUE}🗄️  Starting database services...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml up -d postgres redis

        # Wait for postgres and redis
        wait_for_service "postgres" || {
            echo -e "${RED}❌ PostgreSQL failed to start. Check logs: $COMPOSE_CMD -f docker/docker-compose.yml logs postgres${NC}"
            exit 1
        }
        wait_for_service "redis" || {
            echo -e "${RED}❌ Redis failed to start. Check logs: $COMPOSE_CMD -f docker/docker-compose.yml logs redis${NC}"
            exit 1
        }
        echo ""

        # Run database migrations
        echo -e "${YELLOW}📦 Running database migrations...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml run --rm backend alembic upgrade head || {
            echo -e "${RED}❌ Migrations failed. Check database connection.${NC}"
            echo -e "${YELLOW}Attempting to continue anyway...${NC}"
        }
        echo -e "${GREEN}✅ Database migrations complete${NC}"
        echo ""

        # Start all remaining services
        echo -e "${BLUE}🐳 Starting application services...${NC}"
        if [ "$DETACH" = "-d" ]; then
            $COMPOSE_CMD -f docker/docker-compose.yml up -d
            echo ""

            # Wait for critical services
            echo -e "${BLUE}⏳ Waiting for services to be healthy...${NC}"
            wait_for_service "backend"
            wait_for_service "celery-worker"
            wait_for_service "frontend"
            echo ""

            echo -e "${GREEN}✅ All services started successfully!${NC}"
            echo ""
            echo -e "${BLUE}📊 Service Status:${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml ps
        else
            echo -e "${YELLOW}⚠️  Starting in foreground mode (Ctrl+C to stop)${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml up
        fi

        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}✅ Platform is running!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo -e "${BLUE}📍 Access Points:${NC}"
        echo -e "  Frontend:    ${GREEN}http://localhost${NC} or ${GREEN}http://localhost:80${NC}"
        echo -e "  Backend API: ${GREEN}http://localhost:8000${NC}"
        echo -e "  API Docs:    ${GREEN}http://localhost:8000/docs${NC}"
        echo -e "  Postgres:    localhost:5432"
        echo -e "  Redis:       localhost:6379"
        echo ""
        echo -e "${BLUE}🔧 Useful Commands:${NC}"
        echo -e "  View logs:        ./start.sh logs"
        echo -e "  Stop services:    ./start.sh down"
        echo -e "  Restart:          ./start.sh restart"
        echo -e "  Shell (backend):  ./start.sh shell backend"
        echo -e "  Run migrations:   ./start.sh migrate"
        echo -e "  Rebuild images:   ./start.sh build"
        echo ""
        echo -e "${BLUE}🩺 Health Check:${NC}"
        echo -e "  Backend:  curl http://localhost:8000/health"
        echo -e "  Frontend: curl http://localhost"
        echo ""
        ;;

    down)
        echo -e "${YELLOW}🛑 Stopping Spot Optimizer Platform...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml down
        echo -e "${GREEN}✅ All services stopped${NC}"
        ;;

    restart)
        echo -e "${YELLOW}🔄 Restarting Spot Optimizer Platform...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml restart
        echo -e "${GREEN}✅ All services restarted${NC}"
        echo ""
        $COMPOSE_CMD -f docker/docker-compose.yml ps
        ;;

    logs)
        SERVICE="${2:-}"
        if [ -n "$SERVICE" ]; then
            echo -e "${BLUE}📋 Showing logs for $SERVICE (Ctrl+C to exit)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml logs -f "$SERVICE"
        else
            echo -e "${BLUE}📋 Showing logs for all services (Ctrl+C to exit)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml logs -f
        fi
        ;;

    build)
        echo -e "${BLUE}🔨 Rebuilding Docker images...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache
        echo -e "${GREEN}✅ Build complete${NC}"
        ;;

    fresh)
        echo -e "${BLUE}🆕 Fresh installation (rebuilds everything)...${NC}"
        echo ""

        # Stop and remove everything
        echo -e "${YELLOW}🛑 Stopping existing containers...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml down -v 2>/dev/null || true
        echo ""

        # Build images
        echo -e "${BLUE}🔨 Building Docker images...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache
        echo ""

        # Start services
        echo -e "${BLUE}🚀 Starting services...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml up -d postgres redis
        echo ""

        # Wait for database
        wait_for_service "postgres"
        wait_for_service "redis"
        echo ""

        # Run migrations
        echo -e "${BLUE}📦 Running database migrations...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml run --rm backend alembic upgrade head
        echo ""

        # Start remaining services
        $COMPOSE_CMD -f docker/docker-compose.yml up -d
        echo ""

        # Wait for services
        echo -e "${BLUE}⏳ Waiting for services...${NC}"
        wait_for_service "backend"
        wait_for_service "frontend"
        echo ""

        echo -e "${GREEN}✅ Fresh installation complete!${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml ps
        ;;

    clean)
        echo -e "${RED}🗑️  Cleaning up (removes containers, volumes, and images)...${NC}"
        echo -e "${YELLOW}⚠️  This will DELETE all data. Are you sure? (y/N)${NC}"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            $COMPOSE_CMD -f docker/docker-compose.yml down -v --rmi all
            echo -e "${GREEN}✅ Cleanup complete${NC}"
        else
            echo -e "${YELLOW}Cancelled${NC}"
        fi
        ;;

    migrate)
        echo -e "${BLUE}📦 Running database migrations...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml run --rm backend alembic upgrade head
        echo -e "${GREEN}✅ Migrations complete${NC}"
        ;;

    shell)
        SERVICE="${2:-backend}"
        echo -e "${BLUE}🐚 Opening shell in $SERVICE container...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml exec "$SERVICE" bash
        ;;

    test)
        echo -e "${BLUE}🧪 Running tests...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml run --rm backend pytest
        ;;

    status)
        echo -e "${BLUE}📊 Service Status:${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml ps
        echo ""
        echo -e "${BLUE}🩺 Health Checks:${NC}"
        echo -n "  Backend:  "
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Healthy${NC}"
        else
            echo -e "${RED}❌ Not responding${NC}"
        fi
        echo -n "  Frontend: "
        if curl -sf http://localhost > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Healthy${NC}"
        else
            echo -e "${RED}❌ Not responding${NC}"
        fi
        ;;

    *)
        echo -e "${RED}❌ Unknown command: $MODE${NC}"
        echo ""
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${BLUE}Spot Optimizer Platform - Start Script${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo -e "${BLUE}Usage:${NC}"
        echo -e "  ./start.sh [command] [options]"
        echo ""
        echo -e "${BLUE}🚀 Primary Commands:${NC}"
        echo -e "  ${GREEN}up${NC}       Start all services (default, use -d for detached mode)"
        echo -e "  ${GREEN}down${NC}     Stop all services"
        echo -e "  ${GREEN}restart${NC}  Restart all services"
        echo -e "  ${GREEN}status${NC}   Show service status and health checks"
        echo ""
        echo -e "${BLUE}🔧 Maintenance Commands:${NC}"
        echo -e "  ${GREEN}logs${NC}     Show logs (add service name for specific service)"
        echo -e "  ${GREEN}build${NC}    Rebuild Docker images from scratch"
        echo -e "  ${GREEN}fresh${NC}    Fresh installation (stops, rebuilds, migrates, starts)"
        echo -e "  ${GREEN}migrate${NC}  Run database migrations"
        echo -e "  ${GREEN}clean${NC}    Remove all containers, volumes, and images"
        echo ""
        echo -e "${BLUE}🐚 Development Commands:${NC}"
        echo -e "  ${GREEN}shell${NC}    Open bash shell in container (specify service name)"
        echo -e "  ${GREEN}test${NC}     Run test suite"
        echo ""
        echo -e "${BLUE}📋 Examples:${NC}"
        echo -e "  ./start.sh                  # Start all services in detached mode"
        echo -e "  ./start.sh up -f            # Start in foreground (see live logs)"
        echo -e "  ./start.sh status           # Check service health"
        echo -e "  ./start.sh logs backend     # View backend logs only"
        echo -e "  ./start.sh shell frontend   # Open shell in frontend container"
        echo -e "  ./start.sh fresh            # Clean install (for troubleshooting)"
        echo -e "  ./start.sh migrate          # Run database migrations"
        echo ""
        echo -e "${BLUE}🩺 Quick Health Check:${NC}"
        echo -e "  After starting, verify services are running:"
        echo -e "    ${GREEN}./start.sh status${NC}"
        echo -e "  or visit:"
        echo -e "    Frontend:  ${GREEN}http://localhost${NC}"
        echo -e "    Backend:   ${GREEN}http://localhost:8000/docs${NC}"
        echo ""
        echo -e "${BLUE}💡 First Time Setup:${NC}"
        echo -e "  1. Ensure Docker is running"
        echo -e "  2. Update .env file with your configuration"
        echo -e "  3. Run: ${GREEN}./start.sh fresh${NC}"
        echo -e "  4. Access frontend at ${GREEN}http://localhost${NC}"
        echo ""
        exit 1
        ;;
esac
