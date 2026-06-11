import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==========================================
# BOT CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен в переменных окружения")

# Parse Admin IDs from environment
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',')]
    except ValueError:
        print("⚠️ Ошибка при парсинге ADMIN_IDS")
        ADMIN_IDS = []
else:
    ADMIN_IDS = []
    print("⚠️ ADMIN_IDS не установлен")

print(f"✅ Admin IDs: {ADMIN_IDS}")

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
DATABASE_URL = os.getenv(
    'DATABASE_URL', 
    'postgresql+psycopg2://user:password@localhost:5432/it_market_bot'
)

# ==========================================
# BOTHOST/SERVER CONFIGURATION
# ==========================================
USE_WEBHOOK = os.getenv('USE_WEBHOOK', 'false').lower() == 'true'
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

print(f"🌐 Webhook mode: {USE_WEBHOOK}")
if USE_WEBHOOK:
    print(f"🔗 Webhook URL: {WEBHOOK_URL}")

# ==========================================
# FINANCIAL SETTINGS
# ==========================================
DEVELOPER_PERCENTAGE = 0.70  # 70% для разработчика
MARKET_PERCENTAGE = 0.30    # 30% для магазина
REJECTION_COMPENSATION = 0.50  # 50% при отказе
REVISION_COST = 600  # руб. за доработку
FREE_REVISIONS = 3

# ==========================================
# ORDER STATUSES
# ==========================================
ORDER_STATUS = {
    'CREATED': 'created',
    'WAITING_ADMIN': 'waiting_admin',
    'APPROVED': 'approved',
    'IN_DEVELOPMENT': 'in_development',
    'TESTING': 'testing',
    'REVISION': 'revision',
    'COMPLETED': 'completed',
    'REJECTED': 'rejected',
    'CANCELLED': 'cancelled'
}
