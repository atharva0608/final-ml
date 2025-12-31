# CAST-AI Mini - Simplified Agentless Backend v3.0.0

**Major Simplification**: Removed all complex features, keeping only essential controls.

---

## What Changed

### ❌ Removed (Old Complexity)
- Agent management and coordination
- Replica instances (manual and emergency)
- Complex state machines
- Emergency fallback system
- Multi-instance clusters
- gRPC/HTTP agent communication
- Client tokens and authentication
- Heartbeat tracking
- Command queues
- 25+ database tables

### ✅ Kept (Essential Features)
- Single instance management
- Auto-switch ON/OFF control
- Auto-terminate ON/OFF control
- Reset cooldown functionality
- Decision engine integration
- ML-based optimization
- Cost tracking
- Switch history

---

## New Architecture

```
┌─────────────────────────────────────────────┐
│         Simplified Backend                  │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │  Decision Engine                   │   │
│  │  - Runs every 5 minutes            │   │
│  │  - Checks auto-switch enabled      │   │
│  │  - Respects cooldown               │   │
│  └────────────────────────────────────┘   │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │  AWS Executor                      │   │
│  │  - Gets instance state             │   │
│  │  - Collects CloudWatch metrics     │   │
│  │  - Launches/terminates instances   │   │
│  └────────────────────────────────────┘   │
│                                             │
│  ┌────────────────────────────────────┐   │
│  │  Simple Controls                   │   │
│  │  - Auto-switch: ON/OFF             │   │
│  │  - Auto-terminate: ON/OFF          │   │
│  │  - Reset: Clear cooldown           │   │
│  └────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## Database Schema

### Core Tables (5 total)

1. **instances** - Managed instances
   - instance_id, type, az, state
   - auto_switch_enabled, auto_terminate_enabled
   - cooldown tracking

2. **decisions** - Decision history
   - action (STAY/MIGRATE/DEFER)
   - confidence, savings, reasoning
   - execution status

3. **switches** - Migration events
   - old → new instance mapping
   - cost savings, downtime
   - success/failure tracking

4. **pool_pricing** - Historical pricing
   - spot prices per pool
   - interruption tracking

5. **system_config** - Configuration
   - decision_interval_minutes
   - cooldown_minutes
   - ML weights and thresholds

### Views (3 total)
- v_active_instances
- v_recent_decisions
- v_switch_summary

### Stored Procedures (4 total)
- sp_get_instance_for_decision
- sp_record_decision
- sp_record_switch
- sp_update_switch_status

---

## API Endpoints

### Instance Management

**GET /api/instances**
```bash
curl http://localhost:5000/api/instances
```
Returns all managed instances with status

**GET /api/instances/{id}**
```bash
curl http://localhost:5000/api/instances/i-123abc
```
Get single instance details

### Controls

**POST /api/instances/{id}/auto-switch**
```bash
# Enable auto-switching
curl -X POST http://localhost:5000/api/instances/i-123abc/auto-switch \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Disable auto-switching
curl -X POST http://localhost:5000/api/instances/i-123abc/auto-switch \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**POST /api/instances/{id}/auto-terminate**
```bash
# Enable auto-termination
curl -X POST http://localhost:5000/api/instances/i-123abc/auto-terminate \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Disable auto-termination
curl -X POST http://localhost:5000/api/instances/i-123abc/auto-terminate \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**POST /api/instances/{id}/reset**
```bash
# Reset cooldown (allows immediate decision)
curl -X POST http://localhost:5000/api/instances/i-123abc/reset
```

### Analytics

**GET /api/decisions**
```bash
curl http://localhost:5000/api/decisions?limit=50
```
Get recent decision history

**GET /api/switches**
```bash
curl http://localhost:5000/api/switches?limit=50
```
Get migration history

**GET /api/summary**
```bash
curl http://localhost:5000/api/summary
```
Get summary statistics

### Configuration

**GET /api/config**
```bash
curl http://localhost:5000/api/config
```
Get all configuration values

**POST /api/config/{key}**
```bash
curl -X POST http://localhost:5000/api/config/decision_interval_minutes \
  -H "Content-Type: application/json" \
  -d '{"value": "10"}'
```

---

## How It Works

### Decision Loop

Every 5 minutes (configurable):

1. **Find Eligible Instances**
   ```sql
   SELECT * FROM instances
   WHERE state = 'running'
     AND auto_switch_enabled = true
     AND (cooldown_until IS NULL OR cooldown_until <= NOW())
   ```

2. **For Each Instance**:
   - Get current state from AWS
   - Collect CloudWatch metrics
   - Run decision engine
   - Record decision in database

3. **If Action = MIGRATE**:
   - Check if `auto_terminate_enabled = true`
   - If yes: Launch new instance, terminate old
   - If no: Log decision but don't execute

4. **Set Cooldown**:
   - Prevent rapid repeated decisions
   - Default: 10 minutes

### Control Modes

**Both ON** (Full Auto):
- Decision runs automatically
- Migrations execute automatically
- Optimal for production

**Auto-Switch ON, Auto-Terminate OFF**:
- Decision runs automatically
- Migrations recommended but not executed
- Good for testing/validation

**Both OFF**:
- Decision doesn't run
- Instance stays put
- Manual control only

**Reset**:
- Clears cooldown
- Allows immediate decision
- Useful after manual changes

---

## Deployment

### Fresh Install

```bash
cd scripts/
chmod +x deploy_simple.sh
sudo ./deploy_simple.sh
```

This will:
1. Backup old database
2. Create new simplified schema
3. Stop old backend
4. Update systemd service
5. Start new backend
6. Test health endpoint

### Verify Deployment

```bash
# Check service status
sudo systemctl status spot-optimizer-backend

# View logs
sudo journalctl -u spot-optimizer-backend -f

# Test API
curl http://localhost:5000/health
curl http://localhost:5000/api/instances
```

### Rollback (if needed)

```bash
# Stop new backend
sudo systemctl stop spot-optimizer-backend

# Restore old database
docker exec -i spot-mysql mysql -u root -pcast_ai_root_2025 < /tmp/spot_optimizer_backup_*.sql

# Start old backend
sudo systemctl start spot-optimizer-backend
```

---

## Configuration

### Environment Variables (backend/.env)

```env
# Database
DB_HOST=localhost
DB_PORT=3306
DB_USER=spotuser
DB_PASSWORD=cast_ai_spot_2025
DB_NAME=spot_optimizer

# AWS
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...        # Or use IAM instance profile
AWS_SECRET_ACCESS_KEY=...    # Or use IAM instance profile

# Decision Engine
DECISION_INTERVAL_MINUTES=5
COOLDOWN_MINUTES=10

# ML Models
STABILITY_MODEL_PATH=models/stability_ranker.pkl
PRICE_MODEL_PATH=models/price_predictor.pkl
```

### System Config (via API)

```bash
# Change decision interval to 10 minutes
curl -X POST http://localhost:5000/api/config/decision_interval_minutes \
  -H "Content-Type: application/json" \
  -d '{"value": "10"}'

# Change stability weight to 80%
curl -X POST http://localhost:5000/api/config/stability_weight \
  -H "Content-Type: application/json" \
  -d '{"value": "0.80"}'
```

---

## Adding New Instances

### Via SQL

```sql
INSERT INTO instances (
    instance_id, instance_type, az, lifecycle, state,
    current_spot_price, on_demand_price,
    auto_switch_enabled, auto_terminate_enabled
) VALUES (
    'i-1234567890abcdef0',
    'm5.large',
    'us-east-1a',
    'spot',
    'running',
    0.045,
    0.096,
    true,
    true
);
```

### Via API (future)

```bash
curl -X POST http://localhost:5000/api/instances \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "i-1234567890abcdef0",
    "instance_type": "m5.large",
    "az": "us-east-1a"
  }'
```

---

## Monitoring

### Key Metrics

```sql
-- Active instances
SELECT COUNT(*) FROM instances WHERE state = 'running';

-- Decisions in last 24 hours
SELECT COUNT(*) FROM decisions WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR);

-- Successful switches in last 7 days
SELECT COUNT(*) FROM switches
WHERE status = 'migrated'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY);

-- Average savings
SELECT AVG(cost_savings_percent) FROM switches
WHERE status = 'migrated'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);
```

### Logs

```bash
# Backend logs (live)
sudo journalctl -u spot-optimizer-backend -f

# Backend logs (last 100 lines)
sudo journalctl -u spot-optimizer-backend -n 100

# Database logs
docker logs spot-mysql -f
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Check logs
sudo journalctl -u spot-optimizer-backend -n 50

# Check database connection
docker exec spot-mysql mysql -u spotuser -pcast_ai_spot_2025 spot_optimizer -e "SHOW TABLES"

# Verify AWS credentials
aws sts get-caller-identity

# Restart backend
sudo systemctl restart spot-optimizer-backend
```

### No Decisions Being Made

1. Check if instances have `auto_switch_enabled = true`
2. Check if instances are in cooldown
3. Verify decision loop is running (check logs)
4. Check `DECISION_INTERVAL_MINUTES` setting

```sql
-- Check instance settings
SELECT instance_id, auto_switch_enabled, cooldown_until
FROM instances
WHERE state = 'running';

-- Check recent decisions
SELECT * FROM decisions
ORDER BY created_at DESC
LIMIT 10;
```

### Migrations Not Executing

1. Check if `auto_terminate_enabled = true`
2. Review decision logs for errors
3. Verify AWS IAM permissions
4. Check cooldown settings

---

## Migration from Old Backend

### What Happens to Old Data?

- **Backed up**: Before deployment, old DB is backed up to `/tmp/`
- **Not migrated**: Old agent/replica data is not migrated
- **Fresh start**: New schema starts clean
- **Can restore**: Backup can be restored if needed

### Manual Data Migration (if needed)

```sql
-- Export old instance data
SELECT instance_id, instance_type, az, lifecycle, state
FROM old_backup.instances
WHERE state = 'running';

-- Import to new schema
INSERT INTO instances (instance_id, instance_type, az, lifecycle, state, ...)
VALUES (...);
```

---

## Comparison

### Old Backend
- 25+ database tables
- Agent coordination
- Replica management
- Emergency fallback
- Complex state machines
- ~10,000 lines of code

### New Backend
- 5 database tables
- Simple controls
- Direct AWS API
- Clean decision logic
- ~600 lines of code

**Result**: 80% less complexity, same core functionality

---

## Support

**Issues**: Check logs first
```bash
sudo journalctl -u spot-optimizer-backend -n 100
```

**Questions**: Review this document

**Bugs**: Report with:
- Backend logs
- Database state
- API responses

---

## Version History

**v3.0.0** (2025-12-02)
- Complete simplification
- Removed agents, replicas, emergency fallback
- Simple ON/OFF controls
- Clean database schema
- Agentless architecture

**v2.0.0** (2025-11-21)
- Agent-based with replicas
- Complex state management

**v1.0.0** (Initial)
- Basic spot optimizer

---

**Status**: Production Ready ✅
**Architecture**: Agentless
**Complexity**: Minimal
**Maintenance**: Low
