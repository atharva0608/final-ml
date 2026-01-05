# Deployment Scripts - Component Information

> **Last Updated**: 2026-01-02 13:00:00
> **Maintainer**: LLM Agent

## Folder Purpose
Deployment and server setup automation scripts for Spot Optimizer platform.

## Implemented Scripts

| File Name | Purpose | Lines | Status |
|-----------|---------|-------|--------|
| deploy.sh | Automated deployment | ~300 | ✅ Implemented |
| setup.sh | Initial server setup | ~400 | ✅ Implemented |

## Features

### deploy.sh
- Pull latest code from git repository
- Automated database backup (7-day retention)
- Docker image building
- Database migration execution (Alembic)
- Service startup with docker-compose
- Comprehensive health checks (backend, frontend, DB, Redis)
- Cleanup of old Docker images

### setup.sh
- OS detection (Ubuntu, Debian, CentOS, RHEL)
- Docker and Docker Compose installation
- Firewall configuration (UFW/firewalld)
- SSL certificate setup with Let's Encrypt
- System limits configuration
- Systemd service creation
- Log rotation setup

## Usage

### Initial Setup
```bash
sudo ./setup.sh
# OR with domain
sudo DOMAIN_NAME=example.com EMAIL=admin@example.com ./setup.sh
```

### Deploy Application
```bash
./deploy.sh
```

## Dependencies
- Docker and docker-compose
- git
- bash
- curl (for health checks)
- certbot (for SSL)
