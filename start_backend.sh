#!/bin/bash
set -e

echo "🚀 Checking Backend Environment..."
cd backend

# Check for venv
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    
    echo "📦 Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "✅ Environment ready."
echo "🚀 Starting Backend Server on http://0.0.0.0:8000..."
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
