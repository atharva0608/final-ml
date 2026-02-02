#!/bin/bash
set -e

# Configuration
REPO_NAME="spot-optimizer-agent"
REGION=$(aws configure get region)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
CHART_NAME="spot-optimizer-agent"
VERSION="0.1.0"

echo "🚀 Starting Helm Chart Publish Process..."
echo "📍 Region: $REGION"
echo "🆔 Account: $ACCOUNT_ID"

# 1. Create ECR Repo (if strict checking needed, but OCI push might create?)
# AWS ECR for OCI artifacts usually requires a standard repo
echo "📦 Checking ECR Repository..."
aws ecr describe-repositories --repository-names "$REPO_NAME" > /dev/null 2>&1 || \
aws ecr create-repository --repository-name "$REPO_NAME" > /dev/null

# 2. Login to ECR
echo "🔑 Logging into ECR..."
aws ecr get-login-password --region "$REGION" | helm registry login --username AWS --password-stdin "$ECR_URI"

# 3. Package Chart
echo "📦 Packaging Helm Chart..."
helm package charts/$CHART_NAME

# 4. Push Chart to OCI
echo "⬆️  Pushing Chart to OCI Registry..."
helm push $CHART_NAME-$VERSION.tgz "oci://$ECR_URI"

echo ""
echo "✅ Success! Helm Chart published."
echo "📋 CHART URI: oci://$ECR_URI/$CHART_NAME"
echo ""
echo "👉 NOTE: You must update the backend script generator with this URI if it differs from the placeholder!"
echo "   Edit 'backend/services/cluster_service.py' -> generate_helm_install_script -> CHART_URI"
