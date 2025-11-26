#!/bin/bash
# ============================================================================
# Apply Termination Tracking Migration
# This script adds the missing termination_attempted_at and termination_confirmed columns
# ============================================================================

set -e

echo "=========================================="
echo "Termination Tracking Migration"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found"
    echo "Please create a .env file with your database credentials"
    exit 1
fi

# Load environment variables
source .env

# Check required variables
if [ -z "$DB_HOST" ] || [ -z "$DB_USER" ] || [ -z "$DB_NAME" ]; then
    echo "Error: Missing required environment variables"
    echo "Required: DB_HOST, DB_USER, DB_NAME, DB_PASSWORD"
    exit 1
fi

echo "Database: $DB_NAME"
echo "Host: $DB_HOST"
echo ""

# Prompt for password if not set
if [ -z "$DB_PASSWORD" ]; then
    read -sp "Enter database password: " DB_PASSWORD
    echo ""
fi

# Run the migration
echo "Applying migration..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" << 'EOF'

-- Add tracking columns to instances table
ALTER TABLE instances
    ADD COLUMN IF NOT EXISTS termination_attempted_at TIMESTAMP NULL COMMENT 'When agent last attempted to terminate this instance',
    ADD COLUMN IF NOT EXISTS termination_confirmed BOOLEAN DEFAULT FALSE COMMENT 'TRUE if AWS confirmed termination';

-- Add tracking columns to replica_instances table
ALTER TABLE replica_instances
    ADD COLUMN IF NOT EXISTS termination_attempted_at TIMESTAMP NULL COMMENT 'When agent last attempted to terminate this instance',
    ADD COLUMN IF NOT EXISTS termination_confirmed BOOLEAN DEFAULT FALSE COMMENT 'TRUE if AWS confirmed termination';

-- Add indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_instances_zombie_termination ON instances(instance_status, termination_attempted_at, region);
CREATE INDEX IF NOT EXISTS idx_replicas_termination ON replica_instances(status, termination_attempted_at, agent_id);

SELECT 'Migration completed successfully!' as result;

EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Migration applied successfully!"
    echo ""
    echo "Columns added:"
    echo "  - instances.termination_attempted_at"
    echo "  - instances.termination_confirmed"
    echo "  - replica_instances.termination_attempted_at"
    echo "  - replica_instances.termination_confirmed"
    echo ""
    echo "Indexes created:"
    echo "  - idx_instances_zombie_termination"
    echo "  - idx_replicas_termination"
else
    echo ""
    echo "❌ Migration failed!"
    echo "Please check the error messages above"
    exit 1
fi
