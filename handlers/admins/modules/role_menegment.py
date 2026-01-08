# handlers/admins/role_management.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.states import RoleManagementStates
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import User, Organization, UserRole, get_session
from datetime import datetime, timezone
import logging
from typing import List

logger = logging.getLogger(__name__)
router = Router()

def get_verification_permission(user_id: int) -> bool:
    """Проверить, может ли пользователь управлять ролями"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        # Суперадмины могут управлять всеми
        if user.role == UserRole.SUPER_ADMIN.value:
            return True
        
        # Админы организаций могут управлять в своей организации
        if user.role == UserRole.ORG_ADMIN.value:
            return True
        
        return False
    finally:
        session.close()

@router.callback_query(F.data == "admin_manage_roles")
async def admin_manage_roles(callback: types.CallbackQuery, state: FSMContext):
    """Главное меню управления ролями"""
    if not get_verification_permission(callback.from_user.id):
        await callback.answer("❌ У вас нет прав для управления ролями", show_alert=True)
        return
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        org_id = user.org_id if user else None
        
        # Получаем запросы на верификацию тренеров
        pending_trainers = session.query(User).filter(
            User.role == UserRole.TRAINER.value,
            User.trainer_verified == False,
            User.verification_requested_at.isnot(None)
        )
        
        if user.role == UserRole.ORG_ADMIN.value:
            pending_trainers = pending_trainers.filter(User.org_id == org_id)
        
        pending_count = pending_trainers.count()
        
        builder = InlineKeyboardBuilder()
        
        if pending_count > 0:
            builder.row(
                InlineKeyboardButton(
                    text=f"👨‍🏫 Запросы тренеров ({pending_count})",
                    callback_data="admin_view_pending_trainers"
                )
            )
        
        builder.row(
            InlineKeyboardButton(
                text="📝 Назначить/изменить роль",
                callback_data="admin_promote_user"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="back_to_admin_panel"
            )
        )
        
        text = "👑 Управление ролями\n\n"
        if pending_count > 0:
            text += f"У вас есть {pending_count} запрос(ов) на верификацию тренеров.\n\n"
        text += "Выберите действие:"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"Ошибка в admin_manage_roles: {e}")
        await callback.answer("❌ Ошибка при загрузке меню", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data == "admin_promote_user")
async def start_promote_user(callback: types.CallbackQuery, state: FSMContext):
    """Начать процесс назначения роли"""
    if not get_verification_permission(callback.from_user.id):
        await callback.answer("❌ Нет прав для назначения ролей", show_alert=True)
        return
    
    session = get_session()
    try:
        admin_user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        org_id = admin_user.org_id
        
        # Получаем пользователей для назначения ролей
        if admin_user.role == UserRole.SUPER_ADMIN.value:
            # Суперадмин видит всех пользователей
            users = session.query(User).order_by(User.name).limit(50).all()
        else:
            # Админ организации видит только своих
            users = session.query(User).filter(
                User.org_id == org_id
            ).order_by(User.name).limit(50).all()
        
        if not users:
            await callback.answer("❌ Нет пользователей для назначения ролей", show_alert=True)
            return
        
        builder = InlineKeyboardBuilder()
        
        for user in users:
            # Показываем текущую роль
            role_display = {
                UserRole.MEMBER.value: "👤",
                UserRole.TRAINER.value: "👨‍🏫" if user.trainer_verified else "⏳",
                UserRole.ORG_ADMIN.value: "👨‍💼",
                UserRole.SUPER_ADMIN.value: "👑"
            }.get(user.role, "❓")
            
            user_text = f"{role_display} {user.name} ({user.phone or 'нет тел.'})"
            
            builder.row(
                InlineKeyboardButton(
                    text=user_text,
                    callback_data=f"promote_select_user_{user.id}"
                )
            )
        
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_manage_roles")
        )
        
        await callback.message.edit_text(
            "👥 Выберите пользователя для изменения роли:",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в start_promote_user: {e}")
        await callback.answer("❌ Ошибка при загрузке пользователей", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("promote_select_user_"))
async def select_user_for_promotion(callback: types.CallbackQuery, state: FSMContext):
    """Выбрать пользователя и показать доступные роли"""
    user_id = int(callback.data.replace("promote_select_user_", ""))
    
    if not get_verification_permission(callback.from_user.id):
        await callback.answer("❌ Нет прав для назначения ролей", show_alert=True)
        return
    
    session = get_session()
    try:
        admin_user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        target_user = session.query(User).filter(User.id == user_id).first()
        
        if not target_user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Проверяем права на изменение этого пользователя
        if admin_user.role == UserRole.ORG_ADMIN.value:
            if target_user.org_id != admin_user.org_id:
                await callback.answer("❌ Вы можете управлять только пользователями своей организации", show_alert=True)
                return
        
        await state.update_data(
            target_user_id=target_user.id,
            target_user_name=target_user.name
        )
        
        # Определяем доступные роли в зависимости от прав админа
        builder = InlineKeyboardBuilder()
        
        if admin_user.role == UserRole.SUPER_ADMIN.value:
            # Суперадмин может назначать все роли
            available_roles = [
                (UserRole.MEMBER.value, "👤 Участник"),
                (UserRole.TRAINER.value, "👨‍🏫 Тренер"),
                (UserRole.ORG_ADMIN.value, "👨‍💼 Админ организации"),
                (UserRole.SUPER_ADMIN.value, "👑 Суперадмин")
            ]
        else:
            # Админ организации может назначать только участников и тренеров
            available_roles = [
                (UserRole.MEMBER.value, "👤 Участник"),
                (UserRole.TRAINER.value, "👨‍🏫 Тренер")
            ]
        
        for role_value, role_name in available_roles:
            # Помечаем текущую роль
            is_current = target_user.role == role_value
            prefix = "✅ " if is_current else ""
            
            builder.row(
                InlineKeyboardButton(
                    text=f"{prefix}{role_name}",
                    callback_data=f"promote_set_role_{role_value}"
                )
            )
        
        builder.row(
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_promote_user")
        )
        
        current_role_display = {
            UserRole.MEMBER.value: "👤 Участник",
            UserRole.TRAINER.value: "👨‍🏫 Тренер" + (" (верифицирован)" if target_user.trainer_verified else " (ожидает верификации)"),
            UserRole.ORG_ADMIN.value: "👨‍💼 Админ организации",
            UserRole.SUPER_ADMIN.value: "👑 Суперадмин"
        }.get(target_user.role, "❓ Неизвестно")
        
        await callback.message.edit_text(
            f"👤 Пользователь: {target_user.name}\n"
            f"📱 Телефон: {target_user.phone or 'Не указан'}\n"
            f"🏢 Организация: {target_user.org_id}\n"
            f"🎯 Текущая роль: {current_role_display}\n\n"
            f"Выберите новую роль:",
            reply_markup=builder.as_markup()
        )
        
        await state.set_state(RoleManagementStates.waiting_for_role_selection)
        
    except Exception as e:
        logger.error(f"Ошибка в select_user_for_promotion: {e}")
        await callback.answer("❌ Ошибка при выборе пользователя", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("promote_set_role_"))
async def set_user_role(callback: types.CallbackQuery, state: FSMContext):
    """Установить новую роль пользователю"""
    new_role = callback.data.replace("promote_set_role_", "")
    
    if not get_verification_permission(callback.from_user.id):
        await callback.answer("❌ Нет прав для назначения ролей", show_alert=True)
        return
    
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    target_user_name = data.get('target_user_name')
    
    if not target_user_id:
        await callback.answer("❌ Ошибка: пользователь не выбран", show_alert=True)
        return
    
    session = get_session()
    try:
        admin_user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        target_user = session.query(User).filter(User.id == target_user_id).first()
        
        if not target_user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        old_role = target_user.role
        
        # Проверяем права на изменение роли
        if admin_user.role == UserRole.ORG_ADMIN.value:
            if target_user.org_id != admin_user.org_id:
                await callback.answer("❌ Вы можете управлять только пользователями своей организации", show_alert=True)
                return
            
            # Админ организации не может назначать админов и суперадминов
            if new_role in [UserRole.ORG_ADMIN.value, UserRole.SUPER_ADMIN.value]:
                await callback.answer("❌ Вы не можете назначать эту роль", show_alert=True)
                return
        
        # Обновляем роль
        target_user.role = new_role
        
        # Если назначаем тренера - требуется верификация
        if new_role == UserRole.TRAINER.value:
            target_user.trainer_verified = False
            target_user.verification_requested_at = datetime.now(timezone.utc)
            target_user.verified_by = None
            target_user.verified_at = None
        else:
            # Для других ролей верификация не требуется
            target_user.trainer_verified = True
            target_user.verification_requested_at = None
        
        session.commit()
        
        # Отправляем уведомление пользователю
        role_names = {
            UserRole.MEMBER.value: "участника",
            UserRole.TRAINER.value: "тренера (требует верификации)",
            UserRole.ORG_ADMIN.value: "администратора организации",
            UserRole.SUPER_ADMIN.value: "суперадмина"
        }
        
        new_role_name = role_names.get(new_role, "неизвестной роли")
        old_role_name = role_names.get(old_role, "неизвестной роли")
        
        try:
            await callback.bot.send_message(
                chat_id=target_user.chat_id,
                text=f"👑 Ваша роль изменена!\n\n"
                     f"Старая роль: {old_role_name}\n"
                     f"Новая роль: {new_role_name}\n\n"
                     f"Изменение выполнено администратором: {admin_user.name}"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {target_user.user_id}: {e}")
        
        await callback.answer(f"✅ Роль изменена на: {new_role_name}", show_alert=True)
        
        # Возвращаемся к выбору пользователя
        await admin_manage_roles(callback, state)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при изменении роли: {e}")
        await callback.answer("❌ Ошибка при изменении роли", show_alert=True)
    finally:
        session.close()
        await state.clear()