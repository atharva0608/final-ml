#!/bin/bash
# Script to monitor agent pod status and logs

echo "=== Checking Agent Pod Status ==="
kubectl get pods -n spot-optimizer

echo ""
echo "=== Checking DaemonSet Status ==="
kubectl get daemonset -n spot-optimizer

echo ""
echo "=== Recent Pod Events ==="
kubectl get events -n spot-optimizer --sort-by='.lastTimestamp' | tail -10

# Get pod name if running
POD_NAME=$(kubectl get pods -n spot-optimizer -l app=spot-agent -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -n "$POD_NAME" ]; then
    echo ""
    echo "=== Pod Logs for $POD_NAME ==="
    kubectl logs "$POD_NAME" -n spot-optimizer --tail=50
fi
