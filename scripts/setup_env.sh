#!/bin/bash
# Setup script for Spot Optimizer Platform
# Creates venvs, installs dependencies, creates necessary directories

set -e  # Exit on error

echo "================================================================================"
echo "SPOT OPTIMIZER PLATFORM - ENVIRONMENT SETUP"
echo "================================================================================"
echo "This script will:"
echo "  1. Create Python virtual environments"
echo "  2. Install all dependencies"
echo "  3. Create necessary directories"
echo "  4. Run initial data scraper"
echo "================================================================================"

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Project Root: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# Function to create venv and install requirements
setup_component() {
    local name=$1
    local dir=$2
    local req_file=$3

    echo ""
    echo "Setting up $name..."
    echo "--------------------------------------------------------------------------------"

    cd "$PROJECT_ROOT/$dir"

    # Create venv if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "  Creating virtual environment..."
        python3 -m venv venv
    fi

    # Activate venv
    source venv/bin/activate

    # Install requirements
    if [ -f "$req_file" ]; then
        echo "  Installing dependencies..."
        pip install --upgrade pip
        pip install -r "$req_file"
    fi

    deactivate
    echo "  ✓ $name setup complete"
}

# Create directories
echo ""
echo "Creating directories..."
echo "--------------------------------------------------------------------------------"
mkdir -p models/production models/archive
mkdir -p backend/data
mkdir -p logs
echo "  ✓ Directories created"

# Setup Backend
echo ""
echo "Setting up Backend..."
echo "--------------------------------------------------------------------------------"
cd "$PROJECT_ROOT/backend"

if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "  Installing dependencies..."
pip install --upgrade pip
pip install \
    fastapi==0.104.0 \
    uvicorn[standard]==0.24.0 \
    pydantic-settings==2.0.3 \
    loguru==0.7.2 \
    requests==2.31.0 \
    boto3==1.28.0 \
    kubernetes==28.1.0 \
    apscheduler==3.10.4 \
    lightgbm==4.1.0 \
    scikit-learn==1.3.0 \
    pandas==2.1.0 \
    numpy==1.25.0

deactivate
echo "  ✓ Backend setup complete"

# Setup Scraper
echo ""
echo "Setting up Scraper..."
echo "--------------------------------------------------------------------------------"
cd "$PROJECT_ROOT/scraper"

if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "  Installing dependencies..."
pip install --upgrade pip
pip install requests apscheduler

deactivate
echo "  ✓ Scraper setup complete"

# Run initial data scraper
echo ""
echo "Running initial data scraper..."
echo "--------------------------------------------------------------------------------"
cd "$PROJECT_ROOT/scraper"
source venv/bin/activate
python fetch_static_data.py
deactivate

echo ""
echo "================================================================================"
echo "✅ SETUP COMPLETE!"
echo "================================================================================"
echo ""
echo "Next steps:"
echo "  1. Train the ML model:"
echo "     cd ml-model"
echo "     python family_stress_model.py"
echo ""
echo "  2. Test single instance (TEST mode):"
echo "     ./scripts/test_single_instance.sh"
echo ""
echo "  3. Test pipeline standalone:"
echo "     cd backend/decision_engine_v2"
echo "     python example.py"
echo ""
echo "================================================================================"
