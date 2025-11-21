# Smart Emergency Fallback (SEF) Integration Guide

## Overview

This guide explains how to integrate the Smart Emergency Fallback component into the main `backend.py`.

The SEF component (`smart_emergency_fallback.py`) is a standalone module that provides:
- Data quality assurance (deduplication, gap filling)
- Automatic replica management during interruptions
- Manual replica mode with continuous hot standby
- Works independently of ML models

## Integration Steps

### Step 1: Import SEF in backend.py

Add at the top of `backend.py` (after other imports):

```python
# Import Smart Emergency Fallback System
from smart_emergency_fallback import SmartEmergencyFallback, integrate_with_backend
```

### Step 2: Initialize SEF when Flask app starts

Find where Flask app is initialized, and add:

```python
# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize database connection
db_connection = get_db_connection()

# Initialize Smart Emergency Fallback System
sef = SmartEmergencyFallback(db_connection)
logger.info("Smart Emergency Fallback System initialized")

# Integrate SEF with Flask routes
integrate_with_backend(app, sef)
```

### Step 3: Intercept all agent data through SEF

Modify the pricing data endpoint to process through SEF first:

**BEFORE:**
```python
@app.route('/api/agents/<agent_id>/pricing', methods=['POST'])
def submit_pricing(agent_id):
    data = request.get_json()

    # Insert directly to database
    cursor = db.cursor()
    cursor.execute("""INSERT INTO pricing_reports ...""")
    db.commit()

    return jsonify({"status": "success"})
```

**AFTER:**
```python
@app.route('/api/agents/<agent_id>/pricing', methods=['POST'])
def submit_pricing(agent_id):
    data = request.get_json()

    # ===== PROCESS THROUGH SEF FIRST =====
    processed_data = sef.process_incoming_data(
        agent_id=agent_id,
        data_type='pricing',
        payload=data
    )

    # Check if data was buffered (waiting for replica)
    if processed_data.get('status') == 'buffered':
        return jsonify({"status": "buffered", "message": "Waiting for replica data"})

    # Check if data was rejected
    if processed_data.get('status') == 'rejected':
        return jsonify({"status": "error", "reason": processed_data.get('reason')}), 400

    # Data is clean and deduplicated, insert to database
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO pricing_reports
        (agent_id, spot_price, pool_id, timestamp, data_quality_flag, processed_by)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        agent_id,
        processed_data.get('spot_price'),
        processed_data.get('pool_id'),
        processed_data.get('timestamp'),
        processed_data.get('data_quality_flag', 'normal'),
        'smart_emergency_fallback'
    ))
    db.commit()
    cursor.close()

    return jsonify({"status": "success", "data_quality": processed_data.get('data_quality_flag')})
```

### Step 4: Connect interruption signals to SEF

Modify the interruption handling endpoints:

**BEFORE:**
```python
@app.route('/api/agents/<agent_id>/interruption', methods=['POST'])
def handle_interruption(agent_id):
    data = request.get_json()
    signal_type = data.get('signal_type')

    # Create emergency replica logic here...

    return jsonify({"status": "handled"})
```

**AFTER:**
```python
@app.route('/api/agents/<agent_id>/interruption', methods=['POST'])
def handle_interruption(agent_id):
    data = request.get_json()
    signal_type = data.get('signal_type')

    # ===== LET SEF HANDLE IT =====
    if signal_type == 'rebalance-recommendation':
        result = sef.handle_rebalance_recommendation(agent_id, data)
    elif signal_type == 'termination-notice':
        result = sef.handle_termination_notice(agent_id, data)
    else:
        return jsonify({"status": "error", "reason": "unknown_signal_type"}), 400

    return jsonify(result)
```

### Step 5: Add periodic cleanup task

Add a background task to clean up old data buffers:

```python
from apscheduler.schedulers.background import BackgroundScheduler

# Initialize scheduler
scheduler = BackgroundScheduler()

# Add SEF cleanup task (every 5 minutes)
scheduler.add_job(
    func=sef.cleanup_old_buffers,
    trigger="interval",
    minutes=5,
    id='sef_cleanup',
    name='SEF buffer cleanup',
    replace_existing=True
)

scheduler.start()
logger.info("SEF cleanup scheduler started")
```

### Step 6: Add new frontend endpoints for manual control

The `integrate_with_backend()` function automatically adds these endpoints:

- `POST /api/agents/<agent_id>/manual-replica/enable` - Enable manual replica mode
- `POST /api/agents/<agent_id>/manual-replica/disable` - Disable manual replica mode
- `POST /api/agents/<agent_id>/manual-switch` - Execute manual switch to replica
- `GET /api/agents/<agent_id>/sef-status` - Get SEF status for agent

No additional code needed - these are automatically registered.

## Mutual Exclusion Logic

The SEF enforces mutual exclusion between auto and manual modes:

1. **Enabling Manual Mode:**
   - Checks if `auto_switch_enabled` or `auto_terminate_enabled` is TRUE
   - If yes: Returns error "Cannot enable manual mode while auto mode is active"
   - User must disable auto mode first

2. **Enabling Auto Mode:**
   - Should check if `manual_replica_enabled` is TRUE
   - If yes: Return error "Cannot enable auto mode while manual mode is active"
   - User must disable manual mode first

Add this check to your auto-switch enable endpoint:

```python
@app.route('/api/agents/<agent_id>/auto-switch/enable', methods=['POST'])
def enable_auto_switch(agent_id):
    # Check if manual mode is active
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT manual_replica_enabled FROM agents WHERE id = %s
    """, (agent_id,))

    result = cursor.fetchone()
    cursor.close()

    if result and result['manual_replica_enabled']:
        return jsonify({
            "status": "error",
            "reason": "manual_mode_active",
            "message": "Cannot enable auto-switch while manual replica mode is active"
        }), 403

    # Proceed with enabling auto-switch
    cursor = db.cursor()
    cursor.execute("""
        UPDATE agents SET auto_switch_enabled = TRUE WHERE id = %s
    """, (agent_id,))
    db.commit()
    cursor.close()

    return jsonify({"status": "success"})
```

## Testing the Integration

### Test 1: Data Quality Assurance

```bash
# Send pricing data from primary agent
curl -X POST http://localhost:5000/api/agents/test-agent-1/pricing \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 0.0456,
    "pool_id": "pool-123",
    "timestamp": 1637500000,
    "is_replica": false
  }'

# Send slightly different data from replica
curl -X POST http://localhost:5000/api/agents/test-agent-1/pricing \
  -H "Content-Type: application/json" \
  -d '{
    "spot_price": 0.0458,
    "pool_id": "pool-123",
    "timestamp": 1637500000,
    "is_replica": true
  }'

# Check database - should see averaged price (0.0457) with flag 'averaged_dual_source'
```

### Test 2: Gap Filling

```bash
# Send data point at T=0
curl -X POST http://localhost:5000/api/agents/test-agent-1/pricing \
  -H "Content-Type: application/json" \
  -d '{"spot_price": 0.05, "pool_id": "pool-123", "timestamp": 1637500000}'

# Wait, then send data point at T=1200 (20 minutes later)
curl -X POST http://localhost:5000/api/agents/test-agent-1/pricing \
  -H "Content-Type: application/json" \
  -d '{"spot_price": 0.06, "pool_id": "pool-123", "timestamp": 1637501200}'

# Check database - should see interpolated points at T=300, 600, 900
# with prices ~0.0525, 0.055, 0.0575
```

### Test 3: Manual Replica Mode

```bash
# Enable manual replica mode
curl -X POST http://localhost:5000/api/agents/test-agent-1/manual-replica/enable

# Check status
curl http://localhost:5000/api/agents/test-agent-1/sef-status

# Execute manual switch
curl -X POST http://localhost:5000/api/agents/test-agent-1/manual-switch

# Check status again - should see new instance IDs
curl http://localhost:5000/api/agents/test-agent-1/sef-status
```

### Test 4: Rebalance Recommendation

```bash
# Simulate rebalance recommendation from agent
curl -X POST http://localhost:5000/api/agents/test-agent-1/interruption \
  -H "Content-Type: application/json" \
  -d '{
    "signal_type": "rebalance-recommendation",
    "timestamp": 1637500000,
    "termination_time": null
  }'

# Should create replica if risk is high
# Check database: SELECT * FROM replica_instances WHERE agent_id = 'test-agent-1';
```

## Monitoring SEF Performance

Add these queries to your monitoring dashboard:

```sql
-- Data quality metrics
SELECT
    DATE(timestamp) as date,
    COUNT(*) as total_points,
    SUM(CASE WHEN data_quality_flag = 'interpolated' THEN 1 ELSE 0 END) as interpolated,
    SUM(CASE WHEN data_quality_flag = 'averaged_dual_source' THEN 1 ELSE 0 END) as averaged,
    SUM(CASE WHEN data_quality_flag = 'normal' THEN 1 ELSE 0 END) as normal
FROM pricing_reports
WHERE processed_by = 'smart_emergency_fallback'
GROUP BY DATE(timestamp);

-- Replica operations
SELECT
    replica_type,
    status,
    COUNT(*) as count,
    AVG(TIMESTAMPDIFF(SECOND, created_at, ready_at)) as avg_ready_time
FROM replica_instances
GROUP BY replica_type, status;

-- Failover performance
SELECT
    AVG(failover_time_ms / 1000.0) as avg_failover_seconds,
    MIN(failover_time_ms / 1000.0) as fastest_failover,
    MAX(failover_time_ms / 1000.0) as slowest_failover,
    SUM(CASE WHEN failover_completed = TRUE THEN 1 ELSE 0 END) as successful,
    COUNT(*) as total
FROM spot_interruption_events;
```

## Troubleshooting

### Issue: Data not being deduplicated

**Symptom:** Duplicate entries in database from primary and replica

**Solution:** Check that agents are properly tagging their data with `is_replica` flag

```python
# In agent code, when sending from replica:
payload['is_replica'] = True
```

### Issue: Gaps not being filled

**Symptom:** Missing data points in timeline

**Solution:** Check SEF gap detection settings:

```python
# Adjust thresholds in smart_emergency_fallback.py
self.gap_detection_threshold = 600  # 10 minutes
self.interpolation_max_gap = 1800   # 30 minutes
```

### Issue: Manual and auto modes both enabled

**Symptom:** Agent shows both manual_replica_enabled and auto_switch_enabled as TRUE

**Solution:** This should never happen. If it does, forcefully disable one:

```sql
-- Disable manual mode
UPDATE agents SET manual_replica_enabled = FALSE WHERE id = '<agent_id>';

-- Or disable auto mode
UPDATE agents SET auto_switch_enabled = FALSE WHERE id = '<agent_id>';
```

## Complete Integration Checklist

- [ ] Import SEF module in backend.py
- [ ] Initialize SEF with database connection
- [ ] Call integrate_with_backend() to add endpoints
- [ ] Modify pricing endpoint to process through SEF
- [ ] Modify interruption endpoint to use SEF handlers
- [ ] Add periodic cleanup scheduler
- [ ] Add mutual exclusion checks to auto/manual mode toggles
- [ ] Test data deduplication
- [ ] Test gap filling
- [ ] Test manual replica mode
- [ ] Test rebalance/termination handling
- [ ] Add monitoring queries to dashboard
- [ ] Update frontend to show SEF status
- [ ] Update documentation

## Next Steps

1. Complete integration following this guide
2. Test thoroughly with real AWS instances
3. Monitor data quality metrics
4. Tune thresholds based on production performance
5. Add alerting for SEF errors

## Support

For issues with SEF integration, check:
1. Backend logs: `sudo journalctl -u spot-optimizer-backend -f`
2. SEF-specific logs: `grep "SEF:" /var/log/spot-optimizer/backend.log`
3. Database events: `SELECT * FROM system_events WHERE message LIKE '%SEF%' ORDER BY created_at DESC LIMIT 20;`
