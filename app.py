#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IT Market Bot - Main Entry Point
Direct entry point for BotHost deployment

Usage: python3 app.py
"""

import asyncio
import logging
import sys
import os
import subprocess

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("\n" + "="*70)
print("🤖 IT MARKET BOT - STARTUP")
print("="*70 + "\n")

# ============================================
# STEP 1: Install Dependencies
# ============================================
print("📦 [1/4] Installing dependencies...")
try:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "--upgrade", "pip"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "-r", "requirements.txt"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    logger.info("✅ Dependencies installed successfully")
except subprocess.CalledProcessError as e:
    logger.error(f"❌ Error installing dependencies: {e}")
    print(f"❌ Failed to install dependencies")
    sys.exit(1)

# ============================================
# STEP 2: Check Environment Variables
# ============================================
print("🔐 [2/4] Checking environment variables...")

required_vars = {
    'BOT_TOKEN': 'Telegram Bot Token from @BotFather',
    'ADMIN_IDS': 'Comma-separated admin Telegram IDs',
    'DATABASE_URL': 'PostgreSQL connection string'
}

missing = []
for var, description in required_vars.items():
    value = os.getenv(var)
    if var == 'BOT_TOKEN':
        if value:
            logger.info(f"  ✅ {var}: {'*' * 10}...")
        else:
            missing.append(var)
            logger.error(f"  ❌ {var}: NOT SET")
    else:
        if value:
            logger.info(f"  ✅ {var}: {str(value)[:30]}...")
        else:
            missing.append(var)
            logger.error(f"  ❌ {var}: NOT SET")

if missing:
    print(f"\n❌ ERROR: Missing required environment variables:\n")
    for var in missing:
        print(f"  - {var}: {required_vars[var]}")
    print("\n⚠️ Set these variables in BotHost Settings before continuing.\n")
    sys.exit(1)

logger.info("✅ All environment variables are set")

# ============================================
# STEP 3: Initialize Database
# ============================================
print("🗄️ [3/4] Initializing database...")
try:
    from database import init_db
    init_db()
    logger.info("✅ Database initialized successfully")
except Exception as e:
    logger.warning(f"⚠️ Database initialization warning: {e}")
    logger.info("   Continuing with bot startup...")

# ============================================
# STEP 4: Start Telegram Bot
# ============================================
print("🤖 [4/4] Starting Telegram Bot...\n")
print("="*70)
print()

try:
    from aiogram import Bot, Dispatcher
    from aiogram.types import BotCommand
    from config import BOT_TOKEN, USE_WEBHOOK, WEBHOOK_URL
    from handlers import start, user, admin, developer, messages, completion, admin_panel
    
    # Create bot and dispatcher
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Include all routers
    dp.include_router(start.router)
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(admin_panel.router)
    dp.include_router(developer.router)
    dp.include_router(messages.router)
    dp.include_router(completion.router)
    
    async def set_default_commands():
        """Set default commands in bot menu"""
        commands = [
            BotCommand(command="start", description="🚀 Начать работу"),
            BotCommand(command="admin", description="🛡️ Админ панель"),
            BotCommand(command="list", description="📋 Список заказов"),
            BotCommand(command="myorders", description="📋 Мои заказы"),
            BotCommand(command="myprojects", description="👨‍💻 Мои проекты"),
            BotCommand(command="status", description="🔍 Статус заказа"),
            BotCommand(command="help", description="❓ Помощь"),
        ]
        await bot.set_my_commands(commands)
    
    async def main():
        """Main async function"""
        logger.info("✅ Bot initialized successfully")
        logger.info(f"🌐 Webhook mode: {USE_WEBHOOK}")
        
        await set_default_commands()
        
        if USE_WEBHOOK:
            logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
            await dp.start_webhook(
                listening_host="0.0.0.0",
                listening_port=8080,
                webhook_path="/webhook"
            )
        else:
            logger.info("💬 Polling mode enabled")
            await dp.start_polling(bot)
    
    # Run the bot
    asyncio.run(main())
    
except ImportError as e:
    logger.error(f"❌ Import error: {e}")
    logger.error("Make sure all handlers are properly imported")
    sys.exit(1)
except KeyboardInterrupt:
    logger.info("⚠️ Bot stopped by user (Ctrl+C)")
    sys.exit(0)
except Exception as e:
    logger.error(f"❌ Fatal error: {e}", exc_info=True)
    sys.exit(1)
