#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🐳 Spot Optimizer - Docker Hub Publisher${NC}"
echo "This script will:"
echo "1. Build and push the Agent Docker Image to Docker Hub"
echo "2. Package and push the Helm Chart to Docker Hub (OCI)"
echo "3. Update your local configuration files"
echo ""

# 1. Get Docker Hub Username
read -p "Enter your Docker Hub Username: " DOCKER_USER
if [ -z "$DOCKER_USER" ]; then
    echo "Error: Username is required."
    exit 1
fi

IMAGE_NAME="$DOCKER_USER/spot-agent"
CHART_REPO="registry-1.docker.io/$DOCKER_USER"
CHART_URI="oci://$CHART_REPO/helm-charts" 

echo ""
echo "------------------------------------------------"
echo -e "Target Image:  ${GREEN}$IMAGE_NAME:latest${NC}"
echo -e "Target Chart:  ${GREEN}$CHART_URI${NC}"
echo "------------------------------------------------"
read -p "Press Enter to continue..."

# 2. Login
echo ""
echo "🔑 Logging into Docker Hub (for Image)..."
docker login

echo "🔑 Logging into Docker Hub (for Helm OCI)..."
echo "   (You may need to re-enter credentials or use an Access Token)"
helm registry login registry-1.docker.io

# 3. Build & Push Image
echo ""
echo "🏗️  Building Docker Image..."
docker build -t "$IMAGE_NAME:latest" -f agent/Dockerfile . --platform linux/amd64

echo "⬆️  Pushing Docker Image..."
docker push "$IMAGE_NAME:latest"

# 4. Update Helm config to use this image
echo ""
echo "📝 Updating Helm Chart values.yaml..."
# Cross-platform sed compatible with macOS and Linux
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' "s|repository: .*|repository: $IMAGE_NAME|g" charts/spot-optimizer-agent/values.yaml
else
  sed -i "s|repository: .*|repository: $IMAGE_NAME|g" charts/spot-optimizer-agent/values.yaml
fi

# 5. Package & Push Helm Chart
echo ""
echo "📦 Packaging Helm Chart..."
helm package charts/spot-optimizer-agent

echo "⬆️  Pushing Helm Chart..."
# Get version from Chart.yaml
CHART_VERSION=$(grep 'version:' charts/spot-optimizer-agent/Chart.yaml | awk '{print $2}')
helm push "spot-optimizer-agent-$CHART_VERSION.tgz" "$CHART_URI"

# 6. Update Backend Script Generator
echo ""
echo "📝 Updating Backend Script Generator (cluster_service.py)..."
BACKEND_FILE="backend/services/cluster_service.py"

# Construct the new URI string line for python
# We need to escape special characters if any, but standard URL chars should be fine.
NEW_URI_LINE="CHART_URI=\"$CHART_URI/spot-optimizer-agent\" # Updated via script"

# We look for the line starting with CHART_URI= and replace it.
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' "s|CHART_URI=.*|CHART_URI=\"$CHART_URI/spot-optimizer-agent\"|g" "$BACKEND_FILE"
else
  sed -i "s|CHART_URI=.*|CHART_URI=\"$CHART_URI/spot-optimizer-agent\"|g" "$BACKEND_FILE"
fi

echo ""
echo -e "${GREEN}✅ Success! Everything is published and updated.${NC}"
echo "1. Image: $IMAGE_NAME:latest"
echo "2. Chart: $CHART_URI/spot-optimizer-agent"
echo "3. Backend updated to point to this chart."
echo ""
echo -e "👉 ${GREEN}Next Step:${NC} Run 'docker-compose up -d --build backend' to apply the backend changes."
