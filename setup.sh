#!/bin/bash
# ==============================================================================
# AWS Spot Optimizer - Complete EC2 Setup Script (UPDATED v2.1)
# ==============================================================================
# Updated dependencies for new App.jsx, backend.py v2.1.0, and schema v1.4.0
# ==============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
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

GITHUB_REPO="https://github.com/atharva0608/ml-spot-v2.git"
APP_DIR="/home/ubuntu/ml-spot-optimizer"
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
sudo apt-get install -y \
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

# Remove old Docker versions if any
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu

log "Docker installed and configured"

# ==============================================================================
# STEP 4: INSTALL NODE.JS (LTS)
# ==============================================================================

log "Step 4: Installing Node.js LTS..."

# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
NODE_VERSION=$(node --version)
NPM_VERSION=$(npm --version)
log "Node.js $NODE_VERSION installed"
log "npm $NPM_VERSION installed"

# ==============================================================================
# STEP 5: CREATE DIRECTORY STRUCTURE
# ==============================================================================

log "Step 5: Creating directory structure..."

# Create all necessary directories
sudo mkdir -p "$APP_DIR"
sudo mkdir -p "$BACKEND_DIR"
sudo mkdir -p "$FRONTEND_DIR"
sudo mkdir -p "$MODELS_DIR"
sudo mkdir -p "$LOGS_DIR"
sudo mkdir -p "$SCRIPTS_DIR"
sudo mkdir -p "$NGINX_ROOT"

# Set ownership
sudo chown -R ubuntu:ubuntu /home/ubuntu/
sudo chown -R www-data:www-data "$NGINX_ROOT"

log "Directory structure created"

# ==============================================================================
# STEP 6: CLONE GITHUB REPOSITORY
# ==============================================================================

log "Step 6: Cloning GitHub repository..."

# Remove existing directory if it exists
if [ -d "$APP_DIR/.git" ]; then
    warn "Repository already exists, pulling latest changes..."
    cd "$APP_DIR"
    git pull origin main || git pull origin master || true
else
    # Clone the repository
    sudo rm -rf "$APP_DIR"
    sudo mkdir -p "$APP_DIR"
    git clone "$GITHUB_REPO" "$APP_DIR"
fi

cd "$APP_DIR"
log "Repository cloned to $APP_DIR"

# List contents to verify
log "Repository contents:"
ls -la

# ==============================================================================
# STEP 7: SETUP DATABASE WITH DOCKER
# ==============================================================================

log "Step 7: Setting up MySQL database with Docker..."

# Stop and remove existing MySQL container if exists
docker stop spot-mysql 2>/dev/null || true
docker rm spot-mysql 2>/dev/null || true

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
    --innodb_buffer_pool_size=256M

log "MySQL container started with enhanced configuration"

# Wait for MySQL to be ready
log "Waiting for MySQL to initialize (this may take 30-60 seconds)..."
sleep 15

# First wait for ping (container is up)
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

log "MySQL container is responding to ping"

# Now wait for actual authentication to work (root password is set)
log "Waiting for MySQL authentication to be ready..."
ATTEMPT=0
while ! docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -e "SELECT 1;" > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        error "MySQL authentication failed after $MAX_ATTEMPTS attempts"
        log "Checking MySQL logs..."
        docker logs --tail 30 spot-mysql
        exit 1
    fi
    if [ $((ATTEMPT % 5)) -eq 0 ]; then
        log "Waiting for MySQL auth... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    fi
    sleep 2
done

log "MySQL is fully ready and accepting authenticated connections!"

# ==============================================================================
# STEP 8: IMPORT DATABASE SCHEMA
# ==============================================================================

log "Step 8: Importing database schema..."

# Find schema.sql file (check repo root first since flat structure)
SCHEMA_FILE=""
if [ -f "$APP_DIR/schema.sql" ]; then
    SCHEMA_FILE="$APP_DIR/schema.sql"
elif [ -f "$APP_DIR/database/schema.sql" ]; then
    SCHEMA_FILE="$APP_DIR/database/schema.sql"
elif [ -f "$APP_DIR/sql/schema.sql" ]; then
    SCHEMA_FILE="$APP_DIR/sql/schema.sql"
elif [ -f "$BACKEND_DIR/schema.sql" ]; then
    SCHEMA_FILE="$BACKEND_DIR/schema.sql"
fi

if [ -n "$SCHEMA_FILE" ] && [ -f "$SCHEMA_FILE" ]; then
    log "Found schema file: $SCHEMA_FILE"
    # Import schema - ignore non-critical errors (set +e temporarily)
    set +e
    docker exec -i spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" < "$SCHEMA_FILE" 2>&1 | grep -v "Warning"
    set -e
    
    # Verify tables were created
    TABLE_COUNT=$(docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" 2>/dev/null)
    
    if [ "$TABLE_COUNT" -gt 0 ]; then
        log "Database schema imported successfully ($TABLE_COUNT tables created)"
    else
        error "Failed to import schema - no tables found"
        exit 1
    fi
else
    warn "Schema file not found in repository. You'll need to import it manually."
    warn "Expected locations: $APP_DIR/schema.sql, $APP_DIR/database/schema.sql"
fi

# Grant privileges to the user
log "Configuring database user privileges..."
docker exec spot-mysql mysql -u root -p"$DB_ROOT_PASSWORD" --silent -e "
    GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'%';
    FLUSH PRIVILEGES;
" 2>/dev/null
log "Database privileges configured"

# ==============================================================================
# STEP 9: SETUP PYTHON BACKEND (UPDATED DEPENDENCIES)
# ==============================================================================

log "Step 9: Setting up Python backend with updated dependencies..."

# IMPORTANT: Create the backend directory structure first
mkdir -p "$BACKEND_DIR"
cd "$BACKEND_DIR"

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# FIXED: Copy backend files from repo ROOT (flat structure)
log "Copying backend files from repository root..."

if [ -f "$APP_DIR/backend.py" ]; then
    cp "$APP_DIR/backend.py" "$BACKEND_DIR/"
    log "✓ Copied backend.py"
else
    warn "backend.py not found in repository root!"
fi

if [ -f "$APP_DIR/decision_engine.py" ]; then
    cp "$APP_DIR/decision_engine.py" "$BACKEND_DIR/"
    log "✓ Copied decision_engine.py"
else
    warn "decision_engine.py not found in repository root!"
fi

# Create requirements.txt with UPDATED dependencies
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
DECISION_ENGINE_TYPE=hybrid
MODEL_DIR=$MODELS_DIR
REGION=ap-south-1

# Server
HOST=$BACKEND_HOST
PORT=$BACKEND_PORT
DEBUG=False
EOF

log "Backend environment configured"

# Create startup script for backend with enhanced gunicorn config
cat > "$BACKEND_DIR/start_backend.sh" << 'EOF'
#!/bin/bash
cd /home/ubuntu/ml-spot-optimizer/backend
source venv/bin/activate

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Start with gunicorn for production with threading support
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

log "Backend setup complete with enhanced configuration"

# ==============================================================================
# STEP 10: SETUP FRONTEND (UPDATED DEPENDENCIES)
# ==============================================================================

log "Step 10: Setting up React frontend with updated dependencies..."

# Create frontend directory
mkdir -p "$FRONTEND_DIR"
cd "$FRONTEND_DIR"

# Create package.json with UPDATED dependencies
cat > package.json << 'EOF'
{
  "name": "spot-optimizer-dashboard",
  "version": "2.0.0",
  "private": true,
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "recharts": "^2.10.0",
    "lucide-react": "^0.263.1"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject"
  },
  "eslintConfig": {
    "extends": [
      "react-app",
      "react-app/jest"
    ]
  },
  "browserslist": {
    "production": [
      ">0.2%",
      "not dead",
      "not op_mini all"
    ],
    "development": [
      "last 1 chrome version",
      "last 1 firefox version",
      "last 1 safari version"
    ]
  },
  "devDependencies": {
    "react-scripts": "5.0.1",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.32"
  }
}
EOF

# Create public/index.html
mkdir -p public
cat > public/index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <meta name="description" content="AWS Spot Instance Optimizer Dashboard" />
    <title>AWS Spot Optimizer Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>
EOF

# Create src directory and index.js
mkdir -p src

cat > src/index.js << 'EOF'
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
EOF

# FIXED: Copy App.jsx from repo ROOT (flat structure)
log "Copying App.jsx from repository root..."
if [ -f "$APP_DIR/App.jsx" ]; then
    cp "$APP_DIR/App.jsx" "$FRONTEND_DIR/src/App.jsx"
    log "✓ Copied App.jsx"
else
    warn "App.jsx not found in repository root!"
fi

# Update API_CONFIG in App.jsx to use actual public IP
if [ -f "$FRONTEND_DIR/src/App.jsx" ]; then
    # Replace localhost with the actual backend URL
    sed -i "s|BASE_URL: 'http://localhost:5000'|BASE_URL: 'http://$PUBLIC_IP:5000'|g" "$FRONTEND_DIR/src/App.jsx"
    log "Updated API_CONFIG to use http://$PUBLIC_IP:5000"
fi

# Create Tailwind config
cat > tailwind.config.js << 'EOF'
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
EOF

# Create PostCSS config
cat > postcss.config.js << 'EOF'
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
EOF

# Install npm dependencies
log "Installing npm dependencies (this may take a few minutes)..."
npm install

# Build the frontend
log "Building frontend for production..."
npm run build

# Copy build to Nginx root
sudo rm -rf "$NGINX_ROOT"/*
sudo cp -r build/* "$NGINX_ROOT/"
sudo chown -R www-data:www-data "$NGINX_ROOT"

log "Frontend built and deployed to $NGINX_ROOT"

# ==============================================================================
# STEP 11: CONFIGURE NGINX (ENHANCED)
# ==============================================================================

log "Step 11: Configuring Nginx with enhanced buffer settings..."

# Backup default config
sudo mv /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup 2>/dev/null || true

# Create Nginx configuration with enhanced settings
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
    
    # Serve React frontend
    location / {
        try_files \$uri \$uri/ /index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
    
    # Proxy API requests to backend
    location /api/ {
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
    
    # Health check endpoint
    location /health {
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

log "Nginx configured and running on port 80 with enhanced settings"

# ==============================================================================
# STEP 12: CREATE SYSTEMD SERVICE FOR BACKEND
# ==============================================================================

log "Step 12: Creating systemd service for backend..."

sudo tee /etc/systemd/system/spot-optimizer-backend.service << EOF
[Unit]
Description=AWS Spot Optimizer Backend
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=ubuntu
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

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable spot-optimizer-backend

log "Backend systemd service created"

# ==============================================================================
# STEP 13: CREATE HELPER SCRIPTS
# ==============================================================================

log "Step 13: Creating helper scripts..."

# 1. START script
cat > "$SCRIPTS_DIR/start.sh" << 'EOF'
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
echo "Waiting for backend to be ready..."
MAX_ATTEMPTS=30
ATTEMPT=0
while ! curl -s http://localhost:5000/health > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        echo "Backend failed to start. Check logs with: journalctl -u spot-optimizer-backend"
        exit 1
    fi
    sleep 1
done

# Ensure Nginx is running
sudo systemctl start nginx

echo "All services started!"
echo "Frontend: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || curl -s ifconfig.me)"
echo "Backend API: http://localhost:5000"
EOF
chmod +x "$SCRIPTS_DIR/start.sh"

# 2. STOP script
cat > "$SCRIPTS_DIR/stop.sh" << 'EOF'
#!/bin/bash
echo "Stopping AWS Spot Optimizer services..."

# Stop backend
sudo systemctl stop spot-optimizer-backend

# Stop MySQL (optional, comment out if you want to keep data)
# docker stop spot-mysql

echo "Services stopped (MySQL still running for data persistence)"
EOF
chmod +x "$SCRIPTS_DIR/stop.sh"

# 3. STATUS script
cat > "$SCRIPTS_DIR/status.sh" << 'EOF'
#!/bin/bash
echo "==================================="
echo "AWS Spot Optimizer Service Status"
echo "==================================="

# Get public IP using IMDSv2
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300" 2>/dev/null)
if [ -n "$TOKEN" ]; then
    PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
else
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null)
fi

echo ""
echo "Instance Info:"
echo "  Public IP: $PUBLIC_IP"
echo ""

echo "MySQL Container:"
if docker ps | grep -q spot-mysql; then
    echo "  Status: ✓ Running"
    docker exec spot-mysql mysqladmin ping -u root -pSpotOptimizer2024! --silent 2>/dev/null && echo "  Database: ✓ Responding" || echo "  Database: ✗ Not responding"
else
    echo "  Status: ✗ Not running"
fi

echo ""
echo "Backend Service:"
if systemctl is-active --quiet spot-optimizer-backend; then
    echo "  Status: ✓ Running"
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo "  API: ✓ Responding"
        HEALTH=$(curl -s http://localhost:5000/health | python3 -m json.tool 2>/dev/null)
        echo "  Health Check:"
        echo "$HEALTH" | head -10 | sed 's/^/    /'
    else
        echo "  API: ✗ Not responding"
    fi
else
    echo "  Status: ✗ Not running"
    echo "  Check logs: journalctl -u spot-optimizer-backend -n 50"
fi

echo ""
echo "Nginx (Frontend):"
if systemctl is-active --quiet nginx; then
    echo "  Status: ✓ Running"
    if curl -s http://localhost/ > /dev/null 2>&1; then
        echo "  Frontend: ✓ Accessible"
    else
        echo "  Frontend: ✗ Not accessible"
    fi
else
    echo "  Status: ✗ Not running"
fi

echo ""
echo "==================================="
echo "Access URLs:"
echo "  Frontend: http://$PUBLIC_IP/"
echo "  Backend API: http://$PUBLIC_IP:5000/health"
echo "==================================="
EOF
chmod +x "$SCRIPTS_DIR/status.sh"

# 4. RESTART script
cat > "$SCRIPTS_DIR/restart.sh" << 'EOF'
#!/bin/bash
echo "Restarting AWS Spot Optimizer services..."

# Restart MySQL container
docker restart spot-mysql
sleep 5

# Restart backend
sudo systemctl restart spot-optimizer-backend

# Restart Nginx
sudo systemctl restart nginx

echo "All services restarted!"
sleep 3
/home/ubuntu/scripts/status.sh
EOF
chmod +x "$SCRIPTS_DIR/restart.sh"

# 5. CLEANUP script
cat > "$SCRIPTS_DIR/cleanup.sh" << 'EOF'
#!/bin/bash
echo "WARNING: This will remove all AWS Spot Optimizer data and services!"
read -p "Are you sure? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo "Stopping services..."
sudo systemctl stop spot-optimizer-backend
sudo systemctl disable spot-optimizer-backend
sudo rm -f /etc/systemd/system/spot-optimizer-backend.service

echo "Removing Docker containers..."
docker stop spot-mysql
docker rm spot-mysql
docker network rm spot-network

echo "Removing Nginx configuration..."
sudo rm -f /etc/nginx/sites-enabled/spot-optimizer
sudo rm -f /etc/nginx/sites-available/spot-optimizer
sudo systemctl restart nginx

echo "Removing application files..."
sudo rm -rf /home/ubuntu/ml-spot-optimizer
sudo rm -rf /home/ubuntu/mysql-data
sudo rm -rf /var/www/spot-optimizer
sudo rm -rf /home/ubuntu/logs/*

echo "Cleanup complete!"
EOF
chmod +x "$SCRIPTS_DIR/cleanup.sh"

# 6. REBUILD FRONTEND script
cat > "$SCRIPTS_DIR/rebuild_frontend.sh" << 'EOF'
#!/bin/bash
echo "Rebuilding frontend..."

cd /home/ubuntu/ml-spot-optimizer/frontend

# Get current public IP
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300" 2>/dev/null)
if [ -n "$TOKEN" ]; then
    PUBLIC_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
else
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null)
fi

# Update API URL in App.jsx
if [ -f src/App.jsx ]; then
    sed -i "s|BASE_URL: 'http://[^']*'|BASE_URL: 'http://$PUBLIC_IP:5000'|g" src/App.jsx
    echo "Updated API URL to http://$PUBLIC_IP:5000"
fi

# Rebuild
npm run build

# Deploy
sudo rm -rf /var/www/spot-optimizer/*
sudo cp -r build/* /var/www/spot-optimizer/
sudo chown -R www-data:www-data /var/www/spot-optimizer

echo "Frontend rebuilt and deployed!"
echo "Access at: http://$PUBLIC_IP/"
EOF
chmod +x "$SCRIPTS_DIR/rebuild_frontend.sh"

# 7. VIEW LOGS script
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
    2) tail -f /home/ubuntu/logs/backend_access.log ;;
    3) tail -f /home/ubuntu/logs/backend_error.log ;;
    4) sudo tail -f /var/log/nginx/spot-optimizer.access.log ;;
    5) sudo tail -f /var/log/nginx/spot-optimizer.error.log ;;
    6) docker logs -f spot-mysql ;;
    *) echo "Invalid choice" ;;
esac
EOF
chmod +x "$SCRIPTS_DIR/logs.sh"

# 8. TEST CONNECTIVITY script
cat > "$SCRIPTS_DIR/test_connectivity.sh" << 'EOF'
#!/bin/bash
echo "Testing AWS Spot Optimizer Connectivity..."
echo "=========================================="

# Test Database
echo "1. Testing MySQL Database..."
if docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SELECT 1;" spot_optimizer > /dev/null 2>&1; then
    echo "   ✓ Database connection successful"
else
    echo "   ✗ Database connection failed"
fi

# Test Backend
echo "2. Testing Backend API..."
HEALTH=$(curl -s http://localhost:5000/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "   ✓ Backend is responding"
    DB_STATUS=$(echo "$HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('database', 'unknown'))" 2>/dev/null)
    echo "   Database status: $DB_STATUS"
else
    echo "   ✗ Backend is not responding"
fi

# Test Frontend through Nginx
echo "3. Testing Frontend (Nginx)..."
if curl -s http://localhost/ | grep -q "root"; then
    echo "   ✓ Frontend is being served"
else
    echo "   ✗ Frontend is not accessible"
fi

# Test API proxy through Nginx
echo "4. Testing API proxy through Nginx..."
if curl -s http://localhost/health | grep -q "status"; then
    echo "   ✓ API proxy is working"
else
    echo "   ✗ API proxy is not working"
fi

echo "=========================================="
echo "Connectivity test complete!"
EOF
chmod +x "$SCRIPTS_DIR/test_connectivity.sh"

log "Helper scripts created in $SCRIPTS_DIR"

# ==============================================================================
# STEP 14: CREATE MODELS PLACEHOLDER
# ==============================================================================

log "Step 14: Creating models directory structure..."

mkdir -p "$MODELS_DIR"

# Create placeholder manifest
cat > "$MODELS_DIR/manifest.json" << 'EOF'
{
  "version": "1.0.0",
  "created_at": "2024-01-01T00:00:00Z",
  "region": "ap-south-1",
  "engine_type": "hybrid",
  "note": "PLACEHOLDER - Upload your actual models here"
}
EOF

# Create README for models
cat > "$MODELS_DIR/README.md" << 'EOF'
# Production Models Directory

Upload your trained models here using SCP:
```bash
# From your local machine:
scp -i your-key.pem models/* ubuntu@YOUR_EC2_IP:/home/ubuntu/production_models/
```

Required files:
- manifest.json (model metadata)
- capacity_detector.pkl (capacity event detector)
- price_predictor.pkl (price prediction model)
- model_config.json (configuration)

After uploading, restart the backend:
```bash
~/scripts/restart.sh
```
EOF

log "Models directory ready at $MODELS_DIR"

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
        warn "Backend not responding yet. Check logs: journalctl -u spot-optimizer-backend"
        break
    fi
    sleep 2
done

if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    log "Backend is running and healthy!"
else
    warn "Backend may not be fully operational. Check logs."
fi

# ==============================================================================
# STEP 16: FINAL VERIFICATION AND SUMMARY
# ==============================================================================

log "Step 16: Final verification..."

# Create final summary
cat > /home/ubuntu/SETUP_COMPLETE.txt << EOF
================================================================================
AWS SPOT OPTIMIZER - SETUP COMPLETE (v2.1)
================================================================================

Date: $(date)
Instance ID: $INSTANCE_ID
Region: $REGION
Availability Zone: $AZ
Public IP: $PUBLIC_IP

================================================================================
UPDATED COMPONENTS
================================================================================
✓ Backend: Flask 3.0.0, MySQL 8.2.0, Added pandas support
✓ Frontend: Recharts 2.10.0, Tailwind 3.4.0
✓ MySQL: Enhanced with 200 connections, 256M buffer pool
✓ Gunicorn: Threading enabled (4 workers, 2 threads each)
✓ Nginx: Enhanced buffer sizes for large API responses

================================================================================
ACCESS URLS
================================================================================
Frontend Dashboard: http://$PUBLIC_IP/
Backend API Health: http://$PUBLIC_IP/health
Backend API (direct): http://$PUBLIC_IP:5000/health

================================================================================
DIRECTORY STRUCTURE
================================================================================
Application Code: $APP_DIR
Backend: $BACKEND_DIR
Frontend: $FRONTEND_DIR
Models (upload here): $MODELS_DIR
Logs: $LOGS_DIR
Helper Scripts: $SCRIPTS_DIR
Nginx Root: $NGINX_ROOT

================================================================================
DATABASE CREDENTIALS
================================================================================
Host: 127.0.0.1 (or localhost)
Port: $DB_PORT
Database: $DB_NAME
User: $DB_USER
Password: $DB_PASSWORD
Root Password: $DB_ROOT_PASSWORD

================================================================================
HELPER SCRIPTS (in $SCRIPTS_DIR)
================================================================================
start.sh              - Start all services
stop.sh               - Stop services (keeps MySQL running)
status.sh             - Check service status
restart.sh            - Restart all services
cleanup.sh            - Remove everything (DANGER!)
rebuild_frontend.sh   - Rebuild and redeploy frontend
logs.sh               - View various logs
test_connectivity.sh  - Test all connections

Usage:
  ~/scripts/status.sh
  ~/scripts/restart.sh
  ~/scripts/logs.sh

================================================================================
NEXT STEPS - UPDATE YOUR FILES
================================================================================
Your repository has files in the ROOT directory (flat structure).
The setup script has copied them to the correct locations:
  - backend.py → $BACKEND_DIR/backend.py
  - decision_engine.py → $BACKEND_DIR/decision_engine.py
  - App.jsx → $FRONTEND_DIR/src/App.jsx
  - schema.sql → Already imported to MySQL

If you need to update these files, upload them to the backend/frontend dirs:
  scp -i your-key.pem backend.py ubuntu@$PUBLIC_IP:$BACKEND_DIR/
  scp -i your-key.pem decision_engine.py ubuntu@$PUBLIC_IP:$BACKEND_DIR/
  scp -i your-key.pem App.jsx ubuntu@$PUBLIC_IP:$FRONTEND_DIR/src/

Then rebuild/restart:
  ~/scripts/rebuild_frontend.sh  # For frontend changes
  ~/scripts/restart.sh           # For backend changes

================================================================================
SERVICE STATUS
================================================================================
EOF

# Add live status to the file
{
    echo "MySQL Container: $(docker ps | grep -q spot-mysql && echo '✓ Running' || echo '✗ Not Running')"
    echo "Backend Service: $(systemctl is-active spot-optimizer-backend)"
    echo "Nginx Service: $(systemctl is-active nginx)"
    
    if curl -s http://localhost:5000/health > /dev/null 2>&1; then
        echo "Backend API: ✓ Responding"
    else
        echo "Backend API: ✗ Not responding (may still be starting)"
    fi
    
    if curl -s http://localhost/ > /dev/null 2>&1; then
        echo "Frontend: ✓ Accessible"
    else
        echo "Frontend: ✗ Not accessible"
    fi
} >> /home/ubuntu/SETUP_COMPLETE.txt

cat >> /home/ubuntu/SETUP_COMPLETE.txt << 'EOF'

================================================================================
TROUBLESHOOTING
================================================================================
If backend fails to start:
  journalctl -u spot-optimizer-backend -n 100
  
If database connection fails:
  docker logs spot-mysql
  docker exec -it spot-mysql mysql -u root -p
  
If frontend doesn't load:
  sudo nginx -t
  sudo tail -f /var/log/nginx/spot-optimizer.error.log
  
Check all connections:
  ~/scripts/test_connectivity.sh

================================================================================
EOF

# Display summary
cat /home/ubuntu/SETUP_COMPLETE.txt

log "============================================"
log "SETUP COMPLETE!"
log "============================================"
log ""
log "Dashboard URL: http://$PUBLIC_IP/"
log ""
log "Next: Upload your model files using SCP"
log "Then: ~/scripts/restart.sh"
log ""
log "View full setup details: cat ~/SETUP_COMPLETE.txt"
log "Check status: ~/scripts/status.sh"
log "============================================"
