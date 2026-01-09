#!/bin/bash
set -e

echo "🧹 Cleaning Docker build cache..."
docker builder prune -f

echo "🐳 Rebuilding containers without cache..."
docker-compose -f docker/docker-compose.yml build --no-cache

echo "✅ Rebuild complete!"
echo "Now run: docker-compose -f docker/docker-compose.yml up -d"
