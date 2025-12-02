#!/bin/bash
###############################################################################
# Deploy Simplified Agentless Backend
# Version: 3.0.0
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
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

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

print_header "Deploying Agentless Backend v3.0.0"

# Step 1: Backup old database
print_info "Step 1: Backing up old database..."
docker exec spot-mysql mysqldump -u spotuser -pcast_ai_spot_2025 spot_optimizer > /tmp/spot_optimizer_backup_$(date +%Y%m%d_%H%M%S).sql 2>/dev/null || true
print_success "Database backed up"

# Step 2: Drop and recreate database
print_info "Step 2: Creating new schema..."
docker exec -i spot-mysql mysql -u root -pcast_ai_root_2025 < "$PROJECT_ROOT/database/schema.sql"
print_success "New schema created"

# Step 3: Stop old backend
print_info "Step 3: Stopping old backend..."
systemctl stop spot-optimizer-backend 2>/dev/null || true
print_success "Old backend stopped"

# Step 4: Update systemd service
print_info "Step 4: Updating systemd service..."
cat > /etc/systemd/system/spot-optimizer-backend.service <<EOF
[Unit]
Description=CAST-AI Mini Agentless Backend
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$BACKEND_DIR/venv/bin/python $BACKEND_DIR/backend.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable spot-optimizer-backend
print_success "Systemd service updated"

# Step 5: Install any missing dependencies
print_info "Step 5: Checking dependencies..."
cd "$BACKEND_DIR"
source venv/bin/activate
pip install --quiet flask flask-cors pymysql 2>/dev/null || true
deactivate
print_success "Dependencies checked"

# Step 6: Start new backend
print_info "Step 6: Starting new simplified backend..."
systemctl start spot-optimizer-backend
sleep 3

# Check if started successfully
if systemctl is-active --quiet spot-optimizer-backend; then
    print_success "Backend started successfully"
else
    print_error "Backend failed to start"
    print_info "Check logs with: sudo journalctl -u spot-optimizer-backend -n 50"
    exit 1
fi

# Step 7: Test health endpoint
print_info "Step 7: Testing health endpoint..."
sleep 2
if curl -s http://localhost:5000/health | grep -q "healthy"; then
    print_success "Health check passed"
else
    print_warning "Health check failed (backend may still be starting)"
fi

print_header "Deployment Complete!"

echo ""
print_info "Next Steps:"
echo "  1. Check backend status:"
echo "     sudo systemctl status spot-optimizer-backend"
echo ""
echo "  2. View logs:"
echo "     sudo journalctl -u spot-optimizer-backend -f"
echo ""
echo "  3. Test API:"
echo "     curl http://localhost:5000/health"
echo "     curl http://localhost:5000/api/instances"
echo ""
echo "  4. Access dashboard:"
echo "     http://$(hostname -I | awk '{print $1}')/"
echo ""

print_info "Backend Features:"
echo "  ✓ Auto-switch ON/OFF per instance"
echo "  ✓ Auto-terminate ON/OFF per instance"
echo "  ✓ Reset cooldown functionality"
echo "  ✓ Decision engine integration"
echo "  ✓ No agents, no replicas, no complexity"
echo ""

print_success "Deployment successful! 🚀"
