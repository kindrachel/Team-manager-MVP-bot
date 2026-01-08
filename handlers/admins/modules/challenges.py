from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from utils.states import AdminStates
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardMarkup, InlineKeyboardButton
from ..permissions import require_admin, AdminPermission, AdminContext
from ..menu_manager import menu_manager
from database import get_session, User, Organization, Challenge, ChallengeStatus, UserRole
from utils.helpers import split_long_message
import asyncio
import logging

logger = logging.getLogger(__name__)

router = Router()

@router.callback_query(F.data == "admin_select_org")
async def admin_create_challenge(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Начать создание челленджа с фиксированными баллами"""
    user_id = callback.from_user.id
    
    from .members import is_admin, is_super_admin, is_trainer
    if not is_admin or is_trainer(user_id):
        await callback.message.edit_text("❌ Нет прав")
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.message.edit_text("❌ Вы не зарегистрированы")
            return
        
        # Проверяем, есть ли у пользователя организация
        if not user.org_id:
            await callback.message.edit_text(
                "❌ Вы не привязаны к организации\n\n"
                "Обратитесь к суперадмину для решения проблемы."
            )
            return
        
        # Для суперадминов: показываем выбор организации
        if is_super_admin(user_id):
            organizations = session.query(Organization).filter(
                Organization.org_type != "super_admins"
            ).all()
            
            if organizations:
                kb = InlineKeyboardMarkup(inline_keyboard=[])
                text = "🏢 *ВЫБЕРИТЕ ОРГАНИЗАЦИЮ ДЛЯ ЧЕЛЛЕНДЖА*\n\n"
                
                for org in organizations:
                    user_count = session.query(User).filter(User.org_id == org.id).count()
                    kb.inline_keyboard.append([
                        InlineKeyboardButton(
                            text=f"{org.name} ({user_count} чел.)",
                            callback_data=f"challenge_select_org_{org.id}"
                        )
                    ])
                
                # Добавляем кнопку "Моя организация"
                kb.inline_keyboard.append([
                    InlineKeyboardButton(
                        text=f"🏢 {user.organization.name if user.organization else 'Моя организация'}",
                        callback_data=f"challenge_use_my_org"
                    )
                ])
                
                kb.inline_keyboard.append([
                    InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")
                ])
                
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
                return
        
        # Для обычных админов и суперадминов без выбора: сразу создаем в своей организации
        await state.update_data(
            org_id=user.org_id,
            created_by=user.user_id,
            org_name=user.organization.name if user.organization else None
        )
        
        await callback.message.edit_text(
            "✍️ *СОЗДАНИЕ ЧЕЛЛЕНДЖА*\n\n"
            "Напишите текст челленджа (максимум 500 символов):\n\n"
            "💎 Каждый челлендж принесет участникам *3 балла*",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_challenge_text)
        
    finally:
        session.close()

@router.callback_query(F.data.startswith("challenge_select_org_"))
async def challenge_select_org(callback: types.CallbackQuery, state: FSMContext):
    """Суперадмин выбрал организацию для челленджа"""
    org_id = int(callback.data.replace("challenge_select_org_", ""))
    
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        await state.update_data(
            org_id=org_id,
            created_by=callback.from_user.id,
            org_name=org.name
        )
        
        await callback.message.edit_text(
            f"🏢 *Организация: {org.name}*\n\n"
            "✍️ Напишите текст челленджа (максимум 500 символов):\n\n"
            "💎 Каждый челлендж принесет участникам *3 балла*",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_challenge_text)
        
    finally:
        session.close()

@router.callback_query(F.data == "challenge_use_my_org")
async def challenge_use_my_org(callback: types.CallbackQuery, state: FSMContext):
    """Суперадмин выбрал свою организацию для челленджа"""
    user_id = callback.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.answer("❌ У вас нет организации", show_alert=True)
            return
        
        org = user.organization
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        await state.update_data(
            org_id=user.org_id,
            created_by=user.user_id,
            org_name=org.name
        )
        
        await callback.message.edit_text(
            f"🏢 *Организация: {org.name}*\n\n"
            "✍️ Напишите текст челленджа (максимум 500 символов):\n\n"
            "💎 Каждый челлендж принесет участникам *3 балла*",
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_challenge_text)
        
    finally:
        session.close()

@router.message(AdminStates.waiting_for_challenge_text)
async def process_challenge_text(message: types.Message, state: FSMContext) -> None:
    """Обработка текста челленджа с фиксированными баллами"""
    if len(message.text) > 500:
        await message.answer("❌ Текст слишком длинный (макс 500 символов)")
        return
    
    await state.update_data(challenge_text=message.text)
    
    data = await state.get_data()
    
    confirmation_text = (
        f"📋 Проверьте создаваемый челлендж:\n\n"
        f"📝 *Текст:* {data['challenge_text']}\n"
        f"💎 *Награда:* 3 балла\n\n"
        f"✅ Отправить этот челлендж всем членам команды?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отправить", callback_data="confirm_challenge_send"),
            InlineKeyboardButton(text="❌ Нет, изменить", callback_data="cancel_challenge_create")
        ]
    ])
    
    await message.answer(confirmation_text, parse_mode="Markdown", reply_markup=kb)
    await state.set_state(AdminStates.waiting_for_challenge_confirmation)

@router.callback_query(AdminStates.waiting_for_challenge_confirmation, F.data == "confirm_challenge_send")
async def confirm_and_send_challenge(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Подтверждение и отправка челленджа всем участникам"""
    data = await state.get_data()
    
    session = get_session()
    try:
        creator_telegram_id = callback.from_user.id
        creator = session.query(User).filter(User.user_id == creator_telegram_id).first()
        
        if not creator:
            await callback.message.edit_text("❌ Ошибка: Вы не зарегистрированы в системе")
            session.close()
            return
        
        # Получаем название организации для сообщения
        org = session.query(Organization).filter(Organization.id == data["org_id"]).first()
        org_name = org.name if org else "Неизвестная организация"
        
        # Получаем участников организации
        members = session.query(User).filter(
            User.org_id == data["org_id"],
            User.role == UserRole.MEMBER.value
        ).all()
        
        # НЕ СОЗДАЕМ челленджи здесь! Создаем их только в notify_users_about_challenge
        # Формируем успешное сообщение
        success_text = (
            f"✅ *Челлендж отправлен на утверждение участникам!*\n\n"
            f"🏢 *Организация:* {org_name}\n"
            f"📝 *Текст:* {data['challenge_text'][:100]}...\n"
            f"💎 *Награда:* 3 балла за выполнение\n"
            f"👥 *Получатели:* {len(members)} членов команды\n\n"
            f"📨 *Каждый участник получит уведомление с предложением:*\n"
            f"1️⃣ ✅ Принять челлендж\n"
            f"2️⃣ ❌ Отклонить\n"
            f"3️⃣ 📝 Написать свой вариант"
        )
        
        await callback.message.edit_text(success_text, parse_mode="Markdown")
        
        # Отправляем уведомления участникам
        if len(members) > 0:
            await notify_users_about_challenge(
                bot=callback.bot,
                members=members,
                challenge_text=data["challenge_text"],
                count=len(members),
                creator_user_id=creator.user_id,
                org_name=org_name
            )
        
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка создания челленджа: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        session.close()
        await state.clear()

@router.callback_query(AdminStates.waiting_for_challenge_confirmation, F.data == "cancel_challenge_create")
async def cancel_challenge_create(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Отмена создания челленджа"""
    await state.clear()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Создать новый челлендж", callback_data="admin_create_challenge")],
        [InlineKeyboardButton(text="◀️ Назад в админ-панель", callback_data="back_to_admin_panel")]
    ])
    
    await callback.message.edit_text(
        "❌ Создание челленджа отменено.",
        reply_markup=kb
    )

async def notify_users_about_challenge(bot, members, challenge_text, count, creator_user_id=None, org_name=None):
    """
    Отправка уведомлений пользователям о новом челлендже с выбором действий
    """
    session = get_session()
    try:
        notification_header = "🎯 *НОВЫЙ ЧЕЛЛЕНДЖ!*\n\n"
        if org_name:
            notification_header = f"🎯 *НОВЫЙ ЧЕЛЛЕНДЖ В {org_name.upper()}!*\n\n"
        
        notification_text = (
            f"{notification_header}"
            f"💎 *Награда:* 3 балла\n\n"
            f"Выберите действие:"
        )
        
        for member in members:
            if creator_user_id and member.user_id == creator_user_id:
                continue
                
            if member.chat_id:
                try:
                    # Создаем предложенный челлендж СО СТАТУСОМ OFFERED
                    from database import Challenge, ChallengeStatus
                    from datetime import datetime, timezone as tz
                    
                    offered_challenge = Challenge(
                        user_id=member.user_id,
                        text=challenge_text,
                        points=3,
                        status=ChallengeStatus.OFFERED.value,  # Используем OFFERED
                        created_by=creator_user_id if creator_user_id else member.user_id,
                        created_at=datetime.now(tz.utc),
                        is_custom=True,
                        difficulty="medium",
                        duration="15-20 минут"
                    )
                    
                    session.add(offered_challenge)
                    session.flush()
                    offered_challenge_id = offered_challenge.id
                    
                    # Создаем клавиатуру с callback данными
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Получить",
                                callback_data=f"challenge_accept_{offered_challenge_id}"
                            ),
                            InlineKeyboardButton(
                                text="❌ Отклонить",
                                callback_data=f"challenge_decline_{offered_challenge_id}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="📝 Написать задание",
                                callback_data=f"challenge_custom_{offered_challenge_id}"
                            )
                        ]
                    ])
                    
                    await bot.send_message(
                        member.chat_id,
                        notification_text,
                        parse_mode="Markdown",
                        reply_markup=kb
                    )
                    
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление пользователю {member.user_id}: {e}")
        
        session.commit()
        
    except Exception as e:
        logger.error(f"Ошибка в notify_users_about_challenge: {e}")
        session.rollback()
    finally:
        session.close()

@router.callback_query(F.data.startswith("points_"))
async def process_challenge_points(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка очков за челлендж"""
    points = int(callback.data.replace("points_", ""))
    data = await state.get_data()
    
    session = get_session()
    try:

        creator_telegram_id = callback.from_user.id
        creator = session.query(User).filter(User.user_id == creator_telegram_id).first()
        
        if not creator:
            await callback.message.edit_text("❌ Ошибка: Вы не зарегистрированы в системе")
            session.close()
            return
        

        members = session.query(User).filter(
            User.org_id == data["org_id"],
            User.role == UserRole.MEMBER.value
        ).all()
        
        created_count = 0
        for member in members:
     
            if member.user_id == creator.user_id:
                continue
                
            challenge = Challenge(
                user_id=member.user_id, 
                text=data["challenge_text"],
                status=ChallengeStatus.PENDING.value,
                points=points,
                created_by=creator.user_id 
            )
            session.add(challenge)
            created_count += 1
        
        session.commit()
        
        success_text = (
            f"✅ Челлендж создан!\n\n"
            f"📝 {data['challenge_text']}\n"
            f"💎 {points} очков\n"
            f"👥 Отправлено {created_count} членам команды"
        )
        
        await callback.message.edit_text(success_text)
        
    except Exception as e:
        session.rollback()
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        session.close()
        await state.clear()


@router.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_menu(callback: types.CallbackQuery):
    """Общая функция возврата в админ-меню"""
    from handlers.admins.router import show_admin_menu
    ctx = AdminContext(callback.from_user.id)
    await show_admin_menu(callback.message, ctx, edit=True)

# Экспорт роутера обязательно!
__all__ = ['router']