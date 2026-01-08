# handlers/admins/modules/members.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import User, Organization, get_session, UserRole
from database.models import PlayerMetrics
from utils.states import MetricsStates
from services import MetricsCollector
import logging
from config import load_config
from .metrics import router as metrics_router

router = Router()
logger = logging.getLogger(__name__)

def is_super_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь суперадмином"""
    config = load_config()
    if user_id in config.admin_ids:
        return True
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if user and user.role == UserRole.SUPER_ADMIN.value:
            return True
        return False
    finally:
        session.close()

def is_admin(user_id: int) -> bool:
    """Проверить что пользователь администратор (суперадмин или админ организации)"""
    if is_super_admin(user_id):
        return True
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        from database import get_admin_roles
        admin_roles = get_admin_roles()
        
        logger.info(f"is_admin check: user_id={user_id}, role={user.role}, "
                   f"admin_roles={admin_roles}, is_admin={user.role in admin_roles}")
        
        return user.role in admin_roles
        
    except Exception as e:
        logger.error(f"Ошибка в is_admin: {e}")
        return False
    finally:
        session.close()

def is_trainer(user_id: int) -> bool:
    """Проверить, является ли пользователь тренером (только верифицированные!)"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        # Тренер должен быть верифицирован!
        return user and user.role == UserRole.TRAINER.value and user.trainer_verified
    finally:
        session.close()

def is_trainer_pending(user_id: int) -> bool:
    """Проверить, является ли пользователь тренером, ожидающим верификации"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        return user and user.role == UserRole.TRAINER.value and not user.trainer_verified
    finally:
        session.close()

def get_user_effective_role(user_id: int) -> str:
    """Получить фактическую роль пользователя с учетом верификации"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return UserRole.MEMBER.value
        
        # Если тренер не верифицирован - он участник
        if user.role == UserRole.TRAINER.value and not user.trainer_verified:
            return UserRole.MEMBER.value
        
        return user.role
    finally:
        session.close()

def has_view_access(user_id: int) -> bool:
    """Проверить, имеет ли пользователь доступ к админ-панели"""
    if is_admin(user_id):
        return True
    
    return is_trainer(user_id) 

def get_verification_permission(user_id: int) -> bool:
    """Проверить, может ли пользователь верифицировать тренеров и управлять ролями"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return False
        
        # Суперадмины могут все
        if user.role == UserRole.SUPER_ADMIN.value:
            return True
        
        # Админы организаций могут верифицировать тренеров в своей организации
        if user.role == UserRole.ORG_ADMIN.value:
            return True
        
        # Тренеры не могут верифицировать других
        return False
    except Exception as e:
        logger.error(f"Ошибка в get_verification_permission: {e}")
        return False
    finally:
        session.close()

@router.message(Command ('admin'))
async def admin_panel_button(message: types.Message) -> None:
    """Кнопка админ-панели из меню"""
    if not (is_admin(message.from_user.id) or is_trainer(message.from_user.id)):
        await message.answer("❌ У тебя нет прав администратора")
        return
    await show_admin_menu(message)

async def show_admin_menu(message: types.Message):
    """Показать админ-меню"""
    user_id = message.from_user.id
    
    session = get_session()
    user = session.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        await message.answer("❌ Пользователь не найден")
        session.close()
        return
    
    # Получаем эффективную роль с учетом верификации
    effective_role = get_user_effective_role(user_id)
    
    if effective_role == UserRole.SUPER_ADMIN.value:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏢 Выбрать организацию", callback_data="admin_select_organization")],
            [InlineKeyboardButton(text="⚡ Создать челлендж", callback_data="admin_select_org")],
            [InlineKeyboardButton(text="🎯 Сгенерировать челленджи", callback_data="admin_generate_challenges")],
            [InlineKeyboardButton(text="Команды", callback_data="admin_commands")]
        ])
        
        admin_text = f"👑 *СУПЕРАДМИН-ПАНЕЛЬ*\n\nВы: {user.name}\nВыберите действие:"
        
    elif effective_role == UserRole.ORG_ADMIN.value:
        org = session.query(Organization).filter(Organization.id == user.org_id).first()
        org_name = org.name if org else "Неизвестная организация"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Создать челлендж", callback_data="admin_select_org")],
            [InlineKeyboardButton(text="🎯 Сгенерировать челленджи", callback_data="admin_generate_challenges")],
            [InlineKeyboardButton(text="📊 Месячный отчет (PDF)", callback_data="admin_monthly_report")],
            [InlineKeyboardButton(text="📊 Статистика команды", callback_data="admin_view_stats")],
            [InlineKeyboardButton(text="👥 Управление членами", callback_data="admin_manage_members")],
            [InlineKeyboardButton(text='🕐 Часовой пояс', callback_data='admin_change_timezone')],
            [InlineKeyboardButton(text="💼 Управление вакансиями", callback_data="admin_manage_vacancies")],
            [InlineKeyboardButton(text="📨 Отправить рассылку", callback_data="admin_send_broadcast")],
            [InlineKeyboardButton(text="🏆 Лидерборд", callback_data="admin_leaderboard")],
            [InlineKeyboardButton(text="📅 Расписание сообщений", callback_data="admin_schedule_preview")]
        ])
        
        admin_text = (
            f"👨‍💼 *АДМИН-ПАНЕЛЬ ОРГАНИЗАЦИИ*\n\n"
            f"Вы: {user.name}\n"
            f"Организация: {org_name}\n\n"
            f"Выберите действие для управления командой:"
        )
        
    elif effective_role == UserRole.TRAINER.value:  # Только верифицированные!
        org = session.query(Organization).filter(Organization.id == user.org_id).first()
        org_name = org.name if org else "Неизвестная организация"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Создать челлендж", callback_data="admin_select_org")],
            [InlineKeyboardButton(text="📊 Статистика команды", callback_data="admin_view_stats")],
            [InlineKeyboardButton(text="👥 Просмотр участников", callback_data="admin_manage_members")],
            [InlineKeyboardButton(text="🏆 Лидерборд", callback_data="admin_leaderboard")],
            [InlineKeyboardButton(text='Команды', callback_data='trainer_commands')]
        ])
        
        admin_text = (
            f"👨‍🏫 *ПАНЕЛЬ ТРЕНЕРА*\n\n"
            f"Вы: {user.name}\n"
            f"Команда: {org_name}\n\n"
            f"Доступные функции:"
        )
        
    else:
        # Если пользователь тренер, но не верифицирован
        if user.role == UserRole.TRAINER.value and not user.trainer_verified:
            request_date = user.verification_requested_at.strftime("%d.%m.%Y %H:%M") \
                if user.verification_requested_at else "Неизвестно"
            
            await message.answer(
                f"⏳ *Ваша роль тренера ожидает подтверждения*\n\n"
                f"👤 {user.name}\n"
                f"📅 Запрос отправлен: {request_date}\n\n"
                f"Администратор получил уведомление о вашем запросе.\n"
                f"До подтверждения у вас права обычного участника.",
                parse_mode="Markdown"
            )
        else:
            await message.answer("❌ У тебя нет прав администратора")
        session.close()
        return
    
    session.close()
    await message.answer(admin_text, parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "admin_manage_members")
async def admin_manage_members(callback: types.CallbackQuery) -> None:
    """Управление членами команды"""
    user_id = callback.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return
        
        members = session.query(User).filter(
            User.org_id == user.org_id
        ).order_by(User.registered_at.desc()).all()
        
        text = f"👥 ЧЛЕНЫ КОМАНДЫ ({len(members)})\n\n"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        for member in members[:20]:  # Ограничиваем 20 участниками
            # Каждый участник в отдельной строке
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"{member.name} ({member.level}lvl)",
                    callback_data=f"member_detail_{member.id}"
                )
            ])

        # Кнопка "Назад" в отдельной строке
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text='◀️ Назад',
                callback_data='back_to_admin_panel'
            )
        ])
        
        await callback.message.edit_text(text, reply_markup=kb)
    finally:
        session.close()

@router.callback_query(F.data.startswith("member_detail_"))
async def member_detail(callback: types.CallbackQuery) -> None:
    """Показать детали члена команды с метриками"""
    member_id = int(callback.data.replace("member_detail_", ""))
    
    session = get_session()
    try:
        member = session.query(User).filter(User.id == member_id).first()
        if not member:
            return
        
        # Получаем последнюю оценку метрик
        latest_metrics = session.query(PlayerMetrics).filter(
            PlayerMetrics.player_id == member.user_id
        ).order_by(PlayerMetrics.assessment_date.desc()).first()
        
        from services import MetricsCollector
        stats = MetricsCollector.get_user_stats(member.user_id)
        
        text = (
            f"👤 {member.name}\n"
            f"{member.user_id}\n\n"
            f"⚽ {member.position}\n"
            f"📲 {member.phone}\n\n"
            f"💎 Очки: {member.points}\n"
            f"🥇 Уровень: {member.level}/5\n"
            f"📝 Опросов: {stats['total_surveys']}\n"
            f"⚡ Челленджей: {stats['completed_challenges']}\n"
            f"📊 Посещаемость: {stats['attendance_percent']}%\n\n"
        )
        
        # Добавляем информацию о метриках, если есть
        if latest_metrics:
            tech_avg = latest_metrics.get_technical_average()
            phys_avg = latest_metrics.get_physical_average()
            mental_avg = latest_metrics.get_mental_average()
            overall_avg = latest_metrics.get_overall_average()
            
            text += "📊 *ОЦЕНКА МЕТРИК:*\n"
            if overall_avg:
                text += f"🏆 Общий балл: {overall_avg}/10\n"
            if tech_avg:
                text += f"⚙️ Техника: {tech_avg}/10\n"
            if phys_avg:
                text += f"💪 Физика: {phys_avg}/10\n"
            if mental_avg:
                text += f"🧠 Менталка: {mental_avg}/10\n"
            
            assessment_date = latest_metrics.assessment_date.strftime("%d.%m.%Y")
            text += f"📅 Оценено: {assessment_date}\n\n"
        
        text += (
            f"Последние показатели:\n"
            f"⚡ Энергия: {member.energy or '—'}/10\n"
            f"😴 Сон: {member.sleep_quality or '—'}/10\n"
            f"🎯 Готовность: {member.readiness or '—'}/10\n"
            f"😊 Настроение: {member.mood or '—'}"
        )
        
        # Создаем клавиатуру с новыми опциями
        kb_buttons = []
        
        # Кнопка оценки метрик (только для тренеров и админов)
        coach_id = callback.from_user.id
        coach = session.query(User).filter(User.user_id == coach_id).first()
        
        if coach and (coach.role == UserRole.TRAINER.value and coach.trainer_verified) or coach.role in [UserRole.ORG_ADMIN.value, UserRole.SUPER_ADMIN.value]:
            kb_buttons.append([
                InlineKeyboardButton(
                    text="📈 Оценить метрики", 
                    callback_data=f"assess_metrics_{member.id}"
                )
            ])
        
        if latest_metrics:
            kb_buttons.append([
                InlineKeyboardButton(
                    text="📊 Детали оценки", 
                    callback_data=f"metrics_detail_{member.id}"
                )
            ])
            kb_buttons.append([
                InlineKeyboardButton(
                    text="📈 История оценок", 
                    callback_data=f"metrics_history_{member.id}"
                )
            ])
        
        kb_buttons.extend([
            [InlineKeyboardButton(text="⚡ Челленджи", callback_data=f"member_challenges_{member.id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_manage_members")]
        ])
        
        kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    finally:
        session.close()

@router.callback_query(F.data.startswith("assess_metrics_"))
async def start_assess_metrics(callback: types.CallbackQuery, state: FSMContext):
    """Начать оценку метрик игрока"""
    member_id = int(callback.data.replace("assess_metrics_", ""))
    coach_id = callback.from_user.id
    
    session = get_session()
    try:
        member = session.query(User).filter(User.id == member_id).first()
        coach = session.query(User).filter(User.user_id == coach_id).first()
        
        if not member or not coach:
            await callback.answer("❌ Ошибка: пользователь не найден", show_alert=True)
            return
        
        # Проверяем права тренера
        if coach.role == UserRole.TRAINER.value and not coach.trainer_verified:
            await callback.answer("❌ Только верифицированные тренеры могут оценивать метрики", show_alert=True)
            return
        
        if coach.role not in [UserRole.TRAINER.value, UserRole.ORG_ADMIN.value, UserRole.SUPER_ADMIN.value]:
            await callback.answer("❌ У вас нет прав для оценки метрик", show_alert=True)
            return
        
        # Проверяем, что тренер и игрок в одной организации
        if coach.org_id != member.org_id and coach.role != UserRole.SUPER_ADMIN.value:
            await callback.answer("❌ Вы можете оценивать только игроков своей команды", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            member_id=member.id,
            member_user_id=member.user_id,
            member_name=member.name,
            coach_id=coach.user_id,
            org_id=member.org_id
        )
        
        # Начинаем оценку с технических характеристик
        await ask_technical_metrics(callback, state)
        
    except Exception as e:
        logger.error(f"Ошибка в start_assess_metrics: {e}")
        await callback.answer("❌ Ошибка при начале оценки", show_alert=True)
    finally:
        session.close()

async def ask_technical_metrics(callback: types.CallbackQuery, state: FSMContext):
    """Спросить технические метрики"""
    data = await state.get_data()
    member_name = data['member_name']
    
    text = (
        f"⚙️ *ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ* — {member_name}\n\n"
        f"Оцените от 1 до 10:\n\n"
        f"1️⃣ Короткий пас\n"
        f"2️⃣ Первый контакт (касание)\n"
        f"3️⃣ Дальний пас\n"
        f"4️⃣ Выбор позиции\n"
        f"5️⃣ Аэробная игра (защита)\n"
        f"6️⃣ Удар головой\n"
        f"7️⃣ Навыки борьбы за мяч\n\n"
        f"Введите оценки через пробел (7 чисел):\n"
        f"Пример: 7 8 6 9 8 7 6"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_assessment_{data['member_id']}")]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except:
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    
    await state.set_state(MetricsStates.waiting_for_technical)

@router.callback_query(F.data == "admin_leaderboard")
async def admin_leaderboard(callback: types.CallbackQuery) -> None:
    """Показать лидерборд для админа"""
    user_id = callback.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            return
        
        leaderboard = MetricsCollector.get_leaderboard(user.org_id, limit=15)
        
        text = "🏆 ЛИДЕРБОРД КОМАНДЫ\n\n"
        
        for place in leaderboard:
            medal = "🥇" if place["position"] == 1 else "🥈" if place["position"] == 2 else "🥉" if place["position"] == 3 else "  "
            text += (
                f"{medal} #{place['position']}. {place['name']}\n"
                f"   💎 {place['points']} очков | {place['position_role']}\n"
            )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
        ])

        await callback.message.edit_text(text, reply_markup=kb)
    finally:
        session.close()