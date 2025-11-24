# AWS Spot Optimizer - Complete Architecture Diagram

```
================================================================================
                    AWS SPOT OPTIMIZER ARCHITECTURE
                         Version 5.0 - Modular
================================================================================

┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER LAYER                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Frontend (React + Vite)                            │   │
│  │  - Dashboard UI                                                       │   │
│  │  - Instance Management                                                │   │
│  │  - Replica Controls                                                   │   │
│  │  - Price Charts & Analytics                                           │   │
│  └────────────────────────────┬─────────────────────────────────────────┘   │
└────────────────────────────────┼──────────────────────────────────────────────┘
                                 │ REST API (JSON over HTTPS)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API INTERFACE LAYER                                  │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Agent Routes  │  │ Client Routes│  │ Admin Routes │  │ Replica Routes│  │
│  │ (agent_routes)│  │(client_routes│  │(admin_routes)│  │(replica_routes│  │
│  │               │  │              │  │              │  │               │   │
│  │ /api/agents/* │  │ /api/client/*│  │ /api/admin/* │  │ /api/replicas│   │
│  └───────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘   │
└──────────┼──────────────────┼──────────────────┼──────────────────┼──────────┘
           │                  │                  │                  │
           └──────────────────┴──────────┬───────┴──────────────────┘
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER (Business Logic)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │Agent Service │  │Instance Svc  │  │ Pricing Svc  │  │ Switch Svc   │   │
│  │              │  │              │  │              │  │              │   │
│  │ - Register   │  │ - Tracking   │  │ - Reports    │  │ - Orchestrate│   │
│  │ - Heartbeat  │  │ - Metrics    │  │ - History    │  │ - Execute    │   │
│  │ - Config     │  │ - Status     │  │ - Trends     │  │ - Record     │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                  │                  │                  │            │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴────────┐  │
│  │Replica Svc   │  │Decision Svc  │  │Client Svc    │  │Notification   │  │
│  │              │  │              │  │              │  │Service        │  │
│  │ - Create     │  │ - ML Models  │  │ - Management │  │              │  │
│  │ - Promote    │  │ - Recommend  │  │ - Settings   │  │ - Alerts     │  │
│  │ - Monitor    │  │ - Evaluate   │  │ - Stats      │  │ - Events     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
           │                  │                  │                  │
           └──────────────────┴──────────┬───────┴──────────────────┘
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CORE COMPONENT LAYER (Modular)                          │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                           SENTINEL COMPONENT                            │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Health Monitor   │  │ Interruption     │  │ Rate Limiter     │    │ │
│  │  │                  │  │ Detector         │  │                  │    │ │
│  │  │ - Heartbeats     │  │ - Rebalance      │  │ - Cascading      │    │ │
│  │  │ - Pricing Reports│  │ - Termination    │  │   Failure        │    │ │
│  │  │ - Agent Status   │  │ - Signal Dedup   │  │   Prevention     │    │ │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘    │ │
│  │           │                     │                       │              │ │
│  │           └─────────────────────┴───────────────────────┘              │ │
│  │                                 │                                       │ │
│  │                                 ▼ (triggers)                           │ │
│  │                    ┌────────────────────────┐                          │ │
│  │                    │Smart Emergency Fallback│                          │ │
│  │                    │        (SEF)           │                          │ │
│  │                    └────────────────────────┘                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       DECISION ENGINE COMPONENT                         │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Model Loader     │  │ I/O Contract     │  │ Model Registry   │    │ │
│  │  │                  │  │ Enforcer         │  │                  │    │ │
│  │  │ - Hot Reload     │  │ - Input Valid.   │  │ - Versions       │    │ │
│  │  │ - Validation     │  │ - Output Valid.  │  │ - Fallback       │    │ │
│  │  │ - ML Models      │  │ - Type Checking  │  │ - Statistics     │    │ │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘    │ │
│  │           │                     │                       │              │ │
│  │           └─────────────────────┴───────────────────────┘              │ │
│  │                                 │                                       │ │
│  │                                 ▼ (calls)                               │ │
│  │                     ┌──────────────────────┐                           │ │
│  │                     │ ML Based Engine      │                           │ │
│  │                     │ (Pluggable)          │                           │ │
│  │                     └──────────────────────┘                           │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       CALCULATION COMPONENT                             │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Savings Calc     │  │ Switch Impact    │  │ ROI Analysis     │    │ │
│  │  │                  │  │ Calculator       │  │                  │    │ │
│  │  │ - Hourly         │  │ - Before/After   │  │ - Replica Cost   │    │ │
│  │  │ - Monthly        │  │ - Improvement    │  │ - Downtime Value │    │ │
│  │  │ - Yearly         │  │ - Projections    │  │ - Break-even     │    │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       COMMAND TRACKER COMPONENT                         │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Priority Queue   │  │ Status Tracker   │  │ Result Logger    │    │ │
│  │  │                  │  │                  │  │                  │    │ │
│  │  │ - Emergency=100  │  │ - Pending        │  │ - Success/Fail   │    │ │
│  │  │ - Manual=75      │  │ - Executing      │  │ - Timing         │    │ │
│  │  │ - ML=50          │  │ - Completed      │  │ - Audit Trail    │    │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       AGENT IDENTITY COMPONENT                          │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Agent Minting    │  │ Identity         │  │ Migration        │    │ │
│  │  │                  │  │ Preservation     │  │ Manager          │    │ │
│  │  │ - First Reg.     │  │ - Switch Inherit │  │ - Instance Swap  │    │ │
│  │  │ - Logical ID     │  │ - Replica Merge  │  │ - Deduplication  │    │ │
│  │  │ - Unique UUID    │  │ - Continuity     │  │ - Cleanup        │    │ │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       DATA VALVE COMPONENT                              │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │ │
│  │  │ Data Quality     │  │ Gap Filler       │  │ Cache Manager    │    │ │
│  │  │                  │  │                  │  │                  │    │ │
│  │  │ - Validation     │  │ - Detection      │  │ - In-Memory      │    │ │
│  │  │ - Deduplication  │  │ - Interpolation  │  │ - TTL (60s)      │    │ │
│  │  │ - Normalization  │  │ - Quality Flags  │  │ - LRU Eviction   │    │ │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘    │ │
│  │           │                     │                       │              │ │
│  │           └─────────────────────┴───────────────────────┘              │ │
│  │                                 │                                       │ │
│  │                   ┌─────────────┴─────────────┐                        │ │
│  │                   │ 7-Day Rolling Window      │                        │ │
│  │                   │ Temporary vs Permanent    │                        │ │
│  │                   └───────────────────────────┘                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
           │                  │                  │                  │
           └──────────────────┴──────────┬───────┴──────────────────┘
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER (MySQL 8.0)                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        CORE TABLES                                   │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │ clients  │  │ agents   │  │ instances│  │ switches │           │   │
│  │  │          │  │          │  │          │  │          │           │   │
│  │  │ -id      │  │ -id      │  │ -id      │  │ -id      │           │   │
│  │  │ -token   │  │ -logical │  │ -agent   │  │ -old_id  │           │   │
│  │  │ -savings │  │  _id     │  │ -active  │  │ -new_id  │           │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │   │
│  │       │             │             │             │                   │   │
│  │  ┌────┴─────────────┴─────────────┴─────────────┴─────┐           │   │
│  │  │              Foreign Key Relationships               │           │   │
│  │  └──────────────────────────────────────────────────────┘           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     PRICING TABLES                                   │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│  │  │ spot_pools   │  │ spot_price   │  │ pricing      │             │   │
│  │  │              │  │ _snapshots   │  │ _reports     │             │   │
│  │  │ -id          │  │              │  │              │             │   │
│  │  │ -type        │  │ -pool_id     │  │ -agent_id    │             │   │
│  │  │ -region      │  │ -price       │  │ -prices      │             │   │
│  │  │ -az          │  │ -timestamp   │  │ -json        │             │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     REPLICA TABLES                                   │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│  │  │ replica      │  │ spot_inter   │  │ commands     │             │   │
│  │  │ _instances   │  │ _events      │  │              │             │   │
│  │  │              │  │              │  │ -id          │             │   │
│  │  │ -id          │  │ -signal_type │  │ -priority    │             │   │
│  │  │ -agent_id    │  │ -detected_at │  │ -status      │             │   │
│  │  │ -status      │  │ -replica_id  │  │ -result      │             │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   AUDIT & LOGGING TABLES                             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│  │  │ system       │  │ notifications│  │ agent_       │             │   │
│  │  │ _events      │  │              │  │ decision     │             │   │
│  │  │              │  │ -id          │  │ _history     │             │   │
│  │  │ -type        │  │ -message     │  │              │             │   │
│  │  │ -severity    │  │ -severity    │  │ -decision    │             │   │
│  │  │ -metadata    │  │ -read        │  │ -confidence  │             │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                         ▲
                                         │
                                         │ EC2 Metadata API
                                         │
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AGENT LAYER (Python)                                │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     Agent Process (on EC2 Instance)                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │ │
│  │  │ Heartbeat    │  │ Pricing      │  │ Command      │  │ Interrupt│  │ │
│  │  │ Loop         │  │ Reporter     │  │ Executor     │  │ Monitor  │  │ │
│  │  │              │  │              │  │              │  │          │  │ │
│  │  │ Every 60s    │  │ Every 60s    │  │ Poll 30s     │  │ Every 5s │  │ │
│  │  │              │  │              │  │              │  │          │  │ │
│  │  │ POST /heart  │  │ POST /pricing│  │ GET /pending │  │ AWS API  │  │ │
│  │  │  beat        │  │   -report    │  │  -commands   │  │ Check    │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                         ▲
                                         │
                                         │ Spot Interruption Signals
                                         │
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AWS CLOUD PLATFORM                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        EC2 Service                                      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │ │
│  │  │ Spot         │  │ On-Demand    │  │ Metadata     │  │ Interrup │  │ │
│  │  │ Instances    │  │ Instances    │  │ Endpoint     │  │ Signals  │  │ │
│  │  │              │  │              │  │              │  │          │  │ │
│  │  │ i-abc123     │  │ i-def456     │  │ 169.254.169  │  │ Rebalance│  │ │
│  │  │ $0.0456/hr   │  │ $0.0416/hr   │  │ .254         │  │ Termina  │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

================================================================================
                          DATA FLOW EXAMPLES
================================================================================

1. NORMAL HEARTBEAT FLOW:
   Agent → POST /api/agents/<id>/heartbeat → Agent Routes → Agent Service
   → Sentinel (health check) → Data Valve (store) → Database

2. PRICING REPORT FLOW:
   Agent → POST /api/agents/<id>/pricing-report → Agent Routes → Pricing Service
   → Data Valve (dedup, gap fill, cache) → Database

3. AWS INTERRUPTION FLOW:
   AWS → Agent (metadata API) → POST /api/agents/<id>/interruption
   → Agent Routes → Sentinel (detect, rate limit, dedup)
   → SEF (create replica / promote) → Command Tracker (queue command)
   → Database (log event) → Agent (poll, execute)

4. ML DECISION FLOW:
   Scheduler → Decision Service → Decision Engine (make_decision)
   → Calculation Engine (evaluate savings) → Command Tracker (create command)
   → Database (store) → Agent (poll, execute)

5. USER MANUAL SWITCH FLOW:
   Frontend → POST /api/client/instances/<id>/force-switch → Client Routes
   → Switch Service → Command Tracker (priority=75, manual override)
   → Database → Agent (poll, execute) → Switch Service (report)
   → Calculation Engine (savings) → Database

================================================================================
                       COMPONENT INTERACTION MATRIX
================================================================================

┌──────────────────┬──────────────────────────────────────────────────────────┐
│ Component        │ Depends On / Calls                                       │
├──────────────────┼──────────────────────────────────────────────────────────┤
│ Sentinel         │ → SEF, Data Valve, Database                             │
│ SEF              │ → Command Tracker, Agent Identity, Data Valve, Database │
│ Decision Engine  │ → Calculation Engine, Database                           │
│ Calculation Eng  │ → None (pure functions)                                  │
│ Command Tracker  │ → Database                                               │
│ Agent Identity   │ → Database                                               │
│ Data Valve       │ → Database (only component that writes to DB)           │
│ Services         │ → All Components (orchestration layer)                  │
│ API Routes       │ → Services                                               │
└──────────────────┴──────────────────────────────────────────────────────────┘

================================================================================
                         DIRECTORY STRUCTURE
================================================================================

final-ml/
├── backend/
│   ├── components/              # Core modular components (NEW)
│   │   ├── __init__.py         # Exports all components
│   │   ├── data_valve.py       # Data quality gate
│   │   ├── calculations.py     # Financial calculations
│   │   ├── command_tracker.py  # Command lifecycle
│   │   ├── sentinel.py         # Monitoring & triggers
│   │   ├── decision_engine.py  # ML model loading
│   │   └── agent_identity.py   # Agent lifecycle
│   │
│   ├── services/               # Business logic layer
│   │   ├── agent_service.py
│   │   ├── instance_service.py
│   │   ├── pricing_service.py
│   │   ├── switch_service.py
│   │   ├── replica_service.py
│   │   ├── decision_service.py
│   │   ├── client_service.py
│   │   └── notification_service.py
│   │
│   ├── api/                    # RESTful API routes
│   │   ├── agent_routes.py
│   │   ├── client_routes.py
│   │   ├── admin_routes.py
│   │   ├── notification_routes.py
│   │   └── replica_routes.py
│   │
│   ├── jobs/                   # Background scheduled tasks
│   │   ├── health_monitor.py
│   │   ├── snapshot_jobs.py
│   │   ├── pricing_aggregator.py
│   │   └── data_cleaner.py
│   │
│   ├── decision_engines/       # Pluggable ML engines
│   │   ├── ml_based_engine.py
│   │   └── rule_based_engine.py
│   │
│   ├── smart_emergency_fallback.py  # SEF core
│   ├── database_manager.py          # Connection pooling
│   ├── auth.py                      # Authentication
│   ├── utils.py                     # Utilities
│   ├── schemas.py                   # Validation
│   └── backend.py                   # Main Flask app
│
├── database/
│   └── schema.sql              # MySQL schema v5.1
│
├── frontend/
│   └── src/                    # React components
│
├── agent/
│   └── spot_agent.py           # Agent client
│
├── docs/
│   └── *.md                    # Documentation
│
├── ARCHITECTURE.md             # This file
└── COMPLETE_DOCUMENTATION.md   # Comprehensive guide

================================================================================
                      DESIGN PRINCIPLES
================================================================================

1. SEPARATION OF CONCERNS
   - Each component has ONE responsibility
   - Clear interfaces between layers
   - No circular dependencies

2. MODULARITY
   - Components are standalone and reusable
   - Pluggable architecture (Decision Engine)
   - Easy to test in isolation

3. DATA QUALITY
   - Data Valve is ONLY entry point to database
   - Validation at every layer
   - Deduplication and gap filling

4. RELIABILITY
   - Sentinel monitors continuously
   - SEF handles emergencies automatically
   - Fallback mechanisms at every level

5. OBSERVABILITY
   - Comprehensive logging
   - Statistics tracking
   - Audit trail for all actions

6. PERFORMANCE
   - Caching with TTL
   - Connection pooling
   - Async background jobs

7. SECURITY
   - Token-based authentication
   - Input validation
   - SQL injection prevention

================================================================================
                      VERSION HISTORY
================================================================================

v5.0 (2025-11-24) - Modular Architecture
  - Created 6 core components
  - Scenario-based documentation
  - Complete separation of concerns

v4.3 (2024-11-23) - Replica Management
  - Manual replica mode
  - Enhanced SEF
  - Agent v4.0 compatibility

v3.0 (2024-09-15) - ML Integration
  - Pluggable decision engines
  - Model registry
  - Enhanced pricing data

v2.0 (2024-06-01) - Production Ready
  - Connection pooling
  - Background jobs
  - Complete API

v1.0 (2024-03-01) - Initial Release
  - Basic switching
  - Agent registration
  - Simple pricing

================================================================================
```
