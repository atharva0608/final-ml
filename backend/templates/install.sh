#!/bin/bash
set -e

# ============================================
# Spot Optimizer Agent - One-Click Installer
# Version: 1.0.0
# ============================================

AGENT_VERSION="1.0.0"
AGENT_IMAGE="atharva608/spot-optimizer-agent:${AGENT_VERSION}"
NAMESPACE="spot-optimizer"

# --- Pre-flight Checks ---
echo "🔍 Running pre-flight checks..."

# Check for kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ Error: kubectl is required to install this agent."
    echo "   Please install kubectl: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

# Verify kubectl can reach a cluster
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Error: Cannot connect to Kubernetes cluster."
    echo "   Please ensure your kubeconfig is correctly configured."
    exit 1
fi

# --- Environment Variable Validation ---
if [ -z "$CLUSTER_ID" ] || [ -z "$API_KEY" ] || [ -z "$BACKEND_URL" ]; then
    echo "❌ Error: Missing required variables."
    echo "Usage: curl ... | CLUSTER_ID=... API_KEY=... BACKEND_URL=... sh"
    exit 1
fi

echo "✅ Pre-flight checks passed!"
echo ""
echo "🚀 Starting Spot Optimizer Agent Installation..."
echo "   Agent Version: $AGENT_VERSION"
echo "   Cluster ID:    $CLUSTER_ID"
echo "   Backend URL:   $BACKEND_URL"
echo ""

# --- 1. Setup Namespace ---
echo "📦 Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# --- 2. Create Secrets & Config ---
echo "🔐 Configuring secrets and config..."
kubectl create secret generic spot-agent-secret \
    --namespace $NAMESPACE \
    --from-literal=API_KEY="$API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap spot-agent-config \
    --namespace $NAMESPACE \
    --from-literal=BACKEND_URL="$BACKEND_URL" \
    --from-literal=BACKEND_WS_URL="$BACKEND_WS_URL" \
    --from-literal=CLUSTER_ID="$CLUSTER_ID" \
    --dry-run=client -o yaml | kubectl apply -f -

# --- 3. Deploy Agent ---
echo "🤖 Deploying Spot Optimizer Agent..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ServiceAccount
metadata:
  name: spot-agent-sa
  namespace: $NAMESPACE
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: spot-agent-role
rules:
  - apiGroups: ["", "apps", "batch", "extensions"]
    resources: ["nodes", "pods", "deployments", "replicasets", "daemonsets", "statefulsets", "jobs"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/eviction"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spot-agent-binding
subjects:
  - kind: ServiceAccount
    name: spot-agent-sa
    namespace: $NAMESPACE
roleRef:
  kind: ClusterRole
  name: spot-agent-role
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spot-agent
  namespace: $NAMESPACE
  labels:
    app: spot-agent
    version: "${AGENT_VERSION}"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spot-agent
  template:
    metadata:
      labels:
        app: spot-agent
        version: "${AGENT_VERSION}"
    spec:
      serviceAccountName: spot-agent-sa
      containers:
        - name: agent
          image: $AGENT_IMAGE
          imagePullPolicy: IfNotPresent
          env:
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: spot-agent-secret
                  key: API_KEY
            - name: BACKEND_URL
              valueFrom:
                configMapKeyRef:
                  name: spot-agent-config
                  key: BACKEND_URL
            - name: CLUSTER_ID
              valueFrom:
                configMapKeyRef:
                  name: spot-agent-config
                  key: CLUSTER_ID
            - name: BACKEND_WS_URL
              valueFrom:
                configMapKeyRef:
                  name: spot-agent-config
                  key: BACKEND_WS_URL
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "256Mi"
EOF

echo ""
echo "✅ Installation Complete!"
echo ""
echo "📊 Verify the agent is running:"
echo "   kubectl get pods -n $NAMESPACE"
echo ""
echo "📝 View agent logs:"
echo "   kubectl logs -n $NAMESPACE -l app=spot-agent -f"
echo ""
