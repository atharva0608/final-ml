#!/usr/bin/env python3
"""
Price Scraper Health Check Demo
Demonstrates live connectivity testing and data validation
"""

from unittest.mock import MagicMock
from utils.component_health_checks import PriceScraperCheck
import json
from datetime import datetime

print("=" * 80)
print("PRICE SCRAPER - LIVE CONNECTIVITY HEALTH CHECK DEMO")
print("=" * 80)
print()
print(f"Test Timestamp: {datetime.utcnow().isoformat()}Z")
print()

# Initialize checker
mock_db = MagicMock()
checker = PriceScraperCheck(mock_db)

# Display test configuration
print("📋 TEST CONFIGURATION:")
print(f"   Endpoint: {checker.SPOT_ADVISOR_URL}")
print(f"   Timeout: {checker.TIMEOUT_SECONDS} seconds")
print(f"   Validation: Deep structure check (r & s keys)")
print()

# Run health check
print("🔄 RUNNING HEALTH CHECK...")
print()
status, details = checker.check()

# Display results
print("=" * 80)
print("📊 HEALTH CHECK RESULTS")
print("=" * 80)
print()

if status == "healthy":
    print("✅ STATUS: HEALTHY")
    print()
    print("🎯 ENDPOINT IS FULLY OPERATIONAL")
    print()
    
    print("Response Metrics:")
    print(f"  • HTTP Status Code: {details.get('http_status')}")
    print(f"  • Response Time: {details.get('response_time_ms')} ms")
    print()
    
    print("Data Structure Navigation:")
    print(f"  • Region Tested: {details.get('sample_region')}")
    print(f"  • OS Type: {details.get('sample_os')}")
    print(f"  • Instance Type: {details.get('sample_instance')}")
    print()
    
    print("Sample Data Extracted:")
    if 'sample_data' in details:
        sample_data = details['sample_data']
        print(f"  • Interruption Rate (r): {sample_data.get('interruption_rate')} (0-5 scale)")
        print(f"  • Savings Percentage (s): {sample_data.get('savings')}%")
    print()
    
    print("Validation Summary:")
    print("  ✓ AWS endpoint reachable")
    print("  ✓ Response structure valid")
    print("  ✓ 'r' key present (interruption rate)")
    print("  ✓ 's' key present (savings percentage)")
    print("  ✓ Data ready for scraper ingestion")
    print()
    
    print("📝 NEXT COMPONENT:")
    print("  The Price Scraper can now safely fetch and parse this data")
    print("  without risk of schema-related crashes.")

elif status == "degraded":
    print("⚠️  STATUS: DEGRADED")
    print()
    print("🚨 ENDPOINT REACHABLE BUT DATA STRUCTURE CHANGED")
    print()
    
    print("Issue Details:")
    print(f"  • Message: {details.get('message')}")
    if 'missing_keys' in details:
        print(f"  • Missing Keys: {details['missing_keys']}")
    if 'expected_keys' in details:
        print(f"  • Expected: {details['expected_keys']}")
    if 'actual_keys' in details:
        print(f"  • Found: {details['actual_keys']}")
    print()
    
    print("⚠️  ACTION REQUIRED:")
    print("  AWS may have changed their data format.")
    print("  Update the scraper logic to match new structure.")

else:  # critical
    print("❌ STATUS: CRITICAL")
    print()
    print("🔴 ENDPOINT UNREACHABLE")
    print()
    
    print("Error Details:")
    for key, value in details.items():
        if key != 'url':
            print(f"  • {key}: {value}")
    print()
    
    print("❌ ACTION REQUIRED:")
    print("  1. Check network connectivity")
    print("  2. Verify AWS endpoint is not down")
    print("  3. Check firewall/proxy settings")

print()
print("=" * 80)
print("Full Response (JSON):")
print(json.dumps(details, indent=2))
print("=" * 80)
