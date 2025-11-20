# AWS Spot Optimizer - Backend

Minimal AWS Spot Instance optimization backend with Flask API and MySQL database.

## 📦 Files

- `backend.py` - Flask backend with 42 API endpoints (85KB)
- `schema.sql` - MySQL database schema with 23 tables (53KB)
- `demo-data.sql` - Demo data with 3 clients and 8 agents (24KB)
- `setup.sh` - Automated deployment script for EC2 Ubuntu
- `requirements.txt` - Python dependencies

## 🚀 Quick Start (EC2 Ubuntu)

```bash
git clone https://github.com/atharva0608/final-ml.git
cd final-ml
sudo bash setup.sh
```

## 📋 Manual Setup

### 1. MySQL Database

```bash
# Start MySQL Docker container
docker run -d \
  --name spot-mysql \
  -e MYSQL_ROOT_PASSWORD=rootpassword \
  -e MYSQL_DATABASE=spot_optimizer \
  -e MYSQL_USER=spotuser \
  -e MYSQL_PASSWORD=SpotUser2024! \
  -p 3306:3306 \
  mysql:8.0

# Import schema
docker exec -i spot-mysql mysql -u root -prootpassword spot_optimizer < schema.sql

# Import demo data
docker exec -i spot-mysql mysql -u root -prootpassword < demo-data.sql
```

### 2. Python Backend

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend
python backend.py
# Or with Gunicorn (production):
gunicorn -w 4 -b 0.0.0.0:5000 backend:app
```

### 3. Verify

```bash
curl http://localhost:5000/health
```

## 🗄️ Database

**Schema**: 23 tables
- `clients` - Client accounts
- `agents` - Agent instances
- `instances` - Instance history
- `switches` - Switch events
- `pricing_reports` - Pricing data
- `spot_pools` - Available pools
- And 17 more...

**Demo Accounts**:
- `demo@acme.com` - Token: `demo_token_acme_12345`
- `demo@startupxyz.com` - Token: `demo_token_startup_67890`
- `demo@betatester.com` - Token: `demo_token_beta_11111`

## 🔌 API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /api/health` - Detailed health with DB status

### Client Management
- `POST /api/register` - Register agent
- `POST /api/heartbeat` - Agent heartbeat
- `GET /api/client/<id>` - Get client info
- `GET /api/client/<id>/agents` - List agents
- `GET /api/client/<id>/config` - Get config

### Admin
- `GET /api/admin/stats` - Global statistics
- `GET /api/admin/clients` - List all clients
- `GET /api/admin/instances` - List all instances

### Pricing
- `POST /api/pricing-report` - Submit pricing data
- `GET /api/pricing/<agent_id>` - Get pricing reports

### Decision Engine
- `POST /api/upload-decision-engine` - Upload model
- `POST /api/ml-models/upload` - Upload ML models

## 📊 Tech Stack

- **Backend**: Python 3.12, Flask 3.0, Gunicorn
- **Database**: MySQL 8.0
- **ML**: scikit-learn, numpy, pandas
- **Scheduling**: APScheduler

## 🔧 Configuration

Backend uses these environment variables (or defaults):

- `DB_HOST` - MySQL host (default: localhost)
- `DB_PORT` - MySQL port (default: 3306)
- `DB_NAME` - Database name (default: spot_optimizer)
- `DB_USER` - Database user (default: spotuser)
- `DB_PASSWORD` - Database password (default: SpotUser2024!)
- `PORT` - Backend port (default: 5000)

## 🛠️ Troubleshooting

### Backend won't start

```bash
# Check MySQL connectivity
docker exec spot-mysql mysql -u spotuser -pSpotUser2024! -e "SELECT 1;"

# Check logs
tail -f backend.log
```

### Database errors

```bash
# Verify tables exist
docker exec spot-mysql mysql -u spotuser -pSpotUser2024! spot_optimizer -e "SHOW TABLES;"

# Re-import schema if needed
docker exec -i spot-mysql mysql -u root -prootpassword spot_optimizer < schema.sql
```

## 📝 Development

```bash
# Activate venv
source venv/bin/activate

# Run in development mode
export FLASK_ENV=development
python backend.py

# Run tests (if available)
pytest
```

## 📄 License

Proprietary - Internal Use Only
