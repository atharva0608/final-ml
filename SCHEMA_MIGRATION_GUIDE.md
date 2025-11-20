# Database Schema Migration Guide

## 📋 Current Status

Your database schema has **critical gaps** that need to be filled for all UI features to work properly.

## 🚨 Critical Missing Components

### 1. **agents table missing columns**
- `manual_replica_enabled` - Required for mutual exclusivity
- `current_replica_id` - Track active replica
- `last_interruption_signal` - Emergency tracking
- `last_failover_at` - Failover history

### 2. **Missing Tables** (exist only in migration files)
- `replica_instances` - **Required for Replicas tab**
- `pricing_snapshots_clean` - **Required for multi-pool charts**
- `spot_interruption_events` - **Required for emergency tracking**

### 3. **Missing Optimization Tables**
- `client_savings_daily` - Daily/weekly savings graphs
- `pool_reliability_metrics` - Pool health tracking
- `instance_metrics` - Real-time monitoring (optional)

## ✅ Migration Files Available

### **Migration 006** (Existing)
Location: `/home/user/final-ml/migrations/006_replica_management_schema.sql`

Contains:
- ✓ `replica_instances` table
- ✓ `pricing_snapshots_clean` table
- ✓ `spot_interruption_events` table
- ✓ Additional pricing tables

**Status:** ⚠️ NOT APPLIED - Must run this first

### **Migration 007** (NEW - Just Created)
Location: `/home/user/final-ml/migrations/007_schema_completion.sql`

Contains:
- ✓ Updates to `agents` table (adds manual_replica_enabled)
- ✓ All missing tables from migration 006 (backup in case 006 not run)
- ✓ `client_savings_daily` table
- ✓ `pool_reliability_metrics` table
- ✓ `instance_metrics` table (optional)
- ✓ Helper views: `v_active_replicas`, `v_pool_reliability_ranking`
- ✓ Stored procedures: `compute_daily_savings`, `compute_pool_reliability`

**Status:** ✅ READY TO APPLY

## 🔧 How To Apply Migrations

### Option 1: Run Migration 007 Only (Recommended)
Migration 007 includes everything from 006 plus additional optimizations.

```bash
# Connect to MySQL
mysql -u your_username -p your_database_name

# Run the migration
source /home/user/final-ml/migrations/007_schema_completion.sql

# Or from command line
mysql -u your_username -p your_database_name < /home/user/final-ml/migrations/007_schema_completion.sql
```

### Option 2: Run Both Migrations
If you want to be extra safe:

```bash
# Run migration 006 first
mysql -u your_username -p your_database_name < /home/user/final-ml/migrations/006_replica_management_schema.sql

# Then run migration 007
mysql -u your_username -p your_database_name < /home/user/final-ml/migrations/007_schema_completion.sql
```

### Verification Commands

After running migrations, verify the changes:

```sql
-- Check if manual_replica_enabled column was added
DESCRIBE agents;

-- Check if replica_instances table exists
SHOW TABLES LIKE 'replica%';

-- Check if pricing_snapshots_clean exists
SHOW TABLES LIKE 'pricing_snapshots_clean';

-- Check new views
SHOW FULL TABLES WHERE Table_type = 'VIEW';

-- Check stored procedures
SHOW PROCEDURE STATUS WHERE Db = DATABASE();

-- Verify migration tracking
SELECT * FROM schema_migrations ORDER BY version DESC;
```

## 📊 What Each Table Enables

| Table | UI Feature | Status |
|-------|-----------|---------|
| `replica_instances` | Replicas tab | ⚠️ Required |
| `pricing_snapshots_clean` | Multi-pool price charts | ⚠️ Required |
| `spot_interruption_events` | Emergency failover tracking | ⚠️ Required |
| `client_savings_daily` | Daily/weekly savings graphs | ℹ️ Optimization |
| `pool_reliability_metrics` | Pool health indicators | ℹ️ Optimization |
| `instance_metrics` | Real-time monitoring | ℹ️ Optional |

## 🎯 After Migration

### 1. Restart Backend
```bash
cd /home/user/final-ml
# Kill old process
pkill -f "python.*backend.py"

# Start new process
python backend.py
```

### 2. Test UI Features
- ✅ Navigate to Replicas tab (should load without CORS error)
- ✅ Check multi-pool price history chart (7-day graph)
- ✅ Enable manual replica mode in agent config
- ✅ View switch history with full details

### 3. Run Stored Procedures (Optional)

Compute daily savings:
```sql
CALL compute_daily_savings(CURDATE());
CALL compute_daily_savings(DATE_SUB(CURDATE(), INTERVAL 1 DAY));
```

Compute pool reliability (last 24 hours):
```sql
CALL compute_pool_reliability(24);
```

## ⚠️ Important Notes

1. **Backup First**: Always backup your database before running migrations
   ```bash
   mysqldump -u username -p database_name > backup_$(date +%Y%m%d).sql
   ```

2. **Check Permissions**: Ensure your MySQL user has CREATE, ALTER, INDEX privileges

3. **Test Environment**: If possible, test migrations on a copy first

4. **No Data Loss**: All migrations use `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` to prevent errors

5. **Idempotent**: Safe to run multiple times (won't duplicate data)

## 🐛 Troubleshooting

### Error: "Table already exists"
✅ **Safe to ignore** - The migration uses `IF NOT EXISTS`

### Error: "Unknown column"
❌ **Run migration 007** - Missing the column updates

### Error: "Access denied"
❌ **Check permissions** - User needs CREATE, ALTER, INDEX privileges

### CORS Error on Replicas Tab
❌ **Restart backend** after running migration - New endpoint needs table to exist

## 📝 Summary

**What You Need:**
1. ✅ Run `migrations/007_schema_completion.sql` ← **Do this**
2. ✅ Restart backend server
3. ✅ Test Replicas tab and multi-pool charts

**What You Get:**
- ✅ Full replica management functionality
- ✅ Multi-pool price history charts (7-day)
- ✅ Daily/weekly savings aggregations
- ✅ Pool reliability tracking for "safest pool" selection
- ✅ Emergency interruption handling
- ✅ Optional real-time metrics
