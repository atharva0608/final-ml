#!/bin/bash
set -e

# Configuration
REPO_NAME="spot-optimizer-agent"
REGION=$(aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"

echo "🚀 Starting Agent Build & Push Process..."
echo "📍 Region: $REGION"
echo "🆔 Account: $ACCOUNT_ID"

# 1. Create ECR Repo if it doesn't exist
echo "📦 Checking ECR Repository..."
aws ecr describe-repositories --repository-names "$REPO_NAME" > /dev/null 2>&1 || \
aws ecr create-repository --repository-name "$REPO_NAME" > /dev/null

# 2. Login to ECR
echo "🔑 Logging into ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# 3. Build Image (Multi-arch support is ideal, but single arch fine for now)
echo "🔨 Building Docker Image..."
# Use buildx for better platform support if available, fallback to regular build
if docker buildx version > /dev/null 2>&1; then
    docker buildx build --platform linux/amd64 -t "$ECR_URI:latest" ./agent --load
else
    docker build -t "$ECR_URI:latest" ./agent
fi

# 4. Push Image
echo "⬆️  Pushing Image to ECR..."
docker push "$ECR_URI:latest"

echo ""
echo "✅ Success! Agent image published."
echo "📋 IMAGE URI: $ECR_URI:latest"
echo ""
echo "👉 Copy this URI and paste it into the 'Custom Image' field in the dashboard if we add one,"
echo "   or the system will automatically detect it if we update the frontend."
