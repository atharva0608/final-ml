"""Nuclear Strategy - Scale ASGs to 0, terminate worker nodes"""
import boto3
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class NuclearConfig:
    MIN_DESIRED_CAPACITY = 0
    SCALE_DOWN_TIMEOUT = 600
    TERMINATION_POLICIES = ["OldestInstance"]

class NuclearStrategy:
    def __init__(self, cluster_config: Dict[str, Any]):
        self.cluster_config = cluster_config
        self.config = NuclearConfig()
        self.asg_client = boto3.client('autoscaling')
        self.ec2_client = boto3.client('ec2')
    
    def sleep(self, saved_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """Scale ASGs to 0"""
        logger.info("Starting Nuclear strategy sleep")
        state = saved_state or {"asg_capacities": {}}
        
        # Get cluster ASGs
        asgs = self._get_cluster_asgs()
        
        for asg_name in asgs:
            asg = self.asg_client.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )['AutoScalingGroups'][0]
            
            # Save original capacities
            state["asg_capacities"][asg_name] = {
                "min": asg['MinSize'],
                "desired": asg['DesiredCapacity'],
                "max": asg['MaxSize']
            }
            
            # Scale to 0
            self.asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0,
                DesiredCapacity=0,
                MaxSize=0
            )
            logger.info(f"Scaled ASG {asg_name} to 0")
        
        return {"state": state, "errors": []}
    
    def wake(self, saved_state: Dict[str, Any]) -> Dict[str, Any]:
        """Restore ASG capacities"""
        logger.info("Starting Nuclear strategy wake")
        
        for asg_name, capacities in saved_state.get("asg_capacities", {}).items():
            self.asg_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=capacities["min"],
                DesiredCapacity=capacities["desired"],
                MaxSize=capacities["max"]
            )
            logger.info(f"Restored ASG {asg_name}")
        
        return {"status": "success", "errors": []}
    
    def _get_cluster_asgs(self):
        """Get ASGs for this cluster"""
        cluster_name = self.cluster_config.get("cluster_name")
        response = self.asg_client.describe_auto_scaling_groups()
        
        asgs = []
        for asg in response['AutoScalingGroups']:
            for tag in asg.get('Tags', []):
                if tag['Key'] == 'kubernetes.io/cluster/' + cluster_name:
                    asgs.append(asg['AutoScalingGroupName'])
                    break
        
        return asgs
