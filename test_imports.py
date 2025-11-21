#!/usr/bin/env python3
"""
Test script to verify all imports work correctly
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

print("=" * 70)
print("Testing AWS Spot Optimizer - Import Verification")
print("=" * 70)
print()

# Test 1: Import backend module
print("Test 1: Importing backend module...")
try:
    # We can't fully import backend.py because it starts Flask and requires DB
    # But we can test syntax and parse the file
    import py_compile
    backend_path = os.path.join(os.path.dirname(__file__), 'backend', 'backend.py')
    py_compile.compile(backend_path, doraise=True)
    print("  ✓ backend.py syntax is valid")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 2: Verify database_utils is not imported
print("\nTest 2: Checking for removed database_utils imports...")
try:
    with open(backend_path, 'r') as f:
        content = f.read()
        if 'from database_utils import' in content or 'import database_utils' in content:
            # Check if these are in comments
            lines = content.split('\n')
            uncommented_imports = [line for line in lines
                                  if ('from database_utils import' in line or 'import database_utils' in line)
                                  and not line.strip().startswith('#')]
            if uncommented_imports:
                print(f"  ✗ ERROR: Found database_utils imports:")
                for line in uncommented_imports[:3]:
                    print(f"    {line.strip()}")
                sys.exit(1)
    print("  ✓ No active database_utils imports found")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 3: Verify database functions exist in backend.py
print("\nTest 3: Checking database functions are defined...")
try:
    with open(backend_path, 'r') as f:
        content = f.read()
        required_functions = ['def init_db_pool', 'def get_db_connection', 'def execute_query']
        missing = []
        for func in required_functions:
            if func not in content:
                missing.append(func)

        if missing:
            print(f"  ✗ ERROR: Missing functions: {', '.join(missing)}")
            sys.exit(1)
    print("  ✓ All required database functions are defined")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 4: Check smart_emergency_fallback.py
print("\nTest 4: Checking smart_emergency_fallback.py...")
try:
    sef_path = os.path.join(os.path.dirname(__file__), 'backend', 'smart_emergency_fallback.py')
    if os.path.exists(sef_path):
        py_compile.compile(sef_path, doraise=True)
        print("  ✓ smart_emergency_fallback.py syntax is valid")
    else:
        print("  ⚠ smart_emergency_fallback.py not found (optional)")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 5: Check database schema
print("\nTest 5: Checking database/schema.sql...")
try:
    schema_path = os.path.join(os.path.dirname(__file__), 'database', 'schema.sql')
    if not os.path.exists(schema_path):
        print(f"  ✗ ERROR: schema.sql not found at {schema_path}")
        sys.exit(1)

    with open(schema_path, 'r') as f:
        content = f.read()

        # Check for the ENUM NULL bug we fixed
        if "ENUM('rebalance-recommendation', 'termination-notice', NULL)" in content:
            print("  ✗ ERROR: Found ENUM with NULL value (SQL syntax error)")
            sys.exit(1)

        # Basic check: should have CREATE TABLE statements
        if content.count('CREATE TABLE') < 10:
            print(f"  ⚠ WARNING: Only {content.count('CREATE TABLE')} CREATE TABLE statements found")

    print(f"  ✓ schema.sql exists ({len(content)} bytes)")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 6: Check agent requirements
print("\nTest 6: Checking agent/requirements.txt...")
try:
    agent_req_path = os.path.join(os.path.dirname(__file__), 'agent', 'requirements.txt')
    if os.path.exists(agent_req_path):
        with open(agent_req_path, 'r') as f:
            reqs = f.read().strip()
            if reqs:
                print(f"  ✓ agent/requirements.txt exists")
            else:
                print("  ⚠ agent/requirements.txt is empty")
    else:
        print("  ⚠ agent/requirements.txt not found")
except Exception as e:
    print(f"  ✗ ERROR: {e}")

# Test 7: Check backend requirements
print("\nTest 7: Checking backend/requirements.txt...")
try:
    backend_req_path = os.path.join(os.path.dirname(__file__), 'backend', 'requirements.txt')
    if not os.path.exists(backend_req_path):
        print(f"  ✗ ERROR: backend/requirements.txt not found")
        sys.exit(1)

    with open(backend_req_path, 'r') as f:
        reqs = f.read()
        required_packages = ['Flask', 'mysql-connector-python', 'flask-cors', 'APScheduler']
        missing = []
        for pkg in required_packages:
            if pkg.lower() not in reqs.lower():
                missing.append(pkg)

        if missing:
            print(f"  ✗ ERROR: Missing packages: {', '.join(missing)}")
            sys.exit(1)

    print(f"  ✓ backend/requirements.txt has all required packages")
except Exception as e:
    print(f"  ✗ ERROR: {e}")
    sys.exit(1)

# Test 8: Check project structure
print("\nTest 8: Verifying project structure...")
try:
    required_paths = [
        'backend/backend.py',
        'backend/requirements.txt',
        'database/schema.sql',
        'agent/agent.py',
        'agent/requirements.txt',
        'frontend/package.json',
        'scripts/setup.sh',
        'docs/HOW_IT_WORKS.md',
        'docs/PROBLEMS_AND_SOLUTIONS.md'
    ]

    base_dir = os.path.dirname(__file__)
    missing = []
    for path in required_paths:
        full_path = os.path.join(base_dir, path)
        if not os.path.exists(full_path):
            missing.append(path)

    if missing:
        print(f"  ⚠ WARNING: Missing files:")
        for path in missing:
            print(f"    - {path}")
    else:
        print(f"  ✓ All required files present")
except Exception as e:
    print(f"  ✗ ERROR: {e}")

print()
print("=" * 70)
print("✅ All critical tests passed!")
print("=" * 70)
print()
print("Next steps:")
print("1. Commit and push changes to branch")
print("2. Deploy to production server")
print("3. Run setup.sh to configure environment")
print("4. Test backend startup: systemctl status spot-optimizer-backend")
print("5. Check database connection: ./scripts/test_database.sh")
print()
