#!/bin/bash
# Spot Optimizer - Initial Server Setup Script
# This script prepares a fresh server for running Spot Optimizer

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
DOMAIN_NAME="${DOMAIN_NAME:-}"  # Optional: Set via environment variable
EMAIL="${EMAIL:-admin@example.com}"  # For SSL certificates

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

# Detect OS
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        VER=$VERSION_ID
    else
        log_error "Cannot detect OS. /etc/os-release not found."
        exit 1
    fi

    log_info "Detected OS: $OS $VER"
}

# Update system packages
update_system() {
    log_info "Updating system packages..."

    case $OS in
        ubuntu|debian)
            apt-get update -y
            apt-get upgrade -y
            apt-get install -y \
                apt-transport-https \
                ca-certificates \
                curl \
                gnupg \
                lsb-release \
                software-properties-common \
                git \
                wget \
                unzip \
                htop \
                vim
            ;;
        centos|rhel|fedora)
            yum update -y
            yum install -y \
                ca-certificates \
                curl \
                gnupg \
                git \
                wget \
                unzip \
                htop \
                vim
            ;;
        *)
            log_error "Unsupported OS: $OS"
            exit 1
            ;;
    esac

    log_success "System packages updated"
}

# Install Docker
install_docker() {
    if command_exists docker; then
        log_info "Docker is already installed"
        docker --version
        return 0
    fi

    log_info "Installing Docker..."

    case $OS in
        ubuntu|debian)
            # Add Docker's official GPG key
            curl -fsSL https://download.docker.com/linux/$OS/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

            # Set up the repository
            echo \
              "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/$OS \
              $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

            # Install Docker Engine
            apt-get update -y
            apt-get install -y docker-ce docker-ce-cli containerd.io
            ;;
        centos|rhel)
            yum install -y yum-utils
            yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            yum install -y docker-ce docker-ce-cli containerd.io
            ;;
        *)
            log_error "Unsupported OS for Docker installation: $OS"
            exit 1
            ;;
    esac

    # Start and enable Docker
    systemctl start docker
    systemctl enable docker

    log_success "Docker installed successfully"
    docker --version
}

# Install Docker Compose
install_docker_compose() {
    if command_exists docker-compose; then
        log_info "Docker Compose is already installed"
        docker-compose --version
        return 0
    fi

    log_info "Installing Docker Compose..."

    # Download latest version
    DOCKER_COMPOSE_VERSION="2.24.0"
    curl -L "https://github.com/docker/compose/releases/download/v${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose

    # Make executable
    chmod +x /usr/local/bin/docker-compose

    # Create symbolic link
    ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

    log_success "Docker Compose installed successfully"
    docker-compose --version
}

# Configure firewall
configure_firewall() {
    log_info "Configuring firewall..."

    if command_exists ufw; then
        # Ubuntu/Debian firewall
        ufw --force enable
        ufw default deny incoming
        ufw default allow outgoing
        ufw allow ssh
        ufw allow 80/tcp   # HTTP
        ufw allow 443/tcp  # HTTPS
        ufw allow 8000/tcp # Backend API
        ufw allow 3000/tcp # Frontend (dev)
        ufw --force reload
        log_success "UFW firewall configured"
    elif command_exists firewall-cmd; then
        # CentOS/RHEL firewall
        systemctl start firewalld
        systemctl enable firewalld
        firewall-cmd --permanent --add-service=ssh
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --permanent --add-port=8000/tcp
        firewall-cmd --permanent --add-port=3000/tcp
        firewall-cmd --reload
        log_success "firewalld configured"
    else
        log_warning "No firewall found. Please configure manually."
    fi
}

# Setup project directory
setup_project_directory() {
    log_info "Setting up project directory..."

    # Create project directory
    mkdir -p "$PROJECT_DIR"

    # Clone repository (if not exists)
    if [ ! -d "$PROJECT_DIR/.git" ]; then
        log_info "Cloning repository..."
        # Note: Replace with actual repository URL
        log_warning "Repository URL not specified. Please clone manually:"
        log_warning "  git clone <your-repo-url> $PROJECT_DIR"
    else
        log_info "Repository already cloned"
    fi

    # Create data directories
    mkdir -p "$PROJECT_DIR/data/postgres"
    mkdir -p "$PROJECT_DIR/data/redis"
    mkdir -p /var/backups/spot-optimizer
    mkdir -p /var/log/spot-optimizer

    log_success "Project directory configured"
}

# Setup SSL certificates with Let's Encrypt
setup_ssl() {
    if [ -z "$DOMAIN_NAME" ]; then
        log_warning "DOMAIN_NAME not set. Skipping SSL setup."
        log_warning "To setup SSL later, run: certbot --nginx -d your-domain.com"
        return 0
    fi

    log_info "Setting up SSL certificates for $DOMAIN_NAME..."

    # Install Certbot
    case $OS in
        ubuntu|debian)
            apt-get install -y certbot python3-certbot-nginx
            ;;
        centos|rhel)
            yum install -y certbot python3-certbot-nginx
            ;;
    esac

    # Obtain certificate
    certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos -m "$EMAIL" || {
        log_warning "SSL certificate setup failed. You may need to configure DNS first."
        return 0
    }

    # Setup auto-renewal
    crontab -l 2>/dev/null | { cat; echo "0 12 * * * /usr/bin/certbot renew --quiet"; } | crontab -

    log_success "SSL certificates configured"
}

# Setup environment file
setup_environment() {
    log_info "Setting up environment configuration..."

    ENV_FILE="$PROJECT_DIR/.env"

    if [ -f "$ENV_FILE" ]; then
        log_info ".env file already exists"
        return 0
    fi

    # Copy example env file
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
        log_success "Environment file created from template"
        log_warning "Please edit $ENV_FILE with your actual configuration"
    else
        log_warning ".env.example not found. Please create .env manually"
    fi
}

# Configure system limits
configure_system_limits() {
    log_info "Configuring system limits..."

    # Increase file descriptor limits for Docker
    cat >> /etc/security/limits.conf <<EOF
*               soft    nofile          65536
*               hard    nofile          65536
root            soft    nofile          65536
root            hard    nofile          65536
EOF

    # Increase vm.max_map_count for Elasticsearch (if needed)
    sysctl -w vm.max_map_count=262144
    echo "vm.max_map_count=262144" >> /etc/sysctl.conf

    log_success "System limits configured"
}

# Create systemd service for auto-start
create_systemd_service() {
    log_info "Creating systemd service for auto-start..."

    cat > /etc/systemd/system/spot-optimizer.service <<EOF
[Unit]
Description=Spot Optimizer Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/local/bin/docker-compose -f $PROJECT_DIR/docker/docker-compose.yml up -d
ExecStop=/usr/local/bin/docker-compose -f $PROJECT_DIR/docker/docker-compose.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable spot-optimizer.service

    log_success "Systemd service created and enabled"
}

# Setup log rotation
setup_log_rotation() {
    log_info "Configuring log rotation..."

    cat > /etc/logrotate.d/spot-optimizer <<EOF
/var/log/spot-optimizer/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
    sharedscripts
}
EOF

    log_success "Log rotation configured"
}

# Display summary
display_summary() {
    echo ""
    log_success "========================================="
    log_success "  Server Setup Completed Successfully!"
    log_success "========================================="
    echo ""
    log_info "Next steps:"
    echo ""
    echo "  1. Edit environment configuration:"
    echo "     vim $PROJECT_DIR/.env"
    echo ""
    echo "  2. Deploy the application:"
    echo "     $PROJECT_DIR/scripts/deployment/deploy.sh"
    echo ""
    echo "  3. Check service status:"
    echo "     systemctl status spot-optimizer"
    echo ""
    if [ -n "$DOMAIN_NAME" ]; then
        echo "  4. Access the application:"
        echo "     https://$DOMAIN_NAME"
    else
        echo "  4. Access the application:"
        echo "     http://$(hostname -I | awk '{print $1}'):8000 (Backend)"
        echo "     http://$(hostname -I | awk '{print $1}'):3000 (Frontend)"
    fi
    echo ""
    log_warning "Remember to:"
    log_warning "  - Configure .env with actual credentials"
    log_warning "  - Setup DNS records if using custom domain"
    log_warning "  - Review firewall rules for production"
    log_warning "  - Enable automatic backups"
    echo ""
}

# Main setup function
main() {
    log_info "========================================="
    log_info "  Spot Optimizer Server Setup"
    log_info "========================================="
    echo ""

    # Check if running as root
    check_root

    # Detect OS
    detect_os

    # Update system
    update_system

    # Install Docker
    install_docker

    # Install Docker Compose
    install_docker_compose

    # Configure firewall
    configure_firewall

    # Setup project directory
    setup_project_directory

    # Setup environment
    setup_environment

    # Configure system limits
    configure_system_limits

    # Create systemd service
    create_systemd_service

    # Setup log rotation
    setup_log_rotation

    # Setup SSL (if domain provided)
    setup_ssl

    # Display summary
    display_summary
}

# Run main function
main "$@"
