# Agent Termination Implementation Guide

## Overview

This document describes the required changes to the agent's Cleanup worker to actually terminate instances in AWS when they are marked as 'zombie' or 'terminated' in the database.

## Problem

Currently, the backend correctly marks instances as 'zombie' or 'terminated' in the database, but the agent's Cleanup worker does not poll for these instances and terminate them via AWS EC2 API. This causes instances to remain running in AWS even though the system shows them as terminated.

## Solution

The agent's Cleanup worker needs to poll a new backend endpoint and terminate instances via AWS EC2 API.

---

## Backend Changes (✅ COMPLETED)

### 1. New Endpoint: Get Instances to Terminate

**Endpoint:** `GET /api/agents/{agent_id}/instances-to-terminate`

**Returns:**
```json
{
  "instances": [
    {
      "instance_id": "i-1234567890abcdef0",
      "instance_type": "c5.large",
      "az": "us-east-1a",
      "reason": "zombie_timeout",
      "seconds_waiting": 320
    },
    {
      "instance_id": "i-0987654321fedcba0",
      "instance_type": "c5.large",
      "az": "us-east-1b",
      "reason": "replica_terminated",
      "seconds_since_marked": 5
    }
  ],
  "auto_terminate_enabled": true,
  "terminate_wait_seconds": 300
}
```

**Logic:**
- Only returns instances if `auto_terminate_enabled = TRUE`
- Returns zombie instances that have been in zombie state longer than `terminate_wait_seconds`
- Returns replica instances marked as terminated but not yet terminated in AWS
- Prevents duplicate attempts by tracking `termination_attempted_at`

### 2. New Endpoint: Report Termination

**Endpoint:** `POST /api/agents/{agent_id}/termination-report`

**Request Body:**
```json
{
  "instance_id": "i-1234567890abcdef0",
  "success": true,
  "error": null,
  "terminated_at": "2025-11-25T12:30:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Termination report recorded"
}
```

### 3. Database Migration

**File:** `/database/migrations/add_termination_tracking.sql`

Adds tracking columns:
- `termination_attempted_at` - Timestamp of last termination attempt
- `termination_confirmed` - Boolean flag for AWS confirmation

**To Apply:**
```bash
mysql -u root -p spot_optimizer_production < /home/user/final-ml/database/migrations/add_termination_tracking.sql
```

---

## Agent Changes Required

### Location

The Cleanup worker in the agent (typically in `/opt/spot-agent/workers/cleanup.py` or similar).

### Current Cleanup Worker Behavior

The agent's Cleanup worker currently:
- Cleans up old AMIs (snapshots older than X days)
- Cleans up old snapshots
- Sends cleanup reports to backend

### Required New Behavior

The Cleanup worker needs to:
1. Poll `/api/agents/{agent_id}/instances-to-terminate` every 60 seconds
2. For each instance returned, terminate it via AWS EC2 API
3. Report results back to `/api/agents/{agent_id}/termination-report`

### Implementation

#### 1. Add Instance Termination to Cleanup Worker

```python
import boto3
import requests
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

class CleanupWorker:
    def __init__(self, agent_id: str, server_url: str, client_token: str, region: str):
        self.agent_id = agent_id
        self.server_url = server_url
        self.client_token = client_token
        self.region = region
        self.ec2_client = boto3.client('ec2', region_name=region)

    def run_cleanup_loop(self):
        """Main cleanup loop - runs every 60 seconds"""
        while True:
            try:
                # Existing cleanup tasks
                self._cleanup_old_amis()
                self._cleanup_old_snapshots()

                # NEW: Terminate zombie/terminated instances
                self._terminate_marked_instances()

                time.sleep(60)  # Check every 60 seconds
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                time.sleep(60)

    def _terminate_marked_instances(self):
        """Fetch and terminate instances marked for termination"""
        try:
            # Get instances to terminate from backend
            response = requests.get(
                f"{self.server_url}/api/agents/{self.agent_id}/instances-to-terminate",
                headers={"Authorization": f"Bearer {self.client_token}"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            instances_to_terminate = data.get('instances', [])
            auto_terminate_enabled = data.get('auto_terminate_enabled', False)

            if not auto_terminate_enabled:
                logger.debug("Auto-terminate is disabled - skipping instance termination")
                return

            if not instances_to_terminate:
                logger.debug("No instances to terminate")
                return

            logger.info(f"Found {len(instances_to_terminate)} instances to terminate")

            # Terminate each instance
            for inst in instances_to_terminate:
                instance_id = inst['instance_id']
                reason = inst.get('reason', 'unknown')

                logger.info(f"Terminating instance {instance_id} (reason: {reason})")

                try:
                    # Terminate via AWS EC2 API
                    self._terminate_instance(instance_id)

                    # Report success to backend
                    self._report_termination_success(instance_id)

                    logger.info(f"✓ Successfully terminated instance {instance_id}")

                except Exception as e:
                    logger.error(f"✗ Failed to terminate instance {instance_id}: {e}")

                    # Report failure to backend
                    self._report_termination_failure(instance_id, str(e))

        except Exception as e:
            logger.error(f"Error fetching instances to terminate: {e}")

    def _terminate_instance(self, instance_id: str):
        """Terminate instance via AWS EC2 API"""
        try:
            response = self.ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )

            # Check if termination was initiated
            if response['TerminatingInstances']:
                terminating_inst = response['TerminatingInstances'][0]
                current_state = terminating_inst['CurrentState']['Name']
                logger.info(f"Instance {instance_id} state changed to: {current_state}")
            else:
                raise Exception("No terminating instances in response")

        except self.ec2_client.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']

            # Handle specific AWS errors
            if error_code == 'InvalidInstanceID.NotFound':
                logger.warning(f"Instance {instance_id} not found in AWS - may already be terminated")
                # Still report as success since the goal (instance gone) is achieved
                return
            elif error_code == 'UnauthorizedOperation':
                raise Exception(f"IAM permissions insufficient to terminate instance {instance_id}")
            else:
                raise Exception(f"AWS error: {error_code} - {e.response['Error']['Message']}")

    def _report_termination_success(self, instance_id: str):
        """Report successful termination to backend"""
        try:
            response = requests.post(
                f"{self.server_url}/api/agents/{self.agent_id}/termination-report",
                headers={"Authorization": f"Bearer {self.client_token}"},
                json={
                    "instance_id": instance_id,
                    "success": True,
                    "error": None,
                    "terminated_at": datetime.utcnow().isoformat()
                },
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to report termination success for {instance_id}: {e}")

    def _report_termination_failure(self, instance_id: str, error_message: str):
        """Report failed termination to backend"""
        try:
            response = requests.post(
                f"{self.server_url}/api/agents/{self.agent_id}/termination-report",
                headers={"Authorization": f"Bearer {self.client_token}"},
                json={
                    "instance_id": instance_id,
                    "success": False,
                    "error": error_message,
                    "terminated_at": None
                },
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to report termination failure for {instance_id}: {e}")
```

#### 2. IAM Permissions Required

The agent's IAM role must have permission to terminate instances:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:TerminateInstances",
        "ec2:DescribeInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "ec2:Region": "us-east-1"
        }
      }
    }
  ]
}
```

**Note:** Adjust the region condition to match your deployment region.

#### 3. Configuration

Add to agent configuration (`/opt/spot-agent/config/agent.conf`):

```bash
# Termination settings
AUTO_TERMINATE_ENABLED=true
TERMINATION_CHECK_INTERVAL=60  # seconds
```

---

## Testing

### Test Scenario 1: Manual Replica Disabled

1. Enable manual replica mode for an agent
2. Wait for replica to be created and become ready
3. Disable manual replica mode
4. Check backend logs - should see "TERMINATED X active replicas"
5. Wait 60 seconds for agent cleanup worker to run
6. Check agent logs - should see "Terminating instance i-xxx (reason: replica_terminated)"
7. Verify in AWS console - instance should be in "terminated" or "shutting-down" state
8. Check backend database:
   ```sql
   SELECT instance_id, instance_status, termination_confirmed, terminated_at
   FROM replica_instances
   WHERE agent_id = 'your-agent-id'
   ORDER BY terminated_at DESC;
   ```

### Test Scenario 2: Replica Promotion with Zombie Timeout

1. Enable manual replica mode
2. Promote the replica to primary
3. Old primary should be marked as 'zombie'
4. Wait for `terminate_wait_seconds` (default 300 seconds = 5 minutes)
5. Agent cleanup worker should terminate the zombie instance
6. Verify termination in AWS console
7. Check backend database:
   ```sql
   SELECT id, instance_status, termination_attempted_at, termination_confirmed
   FROM instances
   WHERE instance_status = 'zombie'
   ORDER BY updated_at DESC;
   ```

### Test Scenario 3: Auto-Terminate Disabled

1. Disable auto-terminate in agent configuration
2. Perform any action that marks an instance as zombie or terminated
3. Verify that the cleanup worker does NOT terminate the instance
4. Instance should remain running in AWS console
5. Backend should return empty array from `/instances-to-terminate` endpoint

---

## Monitoring and Logging

### Agent Logs

Add log statements to track termination activity:

```python
logger.info(f"Cleanup: Checking for instances to terminate...")
logger.info(f"Cleanup: Found {len(instances)} instances to terminate")
logger.info(f"Cleanup: Terminating {instance_id} (reason: {reason})")
logger.info(f"Cleanup: ✓ Successfully terminated {instance_id}")
logger.error(f"Cleanup: ✗ Failed to terminate {instance_id}: {error}")
```

### Backend System Events

The backend logs termination events to the `system_events` table:

```sql
SELECT * FROM system_events
WHERE event_type IN ('instance_terminated', 'instance_termination_failed')
ORDER BY created_at DESC
LIMIT 20;
```

### Metrics to Track

- Number of instances terminated per day
- Termination success rate
- Average time from marking to actual termination
- Failed termination attempts

---

## Troubleshooting

### Instances Not Being Terminated

**Symptom:** Database shows instances as 'zombie' or 'terminated', but AWS console shows them still running.

**Possible Causes:**
1. **Agent cleanup worker not running**
   - Check: `ps aux | grep cleanup`
   - Fix: Start the cleanup worker

2. **Auto-terminate disabled**
   - Check: `SELECT auto_terminate_enabled FROM agents WHERE id = 'your-agent-id'`
   - Fix: Enable in agent configuration UI

3. **IAM permissions missing**
   - Check agent logs for "UnauthorizedOperation" errors
   - Fix: Add `ec2:TerminateInstances` permission to agent's IAM role

4. **Network connectivity issues**
   - Check agent logs for connection errors to backend
   - Fix: Verify security groups allow outbound HTTPS to backend

5. **Backend endpoint not accessible**
   - Test: `curl -H "Authorization: Bearer <token>" https://backend/api/agents/<id>/instances-to-terminate`
   - Fix: Check backend server status

### Checking Termination Status

```bash
# On agent instance:
# Check if cleanup worker is calling the endpoint
tail -f /var/log/spot-optimizer/agent.log | grep -i terminate

# Check AWS CLI
aws ec2 describe-instances --instance-ids i-xxx --query 'Reservations[0].Instances[0].State'

# On backend:
# Check database
mysql -u root -p spot_optimizer_production
SELECT instance_id, instance_status, termination_attempted_at, termination_confirmed
FROM instances
WHERE instance_status IN ('zombie', 'terminated')
ORDER BY updated_at DESC;
```

---

## Migration Checklist

- [ ] Apply database migration: `add_termination_tracking.sql`
- [ ] Deploy backend changes (new endpoints already added)
- [ ] Update agent code with termination logic
- [ ] Add IAM permissions for EC2 termination
- [ ] Test with manual replica enable/disable
- [ ] Test with replica promotion
- [ ] Verify logs show successful terminations
- [ ] Monitor system events for failures

---

## Additional Notes

### Why Termination is Done by Agent (Not Backend)

The termination is performed by the agent because:
1. **IAM Security**: Each agent has its own IAM role with permissions limited to its region/account
2. **Network Isolation**: Agent runs in same VPC as instances to terminate
3. **Distributed Architecture**: Backend doesn't have AWS credentials
4. **Scalability**: Each agent manages its own cleanup independently

### Retry Logic

The system includes built-in retry logic:
- Failed terminations are reported back to backend
- `termination_attempted_at` is updated even on failure
- Next poll (60s later) won't re-attempt if `termination_attempted_at` is within last 5 minutes
- This prevents hammering AWS API with failed requests

### Safety Features

- Only terminates if `auto_terminate_enabled = TRUE`
- Waits for `terminate_wait_seconds` before terminating zombies
- Tracks attempts to prevent duplicate termination requests
- Logs all actions for audit trail
- Reports failures for investigation

---

**Last Updated:** 2025-11-25
**Agent Version Required:** 4.1.0+
