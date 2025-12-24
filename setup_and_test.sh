#!/bin/bash
# Quick setup and test script for deployment folder

set -e

echo "🚀 Setting up deployment folder for testing..."

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "✅ Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  No .env file found!"
    echo "📝 Please create .env file from .env.example:"
    echo "   cp .env.example .env"
    echo "   # Then edit .env and add your API keys"
    echo ""
    echo "Or export environment variables:"
    echo "   export OPENAI_API_KEY='your-key'"
    echo "   export SERPAPI_API_KEY='your-key'"
    echo "   # ... etc"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 To run the app:"
echo "   source venv/bin/activate"
echo "   python app_with_auth.py"
echo ""
echo "📱 App will be available at: http://127.0.0.1:5000/login"
echo ""

