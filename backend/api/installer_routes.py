"""
Installer Routes - Dynamic Script Generation

This module provides a public endpoint that generates the installation
script dynamically with pre-filled configuration values.
"""

import os
from pathlib import Path
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

router = APIRouter(prefix="/installer", tags=["installer"])

# Path to the install.sh template
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "install.sh"


@router.get("/linux", response_class=PlainTextResponse)
async def get_linux_installer(
    request: Request,
    cluster_id: str = Query(..., description="The cluster ID to configure"),
    api_key: str = Query(..., description="The API key for agent authentication")
):
    """
    Generate a Linux installation script with pre-filled configuration.
    
    This endpoint returns a shell script that can be piped directly to bash:
    
        curl -sL "https://your-api.com/api/installer/linux?cluster_id=...&api_key=..." | bash
    
    The script is dynamically generated with the correct backend URL and credentials.
    """
    
    # Read the template
    try:
        template_content = TEMPLATE_PATH.read_text()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Install script template not found")
    
    # Get the backend URL from the request
    # This automatically works with ngrok, localhost, or production
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:8000"))
    backend_url = f"{scheme}://{host}"
    
    # Convert to WebSocket URL for agent connection
    ws_url = backend_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_endpoint = f"{ws_url}/ws/cluster/{cluster_id}"
    
    # Generate the dynamic script
    # We inject ALL required values as environment variables at the top of the script
    dynamic_header = f'''#!/bin/bash
set -e

# ============================================
# Spot Optimizer Agent - Dynamic Installer
# Generated for Cluster: {cluster_id}
# ============================================

# --- Static Configuration ---
NAMESPACE="spot-optimizer"
AGENT_VERSION="v1.0.0"
AGENT_IMAGE="atharva0608/spot-optimizer-agent:${{AGENT_VERSION}}"

# --- Dynamic Configuration (Auto-generated) ---
CLUSTER_ID="{cluster_id}"
API_KEY="{api_key}"
BACKEND_URL="{backend_url}"
BACKEND_WS_URL="{ws_endpoint}"

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

echo "✅ Pre-flight checks passed!"
echo ""
echo "🚀 Starting Spot Optimizer Agent Installation..."
echo "   Agent Version: $AGENT_VERSION"
echo "   Cluster ID:    $CLUSTER_ID"
echo "   Backend URL:   $BACKEND_URL"
echo "   WebSocket URL: $BACKEND_WS_URL"
echo ""

# --- 1. Setup Namespace ---
echo "📦 Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# --- 2. Create Secrets & Config ---
echo "🔐 Configuring secrets and config..."
kubectl create secret generic spot-agent-secret \\
    --namespace $NAMESPACE \\
    --from-literal=API_KEY="$API_KEY" \\
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap spot-agent-config \\
    --namespace $NAMESPACE \\
    --from-literal=BACKEND_URL="$BACKEND_URL" \\
    --from-literal=BACKEND_WS_URL="$BACKEND_WS_URL" \\
    --from-literal=CLUSTER_ID="$CLUSTER_ID" \\
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
    version: "$AGENT_VERSION"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: spot-agent
  template:
    metadata:
      labels:
        app: spot-agent
        version: "$AGENT_VERSION"
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
'''
    
    # Return the complete script (no need to read template anymore, we have everything inline)
    final_script = dynamic_header
    
    return PlainTextResponse(
        content=final_script,
        media_type="text/x-shellscript",
        headers={
            "Content-Disposition": f"attachment; filename=install-{cluster_id[:8]}.sh"
        }
    )


@router.get("/macos", response_class=PlainTextResponse)
async def get_macos_installer(
    request: Request,
    cluster_id: str = Query(..., description="The cluster ID to configure"),
    api_key: str = Query(..., description="The API key for agent authentication")
):
    """
    Generate a macOS installation script (alias to Linux for kubectl compatibility).
    """
    return await get_linux_installer(request, cluster_id, api_key)
