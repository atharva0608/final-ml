"""
Nuclear Strategy (NUCLEAR)

Aggressive hibernation by directly scaling AWS Auto Scaling Groups to 0.
This shuts down ALL nodes including the control plane.

Characteristics:
- Wake Time: ~8 minutes
- Cost Savings: ~99%
- Safety: MEDIUM (hard shutdown, control plane goes down)
- Best For: Maximum cost reduction in non-critical environments

Configuration Parameters (editable):
- MIN_DESIRED_CAPACITY: Minimum capacity to restore on wake
- SCALE_DOWN_TIMEOUT: Timeout for ASG scale-down operations
- SCALE_UP_TIMEOUT: Timeout for ASG scale-up operations
- WAIT_FOR_NODES: Wait for nodes to be ready after scale-up
- NODE_READY_TIMEOUT: Maximum time to wait for nodes to be ready
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - Edit these parameters to change strategy behavior
# =============================================================================

# Minimum capacity to restore (ensures at least N nodes on wake)
MIN_DESIRED_CAPACITY = 1

# Scale-down timeout (seconds) - max time to wait for nodes to terminate
SCALE_DOWN_TIMEOUT = 600  # 10 minutes

# Scale-up timeout (seconds) - max time to wait for nodes to launch
SCALE_UP_TIMEOUT = 480  # 8 minutes

# Wait for nodes to be ready after scale-up
WAIT_FOR_NODES = True

# Node ready timeout (seconds)
NODE_READY_TIMEOUT = 300  # 5 minutes

# ASG scaling behavior
HONOR_COOLDOWN = False  # Bypass cooldown periods for immediate scaling

# Instance termination policy
TERMINATION_POLICIES = [
    'OldestInstance',        # Terminate oldest instances first
    'Default'                # AWS default policy as fallback
]

# =============================================================================
# NUCLEAR STRATEGY CLASS
# =============================================================================

class NuclearStrategy:
    """
    Nuclear Strategy Implementation

    This class encapsulates all logic for the NUCLEAR hibernation strategy.
    All configuration parameters are defined above and can be edited.
    """

    def __init__(self):
        self.min_desired_capacity = MIN_DESIRED_CAPACITY
        self.scale_down_timeout = SCALE_DOWN_TIMEOUT
        self.scale_up_timeout = SCALE_UP_TIMEOUT
        self.wait_for_nodes = WAIT_FOR_NODES
        self.node_ready_timeout = NODE_READY_TIMEOUT
        self.honor_cooldown = HONOR_COOLDOWN
        self.termination_policies = TERMINATION_POLICIES

    def execute_sleep(self, cluster, schedule, db: Session, aws_credentials: Dict) -> Dict[str, Any]:
        """
        Execute Nuclear Sleep (scale ASGs to 0)

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            aws_credentials: Dict with 'access_key', 'secret_key', 'session_token'

        Returns:
            Dict with sleep results including ASGs affected and original capacities
        """
        logger.info(f"[NUCLEAR] Starting Nuclear sleep for cluster: {cluster.name}")

        # Create AWS AutoScaling client
        autoscaling = boto3.client(
            'autoscaling',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials.get('session_token'),
            region_name=cluster.region
        )

        # Get all ASGs for this cluster
        asgs = self._get_cluster_asgs(autoscaling, cluster)

        if not asgs:
            logger.warning(f"[NUCLEAR] No ASGs found for cluster {cluster.name}")
            return {
                'status': 'error',
                'message': 'No ASGs found for cluster',
                'timestamp': datetime.utcnow().isoformat()
            }

        # Save current ASG capacities
        saved_state = {
            'timestamp': datetime.utcnow().isoformat(),
            'strategy': 'NUCLEAR',
            'asgs': {}
        }

        # Scale down each ASG to 0
        for asg in asgs:
            asg_name = asg['AutoScalingGroupName']
            original_min = asg['MinSize']
            original_max = asg['MaxSize']
            original_desired = asg['DesiredCapacity']

            # Save original capacities
            saved_state['asgs'][asg_name] = {
                'original_min_size': original_min,
                'original_max_size': original_max,
                'original_desired_capacity': original_desired,
                'availability_zones': asg.get('AvailabilityZones', []),
                'launch_template': asg.get('LaunchTemplate', {}),
                'tags': asg.get('Tags', [])
            }

            logger.info(f"[NUCLEAR] Scaling down ASG: {asg_name} (Desired: {original_desired} → 0)")

            try:
                # Scale to 0
                autoscaling.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=0,
                    MaxSize=0,
                    DesiredCapacity=0
                )
                logger.info(f"[NUCLEAR] ASG {asg_name} scaled to 0")

                # Wait for instances to terminate
                if self.scale_down_timeout > 0:
                    self._wait_for_asg_instances(autoscaling, asg_name, target_count=0, timeout=self.scale_down_timeout)

            except ClientError as e:
                logger.error(f"[NUCLEAR] Failed to scale down ASG {asg_name}: {e}")
                saved_state['asgs'][asg_name]['error'] = str(e)

        # Save state to schedule
        schedule.saved_state = saved_state
        schedule.last_action = 'SLEEP'
        schedule.last_action_at = datetime.utcnow()
        db.commit()

        result = {
            'status': 'success',
            'strategy': 'NUCLEAR',
            'asgs_affected': list(saved_state['asgs'].keys()),
            'total_asgs': len(saved_state['asgs']),
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"[NUCLEAR] Nuclear sleep completed - {len(saved_state['asgs'])} ASGs scaled to 0")
        return result

    def execute_wake(self, cluster, schedule, db: Session, aws_credentials: Dict) -> Dict[str, Any]:
        """
        Execute Nuclear Wake (restore ASGs to original capacity)

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            aws_credentials: Dict with 'access_key', 'secret_key', 'session_token'

        Returns:
            Dict with wake results including ASGs restored and final capacities
        """
        logger.info(f"[NUCLEAR] Starting Nuclear wake for cluster: {cluster.name}")

        # Create AWS AutoScaling client
        autoscaling = boto3.client(
            'autoscaling',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials.get('session_token'),
            region_name=cluster.region
        )

        saved_state = schedule.saved_state or {}
        asgs_state = saved_state.get('asgs', {})

        if not asgs_state:
            logger.warning(f"[NUCLEAR] No saved state found for cluster {cluster.name}")
            return {
                'status': 'error',
                'message': 'No saved state found',
                'timestamp': datetime.utcnow().isoformat()
            }

        asgs_restored = 0

        # Restore each ASG
        for asg_name, asg_state in asgs_state.items():
            original_min = asg_state['original_min_size']
            original_max = asg_state['original_max_size']
            original_desired = asg_state['original_desired_capacity']

            # Ensure at least MIN_DESIRED_CAPACITY nodes
            desired_capacity = max(original_desired, self.min_desired_capacity)

            logger.info(f"[NUCLEAR] Restoring ASG: {asg_name} (0 → Desired: {desired_capacity})")

            try:
                # Restore ASG capacity
                autoscaling.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=original_min,
                    MaxSize=original_max,
                    DesiredCapacity=desired_capacity
                )
                logger.info(f"[NUCLEAR] ASG {asg_name} restored (Desired: {desired_capacity})")

                # Wait for instances to launch
                if self.scale_up_timeout > 0:
                    self._wait_for_asg_instances(
                        autoscaling,
                        asg_name,
                        target_count=desired_capacity,
                        timeout=self.scale_up_timeout
                    )

                asgs_restored += 1

            except ClientError as e:
                logger.error(f"[NUCLEAR] Failed to restore ASG {asg_name}: {e}")

        # Update schedule
        schedule.last_action = 'WAKE'
        schedule.last_action_at = datetime.utcnow()
        db.commit()

        result = {
            'status': 'success',
            'strategy': 'NUCLEAR',
            'asgs_restored': asgs_restored,
            'total_asgs': len(asgs_state),
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"[NUCLEAR] Nuclear wake completed - {asgs_restored} ASGs restored")
        return result

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_cluster_asgs(self, autoscaling, cluster) -> List[Dict]:
        """
        Get all Auto Scaling Groups associated with the cluster

        Args:
            autoscaling: boto3 AutoScaling client
            cluster: Cluster model instance

        Returns:
            List of ASG dictionaries
        """
        try:
            # Get ASGs with cluster tag
            paginator = autoscaling.get_paginator('describe_auto_scaling_groups')
            asgs = []

            for page in paginator.paginate():
                for asg in page['AutoScalingGroups']:
                    # Check if ASG belongs to this cluster
                    tags = {tag['Key']: tag['Value'] for tag in asg.get('Tags', [])}

                    # Match by cluster name or EKS cluster tag
                    if (tags.get('kubernetes.io/cluster/' + cluster.name) == 'owned' or
                        tags.get('eks:cluster-name') == cluster.name or
                        cluster.name in asg['AutoScalingGroupName']):
                        asgs.append(asg)
                        logger.debug(f"[NUCLEAR] Found ASG: {asg['AutoScalingGroupName']}")

            return asgs

        except ClientError as e:
            logger.error(f"[NUCLEAR] Failed to list ASGs: {e}")
            return []

    def _wait_for_asg_instances(self, autoscaling, asg_name: str, target_count: int, timeout: int) -> bool:
        """
        Wait for ASG to reach target instance count

        Args:
            autoscaling: boto3 AutoScaling client
            asg_name: ASG name
            target_count: Target number of instances
            timeout: Maximum wait time in seconds

        Returns:
            True if target reached, False if timeout
        """
        logger.info(f"[NUCLEAR] Waiting for ASG {asg_name} to reach {target_count} instances (timeout: {timeout}s)")

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = autoscaling.describe_auto_scaling_groups(
                    AutoScalingGroupNames=[asg_name]
                )

                if not response['AutoScalingGroups']:
                    logger.warning(f"[NUCLEAR] ASG {asg_name} not found")
                    return False

                asg = response['AutoScalingGroups'][0]
                current_count = len(asg.get('Instances', []))

                logger.debug(f"[NUCLEAR] ASG {asg_name}: {current_count}/{target_count} instances")

                if current_count == target_count:
                    logger.info(f"[NUCLEAR] ASG {asg_name} reached target: {target_count} instances")
                    return True

                time.sleep(10)  # Check every 10 seconds

            except ClientError as e:
                logger.error(f"[NUCLEAR] Error checking ASG {asg_name}: {e}")
                time.sleep(10)

        logger.warning(f"[NUCLEAR] Timeout waiting for ASG {asg_name} to reach {target_count} instances")
        return False


# =============================================================================
# STRATEGY RULES - Edit these to change behavior
# =============================================================================

STRATEGY_RULES = {
    'name': 'Nuclear',
    'code': 'NUCLEAR',
    'wake_time_minutes': 8,
    'cost_savings_percent': 99,
    'safety_level': 'MEDIUM',
    'best_for': 'Maximum cost reduction, non-critical environments',
    'description': 'Scales all ASGs to 0. Hard shutdown with control plane down.',

    # Editable rules
    'min_desired_capacity': MIN_DESIRED_CAPACITY,
    'scale_down_timeout': SCALE_DOWN_TIMEOUT,
    'scale_up_timeout': SCALE_UP_TIMEOUT,
    'wait_for_nodes': WAIT_FOR_NODES,
    'node_ready_timeout': NODE_READY_TIMEOUT,
    'honor_cooldown': HONOR_COOLDOWN,
    'termination_policies': TERMINATION_POLICIES,
}
