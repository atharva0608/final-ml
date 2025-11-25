#!/usr/bin/env python3
"""
Migration script to add config_version column to agents table.
This fixes the "Unknown column 'config_version' in 'field list'" error.
"""

import os
import sys
import mysql.connector
from mysql.connector import Error

# Add backend to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def get_db_config():
    """Get database configuration from environment or defaults."""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 3306)),
        'user': os.getenv('DB_USER', 'spotuser'),
        'password': os.getenv('DB_PASSWORD', 'SpotUser2024!'),
        'database': os.getenv('DB_NAME', 'spot_optimizer')
    }

def check_column_exists(cursor, table, column):
    """Check if a column exists in a table."""
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """, (table, column))
    result = cursor.fetchone()
    return result[0] > 0

def add_config_version_column(cursor):
    """Add config_version column to agents table."""
    print("Checking if config_version column exists...")

    if check_column_exists(cursor, 'agents', 'config_version'):
        print("✓ config_version column already exists in agents table")
        return False

    print("Adding config_version column to agents table...")
    cursor.execute("""
        ALTER TABLE agents
        ADD COLUMN config_version INT DEFAULT 0 COMMENT 'Configuration version counter for forcing agent config refresh'
        AFTER agent_version
    """)
    print("✓ config_version column added successfully")
    return True

def verify_column(cursor):
    """Verify the column was added correctly."""
    cursor.execute("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            IS_NULLABLE,
            COLUMN_DEFAULT,
            COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'agents'
          AND COLUMN_NAME = 'config_version'
    """)
    result = cursor.fetchone()
    if result:
        print(f"\nColumn details:")
        print(f"  Name: {result[0]}")
        print(f"  Type: {result[1]}")
        print(f"  Nullable: {result[2]}")
        print(f"  Default: {result[3]}")
        print(f"  Comment: {result[4]}")
        return True
    return False

def main():
    """Main migration function."""
    print("=" * 70)
    print("Migration: Add config_version column to agents table")
    print("=" * 70)

    db_config = get_db_config()
    print(f"\nConnecting to database: {db_config['user']}@{db_config['host']}:{db_config['port']}/{db_config['database']}")

    connection = None
    try:
        # Connect to database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        print("✓ Database connection established")

        # Add the column
        column_added = add_config_version_column(cursor)

        # Commit changes
        if column_added:
            connection.commit()
            print("✓ Changes committed")

        # Verify
        if verify_column(cursor):
            print("\n" + "=" * 70)
            print("✓ Migration completed successfully!")
            print("=" * 70)
            return 0
        else:
            print("\n✗ Verification failed - column not found")
            return 1

    except Error as e:
        print(f"\n✗ Database error: {e}")
        if connection:
            connection.rollback()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        if connection:
            connection.rollback()
        return 1
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            print("\nDatabase connection closed")

if __name__ == "__main__":
    sys.exit(main())
