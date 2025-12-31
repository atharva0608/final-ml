# Production Task List - Spot Optimizer Platform

> **Purpose**: Complete task breakdown from initial setup to production deployment
> **Execution Mode**: Continuous - Tasks should be executed sequentially without timeline constraints
> **Status Format**: `[ ]` Not started | `[/]` In progress | `[x]` Completed

---

## Phase 1: Project Foundation & Infrastructure Setup

### 1.1 Repository Structure Organization
- [ ] Create complete folder structure as per `folder_structure.md`
  - [ ] Create `docs/` directory and move all documentation files
  - [ ] Create `backend/` with subdirectories: `api/`, `services/`, `workers/`, `modules/`, `scrapers/`, `core/`, `models/`, `schemas/`, `utils/`
  - [ ] Create `frontend/src/` with subdirectories: `components/`, `services/`, `hooks/`, `utils/`
  - [ ] Create `scripts/` with subdirectories: `aws/`, `deployment/`
  - [ ] Create `config/`, `docker/`, `.github/workflows/` directories
  - [ ] Keep `task.md` in root for easy access

### 1.2 INFO.md File Creation
- [ ] Create `INFO.md` template file
- [ ] Generate `INFO.md` for every directory using the template from `folder_structure.md`
  - [ ] `docs/INFO.md` with documentation component table
  - [ ] `backend/INFO.md` with backend module overview
  - [ ] `backend/api/INFO.md` with API routes table
  - [ ] `backend/services/INFO.md` with service layer table
  - [ ] `backend/workers/INFO.md` with worker components table
  - [ ] `backend/modules/INFO.md` with intelligence modules table
  - [ ] `backend/scrapers/INFO.md` with scraper services table
  - [ ] `backend/core/INFO.md` with core components table
  - [ ] `backend/models/INFO.md` with database models table
  - [ ] `backend/schemas/INFO.md` with Pydantic schemas table
  - [ ] `backend/utils/INFO.md` with utility functions table
  - [ ] `frontend/INFO.md` with frontend overview
  - [ ] `frontend/src/components/INFO.md` with component categories
  - [ ] Create `INFO.md` for all component subdirectories (auth, dashboard, clusters, templates, policies, hibernation, audit, settings, admin)
  - [ ] `frontend/src/services/INFO.md` with API client services
  - [ ] `frontend/src/hooks/INFO.md` with custom hooks
  - [ ] `frontend/src/utils/INFO.md` with frontend utilities
  - [ ] `scripts/INFO.md` with automation scripts overview
  - [ ] `scripts/aws/INFO.md` with AWS boto3 scripts table
  - [ ] `scripts/deployment/INFO.md` with deployment scripts
  - [ ] `config/INFO.md` with configuration files
  - [ ] `docker/INFO.md` with Docker configuration

### 1.3 Environment Configuration
- [ ] Create `.env.example` file with all required environment variables
  - [ ] Database connection strings (PostgreSQL)
  - [ ] Redis connection configuration
  - [ ] AWS credentials placeholders
  - [ ] JWT secret key
  - [ ] Celery broker URL
  - [ ] Frontend API endpoint
  - [ ] CORS allowed origins
  - [ ] Email service credentials (SendGrid/SES)
  - [ ] Stripe API keys (for billing)
  - [ ] Log level configuration
- [ ] Create `requirements.txt` for Python dependencies
  - [ ] FastAPI and Uvicorn
  - [ ] SQLAlchemy and Alembic
  - [ ] Pydantic
  - [ ] Redis client
  - [ ] Celery
  - [ ] boto3 (AWS SDK)
  - [ ] bcrypt for password hashing
  - [ ] PyJWT for authentication
  - [ ] scikit-learn for ML models
  - [ ] pandas and numpy
  - [ ] requests for HTTP calls
  - [ ] pytest for testing
- [ ] Create `package.json` for Node.js dependencies
  - [ ] React and ReactDOM
  - [ ] React Router
  - [ ] Axios for API calls
  - [ ] Recharts for data visualization
  - [ ] Framer Motion for animations
  - [ ] Tailwind CSS or custom CSS framework
  - [ ] WebSocket client
  - [ ] Date handling library (date-fns)
  - [ ] Form validation library
  - [ ] Testing libraries (Jest, React Testing Library)

### 1.4 Docker Configuration
- [ ] Create `docker/Dockerfile.backend`
  - [ ] Base image: Python 3.11-slim
  - [ ] Install system dependencies
  - [ ] Copy requirements.txt and install Python packages
  - [ ] Set working directory
  - [ ] Copy backend code
  - [ ] Expose port 8000
  - [ ] Set entrypoint for Uvicorn
- [ ] Create `docker/Dockerfile.frontend`
  - [ ] Base image: Node 18-alpine
  - [ ] Copy package.json and install dependencies
  - [ ] Copy frontend code
  - [ ] Build production bundle
  - [ ] Use nginx to serve static files
  - [ ] Expose port 80
- [ ] Create `docker/docker-compose.yml`
  - [ ] PostgreSQL service with persistent volume
  - [ ] Redis service
  - [ ] Backend service with environment variables
  - [ ] Celery worker service
  - [ ] Celery beat scheduler service
  - [ ] Frontend service
  - [ ] Network configuration
  - [ ] Volume mounts for development

---

## Phase 2: Database Layer Implementation

### 2.1 Database Models (SQLAlchemy)
- [ ] Create `backend/models/user.py` - User model
  - [ ] Fields: id (UUID), email (unique), password_hash, role (enum: client/super_admin), created_at, updated_at
  - [ ] Relationship to accounts table
  - [ ] Password hashing methods
- [ ] Create `backend/models/account.py` - AWS Account model
  - [ ] Fields: id (UUID), user_id (FK), aws_account_id, role_arn, external_id, status (enum: pending/scanning/active), created_at
  - [ ] Relationship to users and clusters
- [ ] Create `backend/models/cluster.py` - Kubernetes Cluster model
  - [ ] Fields: id (UUID), account_id (FK), name, region, vpc_id, api_endpoint, k8s_version, status, created_at
  - [ ] Relationship to instances and policies
- [ ] Create `backend/models/instance.py` - EC2 Instance model
  - [ ] Fields: id (UUID), cluster_id (FK), instance_id, instance_type, lifecycle (spot/on_demand), az, price, cpu_util, memory_util, created_at
  - [ ] Indexes on cluster_id and instance_id
- [ ] Create `backend/models/node_template.py` - Node Template model
  - [ ] Fields: id (UUID), user_id (FK), name, families (ARRAY), architecture, strategy, disk_type, disk_size, is_default, created_at
  - [ ] Unique constraint on (user_id, name)
- [ ] Create `backend/models/cluster_policy.py` - Cluster Policy model
  - [ ] Fields: id (UUID), cluster_id (FK), config (JSONB), updated_at
  - [ ] JSONB structure for karpenter, binpack, fallback, exclusions
- [ ] Create `backend/models/hibernation_schedule.py` - Hibernation Schedule model
  - [ ] Fields: id (UUID), cluster_id (FK), schedule_matrix (JSONB - 168 elements), timezone, prewarm_enabled, prewarm_minutes
  - [ ] Unique constraint on cluster_id
- [ ] Create `backend/models/audit_log.py` - Audit Log model
  - [ ] Fields: id (UUID), timestamp (with milliseconds), actor_id, actor_name, event, resource, resource_type, outcome, ip_address, user_agent, diff_before (JSONB), diff_after (JSONB)
  - [ ] Indexes on timestamp, actor_id, resource_type
  - [ ] Immutable (no updates allowed)
- [ ] Create `backend/models/ml_model.py` - ML Model Registry
  - [ ] Fields: id (UUID), version, file_path, status (enum: testing/production), uploaded_at, validated_at, performance_metrics (JSONB)
- [ ] Create `backend/models/optimization_job.py` - Optimization Job model
  - [ ] Fields: id (UUID), cluster_id (FK), status (enum: queued/running/completed/failed), created_at, completed_at, results (JSONB)
- [ ] Create `backend/models/lab_experiment.py` - Lab Experiment model
  - [ ] Fields: id (UUID), model_id (FK), instance_id, test_type, telemetry (JSONB), created_at
- [ ] Create `backend/models/agent_action.py` - Pending Agent Actions Queue
  - [ ] **Purpose**: Queue for Kubernetes actions that must be executed by the Agent (not Boto3)
  - [ ] Fields: id (UUID), cluster_id (FK), action_type (enum: evict_pod/cordon_node/drain_node/label_node/update_deployment), payload (JSONB), status (enum: pending/picked_up/completed/failed), created_at, expires_at, picked_up_at, completed_at, result (JSONB), error_message
  - [ ] Indexes:
    - [ ] Composite index on (cluster_id, status) for fast polling by Agent
    - [ ] Index on expires_at for cleanup of stale actions
    - [ ] Index on created_at for ordering
  - [ ] Constraints:
    - [ ] expires_at must be > created_at
    - [ ] Default expires_at = created_at + 5 minutes
  - [ ] Relationships:
    - [ ] Foreign key to clusters table
    - [ ] Optional foreign key to optimization_jobs table (if triggered by optimizer)
  - [ ] **Critical for Worker-to-Agent communication loop**

### 2.2 Database Migrations
- [ ] Initialize Alembic for database migrations
  - [ ] Create `alembic.ini` configuration
  - [ ] Create `migrations/` directory structure
- [ ] Create initial migration for all models
  - [ ] Generate migration script: `alembic revision --autogenerate -m "Initial schema"`
  - [ ] Review and adjust migration script
  - [ ] Add indexes for performance
  - [ ] Add constraints and foreign keys
- [ ] Create seed data migration
  - [ ] Default super_admin user
  - [ ] Sample node templates
  - [ ] Default cluster policies

### 2.3 Pydantic Schemas
- [ ] Create `backend/schemas/auth_schemas.py`
  - [ ] SignupRequest, LoginRequest, TokenResponse, UserContext schemas
- [ ] Create `backend/schemas/cluster_schemas.py`
  - [ ] ClusterList, ClusterDetail, AgentCmd, Heartbeat, JobId schemas
- [ ] Create `backend/schemas/template_schemas.py`
  - [ ] TmplList, NodeTemplate, TemplateValidation schemas
- [ ] Create `backend/schemas/policy_schemas.py`
  - [ ] PolState, PolicyUpdate schemas
- [ ] Create `backend/schemas/hibernation_schemas.py`
  - [ ] ScheduleMatrix, Override schemas
- [ ] Create `backend/schemas/metric_schemas.py`
  - [ ] KPISet, ChartData, PieData, FeedData schemas
- [ ] Create `backend/schemas/audit_schemas.py`
  - [ ] AuditLogList, AuditLog, DiffData schemas
- [ ] Create `backend/schemas/admin_schemas.py`
  - [ ] ClientList, ClientOrg schemas
- [ ] Create `backend/schemas/lab_schemas.py`
  - [ ] TelemetryData, ABTestConfig, ABResults schemas

---

## Phase 3: Backend Core Services Implementation

### 3.1 Authentication Service (CORE-API)
- [ ] Create `backend/services/auth_service.py`
  - [ ] Implement `create_user_org_txn()` - Atomic user + org creation
    - [ ] Validate email format and password strength
    - [ ] Hash password with bcrypt
    - [ ] Create user record
    - [ ] Create placeholder account record
    - [ ] Return user_id and JWT token
  - [ ] Implement `authenticate_user()` - Login validation
    - [ ] Query user by email
    - [ ] Verify password hash
    - [ ] Generate JWT token with 24h expiry
    - [ ] Include role in token payload
  - [ ] Implement `determine_route_logic()` - Smart routing
    - [ ] Decode JWT token
    - [ ] Query account status
    - [ ] Return redirect path based on status (pending → /onboarding, active → /dashboard)
  - [ ] Implement `invalidate_session()` - Logout
    - [ ] Add JWT to Redis blacklist with TTL
  - [ ] Implement JWT middleware for route protection
    - [ ] Verify token signature
    - [ ] Check blacklist
    - [ ] Extract user context

### 3.2 Cloud Connection Service
- [ ] Create `backend/services/cloud_connect.py`
  - [ ] Implement `validate_aws_connection()` - IAM role verification
    - [ ] Use boto3 STS to assume role
    - [ ] Validate permissions (ec2:Describe*, eks:List*)
    - [ ] Update account status to 'scanning'
    - [ ] Trigger discovery worker
  - [ ] Implement `initiate_account_link()` - Multi-account support
    - [ ] Generate unique external_id (UUID)
    - [ ] Create CloudFormation template URL
    - [ ] Return setup instructions

### 3.3 Cluster Service
- [ ] Create `backend/services/cluster_service.py`
  - [ ] Implement `list_managed_clusters()` - Cluster registry
    - [ ] Query clusters by user's account_id
    - [ ] Join with instances for node count
    - [ ] Calculate monthly cost
    - [ ] Return ClusterList schema
  - [ ] Implement `get_cluster_details()` - Detailed view
    - [ ] Query cluster with relationships
    - [ ] Fetch health metrics from CloudWatch
    - [ ] Return ClusterDetail schema
  - [ ] Implement `generate_agent_install()` - Helm command generation
    - [ ] Create cluster-specific API token
    - [ ] Generate Helm install command with values
    - [ ] Return AgentCmd schema
  - [ ] Implement `verify_agent_connection()` - Heartbeat check
    - [ ] Query Redis for agent heartbeat timestamp
    - [ ] Calculate time since last seen
    - [ ] Return connection status (connected if <60s)

### 3.4 Template Service
- [ ] Create `backend/services/template_service.py`
  - [ ] Implement `list_node_templates()` - Template grid
  - [ ] Implement `create_node_template()` - Template creation
  - [ ] Implement `set_global_default_template()` - Default management
  - [ ] Implement `delete_node_template()` - Soft delete with usage check

### 3.5 Policy Service
- [ ] Create `backend/services/policy_service.py`
  - [ ] Implement `update_karpenter_state()` - Karpenter toggle
    - [ ] Update JSONB config in cluster_policies
    - [ ] Broadcast to agents via Redis pub/sub
  - [ ] Implement `update_binpack_settings()` - Bin packing configuration
  - [ ] Implement `update_fallback_policy()` - Spot fallback
  - [ ] Implement `update_exclusion_list()` - Namespace exclusions

### 3.6 Hibernation Service
- [ ] Create `backend/services/hibernation_service.py`
  - [ ] Implement `save_weekly_schedule()` - Schedule matrix storage
    - [ ] Validate 168-element array
    - [ ] Store in JSONB format
  - [ ] Implement `trigger_manual_wakeup()` - Override logic
    - [ ] Create override record
    - [ ] Call AWS ASG update script
  - [ ] Implement `update_prewarm_status()` - Pre-warm configuration
  - [ ] Implement `update_cluster_timezone()` - Timezone management

### 3.7 Metrics Service
- [ ] Create `backend/services/metrics_service.py`
  - [ ] Implement `calculate_current_spend()` - Monthly spend KPI
    - [ ] Query all instances for user
    - [ ] Calculate: SUM(instance_price * 730 hours)
  - [ ] Implement `calculate_net_savings()` - Savings calculation
    - [ ] Compare baseline cost vs optimized cost
  - [ ] Implement `get_fleet_composition()` - Pie chart data
    - [ ] Group instances by family and lifecycle
  - [ ] Implement `get_activity_feed()` - Recent actions
    - [ ] Query audit_logs with limit
    - [ ] Format for activity feed

### 3.8 Audit Service
- [ ] Create `backend/services/audit_service.py`
  - [ ] Implement `fetch_audit_logs()` - Paginated logs
  - [ ] Implement `generate_audit_checksum_export()` - Compliance export
    - [ ] Generate CSV with SHA-256 checksum
  - [ ] Implement `fetch_audit_diff()` - JSON diff viewer
  - [ ] Implement audit logging decorator for all write operations

### 3.9 Admin Service
- [ ] Create `backend/services/admin_service.py`
  - [ ] Implement `list_all_clients()` - Client registry
  - [ ] Implement `generate_impersonation_token()` - Impersonation
    - [ ] Create temporary JWT with client's org_id
    - [ ] Include admin's identity in audit trail
  - [ ] Implement `check_worker_queue_depth()` - System health

### 3.10 WebSocket Infrastructure (CORE-WS)
- [ ] Create `backend/core/websocket_manager.py`
  - [ ] Implement `ConnectionManager` class
    - [ ] Handle WebSocket connection upgrades
    - [ ] Authenticate connections via query param token
    - [ ] Maintain active connection pool by client_id
    - [ ] Implement connection cleanup on disconnect
  - [ ] Implement `broadcast_to_client()` - Send message to specific client
  - [ ] Implement `broadcast_to_all()` - Send message to all connected clients
  - [ ] Implement heartbeat/ping-pong mechanism to detect dead connections
- [ ] Create `backend/core/redis_pubsub.py`
  - [ ] Implement async Redis listener
  - [ ] Create pub/sub channels:
    - [ ] `system:logs` - System log stream for admin console
    - [ ] `lab:telemetry:{test_id}` - Live lab experiment telemetry
    - [ ] `cluster:events:{cluster_id}` - Cluster-specific events
    - [ ] `agent:heartbeat:{cluster_id}` - Agent heartbeat updates
  - [ ] Implement `subscribe_to_channel()` - Subscribe to Redis channel
  - [ ] Implement `publish_to_channel()` - Publish message to Redis channel
  - [ ] Implement message routing: Redis → WebSocket clients
  - [ ] Handle reconnection logic with exponential backoff
- [ ] Integrate WebSocket manager with FastAPI
  - [ ] Add WebSocket route handlers to API gateway
  - [ ] Implement connection authentication middleware
  - [ ] Add error handling for WebSocket failures

---

## Phase 4: Intelligence Modules Implementation

### 4.1 Spot Optimization Engine (MOD-SPOT-01)
- [ ] Create `backend/modules/spot_optimizer.py`
  - [ ] Implement `select_best_instance()` - Instance selection logic
    - [ ] Query Redis for current Spot prices
    - [ ] Query global risk tracker for flagged pools
    - [ ] Filter out risky pools
    - [ ] Score: (Price * 0.6) + (Risk * 0.4)
    - [ ] Return sorted candidate list
  - [ ] Implement `detect_opportunities()` - Waste detection
    - [ ] Find On-Demand instances with <30% utilization
    - [ ] Identify Spot replacement candidates
    - [ ] Return opportunity list
  - [ ] Implement `get_savings_projection()` - Projection calculation
    - [ ] Simulate Spot replacement
    - [ ] Calculate bin packing savings
    - [ ] Return ChartData schema

### 4.2 Bin Packing Module (MOD-PACK-01)
- [ ] Create `backend/modules/bin_packer.py`
  - [ ] Implement `analyze_fragmentation()` - Cluster analysis
    - [ ] Calculate node utilization
    - [ ] Identify consolidation opportunities
  - [ ] Implement `generate_migration_plan()` - Pod migration
    - [ ] Create migration plan JSON
    - [ ] Respect PodDisruptionBudgets
    - [ ] Return migration plan

### 4.3 Right-Sizing Module (MOD-SIZE-01)
- [ ] Create `backend/modules/rightsizer.py`
  - [ ] Implement `analyze_resource_usage()` - 14-day analysis
    - [ ] Query Prometheus metrics
    - [ ] Compare requests vs actual usage
  - [ ] Implement `generate_resize_recommendations()` - Recommendations
    - [ ] Suggest smaller instance types
    - [ ] Calculate potential savings

### 4.4 ML Model Server (MOD-AI-01)
- [ ] Create `backend/modules/ml_model_server.py`
  - [ ] Implement `predict_interruption_risk()` - ML prediction
    - [ ] Load trained model from file
    - [ ] Prepare feature vector (instance_type, AZ, price_history, hour, day)
    - [ ] Return interruption probability (0-1)
  - [ ] Implement `promote_model_to_production()` - Model graduation
    - [ ] Update ml_models table status
    - [ ] Broadcast Redis event for hot reload
  - [ ] Implement model validation contract checker
    - [ ] Verify input/output schema matches v1.0 contract

### 4.5 Model Validator (MOD-VAL-01)
- [ ] Create `backend/modules/model_validator.py`
  - [ ] Implement `validate_template_compatibility()` - Template validation
    - [ ] Check instance family vs architecture compatibility
    - [ ] Return warnings list
  - [ ] Implement `validate_ml_model()` - ML model validation
    - [ ] Spin up Docker sandbox
    - [ ] Load model and test with sample input
    - [ ] Verify output contract
    - [ ] Return validation result

### 4.6 Global Risk Tracker (SVC-RISK-GLB)
- [ ] Create `backend/modules/risk_tracker.py`
  - [ ] Implement `flag_risky_pool()` - Risk flagging
    - [ ] Set Redis key: `RISK:{region}:{az}:{instance_type}` = "DANGER"
    - [ ] Set TTL to 30 minutes
    - [ ] Increment interruption counter
  - [ ] Implement `check_pool_risk()` - Risk checking
    - [ ] Query Redis for risk flags
    - [ ] Return risk status

---

## Phase 5: Background Workers Implementation

### 5.1 Discovery Worker (WORK-DISC-01)
- [ ] Create `backend/workers/discovery_worker.py`
  - [ ] Implement `discovery_worker_loop()` - Main loop
    - [ ] Query DB for active accounts
    - [ ] For each account: assume IAM role via STS
    - [ ] Call AWS ec2.describe_instances()
    - [ ] Call AWS eks.list_clusters()
    - [ ] Calculate diff with previous state
    - [ ] Update instances table (UPSERT)
    - [ ] Fetch CloudWatch metrics
  - [ ] Implement `stream_discovery_status()` - WebSocket stream
    - [ ] Stream progress updates to frontend
  - [ ] Configure Celery task with 5-minute cron schedule

### 5.2 Optimizer Worker (WORK-OPT-01)
- [ ] Create `backend/workers/optimizer_worker.py`
  - [ ] Implement `trigger_manual_optimization()` - Manual trigger
    - [ ] Create Celery task
    - [ ] Return job_id
  - [ ] Implement optimization pipeline
    - [ ] Read cluster_policies from DB
    - [ ] Call MOD-SPOT-01.detect_opportunities()
    - [ ] Call MOD-AI-01.predict_interruption_risk()
    - [ ] Pass to CORE-DECIDE for conflict resolution
    - [ ] Execute action plan via CORE-EXEC

### 5.3 Hibernation Worker (WORK-HIB-01)
- [ ] Create `backend/workers/hibernation_worker.py`
  - [ ] Implement schedule checker (runs every 1 minute)
    - [ ] Query hibernation_schedules
    - [ ] Convert timezone to UTC
    - [ ] Check current time against schedule matrix
    - [ ] Trigger sleep/wake actions via AWS ASG scripts
  - [ ] Implement pre-warm logic (30 minutes before wake)

### 5.4 Report Generator (WORK-RPT-01)
- [ ] Create `backend/workers/report_worker.py`
  - [ ] Implement weekly report generation
    - [ ] Aggregate savings data
    - [ ] Generate email HTML template
    - [ ] Send via SendGrid/SES
  - [ ] Configure Celery task with weekly cron schedule

---

## Phase 6: Data Collection Services

### 6.1 Spot Advisor Scraper (SVC-SCRAPE-01)
- [ ] Create `backend/scrapers/spot_advisor_scraper.py`
  - [ ] Implement AWS Spot Advisor API scraper
    - [ ] Fetch interruption frequency data
    - [ ] Parse frequency buckets (<5%, 5-10%, 10-15%, 15-20%, >20%)
    - [ ] Store in interruption_rates table
  - [ ] Configure Celery task with 6-hour schedule

### 6.2 Pricing Collector (SVC-PRICE-01)
- [ ] Create `backend/scrapers/pricing_collector.py`
  - [ ] Implement AWS Price List API collector
    - [ ] Fetch real-time Spot prices
    - [ ] Fetch On-Demand prices
    - [ ] Store in Redis with 5-minute TTL
    - [ ] Data structure: `spot_prices:{region}:{instance_type}`
  - [ ] Configure Celery task with 5-minute schedule

---

## Phase 7: Core System Components

### 7.1 Decision Engine (CORE-DECIDE)
- [ ] Create `backend/core/decision_engine.py`
  - [ ] Implement `resolve_conflicts()` - Conflict resolution
    - [ ] Aggregate recommendations from all modules
    - [ ] Apply priority rules (Stability > Savings)
    - [ ] Example: Block deletion if replacement node is risky
    - [ ] Return final action plan JSON

### 7.2 Action Executor (CORE-EXEC)
- [ ] Create `backend/core/action_executor.py`
  - [ ] Implement `execute_action_plan()` - Main orchestration
    - [ ] Check Redis SAFE_MODE flag
    - [ ] If SAFE_MODE=TRUE, run in DryRun mode (log only)
    - [ ] Route each action to appropriate executor
    - [ ] Log to audit_logs table
    - [ ] Return execution results
  - [ ] Implement error handling and rollback logic

### 7.2.1 Hybrid Execution Router (CRITICAL - Worker-to-Agent Bridge)
> **Purpose**: Routes actions to the correct execution layer (AWS Boto3 vs Kubernetes Agent)

- [ ] Implement `route_action_execution()` - Action routing logic
  - [ ] **Input**: Action plan JSON from CORE-DECIDE
  - [ ] **Output**: Execution results or queue confirmation
  - [ ] **Routing Logic**:
    ```python
    for action in action_plan['actions']:
        if action['type'] in ['terminate_instance', 'launch_spot', 'detach_volume', 'update_asg']:
            # AWS Layer - Execute directly via Boto3
            result = execute_aws_action(action)
        elif action['type'] in ['evict_pod', 'cordon_node', 'drain_node', 'label_node', 'update_deployment']:
            # Kubernetes Layer - Queue for Agent
            result = queue_for_agent(action)
        else:
            raise ValueError(f"Unknown action type: {action['type']}")
    ```

- [ ] Implement `execute_aws_action()` - Direct AWS execution
  - [ ] Map action type to boto3 script:
    - [ ] `terminate_instance` → `scripts/aws/terminate_instance.py`
    - [ ] `launch_spot` → `scripts/aws/launch_spot.py`
    - [ ] `detach_volume` → `scripts/aws/detach_volume.py`
    - [ ] `update_asg` → `scripts/aws/update_asg.py`
  - [ ] Execute script with subprocess or direct import
  - [ ] Capture stdout/stderr
  - [ ] Return execution result immediately
  - [ ] Log to audit_logs with actor="System (Boto3)"

- [ ] Implement `queue_for_agent()` - Queue K8s actions for Agent
  - [ ] **Create record in `agent_action` table**:
    - [ ] cluster_id: from action payload
    - [ ] action_type: evict_pod/cordon_node/etc
    - [ ] payload: JSONB with action details (pod_name, namespace, etc)
    - [ ] status: 'pending'
    - [ ] created_at: current timestamp
    - [ ] expires_at: current timestamp + 5 minutes
  - [ ] **Emit WebSocket event** to wake up Agent immediately:
    - [ ] Channel: `agent:command:{cluster_id}`
    - [ ] Payload: `{"action_id": action_id, "type": action_type}`
    - [ ] Use Redis pub/sub from Phase 3.10
  - [ ] **Return queue confirmation** (not execution result):
    - [ ] `{"status": "queued", "action_id": action_id, "expires_at": timestamp}`
  - [ ] Log to audit_logs with actor="System (Queued for Agent)"

- [ ] Implement `check_agent_action_status()` - Poll for completion
  - [ ] Query `agent_action` table by action_id
  - [ ] Return current status (pending/picked_up/completed/failed)
  - [ ] If completed: return result from result JSONB field
  - [ ] If failed: return error_message
  - [ ] If expired: mark as failed with "timeout" error

- [ ] Implement cleanup job for expired actions
  - [ ] Celery task runs every 1 minute
  - [ ] Query `agent_action` where status='pending' AND expires_at < now()
  - [ ] Update status to 'failed' with error="Action expired"
  - [ ] Notify optimization_job of failure

### 7.3 API Gateway (CORE-API)
- [ ] Create `backend/core/api_gateway.py` - FastAPI application
  - [ ] Configure CORS middleware
  - [ ] Configure JWT authentication middleware
  - [ ] Configure rate limiting
  - [ ] Configure request logging
  - [ ] Mount all API route modules

---

## Phase 8: API Routes Implementation

### 8.1 Authentication Routes
- [ ] Create `backend/api/auth_routes.py`
  - [ ] POST `/api/auth/signup` - User registration
  - [ ] POST `/api/auth/token` - Login
  - [ ] POST `/api/auth/logout` - Logout
  - [ ] GET `/api/auth/me` - Current user context

### 8.2 Cluster Routes
- [ ] Create `backend/api/cluster_routes.py`
  - [ ] GET `/clusters` - List clusters
  - [ ] GET `/clusters/{id}` - Cluster details
  - [ ] GET `/clusters/discover` - Discover EKS clusters
  - [ ] POST `/clusters/connect` - Generate agent install
  - [ ] POST `/clusters/install` - Alternative install endpoint
  - [ ] GET `/clusters/{id}/verify` - Heartbeat check
  - [ ] POST `/clusters/{id}/optimize` - Manual optimization
  - [ ] WS `/clusters/heartbeat` - Heartbeat WebSocket
  - [ ] **POST `/clusters/{id}/heartbeat`** - Agent heartbeat (HTTP endpoint)
    - [ ] Update Redis with agent heartbeat timestamp
    - [ ] Include agent health metrics in request body
  - [ ] **POST `/clusters/{id}/agent/register`** - Agent self-registration
    - [ ] Called by Agent on startup
    - [ ] Receive agent version, K8s version, node count
    - [ ] Return configuration from backend

### 8.2.1 Agent Action Queue Endpoints (CRITICAL - Completes Worker-to-Agent Loop)
> **Purpose**: Enables Agent to fetch pending actions and report results

- [ ] **GET `/clusters/{id}/actions/pending`** - Fetch pending actions for Agent
  - [ ] **Authentication**: Require cluster-specific API token
  - [ ] **Query**: `SELECT * FROM agent_action WHERE cluster_id = {id} AND status = 'pending' ORDER BY created_at ASC`
  - [ ] **Atomic Lock**: Update status to 'picked_up' for returned actions
    - [ ] Use database transaction to prevent double-pickup
    - [ ] Set picked_up_at = current timestamp
  - [ ] **Response**: Array of action objects
    ```json
    [
      {
        "action_id": "uuid-1234",
        "action_type": "evict_pod",
        "payload": {
          "pod_name": "app-xyz-123",
          "namespace": "production",
          "grace_period_seconds": 30
        },
        "created_at": "2025-12-31T17:50:00Z",
        "expires_at": "2025-12-31T17:55:00Z"
      }
    ]
    ```
  - [ ] **Limit**: Return max 10 actions per request to prevent overload
  - [ ] **Filter expired**: Exclude actions where expires_at < now()

- [ ] **POST `/clusters/{id}/actions/{action_id}/result`** - Agent reports action result
  - [ ] **Authentication**: Require cluster-specific API token
  - [ ] **Request Body**:
    ```json
    {
      "status": "completed",  // or "failed"
      "result": {
        "pod_evicted": true,
        "new_node": "node-xyz",
        "duration_seconds": 12
      },
      "error_message": null  // or error string if failed
    }
    ```
  - [ ] **Update agent_action table**:
    - [ ] Set status = request.status
    - [ ] Set result = request.result (JSONB)
    - [ ] Set error_message = request.error_message
    - [ ] Set completed_at = current timestamp
  - [ ] **Update parent optimization_job** (if applicable):
    - [ ] If all actions completed: mark job as 'completed'
    - [ ] If any action failed: mark job as 'failed'
  - [ ] **Emit WebSocket event** to notify frontend:
    - [ ] Channel: `cluster:events:{cluster_id}`
    - [ ] Payload: `{"type": "action_completed", "action_id": action_id, "status": status}`
  - [ ] **Response**: `{"success": true, "acknowledged_at": timestamp}`

- [ ] **POST `/clusters/{id}/metrics`** - Agent sends collected metrics
  - [ ] Called by Agent every 30 seconds (from Phase 9.5.3)
  - [ ] Store metrics in database or time-series DB
  - [ ] Update instances table with latest utilization data

### 8.3 Template Routes
- [ ] Create `backend/api/template_routes.py`
  - [ ] GET `/templates` - List templates
  - [ ] POST `/templates` - Create template
  - [ ] PATCH `/templates/{id}/default` - Set default
  - [ ] POST `/templates/validate` - Validate template
  - [ ] DELETE `/templates/{id}` - Delete template

### 8.4 Policy Routes
- [ ] Create `backend/api/policy_routes.py`
  - [ ] PATCH `/policies/karpenter` - Karpenter toggle
  - [ ] PATCH `/policies/strategy` - Provisioning strategy
  - [ ] PATCH `/policies/binpack` - Bin packing settings
  - [ ] PATCH `/policies/fallback` - Spot fallback
  - [ ] PATCH `/policies/spread` - AZ spread
  - [ ] PATCH `/policies/rightsize` - Right-sizing mode
  - [ ] PATCH `/policies/buffer` - Safety buffer
  - [ ] PATCH `/policies/constraints` - Instance constraints
  - [ ] PATCH `/policies/exclusions` - Namespace exclusions

### 8.5 Hibernation Routes
- [ ] Create `backend/api/hibernation_routes.py`
  - [ ] POST `/hibernation/schedule` - Save schedule
  - [ ] POST `/hibernation/exception` - Calendar exception
  - [ ] POST `/hibernation/override` - Manual wake
  - [ ] PATCH `/hibernation/tz` - Timezone update
  - [ ] PATCH `/hibernation/prewarm` - Pre-warm toggle

### 8.6 Metrics Routes
- [ ] Create `backend/api/metrics_routes.py`
  - [ ] GET `/metrics/kpi` - Dashboard KPIs
  - [ ] GET `/metrics/projection` - Savings projection
  - [ ] GET `/metrics/composition` - Fleet composition
  - [ ] GET `/activity/live` - Activity feed

### 8.7 Audit Routes
- [ ] Create `backend/api/audit_routes.py`
  - [ ] GET `/audit` - Audit logs
  - [ ] GET `/audit/export` - Export with checksum
  - [ ] GET `/audit/{id}/diff` - Diff viewer
  - [ ] PATCH `/audit/retention` - Retention policy

### 8.8 Admin Routes
- [ ] Create `backend/api/admin_routes.py`
  - [ ] GET `/admin/clients` - Client registry
  - [ ] GET `/admin/stats` - Global stats
  - [ ] GET `/admin/health` - System health
  - [ ] GET `/admin/health/workers` - Worker status
  - [ ] POST `/admin/impersonate` - Impersonate client
  - [ ] PATCH `/clients/{id}/flags` - Feature flags
  - [ ] POST `/admin/reset-pass` - Password reset
  - [ ] DELETE `/admin/clients/{id}` - Delete client
  - [ ] WS `/admin/logs` - System log stream
  - [ ] WS `/admin/logs/live` - Live logs

### 8.9 Lab Routes
- [ ] Create `backend/api/lab_routes.py`
  - [ ] POST `/lab/live-switch` - Single instance switch
  - [ ] POST `/lab/parallel` - A/B test configuration
  - [ ] POST `/lab/parallel-config` - Save A/B config
  - [ ] GET `/lab/parallel-results` - A/B results
  - [ ] POST `/lab/graduate` - Promote model
  - [ ] GET `/admin/models` - Model registry
  - [ ] POST `/admin/models/upload` - Upload model
  - [ ] WS `/lab/stream/{id}` - Live telemetry stream

### 8.10 Settings Routes
- [ ] Create `backend/api/settings_routes.py`
  - [ ] GET `/settings/accounts` - List accounts
  - [ ] DELETE `/settings/accounts` - Disconnect account
  - [ ] PATCH `/settings/context` - Switch account context
  - [ ] GET `/settings/team` - Team members
  - [ ] POST `/settings/invite` - Invite team member
  - [ ] POST `/connect/verify` - Verify AWS connection
  - [ ] GET `/connect/stream` - Discovery stream
  - [ ] POST `/connect/link` - Link account
  - [ ] POST `/onboard/skip` - Skip onboarding

### 8.11 Billing Webhooks
- [ ] Create `backend/api/webhook_routes.py`
  - [ ] POST `/webhooks/stripe` - Handle Stripe webhook events
    - [ ] Implement Stripe signature verification middleware
    - [ ] Verify webhook signature using `stripe.Webhook.construct_event()`
    - [ ] Return 400 if signature invalid
  - [ ] Implement `handle_checkout_completed()` - Subscription created
    - [ ] Event: `checkout.session.completed`
    - [ ] Update user's plan in database
    - [ ] Send welcome email
    - [ ] Log to audit_logs
  - [ ] Implement `handle_subscription_updated()` - Plan changed
    - [ ] Event: `customer.subscription.updated`
    - [ ] Update plan tier and limits
    - [ ] Notify user of change
  - [ ] Implement `handle_subscription_deleted()` - Subscription cancelled
    - [ ] Event: `customer.subscription.deleted`
    - [ ] Downgrade to free plan
    - [ ] Lock premium features
    - [ ] Send cancellation confirmation email
  - [ ] Implement `handle_invoice_payment_succeeded()` - Payment successful
    - [ ] Event: `invoice.payment_succeeded`
    - [ ] Update payment status
    - [ ] Generate invoice PDF
    - [ ] Send receipt email
  - [ ] Implement `handle_invoice_payment_failed()` - Payment failed
    - [ ] Event: `invoice.payment_failed`
    - [ ] Notify user via email
    - [ ] Set grace period (7 days)
    - [ ] Log failed payment attempt
  - [ ] Implement idempotency handling
    - [ ] Store processed event IDs in database
    - [ ] Skip duplicate webhook events
  - [ ] Add webhook endpoint to CORS whitelist
  - [ ] Configure webhook URL in Stripe dashboard

---

## Phase 9: AWS Boto3 Scripts

### 9.1 Instance Management Scripts
- [ ] Create `scripts/aws/terminate_instance.py` (SCRIPT-TERM-01)
  - [ ] Implement graceful drain logic
  - [ ] Check PodDisruptionBudgets
  - [ ] Call ec2.terminate_instances()
  - [ ] Support DryRun mode
- [ ] Create `scripts/aws/launch_spot.py` (SCRIPT-SPOT-01)
  - [ ] Implement Spot Fleet request
  - [ ] Validate capacity
  - [ ] Call ec2.request_spot_fleet()
  - [ ] Support DryRun mode
- [ ] Create `scripts/aws/detach_volume.py` (SCRIPT-VOL-01)
  - [ ] Wait for unmount
  - [ ] Call ec2.detach_volume()
  - [ ] Support DryRun mode
- [ ] Create `scripts/aws/update_asg.py` (SCRIPT-ASG-01)
  - [ ] Validate min/max capacity
  - [ ] Call autoscaling.update_auto_scaling_group()
  - [ ] Support DryRun mode

---

## Phase 9.5: Kubernetes Agent Implementation (The "Probe")

> **CRITICAL**: This is the agent that runs inside the customer's Kubernetes cluster. Without this, the system cannot collect metrics or execute actions.

### 9.5.1 Agent Core Architecture
- [ ] Create `agent/` directory structure
  - [ ] `agent/main.py` - Entry point
  - [ ] `agent/config.py` - Configuration loader
  - [ ] `agent/collector.py` - Metrics collection
  - [ ] `agent/actuator.py` - Command execution
  - [ ] `agent/heartbeat.py` - Health reporting
  - [ ] `agent/websocket_client.py` - Real-time communication
  - [ ] `agent/utils/` - Utility functions
  - [ ] `agent/models/` - Data models

### 9.5.2 Agent Entry Point & Configuration
- [ ] Create `agent/main.py`
  - [ ] Implement startup sequence
    - [ ] Load configuration from environment variables
    - [ ] Required env vars: `API_URL`, `CLUSTER_ID`, `API_TOKEN`, `NAMESPACE`
    - [ ] Optional env vars: `LOG_LEVEL`, `COLLECTION_INTERVAL`, `HEARTBEAT_INTERVAL`
  - [ ] Implement self-registration/handshake with backend
    - [ ] POST to `/clusters/{cluster_id}/agent/register`
    - [ ] Send agent version, K8s version, node count
    - [ ] Receive configuration from backend
  - [ ] Start background tasks (collector, heartbeat, actuator)
  - [ ] Implement graceful shutdown handler
  - [ ] Setup structured logging (JSON format)
- [ ] Create `agent/config.py`
  - [ ] Implement `Config` class with validation
  - [ ] Validate API_URL format
  - [ ] Validate API_TOKEN is not empty
  - [ ] Set default values for optional configs
  - [ ] Implement config reload on SIGHUP

### 9.5.3 Metrics Collector
- [ ] Create `agent/collector.py`
  - [ ] Initialize Kubernetes client using `kubernetes` Python library
    - [ ] Use in-cluster config (ServiceAccount)
    - [ ] Fallback to kubeconfig for local testing
  - [ ] Implement `collect_pod_metrics()` - Pod-level metrics
    - [ ] Query Metrics Server API for CPU/RAM usage
    - [ ] Collect pod status (Running, Pending, Failed)
    - [ ] Collect pod resource requests and limits
    - [ ] Group by namespace and node
  - [ ] Implement `collect_node_metrics()` - Node-level metrics
    - [ ] Query node allocatable resources
    - [ ] Calculate node utilization (requested / allocatable)
    - [ ] Collect node conditions (Ready, DiskPressure, MemoryPressure)
    - [ ] Identify Spot vs On-Demand nodes (via labels)
  - [ ] Implement `collect_cluster_events()` - Event watcher
    - [ ] Watch for Pod events (Pending, Evicted, OOMKilled)
    - [ ] Watch for Node events (NodeNotReady, NodeScaleUp)
    - [ ] Watch for Spot interruption warnings (if available)
    - [ ] Filter events by timestamp (only new events)
  - [ ] Implement `send_metrics_to_backend()`
    - [ ] Batch metrics into JSON payload
    - [ ] POST to `/clusters/{cluster_id}/metrics`
    - [ ] Include timestamp and agent_id
    - [ ] Retry on failure with exponential backoff
  - [ ] Run collection loop every 30 seconds (configurable)
  - [ ] Handle Kubernetes API errors gracefully

### 9.5.4 Action Actuator
- [ ] Create `agent/actuator.py`
  - [ ] Implement polling mechanism for action plans
    - [ ] GET `/clusters/{cluster_id}/actions/pending` every 60 seconds
    - [ ] Parse action plan JSON from backend
  - [ ] Implement command execution handlers
    - [ ] `evict_pod()` - Gracefully evict pod
      - [ ] Check PodDisruptionBudget before eviction
      - [ ] Use Kubernetes Eviction API
      - [ ] Wait for pod to terminate
      - [ ] Report success/failure to backend
    - [ ] `cordon_node()` - Mark node as unschedulable
      - [ ] Use `kubectl cordon` equivalent
      - [ ] Prevent new pods from scheduling
    - [ ] `drain_node()` - Drain node for replacement
      - [ ] Evict all pods respecting PDBs
      - [ ] Wait for all pods to be rescheduled
      - [ ] Report drain completion
    - [ ] `label_node()` - Add/remove node labels
      - [ ] Used for targeting specific workloads
    - [ ] `update_deployment()` - Update deployment spec
      - [ ] Change resource requests/limits (right-sizing)
      - [ ] Trigger rolling update
  - [ ] Implement security: Signature verification for commands
    - [ ] Each action plan includes HMAC signature
    - [ ] Verify signature using shared secret (API_TOKEN)
    - [ ] Reject unsigned or invalid commands
  - [ ] Implement dry-run mode
    - [ ] If `DRY_RUN=true`, log actions without executing
    - [ ] Report what would have been done
  - [ ] Report action results to backend
    - [ ] POST `/clusters/{cluster_id}/actions/{action_id}/result`
    - [ ] Include success/failure status
    - [ ] Include error message if failed
    - [ ] Include execution duration

### 9.5.5 Heartbeat & Health Reporting
- [ ] Create `agent/heartbeat.py`
  - [ ] Implement heartbeat sender
    - [ ] POST to `/clusters/{cluster_id}/heartbeat` every 30 seconds
    - [ ] Include local health metrics:
      - [ ] Agent memory usage
      - [ ] Agent CPU usage
      - [ ] Number of errors in last minute
      - [ ] Last successful metric collection timestamp
      - [ ] Kubernetes API connectivity status
    - [ ] Include agent version and uptime
  - [ ] Implement health check endpoint (for K8s liveness probe)
    - [ ] HTTP server on port 8080
    - [ ] GET `/healthz` - Returns 200 if healthy
    - [ ] GET `/readyz` - Returns 200 if ready to serve
  - [ ] Implement self-healing
    - [ ] Restart collector if it crashes
    - [ ] Reconnect to backend if connection lost
    - [ ] Exponential backoff for retries

### 9.5.6 WebSocket Client for Real-Time Communication
- [ ] Create `agent/websocket_client.py`
  - [ ] Implement WebSocket connection to backend
    - [ ] Connect to `wss://{API_URL}/clusters/{cluster_id}/stream`
    - [ ] Include API_TOKEN in connection headers
    - [ ] Authenticate connection on upgrade
  - [ ] Implement message handlers
    - [ ] `on_action_command` - Receive real-time action commands
      - [ ] Trigger actuator immediately (don't wait for polling)
    - [ ] `on_config_update` - Receive configuration updates
      - [ ] Update collection interval
      - [ ] Update enabled features
    - [ ] `on_ping` - Respond to keep-alive pings
  - [ ] Implement reconnection logic
    - [ ] Detect connection loss
    - [ ] Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 60s)
    - [ ] Resume from last known state
  - [ ] Implement message queue for offline buffering
    - [ ] Buffer metrics if WebSocket disconnected
    - [ ] Send buffered data when reconnected
    - [ ] Limit buffer size to prevent memory issues

### 9.5.7 Agent Packaging - Docker Image
- [ ] Create `agent/Dockerfile`
  - [ ] Base image: `python:3.11-slim`
  - [ ] Install system dependencies
    - [ ] `curl` for health checks
    - [ ] `ca-certificates` for HTTPS
  - [ ] Copy `requirements.txt` and install Python packages
    - [ ] `kubernetes` - Kubernetes Python client
    - [ ] `websockets` - WebSocket client
    - [ ] `requests` - HTTP client
    - [ ] `prometheus-client` - Metrics export (optional)
  - [ ] Copy agent source code
  - [ ] Set working directory to `/app`
  - [ ] Create non-root user `agent` (UID 1000)
  - [ ] Switch to non-root user
  - [ ] Expose port 8080 for health checks
  - [ ] Set entrypoint: `python main.py`
  - [ ] Add health check: `HEALTHCHECK CMD curl -f http://localhost:8080/healthz || exit 1`
- [ ] Build and tag Docker image
  - [ ] Tag: `spotoptimizer/agent:v1.0.0`
  - [ ] Tag: `spotoptimizer/agent:latest`
- [ ] Push to container registry
  - [ ] Docker Hub or private registry
  - [ ] Ensure image is publicly accessible (or provide pull secrets)

### 9.5.8 Agent Packaging - Helm Chart
- [ ] Create `charts/spot-optimizer-agent/` directory structure
- [ ] Create `charts/spot-optimizer-agent/Chart.yaml`
  - [ ] Chart name: `spot-optimizer-agent`
  - [ ] Version: `1.0.0`
  - [ ] App version: `1.0.0`
  - [ ] Description: "Kubernetes agent for Spot Optimizer platform"
  - [ ] Maintainers information
- [ ] Create `charts/spot-optimizer-agent/values.yaml`
  - [ ] Default values:
    - [ ] `image.repository`: `spotoptimizer/agent`
    - [ ] `image.tag`: `latest`
    - [ ] `image.pullPolicy`: `IfNotPresent`
    - [ ] `replicaCount`: `1`
    - [ ] `resources.requests.memory`: `128Mi`
    - [ ] `resources.requests.cpu`: `100m`
    - [ ] `resources.limits.memory`: `256Mi`
    - [ ] `resources.limits.cpu`: `200m`
    - [ ] `config.apiUrl`: `https://api.spotoptimizer.com`
    - [ ] `config.clusterId`: `""` (user must provide)
    - [ ] `config.apiToken`: `""` (user must provide)
    - [ ] `config.namespace`: `spot-optimizer`
    - [ ] `config.collectionInterval`: `30`
    - [ ] `config.heartbeatInterval`: `30`
    - [ ] `config.logLevel`: `INFO`
- [ ] Create `charts/spot-optimizer-agent/templates/deployment.yaml`
  - [ ] Deployment spec with 1 replica
  - [ ] Container spec with image from values
  - [ ] Environment variables from ConfigMap and Secret
  - [ ] Resource requests and limits
  - [ ] Liveness probe: `GET /healthz` every 30s
  - [ ] Readiness probe: `GET /readyz` every 10s
  - [ ] Security context: run as non-root
  - [ ] Volume mounts for ServiceAccount token
- [ ] Create `charts/spot-optimizer-agent/templates/configmap.yaml`
  - [ ] ConfigMap with non-sensitive configuration
    - [ ] API_URL
    - [ ] CLUSTER_ID
    - [ ] NAMESPACE
    - [ ] COLLECTION_INTERVAL
    - [ ] HEARTBEAT_INTERVAL
    - [ ] LOG_LEVEL
- [ ] Create `charts/spot-optimizer-agent/templates/secret.yaml`
  - [ ] Secret with sensitive data
    - [ ] API_TOKEN (base64 encoded)
  - [ ] Note: User must provide this value during installation
- [ ] Create `charts/spot-optimizer-agent/templates/serviceaccount.yaml`
  - [ ] ServiceAccount: `spot-optimizer-agent`
  - [ ] Used by agent pod for Kubernetes API access
- [ ] Create `charts/spot-optimizer-agent/templates/rbac.yaml`
  - [ ] ClusterRole: `spot-optimizer-agent`
    - [ ] Permissions:
      - [ ] `get`, `list`, `watch` on `pods`, `nodes`, `events`
      - [ ] `get`, `list` on `deployments`, `replicasets`, `statefulsets`
      - [ ] `create` on `pods/eviction` (for pod eviction)
      - [ ] `patch`, `update` on `nodes` (for cordon/drain)
      - [ ] `get` on `poddisruptionbudgets` (to respect PDBs)
  - [ ] ClusterRoleBinding: `spot-optimizer-agent`
    - [ ] Bind ClusterRole to ServiceAccount
- [ ] Create `charts/spot-optimizer-agent/templates/service.yaml`
  - [ ] Service for health check endpoint (optional)
  - [ ] Type: ClusterIP
  - [ ] Port: 8080
- [ ] Create `charts/spot-optimizer-agent/templates/NOTES.txt`
  - [ ] Post-installation instructions
  - [ ] How to verify agent is running
  - [ ] How to check logs: `kubectl logs -n spot-optimizer deployment/spot-optimizer-agent`
  - [ ] How to verify connection: Check backend dashboard for heartbeat

### 9.5.9 Agent Testing
- [ ] Create unit tests for agent components
  - [ ] Test collector with mocked Kubernetes API
  - [ ] Test actuator command handlers
  - [ ] Test heartbeat sender
  - [ ] Test WebSocket reconnection logic
- [ ] Create integration tests
  - [ ] Deploy agent to test cluster (kind or minikube)
  - [ ] Verify metrics collection
  - [ ] Verify heartbeat reception
  - [ ] Test action execution (evict pod, cordon node)
- [ ] Create end-to-end test
  - [ ] Install agent via Helm
  - [ ] Verify agent registers with backend
  - [ ] Trigger manual optimization from UI
  - [ ] Verify agent executes action
  - [ ] Verify results reported to backend

### 9.5.10 Agent Documentation
- [ ] Create `agent/README.md`
  - [ ] Architecture overview
  - [ ] Installation instructions
  - [ ] Configuration reference
  - [ ] Troubleshooting guide
- [ ] Create `charts/spot-optimizer-agent/README.md`
  - [ ] Helm chart documentation
  - [ ] Values reference
  - [ ] Installation examples
  - [ ] Upgrade guide
- [ ] Create agent deployment guide
  - [ ] Prerequisites (Metrics Server, RBAC)
  - [ ] Step-by-step installation
  - [ ] Verification steps
  - [ ] Uninstallation steps

---

## Phase 10: Frontend Implementation

### 10.1 Core Frontend Setup
- [ ] Create `frontend/src/App.jsx` - Root component
  - [ ] Setup React Router
  - [ ] Setup User Context Provider
  - [ ] Setup authentication state management
  - [ ] Define route structure
- [ ] Create `frontend/src/index.css` - Global styles
  - [ ] Define CSS variables for colors
  - [ ] Define typography system
  - [ ] Define spacing system
  - [ ] Define animation utilities
  - [ ] Implement dark mode support

### 10.2 Authentication Components
- [ ] Create `frontend/src/components/auth/LoginPage.jsx`
  - [ ] Sign-up form with validation
  - [ ] Sign-in form with validation
  - [ ] Toggle between sign-up and sign-in
  - [ ] Call POST `/api/auth/signup` and POST `/api/auth/token`
  - [ ] Store JWT in localStorage
  - [ ] Feature IDs: `any-auth-form-reuse-dep-submit-signup`, `any-auth-form-reuse-dep-submit-signin`
- [ ] Create `frontend/src/components/auth/AuthGateway.jsx`
  - [ ] Call GET `/api/auth/me` on mount
  - [ ] Redirect based on account status
  - [ ] Feature ID: `any-auth-gateway-unique-indep-run-route`
- [ ] Create `frontend/src/components/auth/ClientSetup.jsx` - Onboarding wizard
  - [ ] Welcome screen with value proposition
  - [ ] Production/Lab mode selection cards
  - [ ] AWS connection form
  - [ ] Test connection button → POST `/connect/verify`
  - [ ] Discovery progress bar → GET `/connect/stream` (WebSocket)
  - [ ] Skip wizard button
  - [ ] Feature IDs: `client-onboard-wizard-unique-indep-view-step1`, `client-onboard-button-reuse-dep-click-verify`, `client-onboard-bar-reuse-indep-view-scan`

### 10.3 Dashboard Components
- [ ] Create `frontend/src/components/dashboard/Dashboard.jsx`
  - [ ] KPI cards (Monthly Spend, Net Savings, Fleet Health, Active Nodes)
  - [ ] Call GET `/metrics/kpi`
  - [ ] Savings projection bar chart → GET `/metrics/projection`
  - [ ] Fleet composition pie chart → GET `/metrics/composition`
  - [ ] Real-time activity feed → GET `/activity/live`
  - [ ] Feature IDs: `client-home-kpi-reuse-indep-view-spend`, `client-home-chart-unique-indep-view-proj`, `client-home-feed-unique-indep-view-live`
- [ ] Create `frontend/src/components/dashboard/KPICard.jsx` - Reusable KPI card
- [ ] Create `frontend/src/components/dashboard/ActivityFeed.jsx` - Activity feed component

### 10.4 Cluster Components
- [ ] Create `frontend/src/components/clusters/ClusterRegistry.jsx`
  - [ ] Cluster table → GET `/clusters`
  - [ ] Add cluster button → modal with GET `/clusters/discover`
  - [ ] Connect cluster button → POST `/clusters/connect`
  - [ ] Cluster detail drawer → GET `/clusters/{id}`
  - [ ] Optimize now button → POST `/clusters/{id}/optimize`
  - [ ] Heartbeat status indicator → GET `/clusters/{id}/verify`
  - [ ] Feature IDs: `client-cluster-table-unique-indep-view-list`, `client-cluster-button-reuse-dep-click-connect`, `client-cluster-button-reuse-dep-click-opt`
- [ ] Create `frontend/src/components/clusters/ClusterDetailDrawer.jsx` - Drawer component

### 10.5 Template Components
- [ ] Create `frontend/src/components/templates/NodeTemplates.jsx`
  - [ ] Template grid → GET `/templates`
  - [ ] Set default star → PATCH `/templates/{id}/default`
  - [ ] Delete template → DELETE `/templates/{id}`
  - [ ] Create template wizard
  - [ ] Feature IDs: `client-tmpl-list-unique-indep-view-grid`, `client-tmpl-toggle-reuse-dep-click-default`
- [ ] Create `frontend/src/components/templates/TemplateWizard.jsx`
  - [ ] Step 1: Family selector
  - [ ] Step 2: Purchasing strategy
  - [ ] Step 3: Storage configuration
  - [ ] Live validation → POST `/templates/validate`
  - [ ] Feature ID: `client-tmpl-logic-unique-indep-run-validate`

### 10.6 Policy Components
- [ ] Create `frontend/src/components/policies/OptimizationPolicies.jsx`
  - [ ] Infrastructure tab with Karpenter toggle → PATCH `/policies/karpenter`
  - [ ] Strategy selector → PATCH `/policies/strategy`
  - [ ] Bin pack slider → PATCH `/policies/binpack`
  - [ ] Workload tab with right-sizing mode
  - [ ] Safety buffer slider
  - [ ] Namespace exclusions input
  - [ ] Spot fallback checkbox
  - [ ] AZ spread checkbox
  - [ ] Feature IDs: `client-pol-toggle-reuse-dep-click-karpenter`, `client-pol-slider-reuse-dep-drag-binpack`

### 10.7 Hibernation Components
- [ ] Create `frontend/src/components/hibernation/Hibernation.jsx`
  - [ ] Weekly schedule grid (24x7) with drag-to-paint → POST `/hibernation/schedule`
  - [ ] Calendar exceptions picker
  - [ ] Wake up now button → POST `/hibernation/override`
  - [ ] Timezone selector → PATCH `/hibernation/tz`
  - [ ] Pre-warm checkbox → PATCH `/hibernation/prewarm`
  - [ ] Feature IDs: `client-hib-grid-unique-indep-drag-paint`, `client-hib-button-unique-indep-click-wake`

### 10.8 Audit Components
- [ ] Create `frontend/src/components/audit/AuditLogs.jsx`
  - [ ] Audit logs table → GET `/audit`
  - [ ] Export button → GET `/audit/export`
  - [ ] Diff viewer drawer → GET `/audit/{id}/diff`
  - [ ] Retention policy slider
  - [ ] Feature IDs: `client-audit-table-unique-indep-view-ledger`, `client-audit-drawer-unique-dep-view-diff`

### 10.9 Settings Components
- [ ] Create `frontend/src/components/settings/Settings.jsx`
  - [ ] Multi-account list → GET `/settings/accounts`
  - [ ] Disconnect account button → DELETE `/settings/accounts`
  - [ ] Link new account button
  - [ ] Account context switcher → PATCH `/settings/context`
  - [ ] Team members list → GET `/settings/team`
  - [ ] Invite team member → POST `/settings/invite`
  - [ ] Feature IDs: `client-set-list-unique-indep-view-accts`, `client-set-button-reuse-dep-click-link`
- [ ] Create `frontend/src/components/settings/CloudIntegrations.jsx` - Cloud account management

### 10.10 Admin Components
- [ ] Create `frontend/src/components/admin/AdminDashboard.jsx`
  - [ ] Global business metrics → GET `/admin/stats`
  - [ ] System health lights → GET `/admin/health`
  - [ ] Client registry → GET `/admin/clients`
  - [ ] Feature flag toggles → PATCH `/clients/{id}/flags`
  - [ ] Impersonate button → POST `/admin/impersonate`
  - [ ] Feature IDs: `admin-dash-kpi-reuse-indep-view-global`, `admin-client-list-unique-indep-view-reg`
- [ ] Create `frontend/src/components/admin/TheLab.jsx`
  - [ ] Single-instance live switch form → POST `/lab/live-switch`
  - [ ] A/B test configuration → POST `/lab/parallel`
  - [ ] Comparison graphs → WS `/lab/stream/{id}`
  - [ ] Graduate to production button → POST `/lab/graduate`
  - [ ] Model registry → GET `/admin/models`
  - [ ] Feature IDs: `admin-lab-form-reuse-dep-submit-live`, `admin-lab-chart-unique-indep-view-abtest`
- [ ] Create `frontend/src/components/admin/SystemHealth.jsx`
  - [ ] Worker status traffic lights → GET `/admin/health/workers`
  - [ ] Live logs button → WS `/admin/logs/live`
  - [ ] Feature ID: `admin-health-traffic-unique-indep-view-workers`

### 10.11 API Services
- [ ] Create `frontend/src/services/api.js` - Axios configuration
  - [ ] Base URL configuration
  - [ ] Request interceptor for JWT token
  - [ ] Response interceptor for error handling
  - [ ] Refresh token logic
- [ ] Create `frontend/src/services/authService.js` - Auth API calls
- [ ] Create `frontend/src/services/clusterService.js` - Cluster API calls
- [ ] Create `frontend/src/services/metricsService.js` - Metrics API calls

### 10.12 Custom Hooks
- [ ] Create `frontend/src/hooks/useAuth.js` - Authentication hook
  - [ ] Login, logout, token management
  - [ ] User context state
- [ ] Create `frontend/src/hooks/useClusters.js` - Cluster data hook
  - [ ] Fetch clusters, cache, refresh
- [ ] Create `frontend/src/hooks/useMetrics.js` - Metrics data hook
  - [ ] Fetch KPIs, auto-refresh

### 10.13 Utilities
- [ ] Create `frontend/src/utils/formatters.js` - Data formatters
  - [ ] Currency formatter
  - [ ] Date/time formatter
  - [ ] Number formatter
- [ ] Create `frontend/src/utils/validators.js` - Form validators
  - [ ] Email validation
  - [ ] Password strength
  - [ ] AWS ARN validation

---

## Phase 11: Testing & Quality Assurance

### 11.1 Backend Unit Tests
- [ ] Create tests for authentication service
  - [ ] Test user creation with valid/invalid data
  - [ ] Test login with correct/incorrect credentials
  - [ ] Test JWT token generation and validation
- [ ] Create tests for cluster service
  - [ ] Test cluster listing
  - [ ] Test agent install command generation
- [ ] Create tests for optimization modules
  - [ ] Test MOD-SPOT-01 instance selection logic
  - [ ] Test MOD-PACK-01 bin packing algorithm
- [ ] Create tests for workers
  - [ ] Test discovery worker with mocked AWS responses
  - [ ] Test optimizer worker pipeline
- [ ] Achieve >80% code coverage

### 11.2 Frontend Unit Tests
- [ ] Create tests for authentication components
  - [ ] Test login form submission
  - [ ] Test sign-up form validation
- [ ] Create tests for dashboard components
  - [ ] Test KPI card rendering
  - [ ] Test chart data visualization
- [ ] Create tests for custom hooks
  - [ ] Test useAuth hook state management
  - [ ] Test API call error handling
- [ ] Achieve >70% code coverage

### 11.3 Integration Tests
- [ ] Create end-to-end tests for authentication flow
  - [ ] Sign up → Login → Dashboard
- [ ] Create end-to-end tests for cluster management
  - [ ] Add cluster → Connect → Optimize
- [ ] Create end-to-end tests for policy updates
  - [ ] Update Karpenter → Verify broadcast to agents
- [ ] Use Playwright or Cypress for browser automation

### 11.4 API Tests
- [ ] Create Postman/Newman collection for all API endpoints
- [ ] Test all authentication endpoints
- [ ] Test all CRUD operations
- [ ] Test WebSocket connections
- [ ] Test rate limiting
- [ ] Test error responses

---

## Phase 12: Deployment & DevOps

### 12.1 CI/CD Pipeline
- [ ] Create `.github/workflows/ci.yml` - Continuous Integration
  - [ ] Run backend unit tests
  - [ ] Run frontend unit tests
  - [ ] Run linters (pylint, eslint)
  - [ ] Build Docker images
  - [ ] Push to container registry
- [ ] Create `.github/workflows/deploy.yml` - Continuous Deployment
  - [ ] Deploy to staging environment
  - [ ] Run integration tests
  - [ ] Deploy to production (manual approval)

### 12.2 Deployment Scripts
- [ ] Create `scripts/deployment/deploy.sh`
  - [ ] Pull latest code
  - [ ] Build Docker images
  - [ ] Run database migrations
  - [ ] Start services with docker-compose
  - [ ] Health check verification
- [ ] Create `scripts/deployment/setup.sh`
  - [ ] Initial server setup
  - [ ] Install Docker and docker-compose
  - [ ] Configure firewall
  - [ ] Setup SSL certificates

### 12.3 Infrastructure as Code
- [ ] Create Terraform configuration for AWS resources
  - [ ] VPC and networking
  - [ ] RDS PostgreSQL instance
  - [ ] ElastiCache Redis cluster
  - [ ] EC2 instances for backend
  - [ ] Application Load Balancer
  - [ ] Route53 DNS configuration
  - [ ] S3 buckets for storage
- [ ] Create Kubernetes manifests (if using EKS)
  - [ ] Deployments for backend, frontend, workers
  - [ ] Services and Ingress
  - [ ] ConfigMaps and Secrets
  - [ ] HorizontalPodAutoscaler

### 12.4 Monitoring & Logging
- [ ] Setup Prometheus for metrics collection
  - [ ] Backend API metrics
  - [ ] Worker queue metrics
  - [ ] Database metrics
- [ ] Setup Grafana dashboards
  - [ ] System health dashboard
  - [ ] API performance dashboard
  - [ ] Worker queue dashboard
- [ ] Setup centralized logging (ELK stack or CloudWatch)
  - [ ] Collect logs from all services
  - [ ] Create log aggregation queries
  - [ ] Setup alerts for errors

### 12.5 Security Hardening
- [ ] Implement rate limiting on all API endpoints
- [ ] Setup WAF (Web Application Firewall)
- [ ] Enable HTTPS with SSL certificates
- [ ] Implement CSRF protection
- [ ] Setup database encryption at rest
- [ ] Implement secrets management (AWS Secrets Manager or Vault)
- [ ] Regular security audits and dependency updates

---

## Phase 13: Documentation & Knowledge Transfer

### 13.1 API Documentation
- [ ] Generate OpenAPI/Swagger documentation
  - [ ] Document all endpoints with examples
  - [ ] Include request/response schemas
  - [ ] Add authentication requirements
- [ ] Create Postman collection with examples
- [ ] Host API documentation (Swagger UI or ReDoc)

### 13.2 Developer Documentation
- [ ] Create `README.md` for project overview
  - [ ] Architecture overview
  - [ ] Setup instructions
  - [ ] Development workflow
- [ ] Create `CONTRIBUTING.md` for contribution guidelines
- [ ] Create `docs/ARCHITECTURE.md` - Detailed architecture
- [ ] Create `docs/DEPLOYMENT.md` - Deployment guide
- [ ] Create `docs/TROUBLESHOOTING.md` - Common issues

### 13.3 User Documentation
- [ ] Create user guide for client portal
  - [ ] Getting started guide
  - [ ] Feature walkthroughs
  - [ ] FAQ section
- [ ] Create admin guide for platform owner
  - [ ] The Lab usage guide
  - [ ] Client management guide
  - [ ] System monitoring guide
- [ ] Create video tutorials for key features

### 13.4 Runbooks
- [ ] Create runbook for database backup and restore
- [ ] Create runbook for scaling workers
- [ ] Create runbook for incident response
- [ ] Create runbook for model deployment

---

## Phase 14: Production Readiness

### 14.1 Performance Optimization
- [ ] Database query optimization
  - [ ] Add missing indexes
  - [ ] Optimize slow queries
  - [ ] Implement query caching
- [ ] API response caching
  - [ ] Cache KPI metrics (5-minute TTL)
  - [ ] Cache cluster list (1-minute TTL)
- [ ] Frontend optimization
  - [ ] Code splitting
  - [ ] Lazy loading components
  - [ ] Image optimization
  - [ ] Bundle size reduction

### 14.2 Scalability Testing
- [ ] Load testing with 1000 concurrent users
- [ ] Stress testing worker queues
- [ ] Database connection pool tuning
- [ ] Redis memory optimization
- [ ] Horizontal scaling verification

### 14.3 Disaster Recovery
- [ ] Setup automated database backups (daily)
- [ ] Test database restore procedure
- [ ] Setup Redis persistence
- [ ] Create disaster recovery plan
- [ ] Document RTO and RPO targets

### 14.4 Compliance & Audit
- [ ] Implement GDPR compliance features
  - [ ] Data export functionality
  - [ ] Data deletion functionality
  - [ ] Privacy policy
- [ ] Implement SOC 2 controls
  - [ ] Audit logging (already implemented)
  - [ ] Access controls
  - [ ] Encryption
- [ ] Create compliance documentation

### 14.5 Static Data Seeding
> **CRITICAL**: Without this data, the optimizer modules (MOD-SPOT-01, MOD-SIZE-01) cannot function. This must be completed before production deployment.

- [ ] Create `scripts/seed_cloud_data.py` - Master seeding script
  - [ ] Implement database connection using SQLAlchemy
  - [ ] Implement idempotent seeding (check if data exists before inserting)
  - [ ] Add logging for each seeding step
  - [ ] Add error handling and rollback on failure

- [ ] Seed AWS Regions table
  - [ ] Create `aws_regions` table if not exists
    - [ ] Columns: `id`, `region_code`, `region_name`, `location`, `enabled`
  - [ ] Populate all AWS regions:
    - [ ] us-east-1 (N. Virginia)
    - [ ] us-east-2 (Ohio)
    - [ ] us-west-1 (N. California)
    - [ ] us-west-2 (Oregon)
    - [ ] eu-west-1 (Ireland)
    - [ ] eu-west-2 (London)
    - [ ] eu-west-3 (Paris)
    - [ ] eu-central-1 (Frankfurt)
    - [ ] ap-south-1 (Mumbai)
    - [ ] ap-southeast-1 (Singapore)
    - [ ] ap-southeast-2 (Sydney)
    - [ ] ap-northeast-1 (Tokyo)
    - [ ] ap-northeast-2 (Seoul)
    - [ ] sa-east-1 (São Paulo)
    - [ ] ca-central-1 (Canada)
  - [ ] Mark commonly used regions as enabled by default

- [ ] Seed Instance Families table
  - [ ] Create `instance_families` table if not exists
    - [ ] Columns: `id`, `family_code`, `family_name`, `category`, `description`
  - [ ] Populate instance families:
    - [ ] General Purpose: t3, t3a, t4g, m5, m5a, m5n, m6i, m6a, m7i
    - [ ] Compute Optimized: c5, c5a, c5n, c6i, c6a, c7i
    - [ ] Memory Optimized: r5, r5a, r5n, r6i, r6a, r7i, x2idn, x2iedn
    - [ ] Storage Optimized: i3, i3en, i4i, d2, d3, d3en
    - [ ] Accelerated Computing: p3, p4, g4dn, g5, inf1, inf2
  - [ ] Include category and description for each family

- [ ] Seed Instance Specifications table
  - [ ] Create `instance_specs` table if not exists
    - [ ] Columns: `id`, `instance_type`, `family_id`, `vcpu`, `memory_gb`, `architecture`, `network_performance`, `ebs_optimized`, `spot_eligible`
  - [ ] Populate specifications for all instance types (500+ types)
    - [ ] Use AWS EC2 DescribeInstanceTypes API to fetch latest specs
    - [ ] Or use pre-generated JSON file with instance specs
  - [ ] Key specifications to include:
    - [ ] vCPU count (e.g., 2, 4, 8, 16, 32, 64, 96)
    - [ ] Memory in GB (e.g., 4, 8, 16, 32, 64, 128, 256)
    - [ ] Architecture (x86_64 or ARM64)
    - [ ] Network performance (Low, Moderate, High, Up to 10 Gbps, etc.)
    - [ ] EBS optimized (boolean)
    - [ ] Spot eligible (boolean - some instance types not available as Spot)
  - [ ] **Critical for Right-Sizing**: This data is used by MOD-SIZE-01 to recommend appropriate instance types

- [ ] Seed Instance Pricing (Initial/Baseline)
  - [ ] Create `instance_pricing` table if not exists
    - [ ] Columns: `id`, `instance_type`, `region`, `on_demand_price`, `spot_price_avg`, `last_updated`
  - [ ] Populate baseline On-Demand pricing
    - [ ] Use AWS Price List API
    - [ ] Or use pre-generated pricing file
  - [ ] Populate average Spot pricing (last 30 days)
    - [ ] Use AWS EC2 DescribeSpotPriceHistory API
    - [ ] Calculate average for each instance type per region
  - [ ] Note: Real-time Spot prices will be updated by SVC-PRICE-01 worker

- [ ] Seed Spot Interruption Rates (Baseline)
  - [ ] Create `interruption_rates` table if not exists
    - [ ] Columns: `id`, `instance_type`, `region`, `az`, `frequency_bucket`, `last_updated`
  - [ ] Populate baseline interruption data
    - [ ] Use AWS Spot Advisor data
    - [ ] Frequency buckets: <5%, 5-10%, 10-15%, 15-20%, >20%
  - [ ] Note: This will be updated by SVC-SCRAPE-01 worker every 6 hours

- [ ] Seed Default Node Templates
  - [ ] Create default templates for common use cases:
    - [ ] "General Purpose - Balanced"
      - [ ] Families: m5, m6i, m7i
      - [ ] Strategy: SPOT with On-Demand fallback
      - [ ] Architecture: x86_64
    - [ ] "Compute Optimized - High Performance"
      - [ ] Families: c5, c6i, c7i
      - [ ] Strategy: SPOT
      - [ ] Architecture: x86_64
    - [ ] "Memory Optimized - Large Workloads"
      - [ ] Families: r5, r6i, r7i
      - [ ] Strategy: HYBRID (50% Spot, 50% On-Demand)
      - [ ] Architecture: x86_64
    - [ ] "ARM-Based - Cost Efficient"
      - [ ] Families: t4g, m6g, c6g
      - [ ] Strategy: SPOT
      - [ ] Architecture: ARM64
    - [ ] "GPU - AI/ML Workloads"
      - [ ] Families: g4dn, g5, p3
      - [ ] Strategy: ON_DEMAND (GPUs less available as Spot)
      - [ ] Architecture: x86_64
  - [ ] Mark "General Purpose - Balanced" as global default

- [ ] Seed Default Cluster Policies
  - [ ] Create default policy configuration (JSONB):
    - [ ] Karpenter: enabled=false (user must opt-in)
    - [ ] Strategy: "capacity-optimized"
    - [ ] Bin packing: aggressiveness=40 (moderate)
    - [ ] Fallback: enabled=true (safety first)
    - [ ] AZ spread: enabled=true (high availability)
    - [ ] Right-sizing: mode="recommendations" (not auto)
    - [ ] Safety buffer: 20% (headroom for spikes)
    - [ ] Exclusions: ["kube-system", "kube-public", "kube-node-lease"]

- [ ] Seed System Configuration
  - [ ] Create `system_config` table if not exists
    - [ ] Columns: `key`, `value`, `description`, `updated_at`
  - [ ] Populate system-wide settings:
    - [ ] `SAFE_MODE`: "FALSE" (can be toggled by admin)
    - [ ] `GLOBAL_RISK_TTL`: "1800" (30 minutes)
    - [ ] `HEARTBEAT_TIMEOUT`: "60" (seconds)
    - [ ] `COLLECTION_INTERVAL`: "30" (seconds)
    - [ ] `OPTIMIZATION_COOLDOWN`: "300" (5 minutes between optimizations)
    - [ ] `MAX_CONCURRENT_ACTIONS`: "5" (per cluster)

- [ ] Create seeding verification script
  - [ ] `scripts/verify_seed_data.py`
  - [ ] Check row counts for each table
  - [ ] Verify data integrity (no nulls in required fields)
  - [ ] Verify relationships (foreign keys)
  - [ ] Output seeding report

- [ ] Add seeding to deployment pipeline
  - [ ] Run `seed_cloud_data.py` after database migrations
  - [ ] Run `verify_seed_data.py` to confirm success
  - [ ] Fail deployment if seeding fails

---

## Phase 15: Launch & Post-Launch

### 15.1 Staging Deployment
- [ ] Deploy to staging environment
- [ ] Run full integration test suite
- [ ] Perform manual QA testing
- [ ] Load testing
- [ ] Security penetration testing

### 15.2 Production Deployment
- [ ] Deploy to production environment
- [ ] Run smoke tests
- [ ] Monitor error rates
- [ ] Monitor performance metrics
- [ ] Verify all integrations

### 15.3 Post-Launch Monitoring
- [ ] Monitor system health for 48 hours
- [ ] Address any critical issues immediately
- [ ] Collect user feedback
- [ ] Monitor cost and usage metrics

### 15.4 Continuous Improvement
- [ ] Analyze user behavior and feature usage
- [ ] Identify optimization opportunities
- [ ] Plan feature enhancements
- [ ] Regular security updates
- [ ] Performance tuning based on real-world usage

---

## Completion Checklist

- [ ] All database models created and migrated
- [ ] All backend services implemented and tested
- [ ] All intelligence modules implemented and tested
- [ ] All API endpoints implemented and documented
- [ ] **All WebSocket infrastructure implemented and operational**
- [ ] **Kubernetes Agent built, packaged, and tested**
- [ ] **Stripe webhook handlers implemented and verified**
- [ ] **Static cloud data seeded and verified**
- [ ] All frontend components implemented and tested
- [ ] All workers configured and running
- [ ] All AWS scripts implemented and tested
- [ ] Docker configuration complete
- [ ] Helm charts published and tested
- [ ] CI/CD pipeline operational
- [ ] Monitoring and logging configured
- [ ] Documentation complete
- [ ] Security hardening complete
- [ ] Performance optimization complete
- [ ] Staging deployment successful
- [ ] Production deployment successful
- [ ] Post-launch monitoring complete

---

**Total Estimated Tasks**: 580+  
**Phases**: 15 (including critical additions)  
**Execution Mode**: Sequential, continuous work without timeline constraints  
**Success Criteria**: All tasks marked as `[x]` completed, system running in production

**Critical Components Added**:
- ✅ Phase 2.1: Agent Action Queue Model (`agent_action` table)
- ✅ Phase 3.10: WebSocket Infrastructure (CORE-WS)
- ✅ Phase 7.2.1: Hybrid Execution Router (AWS vs K8s action routing)
- ✅ Phase 8.2.1: Agent Action Queue Endpoints (Worker-to-Agent loop)
- ✅ Phase 8.11: Billing Webhooks (Stripe Integration)
- ✅ Phase 9.5: Kubernetes Agent Implementation (The "Probe")
- ✅ Phase 14.5: Static Data Seeding (AWS Regions, Instance Specs, Pricing)

**Worker-to-Agent Communication Loop** (COMPLETE):
```
Optimizer Worker (WORK-OPT-01)
    ↓
Decision Engine (CORE-DECIDE) - Generates action plan
    ↓
Hybrid Router (CORE-EXEC 7.2.1) - Routes based on action type
    ↓
    ├─→ AWS Actions → Boto3 Scripts (Direct execution)
    │
    └─→ K8s Actions → agent_action table (Queue)
            ↓
        WebSocket Event (agent:command:{cluster_id})
            ↓
        Agent Polls GET /clusters/{id}/actions/pending
            ↓
        Agent Executes (evict_pod, cordon_node, etc)
            ↓
        Agent Reports POST /clusters/{id}/actions/{action_id}/result
            ↓
        Backend Updates optimization_job status
            ↓
        Frontend Notified via WebSocket
```

