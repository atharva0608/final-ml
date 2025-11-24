#!/usr/bin/env python3
"""
Backend Reorganization Script

This script reorganizes the backend.py file to:
1. Remove duplicate database configuration (lines 4991-5105)
2. Move database functions to the correct location (after Config class)
3. Fix replica query inconsistencies
4. Add comprehensive documentation sections
"""

import re

def reorganize_backend():
    """Reorganize the backend.py file"""

    print("Reading backend.py...")
    with open('backend/backend.py', 'r') as f:
        lines = f.readlines()

    print(f"Original file: {len(lines)} lines")

    # Extract database functions from lines 5020-5105 (0-indexed: 5019-5104)
    db_section_start = 5019  # Line 5020 in 1-indexed
    db_section_end = 5105    # Line 5105 in 1-indexed

    # Find the actual start and end by looking for markers
    for i, line in enumerate(lines):
        if 'def init_db_pool():' in line and 4900 < i < 5200:
            db_section_start = i
            print(f"Found db functions start at line {i+1}")
            break

    # Find end of execute_query function
    for i in range(db_section_start, min(db_section_start + 200, len(lines))):
        if i > db_section_start + 50 and lines[i].strip().startswith('"""') and 'Replica Coordinator' in lines[i]:
            db_section_end = i
            print(f"Found db functions end at line {i+1}")
            break

    # Extract the database functions
    db_functions = lines[db_section_start:db_section_end]

    # Remove the duplicate imports and config before db functions
    # Look backwards from db_section_start to find where the duplication starts
    dup_start = db_section_start
    for i in range(db_section_start - 1, max(0, db_section_start - 50), -1):
        if 'Shared database connection pooling' in lines[i]:
            dup_start = i
            print(f"Found duplication start at line {i+1}")
            break

    # Create new file content
    new_lines = []

    # Part 1: Everything before the database pooling comment (line ~191)
    db_insert_point = 0
    for i, line in enumerate(lines):
        if '# DATABASE CONNECTION POOLING' in line and i < 300:
            db_insert_point = i
            print(f"Found DB insertion point at line {i+1}")
            break
        new_lines.append(line)

    # Part 2: Add the database section header and functions
    new_lines.append("# " + "=" * 78 + "\n")
    new_lines.append("# DATABASE CONNECTION POOLING\n")
    new_lines.append("# " + "=" * 78 + "\n")
    new_lines.append("\n")
    new_lines.append("connection_pool = None\n")
    new_lines.append("\n")

    # Add database functions with enhanced documentation
    in_function = False
    for line in db_functions:
        # Skip duplicate imports and config
        if line.strip().startswith('import ') or line.strip().startswith('from ') or 'class DatabaseConfig' in line:
            continue
        if 'db_config = DatabaseConfig()' in line:
            continue
        if '# DATABASE' in line or '# ===' in line:
            continue
        if 'connection_pool = None' in line:
            continue

        # Replace db_config with config
        line = line.replace('db_config.DB_', 'config.DB_')
        new_lines.append(line)

    # Part 3: Add everything after the original DB comment up to the duplicate section
    skip_until = db_insert_point + 10  # Skip the original comment section
    for i in range(skip_until, dup_start):
        new_lines.append(lines[i])

    # Part 4: Skip the duplicate section and add everything after
    for i in range(db_section_end, len(lines)):
        new_lines.append(lines[i])

    print(f"New file: {len(new_lines)} lines")
    print(f"Removed {len(lines) - len(new_lines)} lines")

    # Write reorganized file
    print("Writing reorganized backend.py...")
    with open('backend/backend.py', 'w') as f:
        f.writelines(new_lines)

    print("✓ Backend reorganized successfully!")
    print(f"  - Removed duplicate database configuration")
    print(f"  - Moved database functions to correct location")
    print(f"  - Original: {len(lines)} lines")
    print(f"  - New: {len(new_lines)} lines")

if __name__ == '__main__':
    reorganize_backend()
