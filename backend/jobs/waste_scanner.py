"""
Waste Scanner - Financial Hygiene Job

This scanner finds and tracks unused AWS resources that are costing money:
1. Elastic IPs: Allocated but not attached to any instance
2. EBS Volumes: Unattached volumes older than 7 days
3. Snapshots: Snapshots older than 30 days not linked to any active AMI
4. AMIs: Old unused AMIs

The goal: Eliminate silent financial leaks.
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database.models import WasteResource, Account
from utils.aws_session import get_ec2_client


class WasteScanner:
    """
    Scanner for unused AWS resources (The Financial Janitor)

    This job should be run daily to identify resources that are costing
    money but providing no value. It logs findings to the WasteResource
    table for review and cleanup.
    """

    def __init__(self, db: Session):
        """
        Initialize waste scanner

        Args:
            db: Database session
        """
        self.db = db

    def scan_account(self, account_id: str, region: str) -> Dict[str, Any]:
        """
        Scan an AWS account for waste

        Args:
            account_id: Database account UUID
            region: AWS region to scan

        Returns:
            Summary dict with counts of waste found
        """
        print(f"\n{'='*80}")
        print(f"🧹 WASTE SCANNER - Financial Hygiene Audit")
        print(f"{'='*80}")

        # Get account from database
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account {account_id} not found")

        print(f"Account: {account.account_id}")
        print(f"Region: {region}")
        print(f"{'='*80}\n")

        # Get EC2 client
        ec2 = get_ec2_client(
            account_id=account.account_id,
            region=region,
            db=self.db
        )

        # Scan different resource types
        results = {
            "elastic_ips": self._scan_elastic_ips(ec2, account, region),
            "ebs_volumes": self._scan_ebs_volumes(ec2, account, region),
            "ebs_snapshots": self._scan_ebs_snapshots(ec2, account, region),
        }

        total_waste = sum(r["count"] for r in results.values())
        total_cost = sum(r["monthly_cost"] for r in results.values())

        print(f"\n{'='*80}")
        print(f"📊 WASTE SCAN COMPLETE")
        print(f"{'='*80}")
        print(f"Elastic IPs: {results['elastic_ips']['count']} (${results['elastic_ips']['monthly_cost']:.2f}/mo)")
        print(f"EBS Volumes: {results['ebs_volumes']['count']} (${results['ebs_volumes']['monthly_cost']:.2f}/mo)")
        print(f"EBS Snapshots: {results['ebs_snapshots']['count']} (${results['ebs_snapshots']['monthly_cost']:.2f}/mo)")
        print(f"---")
        print(f"TOTAL: {total_waste} resources (${total_cost:.2f}/mo)")
        print(f"{'='*80}\n")

        return {
            "account_id": account_id,
            "region": region,
            "total_waste": total_waste,
            "total_monthly_cost": total_cost,
            "details": results
        }

    def _scan_elastic_ips(self, ec2_client, account: Account, region: str) -> Dict[str, Any]:
        """
        Scan for unattached Elastic IPs

        Elastic IPs are free when attached but cost $0.005/hour (~$3.60/month)
        when unattached. This is a common source of waste.

        Args:
            ec2_client: Boto3 EC2 client
            account: Database account record
            region: AWS region

        Returns:
            Dict with count and monthly cost
        """
        print("🔍 Scanning Elastic IPs...")

        try:
            response = ec2_client.describe_addresses()
            addresses = response.get('Addresses', [])

            waste_count = 0
            for addr in addresses:
                # Check if EIP has no association (not attached to instance)
                if 'AssociationId' not in addr:
                    allocation_id = addr.get('AllocationId')
                    public_ip = addr.get('PublicIp')

                    # Log to database
                    waste = WasteResource(
                        account_id=account.id,
                        resource_type='elastic_ip',
                        resource_id=allocation_id or public_ip,
                        region=region,
                        monthly_cost=3.60,  # ~$0.005/hour
                        status='DETECTED',
                        reason='Elastic IP is allocated but not attached to any instance',
                        metadata={
                            'public_ip': public_ip,
                            'allocation_id': allocation_id
                        }
                    )

                    # Check if already exists
                    existing = self.db.query(WasteResource).filter(
                        WasteResource.resource_id == waste.resource_id
                    ).first()

                    if not existing:
                        self.db.add(waste)
                        waste_count += 1
                        print(f"   ⚠️  Unattached EIP: {public_ip}")

            self.db.commit()

            print(f"   Found {waste_count} unattached Elastic IPs")
            return {
                "count": waste_count,
                "monthly_cost": waste_count * 3.60
            }

        except Exception as e:
            print(f"   ❌ Error scanning Elastic IPs: {e}")
            return {"count": 0, "monthly_cost": 0.0}

    def _scan_ebs_volumes(self, ec2_client, account: Account, region: str) -> Dict[str, Any]:
        """
        Scan for unattached EBS volumes

        EBS volumes continue to cost money even when not attached to any
        instance. Volumes unattached for > 7 days are likely orphaned.

        Args:
            ec2_client: Boto3 EC2 client
            account: Database account record
            region: AWS region

        Returns:
            Dict with count and monthly cost
        """
        print("🔍 Scanning EBS Volumes...")

        try:
            response = ec2_client.describe_volumes(
                Filters=[{'Name': 'status', 'Values': ['available']}]
            )
            volumes = response.get('Volumes', [])

            waste_count = 0
            total_cost = 0.0

            cutoff_date = datetime.utcnow() - timedelta(days=7)

            for vol in volumes:
                volume_id = vol['VolumeId']
                size_gb = vol['Size']
                volume_type = vol['VolumeType']
                create_time = vol['CreateTime']

                # Convert create_time to offset-naive datetime
                if create_time.tzinfo is not None:
                    create_time = create_time.replace(tzinfo=None)

                # Only flag volumes older than 7 days
                if create_time < cutoff_date:
                    # Cost estimate: gp3 is ~$0.08/GB-month
                    monthly_cost = size_gb * 0.08

                    waste = WasteResource(
                        account_id=account.id,
                        resource_type='ebs_volume',
                        resource_id=volume_id,
                        region=region,
                        monthly_cost=monthly_cost,
                        days_unused=(datetime.utcnow() - create_time).days,
                        status='DETECTED',
                        reason=f'EBS volume has been unattached for {(datetime.utcnow() - create_time).days} days',
                        metadata={
                            'size_gb': size_gb,
                            'volume_type': volume_type,
                            'create_time': create_time.isoformat()
                        }
                    )

                    # Check if already exists
                    existing = self.db.query(WasteResource).filter(
                        WasteResource.resource_id == volume_id
                    ).first()

                    if not existing:
                        self.db.add(waste)
                        waste_count += 1
                        total_cost += monthly_cost
                        print(f"   ⚠️  Unattached volume: {volume_id} ({size_gb}GB, ${monthly_cost:.2f}/mo)")

            self.db.commit()

            print(f"   Found {waste_count} unattached EBS volumes")
            return {
                "count": waste_count,
                "monthly_cost": total_cost
            }

        except Exception as e:
            print(f"   ❌ Error scanning EBS volumes: {e}")
            return {"count": 0, "monthly_cost": 0.0}

    def _scan_ebs_snapshots(self, ec2_client, account: Account, region: str) -> Dict[str, Any]:
        """
        Scan for old, unused EBS snapshots

        Snapshots older than 30 days that aren't linked to any active AMI
        are candidates for cleanup.

        Args:
            ec2_client: Boto3 EC2 client
            account: Database account record
            region: AWS region

        Returns:
            Dict with count and monthly cost
        """
        print("🔍 Scanning EBS Snapshots...")

        try:
            # Get all snapshots owned by this account
            response = ec2_client.describe_snapshots(OwnerIds=['self'])
            snapshots = response.get('Snapshots', [])

            # Get all AMIs to check which snapshots are in use
            amis_response = ec2_client.describe_images(Owners=['self'])
            amis = amis_response.get('Images', [])

            # Build set of snapshot IDs used by AMIs
            snapshot_ids_in_use = set()
            for ami in amis:
                for bdm in ami.get('BlockDeviceMappings', []):
                    if 'Ebs' in bdm:
                        snapshot_ids_in_use.add(bdm['Ebs'].get('SnapshotId'))

            waste_count = 0
            total_cost = 0.0

            cutoff_date = datetime.utcnow() - timedelta(days=30)

            for snap in snapshots:
                snapshot_id = snap['SnapshotId']
                start_time = snap['StartTime']
                size_gb = snap['VolumeSize']

                # Convert start_time to offset-naive datetime
                if start_time.tzinfo is not None:
                    start_time = start_time.replace(tzinfo=None)

                # Check if snapshot is old and not used by any AMI
                if start_time < cutoff_date and snapshot_id not in snapshot_ids_in_use:
                    # Cost estimate: snapshots are ~$0.05/GB-month
                    monthly_cost = size_gb * 0.05

                    waste = WasteResource(
                        account_id=account.id,
                        resource_type='ebs_snapshot',
                        resource_id=snapshot_id,
                        region=region,
                        monthly_cost=monthly_cost,
                        days_unused=(datetime.utcnow() - start_time).days,
                        status='DETECTED',
                        reason=f'Snapshot is {(datetime.utcnow() - start_time).days} days old and not linked to any AMI',
                        metadata={
                            'size_gb': size_gb,
                            'start_time': start_time.isoformat()
                        }
                    )

                    # Check if already exists
                    existing = self.db.query(WasteResource).filter(
                        WasteResource.resource_id == snapshot_id
                    ).first()

                    if not existing:
                        self.db.add(waste)
                        waste_count += 1
                        total_cost += monthly_cost
                        print(f"   ⚠️  Old snapshot: {snapshot_id} ({size_gb}GB, ${monthly_cost:.2f}/mo)")

            self.db.commit()

            print(f"   Found {waste_count} old unused snapshots")
            return {
                "count": waste_count,
                "monthly_cost": total_cost
            }

        except Exception as e:
            print(f"   ❌ Error scanning snapshots: {e}")
            return {"count": 0, "monthly_cost": 0.0}


# For testing
if __name__ == '__main__':
    print("="*80)
    print("WASTE SCANNER - Financial Hygiene Job")
    print("="*80)
    print("\nScans for unused AWS resources that are costing money:")
    print("  1. Elastic IPs: Allocated but not attached ($3.60/month each)")
    print("  2. EBS Volumes: Unattached for > 7 days (~$0.08/GB-month)")
    print("  3. EBS Snapshots: > 30 days old, not linked to AMI (~$0.05/GB-month)")
    print("\nGoal: Eliminate silent financial leaks")
    print("\nUsage:")
    print("  scanner = WasteScanner(db)")
    print("  results = scanner.scan_account(account_id, region)")
    print("="*80)
