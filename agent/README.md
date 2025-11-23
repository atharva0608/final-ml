# SpotGuard Agent v4.0.0 - Standalone Installation

This folder contains the SpotGuard agent v4.0.0 for client-side installation on AWS EC2 instances.

## 🚀 Quick Start

### Prerequisites
- AWS EC2 instance (spot or on-demand)
- Python 3.7+
- AWS credentials configured
- Network access to SpotGuard backend server

### Installation Steps

1. **Copy agent folder to your EC2 instance:**
   ```bash
   scp -r agent/ ubuntu@<your-instance-ip>:~/spotguard-agent/
   ssh ubuntu@<your-instance-ip>
   cd ~/spotguard-agent
   ```

2. **Install dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Create environment configuration:**
   ```bash
   nano .env
   ```

4. **Add required configuration:**
   ```env
   # REQUIRED: Server connection
   SPOT_OPTIMIZER_SERVER_URL=http://<backend-server-ip>:5000
   SPOT_OPTIMIZER_CLIENT_TOKEN=<your-client-token>

   # REQUIRED: Agent identity
   LOGICAL_AGENT_ID=<unique-agent-id>

   # AWS Configuration
   AWS_REGION=us-east-1

   # Optional: Timing configuration (seconds)
   HEARTBEAT_INTERVAL=30
   PENDING_COMMANDS_CHECK_INTERVAL=15
   CONFIG_REFRESH_INTERVAL=60
   PRICING_REPORT_INTERVAL=300
   TERMINATION_CHECK_INTERVAL=5
   REBALANCE_CHECK_INTERVAL=30
   CLEANUP_INTERVAL=3600

   # Optional: Switch configuration
   AUTO_TERMINATE_OLD_INSTANCE=true
   TERMINATE_WAIT_TIME=300
   CREATE_SNAPSHOT_ON_SWITCH=true

   # Optional: Cleanup configuration
   CLEANUP_SNAPSHOTS_OLDER_THAN_DAYS=7
   CLEANUP_AMIS_OLDER_THAN_DAYS=30
   ```

5. **Run the agent:**
   ```bash
   # Test run in foreground
   python3 spot_optimizer_agent.py

   # Or run in background
   nohup python3 spot_optimizer_agent.py > agent.log 2>&1 &
   ```

6. **Set up as systemd service (recommended):**
   ```bash
   sudo nano /etc/systemd/system/spotguard-agent.service
   ```

   Add:
   ```ini
   [Unit]
   Description=SpotGuard Agent v4.0.0
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/spotguard-agent
   Environment="PATH=/usr/local/bin:/usr/bin:/bin"
   ExecStart=/usr/bin/python3 /home/ubuntu/spotguard-agent/spot_optimizer_agent.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable spotguard-agent
   sudo systemctl start spotguard-agent
   sudo systemctl status spotguard-agent
   ```

## 📋 Configuration Options

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SPOT_OPTIMIZER_SERVER_URL` | Backend server URL | `http://100.28.125.108:5000` |
| `SPOT_OPTIMIZER_CLIENT_TOKEN` | Client authentication token | `your-secret-token-here` |
| `LOGICAL_AGENT_ID` | Unique agent identifier | `prod-web-agent-1` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for instance |
| `HEARTBEAT_INTERVAL` | `30` | Heartbeat interval (seconds) |
| `PENDING_COMMANDS_CHECK_INTERVAL` | `15` | Command polling interval (seconds) |
| `PRICING_REPORT_INTERVAL` | `300` | Pricing report interval (seconds) |
| `TERMINATION_CHECK_INTERVAL` | `5` | Check for termination notices (seconds) |
| `REBALANCE_CHECK_INTERVAL` | `30` | Check for rebalance signals (seconds) |
| `CLEANUP_INTERVAL` | `3600` | Cleanup old resources (seconds) |
| `TERMINATE_WAIT_TIME` | `300` | Wait time before terminating old instance (seconds) |
| `CLEANUP_SNAPSHOTS_OLDER_THAN_DAYS` | `7` | Delete snapshots older than N days |
| `CLEANUP_AMIS_OLDER_THAN_DAYS` | `30` | Delete AMIs older than N days |

## 🔧 Agent Features

### Automatic Operations
- **Heartbeat**: Sends instance status every 30 seconds
- **Pricing Reports**: Collects and reports spot pricing every 5 minutes
- **Command Execution**: Polls for switch commands every 15 seconds
- **Termination Detection**: Monitors for AWS spot termination notices (2-minute warning)
- **Rebalance Detection**: Monitors for EC2 rebalance recommendations
- **Replica Management**: Launches and manages replica instances
- **Cleanup**: Removes old snapshots and AMIs hourly

### Manual Operations
All operations are controlled from the SpotGuard dashboard:
- Switch between spot and on-demand modes
- Switch between availability zones
- Enable/disable auto-termination
- Enable/disable manual replica mode
- View pricing history and switch history

## 🔍 Monitoring

### Check Agent Status
```bash
# View logs
tail -f ~/spotguard-agent/spot_optimizer_agent.log

# Or if using systemd
sudo journalctl -u spotguard-agent -f
```

### Verify Agent Registration
Agent logs should show:
```
Agent registered as agent: <agent-id>
Agent started - ID: <agent-id>
Instance: i-xxxxx (t3.medium)
Version: 4.0.0
```

### Monitor Operations
Look for these log messages:
- `Heartbeat sent successfully`
- `Pricing report sent: X pools`
- `Found N pending command(s)`
- `Switch completed: i-xxxxx -> i-yyyyy`
- `Replica created: replica-id`

## 🚨 Troubleshooting

### Agent not registering
**Problem**: `Failed to register agent`

**Solutions**:
1. Check SERVER_URL is accessible: `curl http://<server-url>/health`
2. Verify CLIENT_TOKEN is correct
3. Check network connectivity and firewall rules
4. Ensure backend server is running

### Pricing reports failing
**Problem**: `Pricing report error: Failed to get spot prices`

**Solutions**:
1. Verify AWS credentials: `aws ec2 describe-spot-price-history --max-results 1`
2. Check IAM role has `ec2:DescribeSpotPriceHistory` permission
3. Verify AWS_REGION is correct

### Switch commands not executing
**Problem**: Agent sees commands but doesn't execute

**Solutions**:
1. Check agent logs for error messages
2. Verify IAM role has EC2 permissions:
   - `ec2:RunInstances`
   - `ec2:TerminateInstances`
   - `ec2:CreateImage`
   - `ec2:DescribeInstances`
3. Check instance metadata service is accessible:
   ```bash
   TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
   curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id
   ```

### Old instance not terminating
**Problem**: After switch, old instance stays running

**Expected Behavior**: This is controlled by the "Auto-Terminate" setting:
- **ON**: Old instance terminates after wait period (default 5 minutes)
- **OFF**: Old instance stays running for manual cleanup

**Solutions**:
1. Check agent config in dashboard: Settings > Agent Configuration
2. Review agent logs for termination logic
3. Backend sends `terminate_wait_seconds=0` when auto-terminate is OFF

## 📖 Additional Documentation

### Agent Architecture
The agent consists of 8 background worker threads:
1. **Heartbeat Worker**: Sends instance status to backend
2. **Pending Commands Worker**: Polls for and executes switch commands
3. **Replica Polling Worker**: Launches EC2 instances for pending replicas
4. **Config Refresh Worker**: Updates agent configuration from backend
5. **Pricing Report Worker**: Collects and reports spot pricing
6. **Termination Check Worker**: Monitors for spot termination notices
7. **Rebalance Check Worker**: Monitors for rebalance recommendations
8. **Cleanup Worker**: Removes old snapshots and AMIs

### API Endpoints Used
The agent communicates with these backend endpoints:
- `POST /api/agents/register` - Register agent with backend
- `POST /api/agents/<id>/heartbeat` - Send heartbeat status
- `POST /api/agents/<id>/pricing-report` - Report pricing data
- `GET /api/agents/<id>/config` - Get agent configuration
- `GET /api/agents/<id>/pending-commands` - Poll for commands
- `POST /api/agents/<id>/switch-report` - Report switch completion
- `POST /api/agents/<id>/termination-imminent` - Report termination notice
- `POST /api/agents/<id>/rebalance-recommendation` - Report rebalance signal
- `GET /api/agents/<id>/replicas?status=launching` - Get pending replicas
- `PUT /api/agents/<id>/replicas/<replica_id>` - Update replica instance ID
- `POST /api/agents/<id>/replicas/<replica_id>/status` - Update replica status

### IAM Permissions Required
The EC2 instance needs an IAM role with these permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeSnapshots",
        "ec2:DescribeSpotPriceHistory",
        "ec2:DescribeAvailabilityZones",
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:CreateImage",
        "ec2:DeregisterImage",
        "ec2:DeleteSnapshot",
        "ec2:CreateTags",
        "pricing:GetProducts"
      ],
      "Resource": "*"
    }
  ]
}
```

## 🆘 Support

For issues or questions:
1. Check agent logs for error messages
2. Review backend server logs
3. Verify network connectivity between agent and backend
4. Check AWS IAM permissions
5. Ensure AWS instance metadata service is accessible

## 📝 Version History

### v4.0.0 (Current)
- Full backend integration with all API endpoints
- Dual mode verification (metadata + API)
- Priority-based command execution
- Fast switching mode (under 2 minutes)
- Graceful shutdown with cleanup
- Automatic replica management
- Emergency failover for termination notices
- Comprehensive error handling and logging

### Known Compatibility
- Backend API v2025-11-23 or later required
- Python 3.7+ required
- boto3 latest version recommended
