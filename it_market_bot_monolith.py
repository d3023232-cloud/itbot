#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IT Market Bot - Монолитный бот в одном файле
Профессиональная Telegram-платформа для управления заказами на разработку ботов

Автор: IT Market Platform
Версия: 1.0.0
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum

# ============================================================
# ИМПОРТЫ - УСТАНОВКА ЗАВИСИМОСТЕЙ
# ============================================================
try:
    from dotenv import load_dotenv
    from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, Enum as SQLEnum, ForeignKey
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, relationship
    from aiogram import Bot, Dispatcher, F, Router
    from aiogram.types import (
        Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
        BotCommand, FSInputFile
    )
    from aiogram.filters import Command, CommandStart
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import MemoryStorage
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("\n📦 Установите зависимости:")
    print("   pip install -r requirements-install.txt")
    sys.exit(1)

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else None
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///it_market_bot.db')

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не установлен в переменных окружения")
    sys.exit(1)

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# ПЕРЕЧИСЛЕНИЯ (ENUMS)
# ============================================================
class UserRole(str, Enum):
    """Роли пользователей"""
    USER = "user"           # Клиент
    DEVELOPER = "developer" # Разработчик
    ADMIN = "admin"        # Администратор

class OrderStatus(str, Enum):
    """Статусы заказов"""
    CREATED = "created"
    WAITING_ADMIN = "waiting_admin"
    APPROVED = "approved"
    IN_DEVELOPMENT = "in_development"
    TESTING = "testing"
    REVISION = "revision"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

# ============================================================
# DATABASE - МОДЕЛИ
# ============================================================
Base = declarative_base()

class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), unique=True)
    full_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(20))
    role = Column(SQLEnum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text)
    rating = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    orders_created = relationship('Order', foreign_keys='Order.customer_id', back_populates='customer')
    orders_developed = relationship('Order', foreign_keys='Order.developer_id', back_populates='developer')

class Order(Base):
    """Модель заказа"""
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    order_number = Column(String(50), unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    theme = Column(String(100))
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.CREATED)
    customer_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    developer_id = Column(Integer, ForeignKey('users.id'))
    admin_id = Column(Integer)
    total_price = Column(Float)
    developer_payment = Column(Float)
    market_payment = Column(Float)
    deadline = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)
    
    # Связи
    customer = relationship('User', foreign_keys=[customer_id], back_populates='orders_created')
    developer = relationship('User', foreign_keys=[developer_id], back_populates='orders_developed')

# ============================================================
# DATABASE - ИНИЦИАЛИЗАЦИЯ
# ============================================================
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={'check_same_thread': False} if 'sqlite' in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Инициализация БД"""
    Base.metadata.create_all(bind=engine)
    logger.info("✅ База данных инициализирована")

def get_db():
    """Получить сессию БД"""
    return SessionLocal()

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def get_order_number():
    """Генерирует уникальный номер заказа"""
    return f"Order-{datetime.now().strftime('%Y%m%d')}-{str(int(datetime.now().timestamp()))[-3:]}"

def is_admin(telegram_id: int) -> bool:
    """Проверка - администратор ли"""
    return telegram_id == ADMIN_ID

def get_status_emoji(status: OrderStatus) -> str:
    """Получить эмодзи статуса"""
    emojis = {
        OrderStatus.CREATED: "📝",
        OrderStatus.WAITING_ADMIN: "⏳",
        OrderStatus.APPROVED: "✅",
        OrderStatus.IN_DEVELOPMENT: "🔨",
        OrderStatus.TESTING: "🧪",
        OrderStatus.REVISION: "🔄",
        OrderStatus.COMPLETED: "🎉",
        OrderStatus.REJECTED: "❌",
        OrderStatus.CANCELLED: "🛑",
    }
    return emojis.get(status, "❓")

# ============================================================
# СОСТОЯНИЯ (FSM)
# ============================================================
class UserStates(StatesGroup):
    """Состояния для обычного пользователя"""
    creating_order = State()
    entering_order_title = State()
    entering_order_description = State()
    entering_order_budget = State()

class AdminStates(StatesGroup):
    """Состояния для администратора"""
    finding_order = State()
    finding_user = State()
    ban_reason = State()
    broadcast_message = State()
    assign_role = State()

# ============================================================
# TELEGRAM BOT - ИНИЦИАЛИЗАЦИЯ
# ============================================================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# ============================================================
# ОБРАБОТЧИКИ - КОМАНДА /START
# ============================================================
@router.message(CommandStart())
async def start_handler(message: Message):
    """Обработчик команды /start"""
    db = get_db()
    
    # Проверить/создать пользователя
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    if not user:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name
        )
        db.add(user)
        db.commit()
        logger.info(f"✅ Новый пользователь: {message.from_user.id}")
    
    db.close()
    
    if message.from_user.id == ADMIN_ID:
        text = (
            "🔐 **ADMIN PANEL**\n\n"
            "Добро пожаловать в IT Market Bot!\n\n"
            "Вы администратор. Используйте команды:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
            [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="admin_find_user")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="💰 Финансы", callback_data="admin_finance")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
        ])
    else:
        text = (
            "👋 **Добро пожаловать в IT Market Bot!**\n\n"
            "🤖 Профессиональная платформа для заказа и разработки ботов.\n\n"
            "📋 **Ваши опции:**"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Создать заказ", callback_data="create_order")],
            [InlineKeyboardButton(text="📋 Мои заказы", callback_data="my_orders")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="my_profile")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
        ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# ============================================================
# ОБРАБОТЧИКИ - ADMIN PANEL
# ============================================================
@router.callback_query(F.data == "admin_find_order")
async def admin_find_order(callback: CallbackQuery, state: FSMContext):
    """Начать поиск заказа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔍 **ПОИСК ЗАКАЗА**\n\n"
        "Введите ID заказа или номер (например: 42 или Order-20260611-001)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.finding_order)

@router.message(AdminStates.finding_order)
async def process_find_order(message: Message, state: FSMContext):
    """Обработка поиска заказа"""
    if not is_admin(message.from_user.id):
        return
    
    search_query = message.text.strip()
    db = get_db()
    
    # Поиск по ID или номеру
    order = None
    if search_query.isdigit():
        order = db.query(Order).filter(Order.id == int(search_query)).first()
    else:
        order = db.query(Order).filter(Order.order_number == search_query).first()
    
    if not order:
        await message.answer("❌ Заказ не найден")
        await state.clear()
        db.close()
        return
    
    # Показать детали заказа
    details = (
        f"📋 **ДЕТАЛИ ЗАКАЗА**\n\n"
        f"🔑 ID: {order.id}\n"
        f"📝 Номер: {order.order_number}\n"
        f"📌 Название: {order.title}\n"
        f"📖 Описание: {order.description[:100]}...\n"
        f"💰 Сумма: {order.total_price or 'Не установлена'} ₽\n"
        f"🟢 Статус: {get_status_emoji(order.status)} {order.status.value}\n\n"
        f"👤 Клиент: @{order.customer.username or 'unknown'}\n"
        f"🔨 Разработчик: {order.developer.username if order.developer else 'Не назначен'}\n"
        f"📅 Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать клиенту", callback_data=f"msg_customer_{order.id}")],
        [InlineKeyboardButton(text="⚙️ Изменить статус", callback_data=f"change_status_{order.id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await message.answer(details, reply_markup=keyboard, parse_mode="Markdown")
    await state.clear()
    db.close()

@router.callback_query(F.data == "admin_find_user")
async def admin_find_user(callback: CallbackQuery, state: FSMContext):
    """Начать поиск пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔎 **ПОИСК ПОЛЬЗОВАТЕЛЯ**\n\n"
        "Введите Telegram ID или username (например: 123456789 или @username)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.finding_user)

@router.message(AdminStates.finding_user)
async def process_find_user(message: Message, state: FSMContext):
    """Обработка поиска пользователя"""
    if not is_admin(message.from_user.id):
        return
    
    search_query = message.text.strip().replace('@', '')
    db = get_db()
    
    # Поиск по ID или username
    user = None
    if search_query.isdigit():
        user = db.query(User).filter(User.telegram_id == int(search_query)).first()
    else:
        user = db.query(User).filter(User.username == search_query).first()
    
    if not user:
        await message.answer("❌ Пользователь не найден")
        await state.clear()
        db.close()
        return
    
    # Получить статистику
    orders_count = db.query(Order).filter(Order.customer_id == user.id).count()
    projects_count = db.query(Order).filter(Order.developer_id == user.id).count()
    
    # Показать профиль
    details = (
        f"👤 **ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ**\n\n"
        f"🔑 Telegram ID: {user.telegram_id}\n"
        f"👻 Username: @{user.username or 'Не указан'}\n"
        f"📛 Имя: {user.full_name or 'Не указано'}\n"
        f"📧 Email: {user.email or 'Не указан'}\n\n"
        f"🎭 **Роль:** {user.role.value.upper()}\n"
        f"📊 **Статистика:**\n"
        f"📋 Заказов: {orders_count}\n"
        f"🔨 Проектов: {projects_count}\n"
        f"⭐ Рейтинг: {user.rating}/5.0\n\n"
        f"🟢 Статус: {'🟢 Активен' if user.is_active else '🔴 Заблокирован'}\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить" if user.is_active else "✅ Разбанить", 
                            callback_data=f"ban_user_{user.id}")],
        [InlineKeyboardButton(text="💬 Написать", callback_data=f"msg_user_{user.id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await message.answer(details, reply_markup=keyboard, parse_mode="Markdown")
    await state.clear()
    db.close()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Показать статистику"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    db = get_db()
    
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_orders = db.query(Order).count()
    completed = db.query(Order).filter(Order.status == OrderStatus.COMPLETED).count()
    in_dev = db.query(Order).filter(Order.status == OrderStatus.IN_DEVELOPMENT).count()
    
    stats = (
        f"📊 **СТАТИСТИКА ПЛАТФОРМЫ**\n\n"
        f"👥 **Пользователи:**\n"
        f"  Всего: {total_users}\n"
        f"  Активных: {active_users}\n\n"
        f"📋 **Заказы:**\n"
        f"  Всего: {total_orders}\n"
        f"  Завершено: {completed}\n"
        f"  В разработке: {in_dev}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(stats, reply_markup=keyboard, parse_mode="Markdown")
    db.close()

@router.callback_query(F.data == "admin_finance")
async def admin_finance(callback: CallbackQuery):
    """Финансовый отчет"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    db = get_db()
    
    completed_orders = db.query(Order).filter(Order.status == OrderStatus.COMPLETED).all()
    total_revenue = sum([o.market_payment or 0 for o in completed_orders])
    total_paid = sum([o.developer_payment or 0 for o in completed_orders])
    
    finance = (
        f"💰 **ФИНАНСОВЫЙ ОТЧЕТ**\n\n"
        f"✅ Завершенные заказы: {len(completed_orders)}\n"
        f"💵 Доход магазина: {total_revenue:.2f} ₽\n"
        f"💸 Выплачено разработчикам: {total_paid:.2f} ₽\n\n"
        f"📈 **Итого:**\n"
        f"  Общий доход: {total_revenue + total_paid:.2f} ₽"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(finance, reply_markup=keyboard, parse_mode="Markdown")
    db.close()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 **РАССЫЛКА**\n\n"
        "Введите сообщение для рассылки всем пользователям:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.broadcast_message)

@router.message(AdminStates.broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    """Обработка рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    db = get_db()
    users = db.query(User).filter(User.is_active == True).all()
    
    broadcast_text = f"📢 **ВАЖНОЕ СООБЩЕНИЕ**\n\n{message.text}"
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=broadcast_text,
                parse_mode="Markdown"
            )
            success += 1
        except:
            failed += 1
    
    result = (
        f"✅ Рассылка завершена\n\n"
        f"📨 Отправлено: {success}\n"
        f"❌ Ошибок: {failed}"
    )
    
    await message.answer(result)
    await state.clear()
    db.close()

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    """Вернуться в главное меню админа"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
        [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="admin_find_user")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="admin_finance")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])
    
    await callback.message.edit_text(
        "🔐 **ADMIN PANEL**\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ============================================================
# ОБРАБОТЧИКИ - КОМАНДА /ADMIN
# ============================================================
@router.message(Command('admin'))
async def admin_command(message: Message):
    """Команда /admin"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Вы не администратор")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
        [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="admin_find_user")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="admin_finance")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])
    
    await message.answer(
        "🔐 **ADMIN PANEL**\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ============================================================
# ОБРАБОТЧИКИ - КОМАНДА /HELP
# ============================================================
@router.message(Command('help'))
async def help_command(message: Message):
    """Команда /help"""
    help_text = (
        "❓ **СПРАВКА**\n\n"
        "📋 **Основные команды:**\n"
        "/start - Главное меню\n"
        "/admin - Админ-панель (только для администраторов)\n"
        "/help - Эта справка\n\n"
        "🎯 **Функции:**\n"
        "📝 Создание заказов\n"
        "👥 Поиск разработчиков\n"
        "💰 Управление платежами\n"
        "📊 Статистика и отчеты\n\n"
        "🔗 **Контакты:**\n"
        "📧 Email: support@itmarket.bot\n"
        "💬 Telegram: @ITMarketSupport"
    )
    
    await message.answer(help_text, parse_mode="Markdown")

# ============================================================
# ОБРАБОТЧИКИ - ОСНОВНЫЕ ФУНКЦИИ
# ============================================================
@router.callback_query(F.data == "create_order")
async def create_order(callback: CallbackQuery, state: FSMContext):
    """Создание нового заказа"""
    await callback.message.edit_text(
        "📝 **СОЗДАНИЕ ЗАКАЗА**\n\n"
        "Введите название заказа:",
        parse_mode="Markdown"
    )
    await state.set_state(UserStates.entering_order_title)

@router.message(UserStates.entering_order_title)
async def process_order_title(message: Message, state: FSMContext):
    """Обработка названия заказа"""
    await state.update_data(order_title=message.text)
    await message.answer(
        "📖 Введите описание заказа:"
    )
    await state.set_state(UserStates.entering_order_description)

@router.message(UserStates.entering_order_description)
async def process_order_description(message: Message, state: FSMContext):
    """Обработка описания заказа"""
    await state.update_data(order_description=message.text)
    await message.answer(
        "💰 Введите бюджет заказа (в рублях):"
    )
    await state.set_state(UserStates.entering_order_budget)

@router.message(UserStates.entering_order_budget)
async def process_order_budget(message: Message, state: FSMContext):
    """Обработка бюджета заказа"""
    try:
        budget = float(message.text)
    except ValueError:
        await message.answer("❌ Некорректный формат. Введите число:")
        return
    
    data = await state.get_data()
    db = get_db()
    
    # Создать заказ
    order = Order(
        order_number=get_order_number(),
        title=data['order_title'],
        description=data['order_description'],
        total_price=budget,
        customer_id=message.from_user.id,
        status=OrderStatus.CREATED
    )
    db.add(order)
    db.commit()
    
    result = (
        f"✅ **ЗАКАЗ СОЗДАН**\n\n"
        f"📝 Номер: {order.order_number}\n"
        f"📌 Название: {order.title}\n"
        f"💰 Бюджет: {budget} ₽\n\n"
        f"⏳ Статус: Ожидание одобрения администратора"
    )
    
    await message.answer(result, parse_mode="Markdown")
    
    # Уведомить администратора
    if ADMIN_ID:
        admin_notification = (
            f"🆕 **НОВЫЙ ЗАКАЗ**\n\n"
            f"📝 Номер: {order.order_number}\n"
            f"👤 Клиент: @{message.from_user.username or 'unknown'}\n"
            f"💰 Сумма: {budget} ₽\n\n"
            f"Используйте /admin для одобрения"
        )
        try:
            await bot.send_message(ADMIN_ID, admin_notification, parse_mode="Markdown")
        except:
            pass
    
    await state.clear()
    db.close()

@router.callback_query(F.data == "my_orders")
async def my_orders(callback: CallbackQuery):
    """Показать мои заказы"""
    db = get_db()
    orders = db.query(Order).filter(Order.customer_id == callback.from_user.id).all()
    
    if not orders:
        await callback.message.edit_text(
            "📭 **МОИ ЗАКАЗЫ**\n\n"
            "У вас нет заказов. Создайте первый! 📝",
            parse_mode="Markdown"
        )
        db.close()
        return
    
    orders_text = "📋 **МОИ ЗАКАЗЫ**\n\n"
    for order in orders:
        orders_text += (
            f"{get_status_emoji(order.status)} **{order.title}**\n"
            f"  Номер: {order.order_number}\n"
            f"  Сумма: {order.total_price} ₽\n"
            f"  Статус: {order.status.value}\n\n"
        )
    
    await callback.message.edit_text(orders_text, parse_mode="Markdown")
    db.close()

@router.callback_query(F.data == "my_profile")
async def my_profile(callback: CallbackQuery):
    """Показать мой профиль"""
    db = get_db()
    user = db.query(User).filter(User.telegram_id == callback.from_user.id).first()
    
    profile = (
        f"👤 **МОЙ ПРОФИЛЬ**\n\n"
        f"🔑 Telegram ID: {user.telegram_id}\n"
        f"👻 Username: @{user.username or 'Не указан'}\n"
        f"📛 Имя: {user.full_name or 'Не указано'}\n"
        f"🎭 Роль: {user.role.value.upper()}\n"
        f"⭐ Рейтинг: {user.rating}/5.0\n"
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    
    await callback.message.edit_text(profile, parse_mode="Markdown")
    db.close()

@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    """Справка через callback"""
    help_text = (
        "❓ **СПРАВКА**\n\n"
        "📋 **Основные команды:**\n"
        "/start - Главное меню\n"
        "/admin - Админ-панель\n"
        "/help - Эта справка\n\n"
        "🎯 **Возможности:**\n"
        "📝 Создание заказов\n"
        "💰 Управление платежами\n"
        "📊 Статистика\n\n"
        "🔗 Контакты: @ITMarketSupport"
    )
    
    await callback.message.edit_text(help_text, parse_mode="Markdown")

# ============================================================
# УСТАНОВКА КОМАНД МЕНЮ
# ============================================================
async def set_default_commands():
    """Установить команды в меню бота"""
    commands = [
        BotCommand(command="start", description="🚀 Главное меню"),
        BotCommand(command="admin", description="🔐 Админ-панель"),
        BotCommand(command="help", description="❓ Справка"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды установлены")

# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
async def main():
    """Главная функция запуска бота"""
    print("\n" + "="*70)
    print("🤖 IT MARKET BOT - MONOLITH")
    print("="*70 + "\n")
    
    # Инициализация БД
    print("🗄️  Инициализация базы данных...")
    init_db()
    print("✅ База данных готова\n")
    
    # Установка команд
    print("⚙️  Установка команд...")
    await set_default_commands()
    
    # Подключение роутера
    dp.include_router(router)
    
    # Запуск бота
    print("🤖 Бот запущен и готов к работе!\n")
    logger.info(f"✅ Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"✅ Admin ID: {ADMIN_ID}")
    logger.info(f"✅ Database: {DATABASE_URL[:30]}...")
    print("="*70 + "\n")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except KeyboardInterrupt:
        logger.info("⛔ Бот остановлен")
    finally:
        await bot.session.close()

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        sys.exit(1)
