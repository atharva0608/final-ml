# AWS Spot Optimizer - Complete Setup

Complete infrastructure for managing AWS Spot Instances with intelligent decision engine and real-time monitoring.

## 🚀 Quick Start

```bash
# On your EC2 instance:
sudo bash setup.sh
```

That's it! The script handles everything automatically:
- ✅ Clones both backend and frontend repositories
- ✅ Sets up MySQL 8.0 in Docker with proper permissions
- ✅ Installs Flask 3.0 backend with all endpoints
- ✅ Builds Vite React frontend with API auto-detection
- ✅ Configures Nginx reverse proxy with CORS
- ✅ Creates systemd services
- ✅ Imports schema and demo data
- ✅ Starts all services

## 📦 What's Included

### Core Scripts

- **`setup.sh`** - Master deployment script (single source of truth)
- **`fix_mysql_permissions.sh`** - Utility to fix Docker MySQL permissions

### Database Files

- **`schema_cleaned.sql`** (v6.0) - Optimized database schema (19 tables)
- **`schema.sql`** (v5.1) - Original schema (25 tables) - deprecated
- **`demo-data.sql`** (v2.0) - Comprehensive test data with:
  - 3 demo clients
  - 8 agents (7 online, 1 offline)
  - 35 pricing reports (last 10 minutes)
  - 12 spot pools
  - ~576 price snapshots (48 hours history)
  - 40 agent decisions
  - Full working dashboard data

### Documentation

- **`SETUP_V6_API_AUTO_DETECTION.md`** - API auto-detection guide
- **`ENDPOINT_AND_SCHEMA_UPDATES.md`** - API endpoint documentation
- **`FRONTEND_IMPLEMENTATION_STATUS.md`** - Frontend feature status
- **`SETUP_CHANGES.md`** - Historical setup changes

## 🏗️ Architecture

### Backend
- **Framework:** Flask 3.0
- **Database:** MySQL 8.0 (Docker)
- **API:** RESTful with full CORS support
- **Server:** Gunicorn with 4 workers + threading
- **Repository:** https://github.com/atharva0608/final-ml.git

### Frontend
- **Framework:** React 18.2 + Vite 5.0
- **UI:** Lucide icons + Recharts
- **API Detection:** Automatic runtime URL detection
- **Repository:** https://github.com/atharva0608/frontend-.git

### Infrastructure
- **Reverse Proxy:** Nginx with CORS headers
- **Process Manager:** systemd
- **Container:** Docker for MySQL
- **Deployment:** EC2 (Ubuntu 20.04/22.04)

## 🌟 Key Features

### API URL Auto-Detection
The frontend **automatically detects** the backend URL at runtime:

```javascript
// Development: localhost:3000 → Connects to localhost:5000
// Production: EC2_IP:80 → Connects to EC2_IP:5000
// No hardcoded IPs needed!
```

Benefits:
- ✅ No manual IP configuration
- ✅ Works on any EC2 instance
- ✅ Supports local development
- ✅ Environment variable override available

### Complete API Endpoints

**Global Admin:**
- `GET /api/admin/stats` - Global statistics
- `GET /api/admin/clients` - All clients list
- `GET /api/admin/instances` - All instances (with filters)
- `GET /api/admin/agents` - All agents across clients
- `GET /api/admin/system-health` - System health metrics
- `GET /api/admin/activity` - Recent activity feed
- `GET /api/admin/clients/growth` - Client growth data

**Client Management:**
- `GET /api/client/{id}` - Client details
- `GET /api/client/{id}/agents` - Client agents
- `GET /api/client/{id}/instances` - Client instances
- `GET /api/client/{id}/savings` - Savings calculations
- `GET /api/client/{id}/stats/charts` - Dashboard charts
- `GET /api/client/{id}/switch-history` - Instance switches
- `GET /api/client/{id}/agents/decisions` - Agent decisions

**Instance Management:**
- `GET /api/client/instances/{id}/pricing` - Instance pricing
- `GET /api/client/instances/{id}/price-history` - Historical prices
- `GET /api/client/instances/{id}/available-options` - Switch options
- `POST /api/client/instances/{id}/force-switch` - Manual switch

**File Uploads:**
- `POST /api/admin/decision-engine/upload` - Decision engine files
- `POST /api/admin/ml-models/upload` - ML model files

### Schema Optimization

**v6.0 Cleaned Schema:**
- ✅ 19 active tables (down from 25)
- ✅ Removed 6 unused tables
- ✅ Removed 3 unused views
- ✅ Removed 11 unused procedures
- ✅ Removed 4 MySQL events
- ✅ Better performance
- ✅ Easier maintenance

## 📁 Repository Structure

```
final-ml/
├── setup.sh                          # Master setup script
├── fix_mysql_permissions.sh          # MySQL permissions utility
├── backend.py                        # Flask backend application
├── schema_cleaned.sql                # Database schema v6.0
├── demo-data.sql                     # Test data v2.0
├── src_config_api.jsx                # Frontend API config template
└── docs/
    ├── SETUP_V6_API_AUTO_DETECTION.md
    ├── ENDPOINT_AND_SCHEMA_UPDATES.md
    └── FRONTEND_IMPLEMENTATION_STATUS.md
```

## 🔧 Helper Scripts

After installation, these scripts are available at `/home/ubuntu/scripts/`:

```bash
~/scripts/start.sh      # Start all services
~/scripts/stop.sh       # Stop services
~/scripts/status.sh     # Check service status
~/scripts/restart.sh    # Restart everything
~/scripts/logs.sh       # View logs (interactive menu)
```

## 📊 Demo Data

The demo-data.sql provides complete test data:

**Demo Accounts:**
- **demo@acme.com** (Enterprise) - `token: demo_token_acme_12345`
- **demo@startupxyz.com** (Professional) - `token: demo_token_startup_67890`
- **demo@betatester.com** (Free) - `token: demo_token_beta_11111`

**Included Data:**
- 35 pricing reports (last 10 minutes) - ensures Models view shows "HEALTHY"
- 8 agents across 3 clients
- 12 spot pools in ap-south-1 and us-east-1
- 48 hours of price history
- 40 agent decisions with reasoning
- 5 switch events with timing data
- Monthly savings summaries
- 90 days growth data

## 🚀 Deployment

### Fresh Installation

```bash
# On EC2 Ubuntu instance:
git clone https://github.com/atharva0608/final-ml.git
cd final-ml
sudo bash setup.sh
```

### Update Existing Deployment

```bash
cd /home/ubuntu/final-ml
git pull origin main
sudo bash setup.sh
```

### Manual Updates

```bash
# Update backend code
cd /home/ubuntu/final-ml
git pull origin main
sudo systemctl restart spot-optimizer-backend

# Rebuild frontend
cd /home/ubuntu/final-ml/frontend
git pull origin main
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build
sudo rm -rf /var/www/spot-optimizer/*
sudo cp -r dist/* /var/www/spot-optimizer/
sudo chown -R www-data:www-data /var/www/spot-optimizer
```

## 🔍 Troubleshooting

### Backend Not Starting

```bash
# Check logs
sudo journalctl -u spot-optimizer-backend -n 100

# Verify database connection
docker exec spot-mysql mysql -u spotuser -pSpotUser2024! spot_optimizer -e "SELECT 1;"

# Check Python errors
cd /home/ubuntu/spot-optimizer/backend
source venv/bin/activate
python backend.py
```

### MySQL Permission Errors

```bash
# Fix with utility script
cd /home/ubuntu/final-ml
bash fix_mysql_permissions.sh

# Manual fix
sudo chown -R 999:999 /home/ubuntu/mysql-data
docker restart spot-mysql
```

### Frontend Can't Connect to Backend

```bash
# Check backend is running
curl http://localhost:5000/health

# Check CORS headers
curl -I http://localhost:5000/api/admin/stats

# Verify Nginx config
sudo nginx -t
```

### API URL Not Auto-Detecting

```bash
# Force environment variable during build
cd /home/ubuntu/final-ml/frontend
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build
sudo cp -r dist/* /var/www/spot-optimizer/
```

## 📝 Environment Variables

### Backend (.env)

```bash
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=spotuser
DB_PASSWORD=SpotUser2024!
DB_NAME=spot_optimizer
HOST=0.0.0.0
PORT=5000
DEBUG=False
```

### Frontend (Build-time)

```bash
VITE_API_URL=http://YOUR_EC2_IP:5000  # Optional - defaults to auto-detection
```

## 🔒 Security Notes

- Database credentials are in `.env` (not committed to git)
- MySQL is only accessible from localhost
- Backend API has CORS properly configured
- Nginx adds security headers
- Systemd service runs with limited privileges
- Docker containers are isolated in dedicated network

## 📚 Additional Resources

- [API Auto-Detection Guide](SETUP_V6_API_AUTO_DETECTION.md)
- [Endpoint Documentation](ENDPOINT_AND_SCHEMA_UPDATES.md)
- [Frontend Status](FRONTEND_IMPLEMENTATION_STATUS.md)

## 🤝 Contributing

1. Make changes to your fork
2. Test with `setup.sh` on clean EC2 instance
3. Submit PR with description

## 📄 License

Proprietary - Internal Use Only

## 🆘 Support

For issues or questions:
- Check the troubleshooting section above
- Review logs: `~/scripts/logs.sh`
- Verify setup: `~/scripts/status.sh`
- Check documentation in `/home/user/final-ml/docs/`

---

**Last Updated:** 2024-11-20
**Setup Script Version:** Master (single source of truth)
**Schema Version:** v6.0 (cleaned and optimized)
**Demo Data Version:** v2.0 (comprehensive test data)
