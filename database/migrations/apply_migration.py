#!/usr/bin/env python3
"""
Apply Termination Tracking Migration
Adds termination_attempted_at and termination_confirmed columns to instances and replica_instances tables
"""

import os
import sys
import mysql.connector
from mysql.connector import Error

def load_env():
    """Load environment variables from .env file"""
    env_vars = {}
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')

    if not os.path.exists(env_path):
        print("❌ Error: .env file not found")
        print(f"Expected location: {env_path}")
        return None

    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")

    return env_vars

def apply_migration(connection):
    """Apply the migration SQL"""
    cursor = connection.cursor()

    migrations = [
        # Add columns to instances table
        """
        ALTER TABLE instances
        ADD COLUMN IF NOT EXISTS termination_attempted_at TIMESTAMP NULL
            COMMENT 'When agent last attempted to terminate this instance'
        """,
        """
        ALTER TABLE instances
        ADD COLUMN IF NOT EXISTS termination_confirmed BOOLEAN DEFAULT FALSE
            COMMENT 'TRUE if AWS confirmed termination'
        """,

        # Add columns to replica_instances table
        """
        ALTER TABLE replica_instances
        ADD COLUMN IF NOT EXISTS termination_attempted_at TIMESTAMP NULL
            COMMENT 'When agent last attempted to terminate this instance'
        """,
        """
        ALTER TABLE replica_instances
        ADD COLUMN IF NOT EXISTS termination_confirmed BOOLEAN DEFAULT FALSE
            COMMENT 'TRUE if AWS confirmed termination'
        """,

        # Add indexes
        """
        CREATE INDEX IF NOT EXISTS idx_instances_zombie_termination
        ON instances(instance_status, termination_attempted_at, region)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_replicas_termination
        ON replica_instances(status, termination_attempted_at, agent_id)
        """
    ]

    try:
        for i, migration in enumerate(migrations, 1):
            print(f"Executing migration {i}/{len(migrations)}...", end=' ')
            cursor.execute(migration)
            print("✅")

        connection.commit()
        return True
    except Error as e:
        print(f"\n❌ Migration failed: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()

def main():
    print("=" * 60)
    print("Termination Tracking Migration")
    print("=" * 60)
    print()

    # Load environment variables
    env_vars = load_env()
    if not env_vars:
        sys.exit(1)

    # Get database credentials
    db_host = env_vars.get('DB_HOST', 'localhost')
    db_user = env_vars.get('DB_USER')
    db_password = env_vars.get('DB_PASSWORD')
    db_name = env_vars.get('DB_NAME')
    db_port = int(env_vars.get('DB_PORT', 3306))

    if not all([db_host, db_user, db_password, db_name]):
        print("❌ Error: Missing required database credentials")
        print("Required: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME")
        sys.exit(1)

    print(f"Database: {db_name}")
    print(f"Host: {db_host}:{db_port}")
    print(f"User: {db_user}")
    print()

    # Connect to database
    print("Connecting to database...", end=' ')
    try:
        connection = mysql.connector.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        print("✅")
    except Error as e:
        print(f"\n❌ Connection failed: {e}")
        sys.exit(1)

    # Apply migration
    print()
    print("Applying migration...")
    success = apply_migration(connection)

    connection.close()

    if success:
        print()
        print("✅ Migration completed successfully!")
        print()
        print("Columns added:")
        print("  • instances.termination_attempted_at")
        print("  • instances.termination_confirmed")
        print("  • replica_instances.termination_attempted_at")
        print("  • replica_instances.termination_confirmed")
        print()
        print("Indexes created:")
        print("  • idx_instances_zombie_termination")
        print("  • idx_replicas_termination")
        print()
        print("⚠️  IMPORTANT: Restart your backend server for changes to take effect")
    else:
        print()
        print("❌ Migration failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
