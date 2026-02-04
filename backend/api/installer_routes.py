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
    # We inject the values as environment variables at the top of the script
    dynamic_header = f'''#!/bin/bash
# ============================================
# Spot Optimizer Agent - Dynamic Installer
# Generated for Cluster: {cluster_id}
# ============================================

# Pre-configured values (auto-generated)
export CLUSTER_ID="{cluster_id}"
export API_KEY="{api_key}"
export BACKEND_URL="{ws_endpoint}"

'''
    
    # Remove the original shebang and configuration section from template
    # Find where the actual logic starts (after the variable definitions)
    lines = template_content.split('\n')
    
    # Skip the header/config section, keep the logic
    start_index = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('# --- Pre-flight Checks ---'):
            start_index = i
            break
    
    # Combine dynamic header with the rest of the script
    script_body = '\n'.join(lines[start_index:])
    final_script = dynamic_header + script_body
    
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
