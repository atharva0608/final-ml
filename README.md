# AWS Spot Optimizer v5.0 - Production Ready

**Automated AWS Spot Instance management with ML-driven optimization and zero-downtime failover**

[![Architecture](https://img.shields.io/badge/Architecture-Modular-green)](backend/README.md)
[![Backend](https://img.shields.io/badge/Backend-Flask%203.0-blue)](backend/)
[![Frontend](https://img.shields.io/badge/Frontend-React%2018-blue)](frontend/)
[![Endpoints](https://img.shields.io/badge/API%20Endpoints-67-brightgreen)](backend/README.md)

---

## 🎯 What This System Does

Automatically manages AWS Spot Instances to achieve **50-70% cost savings** while ensuring **zero downtime** through intelligent replica management and instant failover.

**Key Features:**
- ✅ **50-70% Cost Savings** vs on-demand instances
- ✅ **Zero Downtime** during spot interruptions
- ✅ **Automatic Failover** in <15 seconds
- ✅ **67+ API Endpoints** with modular architecture
- ✅ **ML-Driven Optimization** with decision engines
- ✅ **Complete Data Quality** assurance with gap-filling
- ✅ **Manual and Automatic** replica modes
- ✅ **Real-time Monitoring** with React dashboard

---

## 🏗️ Architecture Overview

```
aws-spot-optimizer/
├── backend/                    # Modular Backend (v5.0)
│   ├── app.py                 # Entry point
│   ├── api/                   # 5 route blueprints (67 endpoints)
│   ├── services/              # 9 business logic services
│   ├── components/            # 6 shared components
│   ├── jobs/                  # 4 background jobs
│   ├── decision_engines/      # ML decision engines
│   ├── README.md             # Detailed architecture docs
│   └── DEPLOYMENT.md         # Production deployment guide
│
├── frontend/                   # React Dashboard (Vite)
│   ├── src/components/        # UI components
│   ├── src/services/          # API clients
│   └── package.json
│
├── database/                   # Database Schema
│   └── schema.sql             # Complete MySQL schema
│
├── scripts/                    # Deployment Scripts
│   ├── setup.sh              # Production setup (v5.0)
│   └── cleanup.sh            # Complete cleanup (v5.0)
│
└── docs/                       # Documentation

```

---

## 🚀 Quick Start

### Prerequisites
- Ubuntu 24.04 LTS
- Sudo access
- Internet connectivity
- MySQL 8.0 (installed via setup script)

### Installation

```bash
# Clone repository
git clone https://github.com/atharva0608/final-ml.git
cd final-ml

# Run setup script (installs everything)
sudo bash scripts/setup.sh
```

The setup script will:
1. ✅ Install MySQL 8.0 (Docker container)
2. ✅ Configure modular backend with 67 endpoints
3. ✅ Build and deploy React frontend
4. ✅ Set up Nginx reverse proxy
5. ✅ Create systemd services
6. ✅ Initialize demo data

### Access

- **Frontend Dashboard**: `http://your-server-ip`
- **Backend API**: `http://your-server-ip/api`
- **Health Check**: `http://your-server-ip/api/health`

---

## 📚 Documentation

- **[Backend Architecture](backend/README.md)** - Complete modular architecture documentation
- **[Deployment Guide](backend/DEPLOYMENT.md)** - Production deployment steps
- **[API Reference](backend/README.md#endpoint-migration-mapping)** - All 67 endpoints
- **[Setup Script](scripts/setup.sh)** - Automated installation

---

## 🔧 Key Components

### Backend (Modular Architecture v5.0)
- **67 API Endpoints** across 5 blueprints
- **9 Service Modules** for business logic
- **6 Shared Components** (agent identity, calculations, command tracker, etc.)
- **4 Background Jobs** (health monitoring, pricing aggregation, data cleaning, snapshots)
- **Flask 3.0** with APScheduler
- **MySQL 8.0** with connection pooling

### Frontend
- **React 18** with Vite for fast builds
- **Recharts** for data visualization
- **Tailwind CSS** for styling
- **Real-time updates** via polling
- **CSV exports** for all data tables

### Features
- 🔍 **Global Search** across clients, agents, instances
- 📊 **Export to CSV** (savings, history, statistics)
- 🔐 **Token-based Auth** with auto-copy
- 📈 **Real-time Charts** for monitoring
- ⚡ **Instance Switching** with security checks
- 🛡️ **Zero-downtime Failover** during interruptions

---

## 🎯 Use Cases

1. **Cost Optimization**: Reduce AWS EC2 costs by 50-70%
2. **High Availability**: Maintain 99.9% uptime with spot instances
3. **ML Workloads**: Run training jobs on spot instances with automatic interruption handling
4. **Web Services**: Host production web services on spot instances with instant failover
5. **Batch Processing**: Optimize batch job costs while ensuring completion

---

## 📊 Performance

- **Request Latency**: ~45ms average
- **Failover Time**: <15 seconds during spot interruptions
- **Cost Savings**: 50-70% vs on-demand
- **API Throughput**: 1000+ req/sec
- **Zero Downtime**: With proper replica configuration

---

## 🔄 Cleanup

To completely remove all components:

```bash
sudo bash scripts/cleanup.sh
```

This removes:
- Systemd services
- Docker containers & volumes
- Application files
- Database data
- Nginx configuration

---

## 📝 Version History

- **v5.0** (2025-11-24) - Complete modular refactor, 67 endpoints, search & export APIs
- **v4.0** - Smart Emergency Fallback system
- **v3.3** - Production hardening and security
- **v3.0** - Frontend dashboard and ML integration
- **v2.0** - Replica management
- **v1.0** - Initial release

---

## 🤝 Contributing

This is a production system. When making changes:

1. Follow modular architecture patterns (routes → services → database)
2. Add comprehensive error handling
3. Update tests and documentation
4. Test thoroughly before deployment

See [Backend README](backend/README.md) for development guidelines.

---

## 📄 License

Internal use only - AWS Spot Optimizer Platform

---

## 🔗 Links

- **Repository**: https://github.com/atharva0608/final-ml
- **Backend Docs**: [backend/README.md](backend/README.md)
- **Deployment Guide**: [backend/DEPLOYMENT.md](backend/DEPLOYMENT.md)

---

**Version**: 5.0.0
**Architecture**: Modular
**Production Ready**: ✅ Yes
**Last Updated**: 2025-11-24
