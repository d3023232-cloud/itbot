from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from database import get_db
from models import User, Order, UserRole, OrderStatus
from config import ADMIN_IDS
from utils.order_utils import get_order_status_text

router = Router()


class AdminActions(StatesGroup):
    selecting_action = State()
    finding_user = State()
    finding_order = State()
    broadcast_message = State()
    ban_reason = State()
    unban_confirmation = State()
    assign_role = State()


def is_admin(message: Message) -> bool:
    """Check if user is admin"""
    return message.from_user.id in ADMIN_IDS


@router.message(Command('admin'))
async def admin_panel(message: Message, state: FSMContext):
    """Open admin panel"""
    if not is_admin(message):
        await message.answer("❌ Доступ запрещен. Только администраторы.")
        return
    
    db = get_db()
    user = db.query(User).filter(User.telegram_id == message.from_user.id).first()
    db.close()
    
    panel_text = (
        "🛡️ **АДМИН ПАНЕЛЬ**\n\n"
        "Выберите действие:\n\n"
        "📋 **Управление заказами:**\n"
        "🔍 Найти заказ по ID\n"
        "📊 Статистика\n\n"
        "👥 **Управление пользователями:**\n"
        "🔎 Найти пользователя\n"
        "🚫 Забанить пользователя\n"
        "✅ Разбанить пользователя\n"
        "👤 Назначить роль\n\n"
        "📢 **Коммуникация:**\n"
        "📨 Рассылка сообщения\n"
        "💬 Связь с пользователем\n\n"
        "💰 **Финансы:**\n"
        "💳 Финансовый отчет"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        # Orders
        [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="admin_find_order")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        # Users
        [InlineKeyboardButton(text="🔎 Найти пользователя", callback_data="admin_find_user")],
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban_user")],
        [InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban_user")],
        [InlineKeyboardButton(text="👤 Назначить роль", callback_data="admin_assign_role")],
        # Communication
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💬 Связь с юзером", callback_data="admin_message_user")],
        # Finance
        [InlineKeyboardButton(text="💳 Отчет", callback_data="admin_finance_report")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")]
    ])
    
    await message.answer(panel_text, reply_markup=keyboard, parse_mode="Markdown")


# ============ FIND ORDER ============
@router.callback_query(F.data == "admin_find_order")
async def find_order_start(callback: CallbackQuery, state: FSMContext):
    """Start finding order"""
    await callback.message.edit_text(
        "🔍 **ПОИСК ЗАКАЗА**\n\n"
        "Введите ID заказа или номер заказа (например: Order-20260611-001)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminActions.finding_order)


@router.message(AdminActions.finding_order)
async def process_find_order(message: Message, state: FSMContext):
    """Process order search"""
    if not is_admin(message):
        return
    
    search_query = message.text.strip()
    db = get_db()
    
    # Try to find by ID or order number
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
    
    # Display order details
    details = (
        f"📋 **ДЕТАЛИ ЗАКАЗА**\n\n"
        f"🔢 ID: {order.id}\n"
        f"📝 Номер: {order.order_number}\n"
        f"📌 Тема: {order.theme}\n"
        f"🏷️ Название: {order.title}\n"
        f"📖 Описание: {order.description[:100]}...\n\n"
        f"👤 **Участники:**\n"
        f"🙋 Клиент: {order.customer.full_name or order.customer.username} (@{order.customer.username})\n"
        f"📱 Telegram ID клиента: {order.customer.telegram_id}\n"
        f"📧 Email: {order.customer.email or 'Не указан'}\n"
        f"☎️ Телефон: {order.customer.phone or 'Не указан'}\n\n"
    )
    
    if order.developer:
        details += (
            f"👨‍💻 Разработчик: {order.developer.full_name or order.developer.username}\n"
            f"📱 Telegram ID: {order.developer.telegram_id}\n\n"
        )
    else:
        details += "👨‍💻 Разработчик: Не назначен\n\n"
    
    if order.admin_id:
        details += f"👨‍💼 Админ: {order.admin_id}\n\n"
    
    details += (
        f"💰 **ФИНАНСЫ:**\n"
        f"💵 Сумма: {order.total_price or 'Не установлена'} ₽\n"
        f"👨‍💻 Разработчику: {order.developer_payment or '—'} ₽\n"
        f"🏪 Магазину: {order.market_payment or '—'} ₽\n\n"
        f"⏰ **СРОКИ:**\n"
        f"📅 Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )
    
    if order.deadline:
        details += f"⏲️ Срок: {order.deadline.strftime('%d.%m.%Y')}\n"
    
    if order.completed_at:
        details += f"✅ Завершен: {order.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
    
    details += f"\n🔴 **Статус:** {get_order_status_text(order.status.value)}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать клиенту", callback_data=f"admin_msg_customer_{order.id}")],
        [InlineKeyboardButton(text="☎️ Написать разработчику", callback_data=f"admin_msg_developer_{order.id}")] if order.developer else [],
        [InlineKeyboardButton(text="⚙️ Изменить статус", callback_data=f"admin_change_status_{order.id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    
    await message.answer(details, reply_markup=keyboard, parse_mode="Markdown")
    await state.clear()
    db.close()


# ============ FIND USER ============
@router.callback_query(F.data == "admin_find_user")
async def find_user_start(callback: CallbackQuery, state: FSMContext):
    """Start finding user"""
    await callback.message.edit_text(
        "🔎 **ПОИСК ПОЛЬЗОВАТЕЛЯ**\n\n"
        "Введите Telegram ID или username (например: 123456789 или @username)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminActions.finding_user)


@router.message(AdminActions.finding_user)
async def process_find_user(message: Message, state: FSMContext):
    """Process user search"""
    if not is_admin(message):
        return
    
    search_query = message.text.strip().replace('@', '')
    db = get_db()
    
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
    
    # Get user stats
    orders_count = db.query(Order).filter(Order.customer_id == user.id).count()
    projects_count = db.query(Order).filter(Order.developer_id == user.id).count()
    
    details = (
        f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
        f"🔢 Telegram ID: {user.telegram_id}\n"
        f"👤 Username: @{user.username or 'Не указан'}\n"
        f"📝 Имя: {user.full_name or 'Не указано'}\n"
        f"📧 Email: {user.email or 'Не указан'}\n"
        f"☎️ Телефон: {user.phone or 'Не указан'}\n\n"
        f"🏷️ **Роль:** {user.role.value.upper()}\n"
        f"📊 **Статистика:**\n"
        f"📋 Заказов: {orders_count}\n"
        f"👨‍💻 Проектов: {projects_count}\n"
        f"📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"🟢 Статус: {'Активен' if user.is_active else '🔴 Заблокирован'}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить" if user.is_active else "✅ Разбанить", 
                            callback_data=f"admin_ban_toggle_{user.id}")],
        [InlineKeyboardButton(text="👤 Изменить роль", callback_data=f"admin_set_role_{user.id}")],
        [InlineKeyboardButton(text="💬 Написать", callback_data=f"admin_msg_user_{user.id}")],
        [InlineKeyboardButton(text="📋 Заказы", callback_data=f"admin_user_orders_{user.id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    
    await message.answer(details, reply_markup=keyboard, parse_mode="Markdown")
    await state.clear()
    db.close()


# ============ BAN USER ============
@router.callback_query(F.data.startswith("admin_ban_toggle_"))
async def toggle_ban_user(callback: CallbackQuery, state: FSMContext):
    """Toggle user ban"""
    user_id = int(callback.data.split('_')[-1])
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        db.close()
        return
    
    if user.is_active:
        await state.update_data(user_to_ban=user_id)
        await callback.message.edit_text(
            f"🚫 **ЗАБАНИТЬ ПОЛЬЗОВАТЕЛЯ**\n\n"
            f"Пользователь: @{user.username or user.telegram_id}\n\n"
            f"Укажите причину бана:",
            parse_mode="Markdown"
        )
        await state.set_state(AdminActions.ban_reason)
    else:
        # Unban
        user.is_active = True
        db.commit()
        db.close()
        
        await callback.message.edit_text(
            f"✅ Пользователь @{user.username or user.telegram_id} разбанен"
        )


@router.message(AdminActions.ban_reason)
async def set_ban_reason(message: Message, state: FSMContext):
    """Set ban reason"""
    data = await state.get_data()
    db = get_db()
    user = db.query(User).filter(User.id == data['user_to_ban']).first()
    
    user.is_active = False
    db.commit()
    
    # Notify user about ban
    try:
        await message.bot.send_message(
            chat_id=user.telegram_id,
            text=f"🚫 **ВЫ БЫЛИ ЗАБЛОКИРОВАНЫ**\n\nПричина: {message.text}"
        )
    except:
        pass
    
    db.close()
    await message.answer(f"✅ Пользователь @{user.username or user.telegram_id} заблокирован\nПричина: {message.text}")
    await state.clear()


# ============ ASSIGN ROLE ============
@router.callback_query(F.data.startswith("admin_set_role_"))
async def assign_role_start(callback: CallbackQuery, state: FSMContext):
    """Start role assignment"""
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(user_to_assign=user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Клиент", callback_data="role_assign_user")],
        [InlineKeyboardButton(text="👨‍💻 Разработчик", callback_data="role_assign_developer")],
        [InlineKeyboardButton(text="👨‍💼 Администратор", callback_data="role_assign_admin")]
    ])
    
    await callback.message.edit_text(
        "👤 **ВЫБЕРИТЕ НОВУЮ РОЛЬ:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("role_assign_"))
async def confirm_role(callback: CallbackQuery, state: FSMContext):
    """Confirm role assignment"""
    role_map = {
        'role_assign_user': UserRole.USER,
        'role_assign_developer': UserRole.DEVELOPER,
        'role_assign_admin': UserRole.ADMIN
    }
    
    data = await state.get_data()
    db = get_db()
    user = db.query(User).filter(User.id == data['user_to_assign']).first()
    
    new_role = role_map.get(callback.data)
    if user and new_role:
        user.role = new_role
        db.commit()
        
        role_names = {
            UserRole.USER: '👤 Клиент',
            UserRole.DEVELOPER: '👨‍💻 Разработчик',
            UserRole.ADMIN: '👨‍💼 Администратор'
        }
        
        await callback.message.edit_text(
            f"✅ Роль пользователя @{user.username or user.telegram_id} изменена на {role_names[new_role]}"
        )
        
        try:
            await callback.bot.send_message(
                chat_id=user.telegram_id,
                text=f"✅ Ваша роль изменена на {role_names[new_role]}"
            )
        except:
            pass
    
    db.close()
    await state.clear()


# ============ BROADCAST ============
@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Start broadcast"""
    await callback.message.edit_text(
        "📢 **РАССЫЛКА СООБЩЕНИЯ**\n\n"
        "Напишите сообщение для рассылки всем пользователям:",
        parse_mode="Markdown"
    )
    await state.set_state(AdminActions.broadcast_message)


@router.message(AdminActions.broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    """Process broadcast"""
    if not is_admin(message):
        return
    
    db = get_db()
    users = db.query(User).filter(User.is_active == True).all()
    
    broadcast_text = f"📢 **ВАЖНОЕ СООБЩЕНИЕ ОТ АДМИНИСТРАЦИИ**\n\n{message.text}"
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await message.bot.send_message(
                chat_id=user.telegram_id,
                text=broadcast_text,
                parse_mode="Markdown"
            )
            success += 1
        except:
            failed += 1
    
    db.close()
    
    await message.answer(
        f"📊 **РАССЫЛКА ЗАВЕРШЕНА**\n\n"
        f"✅ Отправлено: {success}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="Markdown"
    )
    await state.clear()


# ============ MESSAGE USER ============
@router.callback_query(F.data.startswith("admin_msg_user_"))
async def message_user(callback: CallbackQuery, state: FSMContext):
    """Send message to specific user"""
    user_id = int(callback.data.split('_')[-1])
    db = get_db()
    user = db.query(User).filter(User.id == user_id).first()
    
    await state.update_data(target_user_id=user.telegram_id)
    await callback.message.edit_text(
        f"💬 **НАПИСАТЬ СООБЩЕНИЕ**\n\n"
        f"Адресат: @{user.username or user.telegram_id}\n\n"
        f"Введите сообщение:",
        parse_mode="Markdown"
    )
    db.close()
    await state.set_state(AdminActions.broadcast_message)  # Reuse state


# ============ STATISTICS ============
@router.callback_query(F.data == "admin_stats")
async def show_statistics(callback: CallbackQuery):
    """Show platform statistics"""
    db = get_db()
    
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_orders = db.query(Order).count()
    completed_orders = db.query(Order).filter(Order.status == OrderStatus.COMPLETED).count()
    pending_orders = db.query(Order).filter(Order.status == OrderStatus.WAITING_ADMIN).count()
    in_dev_orders = db.query(Order).filter(Order.status == OrderStatus.IN_DEVELOPMENT).count()
    
    # Financial stats
    total_revenue = sum([o.market_payment or 0 for o in db.query(Order).filter(Order.status == OrderStatus.COMPLETED).all()])
    total_paid_developers = sum([o.developer_payment or 0 for o in db.query(Order).filter(Order.status == OrderStatus.COMPLETED).all()])
    
    stats = (
        f"📊 **СТАТИСТИКА ПЛАТФОРМЫ**\n\n"
        f"👥 **Пользователи:**\n"
        f"👤 Всего: {total_users}\n"
        f"🟢 Активных: {active_users}\n\n"
        f"📋 **Заказы:**\n"
        f"📝 Всего: {total_orders}\n"
        f"✅ Завершено: {completed_orders}\n"
        f"⏳ Ожидают одобрения: {pending_orders}\n"
        f"🔧 В разработке: {in_dev_orders}\n\n"
        f"💰 **ФИНАНСЫ:**\n"
        f"💵 Доход магазина: {total_revenue:.2f} ₽\n"
        f"👨‍💻 Выплачено разработчикам: {total_paid_developers:.2f} ₽"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    
    await callback.message.edit_text(stats, reply_markup=keyboard, parse_mode="Markdown")
    db.close()


# ============ FINANCE REPORT ============
@router.callback_query(F.data == "admin_finance_report")
async def finance_report(callback: CallbackQuery):
    """Show financial report"""
    db = get_db()
    
    completed_orders = db.query(Order).filter(Order.status == OrderStatus.COMPLETED).all()
    rejected_orders = db.query(Order).filter(Order.status == OrderStatus.REJECTED).all()
    
    total_market = sum([o.market_payment or 0 for o in completed_orders])
    total_dev = sum([o.developer_payment or 0 for o in completed_orders])
    compensation = sum([o.total_price * 0.5 for o in rejected_orders if o.total_price])
    
    report = (
        f"💳 **ФИНАНСОВЫЙ ОТЧЕТ**\n\n"
        f"✅ **Завершено заказов:** {len(completed_orders)}\n"
        f"💰 Доход магазина: {total_market:.2f} ₽\n"
        f"👨‍💻 Выплачено разработчикам: {total_dev:.2f} ₽\n\n"
        f"❌ **Отклонено заказов:** {len(rejected_orders)}\n"
        f"💸 Выплачено компенсаций: {compensation:.2f} ₽\n\n"
        f"📊 **ИТОГО:**\n"
        f"💵 Общий доход: {total_market + compensation:.2f} ₽"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    
    await callback.message.edit_text(report, reply_markup=keyboard, parse_mode="Markdown")
    db.close()


# ============ BACK BUTTON ============
@router.callback_query(F.data == "admin_back_to_panel")
async def back_to_panel(callback: CallbackQuery):
    """Return to admin panel"""
    await admin_panel(callback.message, FSMContext({}))
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def close_panel(callback: CallbackQuery):
    """Close admin panel"""
    await callback.message.delete()
    await callback.answer("✅ Панель закрыта")
