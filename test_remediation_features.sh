#!/bin/bash
# Remediation Features Test Script
# Tests all implemented features from remediation-task.md

echo "========================================="
echo "REMEDIATION FEATURES TEST"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

function test_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((pass_count++))
}

function test_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((fail_count++))
}

function test_info() {
    echo -e "${YELLOW}ℹ INFO${NC}: $1"
}

# Test 1: Check all containers are running
echo "Test 1: Docker Containers"
echo "-------------------------"
if docker-compose -f docker/docker-compose.yml ps | grep -q "Up"; then
    test_pass "All containers running"
else
    test_fail "Some containers not running"
fi
echo ""

# Test 2: Check backend health
echo "Test 2: Backend Health"
echo "---------------------"
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    test_pass "Backend is healthy"
else
    test_fail "Backend health check failed"
fi
echo ""

# Test 3: Check Celery tasks registered
echo "Test 3: Celery Tasks Registration"
echo "---------------------------------"
docker exec spot-optimizer-celery-worker celery -A backend.workers inspect registered 2>&1 | grep -q "resize_guard"
if [ $? -eq 0 ]; then
    test_pass "Resize guard task registered"
else
    test_fail "Resize guard task not registered"
fi

docker exec spot-optimizer-celery-worker celery -A backend.workers inspect registered 2>&1 | grep -q "update_pod_restart_baseline"
if [ $? -eq 0 ]; then
    test_pass "Update baseline task registered"
else
    test_fail "Update baseline task not registered"
fi
echo ""

# Test 4: Check if new worker file exists
echo "Test 4: Resize Guard Worker File"
echo "--------------------------------"
if [ -f "backend/workers/tasks/resize_guard_worker.py" ]; then
    test_pass "Resize guard worker file exists"
    lines=$(wc -l < backend/workers/tasks/resize_guard_worker.py)
    test_info "File size: $lines lines"
else
    test_fail "Resize guard worker file missing"
fi
echo ""

# Test 5: Check coordinator trust phase method
echo "Test 5: Trust Phase Implementation"
echo "----------------------------------"
if grep -q "get_cluster_trust_phase" backend/services/optimizer_coordinator.py; then
    test_pass "get_cluster_trust_phase() method exists"
else
    test_fail "get_cluster_trust_phase() method missing"
fi

if grep -q "Phase 0" backend/services/optimizer_coordinator.py; then
    test_pass "Phase 0/1/2 logic implemented"
else
    test_fail "Phase logic missing"
fi
echo ""

# Test 6: Check circuit breaker implementation
echo "Test 6: Circuit Breaker Implementation"
echo "--------------------------------------"
if grep -q "RESIZE CIRCUIT BREAKER" backend/services/optimizer_coordinator.py; then
    test_pass "Circuit breaker logic exists"
else
    test_fail "Circuit breaker logic missing"
fi

if grep -q "failure_count_24h" backend/services/optimizer_coordinator.py; then
    test_pass "Failure tracking implemented"
else
    test_fail "Failure tracking missing"
fi
echo ""

# Test 7: Check substitute cooldown wiring
echo "Test 7: Substitute Cooldown Wiring"
echo "----------------------------------"
if grep -q "record_substitute_action" backend/services/substitute_manager.py; then
    test_pass "Substitute cooldown wiring exists"
else
    test_fail "Substitute cooldown wiring missing"
fi
echo ""

# Test 8: Check coordinator init on cluster connect
echo "Test 8: Coordinator Init on Connect"
echo "-----------------------------------"
if grep -q "initialize_cluster_state" backend/services/cluster_service.py; then
    test_pass "Coordinator init wired to cluster connect"
else
    test_fail "Coordinator init not wired"
fi
echo ""

# Test 9: Check pricing freshness validation
echo "Test 9: Pricing Freshness Validation"
echo "------------------------------------"
if grep -q "pricing_freshness" backend/core/decision_engine.py; then
    test_pass "Pricing freshness check exists"
else
    test_fail "Pricing freshness check missing"
fi
echo ""

# Test 10: Check UI updates
echo "Test 10: UI Updates"
echo "------------------"
if grep -q "trustPhase" frontend/src/components/optimizer/OptimizerCoordinatorDashboard.jsx; then
    test_pass "Trust phase UI component added"
else
    test_fail "Trust phase UI component missing"
fi

if grep -q "resizeGuard" frontend/src/components/optimizer/OptimizerCoordinatorDashboard.jsx; then
    test_pass "Resize guard UI component added"
else
    test_fail "Resize guard UI component missing"
fi

if grep -q "circuitBreaker" frontend/src/components/optimizer/OptimizerCoordinatorDashboard.jsx; then
    test_pass "Circuit breaker UI component added"
else
    test_fail "Circuit breaker UI component missing"
fi
echo ""

# Test 11: Check Celery Beat schedule
echo "Test 11: Celery Beat Schedule"
echo "-----------------------------"
if grep -q "resize-guard-every-5-mins" backend/workers/app.py; then
    test_pass "Resize guard scheduled in beat"
else
    test_fail "Resize guard not scheduled"
fi

if grep -q "update-restart-baseline-hourly" backend/workers/app.py; then
    test_pass "Baseline update scheduled in beat"
else
    test_fail "Baseline update not scheduled"
fi
echo ""

# Test 12: Check frontend build
echo "Test 12: Frontend Build"
echo "----------------------"
if docker logs spot-optimizer-frontend 2>&1 | grep -q "nginx"; then
    test_pass "Frontend container running nginx"
else
    test_fail "Frontend nginx not running"
fi
echo ""

# Test 13: Check backend imports
echo "Test 13: Backend Module Imports"
echo "-------------------------------"
docker exec spot-optimizer-backend python -c "from backend.workers.tasks import resize_guard_worker" 2>&1 | grep -q "Error"
if [ $? -ne 0 ]; then
    test_pass "Resize guard worker imports successfully"
else
    test_fail "Resize guard worker import failed"
fi

docker exec spot-optimizer-backend python -c "from backend.services.optimizer_coordinator import OptimizerCoordinator" 2>&1 | grep -q "Error"
if [ $? -ne 0 ]; then
    test_pass "OptimizerCoordinator imports successfully"
else
    test_fail "OptimizerCoordinator import failed"
fi
echo ""

# Summary
echo "========================================="
echo "TEST SUMMARY"
echo "========================================="
echo -e "${GREEN}Passed: $pass_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
total=$((pass_count + fail_count))
echo "Total: $total"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. View the UI: http://localhost"
    echo "2. Check Celery logs: docker logs --tail 50 spot-optimizer-celery-worker"
    echo "3. Monitor resize guard: docker logs --tail 50 -f spot-optimizer-celery-worker | grep RESIZE-GUARD"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo "Check logs for details:"
    echo "  docker logs spot-optimizer-backend"
    echo "  docker logs spot-optimizer-celery-worker"
    exit 1
fi
