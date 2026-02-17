#!/bin/bash

# Test Real API Endpoints
# Run this script after restarting the backend to verify all implementations

BASE_URL="http://localhost:8000/api/v1"
AUTH_TOKEN="your-test-token-here"  # Replace with actual token

echo "🧪 Testing Real API Implementations"
echo "===================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Cluster Utilization
echo -e "${YELLOW}Test 1: Cluster Utilization${NC}"
curl -s "${BASE_URL}/metrics/cluster/test-cluster/utilization" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" | jq '.' > /tmp/test1.json

if [ -s /tmp/test1.json ]; then
    echo -e "${GREEN}✓ Endpoint responded${NC}"
    echo "Response:"
    cat /tmp/test1.json | jq '.cpu_history[0:3], .cpu_current'
else
    echo -e "${RED}✗ Endpoint failed${NC}"
fi
echo ""

# Test 2: Node Groups
echo -e "${YELLOW}Test 2: Node Groups${NC}"
curl -s "${BASE_URL}/metrics/cluster/test-cluster/nodegroups" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" | jq '.' > /tmp/test2.json

if [ -s /tmp/test2.json ]; then
    echo -e "${GREEN}✓ Endpoint responded${NC}"
    echo "Response:"
    cat /tmp/test2.json | jq '.[0]'
else
    echo -e "${RED}✗ Endpoint failed${NC}"
fi
echo ""

# Test 3: Health Timeline
echo -e "${YELLOW}Test 3: Health Timeline${NC}"
curl -s "${BASE_URL}/metrics/cluster/test-cluster/health-timeline" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" | jq '.' > /tmp/test3.json

if [ -s /tmp/test3.json ]; then
    echo -e "${GREEN}✓ Endpoint responded${NC}"
    echo "Response:"
    cat /tmp/test3.json | jq '.[0:2]'
else
    echo -e "${RED}✗ Endpoint failed${NC}"
fi
echo ""

# Test 4: Realized Savings
echo -e "${YELLOW}Test 4: Realized Savings${NC}"
curl -s "${BASE_URL}/optimization/savings/realized" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" | jq '.' > /tmp/test4.json

if [ -s /tmp/test4.json ]; then
    echo -e "${GREEN}✓ Endpoint responded${NC}"
    echo "Response:"
    cat /tmp/test4.json | jq '.total_savings, .this_month'
else
    echo -e "${RED}✗ Endpoint failed${NC}"
fi
echo ""

# Test 5: Batch Apply (dry run with invalid IDs to test logic)
echo -e "${YELLOW}Test 5: Batch Apply Right-Sizing${NC}"
curl -s -X POST "${BASE_URL}/optimization/rightsizing/batch-apply" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "instance_ids": ["i-test-invalid"],
    "cluster_id": "test-cluster"
  }' | jq '.' > /tmp/test5.json

if [ -s /tmp/test5.json ]; then
    echo -e "${GREEN}✓ Endpoint responded${NC}"
    echo "Response:"
    cat /tmp/test5.json
else
    echo -e "${RED}✗ Endpoint failed${NC}"
fi
echo ""

# Summary
echo "===================================="
echo -e "${GREEN}Testing Complete!${NC}"
echo ""
echo "Check /tmp/test*.json files for full responses"
echo ""
echo "Next steps:"
echo "1. Update AUTH_TOKEN in this script with a real token"
echo "2. Replace 'test-cluster' with actual cluster ID"
echo "3. Run: chmod +x test_real_apis.sh && ./test_real_apis.sh"
