"""
AWS Agentless Executor

Implementation of Executor interface using AWS SDK (boto3).
No custom agent required on instances - all operations via AWS APIs.

This executor:
- Uses EC2 API for instance management
- Uses CloudWatch API for metrics
- Uses Spot Price History API for pricing
- Polls AWS for state transitions
"""

import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

from .base import (
    Executor,
    InstanceState,
    UsageMetrics,
    PoolInfo,
    PricingSnapshot,
    TargetSpec
)

logger = logging.getLogger(__name__)


class AWSAgentlessExecutor(Executor):
    """Agentless executor using AWS SDK"""

    def __init__(self, region: str, aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None):
        """
        Initialize AWS executor.

        Args:
            region: AWS region
            aws_access_key_id: Optional AWS key (uses default credentials if not provided)
            aws_secret_access_key: Optional AWS secret
        """
        self.region = region

        session_kwargs = {'region_name': region}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs['aws_access_key_id'] = aws_access_key_id
            session_kwargs['aws_secret_access_key'] = aws_secret_access_key

        self.ec2_client = boto3.client('ec2', **session_kwargs)
        self.cloudwatch_client = boto3.client('cloudwatch', **session_kwargs)

        logger.info(f"AWS Agentless Executor initialized for region {region}")

    def get_instance_state(self, instance_id: str) -> InstanceState:
        """Get instance state from EC2 API"""
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])

            if not response['Reservations']:
                raise ValueError(f"Instance {instance_id} not found")

            instance = response['Reservations'][0]['Instances'][0]

            # Extract tags
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}

            return InstanceState(
                instance_id=instance_id,
                instance_type=instance['InstanceType'],
                az=instance['Placement']['AvailabilityZone'],
                lifecycle=instance.get('InstanceLifecycle', 'on-demand'),
                state=instance['State']['Name'],
                subnet_id=instance.get('SubnetId', ''),
                vpc_id=instance.get('VpcId', ''),
                tags=tags
            )

        except ClientError as e:
            logger.error(f"Failed to get instance state: {e}")
            raise

    def get_usage_metrics(self, instance_id: str, window_minutes: int = 30) -> UsageMetrics:
        """Get CloudWatch metrics for instance"""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=window_minutes)

        metrics = UsageMetrics(cpu_p95=0.0, cpu_avg=0.0)

        try:
            # Get CPU metrics
            cpu_response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=['Average'],
                Unit='Percent'
            )

            if cpu_response['Datapoints']:
                cpu_values = [dp['Average'] for dp in cpu_response['Datapoints']]
                metrics.cpu_avg = sum(cpu_values) / len(cpu_values)
                metrics.cpu_p95 = sorted(cpu_values)[int(len(cpu_values) * 0.95)]

            # TODO: Add network metrics
            # TODO: Add memory metrics (if CloudWatch Agent is present)

            return metrics

            return metrics

        except ClientError as e:
            logger.error(f"Failed to get usage metrics: {e}")
            raise

    def get_instance_utilization(self, instance_id: str, region: str = None) -> Dict[str, float]:
        """
        Get detailed instance utilization for Lab Mode (replacing Pod metrics).
        
        Fetches CPU and Memory (if available) from CloudWatch.
        Time Window: 1 hour lookback.
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
        
        region = region or self.region
        
        try:
            # 1. Fetch CPU Utilization (Standard Metric)
            cpu_stats = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5-minute data points
                Statistics=['Average', 'Maximum'],
                Unit='Percent'
            )
            
            max_cpu = 0.0
            avg_cpu = 0.0
            
            if cpu_stats['Datapoints']:
                cpu_max_values = [dp['Maximum'] for dp in cpu_stats['Datapoints']]
                cpu_avg_values = [dp['Average'] for dp in cpu_stats['Datapoints']]
                
                max_cpu = max(cpu_max_values)
                avg_cpu = sum(cpu_avg_values) / len(cpu_avg_values)
            
            # 2. Fetch Memory Usage (Custom Metric from CloudWatch Agent)
            # Namespace: CWAgent, Metric: mem_used_percent
            mem_used = 0.0
            try:
                mem_stats = self.cloudwatch_client.get_metric_statistics(
                    Namespace='CWAgent',
                    MetricName='mem_used_percent',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=['Maximum'],
                    Unit='Percent'
                )
                if mem_stats['Datapoints']:
                    mem_used = max(dp['Maximum'] for dp in mem_stats['Datapoints'])
            except Exception as mem_e:
                logger.warning(f"Could not fetch memory metrics for {instance_id} (Agent missing?): {mem_e}")
                # Fallback note: User requirement example showed 60.0. 
                # Without an agent, we can't know. We'll return 0.0 to indicate missing data.
            
            return {
                "max_cpu": round(max_cpu, 2),
                "avg_cpu": round(avg_cpu, 2),
                "memory_used_percent": round(mem_used, 2)
            }
            
        except ClientError as e:
            logger.error(f"Failed to fetch CloudWatch metrics for {instance_id}: {e}")
            # Return empty/safe defaults on failure
            return {
                "max_cpu": 0.0, 
                "avg_cpu": 0.0, 
                "memory_used_percent": 0.0
            }

    def get_pricing_snapshot(
        self,
        instance_type: str,
        region: str,
        pools: Optional[List[str]] = None
    ) -> PricingSnapshot:
        """Get current spot pricing from AWS"""
        # TODO: Implement spot price fetching
        # This is a placeholder - full implementation would:
        # 1. Call DescribeSpotPriceHistory
        # 2. Get on-demand price from pricing API or cache
        # 3. Calculate discounts
        # 4. Return PricingSnapshot

        raise NotImplementedError("Pricing snapshot not yet implemented")

    def launch_instance(self, target_spec: TargetSpec) -> str:
        """Launch new instance via EC2 API"""
        try:
            launch_args = {
                'InstanceType': target_spec.instance_type,
                'MinCount': 1,
                'MaxCount': 1,
                'SubnetId': target_spec.subnet_id,
            }

            # Optional: AMI or Launch Template
            if target_spec.launch_template_id:
                launch_args['LaunchTemplate'] = {
                    'LaunchTemplateId': target_spec.launch_template_id,
                    'Version': '$Latest'
                }
            elif target_spec.ami_id:
                launch_args['ImageId'] = target_spec.ami_id
            else:
                raise ValueError("TargetSpec must provide either launch_template_id or ami_id")

            # Spot vs On-Demand
            if target_spec.lifecycle == 'spot':
                launch_args['InstanceMarketOptions'] = {
                    'MarketType': 'spot',
                    'SpotOptions': {
                        'SpotInstanceType': 'one-time',
                        'InstanceInterruptionBehavior': 'terminate'
                    }
                }

            # Tags
            if target_spec.tags:
                tag_spec = [
                    {
                        'ResourceType': 'instance',
                        'Tags': [{'Key': k, 'Value': v} for k, v in target_spec.tags.items()]
                    }
                ]
                launch_args['TagSpecifications'] = tag_spec

            # Launch
            response = self.ec2_client.run_instances(**launch_args)
            instance_id = response['Instances'][0]['InstanceId']
            
            logger.info(f"Launched instance {instance_id} ({target_spec.instance_type}, {target_spec.lifecycle})")
            return instance_id

        except ClientError as e:
            logger.error(f"Failed to launch instance: {e}")
            raise

    def terminate_instance(self, instance_id: str) -> bool:
        """Terminate instance via EC2 API"""
        try:
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            logger.info(f"Initiated termination of instance {instance_id}")
            return True
        except ClientError as e:
            logger.error(f"Failed to terminate instance: {e}")
            return False

    def wait_for_instance_state(
        self,
        instance_id: str,
        target_state: str,
        timeout_seconds: int = 300
    ) -> bool:
        """Poll instance state until target reached or timeout"""
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                state = self.get_instance_state(instance_id)
                if state.state == target_state:
                    logger.info(f"Instance {instance_id} reached state {target_state}")
                    return True

            except Exception as e:
                logger.warning(f"Error checking instance state: {e}")

            time.sleep(5)

        logger.warning(f"Timeout waiting for instance {instance_id} to reach {target_state}")
        return False
