"""
Security Enforcer - Governance Cop

This enforcer prevents "Shadow IT" by ensuring every running instance is authorized:
1. The Audit: Scan all running EC2 instances in the account
2. The ID Check: Check tags for authorization (ManagedBy, ASG, EKS)
3. The Verdict: Flag unauthorized instances
4. The Enforcement: Terminate instances flagged for > 24 hours

The goal: Prevent unauthorized infrastructure from running.
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database.models import Instance, Account
from utils.aws_session import get_ec2_client


class SecurityEnforcer:
    """
    Security enforcer for rogue instance detection (The Governance Cop)

    This job scans all running EC2 instances and ensures they have proper
    authorization. Unauthorized instances are flagged and can be automatically
    terminated after a grace period.
    """

    GRACE_PERIOD_HOURS = 24  # 24 hours to fix authorization before termination

    def __init__(self, db: Session):
        """
        Initialize security enforcer

        Args:
            db: Database session
        """
        self.db = db

    def audit_account(self, account_id: str, region: str, auto_terminate: bool = False) -> Dict[str, Any]:
        """
        Audit an AWS account for unauthorized instances

        Args:
            account_id: Database account UUID
            region: AWS region to audit
            auto_terminate: If True, terminate instances past grace period

        Returns:
            Summary dict with counts of authorized/unauthorized instances
        """
        print(f"\n{'='*80}")
        print(f"🚨 SECURITY ENFORCER - Rogue Instance Detection")
        print(f"{'='*80}")

        # Get account from database
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account {account_id} not found")

        print(f"Account: {account.account_id}")
        print(f"Region: {region}")
        print(f"Auto-Terminate: {auto_terminate}")
        print(f"{'='*80}\n")

        # Get EC2 client
        ec2 = get_ec2_client(
            account_id=account.account_id,
            region=region,
            db=self.db
        )

        # Get all running instances
        response = ec2.describe_instances(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
        )

        authorized_count = 0
        unauthorized_count = 0
        flagged_count = 0
        terminated_count = 0

        for reservation in response['Reservations']:
            for inst in reservation['Instances']:
                instance_id = inst['InstanceId']
                tags = {tag['Key']: tag['Value'] for tag in inst.get('Tags', [])}

                # THE ID CHECK: Check authorization
                verdict = self._check_authorization(instance_id, tags)

                if verdict == 'AUTHORIZED':
                    authorized_count += 1
                    self._update_instance_status(instance_id, 'AUTHORIZED')
                elif verdict == 'UNAUTHORIZED':
                    unauthorized_count += 1
                    self._flag_unauthorized(instance_id, account, region, tags)

                    # THE ENFORCEMENT: Check if past grace period
                    if auto_terminate:
                        if self._should_terminate(instance_id):
                            print(f"   🛑 TERMINATING {instance_id} (past grace period)")
                            ec2.terminate_instances(InstanceIds=[instance_id])
                            self._update_instance_status(instance_id, 'TERMINATED')
                            terminated_count += 1
                        else:
                            flagged_count += 1

        print(f"\n{'='*80}")
        print(f"📊 SECURITY AUDIT COMPLETE")
        print(f"{'='*80}")
        print(f"✅ Authorized: {authorized_count}")
        print(f"⚠️  Unauthorized: {unauthorized_count}")
        print(f"🚩 Flagged (in grace period): {flagged_count}")
        print(f"🛑 Terminated: {terminated_count}")
        print(f"{'='*80}\n")

        return {
            "account_id": account_id,
            "region": region,
            "authorized": authorized_count,
            "unauthorized": unauthorized_count,
            "flagged": flagged_count,
            "terminated": terminated_count
        }

    def _check_authorization(self, instance_id: str, tags: Dict[str, str]) -> str:
        """
        Check if an instance is authorized (THE ID CHECK)

        An instance is authorized if it has ANY of these indicators:
        1. ManagedBy: SpotOptimizer tag
        2. aws:autoscaling:groupName tag (part of ASG)
        3. eks:cluster-name tag (part of EKS cluster)

        Args:
            instance_id: EC2 instance ID
            tags: Dict of instance tags

        Returns:
            'AUTHORIZED' or 'UNAUTHORIZED'
        """
        # Check 1: ManagedBy SpotOptimizer
        if tags.get('ManagedBy') == 'SpotOptimizer':
            return 'AUTHORIZED'

        # Check 2: Part of Auto Scaling Group
        if 'aws:autoscaling:groupName' in tags:
            return 'AUTHORIZED'

        # Check 3: Part of EKS cluster
        if 'eks:cluster-name' in tags or 'kubernetes.io/cluster' in tags.get('Name', ''):
            return 'AUTHORIZED'

        # No authorization found
        print(f"   ⚠️  UNAUTHORIZED: {instance_id} (no authorization tags)")
        return 'UNAUTHORIZED'

    def _flag_unauthorized(self, instance_id: str, account: Account, region: str, tags: Dict[str, str]):
        """
        Flag an unauthorized instance in the database

        Args:
            instance_id: EC2 instance ID
            account: Database account record
            region: AWS region
            tags: Instance tags
        """
        # Check if instance already tracked in database
        instance = self.db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()

        if instance:
            # Update existing record
            if instance.auth_status != 'FLAGGED':
                instance.auth_status = 'FLAGGED'
                instance.updated_at = datetime.utcnow()
                print(f"      Flagged in database (grace period: {self.GRACE_PERIOD_HOURS}h)")
        else:
            # Create new tracking record for unauthorized instance
            instance = Instance(
                account_id=account.id,
                instance_id=instance_id,
                instance_type=tags.get('InstanceType', 'unknown'),
                availability_zone=region + 'a',  # Default, actual AZ would come from describe_instances
                auth_status='FLAGGED',
                metadata={
                    'flagged_at': datetime.utcnow().isoformat(),
                    'reason': 'No authorization tags found',
                    'tags': tags
                }
            )
            self.db.add(instance)
            print(f"      Added to database as FLAGGED")

        self.db.commit()

    def _should_terminate(self, instance_id: str) -> bool:
        """
        Check if an unauthorized instance should be terminated

        An instance should be terminated if it has been flagged for longer
        than the grace period (24 hours by default).

        Args:
            instance_id: EC2 instance ID

        Returns:
            True if instance should be terminated
        """
        instance = self.db.query(Instance).filter(
            Instance.instance_id == instance_id,
            Instance.auth_status == 'FLAGGED'
        ).first()

        if not instance:
            return False

        # Check if past grace period
        flagged_at_str = instance.metadata.get('flagged_at')
        if not flagged_at_str:
            # If no flagged_at timestamp, flag it now and don't terminate yet
            instance.metadata['flagged_at'] = datetime.utcnow().isoformat()
            self.db.commit()
            return False

        flagged_at = datetime.fromisoformat(flagged_at_str)
        grace_period_end = flagged_at + timedelta(hours=self.GRACE_PERIOD_HOURS)

        return datetime.utcnow() > grace_period_end

    def _update_instance_status(self, instance_id: str, status: str):
        """
        Update instance authorization status

        Args:
            instance_id: EC2 instance ID
            status: New auth_status value
        """
        instance = self.db.query(Instance).filter(
            Instance.instance_id == instance_id
        ).first()

        if instance:
            instance.auth_status = status
            instance.updated_at = datetime.utcnow()
            self.db.commit()


# For testing
if __name__ == '__main__':
    print("="*80)
    print("SECURITY ENFORCER - Governance Cop")
    print("="*80)
    print("\nPrevents Shadow IT by ensuring all instances are authorized:")
    print("  1. The Audit: Scan all running EC2 instances")
    print("  2. The ID Check: Look for authorization tags:")
    print("     - ManagedBy: SpotOptimizer")
    print("     - aws:autoscaling:groupName (ASG membership)")
    print("     - eks:cluster-name (EKS membership)")
    print("  3. The Verdict: Flag unauthorized instances")
    print("  4. The Enforcement: Terminate after 24h grace period")
    print("\nGoal: Prevent unauthorized infrastructure")
    print("\nUsage:")
    print("  enforcer = SecurityEnforcer(db)")
    print("  results = enforcer.audit_account(account_id, region, auto_terminate=True)")
    print("="*80)
