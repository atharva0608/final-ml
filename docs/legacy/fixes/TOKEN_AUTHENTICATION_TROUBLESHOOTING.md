# Token Authentication Troubleshooting Guide

## Problem Overview

**Error:** `HTTP error 401: {"error":"Invalid client token"}`

This error occurs when:
1. The agent's token doesn't match what's in the database
2. The client account is inactive
3. The token has encoding/whitespace issues
4. The client doesn't exist in the database

## Quick Diagnosis

### Step 1: Run the Debug Script

On your central server:
```bash
cd /home/user/final-ml
chmod +x scripts/debug_token.sh
./scripts/debug_token.sh
```

This will show:
- All clients and their token previews
- Inactive clients
- Recent authentication failures
- Agent status and last heartbeat

### Step 2: Check Agent Configuration

On your agent instance:
```bash
# Check what token the agent is using
cat ~/.env | grep SPOT_OPTIMIZER_CLIENT_TOKEN

# Or if using systemd
sudo systemctl cat spot-optimizer-agent | grep CLIENT_TOKEN
```

### Step 3: Check Backend Logs

On your central server:
```bash
# Real-time logs
sudo journalctl -u backend -f | grep -E "token|auth|401"

# Last 50 auth-related entries
sudo journalctl -u backend -n 50 | grep -E "token|auth|401"
```

Look for log entries like:
```
Invalid client token attempt - token: 12345678...9abc, endpoint: /api/agents/.../heartbeat
```

## Common Issues and Solutions

### Issue 1: Client Account is Inactive

**Symptoms:**
- Agent registered successfully initially
- Now getting 401 errors
- Backend logs show: "Inactive client attempted access"

**Solution:**
```sql
-- Connect to MySQL
mysql -u root -p spot_optimizer

-- Check client status
SELECT id, name, is_active, status FROM clients;

-- Activate the client
UPDATE clients
SET is_active = TRUE, status = 'active'
WHERE id = '<your_client_id>';

-- Verify
SELECT id, name, is_active, status FROM clients;
```

### Issue 2: Token Mismatch

**Symptoms:**
- Agent has a token but it's not in the database
- Backend logs show: "Invalid client token attempt"

**Cause:** Token in agent config doesn't match database

**Solution:**

**Option A: Update Agent with Correct Token**
```bash
# On agent instance
# Get the correct token from database first
# Then update agent config

# If using .env file:
vim ~/.env
# Change SPOT_OPTIMIZER_CLIENT_TOKEN to correct value

# If using systemd:
sudo vim /etc/systemd/system/spot-optimizer-agent.service
# Update Environment=SPOT_OPTIMIZER_CLIENT_TOKEN=...

# Restart agent
sudo systemctl restart spot-optimizer-agent
```

**Option B: Update Database with Agent's Token**
```sql
-- Get token from agent config first
-- Then update database

mysql -u root -p spot_optimizer

UPDATE clients
SET client_token = '<token_from_agent>'
WHERE id = '<your_client_id>';
```

### Issue 3: Whitespace/Encoding Issues

**Symptoms:**
- Token looks correct but still fails
- Token has invisible characters

**Solution:**

The enhanced backend now automatically strips whitespace, but if you still have issues:

```bash
# On agent instance, check for hidden characters
cat ~/.env | grep SPOT_OPTIMIZER_CLIENT_TOKEN | od -c

# Remove any whitespace/newlines
# Edit the file and ensure token is on single line with no spaces
```

### Issue 4: Client Doesn't Exist

**Symptoms:**
- Backend logs show: "Invalid client token attempt"
- Client not found in database

**Solution:**

Create a new client:
```sql
mysql -u root -p spot_optimizer

-- Generate a new UUID for client_token (or use existing one)
INSERT INTO clients (id, name, email, client_token, is_active, status)
VALUES (
    UUID(),
    'Your Company Name',
    'your@email.com',
    'your-secure-token-here',  -- Use the token from agent config
    TRUE,
    'active'
);

-- Get the client_id
SELECT id, name, client_token FROM clients ORDER BY created_at DESC LIMIT 1;
```

### Issue 5: Agent Registered but Token Invalid

**Symptoms:**
- Agent successfully registered (has agent_id)
- But subsequent heartbeats fail with 401
- This is YOUR current issue!

**Cause:**
The token used for registration worked, but something changed:
1. Client was deactivated after registration
2. Token in agent config changed
3. Database was reset/updated

**Solution:**

```sql
-- Check if client exists and is active
mysql -u root -p spot_optimizer

-- Find the client that owns the agent
SELECT
    c.id as client_id,
    c.name,
    c.is_active,
    c.status,
    CONCAT(LEFT(c.client_token, 8), '...', RIGHT(c.client_token, 4)) as token_preview,
    a.id as agent_id,
    a.logical_agent_id,
    a.status as agent_status
FROM agents a
JOIN clients c ON a.client_id = c.id
WHERE a.id = '3736b65f-0a64-4d1c-9bc1-a6f071ae9d38';

-- If client is inactive:
UPDATE clients
SET is_active = TRUE, status = 'active'
WHERE id = (SELECT client_id FROM agents WHERE id = '3736b65f-0a64-4d1c-9bc1-a6f071ae9d38');

-- Verify
SELECT c.is_active, c.status
FROM clients c
JOIN agents a ON c.id = a.client_id
WHERE a.id = '3736b65f-0a64-4d1c-9bc1-a6f071ae9d38';
```

## Enhanced Logging (v5.2)

The backend now includes comprehensive token validation logging:

**Success:**
```
Token validated - client: Company Name, endpoint: /api/agents/.../heartbeat
```

**Missing Token:**
```
Missing client token - endpoint: /api/agents/.../heartbeat
```

**Invalid Token:**
```
Invalid client token attempt - token: 12345678...9abc, endpoint: /api/agents/.../heartbeat
```

**Inactive Client:**
```
Inactive client attempted access - client_id: abc-123, endpoint: /api/agents/.../heartbeat
```

## Testing Token Authentication

### Test 1: Validate Token Directly

```bash
curl -X GET "http://100.28.125.108/api/client/validate" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected Response (Success):**
```json
{
  "valid": true,
  "client_id": "abc-123-...",
  "name": "Your Company",
  "email": "your@email.com"
}
```

**Expected Response (Invalid):**
```json
{
  "valid": false,
  "error": "Invalid token"
}
```

**Expected Response (Inactive):**
```json
{
  "valid": false,
  "error": "Client account is not active"
}
```

### Test 2: Test Agent Heartbeat

```bash
curl -X POST "http://100.28.125.108/api/agents/YOUR_AGENT_ID/heartbeat" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"status": "online"}'
```

**Expected Response (Success):**
```json
{
  "success": true,
  "message": "Heartbeat received"
}
```

**Expected Response (Invalid Token):**
```json
{
  "error": "Invalid client token"
}
```

### Test 3: Check Database Directly

```sql
-- Verify token matches
mysql -u root -p spot_optimizer

-- Get client by token (use actual token)
SELECT id, name, email, is_active, status
FROM clients
WHERE client_token = 'YOUR_TOKEN_HERE';

-- Should return one row with is_active = 1
```

## Prevention Best Practices

### 1. Store Tokens Securely

**Good:**
```bash
# Use environment variables
export SPOT_OPTIMIZER_CLIENT_TOKEN="your-token"

# Or systemd environment files
sudo vim /etc/systemd/system/spot-optimizer-agent.service.d/override.conf
[Service]
Environment="SPOT_OPTIMIZER_CLIENT_TOKEN=your-token"
```

**Bad:**
```bash
# Don't hardcode in scripts
CLIENT_TOKEN="your-token"  # ❌ Can be exposed in logs
```

### 2. Monitor Authentication Failures

Set up alerting for authentication failures:
```sql
-- Query for recent auth failures
SELECT COUNT(*) as failure_count
FROM system_events
WHERE event_type = 'auth_failed'
  AND created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR);
```

### 3. Regular Token Rotation

Rotate tokens periodically for security:
```sql
-- Generate new token
SET @new_token = UUID();

-- Update client
UPDATE clients
SET client_token = @new_token
WHERE id = '<client_id>';

-- Display new token (copy this to agent config)
SELECT @new_token;
```

Then update agent configuration with new token and restart.

### 4. Document Your Tokens

Keep a secure record of:
- Client ID
- Client name
- Token (securely encrypted)
- Which agents use this token
- Date token was created/last rotated

## Your Specific Issue - Quick Fix

Based on your logs showing agent_id `3736b65f-0a64-4d1c-9bc1-a6f071ae9d38`:

```bash
# On central server
mysql -u root -p spot_optimizer

# Find and fix the issue
SELECT
    c.id,
    c.name,
    c.is_active,
    c.status,
    CONCAT(LEFT(c.client_token, 8), '...')  as token
FROM clients c
JOIN agents a ON c.id = a.client_id
WHERE a.id = '3736b65f-0a64-4d1c-9bc1-a6f071ae9d38';

# If is_active = 0, activate it:
UPDATE clients c
JOIN agents a ON c.id = a.client_id
SET c.is_active = TRUE, c.status = 'active'
WHERE a.id = '3736b65f-0a64-4d1c-9bc1-a6f071ae9d38';

# Verify
SELECT c.is_active, c.status
FROM clients c
JOIN agents a ON c.id = a.client_id
WHERE a.id = '3736b65f-0a64-4d1c-9bc1-a6f071ae9d38';
```

Then on your agent instance:
```bash
# Restart the agent to retry
sudo systemctl restart spot-optimizer-agent

# Watch logs
sudo journalctl -u spot-optimizer-agent -f
```

On central server, watch for successful authentication:
```bash
sudo journalctl -u backend -f | grep "3736b65f-0a64-4d1c-9bc1-a6f071ae9d38"
```

You should see:
```
Token validated - client: <name>, endpoint: /api/agents/3736b65f-0a64-4d1c-9bc1-a6f071ae9d38/heartbeat
```

## Related Files

- `backend/backend.py` - Lines 291-338 (require_client_token decorator)
- `scripts/debug_token.sh` - Automated debugging script
- `database/schema.sql` - Lines 32-65 (clients table)

## Summary

The enhanced token validation now includes:
- ✅ Whitespace stripping
- ✅ Comprehensive logging with token previews
- ✅ Separate error messages for invalid vs inactive
- ✅ Debug script for quick diagnosis
- ✅ Detailed troubleshooting documentation

Most 401 errors are caused by inactive clients or token mismatches. Use the debug script and follow the quick fix steps above to resolve your specific issue.
