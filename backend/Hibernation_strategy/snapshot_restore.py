"""Snapshot Restore Strategy - EBS snapshots before full shutdown"""
import boto3
import logging
from typing import Dict, Any
import time

logger = logging.getLogger(__name__)

class SnapshotRestoreConfig:
    SNAPSHOT_TIMEOUT = 1800
    KEEP_SNAPSHOTS_DAYS = 7
    PARALLEL_SNAPSHOTS = 5

class SnapshotRestoreStrategy:
    def __init__(self, cluster_config: Dict[str, Any]):
        self.cluster_config = cluster_config
        self.config = SnapshotRestoreConfig()
        self.ec2_client = boto3.client('ec2')
    
    def sleep(self, saved_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create snapshots then shutdown"""
        logger.info("Starting Snapshot Restore strategy sleep")
        state = saved_state or {"snapshots": {}, "volumes": {}}
        
        # Get all EBS volumes for cluster
        volumes = self._get_cluster_volumes()
        
        # Create snapshots
        for volume_id in volumes:
            volume = self.ec2_client.describe_volumes(VolumeIds=[volume_id])['Volumes'][0]
            az = volume['AvailabilityZone']
            
            snapshot = self.ec2_client.create_snapshot(
                VolumeId=volume_id,
                Description=f"Hibernation snapshot for {volume_id}"
            )
            
            state["snapshots"][volume_id] = snapshot['SnapshotId']
            state["volumes"][volume_id] = {"az": az, "size": volume['Size']}
            
            logger.info(f"Created snapshot {snapshot['SnapshotId']} for {volume_id}")
        
        # Wait for snapshots to complete
        self._wait_for_snapshots(list(state["snapshots"].values()))
        
        # Now execute full shutdown (delegate to Nuclear strategy)
        from backend.hibernation_strategy.nuclear import NuclearStrategy
        nuclear = NuclearStrategy(self.cluster_config)
        nuclear_result = nuclear.sleep()
        state.update(nuclear_result["state"])
        
        return {"state": state, "errors": []}
    
    def wake(self, saved_state: Dict[str, Any]) -> Dict[str, Any]:
        """Restore from snapshots and wake"""
        logger.info("Starting Snapshot Restore strategy wake")
        
        # First restore cluster (delegate to Nuclear strategy)
        from backend.hibernation_strategy.nuclear import NuclearStrategy
        nuclear = NuclearStrategy(self.cluster_config)
        nuclear.wake(saved_state)
        
        # Snapshots are kept for rollback, cleaned up later
        logger.info("Cluster restored from hibernation")
        
        return {"status": "success", "errors": []}
    
    def _get_cluster_volumes(self):
        """Get EBS volumes for this cluster"""
        cluster_name = self.cluster_config.get("cluster_name")
        response = self.ec2_client.describe_volumes(
            Filters=[
                {'Name': 'tag:kubernetes.io/cluster/' + cluster_name, 'Values': ['owned']}
            ]
        )
        return [v['VolumeId'] for v in response['Volumes']]
    
    def _wait_for_snapshots(self, snapshot_ids):
        """Wait for snapshots to complete"""
        logger.info(f"Waiting for {len(snapshot_ids)} snapshots to complete...")
        
        while True:
            response = self.ec2_client.describe_snapshots(SnapshotIds=snapshot_ids)
            
            all_completed = all(s['State'] == 'completed' for s in response['Snapshots'])
            if all_completed:
                logger.info("All snapshots completed")
                break
            
            time.sleep(10)
