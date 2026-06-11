import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN, USE_WEBHOOK, WEBHOOK_URL
from database import init_db
from handlers import start, user, admin, developer, messages, completion, admin_panel

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize database
init_db()

# Create bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Include routers
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
        BotCommand(command="list", description="📋 Список заказов"),
        BotCommand(command="admin", description="🛡️ Админ панель"),
        BotCommand(command="myorders", description="📋 Мои заказы"),
        BotCommand(command="myprojects", description="👨‍💻 Мои проекты"),
        BotCommand(command="status", description="🔍 Статус заказа"),
        BotCommand(command="help", description="❓ Помощь"),
    ]
    await bot.set_my_commands(commands)


async def main():
    """Start bot - Entry point for BotHost"""
    logger.info("🤖 Starting IT Market Bot...")
    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"Database: Connected")
    logger.info(f"Admin IDs: {os.getenv('ADMIN_IDS')}")
    
    await set_default_commands()
    
    if USE_WEBHOOK:
        # Webhook mode for BotHost
        logger.info(f"🌐 Starting webhook mode: {WEBHOOK_URL}")
        await dp.start_webhook(
            listening_host="0.0.0.0",
            listening_port=8080,
            webhook_path="/webhook"
        )
    else:
        # Polling mode (local development)
        logger.info("💬 Starting polling mode")
        await dp.start_polling(bot)


if __name__ == "__main__":
    import os
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("❌ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
