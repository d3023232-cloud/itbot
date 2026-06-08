import asyncio
import os
import logging
import aiosqlite
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
CARD_DETAILS = os.getenv("CARD_DETAILS")
REVIEWS_CHANNEL = os.getenv("REVIEWS_CHANNEL")
DB_NAME = os.path.join(os.getenv("DATA_DIR", "/app/data"), os.getenv("DB_NAME", "it_bot.db"))
REFERRAL_PERCENT = float(os.getenv("REFERRAL_PERCENT", "10"))
DEV_PERCENT = float(os.getenv("DEV_PERCENT", "70"))
PREPAYMENT_LIMIT = float(os.getenv("PREPAYMENT_LIMIT", "5000"))
DEV_PENALTY_PERCENT = float(os.getenv("DEV_PENALTY_PERCENT", "50"))
DEV_DEADLINE_EXTENSION = int(os.getenv("DEV_DEADLINE_EXTENSION", "3"))

missing = []
if not BOT_TOKEN: missing.append("BOT_TOKEN")
if not ADMIN_ID: missing.append("ADMIN_ID")
if not CARD_DETAILS: missing.append("CARD_DETAILS")
if not REVIEWS_CHANNEL: missing.append("REVIEWS_CHANNEL")

if missing:
    raise EnvironmentError(f"[CONFIG ERROR] Missing: {', '.join(missing)}")

try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise EnvironmentError("[CONFIG ERROR] ADMIN_ID must be integer")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== CLEAR STATE ====================
def clear_state(context: ContextTypes.DEFAULT_TYPE):
    for key in list(context.user_data.keys()):
        del context.user_data[key]

# ==================== DATABASE ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE,
                username TEXT,
                language TEXT DEFAULT 'ru',
                role TEXT DEFAULT 'user',
                balance REAL DEFAULT 0,
                referral_code TEXT,
                referred_by INTEGER,
                banned INTEGER DEFAULT 0,
                dev_penalty REAL DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                platform TEXT,
                topic TEXT,
                description TEXT,
                price REAL,
                final_price REAL,
                deadline_days INTEGER,
                status TEXT DEFAULT 'new',
                developer_id INTEGER,
                temp_bot_username TEXT,
                revision_count INTEGER DEFAULT 0,
                promo_code TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS balance_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                screenshot_file_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                initials TEXT,
                card_details TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                type TEXT,
                value REAL,
                uses_count INTEGER DEFAULT 0,
                max_uses INTEGER,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                user_id INTEGER,
                rating INTEGER,
                text TEXT,
                created_at TEXT
            )
        """)
        await db.commit()
        logger.info("Database initialized at %s", DB_NAME)

async def get_user(tg_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def create_user(tg_id: int, username: str, referred_by: str = None):
    ref_code = str(tg_id)
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, username, referral_code, referred_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (tg_id, username, ref_code, referred_by, now)
        )
        await db.commit()
        logger.info("User created: %s", tg_id)

async def update_user_language(tg_id: int, language: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET language = ? WHERE tg_id = ?", (language, tg_id))
        await db.commit()

async def update_user_role(tg_id: int, role: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET role = ? WHERE tg_id = ?", (role, tg_id))
        await db.commit()

async def ban_user(tg_id: int, banned: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET banned = ? WHERE tg_id = ?", (banned, tg_id))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT tg_id FROM users WHERE banned = 0") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_developers():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE role = 'developer'") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def update_balance(tg_id: int, amount: float):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE tg_id = ?", (amount, tg_id))
        await db.commit()
        logger.info("Balance updated for %s: %s", tg_id, amount)

async def get_balance(tg_id: int) -> float:
    user = await get_user(tg_id)
    return user['balance'] if user else 0

async def get_user_lang(tg_id: int) -> str:
    user = await get_user(tg_id)
    return user['language'] if user else 'ru'

async def create_order(user_id: int, platform: str, topic: str, description: str, promo_code: str = None):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, platform, topic, description, promo_code, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, platform, topic, description, promo_code, now, now)
        )
        await db.commit()
        logger.info("Order created: %s", cursor.lastrowid)
        return cursor.lastrowid

async def get_order(order_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_orders_by_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_orders_by_developer(developer_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE developer_id = ? AND status IN ('in_progress', 'testing', 'revision', 'paid') ORDER BY id DESC", (developer_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_available_orders():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE status IN ('price_set', 'price_negotiation', 'waiting_prepayment') AND developer_id IS NULL ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_pending_orders():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE status IN ('new', 'price_set', 'price_negotiation', 'waiting_prepayment') ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def update_order(order_id: int, **kwargs):
    if not kwargs:
        return
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [order_id]
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE orders SET {fields} WHERE id = ?", values)
        await db.commit()
        logger.info("Order %s updated: %s", order_id, kwargs)

async def create_balance_request(user_id: int, amount: float, screenshot_file_id: str):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO balance_requests (user_id, amount, screenshot_file_id, created_at) VALUES (?, ?, ?, ?)",
            (user_id, amount, screenshot_file_id, now)
        )
        await db.commit()
        return cursor.lastrowid

async def get_balance_request(req_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM balance_requests WHERE id = ?", (req_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_pending_balance_requests():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM balance_requests WHERE status = 'pending' ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def update_balance_request(req_id: int, status: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE balance_requests SET status = ? WHERE id = ?", (status, req_id))
        await db.commit()

async def create_withdrawal_request(user_id: int, amount: float, initials: str, card_details: str):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO withdrawal_requests (user_id, amount, initials, card_details, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, initials, card_details, now)
        )
        await db.commit()
        return cursor.lastrowid

async def get_withdrawal_request(req_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawal_requests WHERE id = ?", (req_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawal_requests WHERE status = 'pending' ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def update_withdrawal(req_id: int, status: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE withdrawal_requests SET status = ? WHERE id = ?", (status, req_id))
        await db.commit()

async def create_promo_code(code: str, ptype: str, value: float, max_uses: int):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO promo_codes (code, type, value, max_uses, created_at) VALUES (?, ?, ?, ?, ?)",
            (code.upper(), ptype, value, max_uses, now)
        )
        await db.commit()

async def get_promo_code(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_codes WHERE code = ?", (code.upper(),)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def use_promo_code(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE promo_codes SET uses_count = uses_count + 1 WHERE code = ?", (code.upper(),))
        await db.commit()

async def create_review(order_id: int, user_id: int, rating: int, text: str):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO reviews (order_id, user_id, rating, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (order_id, user_id, rating, text, now)
        )
        await db.commit()

async def update_dev_penalty(tg_id: int, amount: float):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET dev_penalty = dev_penalty + ? WHERE tg_id = ?", (amount, tg_id))
        await db.commit()

async def clear_dev_penalty(tg_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET dev_penalty = 0 WHERE tg_id = ?", (tg_id,))
        await db.commit()


# ==================== LOCALIZATION (FULL RUSSIAN) ====================
TEXTS = {
    'ru': {
        'welcome': "👋 Добро пожаловать в IT Bot Market!\nВыберите язык:",
        'menu': "📋 Главное меню",
        'new_order': "🛒 Создать заказ",
        'my_orders': "📦 Мои заказы",
        'balance': "💰 Баланс",
        'deposit': "💳 Пополнить баланс",
        'withdraw': "🏦 Вывести средства",
        'referral': "👥 Реферальная программа",
        'settings': "⚙️ Настройки",
        'admin_panel': "🔧 Админ-панель",
        'developer_panel': "💻 Панель разработчика",
        'choose_platform': "Выберите платформу для бота:",
        'telegram': "📱 Telegram",
        'vk': "🌐 VK",
        'choose_topic': "Выберите тематику:",
        'business': "🏢 Бизнес",
        'game': "🎮 Игровая",
        'education': "🎓 Образовательная",
        'entertainment': "🎭 Развлекательная",
        'other': "📝 Другое",
        'send_tz': "Опишите подробно функционал бота или пришлите ТЗ (текстом):",
        'order_created': "✅ Заказ #{} создан! Администратор назначит цену в ближайшее время.",
        'price_set': "💰 Стоимость заказа #{}: {} ₽\nСрок: {} дней\n{}\n\nПодтвердите заказ:",
        'prepayment_required': "⚠️ Требуется предоплата 100% ({} ₽), так как сумма < {} ₽. Средства будут списаны с вашего баланса.",
        'no_prepayment': "✅ Предоплата не требуется. Оплата после тестирования.",
        'accept_price': "✅ Согласен",
        'suggest_price': "💬 Предложить свою цену",
        'cancel_order': "❌ Отменить",
        'enter_your_price': "Введите сумму, которую вы готовы заплатить (только число):",
        'enter_your_deadline': "Введите количество дней на разработку:",
        'price_sent': "💬 Ваша цена и срок отправлены администратору.",
        'order_cancelled': "❌ Заказ отменен.",
        'not_enough_balance': "❌ Недостаточно средств. Пополните баланс.",
        'prepayment_done': "✅ Предоплата {} ₽ списана. Заказ передан разработчику.",
        'order_confirmed': "✅ Заказ подтвержден. Ожидайте начала разработки.",
        'new_order_admin': "🆕 Новый заказ #{}\n👤 Клиент: @{}/{}\n📱 Платформа: {}\n📂 Тематика: {}\n📝 Описание: {}\n🎟 Промокод: {}",
        'set_price': "💰 Назначить цену и срок",
        'enter_price': "Введите цену для заказа #{} (только число):",
        'enter_deadline': "Введите срок в днях для заказа #{}:",
        'price_updated': "✅ Цена и срок назначены.",
        'choose_developer': "Выберите разработчика для заказа #{}:",
        'developer_set': "✅ Разработчик назначен.",
        'developer_assigned': "🔔 Вам назначен заказ #{}!\n📱 {} | 📂 {}\n📝 {}\nСрок: {} дней\n\nНажмите 'Отправить тестового бота' когда будет готово.",
        'send_test_bot': "Отправьте юзернейм тестового бота (например, @my_test_bot):",
        'test_bot_sent': "🤖 Ваш бот готов!\nПерейдите для теста: {}\n\nПосле проверки нажмите 'Далее'.",
        'test_bot_received': "✅ Тестовый бот получен. Клиент уведомлен.",
        'next': "➡️ Далее",
        'pay': "💰 Оплатить",
        'revision': "🔧 Правки",
        'refuse': "🚫 Отказ",
        'enter_revision': "Опишите, что нужно исправить:",
        'revision_sent': "🔧 Правки отправлены разработчику. Осталось раундов: {}",
        'max_revisions': "❌ Лимит правок исчерпан (3/3). Дальнейшие правки технически невозможны.",
        'order_paid': "✅ Заказ оплачен! Администратор подготовит исходный код.",
        'order_refused': "🚫 Заказ отменен. {}",
        'prepayment_kept': "Предоплата {} ₽ остается у магазина (сумма < {} ₽).",
        'no_prepayment_return': "Предоплата не требовалась.",
        'send_zip_admin': "📦 Заказ #{} оплачен. Пришлите ZIP-файл с исходным кодом (ответом на это сообщение):",
        'zip_sent': "📦 Исходный код получен! Спасибо за заказ.",
        'leave_review': "⭐ Оцените работу (1-5):",
        'review_text': "Напишите текст отзыва:",
        'review_thanks': "Спасибо за отзыв!",
        'enter_deposit': "Введите сумму для пополнения (₽):",
        'deposit_info': "Переведите {} ₽ на карту:\n{}\n\nВ комментарии укажите: пополнение {}\n\nПосле перевода пришлите скриншот:",
        'deposit_sent': "⏳ Заявка на пополнение отправлена. Ожидайте подтверждения.",
        'enter_withdraw': "Введите сумму, ФИО и номер карты через запятую:\n(Пример: 5000, Иванов И.И., 4276123456789012)",
        'withdraw_sent': "⏳ Заявка на вывод отправлена.",
        'referral_text': "👥 Ваша реферальная ссылка:\nhttps://t.me/{}?start={}\n\nПриглашайте друзей и получайте {}% с их заказов на баланс!",
        'new_balance_req': "💰 Заявка на пополнение #{}\n👤 @{}/{}\n💵 {} ₽",
        'new_withdrawal': "🏦 Заявка на вывод #{}\n👤 @{}/{}\n💵 {} ₽\n👤 ФИО: {}\n💳 Карта: {}",
        'confirm': "✅ Подтвердить",
        'reject': "❌ Отклонить",
        'balance_confirmed': "✅ Баланс пополнен на {} ₽",
        'balance_rejected': "❌ Заявка на пополнение отклонена.",
        'withdrawal_confirmed': "✅ Вывод подтвержден. Средства отправлены.",
        'withdrawal_rejected': "❌ Заявка на вывод отклонена.",
        'enter_user_id': "Введите Telegram ID или @username:",
        'user_banned': "🚫 Пользователь забанен.",
        'user_unbanned': "✅ Пользователь разбанен.",
        'dev_assigned': "✅ Пользователь назначен разработчиком.",
        'dev_removed': "✅ Пользователь снят с должности разработчика.",
        'enter_broadcast': "Введите текст для рассылки всем пользователям:",
        'broadcast_done': "✅ Рассылка завершена. Доставлено: {}",
        'enter_promo': "Введите: КОД, ТИП(percent/fixed), ЗНАЧЕНИЕ, МАКС_ИСПОЛЬЗОВАНИЙ\nПример: SALE10, percent, 10, 50",
        'promo_created': "✅ Промокод создан.",
        'enter_promo_code': "Есть промокод?",
        'promo_applied': "🎟 Промокод применен! Скидка: {} ₽",
        'invalid_promo': "❌ Неверный или недействительный промокод.",
        'skip_promo': "🚫 Без промокода",
        'use_promo': "🎟 У меня есть промокод",
        'status_new': "⏳ Ожидает цену",
        'status_price_set': "💰 Цена назначена",
        'status_price_negotiation': "💬 Согласование цены",
        'status_waiting_prepayment': "⏳ Ожидание предоплаты",
        'status_in_progress': "🔨 В работе",
        'status_testing': "🧪 Тестирование",
        'status_revision': "🔧 Правки {}/3",
        'status_paid': "💵 Оплачен",
        'status_delivered': "📦 Доставлен",
        'status_reviewed': "⭐ Завершен",
        'status_cancelled': "❌ Отменен",
        'no_orders': "У вас пока нет заказов.",
        'order_info': "📦 Заказ #{}\n📊 Статус: {}\n💰 Цена: {} ₽\n📱 {} | 📂 {}\n📝 {}",
        'order_list': "📦 Заказ #{} — {}",
        'banned': "🚫 Вы забанены.",
        'back': "🔙 Назад",
        'main_menu': "🏠 Главное меню",
        'choose_language': "🌐 Выберите язык:",
        'language_set': "✅ Язык изменен.",
        'my_balance': "💰 Ваш баланс: {:.2f} ₽",
        'admin_stats': "📊 Статистика\nВсего заказов: {}\nАктивных: {}\nПользователей: {}",
        'send_test_bot_btn': "🤖 Отправить тестового бота",
        'send_zip_btn': "📦 Отправить ZIP клиенту",
        'no_developers': "Нет доступных разработчиков.",
        'insufficient_funds': "Недостаточно средств. Нужно: {} ₽, у вас: {} ₽",
        'choose_action': "Выберите действие после тестирования:",
        'pay_from_balance': "Списано с баланса: {} ₽",
        'final_price': "Итоговая цена со скидкой: {} ₽",
        'choose_deadline': "Выберите срок разработки (дней):",
        'custom_deadline': "✏️ Свой вариант",
        'deadline_set': "Срок: {} дней",
        'dev_max_orders': "❌ У вас уже есть активный заказ. Завершите или отмените его перед взятием нового.",
        'dev_penalty_applied': "⚠️ Штраф 50% ({:.2f} ₽) удержан с разработчика за предыдущий незавершенный заказ.",
        'dev_cancel_confirm': "❌ Вы уверены, что хотите отменить заказ? С вас будет удержан штраф 50% от следующего выполненного заказа.",
        'dev_cancelled': "❌ Заказ отменен разработчиком. Штраф начислен.",
        'list_title': "📋 Доступные заказы:",
        'list_empty': "Нет доступных заказов.",
        'take_order': "✅ Взять заказ #{}",
        'order_taken': "✅ Заказ #{} взят в работу.",
        'dev_work_panel': "🔨 Ход работы",
        'dev_extend_deadline': "⏳ Продлить срок (+{} дней)",
        'deadline_extended': "Срок продлен на {} дней. Новый срок: {} дней.",
        'dev_cancel_order': "❌ Отменить заказ",
        'admin_only': "🚫 Только для администраторов.",
        'dev_only': "🚫 Только для разработчиков.",
        'cancel': "❌ Отмена",
        'back_to_menu': "🔙 Вернуться в меню",
        'enter_custom_deadline': "Введите количество дней (число):",
        'choose_deadline_buttons': "Выберите срок:",
        'day': "{} дней",
        'admin_menu_title': "🔧 Админ-панель\n\nВыберите раздел:",
        'admin_orders_btn': "📦 Заказы",
        'admin_deposits_btn': "💰 Пополнения",
        'admin_withdrawals_btn': "🏦 Выводы",
        'admin_staff_btn': "👥 Управление персоналом",
        'admin_broadcast_btn': "📢 Рассылка",
        'admin_promos_btn': "🎟 Промокоды",
        'staff_setdev': "Назначить разработчика",
        'staff_removedev': "Снять разработчика",
        'staff_ban': "Забанить",
        'staff_unban': "Разбанить",
        'staff_back': "🔙 Назад",
        'order_details': "📦 Заказ #{}\n👤 Клиент: {}\n📱 {} | 📂 {}\n💰 {} ₽ | Срок: {} дней\n📝 {}",
    },
    'en': {
        'welcome': "👋 Welcome to IT Bot Market!\nChoose language:",
        'menu': "📋 Main menu",
        'new_order': "🛒 New order",
        'my_orders': "📦 My orders",
        'balance': "💰 Balance",
        'deposit': "💳 Deposit",
        'withdraw': "🏦 Withdraw",
        'referral': "👥 Referral program",
        'settings': "⚙️ Settings",
        'admin_panel': "🔧 Admin panel",
        'developer_panel': "💻 Developer panel",
        'choose_platform': "Choose platform:",
        'telegram': "📱 Telegram",
        'vk': "🌐 VK",
        'choose_topic': "Choose topic:",
        'business': "🏢 Business",
        'game': "🎮 Game",
        'education': "🎓 Education",
        'entertainment': "🎭 Entertainment",
        'other': "📝 Other",
        'send_tz': "Describe the bot functionality or send technical task:",
        'order_created': "✅ Order #{} created! Admin will set the price soon.",
        'price_set': "💰 Price for order #{}: {} ₽\nDeadline: {} days\n{}\n\nConfirm order:",
        'prepayment_required': "⚠️ 100% prepayment required ({} ₽) as amount < {} ₽. Will be deducted from balance.",
        'no_prepayment': "✅ No prepayment needed. Pay after testing.",
        'accept_price': "✅ Accept",
        'suggest_price': "💬 Suggest price",
        'cancel_order': "❌ Cancel",
        'enter_your_price': "Enter amount you are ready to pay (number only):",
        'enter_your_deadline': "Enter development deadline in days:",
        'price_sent': "💬 Your price and deadline sent to admin.",
        'order_cancelled': "❌ Order cancelled.",
        'not_enough_balance': "❌ Not enough balance. Please deposit.",
        'prepayment_done': "✅ Prepayment {} ₽ deducted. Order assigned to developer.",
        'order_confirmed': "✅ Order confirmed. Development will start soon.",
        'new_order_admin': "🆕 New order #{}\n👤 Client: @{}/{}\n📱 Platform: {}\n📂 Topic: {}\n📝 Description: {}\n🎟 Promo: {}",
        'set_price': "💰 Set price and deadline",
        'enter_price': "Enter price for order #{} (number only):",
        'enter_deadline': "Enter deadline in days for order #{}:",
        'price_updated': "✅ Price and deadline set.",
        'choose_developer': "Choose developer for order #{}:",
        'developer_set': "✅ Developer assigned.",
        'developer_assigned': "🔔 New order #{} assigned!\n📱 {} | 📂 {}\n📝 {}\nDeadline: {} days\n\nPress 'Send test bot' when ready.",
        'send_test_bot': "Send test bot username (e.g., @my_test_bot):",
        'test_bot_sent': "🤖 Your bot is ready!\nTest it here: {}\n\nAfter testing press 'Next'.",
        'test_bot_received': "✅ Test bot received. Client notified.",
        'next': "➡️ Next",
        'pay': "💰 Pay",
        'revision': "🔧 Revisions",
        'refuse': "🚫 Refuse",
        'enter_revision': "Describe what needs to be fixed:",
        'revision_sent': "🔧 Revisions sent to developer. Remaining rounds: {}",
        'max_revisions': "❌ Revision limit reached (3/3). Further revisions technically impossible.",
        'order_paid': "✅ Order paid! Admin will prepare source code.",
        'order_refused': "🚫 Order cancelled. {}",
        'prepayment_kept': "Prepayment {} ₽ kept by shop (order < {} ₽).",
        'no_prepayment_return': "No prepayment was required.",
        'send_zip_admin': "📦 Order #{} paid. Send ZIP file with source code (reply to this message):",
        'zip_sent': "📦 Source code received! Thank you for order.",
        'leave_review': "⭐ Rate the work (1-5):",
        'review_text': "Write review text:",
        'review_thanks': "Thank you for review!",
        'enter_deposit': "Enter deposit amount (₽):",
        'deposit_info': "Transfer {} ₽ to card:\n{}\n\nComment: deposit {}\n\nAfter transfer send screenshot:",
        'deposit_sent': "⏳ Deposit request sent. Awaiting confirmation.",
        'enter_withdraw': "Enter amount, full name and card number separated by commas:\n(Example: 5000, Ivanov I.I., 4276123456789012)",
        'withdraw_sent': "⏳ Withdrawal request sent.",
        'referral_text': "👥 Your referral link:\nhttps://t.me/{}?start={}\n\nInvite friends and get {}% from their orders!",
        'new_balance_req': "💰 Deposit request #{}\n👤 @{}/{}\n💵 {} ₽",
        'new_withdrawal': "🏦 Withdrawal request #{}\n👤 @{}/{}\n💵 {} ₽\n👤 Name: {}\n💳 Card: {}",
        'confirm': "✅ Confirm",
        'reject': "❌ Reject",
        'balance_confirmed': "✅ Balance deposited: {} ₽",
        'balance_rejected': "❌ Deposit request rejected.",
        'withdrawal_confirmed': "✅ Withdrawal confirmed. Funds sent.",
        'withdrawal_rejected': "❌ Withdrawal request rejected.",
        'enter_user_id': "Enter Telegram ID or @username:",
        'user_banned': "🚫 User banned.",
        'user_unbanned': "✅ User unbanned.",
        'dev_assigned': "✅ User set as developer.",
        'dev_removed': "✅ Developer role removed.",
        'enter_broadcast': "Enter broadcast text for all users:",
        'broadcast_done': "✅ Broadcast done. Delivered: {}",
        'enter_promo': "Enter: CODE, TYPE(percent/fixed), VALUE, MAX_USES\nExample: SALE10, percent, 10, 50",
        'promo_created': "✅ Promo code created.",
        'enter_promo_code': "Have a promo code?",
        'promo_applied': "🎟 Promo applied! Discount: {} ₽",
        'invalid_promo': "❌ Invalid or expired promo code.",
        'skip_promo': "🚫 No promo code",
        'use_promo': "🎟 I have a promo code",
        'status_new': "⏳ Awaiting price",
        'status_price_set': "💰 Price set",
        'status_price_negotiation': "💬 Price negotiation",
        'status_waiting_prepayment': "⏳ Awaiting prepayment",
        'status_in_progress': "🔨 In progress",
        'status_testing': "🧪 Testing",
        'status_revision': "🔧 Revisions {}/3",
        'status_paid': "💵 Paid",
        'status_delivered': "📦 Delivered",
        'status_reviewed': "⭐ Completed",
        'status_cancelled': "❌ Cancelled",
        'no_orders': "You have no orders yet.",
        'order_info': "📦 Order #{}\n📊 Status: {}\n💰 Price: {} ₽\n📱 {} | 📂 {}\n📝 {}",
        'order_list': "📦 Order #{} — {}",
        'banned': "🚫 You are banned.",
        'back': "🔙 Back",
        'main_menu': "🏠 Main menu",
        'choose_language': "🌐 Choose language:",
        'language_set': "✅ Language changed.",
        'my_balance': "💰 Your balance: {:.2f} ₽",
        'admin_stats': "📊 Stats\nTotal orders: {}\nActive: {}\nUsers: {}",
        'send_test_bot_btn': "🤖 Send test bot",
        'send_zip_btn': "📦 Send ZIP to client",
        'no_developers': "No available developers.",
        'insufficient_funds': "Insufficient funds. Need: {} ₽, you have: {} ₽",
        'choose_action': "Choose action after testing:",
        'pay_from_balance': "Deducted from balance: {} ₽",
        'final_price': "Final price with discount: {} ₽",
        'choose_deadline': "Choose development deadline (days):",
        'custom_deadline': "✏️ Custom",
        'deadline_set': "Deadline: {} days",
        'dev_max_orders': "❌ You already have an active order. Complete or cancel it before taking a new one.",
        'dev_penalty_applied': "⚠️ Penalty 50% ({:.2f} ₽) deducted from developer for previous uncompleted order.",
        'dev_cancel_confirm': "❌ Are you sure you want to cancel? A 50% penalty from your next completed order will apply.",
        'dev_cancelled': "❌ Order cancelled by developer. Penalty applied.",
        'list_title': "📋 Available orders:",
        'list_empty': "No available orders.",
        'take_order': "✅ Take order #{}",
        'order_taken': "✅ Order #{} taken.",
        'dev_work_panel': "🔨 Work progress",
        'dev_extend_deadline': "⏳ Extend deadline (+{} days)",
        'deadline_extended': "Deadline extended by {} days. New deadline: {} days.",
        'dev_cancel_order': "❌ Cancel order",
        'admin_only': "🚫 Admin only.",
        'dev_only': "🚫 Developer only.",
        'cancel': "❌ Cancel",
        'back_to_menu': "🔙 Back to menu",
        'enter_custom_deadline': "Enter number of days:",
        'choose_deadline_buttons': "Choose deadline:",
        'day': "{} days",
        'admin_menu_title': "🔧 Admin panel\n\nChoose section:",
        'admin_orders_btn': "📦 Orders",
        'admin_deposits_btn': "💰 Deposits",
        'admin_withdrawals_btn': "🏦 Withdrawals",
        'admin_staff_btn': "👥 Staff management",
        'admin_broadcast_btn': "📢 Broadcast",
        'admin_promos_btn': "🎟 Promo codes",
        'staff_setdev': "Assign developer",
        'staff_removedev': "Remove developer",
        'staff_ban': "Ban",
        'staff_unban': "Unban",
        'staff_back': "🔙 Back",
        'order_details': "📦 Order #{}\n👤 Client: {}\n📱 {} | 📂 {}\n💰 {} ₽ | Deadline: {} days\n📝 {}",
    }
}

async def get_text(user_id: int, key: str, *args) -> str:
    lang = await get_user_lang(user_id)
    text = TEXTS.get(lang, TEXTS['ru']).get(key, key)
    try:
        return text.format(*args) if args else text
    except Exception:
        return text


# ==================== KEYBOARDS ====================
async def main_menu_keyboard(tg_id: int):
    user = await get_user(tg_id)
    role = user['role'] if user else 'user'
    lang = await get_user_lang(tg_id)
    t = TEXTS[lang]

    # Admin sees ALL buttons
    if role == 'admin':
        buttons = [
            [KeyboardButton(t['new_order']), KeyboardButton(t['my_orders'])],
            [KeyboardButton(await get_text(tg_id, 'my_balance', await get_balance(tg_id))), KeyboardButton(t['deposit'])],
            [KeyboardButton(t['referral']), KeyboardButton(t['settings'])],
            [KeyboardButton(t['developer_panel']), KeyboardButton(t['withdraw'])],
            [KeyboardButton(t['admin_panel'])],
        ]
    elif role == 'developer':
        buttons = [
            [KeyboardButton(t['new_order']), KeyboardButton(t['my_orders'])],
            [KeyboardButton(await get_text(tg_id, 'my_balance', await get_balance(tg_id))), KeyboardButton(t['deposit'])],
            [KeyboardButton(t['referral']), KeyboardButton(t['settings'])],
            [KeyboardButton(t['developer_panel']), KeyboardButton(t['withdraw'])],
        ]
    else:
        buttons = [
            [KeyboardButton(t['new_order']), KeyboardButton(t['my_orders'])],
            [KeyboardButton(await get_text(tg_id, 'my_balance', await get_balance(tg_id))), KeyboardButton(t['deposit'])],
            [KeyboardButton(t['referral']), KeyboardButton(t['settings'])],
        ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def cancel_keyboard(tg_id: int):
    lang = await get_user_lang(tg_id)
    t = TEXTS[lang]
    return ReplyKeyboardMarkup([[KeyboardButton(t['cancel'])]], resize_keyboard=True)

async def back_keyboard(tg_id: int):
    lang = await get_user_lang(tg_id)
    t = TEXTS[lang]
    return ReplyKeyboardMarkup([[KeyboardButton(t['back_to_menu'])]], resize_keyboard=True)

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    username = update.effective_user.username or "no_username"
    args = context.args
    clear_state(context)
    user = await get_user(tg_id)
    if user and user['banned']:
        await update.message.reply_text(await get_text(tg_id, 'banned'))
        return
    if not user:
        ref = args[0] if args else None
        await create_user(tg_id, username, ref)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
             InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
        ])
        await update.message.reply_text("👋 Welcome / Добро пожаловать!\nChoose language / Выберите язык:", reply_markup=kb)
    else:
        await update.message.reply_text(await get_text(tg_id, 'menu'), reply_markup=await main_menu_keyboard(tg_id))

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    clear_state(context)
    if tg_id != ADMIN_ID:
        await update.message.reply_text(await get_text(tg_id, 'admin_only'))
        return
    lang = await get_user_lang(tg_id)
    t = TEXTS[lang]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['admin_orders_btn'], callback_data="admin_orders")],
        [InlineKeyboardButton(t['admin_deposits_btn'], callback_data="admin_deposits")],
        [InlineKeyboardButton(t['admin_withdrawals_btn'], callback_data="admin_withdrawals")],
        [InlineKeyboardButton(t['admin_staff_btn'], callback_data="admin_staff")],
        [InlineKeyboardButton(t['admin_broadcast_btn'], callback_data="admin_broadcast")],
        [InlineKeyboardButton(t['admin_promos_btn'], callback_data="admin_promos")],
    ])
    await update.message.reply_text(t['admin_menu_title'], reply_markup=kb)

async def cmd_dev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    clear_state(context)
    user = await get_user(tg_id)
    if not user or user['role'] not in ('developer', 'admin'):
        await update.message.reply_text(await get_text(tg_id, 'dev_only'))
        return

    active_orders = await get_orders_by_developer(tg_id)
    if active_orders:
        order = active_orders[0]
        lang = await get_user_lang(tg_id)
        t = TEXTS[lang]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['send_test_bot_btn'], callback_data=f"dev_sendbot_{order['id']}")],
            [InlineKeyboardButton(t['dev_extend_deadline'].format(DEV_DEADLINE_EXTENSION), callback_data=f"dev_extend_{order['id']}")],
            [InlineKeyboardButton(t['dev_cancel_order'], callback_data=f"dev_cancelconfirm_{order['id']}")],
        ])
        await update.message.reply_text(
            f"📦 Заказ #{order['id']}\n📱 {order['platform']} | 📂 {order['topic']}\n⏳ Срок: {order['deadline_days']} дней\n📝 {order['description']}",
            reply_markup=kb
        )
    else:
        await update.message.reply_text("Нет активных заказов. Используйте /list чтобы найти доступные.")

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    clear_state(context)
    user = await get_user(tg_id)
    if not user or user['role'] not in ('developer', 'admin'):
        await update.message.reply_text(await get_text(tg_id, 'dev_only'))
        return

    if user['role'] == 'developer':
        active = await get_orders_by_developer(tg_id)
        if active:
            await update.message.reply_text(await get_text(tg_id, 'dev_max_orders'))
            return

    orders = await get_available_orders()
    if not orders:
        await update.message.reply_text(await get_text(tg_id, 'list_empty'))
        return

    await update.message.reply_text(await get_text(tg_id, 'list_title'))
    for o in orders:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await get_text(tg_id, 'take_order', o['id']), callback_data=f"list_take_{o['id']}")]
        ])
        await update.message.reply_text(
            f"📦 Заказ #{o['id']}\n📱 {o['platform']} | 📂 {o['topic']}\n💰 {o['price']} ₽ | ⏳ {o['deadline_days']} дней\n📝 {o['description'][:100]}...",
            reply_markup=kb
        )

async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split('_')[1]
    tg_id = update.effective_user.id
    await update_user_language(tg_id, lang)
    await query.edit_message_text(await get_text(tg_id, 'language_set'))
    await context.bot.send_message(chat_id=tg_id, text=await get_text(tg_id, 'menu'), reply_markup=await main_menu_keyboard(tg_id))


# ==================== TEXT HANDLER ====================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    text = update.message.text
    user = await get_user(tg_id)
    if not user:
        await start(update, context)
        return
    if user['banned']:
        await update.message.reply_text(await get_text(tg_id, 'banned'))
        return
    lang = user['language']
    t = TEXTS[lang]

    # Cancel button pressed
    if text == t['cancel'] or text == t['back_to_menu']:
        clear_state(context)
        await update.message.reply_text(t['menu'], reply_markup=await main_menu_keyboard(tg_id))
        return

    state = context.user_data.get('state')

    if state == 'order_desc':
        context.user_data['description'] = text
        context.user_data['state'] = 'order_promo'
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['use_promo'], callback_data="promo_yes")],
            [InlineKeyboardButton(t['skip_promo'], callback_data="promo_no")]
        ])
        await update.message.reply_text(t['enter_promo_code'], reply_markup=kb)
        return
    elif state == 'order_promo_input':
        promo_code = None
        if text.strip():
            promo = await get_promo_code(text.strip())
            if promo and promo['uses_count'] < promo['max_uses']:
                promo_code = text.strip().upper()
                await update.message.reply_text(t['promo_applied'].format(promo['value']))
            else:
                await update.message.reply_text(t['invalid_promo'])
                return
        order_id = await create_order(tg_id, context.user_data['platform'], context.user_data['topic'], context.user_data['description'], promo_code)
        user_data = await get_user(tg_id)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=await get_text(ADMIN_ID, 'new_order_admin', order_id, user_data['username'] or "N/A", tg_id, context.user_data['platform'], context.user_data['topic'], context.user_data['description'], promo_code or "-"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(await get_text(ADMIN_ID, 'set_price'), callback_data=f"admin_setprice_{order_id}")]
            ])
        )
        clear_state(context)
        await update.message.reply_text(t['order_created'].format(order_id), reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'enter_price':
        try:
            price = float(text.strip())
        except ValueError:
            await update.message.reply_text("Введите число.", reply_markup=await cancel_keyboard(tg_id))
            return
        context.user_data['temp_price'] = price
        context.user_data['state'] = 'enter_deadline'
        order_id = context.user_data['admin_order_id']
        await update.message.reply_text(t['enter_deadline'].format(order_id), reply_markup=await cancel_keyboard(tg_id))
        return
    elif state == 'enter_deadline':
        try:
            days = int(text.strip())
        except ValueError:
            await update.message.reply_text("Введите целое число.", reply_markup=await cancel_keyboard(tg_id))
            return
        order_id = context.user_data['admin_order_id']
        price = context.user_data['temp_price']
        await update_order(order_id, price=price, deadline_days=days, status='price_set')
        order = await get_order(order_id)
        prepayment_text = t['prepayment_required'].format(price, PREPAYMENT_LIMIT) if price < PREPAYMENT_LIMIT else t['no_prepayment']
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['accept_price'], callback_data=f"user_acceptprice_{order_id}")],
            [InlineKeyboardButton(t['suggest_price'], callback_data=f"user_suggestprice_{order_id}")],
            [InlineKeyboardButton(t['cancel_order'], callback_data=f"user_cancelorder_{order_id}")]
        ])
        await context.bot.send_message(
            chat_id=order['user_id'],
            text=t['price_set'].format(order_id, price, days, prepayment_text),
            reply_markup=kb
        )
        clear_state(context)
        await update.message.reply_text(t['price_updated'], reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'user_suggest_price':
        try:
            price = float(text.strip())
        except ValueError:
            await update.message.reply_text("Введите число.", reply_markup=await cancel_keyboard(tg_id))
            return
        context.user_data['temp_negoprice'] = price
        context.user_data['state'] = 'user_suggest_deadline'
        await update.message.reply_text(t['enter_your_deadline'], reply_markup=await cancel_keyboard(tg_id))
        return
    elif state == 'user_suggest_deadline':
        try:
            days = int(text.strip())
        except ValueError:
            await update.message.reply_text("Введите целое число.", reply_markup=await cancel_keyboard(tg_id))
            return
        order_id = context.user_data['suggest_order_id']
        price = context.user_data['temp_negoprice']
        await update_order(order_id, status='price_negotiation')
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Клиент предложил цену {price} ₽, срок {days} дней для заказа #{order_id}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Принять", callback_data=f"admin_acceptnegoprice_{order_id}_{price}_{days}")],
                [InlineKeyboardButton("Отклонить", callback_data=f"admin_rejectnegoprice_{order_id}")]
            ])
        )
        clear_state(context)
        await update.message.reply_text(t['price_sent'], reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'dev_send_bot':
        order_id = context.user_data['dev_order_id']
        username = text.strip()
        await update_order(order_id, temp_bot_username=username, status='testing')
        order = await get_order(order_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await get_text(order['user_id'], 'next'), callback_data=f"user_testnext_{order_id}")]
        ])
        await context.bot.send_message(
            chat_id=order['user_id'],
            text=await get_text(order['user_id'], 'test_bot_sent', username),
            reply_markup=kb
        )
        clear_state(context)
        await update.message.reply_text(t['test_bot_received'], reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'user_revision':
        order_id = context.user_data['revision_order_id']
        order = await get_order(order_id)
        new_count = order['revision_count'] + 1
        if new_count > 3:
            await update.message.reply_text(t['max_revisions'])
            clear_state(context)
            return
        await update_order(order_id, revision_count=new_count, status='revision')
        await context.bot.send_message(
            chat_id=order['developer_id'],
            text=f"🔧 Правки по заказу #{order_id} ({new_count}/3):\n{text}"
        )
        clear_state(context)
        await update.message.reply_text(t['revision_sent'].format(3 - new_count), reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'user_review_text':
        order_id = context.user_data['review_order_id']
        rating = context.user_data['review_rating']
        await create_review(order_id, tg_id, rating, text)
        await update_order(order_id, status='reviewed')
        order = await get_order(order_id)
        user_data = await get_user(tg_id)
        channel_text = f"⭐ Отзыв по заказу #{order_id}\nОценка: {'⭐' * rating}\nКлиент: @{user_data['username'] or 'N/A'}\nТекст: {text}"
        await context.bot.send_message(chat_id=REVIEWS_CHANNEL, text=channel_text)
        clear_state(context)
        await update.message.reply_text(t['review_thanks'], reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'deposit_amount':
        try:
            amount = float(text.strip())
        except ValueError:
            await update.message.reply_text("Введите число.", reply_markup=await cancel_keyboard(tg_id))
            return
        context.user_data['deposit_amount'] = amount
        context.user_data['state'] = 'deposit_proof'
        await update.message.reply_text(
            t['deposit_info'].format(amount, CARD_DETAILS, tg_id),
            reply_markup=ReplyKeyboardRemove()
        )
        return
    elif state == 'withdraw_amount':
        parts = text.split(',')
        if len(parts) != 3:
            await update.message.reply_text("Неверный формат. Введите через запятую.", reply_markup=await cancel_keyboard(tg_id))
            return
        try:
            amount = float(parts[0].strip())
        except ValueError:
            await update.message.reply_text("Неверная сумма.", reply_markup=await cancel_keyboard(tg_id))
            return
        initials = parts[1].strip()
        card = parts[2].strip()
        balance = await get_balance(tg_id)
        if balance < amount:
            await update.message.reply_text(t['insufficient_funds'].format(amount, balance), reply_markup=await main_menu_keyboard(tg_id))
            return
        req_id = await create_withdrawal_request(tg_id, amount, initials, card)
        user_data = await get_user(tg_id)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=await get_text(ADMIN_ID, 'new_withdrawal', req_id, user_data['username'] or "N/A", tg_id, amount, initials, card),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(await get_text(ADMIN_ID, 'confirm'), callback_data=f"conf_withdraw_{req_id}"),
                 InlineKeyboardButton(await get_text(ADMIN_ID, 'reject'), callback_data=f"rej_withdraw_{req_id}")]
            ])
        )
        clear_state(context)
        await update.message.reply_text(t['withdraw_sent'], reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'admin_broadcast':
        users = await get_all_users()
        count = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u['tg_id'], text=text)
                count += 1
            except Exception:
                pass
        clear_state(context)
        await update.message.reply_text(t['broadcast_done'].format(count), reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'admin_promo':
        parts = text.split(',')
        if len(parts) != 4:
            await update.message.reply_text("Неверный формат.", reply_markup=await cancel_keyboard(tg_id))
            return
        code = parts[0].strip().upper()
        ptype = parts[1].strip()
        try:
            value = float(parts[2].strip())
            max_uses = int(parts[3].strip())
        except ValueError:
            await update.message.reply_text("Неверные числа.", reply_markup=await cancel_keyboard(tg_id))
            return
        await create_promo_code(code, ptype, value, max_uses)
        clear_state(context)
        await update.message.reply_text(t['promo_created'], reply_markup=await main_menu_keyboard(tg_id))
        return
    elif state == 'admin_staff':
        target_id = None
        if text.isdigit():
            target_id = int(text)
        elif text.startswith('@'):
            async with aiosqlite.connect(DB_NAME) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT tg_id FROM users WHERE username = ?", (text.lstrip('@'),)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        target_id = dict(row)['tg_id']
        if not target_id:
            await update.message.reply_text("Пользователь не найден.", reply_markup=await cancel_keyboard(tg_id))
            return
        action = context.user_data.get('staff_action')
        if action == 'setdev':
            await update_user_role(target_id, 'developer')
            msg = t['dev_assigned']
        elif action == 'removedev':
            await update_user_role(target_id, 'user')
            msg = t['dev_removed']
        elif action == 'ban':
            await ban_user(target_id, 1)
            msg = t['user_banned']
        elif action == 'unban':
            await ban_user(target_id, 0)
            msg = t['user_unbanned']
        else:
            msg = "Готово."
        clear_state(context)
        await update.message.reply_text(msg, reply_markup=await main_menu_keyboard(tg_id))
        return

    # Main menu buttons
    if text == t['new_order']:
        clear_state(context)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['telegram'], callback_data="platform_telegram"),
             InlineKeyboardButton(t['vk'], callback_data="platform_vk")]
        ])
        await update.message.reply_text(t['choose_platform'], reply_markup=kb)
    elif text == t['my_orders']:
        clear_state(context)
        orders = await get_orders_by_user(tg_id)
        if not orders:
            await update.message.reply_text(t['no_orders'])
            return
        msg = ""
        for o in orders:
            status_key = f"status_{o['status']}"
            status_text = TEXTS[lang].get(status_key, o['status'])
            if o['status'] == 'revision':
                status_text = status_text.format(o['revision_count'])
            msg += t['order_list'].format(o['id'], status_text) + "\n"
        await update.message.reply_text(msg, reply_markup=await main_menu_keyboard(tg_id))
    elif text.startswith("💰 Баланс") or text.startswith("💰 Balance"):
        clear_state(context)
        bal = await get_balance(tg_id)
        await update.message.reply_text(t['my_balance'].format(bal), reply_markup=await main_menu_keyboard(tg_id))
    elif text == t['deposit']:
        clear_state(context)
        context.user_data['state'] = 'deposit_amount'
        await update.message.reply_text(t['enter_deposit'], reply_markup=await cancel_keyboard(tg_id))
    elif text == t['withdraw']:
        clear_state(context)
        context.user_data['state'] = 'withdraw_amount'
        await update.message.reply_text(t['enter_withdraw'], reply_markup=await cancel_keyboard(tg_id))
    elif text == t['referral']:
        clear_state(context)
        user_data = await get_user(tg_id)
        bot_username = (await context.bot.get_me()).username
        await update.message.reply_text(t['referral_text'].format(bot_username, user_data['referral_code'], int(REFERRAL_PERCENT)), reply_markup=await main_menu_keyboard(tg_id))
    elif text == t['settings']:
        clear_state(context)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
             InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")]
        ])
        await update.message.reply_text(t['choose_language'], reply_markup=kb)
    elif text == t['admin_panel']:
        clear_state(context)
        if tg_id == ADMIN_ID:
            await cmd_admin(update, context)
        else:
            await update.message.reply_text(t['admin_only'])
    elif text == t['developer_panel']:
        clear_state(context)
        if user['role'] in ('developer', 'admin'):
            await cmd_dev(update, context)
        else:
            await update.message.reply_text(t['dev_only'])
    else:
        clear_state(context)
        await update.message.reply_text(t['menu'], reply_markup=await main_menu_keyboard(tg_id))


# ==================== CALLBACK HANDLER ====================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tg_id = update.effective_user.id
    user = await get_user(tg_id)
    if not user:
        return
    lang = user['language']
    t = TEXTS[lang]

    if data.startswith("platform_"):
        platform = data.split('_')[1]
        context.user_data['platform'] = platform
        topics = [
            [InlineKeyboardButton(t['business'], callback_data="topic_business")],
            [InlineKeyboardButton(t['game'], callback_data="topic_game")],
            [InlineKeyboardButton(t['education'], callback_data="topic_education")],
            [InlineKeyboardButton(t['entertainment'], callback_data="topic_entertainment")],
            [InlineKeyboardButton(t['other'], callback_data="topic_other")],
        ]
        await query.edit_message_text(t['choose_topic'], reply_markup=InlineKeyboardMarkup(topics))
    elif data.startswith("topic_"):
        topic = data.split('_')[1]
        context.user_data['topic'] = topic
        context.user_data['state'] = 'order_desc'
        await query.edit_message_text(t['send_tz'])
        await context.bot.send_message(chat_id=tg_id, text=t['send_tz'], reply_markup=await cancel_keyboard(tg_id))
    elif data == "promo_yes":
        context.user_data['state'] = 'order_promo_input'
        await query.edit_message_text("Введите промокод:")
        await context.bot.send_message(chat_id=tg_id, text="Введите промокод:", reply_markup=await cancel_keyboard(tg_id))
    elif data == "promo_no":
        order_id = await create_order(tg_id, context.user_data['platform'], context.user_data['topic'], context.user_data['description'], None)
        user_data = await get_user(tg_id)
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=t['new_order_admin'].format(order_id, user_data['username'] or "N/A", tg_id, context.user_data['platform'], context.user_data['topic'], context.user_data['description'], "-"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t['set_price'], callback_data=f"admin_setprice_{order_id}")]
            ])
        )
        clear_state(context)
        await query.edit_message_text(t['order_created'].format(order_id))
        await context.bot.send_message(chat_id=tg_id, text=t['menu'], reply_markup=await main_menu_keyboard(tg_id))
    elif data.startswith("setlang_"):
        lang = data.split('_')[1]
        await update_user_language(tg_id, lang)
        await query.edit_message_text(t['language_set'])
        await context.bot.send_message(chat_id=tg_id, text=t['menu'], reply_markup=await main_menu_keyboard(tg_id))
    elif data.startswith("admin_setprice_"):
        order_id = int(data.split('_')[2])
        context.user_data['admin_order_id'] = order_id
        context.user_data['state'] = 'enter_price'
        await query.edit_message_text(t['enter_price'].format(order_id))
        await context.bot.send_message(chat_id=tg_id, text=t['enter_price'].format(order_id), reply_markup=await cancel_keyboard(tg_id))
    elif data.startswith("user_acceptprice_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        price = order['price']
        if price < PREPAYMENT_LIMIT:
            balance = await get_balance(tg_id)
            if balance < price:
                await query.edit_message_text(t['not_enough_balance'])
                return
            await update_balance(tg_id, -price)
            await update_order(order_id, status='waiting_prepayment')
            await query.edit_message_text(t['prepayment_done'].format(price))
        else:
            await update_order(order_id, status='in_progress')
            await query.edit_message_text(t['order_confirmed'])
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Заказ #{order_id} подтвержден клиентом. Назначьте разработчика или используйте /list.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Назначить разработчика", callback_data=f"admin_assigndev_{order_id}")]
            ])
        )
    elif data.startswith("user_suggestprice_"):
        order_id = int(data.split('_')[2])
        context.user_data['suggest_order_id'] = order_id
        context.user_data['state'] = 'user_suggest_price'
        await query.edit_message_text(t['enter_your_price'])
        await context.bot.send_message(chat_id=tg_id, text=t['enter_your_price'], reply_markup=await cancel_keyboard(tg_id))
    elif data.startswith("user_cancelorder_"):
        order_id = int(data.split('_')[2])
        await update_order(order_id, status='cancelled')
        await query.edit_message_text(t['order_cancelled'])
    elif data.startswith("admin_acceptnegoprice_"):
        parts = data.split('_')
        order_id = int(parts[2])
        price = float(parts[3])
        days = int(parts[4])
        await update_order(order_id, price=price, deadline_days=days, status='price_set')
        order = await get_order(order_id)
        prepayment_text = t['prepayment_required'].format(price, PREPAYMENT_LIMIT) if price < PREPAYMENT_LIMIT else t['no_prepayment']
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['accept_price'], callback_data=f"user_acceptprice_{order_id}")],
            [InlineKeyboardButton(t['cancel_order'], callback_data=f"user_cancelorder_{order_id}")]
        ])
        await context.bot.send_message(
            chat_id=order['user_id'],
            text=t['price_set'].format(order_id, price, days, prepayment_text),
            reply_markup=kb
        )
        await query.edit_message_text("Цена и срок обновлены и отправлены клиенту.")
    elif data.startswith("admin_rejectnegoprice_"):
        order_id = int(data.split('_')[2])
        await query.edit_message_text(f"Заказ #{order_id}: предложение отклонено. Ожидайте цену от админа.")
    elif data.startswith("admin_assigndev_"):
        order_id = int(data.split('_')[2])
        developers = await get_developers()
        if not developers:
            await query.edit_message_text(t['no_developers'])
            return
        buttons = []
        for dev in developers:
            buttons.append([InlineKeyboardButton(f"{dev['username'] or dev['tg_id']}", callback_data=f"admin_setdev_{order_id}_{dev['tg_id']}")])
        buttons.append([InlineKeyboardButton(t['back'], callback_data="admin_back_orders")])
        await query.edit_message_text(t['choose_developer'].format(order_id), reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("admin_setdev_"):
        parts = data.split('_')
        order_id = int(parts[2])
        dev_id = int(parts[3])
        await update_order(order_id, developer_id=dev_id, status='in_progress')
        order = await get_order(order_id)
        await context.bot.send_message(
            chat_id=dev_id,
            text=await get_text(dev_id, 'developer_assigned', order_id, order['platform'], order['topic'], order['description'], order['deadline_days']),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(await get_text(dev_id, 'send_test_bot_btn'), callback_data=f"dev_sendbot_{order_id}")]
            ])
        )
        await query.edit_message_text(t['developer_set'])
    elif data == "admin_back_orders":
        await query.edit_message_text("Отменено.")
    elif data.startswith("dev_sendbot_"):
        order_id = int(data.split('_')[2])
        context.user_data['dev_order_id'] = order_id
        context.user_data['state'] = 'dev_send_bot'
        await query.edit_message_text(t['send_test_bot'])
        await context.bot.send_message(chat_id=tg_id, text=t['send_test_bot'], reply_markup=await cancel_keyboard(tg_id))
    elif data.startswith("user_testnext_"):
        order_id = int(data.split('_')[2])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['pay'], callback_data=f"user_payorder_{order_id}")],
            [InlineKeyboardButton(t['revision'], callback_data=f"user_revision_{order_id}")],
            [InlineKeyboardButton(t['refuse'], callback_data=f"user_refuse_{order_id}")]
        ])
        await query.edit_message_text(t['choose_action'], reply_markup=kb)
    elif data.startswith("user_payorder_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        price = order['price']
        if order['promo_code']:
            promo = await get_promo_code(order['promo_code'])
            if promo:
                if promo['type'] == 'percent':
                    discount = price * (promo['value'] / 100)
                else:
                    discount = promo['value']
                final_price = max(0, price - discount)
                await use_promo_code(order['promo_code'])
            else:
                final_price = price
        else:
            final_price = price

        if order['price'] < PREPAYMENT_LIMIT:
            remaining = final_price - order['price']
            if remaining > 0:
                balance = await get_balance(tg_id)
                if balance < remaining:
                    await query.edit_message_text(t['insufficient_funds'].format(remaining, balance))
                    return
                await update_balance(tg_id, -remaining)
        else:
            balance = await get_balance(tg_id)
            if balance < final_price:
                await query.edit_message_text(t['insufficient_funds'].format(final_price, balance))
                return
            await update_balance(tg_id, -final_price)

        await update_order(order_id, final_price=final_price, status='paid')
        user_data = await get_user(tg_id)
        if user_data and user_data['referred_by']:
            bonus = final_price * (REFERRAL_PERCENT / 100)
            await update_balance(int(user_data['referred_by']), bonus)
        if order['developer_id']:
            dev_bonus = final_price * (DEV_PERCENT / 100)
            dev_user = await get_user(order['developer_id'])
            if dev_user and dev_user['dev_penalty'] > 0:
                penalty = min(dev_bonus, dev_user['dev_penalty'])
                dev_bonus -= penalty
                await update_dev_penalty(order['developer_id'], -penalty)
                await context.bot.send_message(
                    chat_id=order['developer_id'],
                    text=await get_text(order['developer_id'], 'dev_penalty_applied', penalty)
                )
            await update_balance(order['developer_id'], dev_bonus)

        await query.edit_message_text(t['order_paid'])
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=t['send_zip_admin'].format(order_id),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(await get_text(ADMIN_ID, 'send_zip_btn'), callback_data=f"admin_sendzip_{order_id}")]
            ])
        )
    elif data.startswith("user_revision_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        if order['revision_count'] >= 3:
            await query.edit_message_text(t['max_revisions'])
            return
        context.user_data['revision_order_id'] = order_id
        context.user_data['state'] = 'user_revision'
        await query.edit_message_text(t['enter_revision'])
        await context.bot.send_message(chat_id=tg_id, text=t['enter_revision'], reply_markup=await cancel_keyboard(tg_id))
    elif data.startswith("user_refuse_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        msg = t['no_prepayment_return']
        if order['price'] < PREPAYMENT_LIMIT:
            msg = t['prepayment_kept'].format(order['price'], PREPAYMENT_LIMIT)
        await update_order(order_id, status='cancelled')
        await query.edit_message_text(t['order_refused'].format(msg))
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Клиент отказался от заказа #{order_id}. {msg}")
        if order['developer_id']:
            await context.bot.send_message(chat_id=order['developer_id'], text=f"❌ Заказ #{order_id} отменен клиентом.")
    elif data.startswith("admin_sendzip_"):
        order_id = int(data.split('_')[2])
        context.user_data['zip_order_id'] = order_id
        context.user_data['state'] = 'admin_send_zip'
        await query.edit_message_text(t['send_zip_admin'].format(order_id))
        await context.bot.send_message(chat_id=tg_id, text=t['send_zip_admin'].format(order_id))
    elif data.startswith("review_"):
        parts = data.split('_')
        order_id = int(parts[1])
        rating = int(parts[2])
        context.user_data['review_order_id'] = order_id
        context.user_data['review_rating'] = rating
        context.user_data['state'] = 'user_review_text'
        await query.edit_message_text(t['review_text'])
        await context.bot.send_message(chat_id=tg_id, text=t['review_text'], reply_markup=await cancel_keyboard(tg_id))
    elif data == "admin_orders":
        orders = await get_pending_orders()
        if not orders:
            await query.edit_message_text("Нет активных заказов.")
            return
        text = "📦 Заказы:\n"
        for o in orders:
            text += f"#{o['id']} | {o['status']} | {o['platform']} | {o['topic']}\n"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t['back'], callback_data="admin_back")]])
        await query.edit_message_text(text, reply_markup=kb)
    elif data == "admin_deposits":
        reqs = await get_pending_balance_requests()
        if not reqs:
            await query.edit_message_text("Нет заявок на пополнение.")
            return
        for r in reqs:
            user_data = await get_user(r['user_id'])
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=r['screenshot_file_id'],
                caption=t['new_balance_req'].format(r['id'], user_data['username'] or "N/A", r['user_id'], r['amount']),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t['confirm'], callback_data=f"conf_deposit_{r['id']}"),
                     InlineKeyboardButton(t['reject'], callback_data=f"rej_deposit_{r['id']}")]
                ])
            )
        await query.edit_message_text("Заявки отправлены выше.")
    elif data == "admin_withdrawals":
        reqs = await get_pending_withdrawals()
        if not reqs:
            await query.edit_message_text("Нет заявок на вывод.")
            return
        for r in reqs:
            user_data = await get_user(r['user_id'])
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=t['new_withdrawal'].format(r['id'], user_data['username'] or "N/A", r['user_id'], r['amount'], r['initials'], r['card_details']),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t['confirm'], callback_data=f"conf_withdraw_{r['id']}"),
                     InlineKeyboardButton(t['reject'], callback_data=f"rej_withdraw_{r['id']}")]
                ])
            )
        await query.edit_message_text("Заявки отправлены выше.")
    elif data.startswith("conf_deposit_"):
        req_id = int(data.split('_')[2])
        req = await get_balance_request(req_id)
        if not req or req['status'] != 'pending':
            await query.edit_message_text("Уже обработано.")
            return
        await update_balance_request(req_id, 'confirmed')
        await update_balance(req['user_id'], req['amount'])
        await context.bot.send_message(req['user_id'], t['balance_confirmed'].format(req['amount']))
        await query.edit_message_text(f"✅ Пополнение #{req_id} подтверждено.")
    elif data.startswith("rej_deposit_"):
        req_id = int(data.split('_')[2])
        req = await get_balance_request(req_id)
        await update_balance_request(req_id, 'rejected')
        if req:
            await context.bot.send_message(req['user_id'], t['balance_rejected'])
        await query.edit_message_text("❌ Отклонено.")
    elif data.startswith("conf_withdraw_"):
        req_id = int(data.split('_')[2])
        req = await get_withdrawal_request(req_id)
        if not req or req['status'] != 'pending':
            await query.edit_message_text("Уже обработано.")
            return
        await update_withdrawal(req_id, 'confirmed')
        await update_balance(req['user_id'], -req['amount'])
        await context.bot.send_message(req['user_id'], t['withdrawal_confirmed'])
        await query.edit_message_text(f"✅ Вывод #{req_id} подтвержден.")
    elif data.startswith("rej_withdraw_"):
        req_id = int(data.split('_')[2])
        req = await get_withdrawal_request(req_id)
        await update_withdrawal(req_id, 'rejected')
        if req:
            await context.bot.send_message(req['user_id'], t['withdrawal_rejected'])
        await query.edit_message_text("❌ Отклонено.")
    elif data == "admin_staff":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['staff_setdev'], callback_data="staff_setdev")],
            [InlineKeyboardButton(t['staff_removedev'], callback_data="staff_removedev")],
            [InlineKeyboardButton(t['staff_ban'], callback_data="staff_ban")],
            [InlineKeyboardButton(t['staff_unban'], callback_data="staff_unban")],
            [InlineKeyboardButton(t['staff_back'], callback_data="admin_back")],
        ])
        await query.edit_message_text("Управление персоналом", reply_markup=kb)
    elif data.startswith("staff_"):
        action = data.split('_')[1]
        context.user_data['staff_action'] = action
        context.user_data['state'] = 'admin_staff'
        await query.edit_message_text(t['enter_user_id'])
        await context.bot.send_message(chat_id=tg_id, text=t['enter_user_id'], reply_markup=await cancel_keyboard(tg_id))
    elif data == "admin_broadcast":
        context.user_data['state'] = 'admin_broadcast'
        await query.edit_message_text(t['enter_broadcast'])
        await context.bot.send_message(chat_id=tg_id, text=t['enter_broadcast'], reply_markup=await cancel_keyboard(tg_id))
    elif data == "admin_promos":
        context.user_data['state'] = 'admin_promo'
        await query.edit_message_text(t['enter_promo'])
        await context.bot.send_message(chat_id=tg_id, text=t['enter_promo'], reply_markup=await cancel_keyboard(tg_id))
    elif data == "admin_back":
        await query.edit_message_text("Назад.")
        await context.bot.send_message(chat_id=tg_id, text=t['menu'], reply_markup=await main_menu_keyboard(tg_id))
    elif data.startswith("list_take_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        if not order or order['developer_id']:
            await query.edit_message_text("Заказ уже взят.")
            return
        if user['role'] == 'developer':
            active = await get_orders_by_developer(tg_id)
            if active:
                await query.edit_message_text(t['dev_max_orders'])
                return
        await update_order(order_id, developer_id=tg_id, status='in_progress')
        await query.edit_message_text(t['order_taken'].format(order_id))
        await context.bot.send_message(
            chat_id=order['user_id'],
            text=f"🔔 Разработчик назначен на ваш заказ #{order_id}. Разработка началась."
        )
    elif data.startswith("dev_extend_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        if not order or order['developer_id'] != tg_id:
            await query.edit_message_text("Не ваш заказ.")
            return
        new_days = (order['deadline_days'] or 0) + DEV_DEADLINE_EXTENSION
        await update_order(order_id, deadline_days=new_days)
        await query.edit_message_text(t['deadline_extended'].format(DEV_DEADLINE_EXTENSION, new_days))
        await context.bot.send_message(
            chat_id=order['user_id'],
            text=f"📅 Срок заказа #{order_id} продлен на {DEV_DEADLINE_EXTENSION} дней. Новый срок: {new_days} дней."
        )
    elif data.startswith("dev_cancelconfirm_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        if not order or order['developer_id'] != tg_id:
            await query.edit_message_text("Не ваш заказ.")
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, отменить", callback_data=f"dev_cancel_{order_id}")],
            [InlineKeyboardButton(t['back'], callback_data=f"dev_back_{order_id}")]
        ])
        await query.edit_message_text(t['dev_cancel_confirm'], reply_markup=kb)
    elif data.startswith("dev_cancel_"):
        order_id = int(data.split('_')[2])
        order = await get_order(order_id)
        if not order or order['developer_id'] != tg_id:
            await query.edit_message_text("Не ваш заказ.")
            return
        penalty_amount = (order['price'] or 0) * (DEV_PENALTY_PERCENT / 100)
        await update_dev_penalty(tg_id, penalty_amount)
        await update_order(order_id, developer_id=None, status='price_set')
        await query.edit_message_text(t['dev_cancelled'])
        if order['price'] and order['price'] < PREPAYMENT_LIMIT:
            await update_balance(order['user_id'], order['price'])
            await context.bot.send_message(
                chat_id=order['user_id'],
                text=f"❌ Заказ #{order_id} отменен разработчиком. Предоплата {order['price']} ₽ возвращена на баланс."
            )
        else:
            await context.bot.send_message(
                chat_id=order['user_id'],
                text=f"❌ Заказ #{order_id} отменен разработчиком. Предоплата не требовалась."
            )
    elif data.startswith("dev_back_"):
        await query.edit_message_text("Отменено.")
    else:
        await query.edit_message_text("Неизвестная команда.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    state = context.user_data.get('state')
    if state == 'deposit_proof':
        photo_id = update.message.photo[-1].file_id
        amount = context.user_data['deposit_amount']
        req_id = await create_balance_request(tg_id, amount, photo_id)
        user_data = await get_user(tg_id)
        lang = await get_user_lang(tg_id)
        t = TEXTS[lang]
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_id,
            caption=t['new_balance_req'].format(req_id, user_data['username'] or "N/A", tg_id, amount),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t['confirm'], callback_data=f"conf_deposit_{req_id}"),
                 InlineKeyboardButton(t['reject'], callback_data=f"rej_deposit_{req_id}")]
            ])
        )
        clear_state(context)
        await update.message.reply_text(t['deposit_sent'], reply_markup=await main_menu_keyboard(tg_id))
    else:
        await update.message.reply_text("Фото не ожидалось.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    state = context.user_data.get('state')
    if state == 'admin_send_zip' and tg_id == ADMIN_ID:
        order_id = context.user_data['zip_order_id']
        order = await get_order(order_id)
        file_id = update.message.document.file_id
        lang = await get_user_lang(order['user_id'])
        t = TEXTS[lang]
        await context.bot.send_document(
            chat_id=order['user_id'],
            document=file_id,
            caption=t['zip_sent']
        )
        await update_order(order_id, status='delivered')
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("1⭐", callback_data=f"review_{order_id}_1"),
             InlineKeyboardButton("2⭐", callback_data=f"review_{order_id}_2"),
             InlineKeyboardButton("3⭐", callback_data=f"review_{order_id}_3"),
             InlineKeyboardButton("4⭐", callback_data=f"review_{order_id}_4"),
             InlineKeyboardButton("5⭐", callback_data=f"review_{order_id}_5")]
        ])
        await context.bot.send_message(
            chat_id=order['user_id'],
            text=t['leave_review'],
            reply_markup=kb
        )
        clear_state(context)
        await update.message.reply_text("ZIP отправлен клиенту.", reply_markup=await main_menu_keyboard(tg_id))
    else:
        await update.message.reply_text("Документ не ожидалось.")


# ==================== MAIN ====================
async def post_init(application: Application):
    await init_db()

def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", cmd_admin))
    application.add_handler(CommandHandler("dev", cmd_dev))
    application.add_handler(CommandHandler("list", cmd_list))

    application.add_handler(CallbackQueryHandler(set_language_callback, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(handle_callback))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ZIP, handle_document))

    application.run_polling()

if __name__ == "__main__":
    main()
