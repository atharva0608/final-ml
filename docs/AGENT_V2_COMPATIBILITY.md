# Agent v2 Compatibility Fix

## Problem Overview

**Issue:** Agents from the agent-v2 repository were not appearing on the server after installation.

**Error:** The backend was rejecting agent registrations due to a missing required field (`mode`).

## Root Cause

The agent-v2 code (`spot_agent_production_v2_final.py`) was not sending the `mode` field in the registration payload, but the backend's `AgentRegistrationSchema` required it as a mandatory field.

### Agent-v2 Registration Payload

```python
registration_data = {
    'client_token': config.CLIENT_TOKEN,
    'hostname': config.HOSTNAME,
    'instance_id': instance_id,
    'instance_type': instance_type,
    'region': region,
    'az': az,
    'ami_id': ami_id,
    'agent_version': config.AGENT_VERSION,
    'logical_agent_id': self.logical_agent_id
    # ❌ Missing 'mode' field!
}
```

The agent-v2 code detects the instance mode (spot/ondemand) on line 933:
```python
current_mode, api_mode = InstanceMetadata.detect_instance_mode_dual()
```

But this value was never included in the `registration_data` dictionary.

### Backend Requirements (Before Fix)

```python
class AgentRegistrationSchema(Schema):
    # ... other fields ...
    mode = fields.Str(required=True, validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
    # ❌ Required field!
```

When agents tried to register, the backend validation failed with:
```
ValidationError: {'mode': ['Missing data for required field.']}
```

This caused the registration endpoint to return a `400 Bad Request`, preventing the agent from being registered.

## Solution Implemented

### 1. Made 'mode' Field Optional (backend/backend.py:254)

**Before:**
```python
mode = fields.Str(required=True, validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
```

**After:**
```python
mode = fields.Str(required=False, missing='unknown', validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
```

**Key Changes:**
- `required=False` - Field is now optional
- `missing='unknown'` - Defaults to 'unknown' if not provided
- Maintains validation for valid mode values

This ensures backward compatibility with agent-v2 while still supporting agents that send the mode field.

### 2. Added Comprehensive Logging (backend/backend.py:480-498)

Added detailed logging at multiple stages:

**Registration Attempt:**
```python
logger.info(f"Agent registration attempt from client {request.client_id}")
logger.debug(f"Registration data: {data}")
```

**Validation Result:**
```python
logger.info(f"Agent registration validated: logical_id={logical_agent_id}, instance_id={validated_data['instance_id']}, mode={validated_data['mode']}")
```

**Update vs Insert:**
```python
# For existing agents
logger.info(f"Updating existing agent: agent_id={agent_id}, logical_id={logical_agent_id}")

# For new agents
logger.info(f"Creating new agent: agent_id={agent_id}, logical_id={logical_agent_id}")
```

**Success:**
```python
logger.info(f"✓ Agent registered successfully: agent_id={agent_id}, logical_id={logical_agent_id}, instance_id={validated_data['instance_id']}, mode={validated_data['mode']}")
```

**Failure:**
```python
logger.warning(f"Agent registration validation failed: {e.messages}")
logger.error(f"Agent registration error: {e}", exc_info=True)
```

### 3. Enhanced Error Tracking

Updated system event logging to include client context:
```python
log_system_event('validation_error', 'warning',
                f"Agent registration validation failed: {e.messages}",
                request.client_id)
```

## Impact

**Before Fix:**
- Agent-v2 registrations failed with `400 Bad Request`
- Agents didn't appear in the server dashboard
- No clear error messages in logs
- Required manual debugging to identify the issue

**After Fix:**
- Agent-v2 registrations succeed with mode defaulting to 'unknown'
- Agents appear in the server dashboard immediately
- Comprehensive logging makes troubleshooting easy
- Backward compatible with all agent versions

## Testing

### Verify Agent Registration

1. **Check Backend Logs** (during agent startup):
```bash
sudo journalctl -u backend -f | grep "Agent registration"
```

Expected output:
```
Agent registration attempt from client <client_id>
Agent registration validated: logical_id=<logical_id>, instance_id=<instance_id>, mode=unknown
Creating new agent: agent_id=<agent_id>, logical_id=<logical_id>
✓ Agent registered successfully: agent_id=<agent_id>, logical_id=<logical_id>, instance_id=<instance_id>, mode=unknown
```

2. **Check Agent Dashboard**:
```
http://100.28.125.108/agents
```

The agent should appear in the list within 30 seconds of startup.

3. **Verify Agent Status via API**:
```bash
curl -X GET "http://100.28.125.108/api/client/<client_id>/agents" \
  -H "Authorization: Bearer YOUR_CLIENT_TOKEN"
```

Should return agent details including:
```json
{
  "agents": [
    {
      "id": "<agent_id>",
      "logical_agent_id": "<logical_id>",
      "status": "online",
      "current_mode": "unknown",
      // ... other fields
    }
  ]
}
```

## Mode Detection

Even though the mode defaults to 'unknown' during registration, it will be updated correctly through:

1. **Heartbeat Updates** - Agents send mode in heartbeat (if available)
2. **Manual Detection** - Backend can query AWS API to determine instance mode
3. **Pricing Reports** - Mode is inferred from spot price presence

The 'unknown' mode is temporary and will be resolved within the first few minutes of operation.

## Backward Compatibility

This fix maintains full backward compatibility:

| Agent Version | Mode Field | Registration Result |
|--------------|------------|---------------------|
| agent-v2 (old) | ❌ Not sent | ✅ Registers as 'unknown' |
| agent-v3+ (new) | ✅ Sent | ✅ Registers with correct mode |
| Older agents | ❌ Not sent | ✅ Registers as 'unknown' |

## Future Recommendations

### For Agent Developers

If you're developing a new agent or updating agent-v2, include the `mode` field in registration:

```python
registration_data = {
    'client_token': config.CLIENT_TOKEN,
    'hostname': config.HOSTNAME,
    'instance_id': instance_id,
    'instance_type': instance_type,
    'region': region,
    'az': az,
    'ami_id': ami_id,
    'mode': current_mode,  # ← Add this field
    'agent_version': config.AGENT_VERSION,
    'logical_agent_id': self.logical_agent_id
}
```

This ensures the mode is correctly set from the start, avoiding the need for backend inference.

### For Backend Developers

When adding new required fields to registration:
1. Always make new fields optional initially
2. Provide sensible default values using `missing=`
3. Add comprehensive logging for debugging
4. Document compatibility implications
5. Consider gradual rollout strategies

## Related Files

- `backend/backend.py` - Lines 244-257 (AgentRegistrationSchema)
- `backend/backend.py` - Lines 474-657 (register_agent endpoint)
- `/tmp/agent-v2/backend/spot_agent_production_v2_final.py` - Lines 918-972 (agent registration code)

## Debugging Tips

### Agent Not Showing Up?

1. **Check agent logs**:
```bash
tail -f /path/to/spot_optimizer_agent.log
```

Look for:
- Registration attempt
- Response from server (agent_id)
- Any error messages

2. **Check backend logs**:
```bash
sudo journalctl -u backend -f | grep -E "registration|agent"
```

Look for:
- Registration attempts
- Validation errors
- Success messages

3. **Check database**:
```sql
SELECT id, logical_agent_id, status, current_mode, last_heartbeat_at
FROM agents
WHERE client_id = '<your_client_id>'
ORDER BY created_at DESC
LIMIT 5;
```

4. **Check network connectivity**:
```bash
# From agent instance
curl -v http://100.28.125.108/api/health
```

Should return `200 OK`.

5. **Verify client token**:
```bash
curl -X GET "http://100.28.125.108/api/client/validate" \
  -H "Authorization: Bearer YOUR_CLIENT_TOKEN"
```

Should return:
```json
{
  "valid": true,
  "client_id": "<client_id>",
  "name": "<client_name>",
  "email": "<client_email>"
}
```

## Summary

This fix resolves the agent visibility issue by making the `mode` field optional with a sensible default, while adding comprehensive logging to make future troubleshooting easier. The solution is backward compatible and doesn't require changes to existing agent code.
