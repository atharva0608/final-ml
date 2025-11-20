# Database Setup Guide

## 🎯 One Complete Schema File

All database tables, indexes, and structures are now in **ONE unified schema file**:
- **File**: `schema.sql` (1900+ lines)
- **Contains**: All 30 tables including replica management, pricing, savings tracking, and more
- **No migrations needed**: Just run this one file

## ✅ What's Included

### Core Tables (13)
- ✓ `clients` - Client accounts
- ✓ `agents` - Agent instances (with replica columns)
- ✓ `agent_configs` - Agent configuration
- ✓ `commands` - Priority-based command queue
- ✓ `spot_pools` - Available spot instance pools
- ✓ `instances` - Instance tracking
- ✓ `switches` - Switch history
- ✓ `model_registry` - ML model management
- ✓ `model_upload_sessions` - Upload tracking
- ✓ `system_events` - System event log
- ✓ `audit_logs` - Audit trail
- ✓ `notifications` - User notifications
- ✓ `clients_daily_snapshot` - Daily snapshots

### Replica Management Tables (2)
- ✓ `replica_instances` - Full replica tracking with sync status
- ✓ `spot_interruption_events` - Interruption event log

### Pricing Tables (7)
- ✓ `spot_price_snapshots` - Raw spot price data
- ✓ `ondemand_price_snapshots` - Raw on-demand price data
- ✓ `ondemand_prices` - Current on-demand pricing
- ✓ `spot_prices` - Current spot pricing
- ✓ `pricing_reports` - Pricing reports from agents
- ✓ `pricing_snapshots_clean` - **Time-bucketed for charts**
- ✓ `risk_scores` - Pool risk analysis

### Cost & Savings Tables (3)
- ✓ `cost_records` - Hourly cost tracking
- ✓ `client_savings_monthly` - Monthly aggregations
- ✓ `client_savings_daily` - **Daily aggregations for graphs**

### ML & Decision Tables (3)
- ✓ `model_predictions` - Model prediction log
- ✓ `agent_decision_history` - Agent decision tracking
- ✓ `decision_engine_log` - Decision engine audit
- ✓ `pending_switch_commands` - Queued switches

### Optimization Tables (2)
- ✓ `pool_reliability_metrics` - Pool health & interruption tracking
- ✓ `instance_metrics` - Real-time performance monitoring (optional)

## 🚀 Setup Instructions

### Step 1: Backup Existing Database (if you have one)
```bash
mysqldump -u username -p database_name > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Create Database (if new installation)
```bash
mysql -u username -p
```

```sql
CREATE DATABASE IF NOT EXISTS aws_spot_optimizer;
USE aws_spot_optimizer;
```

### Step 3: Run The Schema
```bash
mysql -u username -p aws_spot_optimizer < schema.sql
```

**That's it!** All 30 tables are created with proper indexes and foreign keys.

### Step 4: Verify Installation
```sql
-- Check all tables were created
SELECT COUNT(*) as table_count FROM information_schema.tables
WHERE table_schema = 'aws_spot_optimizer';
-- Should return: 30

-- Verify critical tables
SHOW TABLES LIKE '%replica%';
SHOW TABLES LIKE '%pricing%';
SHOW TABLES LIKE '%savings%';

-- Check agents table has replica columns
DESCRIBE agents;
-- Should include: manual_replica_enabled, current_replica_id, last_failover_at
```

## 🔧 Update Existing Database

If you already have the old schema running, you can update it:

```sql
-- Run these ALTER statements to add missing columns
ALTER TABLE agents
    ADD COLUMN IF NOT EXISTS manual_replica_enabled BOOLEAN DEFAULT FALSE AFTER replica_count,
    ADD COLUMN IF NOT EXISTS current_replica_id VARCHAR(255) DEFAULT NULL AFTER manual_replica_enabled,
    ADD COLUMN IF NOT EXISTS last_interruption_signal TIMESTAMP NULL AFTER last_switch_at,
    ADD COLUMN IF NOT EXISTS interruption_handled_count INT DEFAULT 0 AFTER last_interruption_signal,
    ADD COLUMN IF NOT EXISTS last_failover_at TIMESTAMP NULL AFTER interruption_handled_count;

-- Then run the full schema.sql - it uses IF NOT EXISTS so it won't duplicate tables
SOURCE schema.sql;
```

## 📊 What Each Table Enables

| Table | UI Feature | Required |
|-------|-----------|----------|
| `replica_instances` | Replicas tab | **Critical** |
| `pricing_snapshots_clean` | Multi-pool price charts | **Critical** |
| `spot_interruption_events` | Emergency tracking | **Critical** |
| `client_savings_daily` | Daily/weekly graphs | Important |
| `pool_reliability_metrics` | Pool rankings | Important |
| `instance_metrics` | Real-time monitoring | Optional |

## ⚙️ Configuration

### Backend Connection
Update `config.py` with your database credentials:
```python
DB_HOST = 'localhost'
DB_PORT = 3306
DB_NAME = 'aws_spot_optimizer'
DB_USER = 'your_username'
DB_PASSWORD = 'your_password'
```

### Required Privileges
Your MySQL user needs these privileges:
```sql
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
ON aws_spot_optimizer.*
TO 'your_username'@'localhost';

FLUSH PRIVILEGES;
```

## 🔍 Troubleshooting

### Error: "Access denied"
- Check username/password in config.py
- Verify user has correct privileges: `SHOW GRANTS FOR 'username'@'localhost';`

### Error: "Table doesn't exist"
- Ensure schema.sql ran successfully: `SHOW TABLES;`
- Check for errors in MySQL error log

### CORS Error on Replicas Tab
- Verify `replica_instances` table exists: `SHOW TABLES LIKE 'replica%';`
- Restart backend after schema changes

### Multi-pool Chart Not Working
- Verify `pricing_snapshots_clean` exists
- Check if data is being populated: `SELECT COUNT(*) FROM pricing_snapshots_clean;`

## 📝 Schema Updates

The schema includes:
- **Auto-incrementing IDs** for log tables
- **Foreign key constraints** for data integrity
- **Indexes** on frequently queried columns
- **JSON columns** for flexible metadata
- **Enum types** for status fields
- **Timestamp tracking** on all tables

## 🎯 Next Steps

After setting up the database:

1. ✅ Start the backend server
   ```bash
   cd /home/user/final-ml
   python backend.py
   ```

2. ✅ Verify backend connects
   - Check logs for "Database connection pool initialized"

3. ✅ Test UI features
   - Navigate to Replicas tab (should load)
   - View multi-pool price charts (should show data)
   - Check switch history

4. ✅ Set up agents
   - Install agent on EC2 instances
   - Configure auto-switch or manual replica mode

## 📚 Additional Notes

- **Idempotent**: Safe to run schema.sql multiple times (uses `IF NOT EXISTS`)
- **No migrations**: Everything in one file for simplicity
- **Production-ready**: Includes all optimizations and indexes
- **Backwards compatible**: Existing data is preserved when updating

---

**Need Help?**
- Check `README.md` for system documentation
- Review backend logs in `logs/` directory
- Test connection: `mysql -u username -p -e "SELECT 1"`
