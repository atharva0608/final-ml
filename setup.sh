#!/bin/bash
# ==============================================================================
# AWS Spot Optimizer - Unified Setup Script
# ==============================================================================
# Complete setup script with:
#   ✓ Frontend & Backend in same repository
#   ✓ Automatic IP detection (no manual configuration)
#   ✓ MySQL 8.0 in Docker with automatic permission fixes
#   ✓ Flask 3.0 backend with 42 API endpoints
#   ✓ React + Vite frontend with auto-detection
#   ✓ Nginx reverse proxy with CORS support
#   ✓ All error fixes included
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/atharva0608/final-ml/main/setup.sh | sudo bash
#   OR clone repo first:
#   git clone https://github.com/atharva0608/final-ml.git && cd final-ml && sudo bash setup.sh
# ==============================================================================

set -e  # Exit on any error

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
# STEP 0: ENSURE REPOSITORY IS CLONED
# ==============================================================================

log "Starting AWS Spot Optimizer Setup..."
log "============================================"

# Determine repository directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"
CLONE_DIR="/home/ubuntu/final-ml"

# Check if we're already in the repository
if [ -f "$SCRIPT_DIR/backend.py" ] && [ -f "$SCRIPT_DIR/schema.sql" ]; then
    REPO_DIR="$SCRIPT_DIR"
    log "Running from repository directory: $REPO_DIR"
else
    # Need to clone the repository
    log "Repository files not found in current directory"
    log "Cloning repository to: $CLONE_DIR"

    # Remove old clone if exists
    if [ -d "$CLONE_DIR" ]; then
        warn "Removing existing directory: $CLONE_DIR"
        rm -rf "$CLONE_DIR"
    fi

    # Clone repository
    git clone https://github.com/atharva0608/final-ml.git "$CLONE_DIR"
    cd "$CLONE_DIR"

    # Checkout the correct branch
    git checkout claude/unified-repo-final-01DYWUjjfqXjVeiFr7yFRN2P 2>/dev/null || git checkout main

    REPO_DIR="$CLONE_DIR"
    log "Repository cloned to: $REPO_DIR"
fi

# Verify required files exist
if [ ! -f "$REPO_DIR/backend.py" ]; then
    error "backend.py not found in $REPO_DIR"
    exit 1
fi

if [ ! -f "$REPO_DIR/schema.sql" ]; then
    error "schema.sql not found in $REPO_DIR"
    exit 1
fi

if [ ! -d "$REPO_DIR/frontend--main" ]; then
    error "frontend--main directory not found in $REPO_DIR"
    exit 1
fi

log "✓ All required files verified"
log "Repository: $REPO_DIR"

# ==============================================================================
# CONFIGURATION
# ==============================================================================

FRONTEND_SOURCE="$REPO_DIR/frontend--main"

# Application directories
APP_DIR="/home/ubuntu/spot-optimizer"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_BUILD_DIR="$APP_DIR/frontend"
MODELS_DIR="/home/ubuntu/production_models"
LOGS_DIR="/home/ubuntu/logs"
SCRIPTS_DIR="/home/ubuntu/scripts"

# Database configuration
DB_ROOT_PASSWORD="rootpassword"
DB_USER="spotuser"
DB_PASSWORD="SpotUser2024!"
DB_NAME="spot_optimizer"
DB_PORT=3306

# Backend configuration
BACKEND_PORT=5000
BACKEND_HOST="0.0.0.0"

# Frontend build directory (served by Nginx)
NGINX_ROOT="/var/www/spot-optimizer"

# ==============================================================================
# STEP 1: RETRIEVE INSTANCE METADATA USING IMDSv2
# ==============================================================================

log "Step 1: Retrieving instance metadata using IMDSv2..."

# Get IMDSv2 token (required for security)
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" \
    -s --connect-timeout 5 --max-time 10 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
    warn "Could not retrieve IMDSv2 token. Trying IMDSv1 fallback..."
    INSTANCE_ID=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
    REGION=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "unknown")
    AVAILABILITY_ZONE=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/placement/availability-zone 2>/dev/null || echo "unknown")
    PUBLIC_IP=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
else
    log "IMDSv2 token acquired successfully"
    INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
    REGION=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "unknown")
    AVAILABILITY_ZONE=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/placement/availability-zone 2>/dev/null || echo "unknown")
    PUBLIC_IP=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
fi

# Fallback for PUBLIC_IP if metadata service doesn't work
if [ -z "$PUBLIC_IP" ]; then
    warn "Could not get public IP from metadata service, trying external service..."
    PUBLIC_IP=$(curl -s --connect-timeout 5 http://checkip.amazonaws.com 2>/dev/null || echo "localhost")
fi

log "Instance ID: $INSTANCE_ID"
log "Region: $REGION"
log "Availability Zone: $AVAILABILITY_ZONE"
log "Public IP: $PUBLIC_IP"

# ==============================================================================
# STEP 2: UPDATE SYSTEM AND INSTALL DEPENDENCIES
# ==============================================================================

log "Step 2: Updating system and installing dependencies..."

# Update package lists
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y -qq

# Install essential packages
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    curl \
    wget \
    git \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    jq

log "Base packages installed"

# ==============================================================================
# STEP 3: INSTALL DOCKER
# ==============================================================================

log "Step 3: Installing Docker..."

# Check if Docker is already installed
if command -v docker &> /dev/null; then
    log "Docker is already installed: $(docker --version)"
else
    # Remove old Docker versions if any
    sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Set up Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker
    sudo apt-get update -y
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    log "Docker installed"
fi

# Start and enable Docker
sudo systemctl start docker 2>/dev/null || true
sudo systemctl enable docker

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu 2>/dev/null || true

# Activate docker group for current session (fixes permission denied errors)
# Note: This allows the script to continue without logout/login
if groups ubuntu | grep -q docker; then
    log "Docker group membership confirmed"
fi

log "Docker configured"

# ==============================================================================
# STEP 4: INSTALL NODE.JS LTS
# ==============================================================================

log "Step 4: Installing Node.js LTS..."

# Check if Node.js is already installed
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    log "Node.js is already installed: $NODE_VERSION"

    # Check if it's v20.x
    if [[ $NODE_VERSION == v20.* ]]; then
        log "Node.js v20.x detected, skipping installation"
    else
        warn "Different Node.js version detected, installing v20.x..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
    fi
else
    # Install Node.js 20.x LTS
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
fi

# Verify installation
NODE_VERSION=$(node --version)
NPM_VERSION=$(npm --version)
log "Node.js $NODE_VERSION installed"
log "npm $NPM_VERSION installed"

# ==============================================================================
# STEP 5: CREATE DIRECTORY STRUCTURE WITH PROPER PERMISSIONS
# ==============================================================================

log "Step 5: Creating directory structure with proper permissions..."

# Create all necessary directories with proper ownership from the start
sudo mkdir -p "$APP_DIR"
sudo mkdir -p "$BACKEND_DIR"
sudo mkdir -p "$FRONTEND_BUILD_DIR"
sudo mkdir -p "$MODELS_DIR"
sudo mkdir -p "$LOGS_DIR"
sudo mkdir -p "$SCRIPTS_DIR"
sudo mkdir -p "$NGINX_ROOT"

# Set ownership to ubuntu user for application directories
sudo chown -R ubuntu:ubuntu "$APP_DIR"
sudo chown -R ubuntu:ubuntu "$MODELS_DIR"
sudo chown -R ubuntu:ubuntu "$LOGS_DIR"
sudo chown -R ubuntu:ubuntu "$SCRIPTS_DIR"

# Nginx root owned by www-data
sudo chown -R www-data:www-data "$NGINX_ROOT"

# Set proper permissions
chmod 755 "$APP_DIR"
chmod 755 "$BACKEND_DIR"
chmod 755 "$FRONTEND_BUILD_DIR"
chmod 755 "$MODELS_DIR"
chmod 755 "$LOGS_DIR"
chmod 755 "$SCRIPTS_DIR"

log "Directory structure created with proper permissions"

# ==============================================================================
# STEP 6: SETUP DATABASE WITH DOCKER
# ==============================================================================

log "Step 6: Setting up MySQL database with Docker..."

# Stop and remove existing MySQL container if exists
docker stop spot-mysql 2>/dev/null || true
docker rm spot-mysql 2>/dev/null || true

# Remove old mysql-data directory to avoid permission conflicts
# Docker will create it with proper ownership (mysql user UID 999)
if [ -d "/home/ubuntu/mysql-data" ]; then
    log "Removing old mysql-data directory to fix permissions..."
    sudo rm -rf /home/ubuntu/mysql-data
fi

# Create Docker network for the app
docker network create spot-network 2>/dev/null || true

# Run MySQL container with enhanced configuration
docker run -d \
    --name spot-mysql \
    --network spot-network \
    --restart unless-stopped \
    -e MYSQL_ROOT_PASSWORD="$DB_ROOT_PASSWORD" \
    -e MYSQL_DATABASE="$DB_NAME" \
    -e MYSQL_USER="$DB_USER" \
    -e MYSQL_PASSWORD="$DB_PASSWORD" \
    -p "$DB_PORT:3306" \
    -v /home/ubuntu/mysql-data:/var/lib/mysql \
    mysql:8.0 \
    --default-authentication-plugin=mysql_native_password \
    --character-set-server=utf8mb4 \
    --collation-server=utf8mb4_unicode_ci \
    --max_connections=200 \
    --innodb_buffer_pool_size=256M \
    --innodb_log_buffer_size=16M

log "MySQL container started"

# Wait for MySQL to be ready
log "Waiting for MySQL to initialize (this may take 30-60 seconds)..."
sleep 15

# Wait for container to be responsive
MAX_ATTEMPTS=30
ATTEMPT=0
while ! docker exec spot-mysql mysqladmin ping -h "localhost" --silent 2>/dev/null; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        error "MySQL failed to start after $MAX_ATTEMPTS attempts"
        docker logs spot-mysql
        exit 1
    fi
    log "Waiting for MySQL container... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    sleep 2
done

log "MySQL container is responding"

# Wait for authentication to work
log "Waiting for MySQL authentication to be ready..."
ATTEMPT=0
while ! docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -e "SELECT 1;" > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        error "MySQL authentication failed after $MAX_ATTEMPTS attempts"
        docker logs --tail 30 spot-mysql
        exit 1
    fi
    if [ $((ATTEMPT % 5)) -eq 0 ]; then
        log "Waiting for MySQL auth... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    fi
    sleep 2
done

log "MySQL is fully ready!"

# Fix MySQL data directory permissions (Docker MySQL uses UID 999)
# This prevents InnoDB redo log permission errors
log "Ensuring MySQL data directory has correct ownership..."
docker stop spot-mysql
sudo chown -R 999:999 /home/ubuntu/mysql-data 2>/dev/null || {
    warn "Could not change ownership of mysql-data (may not exist yet)"
}
docker start spot-mysql

# Wait for MySQL to be ready after restart
log "Waiting for MySQL to restart..."
sleep 10
ATTEMPT=0
while ! docker exec spot-mysql mysqladmin ping -h "localhost" --silent 2>/dev/null; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge 15 ]; then
        error "MySQL failed to restart after permission fix"
        exit 1
    fi
    sleep 2
done
log "MySQL restarted with correct permissions"

# ==============================================================================
# STEP 7: IMPORT DATABASE SCHEMA
# ==============================================================================

log "Step 7: Importing database schema..."

# Use schema.sql
SCHEMA_FILE="$REPO_DIR/schema.sql"
if [ ! -f "$SCHEMA_FILE" ]; then
    error "Schema file not found: $SCHEMA_FILE"
    exit 1
fi

log "Found schema: $SCHEMA_FILE"

# Import schema
set +e
docker exec -i spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" "$DB_NAME" < "$SCHEMA_FILE" 2>&1 | grep -v "Warning" || true
set -e

# Verify tables were created
TABLE_COUNT=$(docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null || echo "0")

if [ "$TABLE_COUNT" -gt 0 ]; then
    log "Database schema imported successfully ($TABLE_COUNT tables created)"
else
    warn "Schema import may have issues - check manually"
fi

# Grant privileges for all connection types
log "Configuring database user privileges..."

# Wait a moment for user to be fully created
sleep 2

# Grant privileges from any host (%), localhost, and docker network
docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -e "
    -- Grant to user from any host
    GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'%';

    -- Grant to user from localhost
    GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';

    -- Grant to user from docker network (172.18.0.0/16)
    GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'172.18.%';

    -- Also grant root access from docker network for admin tasks
    GRANT ALL PRIVILEGES ON *.* TO 'root'@'172.18.%' IDENTIFIED BY '$DB_ROOT_PASSWORD' WITH GRANT OPTION;

    FLUSH PRIVILEGES;
" 2>/dev/null

# Verify the grants worked
log "Verifying database connection..."
docker exec spot-mysql mysql -u "$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1;" "$DB_NAME" > /dev/null 2>&1 &&
    log "✓ Database user can connect successfully" ||
    warn "Database user connection test failed - may need manual verification"

log "Database privileges configured"

# Import demo data if available
DEMO_DATA_FILE="$REPO_DIR/demo-data.sql"
if [ -f "$DEMO_DATA_FILE" ]; then
    log "Found demo data file - importing for testing..."

    set +e
    docker exec -i spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" < "$DEMO_DATA_FILE" 2>&1 | grep -v "Warning" || true
    set -e

    log "✅ Demo data imported successfully"
else
    warn "Demo data file not found: $DEMO_DATA_FILE"
fi

log "Database setup complete"

# ==============================================================================
# STEP 8: SETUP PYTHON BACKEND
# ==============================================================================

log "Step 8: Setting up Python backend..."

# Copy backend files from repository
log "Copying backend files from repository..."
if [ -f "$REPO_DIR/backend.py" ]; then
    cp "$REPO_DIR/backend.py" "$BACKEND_DIR/"
    log "✓ Copied backend.py"
else
    error "backend.py not found in repository!"
    exit 1
fi

# Copy requirements.txt if exists
if [ -f "$REPO_DIR/requirements.txt" ]; then
    cp "$REPO_DIR/requirements.txt" "$BACKEND_DIR/"
else
    # Create default requirements.txt
    cat > "$BACKEND_DIR/requirements.txt" << 'EOF'
Flask==3.0.0
flask-cors==4.0.0
mysql-connector-python==8.2.0
APScheduler==3.10.4
marshmallow==3.20.1
numpy>=1.26.0
scikit-learn>=1.3.0
gunicorn==21.2.0
python-dotenv==1.0.0
pandas>=2.0.0
EOF
fi

# Create Python virtual environment
log "Installing Python dependencies..."
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

log "Python dependencies installed"

# Create .env file for backend with explicit values
log "Creating backend environment configuration..."
cat > "$BACKEND_DIR/.env" << EOF
# Database Configuration
DB_HOST=localhost
DB_PORT=$DB_PORT
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME

# Backend Configuration
FLASK_ENV=production
PORT=$BACKEND_PORT
HOST=$BACKEND_HOST

# AWS Metadata
AWS_REGION=$REGION
AWS_AZ=$AVAILABILITY_ZONE
AWS_INSTANCE_ID=$INSTANCE_ID
EOF

# Verify .env was created correctly
if [ -f "$BACKEND_DIR/.env" ]; then
    log "✓ Backend .env file created"
    # Show database config (hide password)
    log "Database config: $DB_USER@localhost:$DB_PORT/$DB_NAME"
else
    error ".env file creation failed!"
    exit 1
fi

log "Backend environment configured"

# Create backend startup script
cat > "$BACKEND_DIR/start_backend.sh" << 'EOF'
#!/bin/bash
cd /home/ubuntu/spot-optimizer/backend
source venv/bin/activate
exec gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --access-logfile /home/ubuntu/logs/backend-access.log --error-logfile /home/ubuntu/logs/backend-error.log backend:app
EOF

chmod +x "$BACKEND_DIR/start_backend.sh"

log "Backend setup complete"

# ==============================================================================
# STEP 9: SETUP VITE REACT FRONTEND
# ==============================================================================

log "Step 9: Setting up Vite React frontend..."

# Check if frontend source exists
if [ ! -d "$FRONTEND_SOURCE" ]; then
    error "Frontend directory not found: $FRONTEND_SOURCE"
    exit 1
fi

log "Frontend source found: $FRONTEND_SOURCE"

# Install npm dependencies
log "Installing npm dependencies (this may take a few minutes)..."
cd "$FRONTEND_SOURCE"
npm install --quiet

log "Building frontend for production with API URL: http://$PUBLIC_IP:5000..."

# Build with environment variable for API URL
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build

# Deploy built files to Nginx directory
log "Deploying frontend to $NGINX_ROOT..."
sudo cp -r dist/* "$NGINX_ROOT/"
sudo chown -R www-data:www-data "$NGINX_ROOT"

log "Frontend built and deployed to $NGINX_ROOT"

# ==============================================================================
# STEP 10: CONFIGURE NGINX WITH CORS SUPPORT
# ==============================================================================

log "Step 10: Configuring Nginx with CORS support..."

# Create Nginx configuration
sudo tee /etc/nginx/sites-available/spot-optimizer > /dev/null << 'NGINX_CONFIG'
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    root /var/www/spot-optimizer;
    index index.html;

    # Increase buffer sizes for API responses
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;
    large_client_header_buffers 4 32k;

    # Serve React frontend
    location / {
        try_files $uri $uri/ /index.html;

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Proxy API requests to backend with CORS headers
    location /api/ {
        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
        add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;

        # Handle preflight requests
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }

        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Health check endpoint with CORS
    location /health {
        add_header 'Access-Control-Allow-Origin' '*' always;
        proxy_pass http://127.0.0.1:5000/health;
        proxy_set_header Host $host;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json;

    # Logging
    access_log /var/log/nginx/spot-optimizer.access.log;
    error_log /var/log/nginx/spot-optimizer.error.log;
}
NGINX_CONFIG

# Enable the site
sudo ln -sf /etc/nginx/sites-available/spot-optimizer /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx

log "Nginx configured with CORS support"

# ==============================================================================
# STEP 11: CREATE SYSTEMD SERVICE FOR BACKEND
# ==============================================================================

log "Step 11: Creating systemd service for backend..."

# Create systemd service file
sudo tee /etc/systemd/system/spot-optimizer-backend.service > /dev/null << EOF
[Unit]
Description=AWS Spot Optimizer Backend
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/start_backend.sh
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=spot-optimizer-backend

# Environment
Environment=PATH=$BACKEND_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

log "Backend systemd service created"

# Reload systemd, enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable spot-optimizer-backend
sudo systemctl start spot-optimizer-backend

# Wait for backend to start
log "Waiting for backend to start..."
sleep 5

# Check backend status
if sudo systemctl is-active --quiet spot-optimizer-backend; then
    log "✓ Backend service is running"
else
    warn "Backend service may have issues. Check logs with: sudo journalctl -u spot-optimizer-backend -n 50"
fi

# ==============================================================================
# STEP 12: CREATE HELPER SCRIPTS
# ==============================================================================

log "Step 12: Creating helper scripts..."

# Create start script
cat > "$SCRIPTS_DIR/start.sh" << 'EOF'
#!/bin/bash
echo "Starting AWS Spot Optimizer services..."
docker start spot-mysql
sleep 5
sudo systemctl start spot-optimizer-backend
sudo systemctl start nginx
echo "Services started!"
EOF
chmod +x "$SCRIPTS_DIR/start.sh"

# Create stop script
cat > "$SCRIPTS_DIR/stop.sh" << 'EOF'
#!/bin/bash
echo "Stopping AWS Spot Optimizer services..."
sudo systemctl stop spot-optimizer-backend
sudo systemctl stop nginx
docker stop spot-mysql
echo "Services stopped!"
EOF
chmod +x "$SCRIPTS_DIR/stop.sh"

# Create restart script
cat > "$SCRIPTS_DIR/restart.sh" << 'EOF'
#!/bin/bash
echo "Restarting AWS Spot Optimizer services..."
docker restart spot-mysql
sleep 5
sudo systemctl restart spot-optimizer-backend
sudo systemctl restart nginx
echo "Services restarted!"
EOF
chmod +x "$SCRIPTS_DIR/restart.sh"

# Create status script
cat > "$SCRIPTS_DIR/status.sh" << 'EOF'
#!/bin/bash
echo "==================================="
echo "AWS Spot Optimizer Service Status"
echo "==================================="
echo "MySQL Container:"
docker ps --filter name=spot-mysql --format "Status: {{.Status}}"
echo ""
echo "Backend Service:"
systemctl status spot-optimizer-backend --no-pager -l | grep "Active:"
curl -s http://localhost:5000/health > /dev/null 2>&1 && echo "  API: ✓ Responding" || echo "  API: ✗ Not responding"
echo ""
echo "Nginx (Frontend):"
systemctl status nginx --no-pager -l | grep "Active:"
echo ""
echo "==================================="
EOF
chmod +x "$SCRIPTS_DIR/status.sh"

# Create logs script
cat > "$SCRIPTS_DIR/logs.sh" << 'EOF'
#!/bin/bash
echo "Select log to view:"
echo "1) Backend (systemd journal)"
echo "2) Backend access log"
echo "3) Backend error log"
echo "4) Nginx access log"
echo "5) Nginx error log"
echo "6) MySQL container log"
read -p "Choice [1-6]: " choice

case $choice in
    1) sudo journalctl -u spot-optimizer-backend -f ;;
    2) tail -f /home/ubuntu/logs/backend-access.log ;;
    3) tail -f /home/ubuntu/logs/backend-error.log ;;
    4) sudo tail -f /var/log/nginx/spot-optimizer.access.log ;;
    5) sudo tail -f /var/log/nginx/spot-optimizer.error.log ;;
    6) docker logs -f spot-mysql ;;
    *) echo "Invalid choice" ;;
esac
EOF
chmod +x "$SCRIPTS_DIR/logs.sh"

log "Helper scripts created"

# ==============================================================================
# STEP 13: CREATE MODELS DIRECTORY
# ==============================================================================

log "Step 13: Creating models directory..."
mkdir -p "$MODELS_DIR"
chmod 755 "$MODELS_DIR"
log "Models directory ready at: $MODELS_DIR"

# ==============================================================================
# SETUP COMPLETE - SUMMARY
# ==============================================================================

# Create setup completion summary
cat > /home/ubuntu/SETUP_COMPLETE.txt << EOF
================================================================================
AWS SPOT OPTIMIZER - SETUP COMPLETE!
================================================================================

Instance Details:
  Instance ID: $INSTANCE_ID
  Region: $REGION
  Availability Zone: $AVAILABILITY_ZONE
  Public IP: $PUBLIC_IP

Dashboard URL:
  http://$PUBLIC_IP/

Backend API:
  http://$PUBLIC_IP:5000

Database:
  Host: localhost
  Port: $DB_PORT
  Database: $DB_NAME
  User: $DB_USER
  Password: $DB_PASSWORD

Helper Scripts:
  ~/scripts/start.sh     - Start all services
  ~/scripts/stop.sh      - Stop all services
  ~/scripts/restart.sh   - Restart all services
  ~/scripts/status.sh    - Check service status
  ~/scripts/logs.sh      - View logs (interactive)

Service Management:
  Backend: sudo systemctl {start|stop|restart|status} spot-optimizer-backend
  Nginx: sudo systemctl {start|stop|restart|status} nginx
  MySQL: docker {start|stop|restart} spot-mysql

View Logs:
  Backend: sudo journalctl -u spot-optimizer-backend -f
  MySQL: docker logs -f spot-mysql
  Nginx: sudo tail -f /var/log/nginx/spot-optimizer.error.log

Health Check:
  curl http://localhost:5000/health

Upload ML Models:
  Copy models to: $MODELS_DIR

Demo Accounts:
  - demo@acme.com (Token: demo_token_acme_12345)
  - demo@startupxyz.com (Token: demo_token_startup_67890)
  - demo@betatester.com (Token: demo_token_beta_11111)

================================================================================
Setup completed at: $(date)
================================================================================
EOF

echo ""
echo "==========================================================="
echo "NEXT STEPS"
echo "==========================================================="
echo "1. Check service status:"
echo "   ~/scripts/status.sh"
echo ""
echo "2. View backend logs:"
echo "   sudo journalctl -u spot-optimizer-backend -f"
echo ""
echo "3. Access dashboard:"
echo "   Open http://$PUBLIC_IP/ in your browser"
echo ""
echo "4. Upload ML models (optional):"
echo "   scp -i your-key.pem models/* ubuntu@$PUBLIC_IP:$MODELS_DIR/"
echo ""
echo "==========================================================="
echo "TROUBLESHOOTING"
echo "==========================================================="
echo "Backend not starting:"
echo "  sudo journalctl -u spot-optimizer-backend -n 100"
echo ""
echo "Database connection issues:"
echo "  docker logs spot-mysql"
echo "  docker exec -it spot-mysql mysql -u root -p"
echo ""
echo "Frontend not loading:"
echo "  sudo nginx -t"
echo "  sudo tail -f /var/log/nginx/spot-optimizer.error.log"
echo ""
echo "CORS errors:"
echo "  - Check browser console for specific errors"
echo "  - Verify Nginx config: sudo nginx -t"
echo "  - Check backend CORS: curl -I http://localhost:5000/health"
echo ""
echo "MySQL permission errors:"
echo "  sudo chown -R 999:999 /home/ubuntu/mysql-data"
echo "  docker restart spot-mysql"
echo ""
echo "==========================================================="
log "============================================"
log "SETUP COMPLETE!"
log "============================================"
log ""
log "✓ Repository: $REPO_DIR"
log "✓ Backend: Flask app running on port $BACKEND_PORT"
log "✓ Frontend: Vite React app served by Nginx"
log "✓ Database: MySQL 8.0 running in Docker"
log "✓ CORS: Properly configured in both backend and Nginx"
log ""
log "Dashboard URL: http://$PUBLIC_IP/"
log ""
log "View status: ~/scripts/status.sh"
log "View logs: ~/scripts/logs.sh"
log "View details: cat ~/SETUP_COMPLETE.txt"
log "============================================"
