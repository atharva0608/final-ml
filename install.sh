#!/bin/bash
set -e

# --- Configuration ---
# ⚠️ REPLACE 'your-github-username' WITH YOUR ACTUAL USERNAME
REPO_URL="https://raw.githubusercontent.com/atharva0608/final-ml/main"
AGENT_IMAGE="atharva608/spot-optimizer-agent:latest" # Ensure this matches your DockerHub
NAMESPACE="spot-optimizer"

# --- 1. Validation ---
if [ -z "$CLUSTER_ID" ] || [ -z "$API_KEY" ] || [ -z "$BACKEND_URL" ]; then
    echo "❌ Error: Missing required variables."
    echo "Usage: curl ... | CLUSTER_ID=... API_KEY=... BACKEND_URL=... sh"
    exit 1
fi

echo "🚀 Starting Spot Optimizer Agent Installation..."
echo "📍 Cluster ID: $CLUSTER_ID"
echo "🔌 Backend:    $BACKEND_URL"

# --- 2. Setup Namespace ---
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# --- 3. Create Secrets & Config ---
echo "🔐 Configuring secrets..."
kubectl create secret generic spot-agent-secret \
    --namespace $NAMESPACE \
    --from-literal=API_KEY="$API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap spot-agent-config \
    --namespace $NAMESPACE \
    --from-literal=BACKEND_URL="$BACKEND_URL" \
    --from-literal=CLUSTER_ID="$CLUSTER_ID" \
    --dry-run=client -o yaml | kubectl apply -f -

# --- 4. Deploy Agent (Using files from your agent/ folder) ---
# We download the YAML directly from your repo to ensure it's always up to date
echo "📦 Fetching deployment manifest..."

# Note: We construct the manifest dynamically here to inject the image
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
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spot-agent
  template:
    metadata:
      labels:
        app: spot-agent
    spec:
      serviceAccountName: spot-agent-sa
      containers:
        - name: agent
          image: $AGENT_IMAGE
          imagePullPolicy: Always
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
EOF

echo "✅ Installation Complete! The agent should be running shortly."
