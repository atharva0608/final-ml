#!/bin/bash
# Comprehensive cleanup script for Spot Optimizer Platform
# Removes all generated files, caches, logs, and resets to fresh state

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "================================================================================"
echo "SPOT OPTIMIZER PLATFORM - COMPREHENSIVE CLEANUP"
echo "================================================================================"
echo "This script will remove:"
echo "  1. All Python virtual environments"
echo "  2. All Python caches (__pycache__, .pyc files)"
echo "  3. All trained models and training outputs"
echo "  4. All logs and temporary files"
echo "  5. Scraped static data"
echo "  6. FastAPI/Uvicorn pid files"
echo ""
echo "⚠️  WARNING: This will reset the project to a fresh state."
echo "   You will need to run ./scripts/setup_env.sh again after cleanup."
echo "================================================================================"
echo ""

# Ask for confirmation
read -p "Are you sure you want to continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

cd "$PROJECT_ROOT"

echo ""
echo "🧹 Starting cleanup..."
echo ""

# 1. Remove virtual environments
echo "1️⃣  Removing virtual environments..."
rm -rf ml_training/venv
rm -rf backend/venv
rm -rf scraper/venv
rm -rf ml-model/venv
echo "   ✓ Virtual environments removed"

# 2. Remove Python caches
echo "2️⃣  Removing Python caches..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
echo "   ✓ Python caches removed"

# 3. Remove trained models and outputs
echo "3️⃣  Removing trained models and outputs..."
rm -rf models/production/*.pkl
rm -rf models/production/training_outputs
rm -rf models/production/training_plots
rm -rf models/archive/*.pkl
echo "   ✓ Models and training outputs removed"

# 4. Remove logs
echo "4️⃣  Removing logs..."
rm -rf logs/*.log
rm -rf logs/*.json
rm -rf *.log
echo "   ✓ Logs removed"

# 5. Remove scraped data
echo "5️⃣  Removing scraped static data..."
rm -f backend/data/static_intelligence.json
echo "   ✓ Scraped data removed"

# 6. Remove FastAPI/Uvicorn pid files
echo "6️⃣  Removing FastAPI/Uvicorn pid files..."
rm -f backend/*.pid
rm -f *.pid
echo "   ✓ PID files removed"

# 7. Remove temporary files
echo "7️⃣  Removing temporary files..."
find . -type f -name "*.tmp" -delete 2>/dev/null || true
find . -type f -name "*.temp" -delete 2>/dev/null || true
find . -type f -name ".DS_Store" -delete 2>/dev/null || true
echo "   ✓ Temporary files removed"

# 8. Remove Jupyter notebook checkpoints
echo "8️⃣  Removing Jupyter notebook checkpoints..."
find . -type d -name ".ipynb_checkpoints" -exec rm -rf {} + 2>/dev/null || true
echo "   ✓ Notebook checkpoints removed"

echo ""
echo "================================================================================"
echo "✅ CLEANUP COMPLETE!"
echo "================================================================================"
echo ""
echo "The project has been reset to a fresh state."
echo ""
echo "Next steps:"
echo "  1. Run setup: ./scripts/setup_env.sh"
echo "  2. Train model: cd ml_training && source venv/bin/activate && python train_master_pipeline.py"
echo "  3. Test: ./scripts/test_single_instance.sh"
echo ""
echo "================================================================================"
