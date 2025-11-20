# AWS Spot Optimizer - Production Ready

Complete AWS Spot Instance optimization system with intelligent decision engine and real-time monitoring dashboard.

## 🚀 Quick Start

```bash
# On EC2 Ubuntu instance:
git clone https://github.com/atharva0608/final-ml.git
cd final-ml
sudo bash setup.sh
```

Access dashboard at: `http://YOUR_EC2_IP/`

## 📦 Repository Contents

### Production Files

| File | Description | Size |
|------|-------------|------|
| `backend.py` | Flask backend with 42 endpoints | 85KB |
| `schema_cleaned.sql` | MySQL schema v6.0 (19 tables) | 28KB |
| `demo-data.sql` | Comprehensive test data v2.0 | 37KB |
| `setup.sh` | Complete deployment script | 38KB |
| `fix_mysql_permissions.sh` | MySQL permissions utility | 1.6KB |

### Documentation

| File | Description |
|------|-------------|
| `README.md` | This file - quick reference |
| `COMPLETE_IMPLEMENTATION_GUIDE.md` | **Master guide** - all problems & solutions |

## 🌟 Features

✅ **32 API Endpoints** - Complete backend coverage
✅ **Auto-Detection** - Frontend automatically finds backend
✅ **6-Tab Client Dashboard** - Overview, Agents, Instances, Savings, Models, History
✅ **Real-time Monitoring** - Agent health, pricing reports, notifications
✅ **File Upload System** - Decision engine & ML models
✅ **Demo Data** - 3 clients, 8 agents, 35 pricing reports

## 🗄️ Database

**Schema v6.0**: 19 optimized tables (removed 6 unused tables from original schema)

**Demo Accounts**:
- `demo@acme.com` - Token: `demo_token_acme_12345`
- `demo@startupxyz.com` - Token: `demo_token_startup_67890`
- `demo@betatester.com` - Token: `demo_token_beta_11111`

## 📋 Architecture

```
Frontend (React + Vite)
    ↓
Nginx (Port 80) + CORS
    ↓
Flask Backend (Port 5000)
    ↓
MySQL 8.0 (Docker, Port 3306)
```

## 🛠️ Helper Scripts

After deployment, use these scripts in `/home/ubuntu/scripts/`:

```bash
~/scripts/start.sh       # Start all services
~/scripts/stop.sh        # Stop services
~/scripts/status.sh      # Check service status
~/scripts/restart.sh     # Restart everything
~/scripts/logs.sh        # View logs (interactive)
```

## 🔧 Management

### Update Code

```bash
cd /home/ubuntu/final-ml
git pull origin main
sudo systemctl restart spot-optimizer-backend
```

### Fix MySQL Permissions

```bash
bash fix_mysql_permissions.sh
```

### View Backend Logs

```bash
sudo journalctl -u spot-optimizer-backend -f
```

### Check Service Status

```bash
~/scripts/status.sh
```

## 📊 Tech Stack

- **Frontend**: React 18.2, Vite 5.0, Recharts, Lucide Icons
- **Backend**: Flask 3.0, Gunicorn, APScheduler
- **Database**: MySQL 8.0 (Docker)
- **Proxy**: Nginx with CORS
- **Deployment**: EC2 Ubuntu, Systemd

## 📖 Documentation

### Master Guide

👉 **[COMPLETE_IMPLEMENTATION_GUIDE.md](COMPLETE_IMPLEMENTATION_GUIDE.md)** 👈

**Contains**:
- Complete feature list
- All 10 problems encountered & their solutions
- All 32 API endpoint specifications
- Database schema details
- Demo data requirements
- Testing checklist
- Deployment guide

### Quick Links

- [Frontend Repository](https://github.com/atharva0608/frontend-.git)
- [Backend Repository](https://github.com/atharva0608/final-ml.git)

## ✅ Verification

After deployment, verify:

1. **Backend Health**:
   ```bash
   curl http://localhost:5000/health
   # Should return: {"status": "healthy", "database": "connected", ...}
   ```

2. **Frontend Access**:
   - Open `http://YOUR_EC2_IP/`
   - Dashboard should load with stats
   - No errors in browser console

3. **Models Page** (Critical):
   - Navigate to any client → Models tab
   - All agents should show **"HEALTHY"** status
   - Indicates pricing reports are working correctly

4. **Database**:
   ```bash
   docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SELECT COUNT(*) FROM spot_optimizer.pricing_reports WHERE collected_at >= DATE_SUB(NOW(), INTERVAL 10 MINUTE);"
   # Should return ≥35
   ```

## 🐛 Troubleshooting

### Backend Not Starting

```bash
# Check logs
sudo journalctl -u spot-optimizer-backend -n 100

# Common issues:
# - MySQL not ready (wait longer)
# - Missing Python dependencies (check requirements.txt)
# - Wrong file paths (check systemd config)
```

### Frontend Can't Connect

```bash
# Check auto-detection in browser console
# Should see: [API Config] Using BASE_URL: http://YOUR_EC2_IP:5000

# If not, rebuild frontend:
cd /home/ubuntu/final-ml/frontend
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build
sudo cp -r dist/* /var/www/spot-optimizer/
```

### MySQL Permission Errors

```bash
# Use utility script
bash fix_mysql_permissions.sh

# Manual fix
sudo chown -R 999:999 /home/ubuntu/mysql-data
docker restart spot-mysql
```

### CORS Errors

```bash
# Test CORS headers
curl -I http://localhost:5000/api/admin/stats
# Should have: Access-Control-Allow-Origin: *

# If not, check Nginx config
sudo nginx -t
sudo systemctl restart nginx
```

## 📝 What's New

### Latest Changes (2024-11-20)

✅ **Repository Cleanup**:
- Removed 6 outdated documentation files
- Removed old schema.sql (use schema_cleaned.sql)
- Single consolidated guide (COMPLETE_IMPLEMENTATION_GUIDE.md)

✅ **All Issues Fixed**:
- API URL auto-detection working
- MySQL permissions correct from setup
- All 32 endpoints implemented
- CORS properly configured
- Demo data comprehensive

✅ **Production Ready**:
- Single `setup.sh` script (no versions)
- Clean schema (19 tables)
- Complete demo data (all features testable)
- Full documentation

## 🔐 Security

- MySQL only accessible from localhost
- Client tokens encrypted in database
- Nginx security headers enabled
- Systemd service with limited privileges
- Docker containers isolated in network

## 📄 License

Proprietary - Internal Use Only

---

**Repository Status**: ✅ Production Ready

For complete details, see [COMPLETE_IMPLEMENTATION_GUIDE.md](COMPLETE_IMPLEMENTATION_GUIDE.md)
