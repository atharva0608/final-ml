#!/bin/bash
# ==============================================================================
# AWS Spot Optimizer - Complete Cleanup Script
# ==============================================================================
# This script removes ALL components installed by setup.sh:
# - Systemd services
# - Docker containers, volumes, networks, images
# - Application directories and files
# - Configuration files
# - Helper scripts
# ==============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# ==============================================================================
# CONFIRMATION
# ==============================================================================

echo ""
echo "======================================================================"
echo "  AWS SPOT OPTIMIZER - COMPLETE CLEANUP"
echo "======================================================================"
echo ""
warn "This script will REMOVE ALL components of the Spot Optimizer:"
echo "  - Systemd services (backend)"
echo "  - Docker containers (MySQL)"
echo "  - Docker volumes (mysql-data)"
echo "  - Docker networks (spot-network)"
echo "  - Docker images (mysql, python, node)"
echo "  - Application directories (/home/ubuntu/spot-optimizer)"
echo "  - Model files (/home/ubuntu/production_models)"
echo "  - Log files (/home/ubuntu/logs)"
echo "  - Helper scripts (/home/ubuntu/scripts)"
echo "  - Nginx configuration"
echo "  - Frontend files (/var/www/spot-optimizer)"
echo ""
echo -e "${RED}WARNING: THIS CANNOT BE UNDONE!${NC}"
echo ""

read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirmation

if [ "$confirmation" != "yes" ]; then
    log "Cleanup cancelled."
    exit 0
fi

echo ""
log "Starting cleanup process..."
echo ""

# ==============================================================================
# STEP 1: STOP AND REMOVE SYSTEMD SERVICES
# ==============================================================================

log "Step 1: Stopping and removing systemd services..."

if systemctl is-active --quiet spot-optimizer-backend; then
    sudo systemctl stop spot-optimizer-backend
    log "✓ Stopped spot-optimizer-backend service"
fi

if systemctl is-enabled --quiet spot-optimizer-backend 2>/dev/null; then
    sudo systemctl disable spot-optimizer-backend
    log "✓ Disabled spot-optimizer-backend service"
fi

if [ -f /etc/systemd/system/spot-optimizer-backend.service ]; then
    sudo rm /etc/systemd/system/spot-optimizer-backend.service
    log "✓ Removed service file"
fi

sudo systemctl daemon-reload
log "✓ Reloaded systemd"

# ==============================================================================
# STEP 2: STOP AND REMOVE NGINX CONFIGURATION
# ==============================================================================

log "Step 2: Removing Nginx configuration..."

if systemctl is-active --quiet nginx; then
    sudo systemctl stop nginx
    log "✓ Stopped Nginx"
fi

if [ -f /etc/nginx/sites-enabled/spot-optimizer ]; then
    sudo rm /etc/nginx/sites-enabled/spot-optimizer
    log "✓ Removed Nginx site (enabled)"
fi

if [ -f /etc/nginx/sites-available/spot-optimizer ]; then
    sudo rm /etc/nginx/sites-available/spot-optimizer
    log "✓ Removed Nginx site (available)"
fi

# Restart Nginx to default config (or stop if you want)
if systemctl is-enabled --quiet nginx 2>/dev/null; then
    sudo systemctl start nginx 2>/dev/null || true
    log "✓ Restarted Nginx with default config"
fi

# ==============================================================================
# STEP 3: STOP AND REMOVE DOCKER CONTAINERS
# ==============================================================================

log "Step 3: Stopping and removing Docker containers..."

# Stop and remove spot-mysql container
if docker ps -a | grep -q spot-mysql; then
    docker stop spot-mysql 2>/dev/null || true
    docker rm spot-mysql 2>/dev/null || true
    log "✓ Removed spot-mysql container"
fi

# Remove any other related containers
RELATED_CONTAINERS=$(docker ps -a | grep -E "spot-optimizer|spot_optimizer" | awk '{print $1}' || echo "")
if [ ! -z "$RELATED_CONTAINERS" ]; then
    docker stop $RELATED_CONTAINERS 2>/dev/null || true
    docker rm $RELATED_CONTAINERS 2>/dev/null || true
    log "✓ Removed related containers"
fi

# ==============================================================================
# STEP 4: REMOVE DOCKER VOLUMES
# ==============================================================================

log "Step 4: Removing Docker volumes..."

# Remove named volumes
if docker volume ls | grep -q mysql-data; then
    docker volume rm mysql-data 2>/dev/null || true
    log "✓ Removed mysql-data volume"
fi

# Remove any other related volumes
RELATED_VOLUMES=$(docker volume ls | grep -E "spot" | awk '{print $2}' || echo "")
if [ ! -z "$RELATED_VOLUMES" ]; then
    docker volume rm $RELATED_VOLUMES 2>/dev/null || true
    log "✓ Removed related volumes"
fi

# ==============================================================================
# STEP 5: REMOVE DOCKER NETWORKS
# ==============================================================================

log "Step 5: Removing Docker networks..."

if docker network ls | grep -q spot-network; then
    docker network rm spot-network 2>/dev/null || true
    log "✓ Removed spot-network"
fi

# ==============================================================================
# STEP 6: REMOVE DOCKER IMAGES (OPTIONAL)
# ==============================================================================

log "Step 6: Removing Docker images..."

read -p "Do you want to remove MySQL Docker image? (y/n): " remove_images

if [ "$remove_images" = "y" ]; then
    # Remove MySQL image
    if docker images | grep -q "mysql.*8.0"; then
        docker rmi mysql:8.0 2>/dev/null || warn "Could not remove mysql:8.0 image (may be in use)"
    fi
    log "✓ Attempted to remove Docker images"
else
    log "Skipped Docker image removal"
fi

# ==============================================================================
# STEP 7: REMOVE APPLICATION DIRECTORIES
# ==============================================================================

log "Step 7: Removing application directories..."

# Remove main application directory
if [ -d "/home/ubuntu/spot-optimizer" ]; then
    sudo rm -rf /home/ubuntu/spot-optimizer
    log "✓ Removed /home/ubuntu/spot-optimizer"
fi

# Remove model files directory
if [ -d "/home/ubuntu/production_models" ]; then
    sudo rm -rf /home/ubuntu/production_models
    log "✓ Removed /home/ubuntu/production_models"
fi

# Remove logs directory
if [ -d "/home/ubuntu/logs" ]; then
    sudo rm -rf /home/ubuntu/logs
    log "✓ Removed /home/ubuntu/logs"
fi

# Remove helper scripts directory
if [ -d "/home/ubuntu/scripts" ]; then
    sudo rm -rf /home/ubuntu/scripts
    log "✓ Removed /home/ubuntu/scripts"
fi

# Remove MySQL data directory (if exists on host)
if [ -d "/home/ubuntu/mysql-data" ]; then
    sudo rm -rf /home/ubuntu/mysql-data
    log "✓ Removed /home/ubuntu/mysql-data"
fi

# ==============================================================================
# STEP 8: REMOVE FRONTEND FILES
# ==============================================================================

log "Step 8: Removing frontend files..."

if [ -d "/var/www/spot-optimizer" ]; then
    sudo rm -rf /var/www/spot-optimizer
    log "✓ Removed /var/www/spot-optimizer"
fi

# ==============================================================================
# STEP 9: CLEAN UP TEMPORARY FILES
# ==============================================================================

log "Step 9: Cleaning up temporary files..."

# Remove any .env files
if [ -f "/home/ubuntu/spot-optimizer/backend/.env" ]; then
    sudo rm /home/ubuntu/spot-optimizer/backend/.env 2>/dev/null || true
fi

# Clean up docker system (optional)
read -p "Do you want to prune Docker system (removes unused data)? (y/n): " prune_docker

if [ "$prune_docker" = "y" ]; then
    docker system prune -af --volumes
    log "✓ Pruned Docker system"
else
    log "Skipped Docker system prune"
fi

# ==============================================================================
# STEP 10: SUMMARY
# ==============================================================================

echo ""
log "======================================================================"
log "  CLEANUP COMPLETE"
log "======================================================================"
echo ""
info "Removed components:"
echo "  ✓ Systemd services"
echo "  ✓ Docker containers"
echo "  ✓ Docker volumes"
echo "  ✓ Docker networks"
echo "  ✓ Application directories"
echo "  ✓ Model files"
echo "  ✓ Log files"
echo "  ✓ Helper scripts"
echo "  ✓ Nginx configuration"
echo "  ✓ Frontend files"
echo ""
log "The system has been cleaned up successfully."
log "You can now run setup.sh again for a fresh installation."
echo ""

# ==============================================================================
# STEP 11: OPTIONAL - REMOVE REPOSITORY
# ==============================================================================

echo ""
read -p "Do you want to remove the repository directory (/home/ubuntu/final-ml)? (y/n): " remove_repo

if [ "$remove_repo" = "y" ]; then
    if [ -d "/home/ubuntu/final-ml" ]; then
        cd /home/ubuntu
        sudo rm -rf /home/ubuntu/final-ml
        log "✓ Removed repository directory"
    fi
fi

echo ""
log "Cleanup script finished!"
echo ""
