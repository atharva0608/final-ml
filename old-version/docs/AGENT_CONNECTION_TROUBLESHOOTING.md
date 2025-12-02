# Agent Connection Troubleshooting Guide

## Overview

This guide helps diagnose and resolve connection errors between AWS Spot Optimizer agents and the central server.

## Common Connection Errors

### 1. Connection Error: Cannot Reach Server

**Error Message:**
```
ERROR - Connection error after 3 attempts: GET http://server-url/api/agents/.../heartbeat - [Errno 111] Connection refused
ERROR - Server URL configured as: http://server-url
ERROR - Verify server is running and CLIENT_TOKEN is valid
```

**Possible Causes:**
1. **Server is not running**
   - The backend server is down or not started
   - Solution: Start the backend server (`python backend/backend.py`)

2. **Wrong SERVER_URL configuration**
   - The `SPOT_OPTIMIZER_SERVER_URL` environment variable points to the wrong address
   - Solution: Verify the environment variable matches your server's actual URL

3. **Network/firewall blocking connection**
   - EC2 security groups blocking outbound traffic
   - Network ACLs preventing communication
   - Solution: Check AWS security group rules and ensure port is open

4. **DNS resolution failure**
   - Hostname cannot be resolved
   - Solution: Use IP address instead or verify DNS settings

### 2. HTTP Error 401: Invalid Client Token

**Error Message:**
```
ERROR - HTTP error 401: POST http://server-url/api/agents/register
ERROR - Response: {"error": "Invalid client token"}
ERROR - Authentication failed - check CLIENT_TOKEN configuration
ERROR - Current token: abc12345...xyz9
```

**Possible Causes:**
1. **Invalid or missing CLIENT_TOKEN**
   - The `SPOT_OPTIMIZER_CLIENT_TOKEN` environment variable is incorrect
   - Token doesn't exist in the database

**Solution:**
```bash
# 1. Check current token configuration
echo $SPOT_OPTIMIZER_CLIENT_TOKEN

# 2. Verify token exists in database
mysql -h DB_HOST -u DB_USER -p DB_NAME -e "SELECT id, name, is_active FROM clients WHERE client_token = 'YOUR_TOKEN';"

# 3. If token doesn't exist, create one:
# a. Generate new token
NEW_TOKEN=$(uuidgen)

# b. Insert into database
mysql -h DB_HOST -u DB_USER -p DB_NAME -e "INSERT INTO clients (id, name, email, client_token, is_active) VALUES (UUID(), 'My Company', 'admin@company.com', '$NEW_TOKEN', 1);"

# c. Update environment variable
export SPOT_OPTIMIZER_CLIENT_TOKEN=$NEW_TOKEN
```

### 3. HTTP Error 403: Client Account Not Active

**Error Message:**
```
ERROR - HTTP error 403: POST http://server-url/api/agents/.../heartbeat
ERROR - Response: {"error": "Client account is not active"}
ERROR - Authentication failed - check CLIENT_TOKEN configuration
```

**Possible Causes:**
1. **Client account is disabled**
   - The `is_active` flag is set to 0 in the database

**Solution:**
```bash
# Activate the client account
mysql -h DB_HOST -u DB_USER -p DB_NAME -e "UPDATE clients SET is_active = 1 WHERE client_token = 'YOUR_TOKEN';"
```

### 4. HTTP Error 404: Agent Not Found

**Error Message:**
```
ERROR - HTTP error 404: POST http://server-url/api/agents/.../heartbeat
ERROR - Response: {"error": "Agent not found"}
```

**Possible Causes:**
1. **Agent not registered**
   - Agent failed to register during startup
   - Agent ID doesn't exist for this client

2. **Wrong agent_id**
   - Using incorrect agent ID in requests

**Solution:**
- The agent automatically registers on startup
- Check registration logs for errors
- Verify agent exists: `SELECT * FROM agents WHERE logical_agent_id = 'YOUR_LOGICAL_ID';`

### 5. Request Timeout

**Error Message:**
```
WARNING - Request timeout (attempt 1/3): POST http://server-url/api/agents/.../heartbeat - retrying in 1s
WARNING - Request timeout (attempt 2/3): POST http://server-url/api/agents/.../heartbeat - retrying in 2s
ERROR - Request timeout after 3 attempts: POST http://server-url/api/agents/.../heartbeat - Read timed out.
```

**Possible Causes:**
1. **Server is overloaded**
   - High CPU/memory usage
   - Too many concurrent requests

2. **Slow network**
   - High latency between agent and server
   - Network congestion

3. **Database queries taking too long**
   - Missing indexes
   - Slow queries

**Solution:**
- Check server resource usage
- Optimize database queries
- Increase timeout value (default: 30s)
- Add database indexes if needed

## Configuration Checklist

### Agent Environment Variables

```bash
# Required
SPOT_OPTIMIZER_SERVER_URL=http://your-server:5000
SPOT_OPTIMIZER_CLIENT_TOKEN=your-client-token-here

# Optional
LOGICAL_AGENT_ID=agent-001  # Unique ID for agent persistence
AWS_REGION=us-east-1
HEARTBEAT_INTERVAL=30
PENDING_COMMANDS_CHECK_INTERVAL=15
```

### Server Environment Variables

```bash
# Database configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=spotuser
DB_PASSWORD=SpotUser2024!
DB_NAME=spot_optimizer

# Agent settings
AGENT_HEARTBEAT_TIMEOUT=120  # Seconds before agent marked as offline
```

### Verify Configuration

```bash
# Check agent can reach server
curl -I http://your-server:5000/health

# Test authentication
curl -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     http://your-server:5000/api/agents/test-id/config
```

## Diagnostic Tools

### 1. Startup Connectivity Check

The agent now performs a connectivity check on startup:

```
============================================================
AGENT STARTUP - SERVER CONNECTIVITY CHECK
============================================================
Server URL: http://server:5000
Client Token: abc12345...xyz9
✓ Server is reachable (health check passed)
============================================================
```

If this check fails, the agent will exit immediately with diagnostic information.

### 2. Enhanced Error Logging

All connection errors now include:
- Full URL being accessed
- HTTP method (GET, POST, etc.)
- Actual error message from the network layer
- Retry attempt information (if applicable)
- Authentication details (token preview)

Example:
```
2025-11-25 05:26:47 ERROR - Connection error after 3 attempts: POST http://server:5000/api/agents/abc-123/heartbeat - [Errno 111] Connection refused
2025-11-25 05:26:47 ERROR - Server URL configured as: http://server:5000
2025-11-25 05:26:47 ERROR - Verify server is running and CLIENT_TOKEN is valid
```

### 3. Retry Logic with Exponential Backoff

The agent automatically retries failed requests:
- **Attempt 1:** Immediate
- **Attempt 2:** Wait 1 second
- **Attempt 3:** Wait 2 seconds
- **Attempt 4:** Wait 4 seconds (final attempt)

This helps handle transient network issues automatically.

## Server-Side Debugging

### Check Agent Status

```sql
-- View all agents and their last heartbeat
SELECT
    id,
    logical_agent_id,
    status,
    instance_id,
    last_heartbeat_at,
    TIMESTAMPDIFF(SECOND, last_heartbeat_at, NOW()) as seconds_since_heartbeat
FROM agents
WHERE client_id = 'YOUR_CLIENT_ID'
ORDER BY last_heartbeat_at DESC;
```

### Check Authentication Logs

```sql
-- View system events for auth failures
SELECT * FROM system_events
WHERE event_type = 'auth_failed'
ORDER BY timestamp DESC
LIMIT 20;
```

### Check Server Logs

```bash
# View backend logs
tail -f /var/log/spot-optimizer/backend.log

# Filter for authentication errors
grep "Invalid client token" /var/log/spot-optimizer/backend.log

# Filter for specific agent
grep "agent-id-here" /var/log/spot-optimizer/backend.log
```

## AWS Security Group Configuration

### Inbound Rules (Server EC2 Instance)

| Type | Protocol | Port | Source | Description |
|------|----------|------|--------|-------------|
| HTTP | TCP | 5000 | 0.0.0.0/0 | Backend API (or restrict to VPC CIDR) |
| HTTPS | TCP | 443 | 0.0.0.0/0 | If using HTTPS |
| MySQL | TCP | 3306 | Server IP | Database (if separate) |

### Outbound Rules (Agent EC2 Instance)

| Type | Protocol | Port | Destination | Description |
|------|----------|------|-------------|-------------|
| HTTP | TCP | 5000 | Server IP/SG | Backend API |
| HTTPS | TCP | 443 | 0.0.0.0/0 | AWS APIs |
| All traffic | All | All | 0.0.0.0/0 | (Default, can be more restrictive) |

## Quick Fixes

### Fix 1: Restart Agent with Verbose Logging

```bash
# Stop agent
pkill -f spot_optimizer_agent.py

# Start with debug logging
export LOG_LEVEL=DEBUG
python agent/spot_optimizer_agent.py
```

### Fix 2: Verify Server is Running

```bash
# Check if backend is running
ps aux | grep backend.py

# Check if port is listening
netstat -tuln | grep 5000

# Test health endpoint
curl http://localhost:5000/health
```

### Fix 3: Reset Agent Registration

```bash
# Remove old agent registration
mysql -h DB_HOST -u DB_USER -p DB_NAME -e "DELETE FROM agents WHERE logical_agent_id = 'YOUR_LOGICAL_ID';"

# Restart agent to re-register
python agent/spot_optimizer_agent.py
```

### Fix 4: Check Database Connectivity

```bash
# Test database connection
mysql -h DB_HOST -u DB_USER -p DB_NAME -e "SELECT 1;"

# Check client exists
mysql -h DB_HOST -u DB_USER -p DB_NAME -e "SELECT * FROM clients WHERE client_token = 'YOUR_TOKEN';"
```

## Still Having Issues?

If you're still experiencing connection problems after trying the above solutions:

1. **Collect diagnostic information:**
   - Full agent logs from startup
   - Server logs during the connection attempt
   - Network configuration (security groups, NACLs)
   - Environment variables (sanitize sensitive values)

2. **Check the basics:**
   - Can you ping the server from the agent?
   - Can you curl the health endpoint?
   - Is the server process actually running?
   - Is the database accessible?

3. **Verify the authentication chain:**
   - Token exists in database
   - Token matches environment variable
   - Client is marked as active
   - Agent registered successfully

4. **Review recent changes:**
   - Database schema migrations
   - Server configuration changes
   - Network policy updates
   - AWS security group modifications

## Related Documentation

- [Token Authentication Troubleshooting](./TOKEN_AUTHENTICATION_TROUBLESHOOTING.md)
- [Agent Configuration Guide](./AGENT_CONFIGURATION.md)
- [Server Deployment Guide](./SERVER_DEPLOYMENT.md)

## Change Log

### v4.0.1 - 2025-11-25
- Added automatic retry logic with exponential backoff (3 attempts)
- Enhanced error logging with full URL and error details
- Added startup connectivity check with health endpoint test
- Improved authentication error messages with token preview
- Added diagnostic information for common failure scenarios
