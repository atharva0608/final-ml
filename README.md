# AWS Spot Optimizer - System Overview

**Production-ready spot instance management with automatic failover and data quality assurance**

---

## 🎯 What This System Does

Automatically manages AWS spot instances to minimize costs while ensuring zero downtime through intelligent replica management and instant failover.

**Key Capabilities:**
- **50-70% cost savings** vs on-demand instances
- **Zero downtime** during spot interruptions
- **Automatic failover** in <15 seconds
- **Complete data quality** assurance with gap-filling
- **Manual and automatic** replica modes

---

## 📋 Quick Start

### 1. Installation

```bash
# Clone repository
git clone https://github.com/atharva0608/final-ml.git
cd final-ml

# Run setup script
chmod +x scripts/setup.sh
./scripts/setup.sh

# Load demo data (optional)
mysql -u root -p spot_optimizer < demo/demo_data.sql
```

### 2. Configuration

Edit `backend.py` to configure:
- MySQL connection (host, user, password, database)
- AWS credentials (if using EC2 metadata)
- Port and host settings

### 3. Start System

```bash
# Start backend
python backend.py

# Start frontend (separate terminal)
cd frontend
npm run dev
```

Access UI at: `http://localhost:5173`

---

## 🔄 System Scenarios

### Scenario 1: Normal Operation (No Interruptions)

**What Happens:**
1. Agent runs on spot instance, monitoring pool prices every 5 minutes
2. Pricing data submitted to backend → Deduplication pipeline processes it
3. If cheaper pool found: Agent switches automatically (if auto-switch enabled)
4. All pricing data stored in `pricing_snapshots_clean` table
5. Gaps auto-filled every 15 minutes using interpolation algorithms

**User Actions:**
- View real-time pricing graphs
- Monitor agent status
- See switch history with savings calculations

**Database Flow:**
```
Agent → pricing_submissions_raw → Deduplication → pricing_snapshots_clean
                                       ↓
                                  Gap Detection
                                       ↓
                                  Interpolation
                                       ↓
                             pricing_snapshots_interpolated
```

---

### Scenario 2: AWS Rebalance Recommendation (10-15 min warning)

**When:** AWS sends rebalance recommendation signal to instance metadata

**What System Does:**
1. **Agent detects signal** (polls `http://169.254.169.254/latest/meta-data/events/recommendations/rebalance`)
2. **Calculates interruption probability**:
   - Instance age
   - Pool interruption history
   - Time of day patterns
3. **If probability > 30%**:
   - Agent calls: `POST /api/agents/{id}/create-emergency-replica`
   - Backend selects safest pool (lowest interruption risk)
   - If current pool is cheapest, selects second cheapest
   - Creates replica instance in target pool
4. **Replica boots and syncs**:
   - Connects to primary agent
   - Receives compressed state dump
   - Status: `launching` → `syncing` → `ready`
   - Sync progress tracked in database
5. **Primary continues normal operation**
6. **If termination notice arrives later** → Jump to Scenario 3
7. **If no termination** → Replica stays on standby or gets terminated

**Database Updates:**
```sql
INSERT INTO replica_instances (type='automatic-rebalance', status='launching')
INSERT INTO spot_interruption_events (signal_type='rebalance-recommendation')
UPDATE agents SET replica_count = replica_count + 1
```

**API Calls:**
- `POST /api/agents/{id}/create-emergency-replica`
- `POST /api/agents/{id}/replicas/{rid}/sync-status` (every 10s)

---

### Scenario 3: AWS 2-Minute Termination Notice (CRITICAL)

**When:** AWS sends termination notice exactly 2 minutes before shutdown

**What System Does:**

**Timeline:**
- **T-0s**: Agent detects termination notice
- **T-2s**: Agent stops non-critical operations
- **T-5s**: State transfer to replica begins (compressed, delta-encoded)
- **T-10s**: Agent calls `POST /api/agents/{id}/termination-imminent`
- **T-12s**: Backend promotes replica to primary status
- **T-15s**: Replica connects to backend as new primary
- **T-20s**: Old instance flushes logs, terminates gracefully

**Step-by-Step:**

1. **Detection** (T-0s):
   ```python
   # Agent polls metadata
   response = requests.get('http://169.254.169.254/latest/meta-data/spot/instance-action')
   # Returns: {"action": "terminate", "time": "2025-11-20T10:47:00Z"}
   ```

2. **Immediate Response** (T-2s):
   - Stop pricing collection
   - Stop decision-making
   - Freeze state for transfer

3. **State Transfer** (T-5s):
   - Compress recent pricing data (last 1 hour)
   - Compress switch history
   - Transfer via WebSocket or HTTP POST
   - Target: Complete in <5 seconds

4. **Failover Request** (T-10s):
   ```bash
   POST /api/agents/{id}/termination-imminent
   {
     "instance_id": "i-1234567890abcdef0",
     "termination_time": "2025-11-20T10:47:00Z",
     "replica_id": "uuid-of-ready-replica"
   }
   ```

5. **Backend Actions** (T-12s):
   ```sql
   -- Create new instance record for replica
   INSERT INTO instances (id='i-new', ...) SELECT ... FROM replica_instances WHERE id='replica-id';

   -- Update agent to point to replica
   UPDATE agents SET instance_id='i-new', last_failover_at=NOW() WHERE id='agent-id';

   -- Mark replica as promoted
   UPDATE replica_instances SET status='promoted', promoted_at=NOW() WHERE id='replica-id';

   -- Record switch
   INSERT INTO instance_switches (reason='automatic-interruption-failover', ...);

   -- Mark old instance as inactive
   UPDATE instances SET is_active=FALSE WHERE id='i-old';

   -- Log event
   UPDATE spot_interruption_events SET failover_completed=TRUE, failover_time_ms=8543;
   ```

6. **Replica Takeover** (T-15s):
   - Replica receives promotion signal
   - Connects to backend as primary agent
   - Resumes pricing collection
   - Resumes decision-making

7. **Old Instance Cleanup** (T-20s to T-120s):
   - Flush final logs to S3/backend
   - Submit any cached pricing data
   - Terminate gracefully

**Success Criteria:**
- ✅ Failover completed in <15 seconds
- ✅ Data loss <5 seconds
- ✅ Zero service interruption

**If No Replica Available:**
1. Agent creates emergency snapshot:
   ```python
   state = {
       'pricing_data': get_recent_data(hours=1),
       'config': get_config(),
       'timestamp': time.time()
   }
   upload_to_s3(state)
   ```

2. Backend launches new instance from snapshot
3. Data loss: ~30-120 seconds (time to boot new instance)

**Database State After Failover:**
```sql
-- spot_interruption_events
{
  "signal_type": "termination-notice",
  "response_action": "promoted-existing-replica",
  "failover_completed": true,
  "failover_time_ms": 8543,
  "success": true
}

-- instance_switches
{
  "switch_reason": "automatic-interruption-failover",
  "old_instance_price": 0.0416,
  "new_instance_price": 0.0420,
  "estimated_savings": -0.40,
  "success": true
}
```

---

### Scenario 4: Manual Replica Creation & Failover

**When:** User wants to create standby replica manually (no interruption)

**Steps:**

1. **User clicks "Create Replica" in frontend**

2. **Frontend calls API:**
   ```bash
   POST /api/agents/{id}/replicas
   {
     "pool_id": null,  # Auto-select cheapest
     "exclude_zones": ["us-east-1a"],
     "created_by": "admin@company.com"
   }
   ```

3. **Backend selects pool:**
   - Query all pools for instance type
   - Sort by spot price (ascending)
   - If current pool is cheapest → Select second cheapest
   - If current pool not cheapest → Select cheapest (excluding current)

4. **Backend creates replica:**
   ```sql
   INSERT INTO replica_instances (
     type='manual',
     status='launching',
     pool_id=<selected>,
     created_by='admin@company.com'
   )
   ```

5. **Agent establishes connection:**
   - Replica agent boots
   - Connects to primary agent (WebSocket or polling)
   - Receives state sync
   - Updates status: `launching` → `syncing` → `ready`

6. **User monitors progress:**
   - Frontend shows replica in UI
   - Sync status: 0% → 100%
   - Latency: ~50ms
   - Status: "Ready for Promotion"

7. **User clicks "Promote Replica":**
   ```bash
   POST /api/agents/{id}/replicas/{rid}/promote
   {
     "demote_old_primary": true  # Make old primary the new replica
   }
   ```

8. **Zero-downtime failover:**
   - Primary freezes (1-2 seconds)
   - Final state transfer to replica
   - Replica validates state
   - Backend updates agent mapping
   - Replica becomes primary
   - Old primary becomes replica (or terminates)

9. **Result:**
   - New primary in potentially cheaper pool
   - Old instance available as standby replica
   - Switch recorded in database

**Use Cases:**
- Test failover process
- Preemptive move to cheaper pool
- Regional failover
- Maintenance preparation

---

### Scenario 5: Data Quality - Gap Detection & Filling

**When:** Agent goes offline or network partition occurs

**What Happens:**

1. **Gap Detection** (runs every 15 minutes):
   ```python
   # Scan for missing 5-minute buckets
   gaps = detect_gaps(pool_id=123, last_24_hours)
   # Found: 2025-11-20 10:00 to 10:30 (6 buckets missing)
   ```

2. **Classify Gap:**
   - **Short (5-10 min / 1-2 buckets)**: Linear interpolation
   - **Medium (15-30 min / 3-6 buckets)**: Weighted average
   - **Long (35+ min / 7-24 buckets)**: Cross-pool inference
   - **Blackout (>4 hours)**: No interpolation, leave empty

3. **Example: Medium Gap (20 minutes)**

   **Data:**
   - Last price before gap: `$0.0416` at `09:55`
   - First price after gap: `$0.0420` at `10:20`
   - Gap: `10:00, 10:05, 10:10, 10:15` (4 buckets)

   **Interpolation:**
   ```python
   # Weighted average with time decay
   surrounding_prices = get_prices_around_gap(pool_id, gap_time, window=1hr)

   for price_point in surrounding_prices:
       weight = 1 / (time_distance_minutes + 1)
       weighted_sum += price * weight
       total_weight += weight

   interpolated = weighted_sum / total_weight
   confidence = 0.75  # Medium gap = 0.75 confidence
   ```

   **Database:**
   ```sql
   -- Record interpolation
   INSERT INTO pricing_snapshots_interpolated (
     gap_type='medium',
     interpolation_method='weighted-average',
     price_before=0.0416,
     price_after=0.0420,
     interpolated_price=0.0418,
     confidence_score=0.75
   );

   -- Insert into clean data
   INSERT INTO pricing_snapshots_clean (
     spot_price=0.0418,
     data_source='interpolated',
     confidence_score=0.75,
     interpolation_method='weighted-average'
   );
   ```

4. **Long Gap: Cross-Pool Inference:**
   - Find peer pools (same instance type, different AZ)
   - Observe their price movements during gap
   - Calculate median price change
   - Apply to this pool
   - Confidence: 0.70

5. **Result:**
   - Clean, continuous dataset
   - No gaps in graphs
   - ML models train on complete data
   - Transparency: All interpolations tracked

**Confidence Scores:**
- `1.00` - Measured (primary agent)
- `0.95` - Measured (replica agent)
- `0.85` - Short gap interpolation
- `0.75` - Medium gap interpolation
- `0.70` - Long gap interpolation

---

### Scenario 6: ML Model Upload & Activation

**When:** New ML models ready for deployment

**Steps:**

1. **User uploads models** (frontend):
   - Select files: `xgboost_model.pkl`, `scaler.joblib`
   - Click "Upload ML Models"

2. **Backend processes upload:**
   ```sql
   -- Mark current live as fallback
   UPDATE model_upload_sessions SET is_live=FALSE, is_fallback=TRUE WHERE is_live=TRUE;

   -- Create new session
   INSERT INTO model_upload_sessions (
     session_type='models',
     status='uploaded',
     is_live=FALSE,
     is_fallback=FALSE,
     file_count=2,
     file_names='["xgboost_model.pkl", "scaler.joblib"]'
   );
   ```

3. **UI shows pending session:**
   - 🟡 PENDING ACTIVATION
   - Files: 2 uploaded
   - Status: "Click RESTART to activate"

4. **RESTART button enables** automatically

5. **User clicks RESTART:**
   ```bash
   POST /api/admin/ml-models/activate
   {
     "sessionId": "uuid-of-uploaded-session"
   }
   ```

6. **Backend restarts:**
   ```sql
   -- Promote session to live
   UPDATE model_upload_sessions SET is_live=TRUE, status='activated', activated_at=NOW() WHERE id='uuid';

   -- Demote old live to fallback
   UPDATE model_upload_sessions SET is_live=FALSE, is_fallback=TRUE WHERE id='old-uuid';

   -- Delete very old sessions (keep only last 2)
   DELETE FROM model_upload_sessions WHERE ... LIMIT 100 OFFSET 2;
   ```

7. **Backend service restarts:**
   - Loads new models from disk
   - Validates models
   - Activates for decision-making
   - Health check returns success

8. **Frontend polls health:**
   - Checks every 1 second
   - Waits for backend to return
   - Shows success message

9. **Fallback available:**
   - Previous models kept as backup
   - User can rollback anytime via FALLBACK button

**Rollback Scenario:**
1. User clicks "FALLBACK TO PREVIOUS"
2. Backend swaps live and fallback sessions
3. Restarts with old models
4. System back to previous state

---

## 🏗️ Architecture

### System Components

```
┌─────────────────┐
│   Frontend      │  React + Vite
│  (Port 5173)    │  Dashboard, Controls
└────────┬────────┘
         │ HTTP/REST
┌────────▼────────┐
│   Backend       │  Flask + MySQL
│  (Port 5000)    │  API, Logic
└────────┬────────┘
         │
    ┌────┴─────┬──────────┬──────────┐
    │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│ Agent │ │ Agent │ │ Agent │ │ Agent │
│   1   │ │   2   │ │   3   │ │   4   │
└───────┘ └───────┘ └───────┘ └───────┘
  Spot      Spot      Spot      Spot
Instance  Instance  Instance  Instance
```

### Database Tables (Key Ones)

- **agents** - Agent status, configuration, replica settings
- **instances** - EC2 instances, pools, pricing
- **replica_instances** - All replicas (manual, automatic)
- **pricing_snapshots_clean** - Deduplicated pricing data
- **pricing_submissions_raw** - Complete audit trail
- **spot_interruption_events** - Interruption handling logs
- **instance_switches** - Switch history with pricing
- **model_upload_sessions** - ML model versions

---

## 📁 Repository Structure

```
final-ml/
├── backend.py                      # Main Flask application
├── data_quality_processor.py       # Deduplication & gap-filling
├── replica_management_api.py       # Replica endpoints
├── schema.sql                      # Database schema
│
├── scripts/
│   ├── setup.sh                    # Installation script
│   └── cleanup.sh                  # Cleanup script
│
├── demo/
│   └── demo_data.sql               # Demo data for testing
│
├── migrations/
│   ├── 006_replica_management_schema.sql
│   └── add_model_upload_sessions.sql
│
├── decision_engines/
│   ├── __init__.py
│   └── ml_based_engine.py          # Decision engine logic
│
└── frontend/
    ├── src/
    │   ├── pages/                  # React pages
    │   ├── components/             # React components
    │   └── services/               # API client
    └── dist/                       # Built frontend
```

---

## 🔧 Configuration Files

### Backend Config (`backend.py`)

```python
# MySQL Connection
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = 'your-password'
DB_NAME = 'spot_optimizer'

# Server Config
HOST = '0.0.0.0'
PORT = 5000

# Agent Config
HEARTBEAT_TIMEOUT = 300  # 5 minutes
AUTO_SWITCH_ENABLED = True
```

### Agent Config (on EC2 instances)

```bash
# Enable replica features
AUTO_REPLICA_ENABLED=true
MANUAL_REPLICA_ENABLED=true

# Interruption monitoring
INTERRUPTION_CHECK_INTERVAL=5  # seconds
REBALANCE_THRESHOLD=0.30  # 30% probability

# Sync settings
SYNC_UPDATE_INTERVAL=10  # seconds
```

---

## 🧪 Testing

### Load Demo Data

```bash
mysql -u root -p spot_optimizer < demo/demo_data.sql
```

**Includes:**
- 4 demo clients
- 5 spot pools
- 7 days of pricing data (~2,000 points)
- 4 replica instances
- 3 interruption events
- 3 ML model sessions

### Test Scenarios

**Test Replica Creation:**
```bash
curl -X POST http://localhost:5000/api/agents/agent-demo-1/replicas \
  -H "Content-Type: application/json" \
  -d '{"created_by": "test@example.com"}'
```

**Test Failover:**
```bash
curl -X POST http://localhost:5000/api/agents/agent-demo-1/termination-imminent \
  -H "Content-Type: application/json" \
  -d '{"instance_id": "i-demo001", "termination_time": "2025-11-20T10:47:00Z"}'
```

---

## 📊 Monitoring

### Key Metrics

- **Failover Success Rate**: Target >99%
- **Failover Time**: Target <15 seconds
- **Data Loss**: Target <5 seconds
- **Cost Savings**: Target 50-70%
- **Uptime**: Target 99.9%

### Health Checks

```bash
# Backend health
curl http://localhost:5000/api/health

# Agent heartbeats
SELECT id, last_heartbeat_at FROM agents WHERE status='online';

# Replica status
SELECT * FROM replica_instances WHERE is_active=TRUE;
```

---

## 🚨 Troubleshooting

**Issue:** Agent offline
- Check `last_heartbeat_at` in database
- Verify network connectivity
- Check EC2 instance status

**Issue:** Failover failed
- Check `spot_interruption_events` table for error
- Verify replica was ready (`status='ready'`)
- Check failover logs

**Issue:** Pricing gaps not filled
- Run gap detection manually
- Check interpolation logs
- Verify gap is <4 hours

**Issue:** Models not loading
- Check `model_upload_sessions` status
- Verify files exist in `ml_models/` directory
- Check backend logs for model loading errors

---

## 📞 Support

For issues or questions:
1. Check database logs: `spot_interruption_events`, `instance_switches`
2. Review backend logs
3. Check agent logs on EC2 instances

---

**Version:** 1.0
**Last Updated:** 2025-11-20
**Status:** Production Ready
