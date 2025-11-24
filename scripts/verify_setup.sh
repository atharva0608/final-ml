#!/bin/bash
# ==============================================================================
# AWS Spot Optimizer - Setup Verification Script
# ==============================================================================
# This script verifies that all components are properly configured and working
# Run this after setup.sh completes or to diagnose issues

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="/home/ubuntu/spot-optimizer/backend"
MODELS_DIR="/home/ubuntu/production_models"
LOGS_DIR="/home/ubuntu/logs"

# Counters
PASSED=0
FAILED=0
WARNINGS=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AWS Spot Optimizer Setup Verification${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to report test results
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    echo -e "  ${YELLOW}Fix:${NC} $2"
    ((FAILED++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    echo -e "  ${YELLOW}Note:${NC} $2"
    ((WARNINGS++))
}

# ==============================================================================
# 1. Docker Checks
# ==============================================================================
echo -e "${BLUE}[1] Docker Configuration${NC}"

# Check if Docker is installed
if command -v docker &> /dev/null; then
    check_pass "Docker is installed: $(docker --version 2>&1 | head -1)"
else
    check_fail "Docker is not installed" "Run: curl -fsSL https://get.docker.com | sh"
fi

# Check if Docker service is running
if systemctl is-active --quiet docker; then
    check_pass "Docker service is running"
else
    check_fail "Docker service is not running" "Run: sudo systemctl start docker"
fi

# Check Docker group membership
if groups ubuntu 2>/dev/null | grep -q docker; then
    check_pass "User 'ubuntu' is in docker group"
else
    check_warn "User 'ubuntu' is not in docker group" "Run: sudo usermod -aG docker ubuntu && newgrp docker"
fi

# Check Docker socket permissions
if [ -S /var/run/docker.sock ]; then
    SOCK_PERMS=$(stat -c %a /var/run/docker.sock)
    if [ "$SOCK_PERMS" = "666" ] || [ "$SOCK_PERMS" = "660" ]; then
        check_pass "Docker socket has correct permissions ($SOCK_PERMS)"
    else
        check_warn "Docker socket permissions may be restrictive ($SOCK_PERMS)" "Run: sudo chmod 666 /var/run/docker.sock"
    fi
else
    check_fail "Docker socket not found" "Check Docker installation"
fi

# Check if MySQL container is running
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q spot-mysql; then
    check_pass "MySQL container is running"

    # Check MySQL connectivity
    if docker exec spot-mysql mysqladmin ping -h localhost --silent 2>/dev/null; then
        check_pass "MySQL is responsive"
    else
        check_warn "MySQL container exists but not responding" "Check: docker logs spot-mysql"
    fi
else
    check_fail "MySQL container is not running" "Run: docker start spot-mysql or re-run setup.sh"
fi

echo ""

# ==============================================================================
# 2. Python Backend Checks
# ==============================================================================
echo -e "${BLUE}[2] Python Backend Configuration${NC}"

# Check if backend directory exists
if [ -d "$BACKEND_DIR" ]; then
    check_pass "Backend directory exists: $BACKEND_DIR"
else
    check_fail "Backend directory not found" "Re-run setup.sh"
fi

# Check if virtual environment exists
if [ -d "$BACKEND_DIR/venv" ]; then
    check_pass "Python virtual environment exists"

    # Check Python version
    PYTHON_VERSION=$("$BACKEND_DIR/venv/bin/python" --version 2>&1)
    check_pass "Python version: $PYTHON_VERSION"
else
    check_fail "Virtual environment not found" "Run: cd $BACKEND_DIR && python3 -m venv venv"
fi

# Check if app.py exists
if [ -f "$BACKEND_DIR/app.py" ]; then
    check_pass "Backend app.py exists"
else
    check_fail "Backend app.py not found" "Check repository clone"
fi

# Check if .env file exists
if [ -f "$BACKEND_DIR/.env" ]; then
    check_pass "Backend .env configuration exists"

    # Verify critical environment variables
    if grep -q "DB_HOST" "$BACKEND_DIR/.env"; then
        check_pass ".env has database configuration"
    else
        check_warn ".env may be incomplete" "Verify database settings"
    fi
else
    check_fail "Backend .env file not found" "Re-run setup.sh or create manually"
fi

# Check if start script exists and is executable
if [ -x "$BACKEND_DIR/start_backend.sh" ]; then
    check_pass "Backend start script is executable"

    # Check if PYTHONPATH is configured in start script
    if grep -q "PYTHONPATH" "$BACKEND_DIR/start_backend.sh"; then
        check_pass "PYTHONPATH is configured in start script"
    else
        check_fail "PYTHONPATH not configured in start script" "Add: export PYTHONPATH=/home/ubuntu/spot-optimizer:\$PYTHONPATH"
    fi
else
    check_fail "Backend start script not found or not executable" "Run: chmod +x $BACKEND_DIR/start_backend.sh"
fi

# Test Python imports (critical check)
echo -n "  Testing Python imports... "
cd "$BACKEND_DIR"
source venv/bin/activate 2>/dev/null
export PYTHONPATH=/home/ubuntu/spot-optimizer:$PYTHONPATH

IMPORT_TEST=$(python -c "
import sys
sys.path.insert(0, '/home/ubuntu/spot-optimizer')
try:
    from backend.config import config
    from backend.database_manager import init_db_pool
    from backend.decision_engine_manager import decision_engine_manager
    print('SUCCESS')
except ImportError as e:
    print(f'FAILED: {e}')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)

if echo "$IMPORT_TEST" | grep -q "SUCCESS"; then
    check_pass "Python imports work correctly"
else
    check_fail "Python imports failed: $IMPORT_TEST" "Check PYTHONPATH and module structure"
fi

deactivate 2>/dev/null || true

# Check required Python packages
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    check_pass "requirements.txt exists"

    # Check if key packages are installed
    source "$BACKEND_DIR/venv/bin/activate" 2>/dev/null
    if python -c "import flask" 2>/dev/null; then
        check_pass "Flask is installed"
    else
        check_fail "Flask not installed" "Run: pip install -r $BACKEND_DIR/requirements.txt"
    fi

    if python -c "import gunicorn" 2>/dev/null; then
        check_pass "Gunicorn is installed"
    else
        check_fail "Gunicorn not installed" "Run: pip install -r $BACKEND_DIR/requirements.txt"
    fi
    deactivate 2>/dev/null || true
else
    check_fail "requirements.txt not found" "Check repository"
fi

echo ""

# ==============================================================================
# 3. Systemd Service Checks
# ==============================================================================
echo -e "${BLUE}[3] Systemd Service Configuration${NC}"

# Check if service file exists
if [ -f /etc/systemd/system/spot-optimizer-backend.service ]; then
    check_pass "Systemd service file exists"

    # Check if PYTHONPATH is in service file
    if grep -q "PYTHONPATH" /etc/systemd/system/spot-optimizer-backend.service; then
        check_pass "PYTHONPATH configured in systemd service"
    else
        check_fail "PYTHONPATH not in systemd service" "Add: Environment=PYTHONPATH=/home/ubuntu/spot-optimizer"
    fi
else
    check_fail "Systemd service file not found" "Re-run setup.sh"
fi

# Check if service is enabled
if systemctl is-enabled spot-optimizer-backend &>/dev/null; then
    check_pass "Backend service is enabled"
else
    check_warn "Backend service not enabled" "Run: sudo systemctl enable spot-optimizer-backend"
fi

# Check if service is running
if systemctl is-active spot-optimizer-backend &>/dev/null; then
    check_pass "Backend service is running"

    # Check if API responds
    sleep 2
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        check_pass "Backend API is responding on port 5000"
    else
        check_warn "Backend running but not responding" "Check: sudo journalctl -u spot-optimizer-backend -n 50"
    fi
else
    check_fail "Backend service is not running" "Run: sudo systemctl start spot-optimizer-backend"
    check_warn "Check service logs" "Run: sudo journalctl -u spot-optimizer-backend -n 50"
fi

echo ""

# ==============================================================================
# 4. Nginx Checks
# ==============================================================================
echo -e "${BLUE}[4] Nginx Configuration${NC}"

# Check if Nginx is installed
if command -v nginx &> /dev/null; then
    check_pass "Nginx is installed"
else
    check_fail "Nginx is not installed" "Run: sudo apt install nginx"
fi

# Check if Nginx is running
if systemctl is-active nginx &>/dev/null; then
    check_pass "Nginx service is running"
else
    check_fail "Nginx service is not running" "Run: sudo systemctl start nginx"
fi

# Check if config file exists
if [ -f /etc/nginx/sites-available/spot-optimizer ]; then
    check_pass "Nginx configuration file exists"

    # Test config syntax
    if sudo nginx -t &>/dev/null; then
        check_pass "Nginx configuration syntax is valid"
    else
        check_fail "Nginx configuration has errors" "Run: sudo nginx -t"
    fi
else
    check_fail "Nginx config not found" "Re-run setup.sh"
fi

# Check if site is enabled
if [ -L /etc/nginx/sites-enabled/spot-optimizer ]; then
    check_pass "Site is enabled in Nginx"
else
    check_warn "Site not enabled" "Run: sudo ln -sf /etc/nginx/sites-available/spot-optimizer /etc/nginx/sites-enabled/"
fi

# Check frontend build directory
if [ -d /var/www/spot-optimizer ]; then
    FILE_COUNT=$(find /var/www/spot-optimizer -type f | wc -l)
    if [ "$FILE_COUNT" -gt 0 ]; then
        check_pass "Frontend files are deployed ($FILE_COUNT files)"
    else
        check_fail "Frontend directory is empty" "Re-build frontend"
    fi
else
    check_fail "Frontend directory not found" "Re-run setup.sh"
fi

echo ""

# ==============================================================================
# 5. Directory Permissions
# ==============================================================================
echo -e "${BLUE}[5] Directory Permissions${NC}"

# Check backend directory ownership
BACKEND_OWNER=$(stat -c '%U:%G' "$BACKEND_DIR" 2>/dev/null || echo "unknown")
if [ "$BACKEND_OWNER" = "ubuntu:ubuntu" ]; then
    check_pass "Backend directory has correct ownership"
else
    check_warn "Backend directory ownership: $BACKEND_OWNER" "Run: sudo chown -R ubuntu:ubuntu $BACKEND_DIR"
fi

# Check models directory
if [ -d "$MODELS_DIR" ]; then
    check_pass "Models directory exists"
    MODELS_OWNER=$(stat -c '%U:%G' "$MODELS_DIR")
    if [ "$MODELS_OWNER" = "ubuntu:ubuntu" ]; then
        check_pass "Models directory has correct ownership"
    else
        check_warn "Models directory ownership: $MODELS_OWNER" "Run: sudo chown -R ubuntu:ubuntu $MODELS_DIR"
    fi
else
    check_warn "Models directory not found" "Will be created on first model upload"
fi

# Check logs directory
if [ -d "$LOGS_DIR" ]; then
    check_pass "Logs directory exists"
    LOGS_OWNER=$(stat -c '%U:%G' "$LOGS_DIR")
    if [ "$LOGS_OWNER" = "ubuntu:ubuntu" ]; then
        check_pass "Logs directory has correct ownership"
    else
        check_warn "Logs directory ownership: $LOGS_OWNER" "Run: sudo chown -R ubuntu:ubuntu $LOGS_DIR"
    fi
else
    check_fail "Logs directory not found" "Run: mkdir -p $LOGS_DIR && chown ubuntu:ubuntu $LOGS_DIR"
fi

echo ""

# ==============================================================================
# 6. Network & Connectivity
# ==============================================================================
echo -e "${BLUE}[6] Network & Connectivity${NC}"

# Check if port 5000 is listening
if netstat -tuln 2>/dev/null | grep -q ":5000 " || ss -tuln 2>/dev/null | grep -q ":5000 "; then
    check_pass "Backend is listening on port 5000"
else
    check_warn "Port 5000 is not listening" "Backend may not be running"
fi

# Check if port 80 is listening (Nginx)
if netstat -tuln 2>/dev/null | grep -q ":80 " || ss -tuln 2>/dev/null | grep -q ":80 "; then
    check_pass "Nginx is listening on port 80"
else
    check_fail "Port 80 is not listening" "Check Nginx status"
fi

# Check database connectivity from backend
if [ -f "$BACKEND_DIR/.env" ]; then
    DB_HOST=$(grep DB_HOST "$BACKEND_DIR/.env" | cut -d'=' -f2)
    DB_PORT=$(grep DB_PORT "$BACKEND_DIR/.env" | cut -d'=' -f2)

    if timeout 2 bash -c "echo > /dev/tcp/$DB_HOST/$DB_PORT" 2>/dev/null; then
        check_pass "Database is reachable from backend"
    else
        check_warn "Cannot reach database at $DB_HOST:$DB_PORT" "Check MySQL container"
    fi
fi

echo ""

# ==============================================================================
# Summary
# ==============================================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Verification Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Passed:${NC}   $PASSED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "${RED}Failed:${NC}   $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed! System is ready.${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠ System is functional but has warnings.${NC}"
        echo -e "${YELLOW}  Review warnings above for optimal operation.${NC}"
        exit 0
    fi
else
    echo -e "${RED}✗ System has $FAILED critical issue(s).${NC}"
    echo -e "${RED}  Please address the failed checks above.${NC}"
    exit 1
fi
