#!/bin/bash
###############################################################################
# CAST-AI Mini - Unified Installation Script
# Version: 3.0.0
# Description: Complete installation for agentless spot optimizer
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MYSQL_ROOT_PASSWORD="cast_ai_root_2025"
MYSQL_USER="spotuser"
MYSQL_PASSWORD="cast_ai_spot_2025"
MYSQL_DATABASE="spot_optimizer"
MYSQL_PORT="3306"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
DATABASE_DIR="$PROJECT_ROOT/database"

# Functions
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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_os() {
    if [[ ! -f /etc/os-release ]]; then
        print_error "Cannot detect OS. This script requires Ubuntu 24.04 LTS or compatible"
        exit 1
    fi

    . /etc/os-release
    if [[ "$ID" != "ubuntu" ]] || [[ "$VERSION_ID" != "24.04" ]]; then
        print_warning "This script is designed for Ubuntu 24.04 LTS"
        print_warning "Detected: $PRETTY_NAME"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

install_system_dependencies() {
    print_header "Installing System Dependencies"

    print_info "Updating package lists..."
    apt-get update -qq

    print_info "Installing base packages..."
    apt-get install -y -qq \
        curl \
        wget \
        git \
        build-essential \
        software-properties-common \
        apt-transport-https \
        ca-certificates \
        gnupg \
        lsb-release

    print_success "System dependencies installed"
}

install_docker() {
    print_header "Installing Docker"

    if command -v docker &> /dev/null; then
        print_warning "Docker already installed, skipping..."
        return
    fi

    print_info "Adding Docker GPG key..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    print_info "Adding Docker repository..."
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    print_info "Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    print_info "Starting Docker service..."
    systemctl start docker
    systemctl enable docker

    print_success "Docker installed and started"
}

install_python() {
    print_header "Installing Python 3.12"

    if command -v python3.12 &> /dev/null; then
        print_warning "Python 3.12 already installed, skipping..."
        return
    fi

    print_info "Installing Python 3.12 and pip..."
    apt-get install -y -qq python3.12 python3.12-venv python3-pip

    # Set Python 3.12 as default
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

    print_success "Python 3.12 installed"
}

install_nodejs() {
    print_header "Installing Node.js 20.x"

    if command -v node &> /dev/null; then
        NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [[ "$NODE_VERSION" -ge 20 ]]; then
            print_warning "Node.js 20.x already installed, skipping..."
            return
        fi
    fi

    print_info "Adding NodeSource repository..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -

    print_info "Installing Node.js..."
    apt-get install -y -qq nodejs

    print_success "Node.js $(node -v) installed"
}

install_nginx() {
    print_header "Installing Nginx"

    if command -v nginx &> /dev/null; then
        print_warning "Nginx already installed, skipping..."
        return
    fi

    print_info "Installing Nginx..."
    apt-get install -y -qq nginx

    print_info "Starting Nginx..."
    systemctl start nginx
    systemctl enable nginx

    print_success "Nginx installed and started"
}

setup_mysql() {
    print_header "Setting Up MySQL Database"

    # Check if container already exists
    if docker ps -a --format '{{.Names}}' | grep -q "^spot-mysql$"; then
        print_warning "MySQL container 'spot-mysql' already exists"
        read -p "Remove and recreate? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Removing existing container..."
            docker stop spot-mysql 2>/dev/null || true
            docker rm spot-mysql 2>/dev/null || true
        else
            print_info "Using existing MySQL container"
            return
        fi
    fi

    print_info "Starting MySQL container..."
    docker run --name spot-mysql \
        -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
        -e MYSQL_DATABASE="$MYSQL_DATABASE" \
        -e MYSQL_USER="$MYSQL_USER" \
        -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
        -p $MYSQL_PORT:3306 \
        --restart unless-stopped \
        -d mysql:8.0

    print_info "Waiting for MySQL to be ready (this may take 30-60 seconds)..."
    sleep 10

    # Wait for MySQL to be ready
    MAX_RETRIES=30
    RETRY_COUNT=0
    while ! docker exec spot-mysql mysqladmin ping -h localhost -u root -p"$MYSQL_ROOT_PASSWORD" --silent &> /dev/null; do
        RETRY_COUNT=$((RETRY_COUNT+1))
        if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
            print_error "MySQL failed to start within expected time"
            exit 1
        fi
        echo -n "."
        sleep 2
    done
    echo ""

    print_success "MySQL container started"

    # Import schema
    print_info "Importing database schema..."
    if [[ -f "$DATABASE_DIR/schema.sql" ]]; then
        docker exec -i spot-mysql mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE" < "$DATABASE_DIR/schema.sql"
        print_success "Database schema imported"
    else
        print_warning "Database schema file not found at $DATABASE_DIR/schema.sql"
        print_warning "You will need to import it manually later"
    fi
}

setup_backend() {
    print_header "Setting Up Backend"

    cd "$BACKEND_DIR"

    print_info "Creating Python virtual environment..."
    python3 -m venv venv

    print_info "Installing Python dependencies..."
    source venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    deactivate

    print_success "Backend dependencies installed"

    # Create .env if it doesn't exist
    if [[ ! -f "$BACKEND_DIR/.env" ]]; then
        print_info "Creating backend .env file from template..."
        if [[ -f "$BACKEND_DIR/.env.example" ]]; then
            cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"

            # Update with actual values
            sed -i "s/DB_HOST=.*/DB_HOST=localhost/" "$BACKEND_DIR/.env"
            sed -i "s/DB_PORT=.*/DB_PORT=$MYSQL_PORT/" "$BACKEND_DIR/.env"
            sed -i "s/DB_USER=.*/DB_USER=$MYSQL_USER/" "$BACKEND_DIR/.env"
            sed -i "s/DB_PASSWORD=.*/DB_PASSWORD=$MYSQL_PASSWORD/" "$BACKEND_DIR/.env"
            sed -i "s/DB_NAME=.*/DB_NAME=$MYSQL_DATABASE/" "$BACKEND_DIR/.env"

            print_warning "Backend .env created. Please update AWS credentials and TARGET_INSTANCE_ID:"
            print_warning "  nano $BACKEND_DIR/.env"
        else
            print_warning ".env.example not found. Please create .env manually"
        fi
    else
        print_warning "Backend .env already exists, skipping..."
    fi
}

setup_frontend() {
    print_header "Setting Up Frontend"

    cd "$FRONTEND_DIR"

    print_info "Installing Node.js dependencies..."
    npm install --silent

    print_info "Building frontend for production..."
    npm run build

    print_success "Frontend built successfully"

    # Deploy to nginx
    print_info "Deploying frontend to Nginx..."
    mkdir -p /var/www/spot-optimizer
    cp -r dist/* /var/www/spot-optimizer/
    chown -R www-data:www-data /var/www/spot-optimizer

    print_success "Frontend deployed to /var/www/spot-optimizer"
}

configure_nginx() {
    print_header "Configuring Nginx"

    NGINX_CONF="/etc/nginx/sites-available/spot-optimizer"

    print_info "Creating Nginx configuration..."
    cat > "$NGINX_CONF" <<'EOF'
server {
    listen 80;
    listen [::]:80;

    server_name _;

    root /var/www/spot-optimizer;
    index index.html;

    # Frontend
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;
}
EOF

    # Enable site
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/spot-optimizer

    # Remove default site if exists
    rm -f /etc/nginx/sites-enabled/default

    # Test configuration
    print_info "Testing Nginx configuration..."
    nginx -t

    print_info "Reloading Nginx..."
    systemctl reload nginx

    print_success "Nginx configured"
}

create_systemd_service() {
    print_header "Creating Systemd Service"

    SERVICE_FILE="/etc/systemd/system/spot-optimizer-backend.service"

    print_info "Creating backend service file..."
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=CAST-AI Mini Backend Service
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

    print_info "Reloading systemd daemon..."
    systemctl daemon-reload

    print_info "Enabling backend service..."
    systemctl enable spot-optimizer-backend

    print_success "Systemd service created and enabled"
    print_warning "Service will NOT start automatically during installation"
    print_warning "After configuring .env, start with: sudo systemctl start spot-optimizer-backend"
}

verify_installation() {
    print_header "Verifying Installation"

    # Check Docker
    if docker ps | grep -q spot-mysql; then
        print_success "MySQL container is running"
    else
        print_error "MySQL container is not running"
    fi

    # Check backend venv
    if [[ -d "$BACKEND_DIR/venv" ]]; then
        print_success "Backend virtual environment exists"
    else
        print_error "Backend virtual environment not found"
    fi

    # Check frontend build
    if [[ -d "/var/www/spot-optimizer" ]]; then
        print_success "Frontend deployed"
    else
        print_error "Frontend not deployed"
    fi

    # Check Nginx
    if systemctl is-active --quiet nginx; then
        print_success "Nginx is running"
    else
        print_error "Nginx is not running"
    fi

    # Check systemd service
    if systemctl is-enabled --quiet spot-optimizer-backend; then
        print_success "Backend service is enabled"
    else
        print_error "Backend service is not enabled"
    fi
}

print_next_steps() {
    print_header "Installation Complete!"

    echo ""
    print_info "Next Steps:"
    echo ""
    echo "  1. Configure AWS credentials (choose one):"
    echo "     - IAM instance profile (recommended if running on EC2)"
    echo "     - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
    echo "     - AWS credentials file: ~/.aws/credentials"
    echo ""
    echo "  2. Edit backend configuration:"
    echo "     nano $BACKEND_DIR/.env"
    echo ""
    echo "  3. Set TARGET_INSTANCE_ID in .env to the instance you want to manage"
    echo ""
    echo "  4. Start the backend service:"
    echo "     sudo systemctl start spot-optimizer-backend"
    echo ""
    echo "  5. Check service status:"
    echo "     sudo systemctl status spot-optimizer-backend"
    echo ""
    echo "  6. View logs:"
    echo "     sudo journalctl -u spot-optimizer-backend -f"
    echo ""
    echo "  7. Access dashboard:"
    echo "     http://$(hostname -I | awk '{print $1}')/"
    echo ""
    print_warning "Database Credentials:"
    echo "  Host: localhost:$MYSQL_PORT"
    echo "  Database: $MYSQL_DATABASE"
    echo "  User: $MYSQL_USER"
    echo "  Password: $MYSQL_PASSWORD"
    echo "  Root Password: $MYSQL_ROOT_PASSWORD"
    echo ""
    print_info "Documentation:"
    echo "  - Master Design Doc: $PROJECT_ROOT/docs/master-session-memory.md"
    echo "  - Architecture: $PROJECT_ROOT/docs/agentless-architecture.md"
    echo "  - README: $PROJECT_ROOT/README.md"
    echo ""
}

main() {
    print_header "CAST-AI Mini Installation Script v3.0.0"

    check_root
    check_os

    install_system_dependencies
    install_docker
    install_python
    install_nodejs
    install_nginx

    setup_mysql
    setup_backend
    setup_frontend
    configure_nginx
    create_systemd_service

    verify_installation
    print_next_steps
}

# Run main function
main
