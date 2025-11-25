#!/usr/bin/env python3
"""
Quick fix script to add the missing config_version column.
This script uses the backend's database configuration.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    import mysql.connector
    from mysql.connector import Error

    # Import backend config
    from backend import config, get_db_connection

    print("=" * 70)
    print("Applying Database Fix: Add config_version column")
    print("=" * 70)
    print()

    # Get database connection
    print(f"Connecting to database: {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    conn = get_db_connection()

    if not conn:
        print("✗ Failed to connect to database")
        sys.exit(1)

    print("✓ Connected to database")

    cursor = conn.cursor()

    # Check if column exists
    print("\nChecking if config_version column exists...")
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'agents'
          AND COLUMN_NAME = 'config_version'
    """, (config.DB_NAME,))

    result = cursor.fetchone()
    column_exists = result[0] > 0

    if column_exists:
        print("✓ config_version column already exists")
        cursor.close()
        conn.close()
        print("\n" + "=" * 70)
        print("No changes needed - column already exists!")
        print("=" * 70)
        sys.exit(0)

    # Add the column
    print("Adding config_version column...")
    cursor.execute("""
        ALTER TABLE agents
        ADD COLUMN config_version INT DEFAULT 0
        COMMENT 'Configuration version counter for forcing agent config refresh'
        AFTER agent_version
    """)

    conn.commit()
    print("✓ Column added successfully")

    # Verify
    print("\nVerifying column was added...")
    cursor.execute("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            COLUMN_DEFAULT,
            IS_NULLABLE,
            COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'agents'
          AND COLUMN_NAME = 'config_version'
    """, (config.DB_NAME,))

    result = cursor.fetchone()
    if result:
        print(f"  Column Name: {result[0]}")
        print(f"  Data Type: {result[1]}")
        print(f"  Default: {result[2]}")
        print(f"  Nullable: {result[3]}")
        print(f"  Comment: {result[4]}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 70)
    print("✓ Fix applied successfully!")
    print("=" * 70)
    print("\nYou can now:")
    print("1. Reload your browser")
    print("2. Try saving agent configuration again")
    print()

except ImportError as e:
    print(f"✗ Import error: {e}")
    print("\nPlease ensure you're running this from the project root directory")
    print("and that the backend dependencies are installed.")
    sys.exit(1)
except Error as e:
    print(f"\n✗ Database error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
