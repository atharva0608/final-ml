# Database Schema - Production Lab Mode

This directory contains the production database schema for the Spot Optimizer Platform.

## Schema Files

- **`schema_production.sql`** - Complete PostgreSQL schema with tables, indexes, views, and triggers
- **`models.py`** - SQLAlchemy ORM models (Python)
- **`connection.py`** - Database connection configuration

## Quick Start

### 1. Create PostgreSQL Database

```bash
# Create database
createdb spot_optimizer

# Or using psql
psql -U postgres
CREATE DATABASE spot_optimizer;
```

### 2. Apply Schema

```bash
# Apply the production schema
psql -U postgres -d spot_optimizer -f database/schema_production.sql
```

### 3. Verify Installation

```bash
# Connect to database
psql -U postgres -d spot_optimizer

# List tables
\dt

# View active instances
SELECT * FROM v_active_instances;
```

## Database Tables

### User Management

- **`users`** - User accounts with JWT authentication and role-based access control
  - Roles: `admin`, `user`, `lab`
  - Default credentials: `admin` / `admin` (change in production!)

### AWS Account Management

- **`accounts`** - AWS account configuration with STS AssumeRole
  - **Security**: Uses `external_id` for confused deputy protection
  - **Access**: Agentless cross-account via temporary STS tokens

### Instance Tracking

- **`instances`** - EC2 instance configuration for Lab Mode
  - **Pipeline Modes**: `CLUSTER` (full optimization) or `LINEAR` (single-instance)
  - **Shadow Mode**: Read-only testing without actual switches
  - **Model Assignment**: A/B testing with `assigned_model_version`

### ML Model Management

- **`model_registry`** - ML model version control
  - Model storage: S3 or local filesystem
  - Feature version compatibility tracking
  - Experimental vs. production status

### Experiment Logging

- **`experiment_logs`** - Lab Mode experiment results
  - Full audit trail with feature snapshots
  - Decision tracking (SWITCH, STAY, FALLBACK_ONDEMAND)
  - Performance metrics and timing

## Database Views

### `v_active_instances`

Shows active instances with account and model information:

```sql
SELECT * FROM v_active_instances
WHERE environment_type = 'LAB'
ORDER BY last_evaluation DESC;
```

### `v_recent_experiments`

Shows last 1000 experiment logs with details:

```sql
SELECT * FROM v_recent_experiments
WHERE decision = 'SWITCH'
AND is_shadow_run = FALSE
LIMIT 10;
```

## Environment Variables

Configure database connection in `.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/spot_optimizer
POSTGRES_USER=spot_optimizer_app
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=spot_optimizer
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## Security Best Practices

1. **Change Default Password**: The default `admin` user password must be changed!
2. **Use External ID**: Always set `external_id` in accounts table for AWS security
3. **Rotate Credentials**: STS tokens auto-expire after 1 hour
4. **Database Encryption**: Enable encryption at rest in production
5. **Network Isolation**: Use VPC peering or private subnets

## Migration Guide

### From Sandbox Schema

If migrating from the old sandbox schema:

1. **Backup existing data**:
   ```bash
   pg_dump spot_optimizer > backup.sql
   ```

2. **Drop old schema**:
   ```bash
   psql -U postgres -d spot_optimizer -c "DROP SCHEMA public CASCADE;"
   psql -U postgres -d spot_optimizer -c "CREATE SCHEMA public;"
   ```

3. **Apply new schema**:
   ```bash
   psql -U postgres -d spot_optimizer -f database/schema_production.sql
   ```

### Using Alembic (Recommended)

For version-controlled migrations:

```bash
# Initialize Alembic (if not done)
alembic init alembic

# Generate migration from models
alembic revision --autogenerate -m "Initial production schema"

# Apply migration
alembic upgrade head
```

## Common Queries

### Add New User

```sql
INSERT INTO users (email, username, hashed_password, full_name, role)
VALUES (
    'user@example.com',
    'john_doe',
    '$2b$12$...hashed_password...',  -- Use bcrypt to hash
    'John Doe',
    'user'
);
```

### Add AWS Account

```sql
INSERT INTO accounts (
    user_id,
    account_id,
    account_name,
    environment_type,
    role_arn,
    external_id,
    region
)
VALUES (
    (SELECT id FROM users WHERE username = 'john_doe'),
    '123456789012',
    'Production AWS Account',
    'PROD',
    'arn:aws:iam::123456789012:role/SpotOptimizerRole',
    'unique-external-id-123',  -- Generate unique value
    'ap-south-1'
);
```

### Register Instance

```sql
INSERT INTO instances (
    account_id,
    instance_id,
    instance_type,
    availability_zone,
    pipeline_mode,
    is_shadow_mode
)
VALUES (
    (SELECT id FROM accounts WHERE account_id = '123456789012'),
    'i-1234567890abcdef0',
    'c5.large',
    'ap-south-1a',
    'LINEAR',
    FALSE
);
```

### Query Experiment Results

```sql
-- Model performance comparison
SELECT
    mr.name,
    mr.version,
    COUNT(*) AS total_runs,
    AVG(el.prediction_score) AS avg_crash_prob,
    SUM(CASE WHEN el.decision = 'SWITCH' THEN 1 ELSE 0 END) AS switch_count,
    AVG(el.projected_hourly_savings) AS avg_savings
FROM experiment_logs el
JOIN model_registry mr ON el.model_id = mr.id
WHERE el.execution_time > NOW() - INTERVAL '7 days'
GROUP BY mr.name, mr.version
ORDER BY avg_savings DESC;
```

## Troubleshooting

### Connection Issues

```bash
# Test connection
psql postgresql://user:password@localhost:5432/spot_optimizer

# Check if database exists
psql -U postgres -l | grep spot_optimizer
```

### Permission Issues

```bash
# Grant all permissions to app user
psql -U postgres -d spot_optimizer -c "
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO spot_optimizer_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO spot_optimizer_app;
"
```

### Reset Database

```bash
# WARNING: This deletes all data!
dropdb spot_optimizer
createdb spot_optimizer
psql -U postgres -d spot_optimizer -f database/schema_production.sql
```

## Schema Version

- **Version**: 1.0.0
- **Last Updated**: 2025-12-15
- **PostgreSQL**: 14+
- **Compatible ORM**: SQLAlchemy 2.0+

## Support

For issues or questions:
- See `REFACTOR_STATUS.md` for migration guide
- Check `PRODUCTION_LAB_MODE_REFACTOR.md` for architecture details
