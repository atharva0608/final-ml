#!/bin/bash
# Quick backend starter for development/testing

set -e

echo "🚀 Starting AWS Spot Optimizer Backend..."

# Navigate to backend directory
cd "$(dirname "$0")/backend"

# Check if backend.py exists
if [ ! -f "backend.py" ]; then
    echo "❌ Error: backend.py not found!"
    echo "Current directory: $(pwd)"
    echo "Files present:"
    ls -la
    exit 1
fi

# Create venv if doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/update requirements
echo "📥 Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Create .env file if doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env configuration..."
    cat > .env << 'ENVEOF'
# Database Configuration
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=spotuser
DB_PASSWORD=spotpassword
DB_NAME=spot_optimizer

# Flask Configuration
PORT=5000
FLASK_ENV=production
FLASK_DEBUG=False

# Model Configuration
MODEL_PATH=/home/ubuntu/production_models
DECISION_ENGINE_PATH=/home/ubuntu/production_models/decision_engines
ENVEOF
fi

# Test database connection
echo "🔍 Testing database connection..."
python3 -c "import mysql.connector; mysql.connector.connect(host='127.0.0.1', user='spotuser', password='spotpassword', database='spot_optimizer').close(); print('✓ Database connection OK')" || {
    echo "❌ Database connection failed!"
    echo "Make sure MySQL container is running:"
    echo "  docker ps | grep spot-mysql"
    exit 1
}

# Start backend
echo "✅ Starting backend server on port 5000..."
echo "   Access at: http://localhost:5000/health"
echo "   Press Ctrl+C to stop"
echo ""

python backend.py
