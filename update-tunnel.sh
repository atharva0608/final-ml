#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# update-tunnel.sh — One-command tunnel URL update
#
# Usage:
#   ./update-tunnel.sh <NEW_URL>
#   ./update-tunnel.sh                  # will prompt for URL
#   ./update-tunnel.sh --new-tunnel     # kills old tunnel, starts new, auto-detects URL
#
# What it does:
#   1. Updates Redis (platform:backend_public_url)
#   2. Updates Helm chart values.yaml (backendUrl) for fresh installs
#   3. Finds ALL K8s clusters with spot-agent-config ConfigMap
#   4. Updates each ConfigMap (BACKEND_URL + BACKEND_WS_URL)
#   5. Rolling-restarts DaemonSet + Deployment in each cluster
#   6. Verifies pods come up healthy
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$SCRIPT_DIR/docker"
NAMESPACE="spot-optimizer"
CONFIGMAP="spot-agent-config"
REDIS_CONTAINER="spot-optimizer-redis"
AGENT_IMAGE="atharva608/spot-optimizer-agent:1.1.8"
HELM_VALUES="$SCRIPT_DIR/charts/spot-optimizer-agent/values.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 0. Get the new URL ─────────────────────────────────────────────────────
if [[ "${1:-}" == "--new-tunnel" ]]; then
    info "Killing existing cloudflared processes..."
    pkill -f "cloudflared tunnel" 2>/dev/null || true
    sleep 2

    info "Starting new Cloudflare tunnel..."
    cloudflared tunnel --url http://localhost:8000 > /tmp/cloudflared.log 2>&1 &
    TUNNEL_PID=$!
    
    # Wait for tunnel URL to appear in logs
    for i in $(seq 1 15); do
        NEW_URL=$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | tail -1 || true)
        if [[ -n "$NEW_URL" ]]; then
            break
        fi
        sleep 1
    done
    
    if [[ -z "${NEW_URL:-}" ]]; then
        err "Failed to detect tunnel URL after 15s. Check /tmp/cloudflared.log"
        exit 1
    fi
    ok "New tunnel started (PID $TUNNEL_PID): $NEW_URL"

elif [[ -n "${1:-}" ]]; then
    NEW_URL="${1}"
else
    echo -e "${CYAN}Paste the new tunnel URL:${NC}"
    read -r NEW_URL
fi

# Strip trailing slash
NEW_URL="${NEW_URL%/}"

if [[ -z "$NEW_URL" || ! "$NEW_URL" =~ ^https?:// ]]; then
    err "Invalid URL: '$NEW_URL'. Must start with http:// or https://"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  New Backend URL: ${GREEN}${NEW_URL}${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 1. Update Redis ────────────────────────────────────────────────────────
info "Updating Redis (platform:backend_public_url)..."
if docker exec "$REDIS_CONTAINER" redis-cli SET "platform:backend_public_url" "$NEW_URL" EX 86400 >/dev/null 2>&1; then
    ok "Redis updated"
else
    warn "Redis update failed (container may not be running). Continuing..."
fi

# ── 2. Update Helm chart default backendUrl ────────────────────────────────
# So fresh `helm install` without --set config.backendUrl uses the current URL
info "Updating Helm chart values.yaml (config.backendUrl)..."
if [[ -f "$HELM_VALUES" ]]; then
    # Replace backendUrl line (handles both empty and previously-set values)
    sed -i.bak "s|^  backendUrl:.*|  backendUrl: \"${NEW_URL}\"|" "$HELM_VALUES"
    rm -f "${HELM_VALUES}.bak"
    ok "Helm values.yaml updated — fresh installs will use this URL"
else
    warn "Helm values.yaml not found at $HELM_VALUES. Skipping..."
fi

# ── 3. Verify backend can serve the new URL ────────────────────────────────
info "Testing discover-url endpoint..."
DISCOVER_RESULT=$(curl -sf "${NEW_URL}/api/v1/agents/discover-url" 2>/dev/null || true)
if [[ -n "$DISCOVER_RESULT" ]]; then
    ok "Backend reachable through tunnel"
    echo "    Response: $DISCOVER_RESULT"
else
    warn "Backend not reachable at $NEW_URL yet. Continuing with K8s updates..."
fi

# ── 4. Find all K8s contexts with our ConfigMap ────────────────────────────
info "Scanning kubectl contexts for spot-agent clusters..."
ALL_CONTEXTS=$(kubectl config get-contexts -o name 2>/dev/null || true)
UPDATED_CLUSTERS=0

for CTX in $ALL_CONTEXTS; do
    # Try to read the configmap in this context
    CLUSTER_ID=$(kubectl --context="$CTX" get configmap "$CONFIGMAP" -n "$NAMESPACE" \
        -o jsonpath='{.data.CLUSTER_ID}' 2>/dev/null || true)
    
    if [[ -z "$CLUSTER_ID" ]]; then
        continue
    fi

    info "Found cluster $CLUSTER_ID in context: $CTX"
    
    # Build WS URL
    WS_BASE="${NEW_URL/https:\/\//wss://}"
    WS_BASE="${WS_BASE/http:\/\//ws://}"
    WS_URL="${WS_BASE}/ws/cluster/${CLUSTER_ID}"

    # ── 4a. Patch ConfigMap ────────────────────────────────────────────────
    info "  Patching ConfigMap..."
    if kubectl --context="$CTX" patch configmap "$CONFIGMAP" -n "$NAMESPACE" \
        --type merge -p "{\"data\":{\"BACKEND_URL\":\"${NEW_URL}\",\"BACKEND_WS_URL\":\"${WS_URL}\"}}" \
        >/dev/null 2>&1; then
        ok "  ConfigMap patched (BACKEND_URL + BACKEND_WS_URL)"
    else
        err "  Failed to patch ConfigMap in context $CTX"
        continue
    fi

    # ── 4b. Update image tags (in case they're stale) ─────────────────────
    kubectl --context="$CTX" set image daemonset/spot-agent -n "$NAMESPACE" \
        "agent=$AGENT_IMAGE" >/dev/null 2>&1 || true
    kubectl --context="$CTX" set image deployment/spot-orchestrator -n "$NAMESPACE" \
        "orchestrator=$AGENT_IMAGE" >/dev/null 2>&1 || true

    # ── 4c. Rolling restart ───────────────────────────────────────────────
    info "  Rolling restart..."
    kubectl --context="$CTX" rollout restart daemonset/spot-agent -n "$NAMESPACE" \
        >/dev/null 2>&1 || warn "  DaemonSet restart failed (may not exist)"
    kubectl --context="$CTX" rollout restart deployment/spot-orchestrator -n "$NAMESPACE" \
        >/dev/null 2>&1 || warn "  Orchestrator restart failed (may not exist)"

    UPDATED_CLUSTERS=$((UPDATED_CLUSTERS + 1))
    ok "  Cluster $CLUSTER_ID updated & restarting"
done

echo ""

if [[ $UPDATED_CLUSTERS -eq 0 ]]; then
    warn "No K8s clusters found with $CONFIGMAP. Agents may not be installed yet."
else
    # ── 5. Wait for pods to come up ────────────────────────────────────────
    info "Waiting 20s for pods to stabilize..."
    sleep 20

    for CTX in $ALL_CONTEXTS; do
        CLUSTER_ID=$(kubectl --context="$CTX" get configmap "$CONFIGMAP" -n "$NAMESPACE" \
            -o jsonpath='{.data.CLUSTER_ID}' 2>/dev/null || true)
        [[ -z "$CLUSTER_ID" ]] && continue

        echo ""
        info "Pod status for cluster $CLUSTER_ID ($CTX):"
        kubectl --context="$CTX" get pods -n "$NAMESPACE" \
            --no-headers 2>/dev/null | while read -r line; do
            POD_NAME=$(echo "$line" | awk '{print $1}')
            STATUS=$(echo "$line" | awk '{print $3}')
            if [[ "$STATUS" == "Running" ]]; then
                echo -e "    ${GREEN}✓${NC} $POD_NAME ($STATUS)"
            else
                echo -e "    ${RED}✗${NC} $POD_NAME ($STATUS)"
            fi
        done

        # Quick log check — first agent pod
        FIRST_POD=$(kubectl --context="$CTX" get pods -n "$NAMESPACE" -l app=spot-agent \
            --no-headers 2>/dev/null | head -1 | awk '{print $1}')
        if [[ -n "$FIRST_POD" ]]; then
            REG_LOG=$(kubectl --context="$CTX" logs "$FIRST_POD" -n "$NAMESPACE" --tail=5 2>/dev/null || true)
            if echo "$REG_LOG" | grep -q "registered successfully\|Agent is running"; then
                ok "Agent registered and running"
            elif echo "$REG_LOG" | grep -q "Failed to register"; then
                err "Agent failed to register — check logs: kubectl --context=$CTX logs $FIRST_POD -n $NAMESPACE"
            fi
        fi
    done
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Done!${NC} Updated ${UPDATED_CLUSTERS} cluster(s)"
echo "  Backend URL: $NEW_URL"
echo ""
echo "  Agents will also auto-discover this URL every 5 min"
echo "  via /api/v1/agents/discover-url (v1.1.6+ feature)"
echo "═══════════════════════════════════════════════════════════════"
