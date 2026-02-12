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

        # Create AWS accounts for each team member
        print("📦 Creating AWS accounts for team members...")
        accounts_created = 0

        for idx, member in enumerate(members):
            # Check if member already has accounts
            existing_accounts = db.query(Account).filter(Account.user_id == member.id).count()
            if existing_accounts > 0:
                print(f"  ℹ️  {member.email} already has {existing_accounts} account(s)")
                continue

            # Create 1-2 AWS accounts per member
            num_accounts = random.randint(1, 2)
            for acc_idx in range(num_accounts):
                account = Account(
                    id=str(uuid.uuid4()),
                    organization_id=org.id,
                    user_id=member.id,
                    aws_account_id=f"12345678{idx}{acc_idx:02d}",
                    role_arn=f"arn:aws:iam::12345678{idx}{acc_idx:02d}:role/SpotOptimizer",
                    external_id=str(uuid.uuid4()),
                    region="us-east-1",
                    status=AccountStatus.ACTIVE,
                    sync_status=SyncStatus.HEALTHY,
                    last_sync_at=datetime.utcnow(),
                    is_default=(acc_idx == 0),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(account)
                accounts_created += 1

        db.commit()
        print(f"  ✅ Created {accounts_created} AWS accounts\n")

        # Create clusters for accounts
        print("🎯 Creating EKS clusters...")
        clusters_created = 0

        all_accounts = db.query(Account).filter(Account.organization_id == org.id).all()
        cluster_names = ["prod-cluster", "dev-cluster", "staging-cluster", "ml-cluster"]

        for account in all_accounts:
            # Create 1-3 clusters per account
            num_clusters = random.randint(1, 3)
            for cluster_idx in range(num_clusters):
                cluster_name = f"{cluster_names[cluster_idx % len(cluster_names)]}-{account.aws_account_id[-4:]}"

                cluster = Cluster(
                    id=str(uuid.uuid4()),
                    name=cluster_name,
                    account_id=account.id,
                    arn=f"arn:aws:eks:{account.region}:{account.aws_account_id}:cluster/{cluster_name}",
                    region=account.region,
                    cluster_type=ClusterType.EKS,
                    version="1.28",
                    endpoint=f"https://{uuid.uuid4().hex}.eks.{account.region}.amazonaws.com",
                    status=ClusterStatus.ACTIVE,
                    agent_installed="Y",
                    is_agentless="N",
                    last_heartbeat=datetime.utcnow(),
                    monthly_cost=0,  # Will be calculated from instances
                    estimated_savings=0,
                    node_count=0,  # Will be calculated from instances
                    spot_count=0,
                    cpu_usage_pct=random.uniform(30, 80),
                    mem_usage_pct=random.uniform(40, 85),
                    created_at=datetime.utcnow() - timedelta(days=random.randint(30, 180)),
                    updated_at=datetime.utcnow()
                )
                db.add(cluster)
                clusters_created += 1

        db.commit()
        print(f"  ✅ Created {clusters_created} clusters\n")

        # Create instances for clusters
        print("💻 Creating EC2 instances...")
        instances_created = 0

        instance_types = [
            ("t3.medium", 0.0416, "x86_64"),
            ("t3.large", 0.0832, "x86_64"),
            ("m5.large", 0.096, "x86_64"),
            ("m5.xlarge", 0.192, "x86_64"),
            ("c5.large", 0.085, "x86_64"),
            ("c5.xlarge", 0.17, "x86_64"),
            ("r5.large", 0.126, "x86_64"),
            ("t4g.medium", 0.0336, "arm64"),
            ("m6g.large", 0.077, "arm64"),
        ]

        all_clusters = db.query(Cluster).all()
        azs = ["us-east-1a", "us-east-1b", "us-east-1c"]
        states = ["running"] * 8 + ["stopped"] * 1 + ["pending"] * 1  # Mostly running

        for cluster in all_clusters:
            # Create 3-10 instances per cluster
            num_instances = random.randint(3, 10)

            for inst_idx in range(num_instances):
                inst_type, on_demand_price, arch = random.choice(instance_types)

                # 70% spot, 30% on-demand
                is_spot = random.random() < 0.7
                lifecycle = InstanceLifecycle.SPOT if is_spot else InstanceLifecycle.ON_DEMAND

                # Spot instances are ~70% cheaper
                price = on_demand_price * 0.3 if is_spot else on_demand_price

                state = random.choice(states)

                instance = Instance(
                    id=str(uuid.uuid4()),
                    cluster_id=cluster.id,
                    instance_id=f"i-{uuid.uuid4().hex[:17]}",
                    instance_type=inst_type,
                    lifecycle=lifecycle,
                    az=random.choice(azs),
                    price=price,
                    cpu_util=random.uniform(10, 90) if state == "running" else 0,
                    memory_util=random.uniform(20, 85) if state == "running" else 0,
                    state=state,
                    architecture=arch,
                    created_at=datetime.utcnow() - timedelta(days=random.randint(1, 60)),
                    updated_at=datetime.utcnow(),
                    last_heartbeat=datetime.utcnow() if state == "running" else None
                )
                db.add(instance)
                instances_created += 1

        db.commit()
        print(f"  ✅ Created {instances_created} instances\n")

        # Update cluster costs and node counts
        print("💰 Calculating cluster costs...")

        for cluster in all_clusters:
            instances = db.query(Instance).filter(Instance.cluster_id == cluster.id).all()

            total_cost = 0.0
            node_count = 0
            spot_count = 0

            for instance in instances:
                if instance.state in ['running', 'pending']:
                    # Calculate monthly cost (hours in month = 720)
                    monthly_cost = (instance.price or 0.0) * 720
                    total_cost += monthly_cost
                    node_count += 1

                    if instance.lifecycle == InstanceLifecycle.SPOT:
                        spot_count += 1

            # Calculate potential savings (if we converted all on-demand to spot)
            on_demand_count = node_count - spot_count
            avg_on_demand_cost = total_cost / node_count if node_count > 0 else 0
            potential_savings = on_demand_count * avg_on_demand_cost * 0.7  # 70% savings

            cluster.monthly_cost = int(total_cost)
            cluster.estimated_savings = int(potential_savings)
            cluster.node_count = node_count
            cluster.spot_count = spot_count
            cluster.last_cost_update = datetime.utcnow()

        db.commit()
        print(f"  ✅ Updated cluster costs\n")

        # Summary
        print("=" * 60)
        print("🎉 Test Data Seeding Complete!")
        print("=" * 60)
        print(f"\n📊 Summary:")
        print(f"  • Organization: {org.name}")
        print(f"  • Team: {team.name}")
        print(f"  • Members: {len(members)}")
        print(f"  • AWS Accounts: {accounts_created}")
        print(f"  • Clusters: {clusters_created}")
        print(f"  • Instances: {instances_created}")

        # Calculate total costs
        total_monthly_cost = sum(c.monthly_cost or 0 for c in all_clusters)
        total_savings = sum(c.estimated_savings or 0 for c in all_clusters)

        print(f"\n💰 Financial Summary:")
        print(f"  • Total Monthly Cost: ${total_monthly_cost:,.2f}")
        print(f"  • Potential Savings: ${total_savings:,.2f}")
        print(f"  • Efficiency: {((total_savings / total_monthly_cost) * 100) if total_monthly_cost > 0 else 0:.1f}%")

        print("\n" + "=" * 60)
        print("✅ Dashboards should now display real data!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error seeding test data: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_test_data()
