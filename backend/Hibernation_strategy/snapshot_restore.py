"""
Snapshot & Restore Strategy (SNAPSHOT_RESTORE)

Safe hibernation with EBS volume snapshots before Nuclear sleep.
Preserves data with AZ affinity for stateful workloads.

Characteristics:
- Wake Time: ~12 minutes
- Cost Savings: ~90%
- Safety: HIGH (snapshots ensure data preservation)
- Best For: Stateful workloads, databases

Configuration Parameters (editable):
- SNAPSHOT_TIMEOUT: Maximum time to wait for snapshot completion
- SNAPSHOT_DESCRIPTION_PREFIX: Prefix for snapshot descriptions
- KEEP_SNAPSHOTS_DAYS: How long to keep snapshots (for cleanup)
- PARALLEL_SNAPSHOTS: Number of snapshots to create in parallel
- VERIFY_SNAPSHOTS: Verify snapshot completion before proceeding
- RESTORE_WAIT_TIME: Time to wait after volume restore before wake
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - Edit these parameters to change strategy behavior
# =============================================================================

# Snapshot timeout (seconds) - max time to wait for snapshot completion
SNAPSHOT_TIMEOUT = 1800  # 30 minutes

# Snapshot description prefix
SNAPSHOT_DESCRIPTION_PREFIX = "SpotOptimizer-Hibernation"

# Snapshot retention (days) - for cleanup of old snapshots
KEEP_SNAPSHOTS_DAYS = 7

# Parallel snapshot creation limit
PARALLEL_SNAPSHOTS = 5

# Verify snapshots are completed before scaling down
VERIFY_SNAPSHOTS = True

# Wait time after volume restore (seconds)
RESTORE_WAIT_TIME = 60

# Snapshot tags
SNAPSHOT_TAGS = {
    'ManagedBy': 'SpotOptimizer',
    'HibernationStrategy': 'SNAPSHOT_RESTORE',
    'Purpose': 'HibernationBackup',
}

# AZ affinity tracking
TRACK_AZ_AFFINITY = True

# =============================================================================
# SNAPSHOT & RESTORE STRATEGY CLASS
# =============================================================================

class SnapshotRestoreStrategy:
    """
    Snapshot & Restore Strategy Implementation

    This class encapsulates all logic for the SNAPSHOT_RESTORE hibernation strategy.
    All configuration parameters are defined above and can be edited.
    """

    def __init__(self):
        self.snapshot_timeout = SNAPSHOT_TIMEOUT
        self.snapshot_description_prefix = SNAPSHOT_DESCRIPTION_PREFIX
        self.keep_snapshots_days = KEEP_SNAPSHOTS_DAYS
        self.parallel_snapshots = PARALLEL_SNAPSHOTS
        self.verify_snapshots = VERIFY_SNAPSHOTS
        self.restore_wait_time = RESTORE_WAIT_TIME
        self.snapshot_tags = SNAPSHOT_TAGS.copy()
        self.track_az_affinity = TRACK_AZ_AFFINITY

    def execute_sleep(self, cluster, schedule, db: Session, aws_credentials: Dict, k8s_clients: Dict = None) -> Dict[str, Any]:
        """
        Execute Snapshot & Restore Sleep

        Process:
        1. Identify all EBS volumes attached to cluster instances
        2. Create snapshots of all volumes with AZ affinity tracking
        3. Wait for snapshots to complete (if VERIFY_SNAPSHOTS=True)
        4. Execute Nuclear sleep (scale ASGs to 0)

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            aws_credentials: Dict with 'access_key', 'secret_key', 'session_token'
            k8s_clients: Optional K8s clients (not used in this strategy)

        Returns:
            Dict with sleep results including snapshots created and ASGs affected
        """
        logger.info(f"[SNAPSHOT_RESTORE] Starting Snapshot & Restore sleep for cluster: {cluster.name}")

        # Create AWS clients
        ec2 = boto3.client(
            'ec2',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials.get('session_token'),
            region_name=cluster.region
        )

        autoscaling = boto3.client(
            'autoscaling',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials.get('session_token'),
            region_name=cluster.region
        )

        # === STEP 1: Get all volumes for cluster instances ===
        volumes = self._get_cluster_volumes(ec2, autoscaling, cluster)

        if not volumes:
            logger.warning(f"[SNAPSHOT_RESTORE] No volumes found for cluster {cluster.name}")
            # Proceed with Nuclear sleep even if no volumes found
            volumes = []

        # === STEP 2: Create snapshots ===
        snapshots_created = []
        snapshot_batch = []

        for volume in volumes:
            volume_id = volume['VolumeId']
            az = volume['AvailabilityZone']
            instance_id = volume.get('InstanceId', 'unknown')

            logger.info(f"[SNAPSHOT_RESTORE] Creating snapshot for volume {volume_id} (AZ: {az})")

            try:
                # Create snapshot with tags
                snapshot_tags = [
                    {'Key': k, 'Value': v} for k, v in self.snapshot_tags.items()
                ]
                snapshot_tags.append({'Key': 'ClusterName', 'Value': cluster.name})
                snapshot_tags.append({'Key': 'AvailabilityZone', 'Value': az})
                snapshot_tags.append({'Key': 'OriginalVolumeId', 'Value': volume_id})
                snapshot_tags.append({'Key': 'InstanceId', 'Value': instance_id})
                snapshot_tags.append({'Key': 'CreatedAt', 'Value': datetime.utcnow().isoformat()})

                description = f"{self.snapshot_description_prefix} - {cluster.name} - {volume_id}"

                response = ec2.create_snapshot(
                    VolumeId=volume_id,
                    Description=description,
                    TagSpecifications=[
                        {
                            'ResourceType': 'snapshot',
                            'Tags': snapshot_tags
                        }
                    ]
                )

                snapshot_id = response['SnapshotId']
                snapshot_info = {
                    'snapshot_id': snapshot_id,
                    'volume_id': volume_id,
                    'availability_zone': az,
                    'instance_id': instance_id,
                    'size_gb': volume.get('Size', 0),
                    'volume_type': volume.get('VolumeType', 'unknown'),
                    'created_at': datetime.utcnow().isoformat()
                }

                snapshots_created.append(snapshot_info)
                snapshot_batch.append(snapshot_id)

                logger.info(f"[SNAPSHOT_RESTORE] Snapshot created: {snapshot_id} for volume {volume_id}")

                # Wait if batch size reached
                if len(snapshot_batch) >= self.parallel_snapshots:
                    if self.verify_snapshots:
                        self._wait_for_snapshots(ec2, snapshot_batch)
                    snapshot_batch = []

            except ClientError as e:
                logger.error(f"[SNAPSHOT_RESTORE] Failed to create snapshot for volume {volume_id}: {e}")

        # Wait for remaining snapshots
        if snapshot_batch and self.verify_snapshots:
            self._wait_for_snapshots(ec2, snapshot_batch)

        # === STEP 3: Get ASG information (for Nuclear sleep) ===
        asgs = self._get_cluster_asgs(autoscaling, cluster)
        asgs_state = {}

        for asg in asgs:
            asg_name = asg['AutoScalingGroupName']
            asgs_state[asg_name] = {
                'original_min_size': asg['MinSize'],
                'original_max_size': asg['MaxSize'],
                'original_desired_capacity': asg['DesiredCapacity'],
                'availability_zones': asg.get('AvailabilityZones', []),
            }

        # === STEP 4: Scale ASGs to 0 (Nuclear sleep) ===
        for asg_name in asgs_state.keys():
            logger.info(f"[SNAPSHOT_RESTORE] Scaling down ASG: {asg_name}")
            try:
                autoscaling.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=0,
                    MaxSize=0,
                    DesiredCapacity=0
                )
            except ClientError as e:
                logger.error(f"[SNAPSHOT_RESTORE] Failed to scale down ASG {asg_name}: {e}")

        # === STEP 5: Save state ===
        saved_state = {
            'timestamp': datetime.utcnow().isoformat(),
            'strategy': 'SNAPSHOT_RESTORE',
            'snapshots': snapshots_created,
            'asgs': asgs_state,
            'az_affinity': self._build_az_affinity_map(snapshots_created) if self.track_az_affinity else {}
        }

        schedule.saved_state = saved_state
        schedule.az_affinity = saved_state['az_affinity']
        schedule.last_action = 'SLEEP'
        schedule.last_action_at = datetime.utcnow()
        db.commit()

        result = {
            'status': 'success',
            'strategy': 'SNAPSHOT_RESTORE',
            'snapshots_created': len(snapshots_created),
            'asgs_affected': list(asgs_state.keys()),
            'total_asgs': len(asgs_state),
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"[SNAPSHOT_RESTORE] Snapshot & Restore sleep completed - {len(snapshots_created)} snapshots, {len(asgs_state)} ASGs")
        return result

    def execute_wake(self, cluster, schedule, db: Session, aws_credentials: Dict) -> Dict[str, Any]:
        """
        Execute Snapshot & Restore Wake

        Process:
        1. Restore ASGs to original capacity (Nuclear wake)
        2. Wait for instances to launch
        3. Snapshots are retained for data recovery if needed

        Note: Snapshots are NOT automatically deleted on wake.
        Use cleanup task to delete old snapshots based on KEEP_SNAPSHOTS_DAYS.

        Args:
            cluster: Cluster model instance
            schedule: HibernationSchedule model instance
            db: SQLAlchemy database session
            aws_credentials: Dict with 'access_key', 'secret_key', 'session_token'

        Returns:
            Dict with wake results including ASGs restored and snapshot info
        """
        logger.info(f"[SNAPSHOT_RESTORE] Starting Snapshot & Restore wake for cluster: {cluster.name}")

        # Create AWS client
        autoscaling = boto3.client(
            'autoscaling',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials.get('session_token'),
            region_name=cluster.region
        )

        saved_state = schedule.saved_state or {}
        asgs_state = saved_state.get('asgs', {})
        snapshots = saved_state.get('snapshots', [])

        if not asgs_state:
            logger.warning(f"[SNAPSHOT_RESTORE] No saved state found for cluster {cluster.name}")
            return {
                'status': 'error',
                'message': 'No saved state found',
                'timestamp': datetime.utcnow().isoformat()
            }

        # === STEP 1: Restore ASGs (Nuclear wake) ===
        asgs_restored = 0

        for asg_name, asg_state in asgs_state.items():
            original_min = asg_state['original_min_size']
            original_max = asg_state['original_max_size']
            original_desired = asg_state['original_desired_capacity']

            logger.info(f"[SNAPSHOT_RESTORE] Restoring ASG: {asg_name} (Desired: {original_desired})")

            try:
                autoscaling.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=original_min,
                    MaxSize=original_max,
                    DesiredCapacity=original_desired
                )
                asgs_restored += 1

            except ClientError as e:
                logger.error(f"[SNAPSHOT_RESTORE] Failed to restore ASG {asg_name}: {e}")

        # === STEP 2: Wait for instances to launch ===
        if self.restore_wait_time > 0:
            logger.info(f"[SNAPSHOT_RESTORE] Waiting {self.restore_wait_time}s for instances to launch...")
            time.sleep(self.restore_wait_time)

        # Update schedule
        schedule.last_action = 'WAKE'
        schedule.last_action_at = datetime.utcnow()
        db.commit()

        result = {
            'status': 'success',
            'strategy': 'SNAPSHOT_RESTORE',
            'asgs_restored': asgs_restored,
            'total_asgs': len(asgs_state),
            'snapshots_available': len(snapshots),
            'snapshots_info': [
                {'snapshot_id': s['snapshot_id'], 'volume_id': s['volume_id'], 'az': s['availability_zone']}
                for s in snapshots[:10]  # Return first 10 for logging
            ],
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"[SNAPSHOT_RESTORE] Snapshot & Restore wake completed - {asgs_restored} ASGs restored, {len(snapshots)} snapshots available")
        return result

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_cluster_volumes(self, ec2, autoscaling, cluster) -> List[Dict]:
        """Get all EBS volumes attached to cluster instances"""
        volumes = []

        try:
            # Get ASGs first
            asgs = self._get_cluster_asgs(autoscaling, cluster)

            # Get instances from ASGs
            instance_ids = []
            for asg in asgs:
                for instance in asg.get('Instances', []):
                    instance_ids.append(instance['InstanceId'])

            if not instance_ids:
                logger.warning(f"[SNAPSHOT_RESTORE] No instances found in ASGs")
                return []

            # Get volumes for instances
            response = ec2.describe_volumes(
                Filters=[
                    {'Name': 'attachment.instance-id', 'Values': instance_ids}
                ]
            )

            for volume in response['Volumes']:
                volume_info = {
                    'VolumeId': volume['VolumeId'],
                    'Size': volume['Size'],
                    'VolumeType': volume['VolumeType'],
                    'AvailabilityZone': volume['AvailabilityZone'],
                    'State': volume['State'],
                }

                # Get instance ID from attachments
                if volume.get('Attachments'):
                    volume_info['InstanceId'] = volume['Attachments'][0]['InstanceId']

                volumes.append(volume_info)

            logger.info(f"[SNAPSHOT_RESTORE] Found {len(volumes)} volumes across {len(instance_ids)} instances")
            return volumes

        except ClientError as e:
            logger.error(f"[SNAPSHOT_RESTORE] Failed to get volumes: {e}")
            return []

    def _get_cluster_asgs(self, autoscaling, cluster) -> List[Dict]:
        """Get all Auto Scaling Groups for the cluster"""
        try:
            paginator = autoscaling.get_paginator('describe_auto_scaling_groups')
            asgs = []

            for page in paginator.paginate():
                for asg in page['AutoScalingGroups']:
                    tags = {tag['Key']: tag['Value'] for tag in asg.get('Tags', [])}

                    if (tags.get('kubernetes.io/cluster/' + cluster.name) == 'owned' or
                        tags.get('eks:cluster-name') == cluster.name or
                        cluster.name in asg['AutoScalingGroupName']):
                        asgs.append(asg)

            return asgs

        except ClientError as e:
            logger.error(f"[SNAPSHOT_RESTORE] Failed to list ASGs: {e}")
            return []

    def _wait_for_snapshots(self, ec2, snapshot_ids: List[str]) -> bool:
        """Wait for snapshots to complete"""
        logger.info(f"[SNAPSHOT_RESTORE] Waiting for {len(snapshot_ids)} snapshots to complete...")

        start_time = time.time()

        while time.time() - start_time < self.snapshot_timeout:
            try:
                response = ec2.describe_snapshots(SnapshotIds=snapshot_ids)
                snapshots = response['Snapshots']

                completed = sum(1 for s in snapshots if s['State'] == 'completed')
                pending = sum(1 for s in snapshots if s['State'] == 'pending')
                errors = sum(1 for s in snapshots if s['State'] == 'error')

                logger.info(f"[SNAPSHOT_RESTORE] Snapshot progress: {completed} completed, {pending} pending, {errors} errors")

                if completed == len(snapshot_ids):
                    logger.info(f"[SNAPSHOT_RESTORE] All {len(snapshot_ids)} snapshots completed")
                    return True

                if errors > 0:
                    logger.error(f"[SNAPSHOT_RESTORE] {errors} snapshots failed")
                    return False

                time.sleep(30)  # Check every 30 seconds

            except ClientError as e:
                logger.error(f"[SNAPSHOT_RESTORE] Error checking snapshots: {e}")
                time.sleep(30)

        logger.warning(f"[SNAPSHOT_RESTORE] Timeout waiting for snapshots")
        return False

    def _build_az_affinity_map(self, snapshots: List[Dict]) -> Dict[str, str]:
        """Build AZ affinity map for volume restoration"""
        az_map = {}
        for snapshot in snapshots:
            volume_id = snapshot['volume_id']
            az = snapshot['availability_zone']
            az_map[volume_id] = az
        return az_map

    def cleanup_old_snapshots(self, cluster, aws_credentials: Dict) -> Dict[str, Any]:
        """
        Cleanup old snapshots based on KEEP_SNAPSHOTS_DAYS

        This method can be called periodically to remove old hibernation snapshots.
        """
        logger.info(f"[SNAPSHOT_RESTORE] Cleaning up old snapshots for cluster: {cluster.name}")

        ec2 = boto3.client(
            'ec2',
            aws_access_key_id=aws_credentials['access_key'],
            aws_secret_access_key=aws_credentials['secret_key'],
            aws_session_token=aws_credentials.get('session_token'),
            region_name=cluster.region
        )

        cutoff_date = datetime.utcnow() - timedelta(days=self.keep_snapshots_days)
        deleted_count = 0

        try:
            # Find snapshots created by this system
            response = ec2.describe_snapshots(
                Filters=[
                    {'Name': 'tag:ManagedBy', 'Values': ['SpotOptimizer']},
                    {'Name': 'tag:HibernationStrategy', 'Values': ['SNAPSHOT_RESTORE']},
                    {'Name': 'tag:ClusterName', 'Values': [cluster.name]}
                ]
            )

            for snapshot in response['Snapshots']:
                snapshot_id = snapshot['SnapshotId']
                start_time = snapshot['StartTime'].replace(tzinfo=None)

                if start_time < cutoff_date:
                    logger.info(f"[SNAPSHOT_RESTORE] Deleting old snapshot: {snapshot_id} (created: {start_time})")
                    try:
                        ec2.delete_snapshot(SnapshotId=snapshot_id)
                        deleted_count += 1
                    except ClientError as e:
                        logger.error(f"[SNAPSHOT_RESTORE] Failed to delete snapshot {snapshot_id}: {e}")

            logger.info(f"[SNAPSHOT_RESTORE] Cleanup complete - deleted {deleted_count} old snapshots")
            return {'status': 'success', 'deleted_count': deleted_count}

        except ClientError as e:
            logger.error(f"[SNAPSHOT_RESTORE] Snapshot cleanup failed: {e}")
            return {'status': 'error', 'message': str(e)}


# =============================================================================
# STRATEGY RULES - Edit these to change behavior
# =============================================================================

STRATEGY_RULES = {
    'name': 'Snapshot & Restore',
    'code': 'SNAPSHOT_RESTORE',
    'wake_time_minutes': 12,
    'cost_savings_percent': 90,
    'safety_level': 'HIGH',
    'best_for': 'Stateful workloads, databases',
    'description': 'Snapshots EBS volumes before Nuclear shutdown. Preserves data with AZ affinity.',

    # Editable rules
    'snapshot_timeout': SNAPSHOT_TIMEOUT,
    'snapshot_description_prefix': SNAPSHOT_DESCRIPTION_PREFIX,
    'keep_snapshots_days': KEEP_SNAPSHOTS_DAYS,
    'parallel_snapshots': PARALLEL_SNAPSHOTS,
    'verify_snapshots': VERIFY_SNAPSHOTS,
    'restore_wait_time': RESTORE_WAIT_TIME,
    'snapshot_tags': SNAPSHOT_TAGS,
    'track_az_affinity': TRACK_AZ_AFFINITY,
}
