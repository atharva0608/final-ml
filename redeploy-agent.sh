#!/bin/bash
set -e

echo "🧹 Cleaning up old agent resources..."
kubectl delete configmap spot-agent-config -n spot-optimizer --ignore-not-found=true
kubectl delete daemonset spot-agent -n spot-optimizer --ignore-not-found=true
kubectl delete deployment spot-orchestrator -n spot-optimizer --ignore-not-found=true
kubectl delete clusterrole spot-agent-role --ignore-not-found=true
kubectl delete clusterrolebinding spot-agent-binding --ignore-not-found=true
kubectl delete serviceaccount spot-agent-sa -n spot-optimizer --ignore-not-found=true
kubectl delete secret spot-agent-secret -n spot-optimizer --ignore-not-found=true

echo "✅ Cleanup complete!"
echo ""
echo "📝 Now trigger agent installation from the UI:"
echo "   1. Go to your frontend"
echo "   2. Click on the cluster 'spot-demo-1'"
echo "   3. Click 'Activate Optimization' button"
echo ""
echo "   The agent will be deployed with the new image and configuration!"
echo ""
echo "🔍 To monitor the deployment, run:"
echo "   kubectl get pods -n spot-optimizer -w"
