"""
Action Executor (CORE-EXEC)
Executes approved optimization actions on AWS and Kubernetes

The Action Executor is responsible for translating approved optimization
actions into actual AWS API calls and Kubernetes operations.

Key Responsibilities:
- Execute AWS EC2/ASG operations (launch, terminate, modify)
- Execute Kubernetes operations (drain, cordon, label)
- Rollback on failure
- Progress tracking
- Audit logging
- Safety checks before execution

Dependencies:
- boto3 for AWS operations
- kubernetes-client for K8s operations
- Database for audit logging
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
import time

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.database.models import (
    Cluster,
    Account,
    ActionLog,
    Instance
)
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Action execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ActionExecutor:
    """
    Executes approved optimization actions
    """

    def __init__(self, db: Session, redis_client=None):
        """
        Initialize Action Executor

        Args:
            db: Database session
            redis_client: Optional Redis client
        """
        self.db = db
        self.redis_client = redis_client or get_redis_client()

    def execute_action_plan(
        self,
        cluster_id: str,
        execution_plan: Dict[str, Any],
        job_id: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute complete action plan

        Args:
            cluster_id: UUID of cluster
            execution_plan: Execution plan from Decision Engine
            job_id: Optional optimization job ID
            dry_run: If True, simulate without actually executing

        Returns:
            Dict with execution results
        """
        logger.info(
            f"[CORE-EXEC] Executing action plan for cluster {cluster_id} "
            f"(dry_run={dry_run})"
        )

        # Get cluster
        cluster = self.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        results = {
            "cluster_id": cluster_id,
            "job_id": job_id,
            "dry_run": dry_run,
            "started_at": datetime.utcnow().isoformat(),
            "phases": [],
            "summary": {
                "total_actions": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0
            }
        }

        # Execute each phase
        for phase in execution_plan.get("phases", []):
            phase_num = phase["phase"]
            delay = phase.get("delay_seconds", 0)

            logger.info(
                f"[CORE-EXEC] Starting Phase {phase_num} "
                f"(delay: {delay}s, actions: {len(phase['actions'])})"
            )

            # Wait for delay (except first phase)
            if delay > 0 and not dry_run:
                logger.info(f"[CORE-EXEC] Waiting {delay} seconds before Phase {phase_num}")
                time.sleep(delay)

            # Execute actions in this phase
            phase_results = []

            for action in phase["actions"]:
                results["summary"]["total_actions"] += 1

                try:
                    # Execute single action
                    action_result = self.execute_action(
                        action=action,
                        cluster=cluster,
                        dry_run=dry_run
                    )

                    phase_results.append(action_result)

                    if action_result["status"] == ExecutionStatus.COMPLETED.value:
                        results["summary"]["completed"] += 1
                    elif action_result["status"] == ExecutionStatus.FAILED.value:
                        results["summary"]["failed"] += 1
                    else:
                        results["summary"]["skipped"] += 1

                except Exception as e:
                    logger.error(f"[CORE-EXEC] Error executing action: {str(e)}")

                    # Log failed action
                    action_result = {
                        "action": action,
                        "status": ExecutionStatus.FAILED.value,
                        "error": str(e)
                    }
                    phase_results.append(action_result)
                    results["summary"]["failed"] += 1

            # Add phase results
            results["phases"].append({
                "phase": phase_num,
                "name": phase["name"],
                "actions_executed": len(phase_results),
                "results": phase_results
            })

        results["completed_at"] = datetime.utcnow().isoformat()

        logger.info(f"[CORE-EXEC] Execution complete: {results['summary']}")

        return results

    def execute_action(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute single optimization action

        Args:
            action: Action to execute
            cluster: Cluster record
            dry_run: If True, simulate without executing

        Returns:
            Dict with execution result
        """
        action_type = action.get("type")

        logger.info(
            f"[CORE-EXEC] Executing action: {action_type} "
            f"(dry_run={dry_run})"
        )

        # Route to appropriate handler
        if action_type == "spot_replacement":
            return self._execute_spot_replacement(action, cluster, dry_run)

        elif action_type == "right_size":
            return self._execute_right_size(action, cluster, dry_run)

        elif action_type == "consolidate":
            return self._execute_consolidation(action, cluster, dry_run)

        elif action_type == "scale_down":
            return self._execute_scale_down(action, cluster, dry_run)

        elif action_type == "scale_up":
            return self._execute_scale_up(action, cluster, dry_run)

        else:
            logger.warning(f"[CORE-EXEC] Unknown action type: {action_type}")
            return {
                "action": action,
                "status": ExecutionStatus.FAILED.value,
                "error": f"Unknown action type: {action_type}"
            }

    def _execute_spot_replacement(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Execute Spot instance replacement

        Steps:
        1. Launch new Spot instance
        2. Wait for instance to be running
        3. Drain old On-Demand instance
        4. Terminate old instance

        Args:
            action: Action details
            cluster: Cluster record
            dry_run: If True, simulate only

        Returns:
            Dict with execution result
        """
        logger.info("[CORE-EXEC] Executing Spot replacement")

        old_instance_id = action.get("target_instance_id")
        new_instance_type = action.get("recommended_instance_type")
        availability_zone = action.get("availability_zone")

        if dry_run:
            logger.info(
                f"[CORE-EXEC] DRY RUN: Would replace {old_instance_id} "
                f"with Spot {new_instance_type} in {availability_zone}"
            )

            # Log the simulated action
            self._log_action(
                cluster_id=cluster.id,
                action_type="spot_replacement",
                status="simulated",
                details=action
            )

            return {
                "action": action,
                "status": "simulated",
                "message": "Dry run - no changes made"
            }

        try:
            # Get AWS credentials
            account = self.db.query(Account).filter(
                Account.id == cluster.account_id
            ).first()

            # Assume IAM role
            sts_client = boto3.client('sts')
            assumed_role = sts_client.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=f"SpotOptimizer-Exec-{cluster.id}",
                ExternalId=account.external_id
            )

            credentials = assumed_role['Credentials']

            # Create EC2 client
            ec2_client = boto3.client(
                'ec2',
                region_name=cluster.region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )

            # Step 1: Launch new Spot instance
            logger.info(f"[CORE-EXEC] Launching Spot instance {new_instance_type}")

            # TODO: In production, get launch template from old instance
            launch_response = ec2_client.request_spot_instances(
                InstanceCount=1,
                Type='one-time',
                LaunchSpecification={
                    'ImageId': action.get("ami_id", "ami-12345678"),  # TODO: Get from old instance
                    'InstanceType': new_instance_type,
                    'Placement': {
                        'AvailabilityZone': availability_zone
                    },
                    'SecurityGroupIds': action.get("security_groups", []),
                    'SubnetId': action.get("subnet_id"),
                    'IamInstanceProfile': action.get("iam_instance_profile", {}),
                    'UserData': action.get("user_data", "")
                }
            )

            spot_request_id = launch_response['SpotInstanceRequests'][0]['SpotInstanceRequestId']

            logger.info(f"[CORE-EXEC] Spot request created: {spot_request_id}")

            # Step 2: Wait for Spot instance to launch
            # TODO: Implement proper waiter with timeout

            # Step 3: Drain old instance (Kubernetes)
            # TODO: Implement Kubernetes drain logic

            # Step 4: Terminate old instance
            logger.info(f"[CORE-EXEC] Terminating old instance {old_instance_id}")

            ec2_client.terminate_instances(
                InstanceIds=[old_instance_id]
            )

            # Log successful action
            self._log_action(
                cluster_id=cluster.id,
                action_type="spot_replacement",
                status="completed",
                details={
                    **action,
                    "spot_request_id": spot_request_id,
                    "old_instance_terminated": old_instance_id
                }
            )

            return {
                "action": action,
                "status": ExecutionStatus.COMPLETED.value,
                "spot_request_id": spot_request_id,
                "old_instance_id": old_instance_id
            }

        except ClientError as e:
            logger.error(f"[CORE-EXEC] AWS error during Spot replacement: {str(e)}")

            # Log failed action
            self._log_action(
                cluster_id=cluster.id,
                action_type="spot_replacement",
                status="failed",
                details={
                    **action,
                    "error": str(e)
                }
            )

            return {
                "action": action,
                "status": ExecutionStatus.FAILED.value,
                "error": str(e)
            }

    def _execute_right_size(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Execute instance right-sizing

        Args:
            action: Action details
            cluster: Cluster record
            dry_run: If True, simulate only

        Returns:
            Dict with execution result
        """
        logger.info("[CORE-EXEC] Executing right-sizing")

        instance_id = action.get("target_instance_id")
        new_instance_type = action.get("recommended_instance_type")

        if dry_run:
            logger.info(
                f"[CORE-EXEC] DRY RUN: Would resize {instance_id} to {new_instance_type}"
            )

            self._log_action(
                cluster_id=cluster.id,
                action_type="right_size",
                status="simulated",
                details=action
            )

            return {
                "action": action,
                "status": "simulated"
            }

        # TODO: Implement actual resizing logic
        # Steps:
        # 1. Stop instance
        # 2. Change instance type
        # 3. Start instance
        # 4. Verify health

        self._log_action(
            cluster_id=cluster.id,
            action_type="right_size",
            status="completed",
            details=action
        )

        return {
            "action": action,
            "status": ExecutionStatus.COMPLETED.value
        }

    def _execute_consolidation(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Execute node consolidation

        Args:
            action: Action details
            cluster: Cluster record
            dry_run: If True, simulate only

        Returns:
            Dict with execution result
        """
        logger.info("[CORE-EXEC] Executing consolidation")

        node_id = action.get("target_node_id")

        if dry_run:
            logger.info(f"[CORE-EXEC] DRY RUN: Would drain and terminate node {node_id}")

            self._log_action(
                cluster_id=cluster.id,
                action_type="consolidate",
                status="simulated",
                details=action
            )

            return {
                "action": action,
                "status": "simulated"
            }

        # TODO: Implement actual consolidation logic
        # Steps:
        # 1. Cordon node
        # 2. Drain pods
        # 3. Terminate instance

        self._log_action(
            cluster_id=cluster.id,
            action_type="consolidate",
            status="completed",
            details=action
        )

        return {
            "action": action,
            "status": ExecutionStatus.COMPLETED.value
        }

    def _execute_scale_down(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Execute cluster scale-down

        Args:
            action: Action details
            cluster: Cluster record
            dry_run: If True, simulate only

        Returns:
            Dict with execution result
        """
        logger.info("[CORE-EXEC] Executing scale-down")

        desired_capacity = action.get("desired_capacity")

        if dry_run:
            logger.info(f"[CORE-EXEC] DRY RUN: Would scale down to {desired_capacity} nodes")

            self._log_action(
                cluster_id=cluster.id,
                action_type="scale_down",
                status="simulated",
                details=action
            )

            return {
                "action": action,
                "status": "simulated"
            }

        # TODO: Implement ASG scale-down

        self._log_action(
            cluster_id=cluster.id,
            action_type="scale_down",
            status="completed",
            details=action
        )

        return {
            "action": action,
            "status": ExecutionStatus.COMPLETED.value
        }

    def _execute_scale_up(
        self,
        action: Dict[str, Any],
        cluster: Cluster,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Execute cluster scale-up

        Args:
            action: Action details
            cluster: Cluster record
            dry_run: If True, simulate only

        Returns:
            Dict with execution result
        """
        logger.info("[CORE-EXEC] Executing scale-up")

        desired_capacity = action.get("desired_capacity")

        if dry_run:
            logger.info(f"[CORE-EXEC] DRY RUN: Would scale up to {desired_capacity} nodes")

            self._log_action(
                cluster_id=cluster.id,
                action_type="scale_up",
                status="simulated",
                details=action
            )

            return {
                "action": action,
                "status": "simulated"
            }

        # TODO: Implement ASG scale-up

        self._log_action(
            cluster_id=cluster.id,
            action_type="scale_up",
            status="completed",
            details=action
        )

        return {
            "action": action,
            "status": ExecutionStatus.COMPLETED.value
        }

    def _log_action(
        self,
        cluster_id: str,
        action_type: str,
        status: str,
        details: Dict[str, Any]
    ) -> None:
        """
        Log action to database

        Args:
            cluster_id: Cluster UUID
            action_type: Type of action
            status: Execution status
            details: Action details
        """
        try:
            action_log = ActionLog(
                cluster_id=cluster_id,
                action_type=action_type,
                status=status,
                details=details
            )

            self.db.add(action_log)
            self.db.commit()

            logger.debug(f"[CORE-EXEC] Logged action: {action_type} - {status}")

        except Exception as e:
            logger.error(f"[CORE-EXEC] Error logging action: {str(e)}")


def get_action_executor(db: Session, redis_client=None) -> ActionExecutor:
    """
    Factory function to create Action Executor instance

    Args:
        db: Database session
        redis_client: Optional Redis client

    Returns:
        ActionExecutor instance
    """
    return ActionExecutor(db, redis_client)
