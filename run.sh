#!/bin/bash

# ========================================
# BotHost Entry Point Script
# ========================================
# This script should be run by BotHost when deploying

echo "🚀 Starting IT Market Bot on BotHost..."

# Load environment variables
set -a
if [ -f .env ]; then
    source .env
fi
set +a

echo "✅ Environment loaded"
echo "🤖 Bot Token: ${BOT_TOKEN:0:10}..."
echo "👮 Admin IDs: $ADMIN_IDS"
echo "🗄️ Database: $DATABASE_URL"

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "✅ Dependencies installed"

# Run the bot
echo "🤖 Starting bot..."
python3 app.py
