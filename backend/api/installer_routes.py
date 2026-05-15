"""
Installer Routes - Dynamic Script Generation

This module provides a public endpoint that generates the installation
script dynamically with pre-filled configuration values.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.base import get_db
from backend.models.cluster import Cluster as ClusterModel

router = APIRouter(prefix="/installer", tags=["installer"])

# Agent version — must match charts/spot-optimizer-agent/Chart.yaml appVersion
CURRENT_AGENT_VERSION = "1.1.2"

# Path to the install.sh template
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "install.sh"


@router.get("/linux", response_class=PlainTextResponse)
async def get_linux_installer(
    request: Request,
    cluster_id: str = Query(..., description="The cluster ID to configure"),
    api_key: str = Query(..., description="The API key for agent authentication"),
    db: Session = Depends(get_db),
):
    """
    Generate a Linux installation script with pre-filled configuration.
    
    This endpoint returns a shell script that can be piped directly to bash:
    
        curl -sL "https://your-api.com/api/installer/linux?cluster_id=...&api_key=..." | bash
    
    The script is dynamically generated with the correct backend URL and credentials.
    """
    # Verify the cluster exists
    cluster = db.query(ClusterModel).filter(ClusterModel.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_id}' not found")

    # Warn if agent is already actively connected (seen in last 5 minutes)
    _agent_active = (
        cluster.agent_installed == "Y"
        and cluster.last_heartbeat is not None
        and (datetime.utcnow() - cluster.last_heartbeat) < timedelta(minutes=5)
    )

    # Read the template
    try:
        template_content = TEMPLATE_PATH.read_text()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Install script template not found")

    # ── Resolve backend URL ────────────────────────────────────────────────────
    # In production: use BACKEND_PUBLIC_URL env var (must be set — agents can't reach internal URLs).
    # In development: derive from request headers (works with ngrok / cloudflare tunnel).
    if settings.BACKEND_PUBLIC_URL:
        backend_url = settings.BACKEND_PUBLIC_URL.rstrip("/")
    else:
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost:8000"))
        backend_url = f"{scheme}://{host}"
    
    # Convert to WebSocket URL for agent connection
    ws_url = backend_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_endpoint = f"{ws_url}/ws/cluster/{cluster_id}"
    
    # Read the Kubernetes manifest template
    manifest_path = Path(__file__).parent.parent / "templates" / "k8s" / "agent.yaml"
    try:
        manifest_content = manifest_path.read_text()
    except FileNotFoundError:
        # Fallback to hardcoded if file is missing (safety net)
        # But for 'Critical File Restoration' we assume it's there.
        # Let's raise error to be strict as per user requirement.
        raise HTTPException(status_code=500, detail="Agent manifest template not found")

    # Substitute variables in the manifest
    # We use simple string replacement or Template string
    from string import Template
    manifest_template = Template(manifest_content)
    # Note: The template uses ${VAR} syntax which works with string.Template
    manifest_k8s = manifest_template.safe_substitute(
        NAMESPACE="spot-optimizer",
        AGENT_IMAGE=f"atharva608/spot-optimizer-agent:{CURRENT_AGENT_VERSION}",
        # Other env vars are handled by envFrom/ConfigMap in the manifest structure
        # Wait, the manifest itself relies on ConfigMap values which are set in the script below.
        # The manifest template I wrote uses ${NAMESPACE} and ${AGENT_IMAGE}.
        # The ConfigMap/Secret creation is done in the SHELL SCRIPT part.
        # So I need to keep the SHELL SCRIPT wrapper, but inject the YAML content.
    )

    _already_installed_banner = ""
    if _agent_active:
        _already_installed_banner = f"""
# ⚠️  WARNING: Agent for cluster '{cluster_id}' appears to already be installed and active
# (last heartbeat: {cluster.last_heartbeat.isoformat() if cluster.last_heartbeat else 'unknown'}).
# Re-running this script will rolling-restart the agent DaemonSet but will NOT break the cluster.
# Proceed only if you are upgrading the agent or fixing a broken installation.
"""

    dynamic_header = f'''#!/bin/bash
set -e

# ============================================
# Spot Optimizer Agent - Dynamic Installer
# Generated for Cluster: {cluster_id}
# ============================================{_already_installed_banner}

# --- Static Configuration ---
NAMESPACE="spot-optimizer"
AGENT_VERSION="{CURRENT_AGENT_VERSION}"
AGENT_IMAGE="atharva608/spot-optimizer-agent:${{AGENT_VERSION}}"

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
# We inject the manifest content here, but we need to substitute SHELL variables first
# The python template substitution handled ${{NAMESPACE}} and ${{AGENT_IMAGE}}
# But the manifest in Python had $NAMESPACE (shell var) usage.
# My manifest template used ${{NAMESPACE}}.
# If I inject it directly, I should ensure the shell treats it correctly.
# Ideally, I substituted NAMESPACE="spot-optimizer" in Python.
# So the manifest_k8s string now has "namespace: spot-optimizer".
# That's fine.

cat <<EOF | kubectl apply -f -
{manifest_k8s}
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
    api_key: str = Query(..., description="The API key for agent authentication"),
    db: Session = Depends(get_db),
):
    """
    Generate a macOS installation script (alias to Linux for kubectl compatibility).
    """
    return await get_linux_installer(request, cluster_id, api_key, db)
