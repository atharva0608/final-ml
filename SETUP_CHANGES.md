# Setup Script Changes - v3.2

## What's New in v3.2 (PERMISSION FIX)

This version specifically addresses critical permission issues discovered during production deployment:

### 🔧 Fixed: Docker Permission Denied Error
- **Problem**: After adding user to docker group, commands failed with "permission denied while trying to connect to the docker API"
- **Root Cause**: Group membership changes don't take effect until user logs out/in or uses `newgrp`
- **Solution**: Added group activation check after `usermod -aG docker ubuntu`
- **Impact**: Script can now continue without requiring logout/login

### 🔧 Fixed: MySQL InnoDB Permission Errors
- **Problem**: MySQL container couldn't write to `/var/lib/mysql` causing errors:
  - `[ERROR] [MY-012592] [InnoDB] Operating system error number 13`
  - `[ERROR] [MY-012595] [InnoDB] The error means mysqld does not have the access rights to the directory`
  - `[ERROR] [MY-012894] [InnoDB] Unable to open './#innodb_redo/#ib_redo9'`
- **Root Cause**: `mysql-data` directory was pre-created with ubuntu:ubuntu ownership (UID 1000), but MySQL container runs as mysql user (UID 999)
- **Solution**:
  - Removed pre-creation of `/home/ubuntu/mysql-data` directory
  - Added cleanup step before Docker run to remove old mysql-data
  - Let Docker create the directory automatically with proper ownership
- **Impact**: MySQL container now starts successfully without permission errors

## Overview
This document explains the changes made to the setup script to address permission handling, CORS errors, and proper integration with the frontend, backend, and database.

## Key Improvements

### 1. **Repository Structure Integration**
- **Old**: Tried to clone from a different GitHub repository
- **New**: Uses the actual repository structure where files already exist
- **Benefit**: No need to clone; works directly with your committed code

### 2. **Frontend Technology Update**
- **Old**: Assumed Create React App (CRA) with `npm run build` → `build/` directory
- **New**: Supports Vite + React with `npm run build` → `dist/` directory
- **Benefit**: Works with your modern Vite-based frontend

### 3. **Proper Permission Handling**
- **Old**: Set permissions after copying files, leading to access issues
- **New**: Creates directories with correct ownership from the start
- **Changes**:
  ```bash
  # Application directories owned by ubuntu
  sudo chown -R ubuntu:ubuntu $APP_DIR
  sudo chown -R ubuntu:ubuntu $MODELS_DIR
  sudo chown -R ubuntu:ubuntu $LOGS_DIR

  # Nginx root owned by www-data
  sudo chown -R www-data:www-data $NGINX_ROOT

  # Explicit permission fixing step at the end
  chmod -R 755 $BACKEND_DIR
  chmod +x $BACKEND_DIR/start_backend.sh
  ```
- **Benefit**: Eliminates "Permission denied" errors

### 4. **CORS Configuration - Fixed in Nginx**
- **Old**: Basic proxy configuration without CORS headers
- **New**: Comprehensive CORS support in Nginx with OPTIONS handling

#### CORS Headers Added:
```nginx
location /api/ {
    # CORS headers
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
    add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;

    # Handle preflight OPTIONS requests
    if ($request_method = 'OPTIONS') {
        add_header 'Access-Control-Allow-Origin' '*';
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS';
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization';
        add_header 'Access-Control-Max-Age' 1728000;
        add_header 'Content-Type' 'text/plain; charset=utf-8';
        add_header 'Content-Length' 0;
        return 204;
    }

    # ... proxy configuration
}
```

#### Health Check CORS:
```nginx
location /health {
    add_header 'Access-Control-Allow-Origin' '*' always;
    proxy_pass http://127.0.0.1:5000/health;
}
```

**Why This Matters**:
- Browser preflight requests (OPTIONS) are now properly handled
- All API endpoints return correct CORS headers
- Frontend can make cross-origin requests without errors
- Backend already has `CORS(app)` in backend.py, so double-layered protection

### 5. **Enhanced Nginx Buffer Configuration**
- **Old**: Default buffer sizes (could cause 502 errors with large API responses)
- **New**: Increased buffer sizes for large JSON responses
```nginx
proxy_buffer_size 128k;
proxy_buffers 4 256k;
proxy_busy_buffers_size 256k;
large_client_header_buffers 4 32k;
```
- **Benefit**: Handles large dashboard data and statistics without errors

### 6. **Dynamic API URL Configuration**
- **Old**: Hardcoded API URL in frontend
- **New**: Automatically updates API URL based on instance's public IP
```bash
sed -i "s|BASE_URL: '[^']*'|BASE_URL: 'http://$PUBLIC_IP:5000'|g" App.jsx
```
- **Benefit**: Frontend automatically connects to the correct backend

### 7. **Security Improvements**
- **Systemd Service Security**:
  ```ini
  NoNewPrivileges=true
  PrivateTmp=true
  ```
- **Proper User/Group Assignment**:
  ```ini
  User=ubuntu
  Group=ubuntu
  ```
- **Environment Isolation**: Virtual environment for Python dependencies

### 8. **Better Error Handling**
- **IMDSv2 Support**: Proper AWS metadata token handling
- **Fallback Mechanisms**: Multiple methods to get public IP
- **MySQL Readiness Checks**: Waits for authentication to be ready, not just container start
- **Non-interactive Mode**: Added `DEBIAN_FRONTEND=noninteractive` to prevent package installation hangs

### 9. **File Structure Mapping**

#### Your Repository Structure:
```
final-ml/
├── backend.py          # Flask application
├── schema.sql          # MySQL schema
├── setup.sh            # Old setup script
├── setup-updated.sh    # New setup script (THIS FILE)
└── frontend/           # Cloned from https://github.com/atharva0608/frontend-.git
    ├── App.jsx
    ├── package.json
    ├── vite.config.js
    └── src/
```

#### Deployment Structure (on EC2):
```
/home/ubuntu/
├── spot-optimizer/          # Main application directory
│   ├── backend/
│   │   ├── backend.py       # Copied from repo
│   │   ├── venv/            # Python virtual environment
│   │   ├── requirements.txt # Auto-generated
│   │   ├── .env             # Configuration
│   │   └── start_backend.sh # Startup script
│   └── frontend/
│       ├── App.jsx          # Copied from repo
│       ├── package.json     # From repo
│       ├── node_modules/    # Installed by npm
│       └── dist/            # Build output (Vite)
├── production_models/       # ML models directory
├── logs/                    # Application logs
├── scripts/                 # Helper scripts
│   ├── start.sh
│   ├── stop.sh
│   ├── status.sh
│   ├── restart.sh
│   └── logs.sh
└── mysql-data/              # MySQL Docker volume
```

### 10. **Installation Flow**

1. **System Setup** → Install Docker, Node.js, Python
2. **MySQL Setup** → Run Docker container, wait for readiness
3. **Import Schema** → Load schema.sql from repository
4. **Backend Setup** → Copy backend.py, create venv, install dependencies
5. **Frontend Setup** → Copy frontend/, install npm packages, build with Vite
6. **Nginx Config** → Set up reverse proxy with CORS headers
7. **Systemd Service** → Create and enable backend service
8. **Helper Scripts** → Create management scripts
9. **Permissions Fix** → Ensure all files have correct ownership
10. **Start Services** → Launch backend and verify health

## Usage Instructions

### Running the New Setup Script

```bash
# Make sure you're in the repository root
cd /home/ubuntu/final-ml

# Run the updated setup script
sudo bash setup-updated.sh
```

### Post-Installation

```bash
# Check service status
~/scripts/status.sh

# View backend logs
sudo journalctl -u spot-optimizer-backend -f

# Restart all services
~/scripts/restart.sh

# View specific logs
~/scripts/logs.sh
```

### Accessing the Application

- **Frontend**: http://YOUR_EC2_PUBLIC_IP/
- **Backend API**: http://YOUR_EC2_PUBLIC_IP/api/admin/stats
- **Health Check**: http://YOUR_EC2_PUBLIC_IP/health

## Troubleshooting

### CORS Errors
If you still see CORS errors:
1. Check Nginx config: `sudo nginx -t`
2. View Nginx error log: `sudo tail -f /var/log/nginx/spot-optimizer.error.log`
3. Verify CORS headers: `curl -I http://YOUR_IP/health`

### Permission Denied Errors
```bash
# Fix all permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/spot-optimizer
sudo chown -R www-data:www-data /var/www/spot-optimizer
sudo chmod +x /home/ubuntu/spot-optimizer/backend/start_backend.sh
```

### Backend Won't Start
```bash
# Check logs
sudo journalctl -u spot-optimizer-backend -n 100

# Check if MySQL is ready
docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SELECT 1;" spot_optimizer

# Manually test backend
cd /home/ubuntu/spot-optimizer/backend
source venv/bin/activate
python backend.py
```

### Frontend Not Loading
```bash
# Check Nginx status
sudo systemctl status nginx

# Test Nginx config
sudo nginx -t

# Check if files exist
ls -la /var/www/spot-optimizer/

# Rebuild frontend
cd /home/ubuntu/spot-optimizer/frontend
npm run build
sudo cp -r dist/* /var/www/spot-optimizer/
```

## Comparison: Old vs New Setup Script

| Feature | Old Setup (v2.1) | Setup v3.0 | Setup v3.2 (Current) |
|---------|------------------|------------|----------------------|
| Frontend Framework | Create React App | Vite + React | Vite + React |
| Build Directory | build/ | dist/ | dist/ |
| Repository Cloning | Clone external repo | Use existing files | Auto-clone from GitHub |
| CORS Support | Partial (backend only) | Full (backend + nginx) | Full (backend + nginx) |
| Permission Handling | After file copy | Before file operations | Before + Docker group fix |
| MySQL Data Directory | ubuntu:ubuntu owned | ubuntu:ubuntu owned | Docker auto-creates (mysql:mysql) |
| Docker Group Activation | Manual logout/login | Manual logout/login | Automatic in-script |
| Nginx Buffers | Default (small) | Enhanced (128k-256k) | Enhanced (128k-256k) |
| API URL Config | Hardcoded | Dynamic (auto-detect IP) | Dynamic (auto-detect IP) |
| Error Handling | Basic | Comprehensive | Comprehensive + Permission fixes |
| Security | Basic | Enhanced (systemd sandboxing) | Enhanced (systemd sandboxing) |
| MySQL Wait | Simple ping | Auth readiness check | Auth readiness check |

## Additional Notes

### Why CORS in Both Backend and Nginx?
- **Backend CORS (Flask-CORS)**: Handles direct API calls (port 5000)
- **Nginx CORS**: Handles proxied requests through Nginx (port 80)
- This provides defense-in-depth and ensures CORS works in all scenarios

### Why Vite Instead of CRA?
- Your frontend repository uses Vite (modern, faster build tool)
- The old script assumed Create React App (older, slower)
- Vite outputs to `dist/` while CRA outputs to `build/`
- This change is critical for deployment to work

### Database Schema
The schema.sql file is comprehensive with:
- 25+ tables for spot optimizer functionality
- Stored procedures for common operations
- Views for dashboard queries
- Events for automated maintenance
- Full RBAC and audit logging

## Testing the Setup

After running the script, verify:

```bash
# 1. Check all services are running
~/scripts/status.sh

# 2. Test backend health
curl http://localhost:5000/health

# 3. Test frontend is served
curl -I http://localhost/

# 4. Test CORS headers
curl -I http://localhost/api/admin/stats

# 5. Test database connection
docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SHOW TABLES;" spot_optimizer
```

## Summary of Fixes

### v3.0 Improvements
✅ **Permission Handling**: All directories created with correct ownership from start
✅ **CORS Configuration**: Complete CORS support in Nginx with OPTIONS handling
✅ **Nginx Buffers**: Increased to handle large API responses
✅ **Frontend Build**: Updated for Vite (dist/ instead of build/)
✅ **API URL**: Dynamically configured based on instance IP
✅ **Repository Structure**: Works with existing file layout
✅ **Error Handling**: Improved checks for MySQL readiness
✅ **Security**: Enhanced systemd service with security options
✅ **Documentation**: Comprehensive setup summary and helper scripts

### v3.2 Critical Fixes
✅ **Docker Group Permissions**: Fixed "permission denied" error when running docker commands
✅ **MySQL Data Directory**: Fixed InnoDB permission errors by letting Docker manage directory ownership
✅ **Auto-Cleanup**: Removes conflicting mysql-data directory before container creation
✅ **Production Tested**: All permission issues resolved and verified in production environment

The setup script is now fully production-ready and addresses all discovered issues!
