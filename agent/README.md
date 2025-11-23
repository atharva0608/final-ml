# AWS Spot Optimizer - Agent v4.0

Complete agent backend that runs on AWS EC2 instances and communicates with the central server.

## Features

- ✅ Automatic registration with central server
- ✅ Heartbeat monitoring (every 30 seconds)
- ✅ Pricing data collection and reporting
- ✅ Command polling and execution
- ✅ Instance switching (spot ↔ on-demand)
- ✅ AWS interruption detection:
  - Rebalance recommendations (10-15 min warning)
  - Termination notices (2-min warning)
- ✅ Emergency replica creation
- ✅ Automatic failover handling
- ✅ Graceful shutdown

## Installation

### On AWS EC2 Instance

```bash
# 1. Clone repository or copy agent folder
cd /opt
sudo git clone https://github.com/your-repo/spot-optimizer.git
cd spot-optimizer/agent

# 2. Install dependencies
sudo pip3 install -r requirements.txt

# 3. Set environment variables
export CENTRAL_SERVER_URL="http://your-server:5000"
export CLIENT_TOKEN="your-client-token-here"

# Optional: Set if agent already registered
export AGENT_ID="your-agent-id"

# 4. Run agent
sudo python3 spot_agent.py
```

### As Systemd Service (Recommended)

```bash
# Create systemd service file
sudo nano /etc/systemd/system/spot-agent.service
```

Paste this configuration:

```ini
[Unit]
Description=AWS Spot Optimizer Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/spot-optimizer/agent
Environment="CENTRAL_SERVER_URL=http://your-server:5000"
Environment="CLIENT_TOKEN=your-client-token"
Environment="HEARTBEAT_INTERVAL=30"
ExecStart=/usr/bin/python3 /opt/spot-optimizer/agent/spot_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable spot-agent
sudo systemctl start spot-agent

# Check status
sudo systemctl status spot-agent

# View logs
sudo journalctl -u spot-agent -f
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CENTRAL_SERVER_URL` | Yes | `http://localhost:5000` | Central server URL |
| `CLIENT_TOKEN` | Yes | - | Client authentication token (get from central server) |
| `AGENT_ID` | No | - | Agent ID (auto-set after registration) |
| `HEARTBEAT_INTERVAL` | No | `30` | Heartbeat interval in seconds |

### Getting Client Token

1. Log into the central server web UI
2. Go to "Clients" page
3. Click on your client
4. Copy the client token
5. Set it as `CLIENT_TOKEN` environment variable

## How It Works

### Registration Flow

```
1. Agent starts → Fetches AWS metadata (instance ID, type, region, AZ)
2. Agent registers with central server → Receives agent_id
3. Server creates agent record in database
4. Agent is now ready to receive commands
```

### Heartbeat Loop (Every 30s)

```
1. Send heartbeat (status: online, instance_id, current_mode)
2. Every 5 heartbeats: Report pricing data
3. Check for pending commands from server
4. Execute any pending switch commands
```

### Interruption Monitoring (Every 5s)

```
1. Check AWS metadata for rebalance recommendation
   → If detected: Call /create-emergency-replica

2. Check AWS metadata for termination notice
   → If detected: Call /termination-imminent
   → Perform graceful shutdown
```

### Switch Execution Flow

```
1. Receive switch command from server (target: spot/ondemand, pool_id)
2. Create AMI of current instance (in production)
3. Launch new instance in target pool/mode
4. Transfer state and data
5. Update DNS/load balancer
6. Report switch completion to server
7. Terminate old instance after wait period
```

## AWS Metadata Endpoints Used

The agent uses AWS EC2 metadata service:

- **Instance Identity**: `http://169.254.169.254/latest/dynamic/instance-identity/document`
- **Instance ID**: `http://169.254.169.254/latest/meta-data/instance-id`
- **Instance Type**: `http://169.254.169.254/latest/meta-data/instance-type`
- **Availability Zone**: `http://169.254.169.254/latest/meta-data/placement/availability-zone`
- **Spot Termination**: `http://169.254.169.254/latest/meta-data/spot/termination-time`
- **Spot Action**: `http://169.254.169.254/latest/meta-data/spot/instance-action`
- **Rebalance Recommendation**: `http://169.254.169.254/latest/meta-data/events/recommendations/rebalance`

## Testing Locally (Without AWS)

The agent detects if it's running outside AWS and uses fallback values:

```bash
export CENTRAL_SERVER_URL="http://localhost:5000"
export CLIENT_TOKEN="your-token"
python3 spot_agent.py
```

It will create a fake instance ID like `local-yourhostname` for testing.

## Logs

The agent logs all activities:

- **INFO**: Normal operations (heartbeat, pricing reports, commands)
- **WARNING**: Rebalance recommendations, non-critical errors
- **CRITICAL**: Termination notices, failover events
- **ERROR**: Connection failures, command execution errors

Example log output:

```
2025-01-20 10:30:00 - SpotAgent - INFO - Initializing Spot Agent...
2025-01-20 10:30:01 - SpotAgent - INFO - Instance ID: i-1234567890abcdef0
2025-01-20 10:30:01 - SpotAgent - INFO - Instance Type: t3.medium
2025-01-20 10:30:01 - SpotAgent - INFO - Region: us-east-1, AZ: us-east-1a
2025-01-20 10:30:01 - SpotAgent - INFO - Mode: spot
2025-01-20 10:30:02 - SpotAgent - INFO - ✓ Agent registered successfully! Agent ID: uuid-here
2025-01-20 10:30:02 - SpotAgent - INFO - ✓ Agent started successfully!
```

## Troubleshooting

### Agent won't register

- **Check**: Is `CLIENT_TOKEN` set correctly?
- **Check**: Can agent reach central server? (`curl $CENTRAL_SERVER_URL/api/system-health`)
- **Check**: Is client active in central server database?

### Heartbeat failing

- **Check**: Network connectivity to central server
- **Check**: Agent ID is valid (check logs)
- **Check**: Central server is running

### Commands not executing

- **Check**: Agent is receiving heartbeat responses
- **Check**: Commands are being created in central server
- **Check**: Agent has permission to execute commands

### Interruption detection not working

- **Must be running on AWS EC2**: Metadata service only available on real EC2 instances
- **Check**: Instance has IMDSv2 enabled (for newer instances)
- **Test**: Manually trigger interruption via AWS console

## Production Checklist

- [ ] Agent installed on all EC2 instances
- [ ] Systemd service configured and enabled
- [ ] Environment variables set securely
- [ ] Logs being collected (CloudWatch Logs)
- [ ] Monitoring alerts configured
- [ ] IAM role has required permissions (EC2, pricing)
- [ ] Network security groups allow agent → server communication
- [ ] Tested failover scenarios in staging

## Security Notes

- Store `CLIENT_TOKEN` securely (AWS Secrets Manager recommended)
- Use IAM instance role instead of access keys
- Run agent as non-root user in production
- Encrypt communication with HTTPS (set `CENTRAL_SERVER_URL=https://...`)
- Rotate client tokens periodically

## Support

For issues or questions:
- Check logs: `sudo journalctl -u spot-agent -f`
- Central server health: `curl $CENTRAL_SERVER_URL/api/system-health`
- Agent status: `sudo systemctl status spot-agent`
