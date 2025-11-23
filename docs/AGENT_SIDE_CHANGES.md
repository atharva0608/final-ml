# Agent-Side Implementation Guide

## Overview
This document outlines the changes needed on the agent side to support the new server features, particularly around agent deletion, status management, and proper cleanup.

---

## 🔧 Required Agent Changes

### 1. Agent Deletion Support

#### Current Behavior
- Agent runs continuously until manually stopped
- No cleanup when agent process terminates
- No server notification on shutdown

#### Required Changes

**On Agent Shutdown:**
```python
def shutdown_agent():
    """
    Gracefully shutdown agent and notify server.
    Called when:
    - User manually stops agent service
    - Agent uninstalled via script
    - System shutdown
    """
    try:
        # 1. Send final heartbeat with 'offline' status
        requests.post(
            f"{SERVER_URL}/api/agents/{AGENT_ID}/heartbeat",
            json={"status": "offline"},
            headers={"Authorization": f"Bearer {CLIENT_TOKEN}"}
        )

        # 2. Log shutdown
        logger.info("Agent shutdown initiated")

        # 3. Stop all background tasks
        stop_pricing_collection()
        stop_heartbeat_thread()

        # 4. Close database connections
        cleanup_resources()

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
```

**Signal Handlers:**
```python
import signal
import sys

def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {signum}")
    shutdown_agent()
    sys.exit(0)

# Register handlers
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # kill command
```

**Systemd Service Integration:**
```ini
[Unit]
Description=ML Spot Instance Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/spot-agent start
ExecStop=/usr/local/bin/spot-agent shutdown
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

### 2. Uninstall Script Enhancement

#### Current Uninstall Script
```bash
#!/bin/bash
# Basic uninstall

systemctl stop spot-agent
systemctl disable spot-agent
rm /etc/systemd/system/spot-agent.service
rm -rf /opt/spot-agent
```

#### Enhanced Uninstall Script
```bash
#!/bin/bash
# Enhanced uninstall with server notification

set -e

AGENT_ID=$(cat /opt/spot-agent/agent_id.txt)
CLIENT_TOKEN=$(cat /opt/spot-agent/client_token.txt)
SERVER_URL=$(cat /opt/spot-agent/server_url.txt)

echo "Uninstalling Spot Agent..."

# 1. Notify server of intentional shutdown
curl -X POST "${SERVER_URL}/api/agents/${AGENT_ID}/heartbeat" \
  -H "Authorization: Bearer ${CLIENT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"status":"offline"}' || true

# 2. Wait for graceful shutdown
sleep 2

# 3. Stop and disable service
systemctl stop spot-agent || true
systemctl disable spot-agent || true

# 4. Remove service file
rm -f /etc/systemd/system/spot-agent.service
systemctl daemon-reload

# 5. Remove agent files (keep logs for debugging)
rm -rf /opt/spot-agent/bin
rm -rf /opt/spot-agent/config
# Keep /opt/spot-agent/logs for 7 days
find /opt/spot-agent/logs -type f -mtime +7 -delete

# 6. Remove cron jobs
crontab -l | grep -v spot-agent | crontab - || true

echo "✓ Agent uninstalled successfully"
echo "Note: Logs retained in /opt/spot-agent/logs"
echo "To complete removal, delete agent from server dashboard"
```

---

### 3. Installation Script Enhancement

#### Current Install Script
```bash
#!/bin/bash
# Basic install

# ... setup code ...

# Register with server
AGENT_ID=$(uuidgen)
echo "$AGENT_ID" > /opt/spot-agent/agent_id.txt
```

#### Enhanced Install Script
```bash
#!/bin/bash
# Enhanced install with proper registration

set -e

# Configuration
SERVER_URL=${SERVER_URL:-"http://your-server:5000"}
CLIENT_TOKEN=${CLIENT_TOKEN:?"CLIENT_TOKEN environment variable required"}

echo "Installing Spot Agent..."

# 1. Create directory structure
mkdir -p /opt/spot-agent/{bin,config,logs,data}

# 2. Install agent binary
cp spot-agent /opt/spot-agent/bin/
chmod +x /opt/spot-agent/bin/spot-agent

# 3. Get instance metadata
INSTANCE_ID=$(ec2-metadata --instance-id | cut -d " " -f 2)
INSTANCE_TYPE=$(ec2-metadata --instance-type | cut -d " " -f 2)
REGION=$(ec2-metadata --availability-zone | cut -d " " -f 2 | sed 's/.$//')
AZ=$(ec2-metadata --availability-zone | cut -d " " -f 2)
AMI_ID=$(ec2-metadata --ami-id | cut -d " " -f 2)
PRIVATE_IP=$(ec2-metadata --local-ipv4 | cut -d " " -f 2)
PUBLIC_IP=$(ec2-metadata --public-ipv4 | cut -d " " -f 2 2>/dev/null || echo "")

# 4. Determine current mode
if ec2-metadata --instance-life-cycle | grep -q "spot"; then
    CURRENT_MODE="spot"
else
    CURRENT_MODE="ondemand"
fi

# 5. Generate logical agent ID (persistent across switches)
LOGICAL_AGENT_ID="agent-$(hostname)-$(date +%s)"

# 6. Create configuration file
cat > /opt/spot-agent/config/agent.conf <<EOF
SERVER_URL=$SERVER_URL
CLIENT_TOKEN=$CLIENT_TOKEN
LOGICAL_AGENT_ID=$LOGICAL_AGENT_ID
INSTANCE_ID=$INSTANCE_ID
INSTANCE_TYPE=$INSTANCE_TYPE
REGION=$REGION
AZ=$AZ
AMI_ID=$AMI_ID
CURRENT_MODE=$CURRENT_MODE
AGENT_VERSION=2.0.0
EOF

# 7. Register with server
echo "Registering agent with server..."
RESPONSE=$(curl -s -X POST "${SERVER_URL}/api/agents/register" \
  -H "Authorization: Bearer ${CLIENT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"logical_agent_id\": \"${LOGICAL_AGENT_ID}\",
    \"instance_id\": \"${INSTANCE_ID}\",
    \"instance_type\": \"${INSTANCE_TYPE}\",
    \"region\": \"${REGION}\",
    \"az\": \"${AZ}\",
    \"ami_id\": \"${AMI_ID}\",
    \"mode\": \"${CURRENT_MODE}\",
    \"hostname\": \"$(hostname)\",
    \"private_ip\": \"${PRIVATE_IP}\",
    \"public_ip\": \"${PUBLIC_IP}\",
    \"agent_version\": \"2.0.0\"
  }")

# 8. Extract agent ID from response
AGENT_ID=$(echo "$RESPONSE" | jq -r '.agent_id')
if [ -z "$AGENT_ID" ] || [ "$AGENT_ID" = "null" ]; then
    echo "Error: Failed to register agent"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "✓ Agent registered with ID: $AGENT_ID"
echo "$AGENT_ID" > /opt/spot-agent/agent_id.txt

# 9. Create systemd service
cat > /etc/systemd/system/spot-agent.service <<EOF
[Unit]
Description=ML Spot Instance Management Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/spot-agent
EnvironmentFile=/opt/spot-agent/config/agent.conf
ExecStart=/opt/spot-agent/bin/spot-agent start
ExecStop=/opt/spot-agent/bin/spot-agent shutdown
Restart=on-failure
RestartSec=10
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

# 10. Enable and start service
systemctl daemon-reload
systemctl enable spot-agent
systemctl start spot-agent

# 11. Verify installation
sleep 3
if systemctl is-active --quiet spot-agent; then
    echo "✓ Agent installed and running successfully"
    echo "Agent ID: $AGENT_ID"
    echo "Logical Agent ID: $LOGICAL_AGENT_ID"
else
    echo "✗ Agent failed to start. Check logs:"
    echo "journalctl -u spot-agent -n 50"
    exit 1
fi
```

---

### 4. Heartbeat Enhancement

#### Current Heartbeat
```python
def send_heartbeat():
    """Send basic heartbeat"""
    requests.post(
        f"{SERVER_URL}/api/agents/{AGENT_ID}/heartbeat",
        json={"status": "online"}
    )
```

#### Enhanced Heartbeat
```python
def send_heartbeat():
    """
    Send enhanced heartbeat with instance details.
    Allows server to detect instance changes during auto-switching.
    """
    try:
        # Get current instance metadata
        instance_id = get_instance_id()
        instance_type = get_instance_type()
        current_mode = get_instance_mode()  # 'spot' or 'ondemand'
        az = get_availability_zone()

        # Send heartbeat
        response = requests.post(
            f"{SERVER_URL}/api/agents/{AGENT_ID}/heartbeat",
            json={
                "status": "online",
                "instance_id": instance_id,
                "instance_type": instance_type,
                "mode": current_mode,
                "az": az
            },
            headers={"Authorization": f"Bearer {CLIENT_TOKEN}"},
            timeout=10
        )

        response.raise_for_status()
        logger.debug(f"Heartbeat sent successfully")

    except requests.exceptions.RequestException as e:
        logger.error(f"Heartbeat failed: {e}")
        # Don't crash on heartbeat failure
        # Server will mark agent offline after timeout
```

---

### 5. Agent State Management

#### Recommended State File Structure

```json
{
  "agent_id": "uuid-here",
  "logical_agent_id": "agent-hostname-timestamp",
  "instance_id": "i-1234567890abcdef0",
  "current_mode": "spot",
  "server_url": "http://server:5000",
  "last_heartbeat": "2025-01-01T00:00:00",
  "last_pricing_report": "2025-01-01T00:00:00",
  "replica_mode": "none",
  "auto_switch_enabled": true,
  "manual_replica_enabled": false
}
```

**State File Location:** `/opt/spot-agent/data/agent_state.json`

**Update on:**
- Registration
- Configuration changes from server
- Mode switches
- Replica promotions

---

### 6. Replica Synchronization (for Manual Replica Mode)

#### Replica Agent Behavior

When running as a replica (`replica_type = 'manual'`):

```python
def replica_sync_loop():
    """
    Continuous state synchronization for manual replicas.
    Ensures replica is ready for instant promotion.
    """
    while True:
        try:
            # 1. Fetch primary instance state
            primary_state = fetch_primary_state()

            # 2. Sync application state
            sync_application_state(primary_state)

            # 3. Report sync status to server
            requests.post(
                f"{SERVER_URL}/api/agents/{AGENT_ID}/replicas/{REPLICA_ID}/sync-status",
                json={
                    "sync_status": "synced",
                    "sync_latency_ms": calculate_latency(),
                    "state_transfer_progress": 100.0
                }
            )

            # 4. Sleep before next sync
            time.sleep(1)  # Sync every second

        except Exception as e:
            logger.error(f"Replica sync error: {e}")
            time.sleep(5)
```

---

### 7. Command Polling Enhancement

#### Current Command Polling
```python
def poll_commands():
    """Check for pending commands"""
    response = requests.get(f"{SERVER_URL}/api/agents/{AGENT_ID}/pending-commands")
    commands = response.json()
    for cmd in commands:
        execute_command(cmd)
```

#### Enhanced Command Polling
```python
def poll_commands():
    """
    Poll for pending commands with proper execution and reporting.
    Handles: switch, terminate, cleanup, config updates
    """
    try:
        response = requests.get(
            f"{SERVER_URL}/api/agents/{AGENT_ID}/pending-commands",
            headers={"Authorization": f"Bearer {CLIENT_TOKEN}"},
            timeout=10
        )
        response.raise_for_status()
        commands = response.json()

        for cmd in commands:
            command_id = cmd['id']
            command_type = cmd.get('target_mode', 'unknown')

            logger.info(f"Executing command {command_id}: {command_type}")

            try:
                # Execute command
                if command_type == 'spot':
                    result = switch_to_spot_pool(cmd['target_pool_id'])
                elif command_type == 'ondemand':
                    result = switch_to_ondemand()
                elif command_type == 'terminate':
                    result = graceful_terminate(cmd.get('terminate_wait_seconds', 300))
                else:
                    raise ValueError(f"Unknown command type: {command_type}")

                # Report success
                requests.post(
                    f"{SERVER_URL}/api/agents/{AGENT_ID}/commands/{command_id}/executed",
                    json={
                        "success": True,
                        "message": f"Command executed successfully: {result}"
                    },
                    headers={"Authorization": f"Bearer {CLIENT_TOKEN}"}
                )

            except Exception as e:
                # Report failure
                logger.error(f"Command execution failed: {e}")
                requests.post(
                    f"{SERVER_URL}/api/agents/{AGENT_ID}/commands/{command_id}/executed",
                    json={
                        "success": False,
                        "message": f"Command failed: {str(e)}"
                    },
                    headers={"Authorization": f"Bearer {CLIENT_TOKEN}"}
                )

    except Exception as e:
        logger.error(f"Command polling failed: {e}")
```

---

## 📋 Implementation Checklist

### High Priority

- [ ] Add signal handlers for graceful shutdown
- [ ] Send 'offline' status on agent shutdown
- [ ] Update uninstall script to notify server
- [ ] Enhance install script with proper registration
- [ ] Update heartbeat to include instance details

### Medium Priority

- [ ] Implement state file management
- [ ] Add replica synchronization (if manual replica enabled)
- [ ] Enhance command polling with error reporting
- [ ] Add systemd service ExecStop handler

### Low Priority

- [ ] Add agent self-health monitoring
- [ ] Implement automatic crash recovery
- [ ] Add telemetry and metrics collection
- [ ] Create agent CLI for management

---

## 🧪 Testing Guide

### Test Scenario 1: Normal Shutdown
```bash
# 1. Start agent
systemctl start spot-agent

# 2. Verify online status on dashboard
# 3. Stop agent
systemctl stop spot-agent

# 4. Verify agent shows as 'offline' on dashboard
# 5. Wait 5 minutes - agent should stay visible
```

### Test Scenario 2: Agent Deletion
```bash
# 1. Install and start agent
# 2. Note agent ID from dashboard
# 3. Click "Delete Agent" on dashboard
# 4. Verify agent disappears from active list
# 5. Check "Agent History" - agent should appear with status 'deleted'
```

### Test Scenario 3: Re-installation
```bash
# 1. Uninstall agent: ./uninstall.sh
# 2. Delete agent from dashboard
# 3. Reinstall agent: ./install.sh
# 4. Verify NEW agent ID generated
# 5. Verify agent shows as 'online'
```

### Test Scenario 4: Auto-Switch
```bash
# 1. Enable auto-switch on dashboard
# 2. Wait for ML model decision
# 3. Agent receives switch command
# 4. Agent executes switch
# 5. Agent re-registers with new instance details
# 6. Verify SAME agent ID maintained
# 7. Verify instance details updated
```

### Test Scenario 5: Manual Replica
```bash
# 1. Enable manual replica mode
# 2. Wait 10 seconds
# 3. Verify replica created (check dashboard)
# 4. Verify replica status = 'syncing' → 'ready'
# 5. Promote replica
# 6. Verify new replica created for new primary
```

---

## 🔍 Debugging Tips

### Check Agent Status
```bash
systemctl status spot-agent
journalctl -u spot-agent -f
```

### Verify Registration
```bash
curl http://server/api/client/<client_id>/agents
```

### Test Heartbeat
```bash
curl -X POST http://server/api/agents/<agent_id>/heartbeat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status":"online"}'
```

### Check Agent State
```bash
cat /opt/spot-agent/data/agent_state.json
```

---

## ⚠️ CRITICAL: Auto-Termination Fix

### Problem
Even when `auto_terminate_enabled = FALSE`, the old instance was being terminated during switches. This is now FIXED on the server side, but agents need to be updated to respect this setting.

### Server-Side Fixes (COMPLETED ✅)

1. **switch_report endpoint** - Now checks `auto_terminate_enabled` before marking old instance as terminated
2. **issue_switch_command endpoint** - Now sets `terminate_wait_seconds = 0` when auto_terminate is disabled

### Required Agent-Side Changes

#### Update Switch Command Handler

**Current (BROKEN) Behavior:**
```python
def execute_switch_command(command):
    """Execute switch command"""
    # Create AMI from current instance
    ami_id = create_ami()

    # Launch new instance
    new_instance = launch_instance(ami_id, command['target_pool_id'])

    # Wait for new instance to be ready
    wait_for_ready(new_instance)

    # ALWAYS terminates old instance - THIS IS THE BUG
    time.sleep(command['terminate_wait_seconds'])
    terminate_old_instance()
```

**Fixed (CORRECT) Behavior:**
```python
def execute_switch_command(command):
    """Execute switch command with proper auto-terminate handling"""
    # Create AMI from current instance
    ami_id = create_ami()

    # Launch new instance
    new_instance = launch_instance(ami_id, command['target_pool_id'])

    # Wait for new instance to be ready
    wait_for_ready(new_instance)

    # CRITICAL: Check terminate_wait_seconds before terminating
    # If 0, it means auto_terminate is DISABLED - do NOT terminate
    terminate_wait = command.get('terminate_wait_seconds', 0)

    if terminate_wait > 0:
        logger.info(f"Auto-terminate enabled: waiting {terminate_wait}s before terminating old instance")
        time.sleep(terminate_wait)
        terminate_old_instance()
        logger.info("Old instance terminated")
    else:
        logger.info("Auto-terminate disabled: keeping old instance running")
        # Old instance stays alive - user can manually terminate it later
```

#### Update Switch Report

**Send correct termination timestamp:**
```python
def report_switch_to_server(old_instance, new_instance, command):
    """Report switch completion to server"""

    timing = {
        'initiated_at': switch_start_time,
        'ami_created_at': ami_creation_time,
        'instance_launched_at': instance_launch_time,
        'instance_ready_at': instance_ready_time,
    }

    # ONLY include old_terminated_at if we actually terminated it
    if command.get('terminate_wait_seconds', 0) > 0:
        timing['old_terminated_at'] = datetime.utcnow().isoformat()
    # If terminate_wait_seconds is 0, don't include old_terminated_at
    # This tells server: old instance is still running

    response = requests.post(
        f"{SERVER_URL}/api/agents/{AGENT_ID}/switch-report",
        json={
            'old_instance': old_instance,
            'new_instance': new_instance,
            'timing': timing,
            'pricing': pricing_data,
            'trigger': 'auto_switch',
            'command_id': command['id']
        }
    )
```

### How It Works Now

**When `auto_terminate_enabled = TRUE`:**
1. Server creates command with `terminate_wait_seconds = 300` (or configured value)
2. Agent switches to new instance
3. Agent waits 300 seconds
4. Agent terminates old instance
5. Agent reports switch with `old_terminated_at` timestamp
6. Server marks old instance as inactive

**When `auto_terminate_enabled = FALSE`:**
1. Server creates command with `terminate_wait_seconds = 0`
2. Agent switches to new instance
3. Agent sees `terminate_wait_seconds = 0`
4. Agent **DOES NOT** terminate old instance
5. Agent reports switch **WITHOUT** `old_terminated_at` timestamp
6. Server keeps old instance as active
7. User can manually terminate old instance when ready

### Implementation Checklist

- [ ] Update switch command handler to check `terminate_wait_seconds`
- [ ] Add logging for auto-terminate status
- [ ] Only call `terminate_old_instance()` if `terminate_wait_seconds > 0`
- [ ] Only include `old_terminated_at` in switch report if actually terminated
- [ ] Test with `auto_terminate_enabled = FALSE`
- [ ] Verify old instance stays running after switch

### Testing

```bash
# Test 1: Auto-terminate ENABLED
# 1. Set auto_terminate_enabled = TRUE on dashboard
# 2. Set terminate_wait_seconds = 60
# 3. Trigger switch
# 4. Verify old instance terminated after 60 seconds
# 5. Verify old instance marked as inactive in database

# Test 2: Auto-terminate DISABLED
# 1. Set auto_terminate_enabled = FALSE on dashboard
# 2. Trigger switch
# 3. Verify old instance stays running
# 4. Verify old instance still marked as active in database
# 5. Can still access old instance (SSH, etc.)
```

### Example Code

**Complete switch handler with auto-terminate support:**

```python
def handle_switch_command(command):
    """
    Execute instance switch with proper auto-terminate handling.

    Args:
        command: Switch command from server containing:
            - target_mode: 'spot' or 'ondemand'
            - target_pool_id: Pool to switch to
            - terminate_wait_seconds: 0 = don't terminate, >0 = wait then terminate
    """
    try:
        logger.info(f"Starting switch: {command['target_mode']}, pool={command.get('target_pool_id')}")

        # Get current instance details
        old_instance = get_current_instance_metadata()

        # Step 1: Create AMI from current instance
        logger.info("Creating AMI from current instance...")
        ami_id = create_ami(
            instance_id=old_instance['instance_id'],
            name=f"auto-switch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        )
        ami_created_at = datetime.utcnow()
        logger.info(f"AMI created: {ami_id}")

        # Step 2: Launch new instance
        logger.info(f"Launching new instance in pool {command['target_pool_id']}...")
        new_instance = launch_instance(
            ami_id=ami_id,
            instance_type=old_instance['instance_type'],
            pool_id=command['target_pool_id'],
            target_mode=command['target_mode']
        )
        instance_launched_at = datetime.utcnow()
        logger.info(f"New instance launched: {new_instance['instance_id']}")

        # Step 3: Wait for new instance to be ready
        logger.info("Waiting for new instance to be ready...")
        wait_for_instance_ready(new_instance['instance_id'])
        instance_ready_at = datetime.utcnow()
        logger.info("New instance is ready")

        # Step 4: Handle old instance termination based on auto_terminate setting
        terminate_wait = command.get('terminate_wait_seconds', 0)
        old_terminated_at = None

        if terminate_wait > 0:
            logger.info(f"Auto-terminate ENABLED: waiting {terminate_wait}s before terminating old instance {old_instance['instance_id']}")
            time.sleep(terminate_wait)

            logger.info(f"Terminating old instance {old_instance['instance_id']}...")
            terminate_instance(old_instance['instance_id'])
            old_terminated_at = datetime.utcnow()
            logger.info(f"Old instance {old_instance['instance_id']} terminated")
        else:
            logger.info(f"Auto-terminate DISABLED: keeping old instance {old_instance['instance_id']} running")
            logger.info("User can manually terminate the old instance when ready")

        # Step 5: Report switch to server
        timing = {
            'initiated_at': switch_start_time.isoformat(),
            'ami_created_at': ami_created_at.isoformat(),
            'instance_launched_at': instance_launched_at.isoformat(),
            'instance_ready_at': instance_ready_at.isoformat()
        }

        # Only include old_terminated_at if we actually terminated it
        if old_terminated_at:
            timing['old_terminated_at'] = old_terminated_at.isoformat()

        report_switch_to_server(old_instance, new_instance, timing, command['id'])

        logger.info("✓ Switch completed successfully")
        return {'success': True, 'new_instance_id': new_instance['instance_id']}

    except Exception as e:
        logger.error(f"Switch failed: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}
```

---

## 📚 Additional Resources

- [Server API Documentation](./API_REFERENCE.md)
- [Replica Management Guide](./REPLICA_GUIDE.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)

---

**Last Updated:** 2025-11-23
**Agent Version:** 2.0.0
