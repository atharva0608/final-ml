# AWS Spot Optimizer

Complete AWS Spot Instance optimization system with intelligent decision engine and real-time monitoring dashboard.

## 🚀 Quick Start (EC2 Ubuntu)

```bash
git clone https://github.com/atharva0608/final-ml.git
cd final-ml
sudo bash setup.sh
```

**Access dashboard**: `http://YOUR_EC2_IP/`

## 📦 Repository Contents

```
final-ml/
├── backend.py              - Flask API (42 endpoints)
├── schema_cleaned.sql      - MySQL schema (19 tables)
├── demo-data.sql          - Demo data (3 clients, 8 agents)
├── setup.sh               - Automated deployment script
├── fix_mysql_permissions.sh - MySQL permissions utility
├── requirements.txt       - Python dependencies
└── frontend--main/        - React + Vite frontend
```

## ✨ Features

- **32 API Endpoints** - Complete backend coverage
- **Auto-Detection** - Frontend automatically finds backend
- **6 Admin Pages** - Overview, Clients, Agents, Instances, Savings, Health
- **Real-time Monitoring** - Agent health, pricing reports, notifications
- **File Upload System** - Decision engine & ML models
- **Demo Data** - Ready-to-test with sample data

## 🗄️ Database

**Schema**: 19 optimized tables
- `clients` - Client accounts
- `agents` - Agent instances
- `instances` - Instance history
- `switches` - Switch events
- `pricing_reports` - Pricing data
- And 14 more...

**Demo Accounts**:
- `demo@acme.com` - Token: `demo_token_acme_12345`
- `demo@startupxyz.com` - Token: `demo_token_startup_67890`
- `demo@betatester.com` - Token: `demo_token_beta_11111`

## 📋 Architecture

```
Frontend (React + Vite) → Nginx (Port 80) → Flask Backend (Port 5000) → MySQL 8.0 (Docker)
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

### View Logs
```bash
sudo journalctl -u spot-optimizer-backend -f
```

### Check Status
```bash
~/scripts/status.sh
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

## 📊 Tech Stack

- **Frontend**: React 18.2, Vite 5.0, Recharts, Lucide Icons
- **Backend**: Flask 3.0, Gunicorn, APScheduler
- **Database**: MySQL 8.0 (Docker)
- **Proxy**: Nginx with CORS
- **Deployment**: EC2 Ubuntu, Systemd

## ✅ Verification

After deployment:

```bash
# 1. Backend health
curl http://localhost:5000/health

# 2. Check database
docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SHOW TABLES FROM spot_optimizer;"

# 3. View backend logs
sudo journalctl -u spot-optimizer-backend -n 50

# 4. Check services
~/scripts/status.sh
```

## 🐛 Troubleshooting

### Backend Not Starting
```bash
sudo journalctl -u spot-optimizer-backend -n 100
```

### MySQL Permission Errors
```bash
bash fix_mysql_permissions.sh
```

### CORS Errors
```bash
curl -I http://localhost:5000/api/admin/stats
sudo nginx -t
```

### Frontend Can't Connect
Check browser console for API URL detection:
```
[API Config] Using BASE_URL: http://YOUR_EC2_IP:5000
```

## 🔐 Security

- MySQL only accessible from localhost
- Client tokens encrypted in database
- Nginx security headers enabled
- Systemd service with limited privileges
- Docker containers isolated in network

## 📄 License

Proprietary - Internal Use Only
