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

## 📚 Additional Resources

- [Server API Documentation](./API_REFERENCE.md)
- [Replica Management Guide](./REPLICA_GUIDE.md)
- [Troubleshooting Guide](./TROUBLESHOOTING.md)

---

**Last Updated:** 2025-11-23
**Agent Version:** 2.0.0
