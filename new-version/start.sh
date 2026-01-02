#!/bin/bash
# Spot Optimizer Platform - Docker Startup Script
# Generated: 2026-01-02
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

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✅ Created .env file. Please update with your actual configuration.${NC}"
    echo -e "${YELLOW}⚠️  Edit .env before proceeding for production use!${NC}"
    echo ""
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker and try again.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ docker-compose not found. Please install docker-compose.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ docker-compose found${NC}"
echo ""

# Parse command line arguments
MODE="${1:-up}"
DETACH="${2:--d}"

case "$MODE" in
    up)
        echo -e "${BLUE}🚀 Starting Spot Optimizer Platform...${NC}"
        echo ""

        # Run database migrations first
        echo -e "${YELLOW}📦 Running database migrations...${NC}"
        docker-compose run --rm backend alembic upgrade head || {
            echo -e "${YELLOW}⚠️  Migrations failed. This is normal on first run if DB is not ready.${NC}"
        }
        echo ""

        # Start all services
        echo -e "${BLUE}🐳 Starting Docker containers...${NC}"
        if [ "$DETACH" = "-d" ]; then
            docker-compose up -d
            echo ""
            echo -e "${GREEN}✅ All services started in detached mode!${NC}"
            echo ""
            echo -e "${BLUE}📊 Service Status:${NC}"
            docker-compose ps
        else
            echo -e "${YELLOW}⚠️  Starting in foreground mode (Ctrl+C to stop)${NC}"
            docker-compose up
        fi

        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}✅ Platform is running!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo ""
        echo -e "${BLUE}📍 Access Points:${NC}"
        echo -e "  Frontend:    http://localhost:3000"
        echo -e "  Backend API: http://localhost:8000"
        echo -e "  API Docs:    http://localhost:8000/docs"
        echo -e "  Postgres:    localhost:5432"
        echo -e "  Redis:       localhost:6379"
        echo ""
        echo -e "${BLUE}🔧 Useful Commands:${NC}"
        echo -e "  View logs:        docker-compose logs -f"
        echo -e "  Stop services:    docker-compose down"
        echo -e "  Restart:          docker-compose restart"
        echo -e "  Shell (backend):  docker-compose exec backend bash"
        echo ""
        ;;

    down)
        echo -e "${YELLOW}🛑 Stopping Spot Optimizer Platform...${NC}"
        docker-compose down
        echo -e "${GREEN}✅ All services stopped${NC}"
        ;;

    restart)
        echo -e "${YELLOW}🔄 Restarting Spot Optimizer Platform...${NC}"
        docker-compose restart
        echo -e "${GREEN}✅ All services restarted${NC}"
        echo ""
        docker-compose ps
        ;;

    logs)
        echo -e "${BLUE}📋 Showing logs (Ctrl+C to exit)...${NC}"
        docker-compose logs -f
        ;;

    build)
        echo -e "${BLUE}🔨 Rebuilding Docker images...${NC}"
        docker-compose build --no-cache
        echo -e "${GREEN}✅ Build complete${NC}"
        ;;

    clean)
        echo -e "${RED}🗑️  Cleaning up (removes containers, volumes, and images)...${NC}"
        echo -e "${YELLOW}⚠️  This will DELETE all data. Are you sure? (y/N)${NC}"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            docker-compose down -v --rmi all
            echo -e "${GREEN}✅ Cleanup complete${NC}"
        else
            echo -e "${YELLOW}Cancelled${NC}"
        fi
        ;;

    migrate)
        echo -e "${BLUE}📦 Running database migrations...${NC}"
        docker-compose run --rm backend alembic upgrade head
        echo -e "${GREEN}✅ Migrations complete${NC}"
        ;;

    shell)
        SERVICE="${2:-backend}"
        echo -e "${BLUE}🐚 Opening shell in $SERVICE container...${NC}"
        docker-compose exec "$SERVICE" bash
        ;;

    test)
        echo -e "${BLUE}🧪 Running tests...${NC}"
        docker-compose run --rm backend pytest
        ;;

    *)
        echo -e "${RED}❌ Unknown command: $MODE${NC}"
        echo ""
        echo -e "${BLUE}Usage:${NC}"
        echo -e "  ./start.sh [command] [options]"
        echo ""
        echo -e "${BLUE}Commands:${NC}"
        echo -e "  up       Start all services (default, -d for detached)"
        echo -e "  down     Stop all services"
        echo -e "  restart  Restart all services"
        echo -e "  logs     Show logs (follows)"
        echo -e "  build    Rebuild Docker images"
        echo -e "  clean    Remove all containers, volumes, and images"
        echo -e "  migrate  Run database migrations"
        echo -e "  shell    Open bash shell in container (default: backend)"
        echo -e "  test     Run test suite"
        echo ""
        echo -e "${BLUE}Examples:${NC}"
        echo -e "  ./start.sh                  # Start in detached mode"
        echo -e "  ./start.sh up -f            # Start in foreground"
        echo -e "  ./start.sh logs             # View logs"
        echo -e "  ./start.sh shell frontend   # Open shell in frontend"
        echo ""
        exit 1
        ;;
esac
