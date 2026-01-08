from aiogram import Router, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from database import get_session
from database.models import Organization, User, UserRole
from aiogram.fsm.context import FSMContext
from utils.time import create_timezone_keyboard, SUPPORTED_TIMEZONES
from utils.states import TimezoneStates
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "admin_change_timezone")
async def org_admin_change_timezone(callback: types.CallbackQuery, state: FSMContext):
    """Админ организации меняет часовой пояс своей организации"""
    
    session = get_session()
    try:
        # Получаем пользователя (админа)
        user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Проверяем, что пользователь - админ организации
        if user.role != UserRole.ORG_ADMIN.value:
            await callback.answer("❌ У вас нет прав администратора организации", show_alert=True)
            return
        
        # Проверяем, что пользователь привязан к организации
        if not user.org_id:
            await callback.answer("❌ Вы не привязаны к организации", show_alert=True)
            return
        
        # Получаем организацию админа
        org = session.query(Organization).filter(Organization.id == user.org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        # Получаем текущий часовой пояс
        current_tz = org.timezone
        
        # Находим отображаемое имя текущего часового пояса
        current_display = "Неизвестно"
        for display_name, tz_name in SUPPORTED_TIMEZONES:
            if tz_name == current_tz:
                current_display = display_name
                break
        
        # Сохраняем данные в состоянии
        await state.update_data(
            org_id=org.id,
            org_name=org.name,
            current_tz=current_tz,
            admin_id=user.user_id
        )
        
        # Создаем клавиатуру с часовыми поясами
        tz_kb = create_timezone_keyboard()
        
        text = (
            f"🕐 *Смена часового пояса*\n\n"
            f"🏢 *Ваша организация:* {org.name}\n"
            f"🌍 *Текущий пояс:* {current_display}\n\n"
            f"*Выберите новый часовой пояс:*\n"
            f"Это повлияет на:\n"
            f"• Время в статистике\n"
            f"• Время создания челленджей\n"
            f"• Время опросов\n"
            f"• Отображение дат для всех участников\n\n"
            f"Выберите из списка ниже:"
        )
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=tz_kb)
        await state.set_state(TimezoneStates.waiting_timezone)
        
    except Exception as e:
        logger.error(f"Ошибка при смене часового пояса: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()
    
    await callback.answer()

@router.callback_query(TimezoneStates.waiting_timezone, F.data.startswith("tz_"))
async def org_admin_process_timezone(callback: types.CallbackQuery, state: FSMContext):
    """Админ организации выбирает часовой пояс"""
    selected_tz = callback.data.replace("tz_", "")
    
    if selected_tz == "cancel_timezone":
        await org_admin_cancel_timezone(callback, state)
        return
    
    # Проверяем, что часовой пояс поддерживается
    is_supported = any(tz_name == selected_tz for _, tz_name in SUPPORTED_TIMEZONES)
    if not is_supported:
        await callback.answer("❌ Часовой пояс не поддерживается", show_alert=True)
        return
    
    data = await state.get_data()
    org_id = data.get("org_id")
    current_tz = data.get("current_tz")
    
    # Получаем отображаемое имя для выбранного пояса
    selected_display = "Неизвестно"
    for display_name, tz_name in SUPPORTED_TIMEZONES:
        if tz_name == selected_tz:
            selected_display = display_name
            break
    
    # Если выбрали тот же самый пояс
    if selected_tz == current_tz:
        await callback.answer(f"✅ Часовой пояс уже установлен: {selected_display}", show_alert=True)
        await org_admin_cancel_timezone(callback, state)
        return
    
    # Показываем подтверждение
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        
        # Получаем текущее время в обоих поясах для демонстрации
        import pytz
        from datetime import datetime
        
        old_tz = pytz.timezone(current_tz)
        new_tz = pytz.timezone(selected_tz)
        now_utc = datetime.now(pytz.utc)
        
        old_time = now_utc.astimezone(old_tz).strftime("%H:%M")
        new_time = now_utc.astimezone(new_tz).strftime("%H:%M")
        
        confirm_text = (
            f"🔄 *Подтверждение смены часового пояса*\n\n"
            f"🏢 *Организация:* {org.name}\n\n"
            f"📊 *Изменения:*\n"
            f"• С *{current_tz}* → На *{selected_display}*\n"
            f"• Время изменится с *{old_time}* → На *{new_time}*\n\n"
            f"⚠️ *Это повлияет на всех участников организации!*\n\n"
            f"Вы уверены, что хотите изменить часовой пояс?"
        )
        
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, изменить", callback_data=f"org_admin_confirm_tz_{selected_tz}"),
                InlineKeyboardButton(text="❌ Нет, отменить", callback_data="org_admin_cancel_timezone")
            ]
        ])
        
        await callback.message.edit_text(confirm_text, parse_mode="Markdown", reply_markup=confirm_kb)
        
        # Сохраняем выбранный пояс в состоянии
        await state.update_data(selected_tz=selected_tz, selected_display=selected_display)
        await state.set_state(TimezoneStates.waiting_confirmation)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()
    
    await callback.answer()

@router.callback_query(TimezoneStates.waiting_confirmation, F.data.startswith("org_admin_confirm_tz_"))
async def org_admin_confirm_timezone(callback: types.CallbackQuery, state: FSMContext):
    """Админ организации подтверждает смену часового пояса"""
    selected_tz = callback.data.replace("org_admin_confirm_tz_", "")
    
    data = await state.get_data()
    org_id = data.get("org_id")
    admin_id = data.get("admin_id")
    
    # Проверяем, что текущий пользователь - это тот же админ
    if callback.from_user.id != admin_id:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            await state.clear()
            return
        
        old_tz = org.timezone
        
        # Обновляем часовой пояс организации
        org.timezone = selected_tz
        session.commit()
        
        # Получаем отображаемое имя
        new_display = "Неизвестно"
        for display_name, tz_name in SUPPORTED_TIMEZONES:
            if tz_name == selected_tz:
                new_display = display_name
                break
        
        # Показываем успешное сообщение
        success_text = (
            f"✅ *Часовой пояс изменен!*\n\n"
            f"🏢 *Ваша организация:* {org.name}\n"
            f"🌍 *Новый часовой пояс:* {new_display}\n\n"
            f"📊 *Изменения вступят в силу сразу:*\n"
            f"• Новое время в статистике\n"
            f"• Время создания челленджей\n"
            f"• Расписание опросов\n"
            f"• Отображение всех дат\n\n"
            f"⚙️ Все участники организации увидят новое время."
        )
        
        # Кнопка возврата в меню админа
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_admin_panel")]
        ])
        
        await callback.message.edit_text(success_text, parse_mode="Markdown", reply_markup=back_kb)
        
        # Логируем изменение
        logger.info(f"Часовой пояс организации изменен админом: {org.name} ({org_id}), "
                   f"старый: {old_tz}, новый: {selected_tz}, "
                   f"админ: {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при смене часового пояса: {e}")
        session.rollback()
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()
        await state.clear()
    
    await callback.answer()

@router.callback_query(F.state.in_(["org_admin_waiting_timezone", "org_admin_waiting_confirmation"]), 
                      F.data == "org_admin_cancel_timezone")
async def org_admin_cancel_timezone(callback: types.CallbackQuery, state: FSMContext):
    """Админ организации отменяет смену часового пояса"""
    await state.clear()
    
    await callback.answer("❌ Смена часового пояса отменена")
    
    # Возвращаем в меню админа
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="show_admin_menu")]
    ])
    
    await callback.message.edit_text(
        "❌ Смена часового пояса отменена.",
        reply_markup=back_kb
    )

# Хендлер для отмены через команду /cancel
@router.message(F.text.lower().in_(["отмена", "cancel", "/отмена", "/cancel"]))
async def org_admin_cancel_command(message: Message, state: FSMContext):
    """Отмена смены часового пояса по команде"""
    current_state = await state.get_state()
    if current_state and current_state.startswith("org_admin_"):
        await state.clear()
        await message.answer(
            "✅ Смена часового пояса отменена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="show_admin_menu")]
            ])
        )