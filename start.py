#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Entry Point for IT Market Bot on BotHost

This script:
1. Installs Python dependencies from requirements.txt
2. Initializes the database
3. Starts the Telegram bot
"""

import subprocess
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("\n" + "="*60)
print("🚀 IT MARKET BOT - BOTHOST LAUNCHER")
print("="*60 + "\n")

# Step 1: Install dependencies
print("📦 Step 1: Installing Python dependencies...")
try:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "--upgrade", "pip"
    ])
    print("  ✅ Pip upgraded\n")
    
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "-r", "requirements.txt"
    ])
    print("  ✅ All dependencies installed\n")
except subprocess.CalledProcessError as e:
    print(f"  ❌ Error installing dependencies: {e}")
    sys.exit(1)

# Step 2: Check environment variables
print("🔐 Step 2: Checking environment variables...")
required_vars = ['BOT_TOKEN', 'ADMIN_IDS', 'DATABASE_URL']
missing_vars = []

for var in required_vars:
    value = os.getenv(var)
    if var == 'BOT_TOKEN':
        if value:
            print(f"  ✅ {var}: {value[:10]}...")
        else:
            missing_vars.append(var)
            print(f"  ❌ {var}: NOT SET")
    else:
        if value:
            print(f"  ✅ {var}: {value[:20]}...")
        else:
            missing_vars.append(var)
            print(f"  ❌ {var}: NOT SET")

if missing_vars:
    print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
    print("\nPlease set the following in BotHost Settings:")
    for var in missing_vars:
        print(f"  - {var}")
    sys.exit(1)

print("")

# Step 3: Initialize database
print("🗄️ Step 3: Initializing database...")
try:
    from database import init_db
    init_db()
    print("  ✅ Database initialized\n")
except Exception as e:
    print(f"  ⚠️ Database initialization warning: {e}")
    print("  Continuing anyway...\n")

# Step 4: Start the bot
print("🤖 Step 4: Starting IT Market Bot...\n")
print("="*60)
print("")

try:
    # Import and run main
    from app import main
    import asyncio
    asyncio.run(main())
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nTrying direct execution...")
    os.execvp(sys.executable, [sys.executable, "app.py"])
except KeyboardInterrupt:
    print("\n❌ Bot stopped by user")
    sys.exit(0)
except Exception as e:
    logger.error(f"Fatal error: {e}", exc_info=True)
    sys.exit(1)
