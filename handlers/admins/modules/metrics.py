from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.states import MetricsStates
from database.models import User, UserRole, PlayerMetrics, Challenge, ChallengeStatus
from database import get_session
from datetime import datetime, timezone
import logging
import asyncio

logger = logging.getLogger(__name__)
router = Router()

# Вспомогательные функции
def get_emoji_for_score(score):
    """Получить эмодзи для оценки"""
    if score is None:
        return "⚪"
    elif score >= 9:
        return "🟢"
    elif score >= 7:
        return "🟡"
    elif score >= 5:
        return "🟠"
    else:
        return "🔴"

def create_progress_bar(score):
    """Создать текстовую progress bar"""
    if score is None:
        return "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪"
    
    filled = "🟩" * score
    empty = "⚪" * (10 - score)
    return filled + empty


@router.message(MetricsStates.waiting_for_technical)
async def process_technical_metrics(message: types.Message, state: FSMContext):
    """Обработать технические метрики"""
    try:
        # Парсим оценки
        scores = list(map(int, message.text.strip().split()))
        
        if len(scores) != 7:
            await message.answer("❌ Нужно ввести 7 чисел через пробел. Попробуйте снова:")
            return
        
        # Проверяем диапазон
        for score in scores:
            if not 1 <= score <= 10:
                await message.answer("❌ Все оценки должны быть от 1 до 10. Попробуйте снова:")
                return
        
        # Сохраняем в состоянии
        await state.update_data(
            short_pass=scores[0],
            first_touch=scores[1],
            long_pass=scores[2],
            positioning=scores[3],
            aerobic_game=scores[4],
            heading=scores[5],
            ball_fighting=scores[6]
        )
        
        await message.delete()
        await ask_physical_metrics(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, вводите только числа. Попробуйте снова:")
    except Exception as e:
        logger.error(f"Ошибка в process_technical_metrics: {e}")
        await message.answer("❌ Ошибка обработки. Попробуйте снова:")

async def ask_physical_metrics(message: types.Message, state: FSMContext):
    """Спросить физические метрики"""
    data = await state.get_data()
    member_name = data['member_name']
    
    text = (
        f"💪 *ФИЗИЧЕСКИЕ ХАРАКТЕРИСТИКИ* — {member_name}\n\n"
        f"Оцените от 1 до 10:\n\n"
        f"1️⃣ Сила\n"
        f"2️⃣ Гибкость\n"
        f"3️⃣ Баланс\n"
        f"4️⃣ Скорость\n"
        f"5️⃣ Выносливость\n"
        f"6️⃣ Ловкость\n\n"
        f"Введите оценки через пробел (6 чисел):\n"
        f"Пример: 8 7 9 8 6 7"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_assessment_{data['member_id']}")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(MetricsStates.waiting_for_physical)

@router.message(MetricsStates.waiting_for_physical)
async def process_physical_metrics(message: types.Message, state: FSMContext):
    """Обработать физические метрики"""
    try:
        # Парсим оценки
        scores = list(map(int, message.text.strip().split()))
        
        if len(scores) != 6:
            await message.answer("❌ Нужно ввести 6 чисел через пробел. Попробуйте снова:")
            return
        
        # Проверяем диапазон
        for score in scores:
            if not 1 <= score <= 10:
                await message.answer("❌ Все оценки должны быть от 1 до 10. Попробуйте снова:")
                return
        
        # Сохраняем в состоянии
        await state.update_data(
            strength=scores[0],
            flexibility=scores[1],
            balance=scores[2],
            speed=scores[3],
            stamina=scores[4],
            agility=scores[5]
        )
        
        await message.delete()
        await ask_mental_metrics(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, вводите только числа. Попробуйте снова:")
    except Exception as e:
        logger.error(f"Ошибка в process_physical_metrics: {e}")
        await message.answer("❌ Ошибка обработки. Попробуйте снова:")

async def ask_mental_metrics(message: types.Message, state: FSMContext):
    """Спросить ментальные метрики"""
    data = await state.get_data()
    member_name = data['member_name']
    
    text = (
        f"🧠 *МЕНТАЛЬНЫЕ ХАРАКТЕРИСТИКИ* — {member_name}\n\n"
        f"Оцените от 1 до 10:\n\n"
        f"1️⃣ Внимание\n"
        f"2️⃣ Аналитическое мышление\n"
        f"3️⃣ Позиционирование\n"
        f"4️⃣ Общение\n"
        f"5️⃣ Работа в команде\n"
        f"6️⃣ Концентрация\n"
        f"7️⃣ Лидерство\n"
        f"8️⃣ Волнение в игре\n\n"
        f"Введите оценки через пробел (8 чисел):\n"
        f"Пример: 7 8 6 9 8 7 6 8"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_assessment_{data['member_id']}")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(MetricsStates.waiting_for_mental)

@router.message(MetricsStates.waiting_for_mental)
async def process_mental_metrics(message: types.Message, state: FSMContext):
    """Обработать ментальные метрики"""
    try:
        # Парсим оценки
        scores = list(map(int, message.text.strip().split()))
        
        if len(scores) != 8:
            await message.answer("❌ Нужно ввести 8 чисел через пробел. Попробуйте снова:")
            return
        
        # Проверяем диапазон
        for score in scores:
            if not 1 <= score <= 10:
                await message.answer("❌ Все оценки должны быть от 1 до 10. Попробуйте снова:")
                return
        
        # Сохраняем в состоянии
        await state.update_data(
            attention=scores[0],
            analytical_thinking=scores[1],
            positioning_sense=scores[2],
            communication=scores[3],
            teamwork=scores[4],
            concentration=scores[5],
            leadership=scores[6],
            game_excitement=scores[7]
        )
        
        await message.delete()
        await ask_notes(message, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, вводите только числа. Попробуйте снова:")
    except Exception as e:
        logger.error(f"Ошибка в process_mental_metrics: {e}")
        await message.answer("❌ Ошибка обработки. Попробуйте снова:")

async def ask_notes(message: types.Message, state: FSMContext):
    """Спросить комментарии тренера"""
    data = await state.get_data()
    member_name = data['member_name']
    
    # Рассчитываем средние баллы для предпросмотра
    tech_scores = [
        data.get('short_pass'), data.get('first_touch'), data.get('long_pass'),
        data.get('positioning'), data.get('aerobic_game'), data.get('heading'),
        data.get('ball_fighting')
    ]
    tech_avg = round(sum(tech_scores) / len(tech_scores), 1)
    
    phys_scores = [
        data.get('strength'), data.get('flexibility'), data.get('balance'),
        data.get('speed'), data.get('stamina'), data.get('agility')
    ]
    phys_avg = round(sum(phys_scores) / len(phys_scores), 1)
    
    mental_scores = [
        data.get('attention'), data.get('analytical_thinking'), data.get('positioning_sense'),
        data.get('communication'), data.get('teamwork'), data.get('concentration'),
        data.get('leadership'), data.get('game_excitement')
    ]
    mental_avg = round(sum(mental_scores) / len(mental_scores), 1)
    
    overall_avg = round((tech_avg + phys_avg + mental_avg) / 3, 1)
    
    text = (
        f"📊 *ПРЕДПРОСМОТР ОЦЕНКИ* — {member_name}\n\n"
        f"⚙️ Техника: {tech_avg}/10\n"
        f"💪 Физика: {phys_avg}/10\n"
        f"🧠 Менталка: {mental_avg}/10\n"
        f"🏆 Общий балл: {overall_avg}/10\n\n"
        f"💬 *Добавьте комментарий (не обязательно):*\n"
        f"Можно оставить рекомендации, заметки или наблюдения.\n"
        f"Если комментарий не нужен, отправьте «-»"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_assessment_{data['member_id']}")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(MetricsStates.waiting_for_notes)

@router.message(MetricsStates.waiting_for_notes)
async def process_notes(message: types.Message, state: FSMContext):
    """Обработать комментарии и сохранить оценку"""
    notes = message.text.strip()
    if notes == "-":
        notes = None
    
    data = await state.get_data()
    
    session = get_session()
    try:
        # Создаем запись в базе данных
        metrics = PlayerMetrics(
            player_id=data['member_user_id'],
            coach_id=data['coach_id'],
            org_id=data['org_id'],
            
            # Технические
            short_pass=data['short_pass'],
            first_touch=data['first_touch'],
            long_pass=data['long_pass'],
            positioning=data['positioning'],
            aerobic_game=data['aerobic_game'],
            heading=data['heading'],
            ball_fighting=data['ball_fighting'],
            
            # Физические
            strength=data['strength'],
            flexibility=data['flexibility'],
            balance=data['balance'],
            speed=data['speed'],
            stamina=data['stamina'],
            agility=data['agility'],
            
            # Ментальные
            attention=data['attention'],
            analytical_thinking=data['analytical_thinking'],
            positioning_sense=data['positioning_sense'],
            communication=data['communication'],
            teamwork=data['teamwork'],
            concentration=data['concentration'],
            leadership=data['leadership'],
            game_excitement=data['game_excitement'],
            
            notes=notes,
            assessment_date=datetime.now(timezone.utc)
        )
        
        session.add(metrics)
        session.commit()
        
        # Рассчитываем итоговые баллы
        tech_avg = metrics.get_technical_average()
        phys_avg = metrics.get_physical_average()
        mental_avg = metrics.get_mental_average()
        overall_avg = metrics.get_overall_average()
        
        # Отправляем подтверждение
        text = (
            f"✅ *ОЦЕНКА СОХРАНЕНА!*\n\n"
            f"👤 Игрок: {data['member_name']}\n"
            f"📅 Дата: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📊 *РЕЗУЛЬТАТЫ:*\n"
            f"⚙️ Техника: {tech_avg}/10\n"
            f"💪 Физика: {phys_avg}/10\n"
            f"🧠 Менталка: {mental_avg}/10\n"
            f"🏆 Общий балл: {overall_avg}/10\n"
        )
        
        if notes:
            text += f"\n💬 Комментарий: {notes}"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Посмотреть детали", callback_data=f"metrics_detail_{data['member_id']}")],
            [InlineKeyboardButton(text="👥 К списку игроков", callback_data="admin_manage_members")]
        ])
        
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        
        # Отправляем уведомление игроку
        try:
            member = session.query(User).filter(User.id == data['member_id']).first()
            if member and member.chat_id:
                coach = session.query(User).filter(User.user_id == data['coach_id']).first()
                
                await message.bot.send_message(
                    chat_id=member.chat_id,
                    text=f"👨‍🏫 *Получена новая оценка от тренера!*\n\n"
                         f"Тренер: {coach.name if coach else 'Неизвестно'}\n"
                         f"Общий балл: {overall_avg}/10\n"
                         f"Дата оценки: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}\n\n"
                         f"Подробности в вашем профиле!",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление игроку: {e}")
        
        await state.clear()
        
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при сохранении метрик: {e}")
        await message.answer("❌ Ошибка при сохранении оценки. Попробуйте позже.")
    finally:
        session.close()
        await message.delete()

@router.callback_query(F.data.startswith("metrics_detail_"))
async def show_metrics_detail(callback: types.CallbackQuery):
    """Показать детализированную оценку метрик"""
    member_id = int(callback.data.replace("metrics_detail_", ""))
    
    session = get_session()
    try:
        member = session.query(User).filter(User.id == member_id).first()
        if not member:
            await callback.answer("❌ Игрок не найден", show_alert=True)
            return
        
        # Получаем последнюю оценку
        metrics = session.query(PlayerMetrics).filter(
            PlayerMetrics.player_id == member.user_id
        ).order_by(PlayerMetrics.assessment_date.desc()).first()
        
        if not metrics:
            await callback.answer("❌ Оценки не найдены", show_alert=True)
            return
        
        coach = session.query(User).filter(User.user_id == metrics.coach_id).first()
        coach_name = coach.name if coach else "Неизвестный тренер"
        
        # Формируем детальный текст
        text = f"📊 *ДЕТАЛЬНАЯ ОЦЕНКА* — {member.name}\n\n"
        text += f"👨‍🏫 Тренер: {coach_name}\n"
        text += f"📅 Дата: {metrics.assessment_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        
        # Технические характеристики
        text += "*⚙️ ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ:*\n"
        tech_metrics = [
            ("Короткий пас", metrics.short_pass),
            ("Первый контакт", metrics.first_touch),
            ("Дальний пас", metrics.long_pass),
            ("Выбор позиции", metrics.positioning),
            ("Аэробная игра", metrics.aerobic_game),
            ("Удар головой", metrics.heading),
            ("Борьба за мяч", metrics.ball_fighting),
        ]
        
        for name, score in tech_metrics:
            emoji = get_emoji_for_score(score)
            bar = create_progress_bar(score)
            text += f"{emoji} {name}: {score}/10\n{bar}\n"
        
        text += f"\n*Средний балл: {metrics.get_technical_average()}/10*\n\n"
        
        # Физические характеристики
        text += "*💪 ФИЗИЧЕСКИЕ ХАРАКТЕРИСТИКИ:*\n"
        phys_metrics = [
            ("Сила", metrics.strength),
            ("Гибкость", metrics.flexibility),
            ("Баланс", metrics.balance),
            ("Скорость", metrics.speed),
            ("Выносливость", metrics.stamina),
            ("Ловкость", metrics.agility),
        ]
        
        for name, score in phys_metrics:
            emoji = get_emoji_for_score(score)
            bar = create_progress_bar(score)
            text += f"{emoji} {name}: {score}/10\n{bar}\n"
        
        text += f"\n*Средний балл: {metrics.get_physical_average()}/10*\n\n"
        
        # Ментальные характеристики
        text += "*🧠 МЕНТАЛЬНЫЕ ХАРАКТЕРИСТИКИ:*\n"
        mental_metrics = [
            ("Внимание", metrics.attention),
            ("Аналитическое мышление", metrics.analytical_thinking),
            ("Позиционирование", metrics.positioning_sense),
            ("Общение", metrics.communication),
            ("Работа в команде", metrics.teamwork),
            ("Концентрация", metrics.concentration),
            ("Лидерство", metrics.leadership),
            ("Волнение в игре", metrics.game_excitement),
        ]
        
        for name, score in mental_metrics:
            emoji = get_emoji_for_score(score)
            bar = create_progress_bar(score)
            text += f"{emoji} {name}: {score}/10\n{bar}\n"
        
        text += f"\n*Средний балл: {metrics.get_mental_average()}/10*\n\n"
        
        # Итоги
        text += "*🏆 ИТОГИ:*\n"
        text += f"📈 Общий балл: {metrics.get_overall_average()}/10\n"
        
        if metrics.notes:
            text += f"\n💬 *Комментарий тренера:*\n{metrics.notes}\n"
        
        # Клавиатура
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 История оценок", callback_data=f"metrics_history_{member.id}")],
            [InlineKeyboardButton(text="🔄 Новая оценка", callback_data=f"assess_metrics_{member.id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"member_detail_{member.id}")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка в show_metrics_detail: {e}")
        await callback.answer("❌ Ошибка при загрузке деталей", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("metrics_history_"))
async def show_metrics_history(callback: types.CallbackQuery):
    """Показать историю оценок игрока"""
    member_id = int(callback.data.replace("metrics_history_", ""))
    
    session = get_session()
    try:
        member = session.query(User).filter(User.id == member_id).first()
        if not member:
            await callback.answer("❌ Игрок не найден", show_alert=True)
            return
        
        # Получаем все оценки
        all_metrics = session.query(PlayerMetrics).filter(
            PlayerMetrics.player_id == member.user_id
        ).order_by(PlayerMetrics.assessment_date.desc()).limit(10).all()
        
        if not all_metrics:
            await callback.answer("❌ История оценок пуста", show_alert=True)
            return
        
        text = f"📈 *ИСТОРИЯ ОЦЕНОК* — {member.name}\n\n"
        
        for i, metrics in enumerate(all_metrics, 1):
            coach = session.query(User).filter(User.user_id == metrics.coach_id).first()
            coach_name = coach.name if coach else "Неизвестно"
            
            overall_avg = metrics.get_overall_average() or 0
            
            text += (
                f"{i}. {metrics.assessment_date.strftime('%d.%m.%Y')} — "
                f"{overall_avg}/10 (тренер: {coach_name})\n"
            )
            
            if metrics.notes:
                # Обрезаем длинный комментарий
                notes_preview = metrics.notes[:50] + "..." if len(metrics.notes) > 50 else metrics.notes
                text += f"   💬 {notes_preview}\n"
            
            text += "\n"
        
        text += f"Всего оценок: {len(all_metrics)}"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Посмотреть последнюю", callback_data=f"metrics_detail_{member.id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"member_detail_{member.id}")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка в show_metrics_history: {e}")
        await callback.answer("❌ Ошибка при загрузке истории", show_alert=True)
    finally:
        session.close()

@router.callback_query(F.data.startswith("cancel_assessment_"))
async def cancel_assessment(callback: types.CallbackQuery, state: FSMContext):
    """Отменить оценку метрик"""
    await state.clear()
    member_id = int(callback.data.replace("cancel_assessment_", ""))
    
    await callback.answer("❌ Оценка отменена", show_alert=True)
    
    # Возвращаемся к деталям игрока
    await callback.message.delete()
    session = get_session()
    try:
        member = session.query(User).filter(User.id == member_id).first()
        if member:
            from handlers.admins.modules.members import member_detail as show_member_detail
            # Нужно немного изменить вызов, так как мы в другом модуле
            await show_member_detail(callback)
    finally:
        session.close()

@router.message(Command("assess"))
async def quick_assess_command(message: types.Message):
    """Быстрая команда для оценки игрока"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "📋 *Использование:*\n"
            "`/assess [номер телефона]` — начать оценку игрока\n\n"
            "Пример: `/assess 79123456789`",
            parse_mode="Markdown"
        )
        return
    
    phone = args[1]
    
    session = get_session()
    try:
        # Ищем игрока по номеру телефона
        player = session.query(User).filter(
            User.phone.like(f"%{phone}%")
        ).first()
        
        if not player:
            await message.answer("❌ Игрок с таким номером телефона не найден")
            return
        
        # Проверяем права тренера
        coach = session.query(User).filter(User.user_id == message.from_user.id).first()
        if not coach or coach.role not in [UserRole.TRAINER.value, UserRole.ORG_ADMIN.value, UserRole.SUPER_ADMIN.value]:
            await message.answer("❌ У вас нет прав для оценки игроков")
            return
        
        if coach.role == UserRole.TRAINER.value and not coach.trainer_verified:
            await message.answer("❌ Только верифицированные тренеры могут оценивать игроков")
            return
        
        # Создаем callback для начала оценки
        from aiogram.utils.callback_answer import CallbackAnswer
        await message.answer(
            f"🔍 Найден игрок: {player.name}\n"
            f"Начать оценку метрик?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ Начать оценку", 
                    callback_data=f"assess_metrics_{player.id}"
                )],
                [InlineKeyboardButton(
                    text="❌ Отмена", 
                    callback_data="cancel"
                )]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка в quick_assess_command: {e}")
        await message.answer("❌ Ошибка при поиске игрока")
    finally:
        session.close()

class MetricsCollector:
    """Сбор метрик с исправленным подсчетом челленджей"""
    
    @staticmethod
    def get_user_completed_challenges(user_id: int, start_date: datetime = None, end_date: datetime = None) -> int:
        """Получить количество ВЫПОЛНЕННЫХ челленджей пользователя"""
        session = get_session()
        try:
            query = session.query(Challenge).filter(
                Challenge.user_id == user_id,
                Challenge.status == ChallengeStatus.COMPLETED.value
            )
            
            if start_date:
                query = query.filter(Challenge.completed_at >= start_date)
            if end_date:
                query = query.filter(Challenge.completed_at <= end_date)
            
            return query.count()
        except Exception as e:
            logger.error(f"Ошибка подсчета челленджей: {e}")
            return 0
        finally:
            session.close()
    
    @staticmethod
    def get_organization_completed_challenges(org_id: int, start_date: datetime = None, end_date: datetime = None) -> int:
        """Получить количество ВЫПОЛНЕННЫХ челленджей в организации"""
        session = get_session()
        try:
            query = session.query(Challenge).join(
                User, Challenge.user_id == User.user_id
            ).filter(
                User.org_id == org_id,
                Challenge.status == ChallengeStatus.COMPLETED.value
            )
            
            if start_date:
                query = query.filter(Challenge.completed_at >= start_date)
            if end_date:
                query = query.filter(Challenge.completed_at <= end_date)
            
            return query.count()
        except Exception as e:
            logger.error(f"Ошибка подсчета челленджей организации: {e}")
            return 0
        finally:
            session.close()