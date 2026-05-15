#!/bin/bash
# Spot Optimizer Platform - Docker Startup Script
# Generated: 2026-01-06
# Purpose: Bridges the gap between git repo and running Docker containers
#
# ════════════════════════════════════════════════════════════════════
# QUICK REFERENCE — ALL COMMANDS & FLAGS
# ════════════════════════════════════════════════════════════════════
#
# USAGE: ./start.sh [command] [flags]
#
# ── Flags (combine with any command) ────────────────────────────────
#   -novolume              Rebuild/restart WITHOUT touching volumes (preserves data) [DEFAULT for up]
#   --all                  Apply to all containers (default behaviour)
#   --container <name>     Target a specific container/service only
#   --full                 Wipe volumes + images + networks, then rebuild
#
# ── Primary Commands ─────────────────────────────────────────────────
#   ./start.sh                                   # Rebuild all containers, volumes preserved (default)
#   ./start.sh up                                # Same as above
#   ./start.sh up -novolume                      # Explicit: rebuild all, keep volumes
#   ./start.sh up --all                          # Rebuild all containers, volumes preserved
#   ./start.sh up --full                         # Wipe everything (volumes/images/networks) + rebuild
#   ./start.sh up --container backend            # Rebuild only the backend container
#   ./start.sh up --container backend -novolume  # Rebuild backend, keep volumes
#   ./start.sh up --container backend --full     # Full wipe + rebuild backend only
#
#   ./start.sh down                              # Stop all containers (volumes preserved)
#   ./start.sh down -novolume                    # Stop containers, explicitly keep volumes
#   ./start.sh down --full                       # Full teardown incl. volumes + images + networks
#   ./start.sh down --container frontend         # Stop and remove one container
#
#   ./start.sh restart                           # Restart all services
#   ./start.sh restart --all                     # Restart all services
#   ./start.sh restart --container celery-worker # Restart one service
#
#   ./start.sh status                            # Show service status + health checks
#
# ── Maintenance Commands ──────────────────────────────────────────────
#   ./start.sh logs                              # Stream logs for all services
#   ./start.sh logs --container frontend         # Stream logs for frontend only
#   ./start.sh build                             # Rebuild all Docker images
#   ./start.sh build --container backend         # Rebuild only backend image
#   ./start.sh fresh                             # Full fresh install (stops, rebuilds, migrates, starts)
#   ./start.sh migrate                           # Run database migrations
#   ./start.sh clean                             # Remove containers, volumes, images (interactive)
#
# ── Development Commands ──────────────────────────────────────────────
#   ./start.sh shell                             # Shell into backend container (default)
#   ./start.sh shell --container frontend        # Shell into specific container
#   ./start.sh test                              # Run test suite
#
# ════════════════════════════════════════════════════════════════════

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
shift 2>/dev/null || true

# Default flag values
FLAG_NOVOLUME=false
FLAG_ALL=false
FLAG_CONTAINER=""
FLAG_FULL=false
SERVICE=""

# Parse remaining flags and positional arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -novolume)
            FLAG_NOVOLUME=true
            shift
            ;;
        --all)
            FLAG_ALL=true
            shift
            ;;
        --container)
            if [[ -z "${2:-}" ]]; then
                echo -e "${RED}❌ --container requires a container/service name${NC}"
                exit 1
            fi
            FLAG_CONTAINER="$2"
            shift 2
            ;;
        --full)
            FLAG_FULL=true
            shift
            ;;
        *)
            SERVICE="$1"
            shift
            ;;
    esac
done

# Flag conflict validation
if [[ "$FLAG_FULL" == "true" && "$FLAG_NOVOLUME" == "true" ]]; then
    echo -e "${RED}❌ Conflicting flags: --full and -novolume cannot be used together${NC}"
    exit 1
fi
if [[ -n "$FLAG_CONTAINER" && "$FLAG_ALL" == "true" ]]; then
    echo -e "${RED}❌ Conflicting flags: --container and --all cannot be used together${NC}"
    exit 1
fi

# Helper: start databases first, then all services, then wait for health
start_all_services() {
    echo -e "${BLUE}🗄️  Starting database services...${NC}"
    $COMPOSE_CMD -f docker/docker-compose.yml up -d postgres redis
    echo ""
    echo -e "${BLUE}⏳ Waiting for databases...${NC}"
    wait_for_service "postgres" || {
        echo -e "${RED}❌ PostgreSQL failed to start${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml logs postgres
        exit 1
    }
    wait_for_service "redis" || {
        echo -e "${RED}❌ Redis failed to start${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml logs redis
        exit 1
    }
    echo ""
    echo -e "${BLUE}🐳 Starting application services...${NC}"
    echo -e "${YELLOW}  ↳ Database tables will be auto-created on startup${NC}"
    $COMPOSE_CMD -f docker/docker-compose.yml up -d
    echo ""
    echo -e "${BLUE}⏳ Waiting for services to be healthy...${NC}"
    wait_for_service "backend" || {
        echo -e "${RED}❌ Backend failed to start${NC}"
        echo -e "${YELLOW}Showing last 50 lines of backend logs:${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml logs --tail=50 backend
        exit 1
    }
    wait_for_service "celery-worker" || {
        echo -e "${YELLOW}⚠️  Celery worker issues (non-critical)${NC}"
    }
    wait_for_service "frontend" || {
        echo -e "${RED}❌ Frontend failed to start${NC}"
        exit 1
    }
    echo ""
}

# Helper: print access points and credentials after a successful startup
show_access_points() {
    echo -e "${GREEN}✅ All services started successfully!${NC}"
    echo ""
    echo -e "${BLUE}📊 Service Status:${NC}"
    $COMPOSE_CMD -f docker/docker-compose.yml ps
    echo ""
    echo -e "${BLUE}📋 Backend Initialization Logs:${NC}"
    $COMPOSE_CMD -f docker/docker-compose.yml logs backend | grep -E "(Database tables|Created default admin|Application starting)" | tail -5
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ Platform is READY!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}📍 Access Points:${NC}"
    echo -e "  Frontend:    ${GREEN}http://localhost${NC}"
    echo -e "  Backend API: ${GREEN}http://localhost:8000${NC}"
    echo -e "  API Docs:    ${GREEN}http://localhost:8000/docs${NC}"
    echo ""
    echo -e "${BLUE}🔑 Login Credentials:${NC}"
    echo ""
    echo -e "  ${YELLOW}Super Admin:${NC}"
    echo -e "    Email:    ${GREEN}admin@spotoptimizer.com${NC}"
    echo -e "    Password: ${GREEN}admin123${NC}"
    echo ""
    echo -e "  ${YELLOW}Demo Client:${NC}"
    echo -e "    Email:    ${GREEN}demo@spotoptimizer.com${NC}"
    echo -e "    Password: ${GREEN}demo1234${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  Change default passwords immediately!${NC}"
    echo ""
    echo -e "${BLUE}🔧 Useful Commands:${NC}"
    echo -e "  View logs:      ./start.sh logs [--container <name>]"
    echo -e "  Stop all:       ./start.sh down"
    echo -e "  Service status: ./start.sh status"
    echo ""
}

case "$MODE" in
    up)
        # ── Specific container: stop → rebuild → start one service ───────────
        if [[ -n "$FLAG_CONTAINER" ]]; then
            echo -e "${BLUE}🔄 Targeting container: ${YELLOW}$FLAG_CONTAINER${NC}"
            echo ""
            if [[ "$FLAG_FULL" == "true" ]]; then
                echo -e "${YELLOW}🗑️  Full teardown of $FLAG_CONTAINER (container + volumes + image)...${NC}"
                $COMPOSE_CMD -f docker/docker-compose.yml stop "$FLAG_CONTAINER" 2>/dev/null || true
                $COMPOSE_CMD -f docker/docker-compose.yml rm -f -v "$FLAG_CONTAINER" 2>/dev/null || true
                docker images | grep -E "docker[-_]${FLAG_CONTAINER}|${FLAG_CONTAINER}" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
                echo -e "${GREEN}✅ $FLAG_CONTAINER fully cleared${NC}"
            elif [[ "$FLAG_NOVOLUME" == "true" ]]; then
                echo -e "${YELLOW}🛑 Stopping $FLAG_CONTAINER (preserving volumes)...${NC}"
                $COMPOSE_CMD -f docker/docker-compose.yml stop "$FLAG_CONTAINER" 2>/dev/null || true
                $COMPOSE_CMD -f docker/docker-compose.yml rm -f "$FLAG_CONTAINER" 2>/dev/null || true
            else
                echo -e "${YELLOW}🛑 Stopping $FLAG_CONTAINER...${NC}"
                $COMPOSE_CMD -f docker/docker-compose.yml stop "$FLAG_CONTAINER" 2>/dev/null || true
                $COMPOSE_CMD -f docker/docker-compose.yml rm -f "$FLAG_CONTAINER" 2>/dev/null || true
            fi
            echo ""
            echo -e "${BLUE}🔨 Rebuilding $FLAG_CONTAINER...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache "$FLAG_CONTAINER"
            echo -e "${BLUE}🚀 Starting $FLAG_CONTAINER...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml up -d "$FLAG_CONTAINER"
            echo ""
            echo -e "${GREEN}✅ $FLAG_CONTAINER rebuilt and restarted${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml ps "$FLAG_CONTAINER"

        # ── --full: wipe volumes + images + networks, then rebuild all ────────
        elif [[ "$FLAG_FULL" == "true" ]]; then
            echo -e "${BLUE}🔥 Full Wipe + Rebuild: containers, volumes, images, networks${NC}"
            echo ""
            echo -e "${YELLOW}🗑️  Removing all containers, volumes, images, and networks...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml down --volumes --rmi all --remove-orphans 2>/dev/null || true
            echo -e "${YELLOW}  ↳ Pruning unused Docker networks...${NC}"
            docker network prune -f
            echo -e "${GREEN}✅ Full cleanup complete${NC}"
            echo ""
            echo -e "${BLUE}🔨 Building Docker images from scratch...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache
            echo -e "${GREEN}✅ Docker images built${NC}"
            echo ""
            start_all_services
            show_access_points

        # ── -novolume: rebuild code/images, preserve volume data ─────────────
        elif [[ "$FLAG_NOVOLUME" == "true" ]]; then
            echo -e "${BLUE}🔨 Rebuild (volumes preserved): Spot Optimizer Platform${NC}"
            echo ""
            echo -e "${YELLOW}🛑 Stopping containers (volumes are preserved)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml down 2>/dev/null || true
            echo -e "${YELLOW}  ↳ Removing old Docker images...${NC}"
            docker images | grep "docker-" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
            echo -e "${GREEN}✅ Containers stopped, volumes intact${NC}"
            echo ""
            echo -e "${BLUE}🔨 Building Docker images from scratch...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache
            echo -e "${GREEN}✅ Docker images built${NC}"
            echo ""
            start_all_services
            show_access_points

        # ── Default / --all: rebuild all containers, volumes preserved ─────────
        else
            echo -e "${BLUE}🔨 Rebuild All Containers (volumes preserved): Spot Optimizer Platform${NC}"
            echo -e "${BLUE}Containers and images will be rebuilt — your data volumes are safe${NC}"
            echo ""
            echo -e "${YELLOW}🛑 Stopping containers (volumes are preserved)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml down 2>/dev/null || true
            echo -e "${YELLOW}  ↳ Removing old Docker images...${NC}"
            docker images | grep "docker-" | awk '{print $3}' | xargs -r docker rmi -f 2>/dev/null || true
            echo -e "${GREEN}✅ Containers stopped, volumes intact${NC}"
            echo ""
            echo -e "${BLUE}🔨 Building Docker images from scratch...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache
            echo -e "${GREEN}✅ Docker images built${NC}"
            echo ""
            start_all_services
            show_access_points
        fi
        ;;

    down)
        if [[ -n "$FLAG_CONTAINER" ]]; then
            echo -e "${YELLOW}🛑 Stopping container: $FLAG_CONTAINER${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml stop "$FLAG_CONTAINER"
            $COMPOSE_CMD -f docker/docker-compose.yml rm -f "$FLAG_CONTAINER"
            echo -e "${GREEN}✅ $FLAG_CONTAINER stopped and removed${NC}"
        elif [[ "$FLAG_FULL" == "true" ]]; then
            echo -e "${RED}🗑️  Full teardown: ALL containers, volumes, images, networks...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml down --volumes --rmi all --remove-orphans 2>/dev/null || true
            docker network prune -f
            echo -e "${GREEN}✅ Full teardown complete${NC}"
        elif [[ "$FLAG_NOVOLUME" == "true" ]]; then
            echo -e "${YELLOW}🛑 Stopping all containers (preserving volumes)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml down
            echo -e "${GREEN}✅ All services stopped (volumes preserved)${NC}"
        else
            echo -e "${YELLOW}🛑 Stopping Spot Optimizer Platform...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml down
            echo -e "${GREEN}✅ All services stopped${NC}"
        fi
        ;;

    restart)
        if [[ -n "$FLAG_CONTAINER" ]]; then
            echo -e "${YELLOW}🔄 Restarting container: $FLAG_CONTAINER${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml restart "$FLAG_CONTAINER"
            echo -e "${GREEN}✅ $FLAG_CONTAINER restarted${NC}"
            echo ""
            $COMPOSE_CMD -f docker/docker-compose.yml ps "$FLAG_CONTAINER"
        else
            echo -e "${YELLOW}🔄 Restarting Spot Optimizer Platform...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml restart
            echo -e "${GREEN}✅ All services restarted${NC}"
            echo ""
            $COMPOSE_CMD -f docker/docker-compose.yml ps
        fi
        ;;

    logs)
        TARGET="${FLAG_CONTAINER:-$SERVICE}"
        if [[ -n "$TARGET" ]]; then
            echo -e "${BLUE}📋 Showing logs for $TARGET (Ctrl+C to exit)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml logs -f "$TARGET"
        else
            echo -e "${BLUE}📋 Showing logs for all services (Ctrl+C to exit)...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml logs -f
        fi
        ;;

    build)
        if [[ -n "$FLAG_CONTAINER" ]]; then
            echo -e "${BLUE}🔨 Rebuilding Docker image for: $FLAG_CONTAINER${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache "$FLAG_CONTAINER"
            echo -e "${GREEN}✅ Build complete for $FLAG_CONTAINER${NC}"
        else
            echo -e "${BLUE}🔨 Rebuilding all Docker images...${NC}"
            $COMPOSE_CMD -f docker/docker-compose.yml build --no-cache
            echo -e "${GREEN}✅ Build complete${NC}"
        fi
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
        TARGET="${FLAG_CONTAINER:-${SERVICE:-backend}}"
        echo -e "${BLUE}🐚 Opening shell in $TARGET container...${NC}"
        $COMPOSE_CMD -f docker/docker-compose.yml exec "$TARGET" bash
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
        echo -e "  ./start.sh [command] [flags]"
        echo ""
        echo -e "${BLUE}🚀 Primary Commands:${NC}"
        echo -e "  ${GREEN}up${NC}       Start/rebuild all services (default)"
        echo -e "  ${GREEN}down${NC}     Stop all services"
        echo -e "  ${GREEN}restart${NC}  Restart all services"
        echo -e "  ${GREEN}status${NC}   Show service status and health checks"
        echo ""
        echo -e "${BLUE}🏳️  Flags (combine with any command):${NC}"
        echo -e "  ${YELLOW}-novolume${NC}            Rebuild/restart without touching volumes (preserve data)"
        echo -e "  ${YELLOW}--all${NC}                Apply to all containers (default behaviour)"
        echo -e "  ${YELLOW}--container <name>${NC}   Target a specific container/service only"
        echo -e "  ${YELLOW}--full${NC}               Full wipe: remove volumes + images + networks, then rebuild"
        echo ""
        echo -e "${BLUE}🔧 Maintenance Commands:${NC}"
        echo -e "  ${GREEN}logs${NC}     Show logs (use --container for a specific service)"
        echo -e "  ${GREEN}build${NC}    Rebuild Docker images (use --container for a specific service)"
        echo -e "  ${GREEN}fresh${NC}    Fresh installation (stops, rebuilds, migrates, starts)"
        echo -e "  ${GREEN}migrate${NC}  Run database migrations"
        echo -e "  ${GREEN}clean${NC}    Remove all containers, volumes, and images (interactive)"
        echo ""
        echo -e "${BLUE}🐚 Development Commands:${NC}"
        echo -e "  ${GREEN}shell${NC}    Open bash shell in container (use --container to specify)"
        echo -e "  ${GREEN}test${NC}     Run test suite"
        echo ""
        echo -e "${BLUE}📋 Examples:${NC}"
        echo -e "  ./start.sh                                    # Full rebuild (removes volumes)"
        echo -e "  ./start.sh up -novolume                       # Rebuild, keep existing data"
        echo -e "  ./start.sh up --full                          # Wipe everything and rebuild"
        echo -e "  ./start.sh up --all                           # Rebuild all (same as default)"
        echo -e "  ./start.sh up --container backend             # Rebuild only the backend"
        echo -e "  ./start.sh up --container backend --full      # Full wipe + rebuild backend only"
        echo -e "  ./start.sh up --container backend -novolume   # Rebuild backend, keep volumes"
        echo -e "  ./start.sh restart --all                      # Restart all services"
        echo -e "  ./start.sh restart --container celery-worker  # Restart one service"
        echo -e "  ./start.sh down -novolume                     # Stop containers, keep volumes"
        echo -e "  ./start.sh down --full                        # Full teardown incl. volumes"
        echo -e "  ./start.sh down --container frontend          # Stop and remove one container"
        echo -e "  ./start.sh logs --container frontend          # Stream logs for frontend"
        echo -e "  ./start.sh build --container backend          # Rebuild only backend image"
        echo -e "  ./start.sh shell --container frontend         # Shell into frontend container"
        echo -e "  ./start.sh status                             # Check service health"
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
