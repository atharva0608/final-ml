"""
================================================================================
COMMAND TRACKING COMPONENT - Command Lifecycle Management
================================================================================

COMPONENT PURPOSE:
------------------
Reusable utility for generating, structuring, and tracking the complete lifecycle
of all commands intended for execution on the agent side. Provides priority-based
queuing, status tracking, and execution result logging.

KEY RESPONSIBILITIES:
--------------------
1. Command Generation: Create properly structured commands
2. Priority Management: Emergency (100) > Manual (75) > ML (50) > Scheduled (10)
3. Status Tracking: pending → executing → completed/failed
4. Result Logging: Capture execution results and timing
5. Queue Management: Ensure agents get highest priority commands first

SCENARIO EXAMPLES:
-----------------

Scenario 1: Emergency Termination Command (Highest Priority)
------------------------------------------------------------
AWS sends termination notice → Backend must act immediately

Command Tracker Processing:
1. create_command(
     type='emergency_switch',
     priority=100,  # CRITICAL
     agent_id='agent-123',
     target_mode='spot',
     target_pool='t3.medium.us-east-1b',  # Cheapest available
     trigger='aws_termination_notice'
   )

2. Inserts into commands table:
   {
     'id': 'cmd-uuid-here',
     'priority': 100,
     'status': 'pending',
     'created_at': '2024-01-15 10:23:45',
     'command_type': 'emergency_switch',
     ...
   }

3. Agent polls /api/agents/<id>/pending-commands
   → Gets this command FIRST (highest priority)

4. Agent executes switch (AMI creation → instance launch → failover)

5. Agent reports result → mark_completed()
   {
     'command_id': 'cmd-uuid-here',
     'success': True,
     'execution_time_seconds': 42,
     'new_instance_id': 'i-new789',
     'ami_id': 'ami-snapshot123'
   }

6. Updates command:
   status='completed', success=True, completed_at='2024-01-15 10:24:27'

Result: Full audit trail, Emergency handled in 42 seconds

Scenario 2: ML-Driven Switch (Normal Priority)
----------------------------------------------
ML model recommends switch to cheaper pool

Command Tracker Processing:
1. create_command(
     type='switch',
     priority=50,  # Normal ML priority
     agent_id='agent-456',
     target_pool='t3.medium.us-east-1c',
     trigger='ml_recommendation',
     created_by='ml_based_engine',
     metadata={'confidence': 0.87, 'expected_savings': 0.0245}
   )

2. Agent polls commands → Gets this after any emergency commands

3. Agent executes → Reports success

4. Links to switches table record for tracking

Result: ML decision tracked with confidence score and outcome

Scenario 3: Manual Override (High Priority)
-------------------------------------------
User clicks "Switch to On-Demand" button in dashboard

Command Tracker Processing:
1. create_command(
     type='switch_to_ondemand',
     priority=75,  # Manual override = high priority
     agent_id='agent-789',
     target_mode='ondemand',
     trigger='manual_ui',
     created_by='user@company.com'
   )

2. Executes before ML recommendations but after emergencies

3. Logs who initiated (user email) for audit

Result: User action logged, priorities respected

Scenario 4: Failed Command Handling
-----------------------------------
Switch fails due to AWS capacity limit

Command Tracker Processing:
1. Agent attempts switch → AWS returns CapacityError

2. Agent reports failure:
   mark_failed(
     command_id='cmd-uuid',
     error='InsufficientInstanceCapacity: t3.medium.us-east-1c',
     retry_recommended=True
   )

3. Updates command:
   status='failed',
   success=False,
   message='InsufficientInstanceCapacity...',
   metadata={'retry_count': 1, 'can_retry': True}

4. System can auto-retry or fallback:
   - Try next cheapest pool
   - Escalate to on-demand if critical

Result: Failures tracked, retry logic enabled

CONFIGURATION:
-------------
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import IntEnum

from backend.database_manager import execute_query
from backend.utils import generate_uuid

logger = logging.getLogger(__name__)


class CommandPriority(IntEnum):
    """
    Command priority levels

    Higher number = executes first

    Emergency situations (AWS interruptions) always take precedence
    """
    EMERGENCY = 100  # AWS termination/rebalance notices
    MANUAL_OVERRIDE = 75  # User-initiated actions
    ML_URGENT = 50  # ML model recommendations (high confidence)
    ML_NORMAL = 25  # ML model recommendations (normal)
    SCHEDULED = 10  # Scheduled/maintenance tasks


class CommandStatus:
    """Command lifecycle status values"""
    PENDING = 'pending'
    EXECUTING = 'executing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class CommandType:
    """Standard command types"""
    SWITCH = 'switch'
    EMERGENCY_SWITCH = 'emergency_switch'
    SWITCH_TO_ONDEMAND = 'switch_to_ondemand'
    CREATE_REPLICA = 'create_replica'
    DELETE_REPLICA = 'delete_replica'
    PROMOTE_REPLICA = 'promote_replica'
    CLEANUP_OLD_AMIS = 'cleanup_old_amis'
    HEALTH_CHECK = 'health_check'


class CommandTracker:
    """
    Command Tracker - Command Lifecycle Manager

    Provides centralized command creation, tracking, and result logging.

    Example Usage:

    from backend.components.command_tracker import command_tracker

    # Create emergency command
    cmd_id = command_tracker.create_command(
        agent_id='agent-123',
        command_type=CommandType.EMERGENCY_SWITCH,
        priority=CommandPriority.EMERGENCY,
        target_pool='t3.medium.us-east-1b',
        trigger='aws_termination_notice'
    )

    # Agent polls for commands
    commands = command_tracker.get_pending_commands('agent-123')
    # Returns highest priority commands first

    # Agent reports execution result
    command_tracker.mark_completed(
        command_id=cmd_id,
        success=True,
        execution_result={'new_instance_id': 'i-new123', 'ami_id': 'ami-snap456'},
        execution_time_seconds=42
    )
    """

    def create_command(
        self,
        agent_id: str,
        client_id: str,
        command_type: str,
        priority: int = CommandPriority.ML_NORMAL,
        target_mode: str = None,
        target_pool_id: str = None,
        instance_id: str = None,
        terminate_wait_seconds: int = None,
        trigger_type: str = None,
        created_by: str = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Create a new command in the queue

        Args:
            agent_id: Target agent UUID
            client_id: Client UUID
            command_type: Type of command (use CommandType constants)
            priority: Priority level (use CommandPriority constants)
            target_mode: Target mode ('spot', 'ondemand', 'pool')
            target_pool_id: Target spot pool ID
            instance_id: Related instance ID
            terminate_wait_seconds: Wait time before terminating old instance
            trigger_type: What triggered this command
            created_by: Who/what created it (user email, 'ml_engine', 'system')
            metadata: Additional context as JSON

        Returns:
            command_id: UUID of created command

        Example:
            cmd_id = command_tracker.create_command(
                agent_id='agent-123',
                client_id='client-456',
                command_type=CommandType.SWITCH,
                priority=CommandPriority.ML_URGENT,
                target_pool_id='t3.medium.us-east-1c',
                trigger_type='ml_recommendation',
                created_by='ml_based_engine',
                metadata={
                    'ml_confidence': 0.87,
                    'expected_savings': 0.0245,
                    'risk_score': 0.15
                }
            )
        """
        command_id = generate_uuid()

        execute_query("""
            INSERT INTO commands (
                id, client_id, agent_id, command_type,
                target_mode, target_pool_id, instance_id,
                priority, terminate_wait_seconds,
                status, created_by, trigger_type,
                execution_result, created_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, NOW()
            )
        """, (
            command_id, client_id, agent_id, command_type,
            target_mode, target_pool_id, instance_id,
            priority, terminate_wait_seconds,
            CommandStatus.PENDING, created_by, trigger_type,
            None if not metadata else str(metadata)
        ))

        logger.info(
            f"Command created: id={command_id}, type={command_type}, "
            f"priority={priority}, agent={agent_id}, trigger={trigger_type}"
        )

        return command_id

    def get_pending_commands(
        self,
        agent_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get pending commands for agent (highest priority first)

        Priority Order:
        1. Emergency (100) - AWS interruptions
        2. Manual Override (75) - User actions
        3. ML Urgent (50) - High-confidence ML recommendations
        4. ML Normal (25) - Normal ML recommendations
        5. Scheduled (10) - Maintenance tasks

        Args:
            agent_id: Agent UUID
            limit: Max commands to return (default 10)

        Returns:
            List of command dictionaries, highest priority first

        Example Result:
            [
                {
                    'id': 'cmd-uuid-123',
                    'command_type': 'emergency_switch',
                    'priority': 100,
                    'target_pool_id': 't3.medium.us-east-1b',
                    'created_at': datetime(...),
                    'trigger_type': 'aws_termination_notice'
                },
                ...
            ]
        """
        commands = execute_query("""
            SELECT
                id, command_type, target_mode, target_pool_id,
                instance_id, priority, terminate_wait_seconds,
                status, created_by, trigger_type, created_at
            FROM commands
            WHERE agent_id = %s
              AND status = %s
            ORDER BY priority DESC, created_at ASC
            LIMIT %s
        """, (agent_id, CommandStatus.PENDING, limit), fetch=True)

        return commands or []

    def mark_executing(self, command_id: str) -> bool:
        """
        Mark command as currently executing

        Called by agent when it starts processing a command

        Args:
            command_id: Command UUID

        Returns:
            True if status updated successfully
        """
        rowcount = execute_query("""
            UPDATE commands
            SET status = %s, executed_at = NOW()
            WHERE id = %s AND status = %s
        """, (CommandStatus.EXECUTING, command_id, CommandStatus.PENDING), return_rowcount=True)

        if rowcount > 0:
            logger.info(f"Command executing: id={command_id}")
            return True
        else:
            logger.warning(f"Failed to mark command executing: id={command_id} (already executing?)")
            return False

    def mark_completed(
        self,
        command_id: str,
        success: bool = True,
        message: str = None,
        execution_result: Dict[str, Any] = None,
        execution_time_seconds: int = None
    ) -> bool:
        """
        Mark command as completed (success or failure)

        Called by agent after command execution finishes

        Args:
            command_id: Command UUID
            success: Whether execution succeeded
            message: Human-readable result message
            execution_result: Detailed result data as dictionary
            execution_time_seconds: How long execution took

        Returns:
            True if status updated successfully

        Example:
            command_tracker.mark_completed(
                command_id='cmd-123',
                success=True,
                message='Switch completed successfully',
                execution_result={
                    'new_instance_id': 'i-new789',
                    'ami_id': 'ami-snap456',
                    'old_instance_terminated': True,
                    'switch_duration_seconds': 47
                },
                execution_time_seconds=47
            )
        """
        import json

        rowcount = execute_query("""
            UPDATE commands
            SET
                status = %s,
                success = %s,
                message = %s,
                execution_result = %s,
                completed_at = NOW()
            WHERE id = %s
        """, (
            CommandStatus.COMPLETED,
            success,
            message,
            json.dumps(execution_result) if execution_result else None,
            command_id
        ), return_rowcount=True)

        if rowcount > 0:
            logger.info(
                f"Command completed: id={command_id}, success={success}, "
                f"execution_time={execution_time_seconds}s"
            )
            return True
        else:
            logger.warning(f"Failed to mark command completed: id={command_id}")
            return False

    def mark_failed(
        self,
        command_id: str,
        error: str,
        retry_recommended: bool = False,
        execution_result: Dict[str, Any] = None
    ) -> bool:
        """
        Mark command as failed

        Args:
            command_id: Command UUID
            error: Error message
            retry_recommended: Whether system should retry
            execution_result: Error details

        Returns:
            True if status updated successfully

        Example:
            command_tracker.mark_failed(
                command_id='cmd-123',
                error='InsufficientInstanceCapacity: t3.medium.us-east-1c',
                retry_recommended=True,
                execution_result={
                    'aws_error_code': 'InsufficientInstanceCapacity',
                    'pool_id': 't3.medium.us-east-1c',
                    'suggested_action': 'try_different_pool'
                }
            )
        """
        import json

        rowcount = execute_query("""
            UPDATE commands
            SET
                status = %s,
                success = FALSE,
                message = %s,
                execution_result = %s,
                completed_at = NOW()
            WHERE id = %s
        """, (
            CommandStatus.FAILED,
            error,
            json.dumps(execution_result) if execution_result else None,
            command_id
        ), return_rowcount=True)

        if rowcount > 0:
            logger.error(
                f"Command failed: id={command_id}, error={error}, "
                f"retry_recommended={retry_recommended}"
            )
            return True
        else:
            logger.warning(f"Failed to mark command as failed: id={command_id}")
            return False

    def cancel_command(self, command_id: str, reason: str = None) -> bool:
        """
        Cancel a pending command

        Args:
            command_id: Command UUID
            reason: Why it was cancelled

        Returns:
            True if cancelled successfully
        """
        rowcount = execute_query("""
            UPDATE commands
            SET status = %s, message = %s
            WHERE id = %s AND status = %s
        """, (
            CommandStatus.CANCELLED,
            reason or 'Cancelled by system',
            command_id,
            CommandStatus.PENDING
        ), return_rowcount=True)

        if rowcount > 0:
            logger.info(f"Command cancelled: id={command_id}, reason={reason}")
            return True
        else:
            return False

    def get_command_status(self, command_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a command

        Args:
            command_id: Command UUID

        Returns:
            Command details or None if not found
        """
        return execute_query("""
            SELECT
                id, command_type, status, success,
                message, execution_result,
                created_at, executed_at, completed_at,
                priority, created_by, trigger_type
            FROM commands
            WHERE id = %s
        """, (command_id,), fetch_one=True)

    def get_command_history(
        self,
        agent_id: str = None,
        client_id: str = None,
        limit: int = 50,
        include_pending: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get command execution history

        Args:
            agent_id: Filter by agent
            client_id: Filter by client
            limit: Max results
            include_pending: Include pending commands

        Returns:
            List of command records, most recent first
        """
        where_clauses = []
        params = []

        if agent_id:
            where_clauses.append("agent_id = %s")
            params.append(agent_id)

        if client_id:
            where_clauses.append("client_id = %s")
            params.append(client_id)

        if not include_pending:
            where_clauses.append("status != %s")
            params.append(CommandStatus.PENDING)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        params.append(limit)

        commands = execute_query(f"""
            SELECT
                id, command_type, status, success,
                message, priority, trigger_type, created_by,
                created_at, executed_at, completed_at
            FROM commands
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT %s
        """, tuple(params), fetch=True)

        return commands or []


# ============================================================================
# GLOBAL INSTANCE (SINGLETON PATTERN)
# ============================================================================

# Global command tracker instance - import this in services
command_tracker = CommandTracker()

logger.info("Command Tracker component initialized and ready")
