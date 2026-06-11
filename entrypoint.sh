#!/bin/bash
set -e

echo "🚀 BotHost Initialization"
echo "========================="
echo ""

# Check Python
echo "✅ Python version:"
python3 --version
echo ""

# Install requirements
echo "📦 Installing dependencies from requirements.txt..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Check environment variables
echo "🔐 Checking environment variables..."
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ BOT_TOKEN not set"
    exit 1
fi
echo "✅ BOT_TOKEN: ${BOT_TOKEN:0:10}..."
echo "✅ ADMIN_IDS: $ADMIN_IDS"
echo ""

# Run the bot
echo "🤖 Starting IT Market Bot..."
echo ""
python3 app.py
