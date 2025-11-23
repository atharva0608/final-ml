#!/bin/bash
# ============================================================================
# Token Authentication Debugging Script
# ============================================================================
# This script helps debug "Invalid client token" errors
# Run this on your central server to diagnose token issues
# ============================================================================

set -e

echo "======================================================================"
echo "Token Authentication Debug Tool"
echo "======================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're running as root or can use sudo
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

echo "Step 1: Checking MySQL connection..."
if ! command -v mysql &> /dev/null; then
    echo -e "${RED}✗ MySQL client not found${NC}"
    exit 1
fi

# Get MySQL credentials
echo ""
echo "Enter MySQL root password when prompted..."
echo ""

echo "Step 2: Listing all clients in database..."
echo "----------------------------------------------------------------------"
mysql -u root -p spot_optimizer -e "
SELECT
    id,
    name,
    email,
    CONCAT(LEFT(client_token, 8), '...', RIGHT(client_token, 4)) as token_preview,
    is_active,
    status,
    created_at
FROM clients
ORDER BY created_at DESC;
"

echo ""
echo "Step 3: Checking for inactive clients..."
echo "----------------------------------------------------------------------"
INACTIVE=$(mysql -u root -p spot_optimizer -N -e "
SELECT COUNT(*) FROM clients WHERE is_active = FALSE;
")

if [ "$INACTIVE" -gt 0 ]; then
    echo -e "${RED}⚠ Found $INACTIVE inactive client(s)${NC}"
    echo ""
    echo "Inactive clients:"
    mysql -u root -p spot_optimizer -e "
    SELECT id, name, email, status
    FROM clients
    WHERE is_active = FALSE;
    "
    echo ""
    echo "To activate a client, run:"
    echo "  UPDATE clients SET is_active = TRUE, status = 'active' WHERE id = '<client_id>';"
else
    echo -e "${GREEN}✓ All clients are active${NC}"
fi

echo ""
echo "Step 4: Checking recent authentication failures..."
echo "----------------------------------------------------------------------"
mysql -u root -p spot_optimizer -e "
SELECT
    created_at,
    event_type,
    severity,
    message,
    client_id,
    agent_id
FROM system_events
WHERE event_type = 'auth_failed'
ORDER BY created_at DESC
LIMIT 10;
"

echo ""
echo "Step 5: Checking agents and their last heartbeat..."
echo "----------------------------------------------------------------------"
mysql -u root -p spot_optimizer -e "
SELECT
    a.id,
    a.logical_agent_id,
    a.hostname,
    a.status,
    a.last_heartbeat_at,
    TIMESTAMPDIFF(SECOND, a.last_heartbeat_at, NOW()) as seconds_since_heartbeat,
    c.name as client_name
FROM agents a
JOIN clients c ON a.client_id = c.id
ORDER BY a.last_heartbeat_at DESC
LIMIT 10;
"

echo ""
echo "======================================================================"
echo "Manual Token Testing"
echo "======================================================================"
echo ""
echo "To test a specific token, you can use curl:"
echo ""
echo "1. Test token validation endpoint:"
echo "   curl -X GET 'http://localhost:5000/api/client/validate' \\"
echo "     -H 'Authorization: Bearer YOUR_TOKEN_HERE'"
echo ""
echo "2. Test agent registration:"
echo "   curl -X POST 'http://localhost:5000/api/agents/register' \\"
echo "     -H 'Authorization: Bearer YOUR_TOKEN_HERE' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"logical_agent_id\":\"test\",\"instance_id\":\"i-test\",\"instance_type\":\"t3.medium\",\"region\":\"us-east-1\",\"az\":\"us-east-1a\"}'"
echo ""
echo "======================================================================"
echo "Backend Logs"
echo "======================================================================"
echo ""
echo "To see real-time backend logs with token validation:"
echo "  ${SUDO} journalctl -u backend -f | grep -E 'token|auth'"
echo ""
echo "To see last 50 authentication-related log entries:"
echo "  ${SUDO} journalctl -u backend -n 50 | grep -E 'token|auth|401'"
echo ""
echo "======================================================================"
echo ""
