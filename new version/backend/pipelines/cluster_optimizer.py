"""
Cluster Optimizer - Production ASG Pipeline

This pipeline handles fleet-wide optimization across Auto Scaling Groups:
1. Discovery: Find all instances in target ASG
2. Filtration: Identify On-Demand instances that are InService
3. Global Risk Check: Query SpotPoolRisk table for poisoned pools
4. Execution: Scale-out swap (attach new Spot, then detach old On-Demand)
5. Audit logging and risk tracking

The key invariant: ASG capacity NEVER drops during optimization.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session

from database.models import Instance, Account, SpotPoolRisk, ExperimentLog
from utils.aws_session import get_ec2_client
from pipelines.linear_optimizer import execute_atomic_switch
from logic.risk_manager import RiskManager
from utils.system_logger import SystemLogger, Component

# Initialize logger for this module
logger = SystemLogger(Component.LINEAR_OPTIMIZER)



@dataclass
class ASGTarget:
    """On-Demand instance target for replacement"""
    instance_id: str
    instance_type: str
    availability_zone: str
    asg_name: str
    lifecycle_state: str  # InService, Pending, Terminating


class ClusterPipeline:
    """
    Cluster-wide optimization pipeline for Production ASGs

    This pipeline implements the Scale-Out Swap pattern:
    1. Launch new Spot instance
    2. Wait for health checks
    3. Attach to ASG (capacity goes from N to N+1)
    4. Detach old On-Demand (capacity goes back to N)
    5. Terminate old instance

    This ensures ASG capacity never drops during optimization.
    """

    def __init__(self, db: Session, config: Optional[Dict[str, Any]] = None):
        """
        Initialize cluster pipeline

        Args:
            db: Database session
            config: Optional configuration overrides
        """
        self.db = db
        self.config = config or {}
        self.risk_manager = RiskManager(db=db)

    def execute(self, asg_name: str, account_id: str, region: str, max_instances: int = 10) -> Dict[str, Any]:
        """
        Execute cluster-wide optimization for an ASG

        Args:
            asg_name: Auto Scaling Group name
            account_id: AWS account ID (database UUID)
            region: AWS region
            max_instances: Maximum instances to optimize in one run

        Returns:
            Execution summary with success/failure counts
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"🏭 CLUSTER OPTIMIZATION - ASG Mode")
        logger.info(f"{'='*80}")
        logger.info(f"ASG: {asg_name}")
        logger.info(f"Region: {region}")
        logger.info(f"Max Instances: {max_instances}")
        logger.info(f"{'='*80}\n")

        # Get account from database
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account {account_id} not found")

        # Get AWS clients
        ec2 = get_ec2_client(account_id=account.account_id, region=region, db=self.db)

        # Import boto3 for ASG client
        import boto3
        from utils.aws_session import assume_role_with_sts

        # Get ASG client
        credentials = assume_role_with_sts(
            account_id=account.account_id,
            role_arn=account.role_arn,
            external_id=account.external_id,
            session_name=f"ClusterOptimizer-{region}"
        )
        asg_client = boto3.client(
            'autoscaling',
            region_name=region,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

        # Step 1: Discovery - Find all instances in ASG
        targets = self._discover_targets(asg_client, asg_name, ec2)
        logger.info(f"📊 Discovered {len(targets)} On-Demand instances in ASG")

        if not targets:
            logger.info("✓ No On-Demand instances found. ASG is already optimized!")
            return {
                "status": "complete",
                "asg_name": asg_name,
                "targets_found": 0,
                "optimized": 0,
                "skipped": 0,
                "failed": 0
            }

        # Limit batch size
        targets = targets[:max_instances]
        logger.info(f"📋 Processing batch of {len(targets)} instances\n")

        # Step 2: Process each target
        results = {
            "optimized": [],
            "skipped": [],
            "failed": []
        }

        for target in targets:
            try:
                result = self._optimize_target(target, asg_client, ec2, account, region)
                if result["status"] == "success":
                    results["optimized"].append(target.instance_id)
                    logger.info(f"✅ {target.instance_id} optimized successfully\n")
                elif result["status"] == "skipped":
                    results["skipped"].append(target.instance_id)
                    logger.info(f"⏭️  {target.instance_id} skipped: {result['reason']}\n")
                else:
                    results["failed"].append(target.instance_id)
                    logger.error(f"❌ {target.instance_id} failed: {result['reason']}\n")
            except Exception as e:
                results["failed"].append(target.instance_id)
                logger.error(f"❌ {target.instance_id} failed with exception: {e}\n")

        logger.info(f"\n{'='*80}")
        logger.info(f"🏁 CLUSTER OPTIMIZATION COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Optimized: {len(results['optimized'])}")
        logger.info(f"Skipped: {len(results['skipped'])}")
        logger.info(f"Failed: {len(results['failed'])}")
        logger.info(f"{'='*80}\n")

        return {
            "status": "complete",
            "asg_name": asg_name,
            "targets_found": len(targets),
            "optimized": len(results["optimized"]),
            "skipped": len(results["skipped"]),
            "failed": len(results["failed"]),
            "details": results
        }

    def _discover_targets(self, asg_client, asg_name: str, ec2_client) -> List[ASGTarget]:
        """
        Discover On-Demand instances in ASG

        Args:
            asg_client: Boto3 ASG client
            asg_name: ASG name
            ec2_client: Boto3 EC2 client

        Returns:
            List of ASGTarget objects (On-Demand instances only)
        """
        # Get ASG details
        response = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )

        if not response['AutoScalingGroups']:
            return []

        asg = response['AutoScalingGroups'][0]
        instances = asg['Instances']

        # Filter for InService instances only
        targets = []
        for inst in instances:
            if inst['LifecycleState'] != 'InService':
                continue

            # Get instance details to check if it's On-Demand
            instance_id = inst['InstanceId']
            ec2_response = ec2_client.describe_instances(InstanceIds=[instance_id])

            if not ec2_response['Reservations']:
                continue

            instance_data = ec2_response['Reservations'][0]['Instances'][0]

            # Check if On-Demand (not Spot)
            if instance_data.get('InstanceLifecycle') == 'spot':
                continue  # Already a Spot instance, skip

            targets.append(ASGTarget(
                instance_id=instance_id,
                instance_type=instance_data['InstanceType'],
                availability_zone=instance_data['Placement']['AvailabilityZone'],
                asg_name=asg_name,
                lifecycle_state=inst['LifecycleState']
            ))

        return targets

    def _optimize_target(
        self,
        target: ASGTarget,
        asg_client,
        ec2_client,
        account: Account,
        region: str
    ) -> Dict[str, Any]:
        """
        Optimize a single target instance

        Args:
            target: ASGTarget to optimize
            asg_client: Boto3 ASG client
            ec2_client: Boto3 EC2 client
            account: Database account record
            region: AWS region

        Returns:
            Result dict with status and reason
        """
        logger.info(f"🔄 Processing {target.instance_id} ({target.instance_type} in {target.availability_zone})")

        # Step 1: Global Risk Check (THE GATEKEEPER)
        is_risky = self.risk_manager.is_pool_poisoned(
            region=region,
            availability_zone=target.availability_zone,
            instance_type=target.instance_type
        )

        if is_risky:
            return {
                "status": "skipped",
                "reason": f"Pool {target.instance_type}@{target.availability_zone} is flagged as risky (global contagion)"
            }

        # Step 2: Execute Atomic Switch (Launch new Spot)
        try:
            logger.info(f"  🚀 Launching replacement Spot instance...")
            switch_result = execute_atomic_switch(
                ec2_client=ec2_client,
                source_instance_id=target.instance_id,
                target_instance_type=target.instance_type,
                target_az=target.availability_zone,
                dry_run=False
            )

            new_instance_id = switch_result['new_instance_id']
            logger.info(f"  ✓ New instance {new_instance_id} launched and healthy")

        except Exception as e:
            return {
                "status": "failed",
                "reason": f"Atomic switch failed: {str(e)}"
            }

        # Step 3: Attach new instance to ASG (Scale Out: N -> N+1)
        try:
            logger.info(f"  🔗 Attaching {new_instance_id} to ASG...")
            asg_client.attach_instances(
                InstanceIds=[new_instance_id],
                AutoScalingGroupName=target.asg_name
            )

            # Wait for attachment to complete
            import time
            time.sleep(10)  # Give ASG time to register the instance

            logger.info(f"  ✓ Instance attached to ASG")

        except Exception as e:
            # Rollback: Terminate the new instance
            logger.warning(f"  ⚠️  Attachment failed, rolling back...")
            ec2_client.terminate_instances(InstanceIds=[new_instance_id])
            return {
                "status": "failed",
                "reason": f"ASG attachment failed: {str(e)}"
            }

        # Step 4: Detach and terminate old instance (Scale In: N+1 -> N)
        try:
            logger.info(f"  🔓 Detaching old instance {target.instance_id}...")
            asg_client.detach_instances(
                InstanceIds=[target.instance_id],
                AutoScalingGroupName=target.asg_name,
                ShouldDecrementDesiredCapacity=True  # Reduce desired count back to N
            )

            # Wait for detachment
            import time
            time.sleep(5)

            logger.info(f"  🛑 Terminating old instance...")
            ec2_client.terminate_instances(InstanceIds=[target.instance_id])

            logger.info(f"  ✓ Old instance detached and terminated")

        except Exception as e:
            # The new instance is now in the ASG, but we couldn't remove the old one
            # This leaves the ASG over-capacity temporarily
            logger.error(f"  ⚠️  Detachment/termination failed: {e}")
            logger.warning(f"  ℹ️  New instance is active, but old instance remains (manual cleanup needed)")
            return {
                "status": "partial",
                "reason": f"New instance active, but old cleanup failed: {str(e)}",
                "new_instance_id": new_instance_id
            }

        return {
            "status": "success",
            "old_instance_id": target.instance_id,
            "new_instance_id": new_instance_id
        }


# For testing
if __name__ == '__main__':
    print("="*80)
    print("CLUSTER OPTIMIZER - Production ASG Pipeline")
    print("="*80)
    print("\nImplements Scale-Out Swap pattern for Auto Scaling Groups:")
    print("  1. Discovery: Find On-Demand instances in ASG")
    print("  2. Risk Check: Query global contagion table")
    print("  3. Launch: Create replacement Spot instance")
    print("  4. Attach: Add to ASG (N → N+1)")
    print("  5. Detach: Remove old instance (N+1 → N)")
    print("  6. Terminate: Clean up old instance")
    print("\nCritical Invariant: ASG capacity NEVER drops during optimization")
    print("="*80)
