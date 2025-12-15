#!/bin/bash
# Test script for single instance mode (TEST environment)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "================================================================================"
echo "SPOT OPTIMIZER - SINGLE INSTANCE TEST MODE"
echo "================================================================================"
echo "This will start the backend in TEST mode and verify it works."
echo "================================================================================"

cd "$PROJECT_ROOT"

# Set environment variables
export ENV=TEST
export LOG_LEVEL=INFO
export API_PORT=8000

# Check if model exists
MODEL_PATH="$PROJECT_ROOT/models/production/family_stress_model.pkl"
if [ ! -f "$MODEL_PATH" ]; then
    echo "⚠️  Model not found: $MODEL_PATH"
    echo "   The backend will use fallback predictions."
    echo "   To train the model, run:"
    echo "     cd ml_training && source venv/bin/activate && python train_master_pipeline.py"
    echo ""
fi

# Check if static data exists
STATIC_DATA="$PROJECT_ROOT/backend/data/static_intelligence.json"
if [ ! -f "$STATIC_DATA" ]; then
    echo "⚠️  Static data not found, running scraper first..."
    cd "$PROJECT_ROOT/scraper"
    source venv/bin/activate
    python fetch_static_data.py
    deactivate
    cd "$PROJECT_ROOT"
fi

# Start backend
echo ""
echo "🚀 Starting backend in TEST mode..."
echo "   API will be available at: http://localhost:$API_PORT"
echo "   Press Ctrl+C to stop"
echo ""

cd "$PROJECT_ROOT/backend"
source venv/bin/activate

# Run with uvicorn
uvicorn main:app --host 0.0.0.0 --port $API_PORT --reload
