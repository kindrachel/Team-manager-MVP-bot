from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy import func
from aiogram.utils.keyboard import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from utils.states import CreateOrganizationStates
from database import get_session, User, Organization, Challenge, ChallengeStatus, UserRole
from datetime import timezone, datetime
from html import escape
import logging
from services.ai_report_analyzer import AIReportAnalyzer
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

router = Router()

# Добавляем функцию is_super_admin, если ее нет в members.py
def is_super_admin(user_id: int) -> bool:
    try:
        from .members import is_super_admin as members_is_super_admin
        return members_is_super_admin(user_id)
    except ImportError:
        # Резервная проверка
        from config import load_config
        config = load_config()
        if user_id in config.admin_ids:
            return True
        
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            from database import UserRole
            return user and user.role == UserRole.SUPER_ADMIN.value
        finally:
            session.close()

@router.callback_query(F.data == "admin_select_organization")
async def admin_select_organization(callback: types.CallbackQuery):
    """Суперадмин выбирает организацию для управления"""
    user_id = callback.from_user.id
    
    if not is_super_admin(user_id):
        await callback.answer("❌ Только суперадмины могут выбирать организации", show_alert=True)
        return
    
    session = get_session()
    try:
        # Получаем все организации (кроме системы суперадминов)
        organizations = session.query(Organization).filter(
            Organization.org_type != "super_admins"
        ).order_by(Organization.name).all()
        
        if not organizations:
            await callback.message.edit_text(
                "🏢 НЕТ ДОСТУПНЫХ ОРГАНИЗАЦИЙ\n\n"
                "В системе пока нет других организаций.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Создать организацию", callback_data="superadmin_create_org")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
                ])
            )
            return
        
        text = "🏢 *ВЫБЕРИТЕ ОРГАНИЗАЦИЮ ДЛЯ УПРАВЛЕНИЯ*\n\n"
        
        # Клавиатура с организациями
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        for org in organizations:
            # Считаем количество пользователей
            user_count = session.query(User).filter(User.org_id == org.id).count()
            
            # Получаем администратора организации
            admin = session.query(User).filter(User.user_id == org.admin_id).first()
            admin_name = admin.name if admin else "Не назначен"
            
            # Создаем кнопку
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"🏢 {org.name} ({user_count} чел.)",
                    callback_data=f"superadmin_select_org_{org.id}"
                )
            ])
            
            # Добавляем в текст
            text += f"🏢 *{org.name}*\n"
            text += f"   👥 {user_count} чел. | 👑 {admin_name}\n\n"
        
        
        # Кнопки навигации
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="➕ Создать организацию", callback_data="superadmin_create_org")
        ])
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        
    finally:
        session.close()

@router.callback_query(F.data.startswith("superadmin_select_org_"))
async def superadmin_select_org_handler(callback: types.CallbackQuery, state: FSMContext):
    """Суперадмин выбрал организацию - переключаем контекст"""
    user_id = callback.from_user.id
    
    if not is_super_admin(user_id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    
    org_id = int(callback.data.replace("superadmin_select_org_", ""))
    
    session = get_session()
    try:
        # Получаем информацию об организации
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        # Сохраняем выбранную организацию в state для использования в других функциях
        await state.update_data(
            selected_org_id=org_id,
            selected_org_name=org.name
        )
        
        # Получаем статистику по организации
        user_count = session.query(User).filter(User.org_id == org.id).count()
        admin = session.query(User).filter(User.user_id == org.admin_id).first()
        challenges_count = session.query(Challenge).filter(
            Challenge.user_id.in_(
                session.query(User.user_id).filter(User.org_id == org.id)
            )
        ).count()
        
        # Текст с информацией
        text = (
            f"🏢 *УПРАВЛЕНИЕ ОРГАНИЗАЦИЕЙ*\n\n"
            f"*Вы выбрали:* {org.name}\n\n"
            f"*Основная информация:*\n"
            f"👥 Участников: {user_count}\n"
            f"👑 Администратор: {admin.name if admin else 'Не назначен'}\n"
            f"🎯 Челленджей: {challenges_count}\n"
            f"📅 Создана: {org.created_at.strftime('%d.%m.%Y')}\n\n"
            f"*Вы можете:*"
            f'* Назначить админа через команду /set_role*' 
        )
        
        # Клавиатура управления организацией
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Участники", callback_data=f"superadmin_org_members_{org_id}"),
                InlineKeyboardButton(text="📊 Статистика", callback_data=f"superadmin_org_stats_{org_id}")
            ],
            [
                InlineKeyboardButton(text="🎯 Челленджи организации", callback_data=f"admin_view_challenges_{org_id}"),
                InlineKeyboardButton(text="🏢 Сменить организацию", callback_data="admin_select_organization")
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить организацию", callback_data=f"admin_delete_org_{org_id}")
            ],
            [
                InlineKeyboardButton(text="◀️ Выйти", callback_data="back_to_admin_panel")
            ]
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        
    finally:
        session.close()

@router.callback_query(F.data.startswith("superadmin_org_members_"))
async def superadmin_manage_members(callback: types.CallbackQuery):
    """Управление участниками выбранной организации"""
    org_id = int(callback.data.replace("superadmin_org_members_", ""))
    
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        members = session.query(User).filter(User.org_id == org_id).order_by(
            User.points.desc()
        ).all()
        
        text = f"👥 *Участники организации: {org.name}*\n\n"
        
        if not members:
            text += "❌ Нет участников\n"
        else:
            text += f"Всего участников: *{len(members)}*\n\n"
            
            for i, member in enumerate(members[:10], 1):  # Показываем первых 10
                role_icon = "👑" if member.user_id == org.admin_id else "👨‍💼" if member.role == "ADMIN" else "👤"
                text += (
                    f"{i}. {role_icon} *{member.name}*\n"
                    f"   💎 {member.points} очков | 🥇 Уровень {member.level}\n"
                )
            
            if len(members) > 10:
                text += f"\n...и еще {len(members) - 10} участников"
        
        # Клавиатура
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        # Кнопки для каждого участника (первые 5)
        for member in members[:5]:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"👤 {member.name[:15]}...",
                    callback_data=f"superadmin_view_member_{member.id}"
                )
            ])
        
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"superadmin_select_org_{org_id}")
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        
    finally:
        session.close()

@router.callback_query(F.data.startswith("superadmin_view_member_"))
async def superadmin_view_member(callback: types.CallbackQuery):
    """Просмотр информации об участнике"""
    member_id = int(callback.data.replace("superadmin_view_member_", ""))
    
    session = get_session()
    try:
        member = session.query(User).filter(User.id == member_id).first()
        if not member:
            await callback.answer("❌ Участник не найден", show_alert=True)
            return
        
        org = session.query(Organization).filter(Organization.id == member.org_id).first()
        
        # Получаем статистику участника
        completed_challenges = session.query(Challenge).filter(
            Challenge.user_id == member.user_id,
            Challenge.status == "COMPLETED"
        ).count()
        
        total_challenges = session.query(Challenge).filter(
            Challenge.user_id == member.user_id
        ).count()
        
        completion_rate = (completed_challenges / total_challenges * 100) if total_challenges > 0 else 0
        
        text = (
            f"👤 <b>ПРОФИЛЬ УЧАСТНИКА</b>\n\n"
            f"<b>Имя:</b> {escape(member.name)}\n"
            f"<b>Telegram id:</b> {escape(str(member.user_id))}\n\n"
            f"<b>Телефон:</b> {escape(member.phone) if member.phone else 'Не указан'}\n"
            f"<b>Должность:</b> {escape(member.position) if member.position else 'Не указана'}\n\n"
            f"<b>Организация:</b> {escape(org.name) if org else 'Не указана'}\n"
            f"<b>Роль:</b> {escape(member.role)}\n\n"
            f"<b>Статистика:</b>\n"
            f"💎 Очков: {member.points}\n"
            f"🥇 Уровень: {member.level}\n"
            f"✅ Выполнено челленджей: {completed_challenges}/{total_challenges}\n"
            f"📊 Процент выполнения: {completion_rate:.1f}%\n\n"
            f"📅 Зарегистрирован: {member.registered_at.strftime('%d.%m.%Y')}\n"
            f"📅 Последняя активность: {member.last_active.strftime('%d.%m.%Y %H:%M') if member.last_active else 'Неизвестно'}"
        )
        
        # Клавиатура
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"superadmin_edit_member_{member.id}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"superadmin_delete_member_{member.id}")
            ],
            [
                InlineKeyboardButton(text="📊 История активностей", callback_data=f"superadmin_member_activity_{member.id}"),
                InlineKeyboardButton(text="🎯 Челленджи", callback_data=f"superadmin_member_challenges_{member.id}")
            ],
            [
                InlineKeyboardButton(text="◀️ Назад к участникам", callback_data=f"superadmin_org_members_{org.id}")
            ]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        
    finally:
        session.close()

@router.callback_query(F.data.startswith("superadmin_org_stats_"))
async def superadmin_org_stats(callback: types.CallbackQuery):
    """Статистика организации"""
    org_id = int(callback.data.replace("superadmin_org_stats_", ""))
    
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        # Получаем статистику
        total_users = session.query(User).filter(User.org_id == org_id).count()
        active_users = session.query(User).filter(
            User.org_id == org_id,
            User.last_active.isnot(None)
        ).count()
        
        # Средние показатели
        avg_points_result = session.query(func.avg(User.points)).filter(
            User.org_id == org_id
        ).scalar()
        avg_points = round(avg_points_result or 0, 1)
        
        avg_level_result = session.query(func.avg(User.level)).filter(
            User.org_id == org_id
        ).scalar()
        avg_level = round(avg_level_result or 0, 1)
        
        # Челленджи
        total_challenges = session.query(Challenge).filter(
            Challenge.user_id.in_(
                session.query(User.user_id).filter(User.org_id == org_id)
            )
        ).count()
        
        completed_challenges = session.query(Challenge).filter(
            Challenge.user_id.in_(
                session.query(User.user_id).filter(User.org_id == org_id)
            ),
            Challenge.status == "COMPLETED"
        ).count()
        
        completion_rate = (completed_challenges / total_challenges * 100) if total_challenges > 0 else 0
        
        text = (
            f"📊 *СТАТИСТИКА ОРГАНИЗАЦИИ*\n\n"
            f"🏢 *{org.name}*\n\n"
            
            f"*👥 Участники:*\n"
            f"• Всего: {total_users} чел.\n"
            f"• Активных: {active_users} чел.\n"
            f"• Средний уровень: {avg_level}\n"
            f"• Средние очки: {avg_points}\n\n"
            
            f"*🎯 Челленджи:*\n"
            f"• Всего: {total_challenges}\n"
            f"• Выполнено: {completed_challenges}\n"
            f"• Процент выполнения: {completion_rate:.1f}%\n\n"
            
            f"*📅 Активность:*\n"
            f"• Создана: {org.created_at.strftime('%d.%m.%Y')}\n"
            f"• Тип: {org.org_type or 'Не указан'}"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Отчет (PDF)", callback_data=f"superadmin_pdf_report_{org_id}")
            ],
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"superadmin_select_org_{org_id}")
            ]
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        
    finally:
        session.close()

@router.callback_query(F.data.startswith("superadmin_pdf_report_"))
async def superadmin_pdf_report_handler(callback: types.CallbackQuery):
    """Генерация и отправка PDF отчета организации"""
    org_id = int(callback.data.replace("superadmin_pdf_report_", ""))

    # Проверяем права суперадмина
    user_id = callback.from_user.id
    if not is_super_admin(user_id):
        await callback.answer("❌ Нет прав доступа", show_alert=True)
        return

    session = get_session()
    try:
        # Проверяем существование организации
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return

        # Отправляем сообщение о генерации
        await callback.message.edit_text(
            "📄 *Генерация PDF отчета...*\n\n"
            f"🏢 Организация: {org.name}\n"
            "⏳ Пожалуйста, подождите...",
            parse_mode="Markdown"
        )

        # Генерируем отчет
        analyzer = AIReportAnalyzer()
        pdf_buffer = await analyzer.generate_daily_report_pdf(org_id)

        if pdf_buffer is None:
            await callback.message.edit_text(
                "❌ *Ошибка генерации отчета*\n\n"
                "Не удалось создать PDF отчет. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data=f"superadmin_org_stats_{org_id}")]
                ])
            )
            return

        # Отправляем PDF файл
        pdf_file = BufferedInputFile(
            pdf_buffer.getvalue(),
            filename=f"report_{org.name}_{datetime.now().strftime('%d%m%Y')}.pdf"
        )

        await callback.message.answer_document(
            document=pdf_file,
            caption=f"📄 *Отчет организации*\n🏢 {org.name}\n📅 {datetime.now().strftime('%d.%m.%Y')}",
            parse_mode="Markdown"
        )

        # Возвращаемся к статистике
        await callback.message.edit_text(
            "✅ *PDF отчет отправлен!*\n\n"
            "Отчет был отправлен в виде файла выше.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к статистике", callback_data=f"superadmin_org_stats_{org_id}")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка генерации PDF отчета: {e}")
        await callback.message.edit_text(
            "❌ *Ошибка генерации отчета*\n\n"
            f"Произошла ошибка: {str(e)[:100]}...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"superadmin_org_stats_{org_id}")]
            ])
        )
    finally:
        session.close()

__all__ = ['router']


@router.callback_query(F.data.startswith("admin_view_challenges_"))
async def admin_view_challenges(callback: types.CallbackQuery):
    """Просмотр всех челленджей организации"""
    org_id = int(callback.data.replace("admin_view_challenges_", ""))
    
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        # 1. Получаем user_id (BigInteger) всех пользователей организации
        org_users = session.query(User.user_id).filter(User.org_id == org_id).all()
        user_ids = [user.user_id for user in org_users]  # Берем именно user_id (BigInteger)
        
        if not user_ids:
            text = f"В организации '{org.name}' нет пользователей."
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_view_organization_{org_id}")]
            ])
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return
        
        # 2. Получаем челленджи по user_id (BigInteger)
        challenges = session.query(Challenge).filter(
            Challenge.user_id.in_(user_ids)
        ).order_by(Challenge.created_at.desc()).all()
        
        if not challenges:
            text = (
                f"📭 *Челленджи организации*\n\n"
                f"*{org.name}*\n\n"
                f"В этой организации пока нет созданных челленджей.\n\n"
                f"ℹ️ Пользователей в организации: {len(user_ids)}"
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад к организации", 
                                    callback_data=f"admin_view_organization_{org_id}")]
            ])
            
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return
        
        # Статистика
        active_challenges = [c for c in challenges if c.status == ChallengeStatus.ACTIVE.value]
        completed_challenges = [c for c in challenges if c.status == ChallengeStatus.COMPLETED.value]
        failed_challenges = [c for c in challenges if c.status == ChallengeStatus.FAILED.value]
        pending_challenges = [c for c in challenges if c.status == ChallengeStatus.PENDING.value]
        
        total_challenges = len(challenges)
        completion_rate = (len(completed_challenges) / total_challenges * 100) if total_challenges > 0 else 0
        
        text = (
            f"🎯 *Челленджи организации*\n\n"
            f"*{org.name}*\n\n"
            f"📊 *Статистика:*\n"
            f"• Всего челленджей: {total_challenges}\n"
            f"• Активные: {len(active_challenges)}\n"
            f"• Завершённые: {len(completed_challenges)}\n"
            f"• Проваленные: {len(failed_challenges)}\n"
            f"• Ожидающие: {len(pending_challenges)}\n"
            f"• Успешность: {completion_rate:.1f}%\n\n"
            f"📋 *Последние челленджи:*"
        )
        
        # Показываем последние 5 челленджей
        for i, challenge in enumerate(challenges[:5], 1):
            # Находим пользователя по user_id (BigInteger)
            user = session.query(User).filter(User.user_id == challenge.user_id).first()
            status_icon = {
                "ACTIVE": "🟢",
                "COMPLETED": "✅",
                "FAILED": "❌",
                "PENDING": "⏳",
                "SCHEDULED": "📅"
            }.get(challenge.status, "⚪")
            
            deadline = challenge.scheduled_for.strftime("%d.%m.%Y %H:%M") if challenge.scheduled_for else "Без срока"
            user_name = user.name if user else f"User #{challenge.user_id}"
            
            # Обрезаем текст челленджа, если он слишком длинный
            challenge_text = challenge.text[:30] + "..." if len(challenge.text) > 30 else challenge.text
            text += f"\n{i}. {status_icon} {challenge_text}\n"
            text += f"   👤 {user_name}\n"
            text += f"   📅 {deadline} | 💎 {challenge.points} очков\n"
            text += f"   📊 Сложность: {challenge.difficulty or 'Не указана'}"
        
        if len(challenges) > 5:
            text += f"\n\n...и еще {len(challenges) - 5} челленджей"
        
        # Создаем клавиатуру
        buttons = []
        
        # Кнопки дополнительных действий
        buttons.append([
            InlineKeyboardButton(text="📊 Статистика", callback_data=f"admin_challenges_stats_{org_id}")
        ])
        
        buttons.append([
            InlineKeyboardButton(text="◀️ Назад к организации", callback_data=f"superadmin_select_org_{org_id}")
        ])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("admin_challenges_stats_"))
async def admin_challenges_stats(callback: types.CallbackQuery):
    """Подробная статистика челленджей"""
    org_id = int(callback.data.replace("admin_challenges_stats_", ""))
    
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        # Получаем user_id (BigInteger) пользователей организации
        user_ids = [user.user_id for user in session.query(User.user_id).filter(User.org_id == org_id).all()]
        
        if not user_ids:
            await callback.answer("❌ В организации нет пользователей", show_alert=True)
            return
        
        # Статистика через подзапрос
        from sqlalchemy import func
        
        # Общая статистика
        total_challenges = session.query(Challenge).filter(
            Challenge.user_id.in_(user_ids)
        ).count()
        
        completed_challenges = session.query(Challenge).filter(
            Challenge.user_id.in_(user_ids),
            Challenge.status == ChallengeStatus.COMPLETED.value
        ).count()
        
        # Средние показатели
        avg_points = session.query(func.avg(Challenge.points)).filter(
            Challenge.user_id.in_(user_ids)
        ).scalar() or 0
        
        # Топ пользователей по количеству челленджей
        from sqlalchemy import case
        
        top_users_subquery = session.query(
            Challenge.user_id,
            func.count(Challenge.id).label('challenge_count'),
            func.sum(case((Challenge.status == ChallengeStatus.COMPLETED.value, 1), else_=0)).label('completed_count')
        ).filter(
            Challenge.user_id.in_(user_ids)
        ).group_by(Challenge.user_id).subquery()
        
        top_users = session.query(
            User, 
            top_users_subquery.c.challenge_count,
            top_users_subquery.c.completed_count
        ).join(
            top_users_subquery, User.user_id == top_users_subquery.c.user_id
        ).order_by(top_users_subquery.c.challenge_count.desc()).limit(5).all()
        
        # Распределение по сложности
        difficulty_stats = session.query(
            Challenge.difficulty,
            func.count(Challenge.id).label('count')
        ).filter(
            Challenge.user_id.in_(user_ids)
        ).group_by(Challenge.difficulty).all()
        
        text = (
            f"📊 *Статистика челленджей*\n\n"
            f"*{org.name}*\n\n"
            f"📈 *Общая статистика:*\n"
            f"• Всего челленджей: {total_challenges}\n"
            f"• Завершено: {completed_challenges}\n"
            f"• Успешность: {(completed_challenges/total_challenges*100 if total_challenges > 0 else 0):.1f}%\n"
            f"• Средняя награда: {avg_points:.1f} очков\n\n"
        )
        
        if difficulty_stats:
            text += f"📊 *Распределение по сложности:*\n"
            for diff, count in difficulty_stats:
                if diff:
                    percentage = (count / total_challenges * 100) if total_challenges > 0 else 0
                    text += f"• {diff.capitalize()}: {count} ({percentage:.1f}%)\n"
            text += "\n"
        
        if top_users:
            text += f"🏆 *Топ участников:*\n"
            for i, (user, total, completed) in enumerate(top_users, 1):
                success_rate = (completed / total * 100) if total > 0 else 0
                text += f"{i}. {user.name}: {total} челленджей ({completed} завершено, {success_rate:.0f}%)\n"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к челленджам", 
                                callback_data=f"admin_view_challenges_{org_id}")]
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()

# handlers/admins/modules/organizations.py

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram import F

@router.callback_query(F.data == "superadmin_create_org")
async def start_create_organization(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания спортивной организации"""
    
    # Сбрасываем состояние
    await state.clear()
    
    # Создаем клавиатуру с видами спорта
    sport_types_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ Футбол", callback_data="sport_football")],
        [InlineKeyboardButton(text="🏀 Баскетбол", callback_data="sport_basketball")],
        [InlineKeyboardButton(text="🏐 Волейбол", callback_data="sport_volleyball")],
        [InlineKeyboardButton(text="🥋 Тхэквондо", callback_data="sport_taekwondo")],
        [InlineKeyboardButton(text="🔥 Танцы", callback_data="sport_dance")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
    ])
    
    text = (
        "🏅 *Создание новой спортивной организации*\n\n"
        "📋 *Шаг 1: Выберите вид спорта*\n\n"
        "Выберите из списка ниже:"
    )
    
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=sport_types_kb)
    except:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=sport_types_kb)
    
    await state.set_state("waiting_sport_type_selection")
    await callback.answer()

@router.callback_query(StateFilter("waiting_sport_type_selection"))
async def process_sport_type_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора вида спорта"""
    
    if callback.data == "cancel_creation":
        await callback.message.edit_text("❌ Создание организации отменено.")
        await state.clear()
        await callback.answer()
        return
    
    # Получаем вид спорта из callback_data
    sport_type = callback.data.replace("sport_", "")
    
    # Сохраняем в состоянии
    await state.update_data(
        sport_type=sport_type,
        direction="sport"  # Всегда спорт для новых организаций
    )
    
    # Показываем примеры названий в зависимости от вида спорта
    examples = {
        "football": "• ФК «Спартак»\n• ФК «Зенит»\n• Футбольная академия «Юность»",
        "basketball": "• БК «ЦСКА»\n• БК «Химки»\n• Баскетбольный клуб «Локомотив»",
        "volleyball": "• ВК «Зенит»\n• ВК «Динамо»\n• Волейбольный клуб «Белогорье»",
        "taekwondo": "• СК «Тайгер»\n• Клуб тхэквондо «Олимп»\n• Школа тхэквондо «Виктория»",
        "dance": "• Танцевальная студия «Грация»\n• Школа танцев «Ритм»\n• Студия «Dance Mix»"
    }
    
    sport_names = {
        "football": "⚽ Футбол",
        "basketball": "🏀 Баскетбол", 
        "volleyball": "🏐 Волейбол",
        "taekwondo": "🥋 Тхэквондо",
        "dance": "🔥 Танцы"
    }
    
    sport_display = sport_names.get(sport_type, sport_type)
    example_text = examples.get(sport_type, "• Ваша спортивная организация")
    
    text = (
        f"{sport_display} *Создание новой организации*\n\n"
        f"📝 *Шаг 2: Введите название организации*\n\n"
        f"Примеры:\n{example_text}"
    )
    
    sport_type_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к выбору спорта", callback_data="back_to_sport_selection")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
    ])
    
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=sport_type_kb)
    except:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=sport_type_kb)
    
    await state.set_state("waiting_org_name")
    await callback.answer()

@router.callback_query(StateFilter("waiting_org_name"), F.data == "back_to_sport_selection")
async def back_to_sport_selection(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору вида спорта"""
    await start_create_organization(callback, state)

@router.message(StateFilter("waiting_org_name"))
async def process_org_name(message: Message, state: FSMContext):
    """Обработка названия организации"""
    
    org_name = message.text.strip()
    
    # Валидация названия
    if len(org_name) < 2:
        await message.answer("❌ Название слишком короткое. Минимум 2 символа.\nПожалуйста, введите название еще раз:")
        return
    
    if len(org_name) > 100:
        await message.answer("❌ Название слишком длинное. Максимум 100 символов.\nПожалуйста, введите название еще раз:")
        return
    
    # Проверяем, нет ли уже организации с таким названием
    session = get_session()
    try:
        existing_org = session.query(Organization).filter(
            func.lower(Organization.name) == func.lower(org_name)
        ).first()
        
        if existing_org:
            await message.answer(
                f"❌ Организация с названием «{org_name}» уже существует.\n"
                "Пожалуйста, введите другое название:"
            )
            return
    finally:
        session.close()
    
    # Сохраняем название
    await state.update_data(org_name=org_name)
    
    # Получаем данные из состояния
    data = await state.get_data()
    sport_type = data.get("sport_type", "football")
    
    # Определяем, какие позиции показывать в зависимости от вида спорта
    if sport_type == "football":
        positions_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Вратарь", callback_data="admin_goalkeeper")],
            [InlineKeyboardButton(text="Защитник", callback_data="admin_defender")],
            [InlineKeyboardButton(text="Полузащитник", callback_data="admin_midfielder")],
            [InlineKeyboardButton(text="Нападающий", callback_data="admin_forward")],
            [InlineKeyboardButton(text="Тренер", callback_data="admin_coach")],
            [InlineKeyboardButton(text="Менеджер", callback_data="admin_manager")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_name_input"),
             InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ])
        position_text = "Выберите вашу позицию в организации:"
        
    elif sport_type in ["basketball", "volleyball"]:
        positions_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Игрок", callback_data="admin_player")],
            [InlineKeyboardButton(text="Тренер", callback_data="admin_coach")],
            [InlineKeyboardButton(text="Менеджер", callback_data="admin_manager")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_name_input"),
             InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ])
        position_text = "Выберите вашу позицию в организации:"
        
    else:  # taekwondo, dance и другие
        positions_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Спортсмен", callback_data="admin_athlete")],
            [InlineKeyboardButton(text="Тренер", callback_data="admin_coach")],
            [InlineKeyboardButton(text="Администратор", callback_data="admin_manager")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_name_input"),
             InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
        ])
        position_text = "Выберите вашу позицию в организации:"
    
    text = (
        f"✅ Название сохранено: *{org_name}*\n\n"
        f"👤 *Шаг 3: {position_text}*"
    )
    
    await message.answer(text, parse_mode="Markdown", reply_markup=positions_kb)
    await state.set_state("waiting_admin_position")

@router.callback_query(StateFilter("waiting_org_name"), F.data == "back_to_name_input")
async def back_to_name_input(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к вводу названия"""
    data = await state.get_data()
    sport_type = data.get("sport_type", "football")
    
    sport_names = {
        "football": "⚽ Футбол",
        "basketball": "🏀 Баскетбол", 
        "volleyball": "🏐 Волейбол",
        "taekwondo": "🥋 Тхэквондо",
        "dance": "🔥 Танцы"
    }
    
    examples = {
        "football": "• ФК «Спартак»\n• ФК «Зенит»\n• Футбольная академия «Юность»",
        "basketball": "• БК «ЦСКА»\n• БК «Химки»\n• Баскетбольный клуб «Локомотив»",
        "volleyball": "• ВК «Зенит»\n• ВК «Динамо»\n• Волейбольный клуб «Белогорье»",
        "taekwondo": "• СК «Тайгер»\n• Клуб тхэквондо «Олимп»\n• Школа тхэквондо «Виктория»",
        "dance": "• Танцевальная студия «Грация»\n• Школа танцев «Ритм»\n• Студия «Dance Mix»"
    }
    
    sport_display = sport_names.get(sport_type, sport_type)
    example_text = examples.get(sport_type, "• Ваша спортивная организация")
    
    text = (
        f"{sport_display} *Создание новой организации*\n\n"
        f"📝 Введите название организации:\n\n"
        f"Примеры:\n{example_text}"
    )
    
    sport_type_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к выбору спорта", callback_data="back_to_sport_selection")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=sport_type_kb)
    await state.set_state("waiting_org_name")
    await callback.answer()

@router.callback_query(StateFilter("waiting_admin_position"))
async def process_admin_position(callback: types.CallbackQuery, state: FSMContext):
    """Обработка позиции администратора"""
    
    if callback.data == "cancel_creation":
        await callback.message.edit_text("❌ Создание организации отменено.")
        await state.clear()
        await callback.answer()
        return
    
    if callback.data == "back_to_name_input":
        await back_to_name_input(callback, state)
        return
    
    # Сохраняем позицию администратора
    position_map = {
        "admin_goalkeeper": "Вратарь",
        "admin_defender": "Защитник", 
        "admin_midfielder": "Полузащитник",
        "admin_forward": "Нападающий",
        "admin_player": "Игрок",
        "admin_athlete": "Спортсмен",
        "admin_coach": "Тренер",
        "admin_manager": "Менеджер"
    }
    
    admin_position = position_map.get(callback.data, "Администратор")
    await state.update_data(admin_position=admin_position)
    
    # Получаем все данные
    data = await state.get_data()
    org_name = data.get("org_name", "Новая организация")
    sport_type = data.get("sport_type", "football")
    direction = data.get("direction", "sport")
    
    sport_names = {
        "football": "⚽ Футбол",
        "basketball": "🏀 Баскетбол", 
        "volleyball": "🏐 Волейбол", 
        "taekwondo": "🥋 Тхэквондо",
        "dance": "🔥 Танцы"
    }
    
    sport_display = sport_names.get(sport_type, sport_type)
    
    # Клавиатура подтверждения
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать организацию", callback_data="confirm_creation")],
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data="edit_org_name")],
        [InlineKeyboardButton(text="✏️ Изменить вид спорта", callback_data="edit_sport_type")],
        [InlineKeyboardButton(text="✏️ Изменить позицию", callback_data="edit_admin_position")],
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]
    ])
    
    text = (
        "🏅 *Подтверждение создания организации*\n\n"
        f"📋 *Проверьте данные:*\n\n"
        f"🏢 *Название:* {org_name}\n"
        f"🎯 *Вид спорта:* {sport_display}\n"
        f"👤 *Ваша позиция:* {admin_position}\n"
        f"📂 *Направление:* Спорт\n\n"
        f"✅ *Нажмите «Создать организацию» для подтверждения*\n"
        f"✏️ *Или измените нужные данные*"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=confirm_kb)
    await state.set_state("waiting_confirmation")
    await callback.answer()

@router.callback_query(StateFilter("waiting_confirmation"))
async def handle_confirmation_actions(callback: types.CallbackQuery, state: FSMContext):
    """Обработка действий в подтверждении"""
    
    if callback.data == "confirm_creation":
        await finalize_organization_creation(callback, state)
        return
    
    elif callback.data == "edit_org_name":
        await back_to_name_input(callback, state)
        return
    
    elif callback.data == "edit_sport_type":
        await start_create_organization(callback, state)
        return
    
    elif callback.data == "edit_admin_position":
        data = await state.get_data()
        sport_type = data.get("sport_type", "football")
        
        # Повторяем логику выбора позиции
        if sport_type == "football":
            positions_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Вратарь", callback_data="admin_goalkeeper")],
                [InlineKeyboardButton(text="Защитник", callback_data="admin_defender")],
                [InlineKeyboardButton(text="Полузащитник", callback_data="admin_midfielder")],
                [InlineKeyboardButton(text="Нападающий", callback_data="admin_forward")],
                [InlineKeyboardButton(text="Тренер", callback_data="admin_coach")],
                [InlineKeyboardButton(text="Менеджер", callback_data="admin_manager")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_confirmation"),
                 InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
            ])
        elif sport_type in ["basketball", "volleyball"]:
            positions_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Игрок", callback_data="admin_player")],
                [InlineKeyboardButton(text="Тренер", callback_data="admin_coach")],
                [InlineKeyboardButton(text="Менеджер", callback_data="admin_manager")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_confirmation"),
                 InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
            ])
        else:
            positions_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Спортсмен", callback_data="admin_athlete")],
                [InlineKeyboardButton(text="Тренер", callback_data="admin_coach")],
                [InlineKeyboardButton(text="Администратор", callback_data="admin_manager")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_confirmation"),
                 InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")]
            ])
        
        await callback.message.edit_text(
            "Выберите вашу позицию в организации:",
            reply_markup=positions_kb
        )
        await state.set_state("waiting_admin_position")
        await callback.answer()
        return
    
    elif callback.data == "back_to_confirmation":
        # Возвращаемся к подтверждению
        data = await state.get_data()
        org_name = data.get("org_name", "Новая организация")
        sport_type = data.get("sport_type", "football")
        admin_position = data.get("admin_position", "Администратор")
        
        sport_names = {
            "football": "⚽ Футбол",
            "basketball": "🏀 Баскетбол", 
            "volleyball": "🏐 Волейбол",
            "taekwondo": "🥋 Тхэквондо",
            "dance": "🔥 Танцы"
        }
        
        sport_display = sport_names.get(sport_type, sport_type)
        
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать организацию", callback_data="confirm_creation")],
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data="edit_org_name")],
            [InlineKeyboardButton(text="✏️ Изменить вид спорта", callback_data="edit_sport_type")],
            [InlineKeyboardButton(text="✏️ Изменить позицию", callback_data="edit_admin_position")],
            [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]
        ])
        
        text = (
            "🏅 *Подтверждение создания организации*\n\n"
            f"📋 *Проверьте данные:*\n\n"
            f"🏢 *Название:* {org_name}\n"
            f"🎯 *Вид спорта:* {sport_display}\n"
            f"👤 *Ваша позиция:* {admin_position}\n"
            f"📂 *Направление:* Спорт\n\n"
            f"✅ *Нажмите «Создать организацию» для подтверждения*\n"
            f"✏️ *Или измените нужные данные*"
        )
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=confirm_kb)
        await state.set_state("waiting_confirmation")
        await callback.answer()
        return
    
    elif callback.data == "cancel_creation":
        await callback.message.edit_text("❌ Создание организации отменено.")
        await state.clear()
        await callback.answer()

async def finalize_organization_creation(callback: types.CallbackQuery, state: FSMContext):
    """Финальное создание организации"""
    
    data = await state.get_data()
    
    org_name = data.get("org_name")
    sport_type = data.get("sport_type", "football")
    direction = data.get("direction", "sport")
    admin_position = data.get("admin_position", "Администратор")
    user_id = callback.from_user.id
    
    if not org_name:
        await callback.answer("❌ Ошибка: название организации не указано.", show_alert=True)
        await state.clear()
        return
    
    session = get_session()
    try:
        # Создаем организацию
        organization = Organization(
            name=org_name,
            org_type=sport_type,  # Сохраняем вид спорта как тип организации
            admin_id=user_id,  # Текущий пользователь как администратор
            created_at=datetime.now(timezone.utc)
        )
        
        session.add(organization)
        session.flush()  # Получаем ID организации
        
        # Создаем/обновляем пользователя как администратора организации
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if user:
            # Обновляем существующего пользователя
            user.org_id = organization.id
            user.role = UserRole.SUPER_ADMIN.value
            user.position = admin_position
            user.direction = direction
            user.sport_type = sport_type
        else:
            # Создаем нового пользователя
            user = User(
                user_id=user_id,
                chat_id=callback.message.chat.id,
                name=callback.from_user.full_name,
                org_id=organization.id,
                role=UserRole.ORG_ADMIN.value,
                position=admin_position,
                direction=direction,
                sport_type=sport_type,
                points=0,
                level=1
            )
            session.add(user)
        
        session.commit()
        
        # Успешное сообщение
        sport_names = {
            "football": "⚽ Футбол",
            "basketball": "🏀 Баскетбол", 
            "volleyball": "🏐 Волейбол",
            "taekwondо": "🥋 Тхэквондо",
            "dance": "🔥 Танцы"
        }
        
        sport_display = sport_names.get(sport_type, sport_type)
        
        success_text = (
            f"🎉 *Организация успешно создана!*\n\n"
            f"🏢 *Название:* {org_name}\n"
            f"🎯 *Вид спорта:* {sport_display}\n"
            f"👤 *Ваша роль:* Администратор ({admin_position})\n"
            f"🆔 *ID организации:* {organization.id}\n\n"
            f"Используйте кнопку «Организации» в меню."
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В админ панель", callback_data="back_to_admin_panel")]
        ])
        
        await callback.message.edit_text(success_text, parse_mode="Markdown", reply_markup=kb)

        
    except Exception as e:
        logger.error(f"Ошибка создания организации: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()
        await state.clear()

# Хендлер для отмены из любого состояния
@router.callback_query(F.data == "cancel_creation")
async def cancel_creation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания из любого состояния"""
    await callback.message.edit_text("❌ Создание организации отменено.")
    await state.clear()
    await callback.answer()

@router.message(CreateOrganizationStates.CONFIRMATION, F.text == "❌ Отменить создание")
async def cancel_create_organization(message: Message, state: FSMContext):
    """Отмена создания организации"""
    await message.answer("❌ Создание организации отменено.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@router.message(
    CreateOrganizationStates.WAITING_FOR_NAME,
    CreateOrganizationStates.WAITING_FOR_TYPE,
    CreateOrganizationStates.WAITING_FOR_ADMIN,
    CreateOrganizationStates.CONFIRMATION,
    F.text.lower().in_(["отмена", "cancel", "/отмена", "/cancel"])
)
async def cancel_creation_from_any_state(message: Message, state: FSMContext):
    """Отмена из любого состояния"""
    await message.answer("❌ Создание организации отменено.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Команда отмены текущего действия"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("✅ Текущее действие отменено.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("🤷 Нет активных действий для отмены.")

@router.callback_query(F.data.startswith("admin_delete_org_"))
async def start_delete_organization(callback: types.CallbackQuery, state: FSMContext):
    """Начало удаления организации"""
    org_id = int(callback.data.replace("admin_delete_org_", ""))
    
    session = get_session()
    try:
        # Получаем организацию
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return
        
        # Получаем статистику организации
        user_count = session.query(User).filter(User.org_id == org_id).count()
        
        # Получаем количество челленджей - исправляем JOIN
        challenge_count = session.query(Challenge).join(
            User, Challenge.user_id == User.user_id  # Явно указываем условие соединения
        ).filter(
            User.org_id == org_id
        ).count()
        
        # Предупреждающее сообщение
        warning_text = (
            f"⚠️ *УДАЛЕНИЕ ОРГАНИЗАЦИИ*\n\n"
            f"🏢 *Название:* {org.name}\n"
            f"🎯 *Тип:* {org.org_type}\n"
            f"👤 *Админ ID:* {org.admin_id}\n\n"
            f"📊 *Статистика:*\n"
            f"• Участников: {user_count}\n"
            f"• Челленджей: {challenge_count}\n\n"
            f"🔥 *Что будет удалено:*\n"
            f"1. Все данные организации\n"
            f"2. Связь с пользователями\n"
            f"3. Все челленджи\n"
            f"4. Статистика и история\n\n"
            f"❌ *ЭТО ДЕЙСТВИЕ НЕОБРАТИМО!*\n\n"
            f"Вы уверены, что хотите удалить организацию?\n"
            f"*Для подтверждения введите название организации:*"
        )
        
        # Создаем клавиатуру с отменой
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить удаление", callback_data=f"cancel_delete_{org_id}")]
        ])
        
        await callback.message.edit_text(
            warning_text, 
            parse_mode="Markdown", 
            reply_markup=cancel_kb
        )
        
        # Сохраняем данные в состоянии
        await state.update_data(
            org_id=org_id,
            org_name=org.name,
            user_count=user_count,
            challenge_count=challenge_count
        )
        
        # Устанавливаем состояние ожидания подтверждения
        await state.set_state("waiting_delete_confirmation")
        
    except Exception as e:
        logger.error(f"Ошибка при начале удаления: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()
    
    await callback.answer()

@router.message(StateFilter("waiting_delete_confirmation"))
async def confirm_delete_organization(message: Message, state: FSMContext):
    """Подтверждение удаления по названию"""
    
    user_input = message.text.strip()
    data = await state.get_data()
    
    org_id = data.get("org_id")
    org_name = data.get("org_name")
    user_count = data.get("user_count", 0)
    challenge_count = data.get("challenge_count", 0)
    
    # Проверяем, совпадает ли введенное название с названием организации
    if user_input.lower() != org_name.lower():
        await message.answer(
            f"❌ Название не совпадает!\n\n"
            f"Вы ввели: *{user_input}*\n"
            f"Нужно ввести: *{org_name}*\n\n"
            f"Попробуйте еще раз или отмените удаление:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить удаление", callback_data=f"cancel_delete_{org_id}")]
            ])
        )
        return
    
    # Показываем финальное предупреждение
    final_warning_text = (
        f"🔥 *ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ!*\n\n"
        f"Вы собираетесь удалить:\n"
        f"🏢 *{org_name}*\n\n"
        f"📊 Будет удалено:\n"
        f"• {user_count} участников\n"
        f"• {challenge_count} челленджей\n"
        f"• Вся история и статистика\n\n"
        f"❌ *ЭТО ДЕЙСТВИЕ НЕЛЬЗЯ ОТМЕНИТЬ!*\n\n"
        f"Вы точно уверены?"
    )
    
    final_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ", callback_data=f"final_delete_{org_id}"),
            InlineKeyboardButton(text="❌ НЕТ, ОТМЕНИТЬ", callback_data=f"cancel_delete_{org_id}")
        ]
    ])
    
    await message.answer(final_warning_text, parse_mode="Markdown", reply_markup=final_kb)
    await state.set_state("waiting_final_confirmation")

@router.callback_query(F.data.startswith("final_delete_"))
async def final_delete_organization(callback: types.CallbackQuery, state: FSMContext):
    """Финальное удаление организации"""
    org_id = int(callback.data.replace("final_delete_", ""))
    
    session = get_session()
    try:
        # Получаем данные об организации перед удалением
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            await state.clear()
            return
        
        org_name = org.name
        
        # Получаем статистику перед удалением
        user_count = session.query(User).filter(User.org_id == org_id).count()
        
        # Получаем количество челленджей - исправляем JOIN
        challenge_count = session.query(Challenge).join(
            User, Challenge.user_id == User.user_id
        ).filter(
            User.org_id == org_id
        ).count()
        
        # 1. Удаляем челленджи пользователей организации
        if challenge_count > 0:
            # Получаем user_id всех пользователей организации (BIGINT)
            org_users = session.query(User.user_id).filter(User.org_id == org_id).all()
            org_user_ids = [user.user_id for user in org_users]
            
            # Удаляем челленджи
            if org_user_ids:
                session.query(Challenge).filter(
                    Challenge.user_id.in_(org_user_ids)
                ).delete(synchronize_session=False)
        
        # 2. Обновляем пользователей (убираем org_id, сбрасываем роль)
        users = session.query(User).filter(User.org_id == org_id).all()
        for user in users:
            user.org_id = None
            # Если пользователь был админом организации, сбрасываем роль
            if user.role == UserRole.ORG_ADMIN.value:
                user.role = UserRole.MEMBER.value
        
        # 3. Удаляем организацию
        session.delete(org)
        
        # 4. Коммитим все изменения
        session.commit()
        
        # Формируем отчет об удалении
        report_text = (
            f"🗑️ *Организация удалена*\n\n"
            f"🏢 *Название:* {org_name}\n"
            f"📊 *Удалено:*\n"
            f"• {user_count} участников отвязано\n"
            f"• {challenge_count} челленджей удалено\n"
            f"• Все данные организации очищены\n\n"
            f"✅ Удаление успешно завершено."
        )
        
        # Клавиатура возврата
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏢 К списку организаций", callback_data="admin_select_organization")]
        ])
        
        await callback.message.edit_text(report_text, parse_mode="Markdown", reply_markup=back_kb)
        
        # Логируем удаление
        logger.warning(
            f"Организация удалена: ID={org_id}, Название={org_name}, "
            f"Пользователей={user_count}, Челленджей={challenge_count}, "
            f"Удалил пользователь={callback.from_user.id}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при удалении организации: {e}")
        session.rollback()
        await callback.answer(f"❌ Ошибка при удалении: {str(e)}", show_alert=True)
        
        # Восстанавливаем сообщение об ошибке
        error_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏢 К списку организаций", callback_data="admin_select_organization")]
        ])
        
        await callback.message.edit_text(
            f"❌ *Ошибка при удалении организации*\n\n"
            f"Причина: {str(e)[:200]}\n\n"
            f"Обратитесь к разработчику.",
            parse_mode="Markdown",
            reply_markup=error_kb
        )
    finally:
        session.close()
        await state.clear()
    
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_delete_"))
async def cancel_delete_organization(callback: types.CallbackQuery, state: FSMContext):
    """Отмена удаления организации - возвращаем к тому же виду, что и при первом входе в организацию"""
    await state.clear()

    org_id = int(callback.data.replace("cancel_delete_", ""))

    # Возвращаем к тому же интерфейсу управления организацией, что и при первом выборе
    session = get_session()
    try:
        # Получаем информацию об организации
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.answer("❌ Организация не найдена", show_alert=True)
            return

        # Получаем статистику по организации
        user_count = session.query(User).filter(User.org_id == org.id).count()
        admin = session.query(User).filter(User.user_id == org.admin_id).first()
        challenges_count = session.query(Challenge).filter(
            Challenge.user_id.in_(
                session.query(User.user_id).filter(User.org_id == org.id)
            )
        ).count()

        # Текст с информацией (тот же, что и при первом входе)
        text = (
            f"🏢 *УПРАВЛЕНИЕ ОРГАНИЗАЦИЕЙ*\n\n"
            f"*Вы выбрали:* {org.name}\n\n"
            f"*Основная информация:*\n"
            f"👥 Участников: {user_count}\n"
            f"👑 Администратор: {admin.name if admin else 'Не назначен'}\n"
            f"🎯 Челленджей: {challenges_count}\n"
            f"📅 Создана: {org.created_at.strftime('%d.%m.%Y')}\n\n"
            f"*Вы можете:*"
            f'* Назначить админа через команду /set_role*'
        )

        # Клавиатура управления организацией (та же, что и при первом входе)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Участники", callback_data=f"superadmin_org_members_{org_id}"),
                InlineKeyboardButton(text="📊 Статистика", callback_data=f"superadmin_org_stats_{org_id}")
            ],
            [
                InlineKeyboardButton(text="🎯 Челленджи организации", callback_data=f"admin_view_challenges_{org_id}"),
                InlineKeyboardButton(text="🏢 Сменить организацию", callback_data="admin_select_organization")
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить организацию", callback_data=f"admin_delete_org_{org_id}")
            ],
            [
                InlineKeyboardButton(text="◀️ Выйти", callback_data="back_to_admin_panel")
            ]
        ])

        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

    except Exception as e:
        logger.error(f"Ошибка при отмене удаления: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        session.close()

    await callback.answer("✅ Удаление отменено")

# Обработчик для отмены из любого состояния
@router.callback_query(F.state.in_(["waiting_delete_confirmation", "waiting_final_confirmation"]))
async def cancel_from_any_state(callback: types.CallbackQuery, state: FSMContext):
    """Отмена удаления из любого состояния"""
    await state.clear()
    
    await callback.message.edit_text(
        "✅ Удаление организации отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏢 К списку организаций", callback_data="superadmin_organizations")]
        ])
    )
    await callback.answer()