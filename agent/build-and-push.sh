#!/bin/bash
#
# Build and Push Agent Image with Pod Metrics Collection
#
# Usage: ./build-and-push.sh [--skip-push] [--local-test]
#
# Options:
#   --skip-push    Build only, don't push to Docker Hub
#   --local-test   Build and run local test container
#

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="atharva608/spot-optimizer-agent"

# Read version from Chart.yaml (single source of truth)
# Allow override via VERSION env variable: VERSION=1.0.1 ./build-and-push.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHART_YAML="${SCRIPT_DIR}/../charts/spot-optimizer-agent/Chart.yaml"

if [ -z "${VERSION:-}" ]; then
    if [ ! -f "$CHART_YAML" ]; then
        echo -e "${RED}Error: Chart.yaml not found at $CHART_YAML${NC}"
        exit 1
    fi
    VERSION=$(grep '^appVersion:' "$CHART_YAML" | sed 's/appVersion: *"\([^"]*\)"/\1/' | tr -d ' ')
    if [ -z "$VERSION" ]; then
        echo -e "${RED}Error: could not parse appVersion from $CHART_YAML${NC}"
        exit 1
    fi
fi

# Parse arguments
SKIP_PUSH=false
LOCAL_TEST=false

for arg in "$@"; do
    case $arg in
        --skip-push)
            SKIP_PUSH=true
            shift
            ;;
        --local-test)
            LOCAL_TEST=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown argument: $arg${NC}"
            echo "Usage: $0 [--skip-push] [--local-test]"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Building Agent Image${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if we're in the agent directory
if [ ! -f "main.py" ]; then
    echo -e "${RED}Error: main.py not found. Please run this script from the agent directory.${NC}"
    exit 1
fi

# Check if pod_metrics_collector.py exists
if [ ! -f "pod_metrics_collector.py" ]; then
    echo -e "${RED}Error: pod_metrics_collector.py not found. New module missing!${NC}"
    exit 1
fi

echo -e "${YELLOW}Building image: ${IMAGE_NAME}:${VERSION}${NC}"
echo -e "${YELLOW}Platform: linux/amd64,linux/arm64 (multi-arch manifest)${NC}"
echo ""

# Use buildx for cross-platform builds (macOS ARM → linux/amd64).
# Ensure a buildx builder exists. If pushing, use --push directly
# (buildx multi-platform images can't be loaded into local docker).
_BUILDX_BUILDER="spot-agent-builder"
if ! docker buildx inspect "${_BUILDX_BUILDER}" &>/dev/null; then
    echo -e "${YELLOW}Creating buildx builder: ${_BUILDX_BUILDER}${NC}"
    docker buildx create --name "${_BUILDX_BUILDER}" --use
else
    docker buildx use "${_BUILDX_BUILDER}"
fi

if [ "$SKIP_PUSH" = false ]; then
    # Check if logged in to Docker Hub
    if ! docker info 2>/dev/null | grep -q "Username"; then
        echo -e "${YELLOW}Not logged in to Docker Hub. Please login:${NC}"
        docker login
    fi

    # Build and push multi-arch manifest (amd64 + arm64).
    # --push is required for multi-platform buildx (can't --load multi-arch locally).
    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        --build-arg AGENT_VERSION="${VERSION}" \
        -t "${IMAGE_NAME}:${VERSION}" \
        -t "${IMAGE_NAME}:latest" \
        --push \
        .
else
    # Local build only — single platform (multi-arch --load not supported by Docker daemon).
    # Defaults to host arch (amd64 on x86, arm64 on Apple Silicon).
    _LOCAL_ARCH="linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"
    echo -e "${YELLOW}Local build only: ${_LOCAL_ARCH}${NC}"
    docker buildx build \
        --platform "${_LOCAL_ARCH}" \
        --build-arg AGENT_VERSION="${VERSION}" \
        -t "${IMAGE_NAME}:${VERSION}" \
        --load \
        .
fi

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Build successful!${NC}"
    echo ""
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi

# Show image details
echo -e "${YELLOW}Image details:${NC}"
docker images | grep "spot-optimizer-agent" | head -2
echo ""

# Local test mode
if [ "$LOCAL_TEST" = true ]; then
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}Running Local Test${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""

    echo -e "${YELLOW}Starting test container...${NC}"
    docker run --rm \
        -e BACKEND_URL=http://host.docker.internal:8000 \
        -e API_KEY=test-key \
        -e CLUSTER_ID=test-cluster \
        -e NODE_NAME=test-node \
        -e POD_METRICS_INTERVAL=60 \
        "${IMAGE_NAME}:${VERSION}" &

    CONTAINER_PID=$!

    echo "Container PID: $CONTAINER_PID"
    echo "Waiting 10 seconds for agent to start..."
    sleep 10

    echo ""
    echo -e "${YELLOW}Checking container logs...${NC}"
    docker ps | grep spot-optimizer-agent

    echo ""
    echo -e "${YELLOW}Stopping test container...${NC}"
    kill $CONTAINER_PID 2>/dev/null || true

    echo -e "${GREEN}✓ Local test complete${NC}"
    echo ""
fi

# Push to Docker Hub
if [ "$SKIP_PUSH" = false ]; then
    echo ""
    echo -e "${GREEN}✓ Build and push successful!${NC}"
    echo ""

    # Verify on Docker Hub
    echo -e "${YELLOW}Verifying image on Docker Hub...${NC}"
    echo "Visit: https://hub.docker.com/r/${IMAGE_NAME}/tags"
    echo ""
else
    echo -e "${YELLOW}Skipping push to Docker Hub (--skip-push flag)${NC}"
    echo ""
fi

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Summary${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Image built: ${IMAGE_NAME}:${VERSION}"
echo "Image size: $(docker images "${IMAGE_NAME}:${VERSION}" --format '{{.Size}}')"

if [ "$SKIP_PUSH" = false ]; then
    echo "Status: Pushed to Docker Hub ✓"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "1. Verify image: docker pull ${IMAGE_NAME}:${VERSION}"
    echo "2. Restart DaemonSet: kubectl rollout restart daemonset/spot-agent -n spot-optimizer"
    echo "3. Check logs: kubectl logs -n spot-optimizer -l app=spot-agent | grep PodMetrics"
    echo "4. Query API: curl http://localhost:8000/api/v1/pod-metrics?cluster_id=test&limit=5"
else
    echo "Status: Built locally (not pushed)"
    echo ""
    echo -e "${YELLOW}To push manually:${NC}"
    echo "docker push ${IMAGE_NAME}:${VERSION}"
fi

echo ""
echo -e "${GREEN}✓ Agent upgrade complete!${NC}"
