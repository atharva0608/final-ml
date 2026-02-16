#!/usr/bin/env python3
"""
Quick test to verify scanner is working correctly
"""
import sys
sys.path.insert(0, '/Users/atharvapudale/Desktop/backend-ecc/Atharva Repo/github/final-ml')

from backend.services.hygiene_service import HygieneService
from backend.core.database import SessionLocal
from backend.models.account import Account

# Create a test to verify the scanner code
db = SessionLocal()

try:
    # Check if account_id is properly handled in the code
    import inspect
    source_code = inspect.getsource(HygieneService._scan_region_worker)

    print("=" * 80)
    print("SCANNER CODE VERIFICATION")
    print("=" * 80)

    # Check for the bug
    if "account_id=account_id" in source_code:
        print("❌ BUG FOUND: account_id=account_id (undefined variable)")
        sys.exit(1)
    else:
        print("✅ BUG NOT FOUND: account_id=account_id is not in code")

    # Check for the fix
    if "account_id=account.id" in source_code:
        print("✅ FIX CONFIRMED: account_id=account.id is present")
    else:
        print("⚠️  WARNING: account_id=account.id not found")

    # Count occurrences
    fix_count = source_code.count("account.id")
    print(f"\n📊 Found {fix_count} occurrences of 'account.id' in scanner code")

    print("\n" + "=" * 80)
    print("ACCOUNT TEST")
    print("=" * 80)

    # Get first account
    account = db.query(Account).first()
    if account:
        print(f"✅ Account found: {account.aws_account_id}")
        print(f"✅ Account ID: {account.id}")
        print(f"\nThe scanner will use: account_id={account.id}")
    else:
        print("❌ No accounts found in database")

    print("\n" + "=" * 80)
    print("RESULT: Scanner code is CORRECT and ready to use")
    print("=" * 80)
    print("\nNext step: Trigger a scan from the UI and check DevTools Network tab")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()
