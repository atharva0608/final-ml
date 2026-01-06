#!/usr/bin/env python3
"""
Demo JWT Token Generator
Generates a valid JWT token for testing API endpoints without login.
"""
import sys
import os
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from backend.core.crypto import create_access_token
except ImportError as e:
    print(f"Error: Could not import backend modules. Detail: {e}")
    # print traceback for more details if needed
    import traceback
    traceback.print_exc()
    sys.exit(1)

def generate_demo_tokens():
    # Demo user data matches admin@spotoptimizer.com
    demo_user = {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "admin@spotoptimizer.com",
        "role": "super_admin",
        "company": "SpotOptimizer Demo"
    }
    
    access_token = create_access_token(data=demo_user, expires_delta=timedelta(hours=24))
    refresh_token = create_access_token(data={**demo_user, "type": "refresh"}, expires_delta=timedelta(days=7))
    
    print("\n=== DEMO JWT TOKENS ===\n")
    print(f"User: {demo_user['email']} ({demo_user['role']})\n")
    print(f"ACCESS_TOKEN:\n{access_token}\n")
    print(f"REFRESH_TOKEN:\n{refresh_token}\n")

if __name__ == "__main__":
    generate_demo_tokens()
