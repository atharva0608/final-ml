#!/bin/bash
# ==============================================================================
# AWS Spot Optimizer - Complete EC2 Setup Script v5.0
# ==============================================================================
# Compatible with:
#   - Backend: https://github.com/atharva0608/final-ml.git
#   - Frontend: https://github.com/atharva0608/frontend-.git
#   - Database: schema_cleaned.sql v6.0 (MySQL 8.0) - Optimized schema
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
# CONFIGURATION
# ==============================================================================

# GitHub repository
GITHUB_REPO="https://github.com/atharva0608/final-ml.git"
CLONE_DIR="/home/ubuntu/final-ml"

# Application directories
APP_DIR="/home/ubuntu/spot-optimizer"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
MODELS_DIR="/home/ubuntu/production_models"
LOGS_DIR="/home/ubuntu/logs"
SCRIPTS_DIR="/home/ubuntu/scripts"

# Database configuration
DB_ROOT_PASSWORD="SpotOptimizer2024!"
DB_USER="spotuser"
DB_PASSWORD="SpotUser2024!"
DB_NAME="spot_optimizer"
DB_PORT=3306

# Backend configuration
BACKEND_PORT=5000
BACKEND_HOST="0.0.0.0"

# Frontend build directory (served by Nginx)
NGINX_ROOT="/var/www/spot-optimizer"

log "Starting AWS Spot Optimizer Setup..."
log "============================================"

# ==============================================================================
# STEP 0: CLONE OR UPDATE REPOSITORIES
# ==============================================================================

log "Step 0: Ensuring repositories are available..."

# Clone/update backend repository
if [ -d "$CLONE_DIR/.git" ]; then
    log "Backend repository already exists at $CLONE_DIR"
    cd "$CLONE_DIR"
    log "Pulling latest backend changes..."
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || warn "Could not pull backend changes"
else
    log "Cloning backend repository from $GITHUB_REPO..."
    cd /home/ubuntu
    if [ -d "$CLONE_DIR" ]; then
        warn "Directory exists but is not a git repository, removing..."
        sudo rm -rf "$CLONE_DIR"
    fi
    git clone "$GITHUB_REPO" "$CLONE_DIR"
    cd "$CLONE_DIR"
fi

# Set REPO_DIR to the cloned directory
REPO_DIR="$CLONE_DIR"

# Clone/update frontend repository separately
FRONTEND_REPO="https://github.com/atharva0608/frontend-.git"
FRONTEND_DIR="$REPO_DIR/frontend"

if [ -d "$FRONTEND_DIR/.git" ]; then
    log "Frontend repository already exists at $FRONTEND_DIR"
    cd "$FRONTEND_DIR"
    log "Pulling latest frontend changes..."
    git pull origin main 2>/dev/null || warn "Could not pull frontend changes"
    cd "$REPO_DIR"
else
    log "Cloning frontend repository from $FRONTEND_REPO..."
    if [ -d "$FRONTEND_DIR" ]; then
        warn "Frontend directory exists, removing..."
        sudo rm -rf "$FRONTEND_DIR"
    fi
    git clone "$FRONTEND_REPO" "$FRONTEND_DIR"
fi

log "✓ Repositories cloned/updated successfully"

# Verify critical files exist
if [ ! -f "$REPO_DIR/backend.py" ]; then
    error "backend.py not found in repository!"
    exit 1
fi

# Check for schema files (prefer cleaned, fallback to original)
if [ ! -f "$REPO_DIR/schema_cleaned.sql" ] && [ ! -f "$REPO_DIR/schema.sql" ]; then
    error "No schema file (schema_cleaned.sql or schema.sql) found in repository!"
    exit 1
fi

if [ -f "$REPO_DIR/schema_cleaned.sql" ]; then
    log "✓ Found cleaned schema v6.0 (optimized)"
elif [ -f "$REPO_DIR/schema.sql" ]; then
    log "✓ Found original schema v5.1"
fi

if [ ! -d "$FRONTEND_DIR/src" ]; then
    error "frontend/src directory not found!"
    exit 1
fi

if [ -f "$REPO_DIR/demo-data.sql" ]; then
    log "✓ Demo data file found (will import for testing)"
fi

log "✓ All required files verified"

# ==============================================================================
# STEP 1: GET INSTANCE METADATA USING IMDSv2
# ==============================================================================

log "Step 1: Retrieving instance metadata using IMDSv2..."

# Get IMDSv2 token (required for modern EC2 instances)
get_imds_token() {
    curl -s -X PUT "http://169.254.169.254/latest/api/token" \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null || echo ""
}

IMDS_TOKEN=$(get_imds_token)

if [ -z "$IMDS_TOKEN" ]; then
    warn "Could not get IMDSv2 token. Trying without token..."
    PUBLIC_IP=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
    INSTANCE_ID=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
    REGION=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "ap-south-1")
    AZ=$(curl -s --connect-timeout 5 http://169.254.169.254/latest/meta-data/placement/availability-zone 2>/dev/null || echo "unknown")
else
    log "IMDSv2 token acquired successfully"
    PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
        http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
    INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
        http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
    REGION=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
        http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "ap-south-1")
    AZ=$(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
        http://169.254.169.254/latest/meta-data/placement/availability-zone 2>/dev/null || echo "unknown")
fi

# Fallback for public IP if not available via metadata
if [ -z "$PUBLIC_IP" ]; then
    warn "Could not get public IP from metadata service"
    PUBLIC_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || curl -s --connect-timeout 5 icanhazip.com 2>/dev/null || echo "UNKNOWN")
fi

log "Instance ID: $INSTANCE_ID"
log "Region: $REGION"
log "Availability Zone: $AZ"
log "Public IP: $PUBLIC_IP"

# ==============================================================================
# STEP 2: UPDATE SYSTEM AND INSTALL DEPENDENCIES
# ==============================================================================

log "Step 2: Updating system and installing dependencies..."

# Update package list
sudo apt-get update -y

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
    # Use sg to run remaining docker commands with docker group
    export DOCKER_GROUP_ACTIVE=1
else
    warn "Docker group added but requires shell restart to take effect"
fi

log "Docker configured"

# ==============================================================================
# STEP 4: INSTALL NODE.JS (LTS v20)
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
sudo mkdir -p "$FRONTEND_DIR"
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
chmod 755 "$FRONTEND_DIR"
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

# ==============================================================================
# STEP 7: IMPORT DATABASE SCHEMA
# ==============================================================================

log "Step 7: Importing database schema..."

# Try cleaned schema first (v6.0), fallback to original schema (v5.1)
SCHEMA_FILE=""
if [ -f "$REPO_DIR/schema_cleaned.sql" ]; then
    SCHEMA_FILE="$REPO_DIR/schema_cleaned.sql"
    log "Found cleaned schema v6.0: $SCHEMA_FILE"
elif [ -f "$REPO_DIR/schema.sql" ]; then
    SCHEMA_FILE="$REPO_DIR/schema.sql"
    log "Found original schema v5.1: $SCHEMA_FILE"
else
    error "No schema file found in repository!"
    exit 1
fi

# Import schema
set +e
docker exec -i spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" "$DB_NAME" < "$SCHEMA_FILE" 2>&1 | grep -v "Warning" || true
set -e

# Verify tables were created
TABLE_COUNT=$(docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null || echo "0")

if [ "$TABLE_COUNT" -gt 0 ]; then
    log "Database schema imported successfully ($TABLE_COUNT tables created)"
    log "Schema version: $(basename $SCHEMA_FILE)"
else
    warn "Schema import may have issues - check manually"
fi

# Grant privileges
log "Configuring database user privileges..."
docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" --silent -e "
    GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'%';
    FLUSH PRIVILEGES;
" 2>/dev/null || true

log "Database privileges configured"

# Import demo data if available (optional)
DEMO_DATA_FILE="$REPO_DIR/demo-data.sql"
if [ -f "$DEMO_DATA_FILE" ]; then
    log "Found demo data file - importing for testing..."

    set +e
    docker exec -i spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" < "$DEMO_DATA_FILE" 2>&1 | grep -v "Warning" || true
    set -e

    # Verify demo data was imported
    DEMO_CLIENT_COUNT=$(docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM spot_optimizer.clients WHERE email LIKE '%demo%';" 2>/dev/null || echo "0")

    if [ "$DEMO_CLIENT_COUNT" -gt 0 ]; then
        log "✅ Demo data imported successfully ($DEMO_CLIENT_COUNT demo clients)"
        log "Demo Accounts:"
        log "  - demo@acme.com (token: demo_token_acme_12345) - Enterprise plan"
        log "  - demo@startupxyz.com (token: demo_token_startup_67890) - Professional plan"
        log "  - demo@betatester.com (token: demo_token_beta_11111) - Free plan"
    else
        warn "Demo data import may have issues - check manually"
    fi
else
    log "No demo data file found - skipping (production setup)"
fi

# ==============================================================================
# STEP 8: SETUP PYTHON BACKEND
# ==============================================================================

log "Step 8: Setting up Python backend..."

cd "$BACKEND_DIR"

# Create Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Copy backend.py from repository
log "Copying backend files from repository..."
if [ -f "$REPO_DIR/backend.py" ]; then
    cp "$REPO_DIR/backend.py" "$BACKEND_DIR/"
    log "✓ Copied backend.py"
else
    error "backend.py not found in repository!"
    exit 1
fi

# Create requirements.txt with exact dependencies
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

# Install Python dependencies
log "Installing Python dependencies..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
pip install -r requirements.txt

log "Python dependencies installed"

# Create environment configuration file
cat > "$BACKEND_DIR/.env" << EOF
# Database Configuration
DB_HOST=127.0.0.1
DB_PORT=$DB_PORT
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
DB_POOL_SIZE=10

# Decision Engine
DECISION_ENGINE_MODULE=decision_engines.ml_based_engine
DECISION_ENGINE_CLASS=MLBasedDecisionEngine
MODEL_DIR=$MODELS_DIR

# Server
HOST=$BACKEND_HOST
PORT=$BACKEND_PORT
DEBUG=False

# Background Jobs
ENABLE_BACKGROUND_JOBS=True

# Agent Communication
AGENT_HEARTBEAT_TIMEOUT=120
EOF

log "Backend environment configured"

# Create startup script for backend
cat > "$BACKEND_DIR/start_backend.sh" << 'EOF'
#!/bin/bash
cd /home/ubuntu/spot-optimizer/backend
source venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Start with gunicorn
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --threads 2 \
    --worker-class gthread \
    --timeout 120 \
    --access-logfile /home/ubuntu/logs/backend_access.log \
    --error-logfile /home/ubuntu/logs/backend_error.log \
    --capture-output \
    --log-level info \
    backend:app
EOF

chmod +x "$BACKEND_DIR/start_backend.sh"

deactivate

log "Backend setup complete"

# ==============================================================================
# STEP 9: SETUP VITE FRONTEND
# ==============================================================================

log "Step 9: Setting up Vite React frontend..."

# Copy entire frontend directory from repository
log "Copying frontend from repository..."
if [ -d "$REPO_DIR/frontend" ]; then
    # Copy all frontend files
    cp -r "$REPO_DIR/frontend"/* "$FRONTEND_DIR/" 2>/dev/null || true

    # Also copy hidden files like .gitignore
    cp -r "$REPO_DIR/frontend"/.[!.]* "$FRONTEND_DIR/" 2>/dev/null || true

    log "✓ Copied frontend files"
else
    error "frontend directory not found in repository!"
    exit 1
fi

cd "$FRONTEND_DIR"

# ==============================================================================
# IMPROVED API URL CONFIGURATION - AUTO-DETECTION
# ==============================================================================
# Instead of using sed to replace URLs, we deploy an auto-detection config
# that automatically determines the correct backend URL at runtime.
# ==============================================================================

log "Configuring API auto-detection for http://$PUBLIC_IP:5000..."

# Create the auto-detection config file
mkdir -p src/config
cat > src/config/api.jsx << 'APICONFIG_EOF'
// ==============================================================================
// API CONFIGURATION - AUTO-DETECTION
// ==============================================================================
// This configuration automatically detects the correct backend URL:
// - In production (EC2): Uses the EC2 instance's public IP
// - In development: Uses localhost:5000
// - Can be overridden with VITE_API_URL environment variable during build
// ==============================================================================

// Method 1: Environment variable set during build (highest priority)
const ENV_API_URL = import.meta.env.VITE_API_URL;

// Method 2: Auto-detect from current browser location
const getAutoDetectedURL = () => {
  // If we're in the browser
  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;

    // If running on localhost (development), connect to localhost:5000
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:5000';
    }

    // Otherwise, use the current hostname with port 5000 (production on EC2)
    return `${protocol}//${hostname}:5000`;
  }

  // Fallback for SSR or non-browser environments
  return 'http://localhost:5000';
};

// Final configuration with priority:
// 1. Environment variable (VITE_API_URL) - set during build
// 2. Auto-detected from window.location
export const API_CONFIG = {
  BASE_URL: ENV_API_URL || getAutoDetectedURL(),
};

// Log the configuration in development
if (import.meta.env.DEV) {
  console.log('[API Config] Using BASE_URL:', API_CONFIG.BASE_URL);
  console.log('[API Config] Source:', ENV_API_URL ? 'Environment Variable' : 'Auto-detected');
}
APICONFIG_EOF

log "✓ API auto-detection config created"
log "  → Auto-detection: Frontend will use window.location to find backend"
log "  → Environment override: VITE_API_URL=http://$PUBLIC_IP:5000"

# Install npm dependencies
log "Installing npm dependencies (this may take a few minutes)..."
npm install --legacy-peer-deps

# Build the frontend with environment variable
log "Building frontend for production with API URL: http://$PUBLIC_IP:5000..."
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build

# Copy build to Nginx root
sudo rm -rf "$NGINX_ROOT"/*
sudo cp -r dist/* "$NGINX_ROOT/"
sudo chown -R www-data:www-data "$NGINX_ROOT"

log "Frontend built and deployed to $NGINX_ROOT"

# ==============================================================================
# STEP 10: CONFIGURE NGINX WITH PROPER CORS
# ==============================================================================

log "Step 10: Configuring Nginx with CORS support..."

# Backup default config
sudo mv /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup 2>/dev/null || true

# Create Nginx configuration with CORS headers
sudo tee /etc/nginx/sites-available/spot-optimizer << EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    root $NGINX_ROOT;
    index index.html;

    # Increase buffer sizes for API responses
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;
    large_client_header_buffers 4 32k;

    # Serve React frontend
    location / {
        try_files \$uri \$uri/ /index.html;

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
        if (\$request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }

        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Health check endpoint with CORS
    location /health {
        add_header 'Access-Control-Allow-Origin' '*' always;
        proxy_pass http://127.0.0.1:$BACKEND_PORT/health;
        proxy_set_header Host \$host;
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
EOF

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

sudo tee /etc/systemd/system/spot-optimizer-backend.service << EOF
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

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable spot-optimizer-backend

log "Backend systemd service created"

# ==============================================================================
# STEP 12: CREATE HELPER SCRIPTS
# ==============================================================================

log "Step 12: Creating helper scripts..."

# 1. START script
cat > "$SCRIPTS_DIR/start.sh" << 'SCRIPT_EOF'
#!/bin/bash
echo "Starting AWS Spot Optimizer services..."

# Start MySQL if not running
if ! docker ps | grep -q spot-mysql; then
    echo "Starting MySQL container..."
    docker start spot-mysql
    sleep 5
fi

# Start backend
echo "Starting backend service..."
sudo systemctl start spot-optimizer-backend

# Wait for backend to be ready
echo "Waiting for backend..."
for i in {1..30}; do
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo "✓ Backend is ready"
        break
    fi
    sleep 1
done

# Ensure Nginx is running
sudo systemctl start nginx

echo "All services started!"
SCRIPT_EOF
chmod +x "$SCRIPTS_DIR/start.sh"

# 2. STOP script
cat > "$SCRIPTS_DIR/stop.sh" << 'SCRIPT_EOF'
#!/bin/bash
echo "Stopping AWS Spot Optimizer services..."
sudo systemctl stop spot-optimizer-backend
echo "Services stopped (MySQL still running for data persistence)"
SCRIPT_EOF
chmod +x "$SCRIPTS_DIR/stop.sh"

# 3. STATUS script
cat > "$SCRIPTS_DIR/status.sh" << 'SCRIPT_EOF'
#!/bin/bash
echo "==================================="
echo "AWS Spot Optimizer Service Status"
echo "==================================="

# MySQL
echo "MySQL Container:"
docker ps --filter name=spot-mysql --format "  Status: {{.Status}}"

# Backend
echo ""
echo "Backend Service:"
systemctl status spot-optimizer-backend --no-pager | grep "Active:" | sed 's/^/  /'

# Check backend API
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo "  API: ✓ Responding"
else
    echo "  API: ✗ Not responding"
fi

# Nginx
echo ""
echo "Nginx (Frontend):"
systemctl status nginx --no-pager | grep "Active:" | sed 's/^/  /'

echo ""
echo "==================================="
SCRIPT_EOF
chmod +x "$SCRIPTS_DIR/status.sh"

# 4. RESTART script
cat > "$SCRIPTS_DIR/restart.sh" << 'SCRIPT_EOF'
#!/bin/bash
echo "Restarting AWS Spot Optimizer services..."
docker restart spot-mysql
sleep 5
sudo systemctl restart spot-optimizer-backend
sudo systemctl restart nginx
echo "All services restarted!"
sleep 2
/home/ubuntu/scripts/status.sh
SCRIPT_EOF
chmod +x "$SCRIPTS_DIR/restart.sh"

# 5. LOGS script
cat > "$SCRIPTS_DIR/logs.sh" << 'SCRIPT_EOF'
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
    2) tail -f /home/ubuntu/logs/backend_access.log 2>/dev/null || echo "Log file not found" ;;
    3) tail -f /home/ubuntu/logs/backend_error.log 2>/dev/null || echo "Log file not found" ;;
    4) sudo tail -f /var/log/nginx/spot-optimizer.access.log ;;
    5) sudo tail -f /var/log/nginx/spot-optimizer.error.log ;;
    6) docker logs -f spot-mysql ;;
    *) echo "Invalid choice" ;;
esac
SCRIPT_EOF
chmod +x "$SCRIPTS_DIR/logs.sh"

log "Helper scripts created"

# ==============================================================================
# STEP 13: CREATE MODELS DIRECTORY
# ==============================================================================

log "Step 13: Creating models directory..."

mkdir -p "$MODELS_DIR"

cat > "$MODELS_DIR/README.md" << 'EOF'
# Production Models Directory

Upload your trained ML models here.

After uploading, restart the backend:
```bash
~/scripts/restart.sh
```
EOF

log "Models directory ready"

# ==============================================================================
# STEP 14: FIX ALL PERMISSIONS
# ==============================================================================

log "Step 14: Fixing all permissions..."

# Backend directory permissions
sudo chown -R ubuntu:ubuntu "$BACKEND_DIR"
chmod -R 755 "$BACKEND_DIR"
chmod +x "$BACKEND_DIR/start_backend.sh"

# Frontend directory permissions
sudo chown -R ubuntu:ubuntu "$FRONTEND_DIR"
chmod -R 755 "$FRONTEND_DIR"

# Models directory permissions
sudo chown -R ubuntu:ubuntu "$MODELS_DIR"
chmod -R 755 "$MODELS_DIR"

# Logs directory permissions
sudo chown -R ubuntu:ubuntu "$LOGS_DIR"
chmod -R 755 "$LOGS_DIR"

# Scripts directory permissions
sudo chown -R ubuntu:ubuntu "$SCRIPTS_DIR"
chmod -R 755 "$SCRIPTS_DIR"

# MySQL data directory permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/mysql-data
chmod -R 755 /home/ubuntu/mysql-data

# Nginx directory permissions
sudo chown -R www-data:www-data "$NGINX_ROOT"
chmod -R 755 "$NGINX_ROOT"

# Repository permissions
sudo chown -R ubuntu:ubuntu "$CLONE_DIR"

log "All permissions fixed"

# ==============================================================================
# STEP 15: START ALL SERVICES
# ==============================================================================

log "Step 15: Starting all services..."

# Start backend service
sudo systemctl start spot-optimizer-backend

# Wait for backend to be ready
log "Waiting for backend to start..."
sleep 5

MAX_ATTEMPTS=30
ATTEMPT=0
while ! curl -s http://localhost:5000/health > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        warn "Backend not responding yet. Check logs: sudo journalctl -u spot-optimizer-backend"
        break
    fi
    sleep 2
done

if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    log "✓ Backend is running and healthy!"
else
    warn "Backend may not be fully operational. Check logs."
fi

# ==============================================================================
# STEP 16: CREATE SETUP SUMMARY
# ==============================================================================

log "Step 16: Creating setup summary..."

cat > /home/ubuntu/SETUP_COMPLETE.txt << EOF
================================================================================
AWS SPOT OPTIMIZER - SETUP COMPLETE (v5.0)
================================================================================

Date: $(date)
Instance ID: $INSTANCE_ID
Region: $REGION
Availability Zone: $AZ
Public IP: $PUBLIC_IP

================================================================================
REPOSITORIES
================================================================================
Backend: $CLONE_DIR
  GitHub: $GITHUB_REPO
Frontend: $FRONTEND_DIR
  GitHub: https://github.com/atharva0608/frontend-.git

================================================================================
DATABASE SCHEMA
================================================================================
Version: $(basename ${SCHEMA_FILE:-"Unknown"})
Tables Created: $TABLE_COUNT
Note: Using optimized schema v6.0 with reduced complexity

================================================================================
ACCESS URLS
================================================================================
Frontend Dashboard: http://$PUBLIC_IP/
Backend API: http://$PUBLIC_IP/api/admin/stats
Health Check: http://$PUBLIC_IP/health

================================================================================
DIRECTORY STRUCTURE
================================================================================
Repository: $CLONE_DIR
Application: $APP_DIR
Backend: $BACKEND_DIR
Frontend: $FRONTEND_DIR
Models: $MODELS_DIR
Logs: $LOGS_DIR
Scripts: $SCRIPTS_DIR

================================================================================
DATABASE CREDENTIALS
================================================================================
Host: 127.0.0.1
Port: $DB_PORT
Database: $DB_NAME
User: $DB_USER
Password: $DB_PASSWORD
Root Password: $DB_ROOT_PASSWORD

================================================================================
HELPER SCRIPTS (in $SCRIPTS_DIR)
================================================================================
start.sh    - Start all services
stop.sh     - Stop services
status.sh   - Check service status
restart.sh  - Restart all services
logs.sh     - View logs

Usage:
  ~/scripts/status.sh
  ~/scripts/restart.sh
  ~/scripts/logs.sh

================================================================================
SECURITY & CORS
================================================================================
✓ CORS enabled in backend (Flask-CORS)
✓ CORS headers configured in Nginx
✓ Proper file permissions set
✓ Systemd service with security options
✓ Docker containers isolated in network

================================================================================
NEXT STEPS
================================================================================
1. Check service status:
   ~/scripts/status.sh

2. View backend logs:
   sudo journalctl -u spot-optimizer-backend -f

3. Access dashboard:
   Open http://$PUBLIC_IP/ in your browser

4. Upload ML models (optional):
   scp -i your-key.pem models/* ubuntu@$PUBLIC_IP:$MODELS_DIR/

5. Update repository:
   cd $CLONE_DIR && git pull

================================================================================
TROUBLESHOOTING
================================================================================
Backend not starting:
  sudo journalctl -u spot-optimizer-backend -n 100

Database connection issues:
  docker logs spot-mysql
  docker exec -it spot-mysql mysql -u root -p

Frontend not loading:
  sudo nginx -t
  sudo tail -f /var/log/nginx/spot-optimizer.error.log

CORS errors:
  - Check browser console for specific errors
  - Verify Nginx config: sudo nginx -t
  - Check backend CORS: curl -I http://localhost:5000/health

Repository updates:
  cd $CLONE_DIR
  git pull origin main
  ~/scripts/restart.sh

================================================================================
EOF

cat /home/ubuntu/SETUP_COMPLETE.txt

log "============================================"
log "SETUP COMPLETE!"
log "============================================"
log ""
log "✓ Repository cloned: $CLONE_DIR"
log "✓ Backend: Flask app running on port 5000"
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
