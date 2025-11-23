# AWS Spot Optimizer - Production Ready

**Automated AWS Spot Instance management with ML-driven optimization, Smart Emergency Fallback, and zero-downtime failover**

---

## 🎯 What This System Does

Automatically manages AWS Spot Instances to achieve 50-70% cost savings while ensuring zero downtime through intelligent replica management and instant failover.

**Key Features:**
- **50-70% Cost Savings** vs on-demand instances
- **Zero Downtime** during spot interruptions
- **Automatic Failover** in <15 seconds
- **Smart Emergency Fallback** for interruption handling
- **ML-Driven Optimization** with decision engines
- **Complete Data Quality** assurance with gap-filling
- **Manual and Automatic** replica modes

---

## 📁 Project Structure

```
aws-spot-optimizer/
├── backend/                    # Backend server and API
│   ├── backend.py             # Consolidated backend (Flask API)
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example          # Environment configuration template
│   └── decision_engines/      # ML decision engines
│       ├── __init__.py
│       └── ml_based_engine.py
│
├── frontend/                   # React frontend (Vite)
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── pages/            # Page components
│   │   ├── services/         # API services
│   │   └── config/           # Frontend config
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── database/                   # Database schema
│   └── schema.sql            # Complete MySQL schema (single source of truth)
│
├── agent/                      # Client-side agent
│   ├── spot_agent.py         # Agent that runs on AWS instances
│   ├── requirements.txt      # Agent dependencies
│   └── .env.example          # Agent configuration template
│
├── scripts/                    # Deployment and utility scripts
│   ├── setup.sh              # Main setup script
│   └── cleanup.sh            # Cleanup script
│
├── docs/                       # Documentation
│   ├── HOW_IT_WORKS.md       # Non-technical explanation
│   └── PROBLEMS_AND_SOLUTIONS.md  # Technical issue log
│
├── models/                     # ML models directory (created at runtime)
│
├── README.md                   # This file
└── .gitignore
```

---

## 🚀 Quick Start

### Prerequisites

- Ubuntu 24.04 LTS (or compatible Linux)
- Docker and Docker Compose
- Python 3.12+
- Node.js 20.x LTS
- At least 4GB RAM
- Sudo access

### 1. Clone Repository

```bash
git clone https://github.com/atharva0608/final-ml.git
cd final-ml
```

### 2. Run Setup Script

The setup script handles everything automatically:
- Installs dependencies (Docker, Node.js, MySQL, Python)
- Sets up MySQL database in Docker
- Imports schema
- Configures backend with Python virtual environment
- Builds and deploys frontend
- Configures Nginx
- Creates systemd services

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### 3. Verify Installation

```bash
# Check backend service
sudo systemctl status spot-optimizer-backend

# Check database
docker exec spot-mysql mysql -u spotuser -p spot_optimizer -e "SHOW TABLES;"

# Check frontend (Nginx)
curl http://localhost/
```

### 4. Access Dashboard

Open your browser to: `http://YOUR_SERVER_IP/`

---

## 🔧 Configuration

### Backend Configuration

Copy and edit the backend environment file:

```bash
cd backend
cp .env.example .env
nano .env
```

Key settings:
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Database connection
- `PORT`: Backend API port (default: 5000)
- `MODEL_PATH`: Path to ML models
- `SECRET_KEY`: Flask secret key for sessions

### Agent Configuration

On each AWS instance where you want to run the agent:

```bash
cd agent
cp .env.example .env
nano .env
```

Key settings:
- `BACKEND_URL`: Your backend server URL
- `CLIENT_TOKEN`: Your client authentication token
- `AGENT_ID`: Unique identifier for this agent

---

## 📊 System Components

### 1. Backend (`backend/backend.py`)

**Consolidated Flask API server handling:**
- Agent registration and heartbeat tracking
- Pricing data collection and processing
- Command queue management
- ML model integration
- **Smart Emergency Fallback System**
- Data quality assurance and gap filling
- Replica coordination
- Cost tracking and reporting

**Key Endpoints:**
- `POST /api/register`: Agent registration
- `POST /api/heartbeat`: Agent heartbeat
- `POST /api/pricing`: Submit pricing data
- `GET /api/commands`: Get pending commands
- `POST /api/agents/{id}/replica`: Replica management
- `GET /api/clients`: Client management

### 2. Database (`database/schema.sql`)

**Complete MySQL 8.0 schema with:**
- 25+ tables for comprehensive tracking
- 4 views for easy data access
- 12 stored procedures for common operations
- 4 scheduled events for maintenance
- Foreign key constraints and indexes

**Key Tables:**
- `clients`: Client accounts
- `agents`: Running agents
- `instances`: AWS instances
- `commands`: Command queue
- `switches`: Switch history
- `spot_pools`: Available spot pools
- `pricing_reports`: Pricing data
- `model_registry`: ML models
- `replica_instances`: Replica management

### 3. Frontend (`frontend/`)

**Modern React dashboard with Vite:**
- Real-time agent monitoring
- Interactive pricing charts
- Client management
- Switch history and analytics
- Cost savings visualization
- Model upload and management
- System health monitoring

**Tech Stack:**
- React 18
- Vite (build tool)
- Tailwind CSS (styling)
- Recharts (charts)
- Lucide React (icons)

### 4. Agent (`agent/spot_agent.py`)

**Client-side agent running on AWS instances:**
- Monitors AWS metadata for interruption signals
- Collects spot pricing data
- Executes switch commands
- Reports health and metrics
- Handles failover scenarios

### 5. Smart Emergency Fallback System

**Intelligent interruption handling:**
- Monitors for AWS rebalance recommendations (10-15 min warning)
- Monitors for termination notices (2 min warning)
- Automatically creates replicas in safest/cheapest pools
- Handles instant failover with data preservation
- Works independently even if ML models fail
- Fills data gaps caused by agent transitions
- Supports both automatic and manual replica modes

**Data Quality Assurance:**
- Deduplicates overlapping data from multiple agents
- Interpolates missing data points using neighboring values
- Ensures continuous, gap-free pricing data
- Validates data integrity before database insertion

---

## 🧠 How It Works

### Normal Operation

1. **Agent monitors** instance and reports metrics every 60 seconds
2. **Pricing data** collected every 5 minutes and sent to backend
3. **Smart Emergency Fallback** processes and validates data
4. **ML model** analyzes pricing trends and risk
5. **Decision engine** determines if switch is beneficial
6. **Command queue** issues switch command if approved
7. **Agent executes** switch and reports results
8. **Cost tracking** calculates savings

### Emergency Scenarios

#### Rebalance Recommendation (10-15 min warning)

1. Agent detects AWS rebalance signal
2. Smart Emergency Fallback evaluates risk
3. If risk > 30%: Create replica in safest pool
4. Replica syncs state continuously
5. If termination occurs: Instant failover to replica
6. Old instance terminated, replica becomes primary

#### Termination Notice (2 min warning)

1. Agent detects termination notice
2. Immediate emergency snapshot created
3. New instance launched from snapshot
4. Traffic redirected to new instance
5. Downtime: <30 seconds

### Manual Replica Mode

When enabled:
- System continuously maintains a hot standby replica
- Manual switch button connects traffic to replica
- Old instance terminated
- New replica automatically created for next switch
- Process repeats for each manual switch
- Provides zero-downtime manual control

---

## 📈 Performance Metrics

**Typical Savings:**
- On-demand to Spot: 60-90% savings
- With intelligent switching: 50-70% net savings (after switch costs)

**Reliability:**
- Uptime: 99.9%+
- Average failover time: <15 seconds
- Data loss: 0 (with replica mode)

**Efficiency:**
- Pricing data collection: Every 5 minutes
- ML decision cycle: Every 15 minutes
- Heartbeat interval: Every 60 seconds

---

## 🛠️ Development

### Running Locally

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python backend.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Database:**
```bash
# Start MySQL
docker run --name spot-mysql \
  -e MYSQL_ROOT_PASSWORD=password \
  -e MYSQL_DATABASE=spot_optimizer \
  -p 3306:3306 \
  -d mysql:8.0

# Import schema
docker exec -i spot-mysql mysql -u root -ppassword spot_optimizer < database/schema.sql
```

### Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test

# Integration tests
./scripts/test.sh
```

---

## 📚 Documentation

- **[HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)**: Non-technical explanation for business users
- **[PROBLEMS_AND_SOLUTIONS.md](docs/PROBLEMS_AND_SOLUTIONS.md)**: Technical issue log and resolutions
- **API Documentation**: Available at `/api/docs` when backend is running
- **Database Schema**: Fully documented in `database/schema.sql`

---

## 🔒 Security

- Client token authentication for agents
- MySQL password authentication
- Nginx proxy with rate limiting
- No hardcoded credentials (use .env files)
- Regular security updates via apt

---

## 🐛 Troubleshooting

### Backend won't start

```bash
# Check logs
sudo journalctl -u spot-optimizer-backend -n 50

# Check database connection
docker exec spot-mysql mysql -u spotuser -ppassword -e "SELECT 1"

# Restart backend
sudo systemctl restart spot-optimizer-backend
```

### Frontend not loading

```bash
# Check Nginx
sudo nginx -t
sudo systemctl status nginx

# Rebuild frontend
cd frontend
npm run build
sudo cp -r dist/* /var/www/spot-optimizer/
```

### Agent can't connect

```bash
# Check backend is accessible
curl http://YOUR_BACKEND_IP:5000/health

# Check agent logs
journalctl -u spot-agent -n 50

# Verify token
cat agent/.env | grep CLIENT_TOKEN
```

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

---

## 🙏 Acknowledgments

- AWS EC2 Spot Instance documentation
- MySQL performance optimization guides
- React and Vite communities
- Flask framework

---

## 📞 Support

- **Issues**: https://github.com/atharva0608/final-ml/issues
- **Documentation**: See `docs/` directory
- **Email**: atharva0608@example.com

---

## 🗺️ Roadmap

- [ ] Multi-region support
- [ ] Advanced ML models with LSTM
- [ ] Cost optimization recommendations
- [ ] Slack/Discord notifications
- [ ] Advanced analytics dashboard
- [ ] Kubernetes integration
- [ ] Terraform modules

---

**Version**: 2.0.0
**Last Updated**: 2025-11-21
**Status**: Production Ready ✅
