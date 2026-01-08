# handlers/admins/trainer_verification.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from .members import get_verification_permission
from database import User, Organization, UserRole, get_session
from datetime import datetime, timezone
import logging
from typing import List

logger = logging.getLogger(__name__)
router = Router()

def has_trainer_verification_permission(user_id: int) -> bool:
    """Проверить, может ли пользователь верифицировать тренеров"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        # Суперадмины и админы организаций могут верифицировать
        return user.role in [UserRole.SUPER_ADMIN.value, UserRole.ORG_ADMIN.value]
    finally:
        session.close()

def get_pending_trainer_requests(org_id: int = None) -> List[User]:
    """Получить список неподтвержденных тренеров"""
    session = get_session()
    try:
        query = session.query(User).filter(
            User.role == UserRole.TRAINER.value,
            User.trainer_verified == False,
            User.verification_requested_at.isnot(None)
        )
        
        if org_id:
            query = query.filter(User.org_id == org_id)
        
        return query.order_by(User.verification_requested_at).all()
    finally:
        session.close()

@router.callback_query(F.data == "admin_manage_roles")
async def admin_manage_roles(callback: types.CallbackQuery):
    """Управление ролями (включая верификацию тренеров)"""
    user_id = callback.from_user.id
    
    if not has_trainer_verification_permission(user_id):
        await callback.answer("❌ У вас нет прав для управления ролями", show_alert=True)
        return
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        org_id = user.org_id if user else None
        
        # Получаем запросы на верификацию
        pending_requests = get_pending_trainer_requests(org_id)
        
        builder = InlineKeyboardBuilder()
        
        if pending_requests:
            # Показываем запросы на верификацию
            builder.add(
                InlineKeyboardButton(
                    text=f"👨‍🏫 Запросы тренеров ({len(pending_requests)})",
                    callback_data="admin_view_pending_trainers"
                )
            )
        
        
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="back_to_admin_panel"
            )
        )
        
        text = "👑 Управление ролями\n\n"
        if pending_requests:
            text += f"У вас есть {len(pending_requests)} запрос(ов) на верификацию тренеров.\n\n"
        text += "Выберите действие:"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"Ошибка в admin_manage_roles: {e}")
        await callback.answer("❌ Ошибка при загрузке меню", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data == "admin_view_pending_trainers")
async def view_pending_trainers(callback: types.CallbackQuery):
    """Показать список тренеров, ожидающих верификации"""
    user_id = callback.from_user.id
    
    if not get_verification_permission(user_id):
        await callback.answer("❌ Нет прав для просмотра запросов", show_alert=True)
        return
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        org_id = user.org_id if user else None
        
        query = session.query(User).filter(
            User.role == UserRole.TRAINER.value,
            User.trainer_verified == False,
            User.verification_requested_at.isnot(None)
        )
        
        if user.role == UserRole.ORG_ADMIN.value:
            query = query.filter(User.org_id == org_id)
        
        pending_trainers = query.order_by(User.verification_requested_at).all()
        
        if not pending_trainers:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_manage_roles")]
            ])
            await callback.message.edit_text(
                "✅ Нет запросов на верификацию тренеров.",
                reply_markup=kb
            )
            return
        
        builder = InlineKeyboardBuilder()
        
        for trainer in pending_trainers:
            org = session.query(Organization).filter(Organization.id == trainer.org_id).first()
            org_name = org.name if org else "Неизвестно"
            
            request_date = trainer.verification_requested_at.strftime("%d.%m.%Y %H:%M") \
                if trainer.verification_requested_at else "Неизвестно"
            
            trainer_text = f"👨‍🏫 {trainer.name}\n🏢 {org_name} ({request_date})"
            
            builder.row(
                InlineKeyboardButton(
                    text=trainer_text,
                    callback_data=f"trainer_verify_detail_{trainer.id}"
                )
            )
        
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="admin_manage_roles"
            )
        )
        
        await callback.message.edit_text(
            f"👨‍🏫 Тренеры на верификации ({len(pending_trainers)}):\n\n"
            "Выберите тренера для просмотра деталей:",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в view_pending_trainers: {e}")
        await callback.answer("❌ Ошибка при загрузке списка", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("trainer_verify_detail_"))
async def trainer_verify_detail(callback: types.CallbackQuery):
    """Детальная информация о тренере для верификации"""
    trainer_id = int(callback.data.replace("trainer_verify_detail_", ""))
    
    if not has_trainer_verification_permission(callback.from_user.id):
        await callback.answer("❌ Нет прав для верификации", show_alert=True)
        return
    
    session = get_session()
    try:
        trainer = session.query(User).filter(User.id == trainer_id).first()
        if not trainer:
            await callback.answer("❌ Тренер не найден", show_alert=True)
            return
        
        org = session.query(Organization).filter(Organization.id == trainer.org_id).first()
        org_name = org.name if org else "Неизвестно"
        
        request_date = trainer.verification_requested_at.strftime("%d.%m.%Y %H:%M") \
            if trainer.verification_requested_at else "Неизвестно"
        
        text = (
            f"👨‍🏫 Информация о тренере:\n\n"
            f"👤 Имя: {trainer.name}\n"
            f"📱 Телефон: {trainer.phone or 'Не указан'}\n"
            f"⚽ Позиция: {trainer.position or 'Не указана'}\n"
            f"🏢 Организация: {org_name}\n"
            f"📅 Запрос отправлен: {request_date}\n"
            f"💎 Очки: {trainer.points}\n"
            f"🥇 Уровень: {trainer.level}\n\n"
            f"Подтвердить роль тренера?"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"trainer_verify_approve_{trainer.id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"trainer_verify_reject_{trainer.id}")
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_view_pending_trainers")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка в trainer_verify_detail: {e}")
        await callback.answer("❌ Ошибка при загрузке информации", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("trainer_verify_approve_"))
async def approve_trainer(callback: types.CallbackQuery):
    """Подтвердить тренера"""
    trainer_id = int(callback.data.replace("trainer_verify_approve_", ""))
    verifier_id = callback.from_user.id
    
    if not has_trainer_verification_permission(verifier_id):
        await callback.answer("❌ Нет прав для подтверждения", show_alert=True)
        return
    
    session = get_session()
    try:
        trainer = session.query(User).filter(User.id == trainer_id).first()
        if not trainer:
            await callback.answer("❌ Тренер не найден", show_alert=True)
            return
        
        # Подтверждаем тренера
        trainer.trainer_verified = True
        trainer.verified_at = datetime.now(timezone.utc)
        trainer.verified_by = verifier_id
        
        session.commit()
        
        # Отправляем уведомление тренеру
        try:
            await callback.bot.send_message(
                chat_id=trainer.chat_id,
                text="🎉 Поздравляем! Ваша роль тренера подтверждена администратором.\n\n"
                     "Теперь вам доступны все функции тренерской панели!"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление тренеру {trainer.user_id}: {e}")
        
        await callback.answer("✅ Тренер успешно подтвержден!", show_alert=True)
        
        # Возвращаемся к списку
        await view_pending_trainers(callback)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при подтверждении тренера: {e}")
        await callback.answer("❌ Ошибка при подтверждении", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("trainer_verify_reject_"))
async def reject_trainer(callback: types.CallbackQuery):
    """Отклонить запрос на тренера"""
    trainer_id = int(callback.data.replace("trainer_verify_reject_", ""))
    
    if not has_trainer_verification_permission(callback.from_user.id):
        await callback.answer("❌ Нет прав для отклонения", show_alert=True)
        return
    
    session = get_session()
    try:
        trainer = session.query(User).filter(User.id == trainer_id).first()
        if not trainer:
            await callback.answer("❌ Тренер не найден", show_alert=True)
            return
        
        # Возвращаем роль к MEMBER
        trainer.role = UserRole.MEMBER.value
        trainer.trainer_verified = False
        trainer.verification_requested_at = None
        
        session.commit()
        
        # Отправляем уведомление пользователю
        try:
            await callback.bot.send_message(
                chat_id=trainer.chat_id,
                text="❌ Ваш запрос на роль тренера был отклонен администратором.\n\n"
                     "Вы остаетесь в роли участника. Если это ошибка, обратитесь к администратору."
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {trainer.user_id}: {e}")
        
        await callback.answer("❌ Запрос тренера отклонен", show_alert=True)
        
        # Возвращаемся к списку
        await view_pending_trainers(callback)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при отклонении тренера: {e}")
        await callback.answer("❌ Ошибка при отклонении", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data == "trainer_pending")
async def trainer_pending_status(callback: types.CallbackQuery):
    """Показать статус верификации тренера"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        
        if not user or user.role != UserRole.TRAINER.value:
            await callback.answer("❌ Вы не зарегистрированы как тренер", show_alert=True)
            return
        
        if user.trainer_verified:
            await callback.answer("✅ Вы уже верифицированы как тренер!", show_alert=True)
            return
        
        request_date = user.verification_requested_at.strftime("%d.%m.%Y %H:%M") \
            if user.verification_requested_at else "Неизвестно"
        
        await callback.answer(
            f"⏳ Ваша роль тренера ожидает подтверждения.\n\n"
            f"Запрос отправлен: {request_date}\n"
            f"Администратор получил уведомление.\n"
            f"До подтверждения у вас права обычного участника.",
            show_alert=True
        )
    finally:
        session.close()

@router.message(Command("mystatus"))
async def check_my_status(message: types.Message):
    """Проверить статус верификации"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == message.from_user.id).first()
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы в системе")
            return
        
        if user.role == UserRole.TRAINER.value:
            if user.trainer_verified:
                verified_date = user.verified_at.strftime("%d.%m.%Y %H:%M") \
                    if user.verified_at else "Неизвестно"
                
                await message.answer(
                    f"✅ Вы верифицированный тренер!\n\n"
                    f"Подтверждено: {verified_date}\n"
                    f"Вам доступны все функции тренерской панели."
                )
            else:
                request_date = user.verification_requested_at.strftime("%d.%m.%Y %H:%M") \
                    if user.verification_requested_at else "Неизвестно"
                
                await message.answer(
                    f"⏳ Ваша роль тренера ожидает подтверждения.\n\n"
                    f"Запрос отправлен: {request_date}\n"
                    f"Администратор получил уведомление.\n\n"
                    f"До подтверждения у вас права обычного участника."
                )
        else:
            await message.answer(f"👤 Ваша роль: {user.role}\n\nВерификация не требуется.")
            
    finally:
        session.close()