#!/bin/bash
# Spot Optimizer - Deployment Script
# This script handles automated deployment of the application

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/opt/spot-optimizer"
DOCKER_COMPOSE_FILE="docker/docker-compose.yml"
BACKUP_DIR="/var/backups/spot-optimizer"
LOG_DIR="/var/log/spot-optimizer"
MAX_HEALTH_CHECK_ATTEMPTS=30
HEALTH_CHECK_INTERVAL=5

# Function to print colored messages
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command_exists docker; then
        log_error "Docker is not installed. Please run setup.sh first."
        exit 1
    fi

    if ! command_exists docker-compose; then
        log_error "docker-compose is not installed. Please run setup.sh first."
        exit 1
    fi

    if ! command_exists git; then
        log_error "Git is not installed."
        exit 1
    fi

    log_success "All prerequisites are installed"
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."

    mkdir -p "$BACKUP_DIR"
    mkdir -p "$LOG_DIR"
    mkdir -p "$PROJECT_DIR/data/postgres"
    mkdir -p "$PROJECT_DIR/data/redis"

    log_success "Directories created"
}

# Pull latest code from repository
pull_code() {
    log_info "Pulling latest code from repository..."

    cd "$PROJECT_DIR"

    # Stash any local changes
    if [[ -n $(git status -s) ]]; then
        log_warning "Local changes detected, stashing..."
        git stash
    fi

    # Pull latest code
    git pull origin main || {
        log_error "Failed to pull latest code"
        exit 1
    }

    log_success "Code updated successfully"
}

# Backup database
backup_database() {
    log_info "Creating database backup..."

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

    # Create backup using pg_dump inside container
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgres pg_dump -U spotoptimizer spotoptimizer > "$BACKUP_FILE" 2>/dev/null || {
        log_warning "Database backup failed (database might not be running)"
        return 0
    }

    # Compress backup
    gzip "$BACKUP_FILE"

    # Keep only last 7 backups
    find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -type f -mtime +7 -delete

    log_success "Database backup created: ${BACKUP_FILE}.gz"
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."

    cd "$PROJECT_DIR"

    # Build all images
    docker-compose -f "$DOCKER_COMPOSE_FILE" build || {
        log_error "Failed to build Docker images"
        exit 1
    }

    log_success "Docker images built successfully"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."

    cd "$PROJECT_DIR"

    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d postgres
    sleep 10

    # Run Alembic migrations
    docker-compose -f "$DOCKER_COMPOSE_FILE" run --rm backend alembic upgrade head || {
        log_error "Database migration failed"
        exit 1
    }

    log_success "Database migrations completed"
}

# Start services
start_services() {
    log_info "Starting services with docker-compose..."

    cd "$PROJECT_DIR"

    # Start all services
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d || {
        log_error "Failed to start services"
        exit 1
    }

    log_success "Services started"
}

# Health check verification
health_check() {
    log_info "Performing health checks..."

    local backend_url="http://localhost:8000/health"
    local frontend_url="http://localhost:3000"
    local attempt=0

    # Wait for backend to be healthy
    log_info "Checking backend health..."
    while [ $attempt -lt $MAX_HEALTH_CHECK_ATTEMPTS ]; do
        if curl -f -s "$backend_url" > /dev/null 2>&1; then
            log_success "Backend is healthy"
            break
        fi

        attempt=$((attempt + 1))
        if [ $attempt -ge $MAX_HEALTH_CHECK_ATTEMPTS ]; then
            log_error "Backend health check failed after $MAX_HEALTH_CHECK_ATTEMPTS attempts"
            log_error "Check logs: docker-compose -f $DOCKER_COMPOSE_FILE logs backend"
            exit 1
        fi

        log_info "Waiting for backend to be ready... (attempt $attempt/$MAX_HEALTH_CHECK_ATTEMPTS)"
        sleep $HEALTH_CHECK_INTERVAL
    done

    # Check frontend
    log_info "Checking frontend health..."
    attempt=0
    while [ $attempt -lt $MAX_HEALTH_CHECK_ATTEMPTS ]; do
        if curl -f -s "$frontend_url" > /dev/null 2>&1; then
            log_success "Frontend is healthy"
            break
        fi

        attempt=$((attempt + 1))
        if [ $attempt -ge $MAX_HEALTH_CHECK_ATTEMPTS ]; then
            log_warning "Frontend health check failed (might still be building)"
            break
        fi

        log_info "Waiting for frontend to be ready... (attempt $attempt/$MAX_HEALTH_CHECK_ATTEMPTS)"
        sleep $HEALTH_CHECK_INTERVAL
    done

    # Check database
    log_info "Checking database connection..."
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgres pg_isready -U spotoptimizer > /dev/null 2>&1; then
        log_success "Database is healthy"
    else
        log_error "Database health check failed"
        exit 1
    fi

    # Check Redis
    log_info "Checking Redis connection..."
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis is healthy"
    else
        log_error "Redis health check failed"
        exit 1
    fi

    log_success "All health checks passed"
}

# Show service status
show_status() {
    log_info "Service status:"
    echo ""
    docker-compose -f "$DOCKER_COMPOSE_FILE" ps
    echo ""
    log_info "View logs with: docker-compose -f $DOCKER_COMPOSE_FILE logs -f [service]"
    log_info "Available services: backend, frontend, postgres, redis, celery-worker, celery-beat"
}

# Cleanup old Docker images
cleanup() {
    log_info "Cleaning up old Docker images..."

    # Remove dangling images
    docker image prune -f > /dev/null 2>&1 || true

    log_success "Cleanup completed"
}

# Main deployment function
main() {
    log_info "========================================="
    log_info "  Spot Optimizer Deployment Script"
    log_info "========================================="
    echo ""

    # Check prerequisites
    check_prerequisites

    # Create directories
    create_directories

    # Pull latest code
    pull_code

    # Backup database
    backup_database

    # Build images
    build_images

    # Run migrations
    run_migrations

    # Start services
    start_services

    # Health checks
    health_check

    # Show status
    show_status

    # Cleanup
    cleanup

    echo ""
    log_success "========================================="
    log_success "  Deployment completed successfully!"
    log_success "========================================="
    echo ""
    log_info "Backend:  http://localhost:8000"
    log_info "Frontend: http://localhost:3000"
    log_info "API Docs: http://localhost:8000/docs"
    echo ""
}

# Run main function
main "$@"
