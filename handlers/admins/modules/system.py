# handlers/admins/modules/system.py
from aiogram import Router, types, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import User, Organization, get_session, UserRole
from database.models import MessageSchedule
from services.challenge_storage import challenge_storage
from datetime import datetime, timezone, time
from ..menu_manager import AdminMenuManager
from utils.states import TimeSettingStates
import json
import logging
import re

router = Router()
logger = logging.getLogger(__name__)
menu_manager = AdminMenuManager()

@router.callback_query(F.data == "admin_storage_stats")
async def admin_storage_stats(callback: types.CallbackQuery):
    """Показать статистику хранилища"""
    user_id = callback.from_user.id
    
    from .members import is_admin
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    try:
        stats = await challenge_storage.get_statistics()
        
        stats_text = (
            "📊 *СТАТИСТИКА ХРАНИЛИЩА ЧЕЛЛЕНДЖЕЙ*\n\n"
            f"📁 Всего записей: {stats.get('total_records', 0)}\n"
            f"⏳ В ожидании: {stats.get('pending', 0)}\n"
            f"⌛ Просрочено: {stats.get('expired', 0)}\n"
            f"🕐 Возраст самой старой записи: {stats.get('oldest_record_age', 0):.1f} ч.\n\n"
            f"🔄 Очистка происходит автоматически каждые 6 часов."
        )
        
        await callback.message.edit_text(stats_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.message.edit_text("❌ Ошибка получения статистики")

@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(callback: types.CallbackQuery):
    """Управление администраторами системы"""
    user_id = callback.from_user.id
    
    from .members import is_super_admin
    if not is_super_admin(user_id):
        await callback.answer("❌ Только суперадмины могут управлять админами", show_alert=True)
        return
    
    from config import load_config
    config = load_config()
    
    session = get_session()
    try:
        admins = session.query(User).filter(
            User.role.in_([UserRole.ORG_ADMIN.value, UserRole.TRAINER.value])
        ).order_by(User.registered_at.desc()).all()
        
        text = "👑 АДМИНИСТРАТОРЫ СИСТЕМЫ\n\n"
        text += f"🔐 Суперадмины (из .env): {', '.join(map(str, config.admin_ids))}\n\n"
        
        if admins:
            for admin in admins:
                role_icon = "👑" if admin.user_id in config.admin_ids else "👨‍💼"
                text += f"{role_icon} {admin.name} (ID: {admin.user_id})\n"
                text += f"   Роль: {admin.role} | Организация: {admin.organization.name if admin.organization else 'N/A'}\n\n"
        else:
            text += "❌ Нет зарегистрированных администраторов\n\n"
        
        text += "Добавить нового админа: /promote <user_id>"
        
        await callback.message.edit_text(text)
        
    finally:
        session.close()

@router.message(Command("promote"))
async def promote_to_admin(message: types.Message):
    """Назначить пользователя администратором (только для суперадминов)"""
    from .members import is_super_admin
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Эта команда только для суперадминов")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ Использование: /promote <user_id>")
            return
        
        target_user_id = int(args[1])
        
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == target_user_id).first()
            if not user:
                await message.answer(f"❌ Пользователь с ID {target_user_id} не найден")
                return
            
            user.role = UserRole.ORG_ADMIN.value
            session.commit()
            
            await message.answer(
                f"✅ Пользователь {user.name} (ID: {user.user_id}) назначен администратором!\n\n"
                f"Теперь он имеет доступ к админ-панели."
            )
            
            if user.chat_id:
                try:
                    await message.bot.send_message(
                        user.chat_id,
                        "🎖️ Вы были назначены администратором системы!\n\n"
                        "Теперь вам доступна админ-панель через кнопку '⚙️ Админ-панель' или команду /admin"
                    )
                except:
                    pass
                    
        finally:
            session.close()
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Должно быть число.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("set_role"))
async def set_role_command(message: types.Message):
    """Изменить роль пользователя (только для суперадминов)"""
    from .members import is_super_admin
    if not is_super_admin(message.from_user.id):
        await message.answer("❌ Эта команда только для суперадминов")
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.answer(
                "❌ Использование: /set_role <user_id> <role>\n\n"
                "Доступные роли:\n"
                "• SUPER_ADMIN - суперадмин системы\n"
                "• ORG_ADMIN - администратор организации\n"
                "• TRAINER - тренер (просмотр + челленджи)\n"
                "• MEMBER - обычный участник\n"
            )
            return
        
        target_user_id = int(args[1])
        new_role = args[2].upper()
        
        from database import is_valid_role, get_all_roles
        if not is_valid_role(new_role):
            valid_roles = get_all_roles()
            await message.answer(
                f"❌ Неверная роль. Доступные роли: {', '.join(valid_roles)}"
            )
            return
        
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == target_user_id).first()
            if not user:
                await message.answer(f"❌ Пользователь с ID {target_user_id} не найден")
                return
            
            old_role = user.role
            
            # Проверка: нельзя снять роль админа, если он единственный админ в организации
            if old_role == UserRole.ORG_ADMIN.value and new_role != UserRole.ORG_ADMIN.value:
                org = session.query(Organization).filter(Organization.admin_id == user.user_id).first()
                if org:
                    # Проверяем, есть ли другие админы в организации
                    other_admins = session.query(User).filter(
                        User.org_id == org.id,
                        User.role == UserRole.ORG_ADMIN.value,
                        User.user_id != user.user_id
                    ).count()
                    
                    if other_admins == 0:
                        # Нет других админов - нельзя снимать роль
                        await message.answer(
                            f"❌ Нельзя снять роль админа с пользователя {user.name}!\n\n"
                            f"Он единственный администратор в организации '{org.name}'.\n"
                            f"Сначала назначьте другого администратора с помощью:\n"
                            f"`/set_role <user_id> ORG_ADMIN`\n\n"
                            f"Только потом можно снять роль у текущего админа.", 
                            parse_mode="Markdown"
                        )
                        return
            
            user.role = new_role
            
            if new_role == UserRole.ORG_ADMIN.value:
                # Назначаем пользователя админом его организации
                org = session.query(Organization).filter(Organization.id == user.org_id).first()
                if org:
                    org.admin_id = user.user_id
                    
            elif old_role == UserRole.ORG_ADMIN.value and new_role != UserRole.ORG_ADMIN.value:
                # Пользователь больше не админ - нужно найти замену
                org = session.query(Organization).filter(Organization.admin_id == user.user_id).first()
                if org:
                    # Ищем другого админа в организации
                    new_admin = session.query(User).filter(
                        User.org_id == org.id,
                        User.role.in_([UserRole.ORG_ADMIN.value, UserRole.SUPER_ADMIN.value]),
                        User.user_id != user.user_id
                    ).first()
                    
                    if new_admin:
                        org.admin_id = new_admin.user_id
                    else:
                        # Ищем любого активного пользователя в организации
                        any_user = session.query(User).filter(
                            User.org_id == org.id,
                            User.user_id != user.user_id,
                            User.chat_id.isnot(None)  # Только активные пользователи
                        ).first()
                        
                        if any_user:
                            org.admin_id = any_user.user_id
                            # Сделаем его админом
                            any_user.role = UserRole.ORG_ADMIN.value
                            print(f"⚠️ Пользователь {any_user.name} автоматически назначен админом организации {org.name}")
                        else:
                            # Если нет других пользователей, назначаем системного админа (user_id = 0)
                            org.admin_id = 0
                            print(f"⚠️ Организация {org.name} осталась без активного админа")
            
            session.commit()
            
            from database import get_role_description
            await message.answer(
                f"✅ Роль пользователя изменена!\n\n"
                f"👤 {user.name} (ID: {user.user_id})\n"
                f"🔄 {old_role} → {new_role}\n"
                f"📝 {get_role_description(new_role)}"
            )
            
            # Отправляем уведомление пользователю
            if user.chat_id:
                role_descriptions = {
                    "SUPER_ADMIN": "👑 СУПЕРАДМИН СИСТЕМЫ\n• Полный доступ ко всем функциям\n• Управление всеми организациями\n• Назначение ролей",
                    "ORG_ADMIN": "👨‍💼 АДМИНИСТРАТОР ОРГАНИЗАЦИИ\n• Управление своей командой\n• Создание челленджей\n• Просмотр статистики\n• Управление участниками",
                    "TRAINER": "👨‍🏫 ТРЕНЕР\n• Создание челленджей\n• Просмотр статистики команды\n• Просмотр участников\n• Доступ к расписанию",
                    "MEMBER": "👤 УЧАСТНИК\n• Личный профиль\n• Выполнение челленджей\n• Просмотр лидерборда\n• Прохождение опросов",
                }
                
                try:
                    await message.bot.send_message(
                        user.chat_id,
                        f"🎖️ *ВАША РОЛЬ ИЗМЕНЕНА!*\n\n"
                        f"Ваша новая роль: *{new_role}*\n\n"
                        f"{role_descriptions.get(new_role, '')}\n\n"
                        f"Доступные функции обновлены.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление: {e}")
                    
        except Exception as e:
            session.rollback()
            await message.answer(f"❌ Ошибка изменения роли: {str(e)[:200]}")
            logger.error(f"Ошибка в set_role_command: {e}")
        finally:
            session.close()
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Должно быть число.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:200]}")

@router.message(Command("my_role"))
async def my_role_command(message: types.Message):
    """Показать свою роль и права"""
    user_id = message.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            await message.answer("❌ Вы не зарегистрированы в системе")
            return
        
        role_descriptions = {
            "SUPER_ADMIN": {
                "icon": "👑",
                "name": "Суперадмин системы",
                "permissions": [
                    "Полный доступ ко всем организациям",
                    "Управление всеми пользователями",
                    "Создание/удаление организаций",
                    "Назначение ролей",
                    "Все системные настройки"
                ]
            },
            "ORG_ADMIN": {
                "icon": "👨‍💼",
                "name": "Администратор организации",
                "permissions": [
                    "Управление своей организацией",
                    "Создание челленджей",
                    "Просмотр статистики команды",
                    "Управление участниками",
                    "Рассылки в команде"
                ]
            },
            "TRAINER": {
                "icon": "👨‍🏫",
                "name": "Тренер",
                "permissions": [
                    "Просмотр статистики команды",
                    "Создание челленджей",
                    "Просмотр участников",
                    "Доступ к расписанию"
                ]
            },
            "MEMBER": {
                "icon": "👤",
                "name": "Участник",
                "permissions": [
                    "Личный профиль",
                    "Выполнение челленджей",
                    "Просмотр лидерборда",
                    "Прохождение опросов"
                ]
            }
        }
        
        role_info = role_descriptions.get(user.role, role_descriptions["MEMBER"])
        
        text = (
            f"{role_info['icon']} *ВАША РОЛЬ: {role_info['name']}*\n\n"
            f"*Доступные права:*\n"
        )
        
        for permission in role_info['permissions']:
            text += f"✅ {permission}\n"
        
        text += f"\n*Статус проверок:*\n"
        
        from .members import is_super_admin, is_admin, is_trainer, has_view_access
        text += f"• Суперадмин: {'✅' if is_super_admin(user_id) else '❌'}\n"
        text += f"• Администратор: {'✅' if is_admin(user_id) else '❌'}\n"
        text += f"• Тренер: {'✅' if is_trainer(user_id) else '❌'}\n"
        text += f"• Просмотр статистики: {'✅' if has_view_access(user_id) else '❌'}"
        
        await message.answer(text, parse_mode="Markdown")
        
    finally:
        session.close()

async def admin_export_stats(org_id: int) -> str:
    """Экспортировать статистику в JSON"""
    try:
        from services import MetricsCollector
        stats = MetricsCollector.get_organization_stats(org_id)
        
        export_data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "organization": {
                "name": stats["org_name"],
                "type": stats["org_type"],
                "members": stats["total_members"],
                "total_surveys": stats["total_surveys"],
                "avg_level": stats["avg_level"],
                "total_points": stats["total_points"]
            },
            "members": stats["members"]
        }
        
        return json.dumps(export_data, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"❌ Ошибка экспорта: {e}"

async def get_admin_dashboard_data(org_id: int) -> dict:
    """Получить все данные для админ-панели"""
    from services import MetricsCollector
    return {
        "organization": MetricsCollector.get_organization_stats(org_id),
        "daily": MetricsCollector.get_daily_report(org_id),
        "leaderboard": MetricsCollector.get_leaderboard(org_id),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.callback_query(F.data == "admin_settings_handler")
async def admin_settings_handler(callback: types.CallbackQuery):
    """Обработчик для кнопки настроек (новый формат)"""
    await callback.answer("⚙️ Настройки системы - в разработке", show_alert=True)


@router.callback_query(F.data.startswith("change_time_"))
async def change_message_time(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Запрос нового времени для сообщения"""
    try:
        schedule_id = int(callback.data.split("_")[2])
        
        await state.set_state(TimeSettingStates.waiting_for_time)
        await state.update_data(schedule_id=schedule_id)
        
        await callback.message.edit_text(
            f"⏰ УКАЖИТЕ НОВОЕ ВРЕМЯ\n\n"
            f"Для сообщения ID: {schedule_id}\n\n"
            f"Введите время в формате ЧЧ:ММ (24-часовой):\n"
            f"Например: 14:30 или 09:00\n\n"
            f"Для отмены нажмите /cancel",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Отмена", callback_data=f"edit_msg_{schedule_id}")
            ]])
        )
        
    except Exception as e:
        logger.error(f"Ошибка смены времени: {e}")
        await callback.message.edit_text("❌ Ошибка")

@router.message(TimeSettingStates.waiting_for_time)
async def process_time_input(message: types.Message, state: FSMContext) -> None:
    """Обработка введенного времени"""
    try:
        time_str = message.text.strip()
        
        # Проверяем формат времени
        time_pattern = r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$'
        if not re.match(time_pattern, time_str):
            await message.answer(
                "❌ Неверный формат времени.\n"
                "Пожалуйста, введите время в формате ЧЧ:ММ (например, 14:30)\n"
                "Используйте 24-часовой формат."
            )
            return
        
        # Парсим время
        hours, minutes = map(int, time_str.split(':'))
        new_time = time(hours, minutes)
        
        data = await state.get_data()
        schedule_id = data.get('schedule_id')
        
        session = get_session()
        schedule = session.query(MessageSchedule).filter(
            MessageSchedule.id == schedule_id
        ).first()
        
        if schedule:
            schedule.scheduled_time = new_time
            session.commit()
            
            time_str_formatted = new_time.strftime("%H:%M")
            await message.answer(
                f"✅ Время обновлено!\n\n"
                f"Сообщение '{schedule.title}'\n"
                f"будет отправляться в {time_str_formatted}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_msg_{schedule_id}")
                ]])
            )
        else:
            await message.answer("❌ Сообщение не найдено")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки времени: {e}")
        await message.answer("❌ Ошибка при обновлении времени")
        await state.clear()

@router.callback_query(F.data == 'admin_commands')
async def show_admin_commands (call: types.CallbackQuery) -> None:
    command_text = (
        '*Команды для суперадминов:*\n\n'
        '```/set_role <id_пользователя> <роль>```'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
        ])

    await call.message.delete() 
    await call.message.answer(command_text, parse_mode='Markdown', reply_markup=kb)

@router.callback_query(F.data == ('trainer_commands'))
async def show_trainer_commands (call: types.CallbackQuery) -> None:
    command_text = (
        '*Команнды для тренеров:*\n\n'
        '```/assess <номер телефона>```'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
    ])

    await call.message.delete()
    await call.message.answer(command_text, parse_mode='Markdown', reply_markup=kb)


motivation_service = None