#!/usr/bin/env python3
"""Quick test to verify scanner fix is applied"""
import inspect
from backend.services.hygiene_service import HygieneService

print("=" * 80)
print("SCANNER CODE VERIFICATION - account_id Fix")
print("=" * 80)

# Get the source code of the scanner method
source_code = inspect.getsource(HygieneService._scan_region_worker)

# Check for the bug (account_id=account_id)
bug_found = source_code.count("account_id=account_id")
# Check for the fix (account_id=account.id)
fix_found = source_code.count("account_id=account.id")

print(f"\n🔍 Checking for BUG (account_id=account_id)...")
if bug_found > 0:
    print(f"   ❌ FOUND {bug_found} occurrences - BUG STILL EXISTS!")
    exit(1)
else:
    print(f"   ✅ NOT FOUND - Bug has been removed!")

print(f"\n🔍 Checking for FIX (account_id=account.id)...")
if fix_found > 0:
    print(f"   ✅ FOUND {fix_found} occurrences - Fix is applied!")
else:
    print(f"   ⚠️  NOT FOUND - Fix may not be applied")

print("\n" + "=" * 80)
print("RESULT")
print("=" * 80)

if bug_found == 0 and fix_found > 0:
    print("✅ Scanner code is CORRECT!")
    print("✅ The undefined account_id bug has been fixed")
    print(f"✅ Found {fix_found} correct usages of account.id")
    print("\n👉 You can now trigger a scan from the UI")
    exit(0)
else:
    print("❌ Scanner code has issues!")
    exit(1)
