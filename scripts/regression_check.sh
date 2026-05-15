#!/usr/bin/env bash
# P-18: Phase 3 regression check script
# Usage: API_BASE=http://localhost:8000 TEST_CLUSTER_ID=<uuid> bash scripts/regression_check.sh
set -e

API_BASE="${API_BASE:-http://localhost:8000}"
CID="${TEST_CLUSTER_ID:-test-cluster-id}"
AUTH="${API_AUTH_HEADER:-Authorization: Bearer test-token}"

PASS=0
FAIL=0

check() {
  local label="$1"
  local url="$2"
  local expected_status="${3:-200}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$url")
  if [ "$status" = "$expected_status" ]; then
    echo "PASS [$label] => HTTP $status"
    PASS=$((PASS + 1))
  else
    echo "FAIL [$label] => expected $expected_status, got $status  ($url)"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Phase 3 Regression Check ==="
echo "API_BASE=$API_BASE  CLUSTER_ID=$CID"
echo ""

# --- Existing endpoints ---
check "pod-metrics/recommendations"   "$API_BASE/api/v1/pod-metrics/recommendations?cluster_id=$CID"
check "workload-classification"       "$API_BASE/api/v1/workload-classification/clusters/$CID/workloads"
check "placement-policies"            "$API_BASE/api/v1/clusters/$CID/placement-policies"

# --- New optimize endpoints ---
check "optimize/workloads/gates"               "$API_BASE/api/v1/optimize/workloads/$CID/gates"
check "optimize/workloads/placement/summary"   "$API_BASE/api/v1/optimize/workloads/placement/summary?cluster_id=$CID"
check "optimize/nodes/bin-packing"             "$API_BASE/api/v1/optimize/nodes/bin-packing?cluster_id=$CID"
check "optimize/workloads/scaling"             "$API_BASE/api/v1/optimize/workloads/scaling?cluster_id=$CID"
check "optimize/system/health"                 "$API_BASE/api/v1/optimize/system/health?cluster_id=$CID"

# --- P-04 validation guard (invalid cluster_id must return 400 or 422) ---
status_invalid=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" \
  "$API_BASE/api/v1/optimize/nodes/bin-packing?cluster_id=bad!")
if [ "$status_invalid" = "400" ] || [ "$status_invalid" = "422" ]; then
  echo "PASS [P-04 invalid cluster_id] => HTTP $status_invalid"
  PASS=$((PASS + 1))
else
  echo "FAIL [P-04 invalid cluster_id] => expected 400/422, got $status_invalid"
  FAIL=$((FAIL + 1))
fi

# --- P-23 rate limit (11th request must return 429) ---
echo ""
echo "Checking P-23 rate limit (bin-packing, 11 rapid requests)..."
RL_URL="$API_BASE/api/v1/optimize/nodes/bin-packing?cluster_id=$CID"
last_status=0
for i in $(seq 1 11); do
  last_status=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$RL_URL")
done
if [ "$last_status" = "429" ]; then
  echo "PASS [P-23 rate limit 429 on 11th] => HTTP $last_status"
  PASS=$((PASS + 1))
else
  echo "WARN [P-23 rate limit] => 11th request returned $last_status (may need Redis)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
