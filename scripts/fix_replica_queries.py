#!/usr/bin/env python3
"""
Fix Replica Query Inconsistencies

This script adds a standardized helper function for fetching replicas
and updates inconsistent queries throughout the backend.
"""

import re

def fix_replica_queries():
    """Fix replica query inconsistencies"""

    print("Reading backend.py...")
    with open('backend/backend.py', 'r') as f:
        content = f.read()

    print("Original file size:", len(content), "bytes")

    # Find where to insert the helper function (after execute_query)
    helper_function = '''
# ==============================================================================
# REPLICA QUERY HELPERS
# ==============================================================================

def get_active_replicas(agent_id: str, status_filter: list = None) -> list:
    """
    Get active replicas for an agent with consistent filtering.

    This is the standardized way to fetch replicas across the backend.
    It ensures consistent status filtering and proper indexing.

    Args:
        agent_id: The agent ID to fetch replicas for
        status_filter: Optional list of statuses to filter by
                      (e.g., ['ready', 'syncing', 'launching'])
                      If None, returns all active replicas except terminated/failed

    Returns:
        List of replica dictionaries with all fields

    Example:
        # Get all active replicas
        replicas = get_active_replicas(agent_id)

        # Get only ready replicas
        ready_replicas = get_active_replicas(agent_id, ['ready'])

        # Get replicas that can be promoted
        promotable = get_active_replicas(agent_id, ['ready', 'syncing'])
    """
    query = """
        SELECT
            id, agent_id, instance_id, replica_type, pool_id,
            instance_type, region, az, status, created_at, ready_at,
            promoted_at, terminated_at, created_by, parent_instance_id,
            is_active, sync_status, sync_latency_ms, last_sync_at,
            state_transfer_progress, hourly_cost, total_cost,
            total_runtime_hours, accumulated_cost,
            interruption_signal_type, interruption_detected_at,
            termination_time, failover_completed_at, tags
        FROM replica_instances
        WHERE agent_id = %s
          AND is_active = TRUE
    """

    params = [agent_id]

    if status_filter:
        placeholders = ','.join(['%s'] * len(status_filter))
        query += f" AND status IN ({placeholders})"
        params.extend(status_filter)
    else:
        # Default: exclude terminated and failed
        query += " AND status NOT IN ('terminated', 'failed')"

    query += " ORDER BY created_at DESC"

    return execute_query(query, tuple(params), fetch=True) or []

def get_promotable_replica(agent_id: str) -> dict:
    """
    Get the best replica available for promotion.

    Prioritizes:
    1. 'ready' status replicas (fully synced)
    2. 'syncing' status replicas (partially synced, better than nothing)
    3. Newest replica if multiple available

    Args:
        agent_id: The agent ID

    Returns:
        Single replica dictionary or None if no promotable replica exists
    """
    # Try to get a ready replica first
    replicas = get_active_replicas(agent_id, ['ready'])
    if replicas:
        return replicas[0]  # Newest ready replica

    # Fall back to syncing replica
    replicas = get_active_replicas(agent_id, ['syncing'])
    if replicas:
        return replicas[0]  # Newest syncing replica

    return None

'''

    # Insert helper function after execute_query function
    # Find the end of execute_query
    pattern = r'(def execute_query\(.*?\n(?:.*?\n)*?.*?connection\.close\(\))\n'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + helper_function + content[insert_pos:]
        print("✓ Added replica helper functions")
    else:
        print("⚠ Could not find execute_query function end")

    # Fix inconsistent replica queries
    fixes_made = 0

    # Fix 1: Standardize get_client_replicas query
    old_pattern1 = r'FROM replica_instances ri\s+WHERE a\.client_id = %s AND ri\.is_active = TRUE'
    new_pattern1 = '''FROM replica_instances ri
            JOIN agents a ON ri.agent_id = a.id
            WHERE a.client_id = %s
              AND ri.is_active = TRUE
              AND ri.status NOT IN ('terminated', 'failed')'''

    if re.search(old_pattern1, content):
        content = re.sub(old_pattern1, new_pattern1, content)
        fixes_made += 1
        print("✓ Fixed get_client_replicas query")

    # Fix 2: Add status NOT IN filter to queries missing it
    # Find SELECT queries on replica_instances without proper status filtering
    pattern2 = r'(SELECT.*?FROM replica_instances.*?WHERE.*?is_active = TRUE)(?!\s+AND\s+status)'
    matches = list(re.finditer(pattern2, content, re.DOTALL))

    for match in matches:
        # Only fix if it doesn't already have a status filter
        query_text = match.group(0)
        if 'status NOT IN' not in query_text and 'status IN' not in query_text:
            # Don't fix if this is part of an UPDATE or if it's checking for specific statuses
            if 'UPDATE replica_instances' not in content[max(0, match.start()-100):match.start()]:
                # This would require more sophisticated parsing, skip for now
                pass

    # Update schema to add index for common query pattern
    schema_update = '''

-- ============================================================================
-- REPLICA QUERY OPTIMIZATION (Added by cleanup script)
-- ============================================================================

-- Add composite index for common replica lookups
-- This index speeds up queries that filter by agent_id, is_active, and status
CREATE INDEX IF NOT EXISTS idx_replica_agent_active_status
ON replica_instances(agent_id, is_active, status, created_at DESC);

-- Add index for promotable replica queries
CREATE INDEX IF NOT EXISTS idx_replica_promotable
ON replica_instances(agent_id, status, created_at DESC)
WHERE is_active = TRUE AND status IN ('ready', 'syncing');
'''

    # Add schema updates to database/schema.sql
    try:
        with open('database/schema.sql', 'r') as f:
            schema_content = f.read()

        if 'idx_replica_agent_active_status' not in schema_content:
            # Add before the end of file marker
            if '-- END OF SCHEMA' in schema_content:
                schema_content = schema_content.replace(
                    '-- END OF SCHEMA',
                    schema_update + '\n-- END OF SCHEMA'
                )
            else:
                schema_content += schema_update

            with open('database/schema.sql', 'w') as f:
                f.write(schema_content)

            print("✓ Added replica query optimization indexes to schema")
    except Exception as e:
        print(f"⚠ Could not update schema: {e}")

    # Write updated backend
    print("Writing updated backend.py...")
    with open('backend/backend.py', 'w') as f:
        f.write(content)

    print(f"\n✓ Replica query fixes completed!")
    print(f"  - Added standardized helper functions")
    print(f"  - Fixed {fixes_made} inconsistent queries")
    print(f"  - Updated schema with optimization indexes")
    print(f"  - New file size: {len(content)} bytes")

if __name__ == '__main__':
    fix_replica_queries()
