#!/usr/bin/env python3
"""
Seed Test Data Script

Creates realistic test data with proper hierarchy:
Organization -> Users -> Teams -> Accounts -> Clusters -> Instances

This ensures dashboard visualizations have real data to display.
"""
import sys
import os
from datetime import datetime, timedelta
import uuid
import warnings
import random

warnings.filterwarnings('ignore', message='.*bcrypt.*')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.base import SessionLocal
from backend.models.user import User, UserRole
from backend.models.team import Team
from backend.models.organization import Organization
from backend.models.account import Account, AccountStatus, SyncStatus
from backend.models.cluster import Cluster, ClusterStatus, ClusterType
from backend.models.instance import Instance, InstanceLifecycle
from decimal import Decimal

def seed_test_data():
    """Create test data with proper hierarchy"""
    print("🌱 Seeding test data for dashboards...\n")

    db = SessionLocal()
    try:
        # Get the existing cloud team and its members
        team = db.query(Team).filter(Team.name == "cloud").first()
        if not team:
            print("❌ Team 'cloud' not found. Please ensure team exists first.")
            return

        print(f"✅ Found team: {team.name} (ID: {team.id})")

        # Get team members
        members = db.query(User).filter(User.team_id == team.id).all()
        if not members:
            print("❌ No team members found")
            return

        print(f"✅ Found {len(members)} team members")

        # Get organization
        org = db.query(Organization).filter(Organization.id == members[0].organization_id).first()
        if not org:
            print("❌ Organization not found")
            return

        print(f"✅ Found organization: {org.name}\n")

        # ---------------------------------------------------------
        # FAKE DATA GENERATION REMOVED AS PER USER REQUEST
        # We no longer seed mock AWS accounts, clusters, or instances.
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("✅ User seeding complete. Fake cluster/node data generation is DISABLED.")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_test_data()
