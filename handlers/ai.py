# handlers/ai.py - исправленная версия
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from datetime import datetime
import json

from services.ai_helper import AIHelper
from services.ai_service import AIService
from database import User, Challenge, Survey, Organization, get_session
from keyboards import main_menu, challenge_types, report_types, progress_actions
from utils.motivation import MotivationSystem


router = Router()
ai_service = AIService()
ai_helper = AIHelper(ai_service)
logger = logging.getLogger(__name__)

try:
    from services.report_generator import ReportGenerator
    HAS_REPORT_GENERATOR = True
except ImportError:
    HAS_REPORT_GENERATOR = False
    logger.warning("ReportGenerator не найден, отчеты не будут создаваться")

# Определение состояний
class UserStates(StatesGroup):
    choosing_direction = State()
    waiting_challenge_completion = State()
    waiting_question = State()

def _create_progress_bar(progress_percentage: float) -> str:
    """Создание визуальной прогресс-бара"""
    bars = 10
    filled = int(progress_percentage * bars / 100)
    empty = bars - filled
    return f"[{'█' * filled}{'░' * empty}] {progress_percentage:.1f}%"

@router.message(Command("challenge"))
async def create_challenge_handler(message: Message, state: FSMContext):
    """Создание индивидуального челленджа"""
    user_id = message.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            await message.answer("Сначала пройдите регистрацию /start")
            return
            
        await message.answer(
            "🎯 Выберите направление для челленджа:",
            reply_markup=challenge_types()
        )
        await state.set_state(UserStates.choosing_direction)
        
    except Exception as e:
        logger.error(f"Ошибка в create_challenge_handler: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")
    finally:
        session.close()

@router.callback_query(F.data.startswith("direction_"))
async def process_direction(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора направления и генерация челленджа"""
    direction = callback.data.split("_")[1]  # football/company/growth
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == callback.from_user.id).first()
        
        if not user:
            await callback.message.edit_text("Пользователь не найден. Пройдите /start")
            await state.clear()
            return
        
        # Собираем данные пользователя
        surveys = session.query(Survey).filter(Survey.user_id == user.id).order_by(Survey.created_at.desc()).limit(3).all()
        challenges = session.query(Challenge).filter(Challenge.user_id == user.id).all()
        
        user_data = {
            "user_id": user.id,
            "name": user.name,
            "level": user.level,
            "points": user.points,
            "direction": direction,
            "available_time": "15-30",
            "last_metrics": {
                "last_survey_score": surveys[0].score if surveys else 0,
                "avg_energy": sum(s.energy for s in surveys) / len(surveys) if surveys else 0,
                "completion_rate": len([c for c in challenges if c.status == "COMPLETED"]) / len(challenges) * 100 if challenges else 0
            } if surveys else {},
            "previous_successes": [
                {"challenge": c.text[:50] + "...", "completed_at": c.completed_at.strftime("%d.%m.%Y") if c.completed_at else "N/A"}
                for c in challenges[-3:] if c.status == "COMPLETED"
            ] if challenges else []
        }
        
        # Генерация персонализированного челленджа через AI
        await callback.message.edit_text("🤖 Генерирую индивидуальный челлендж...")
        
        # Используем экземпляр ai_service
        challenge_data = await ai_service.generate_personalized_challenge(
            user_id=user.id,
            direction=direction,
            user_data=user_data
        )
        
        # Сохранение челленджа в БД
        new_challenge = Challenge(
            user_id=user.id,
            text=challenge_data["text"],
            points=3,  # ФИКСИРОВАННЫЕ 3 БАЛЛА
            difficulty=challenge_data.get("difficulty", "medium"),
            estimated_time=challenge_data.get("estimated_time", "15 минут"),
            direction=direction,
            ai_generated=True,
            status="ACTIVE"
        )
        session.add(new_challenge)
        session.commit()
        
        # Форматированный вывод челленджа
        success_tips = challenge_data.get('success_tips', [])
        tips_text = "\n".join([f"• {tip}" for tip in success_tips]) if success_tips else "• Верь в себя!"
        
        challenge_text = f"""
🎯 *Ваш персонализированный челлендж*:

{challenge_data['text']}

📊 *Детали*:
• Сложность: {challenge_data['difficulty']}
• Время: {challenge_data['estimated_time']}
• Награда: {challenge_data['points']} очков

💡 *Советы для успеха*:
{tips_text}

🎯 *Почему именно этот челлендж*:
{challenge_data.get('why_this_challenge', 'Поможет развить ключевые навыки')}

Готовы принять вызов? Напишите /complete когда выполните!
        """
        
        await callback.message.edit_text(
            challenge_text,
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        
        await state.update_data(challenge_id=new_challenge.id)
        await state.set_state(UserStates.waiting_challenge_completion)
        
    except Exception as e:
        logger.error(f"Ошибка генерации челленджа: {e}")
        await callback.message.edit_text(
            "⚠️ Не удалось сгенерировать челлендж. Попробуйте позже.",
            reply_markup=main_menu()
        )
        await state.clear()
    finally:
        session.close()

@router.message(Command("complete"))
async def complete_challenge(message: Message, state: FSMContext):
    """Завершение челленджа"""
    user_id = message.from_user.id
    session = get_session()
    
    try:
        # Получаем данные из состояния
        state_data = await state.get_data()
        challenge_id = state_data.get("challenge_id")
        
        if not challenge_id:
            # Ищем активный челлендж пользователя
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                active_challenge = session.query(Challenge).filter(
                    Challenge.user_id == user.id,
                    Challenge.status == "ACTIVE"
                ).order_by(Challenge.created_at.desc()).first()
                
                if active_challenge:
                    challenge_id = active_challenge.id
        
        if challenge_id:
            challenge = session.query(Challenge).filter(Challenge.id == challenge_id).first()
            if challenge:
                # Обновляем статус и добавляем очки
                challenge.status = "COMPLETED"
                challenge.completed_at = datetime.now()
                
                user = session.query(User).filter(User.id == challenge.user_id).first()
                if user:
                    user.points += challenge.points
                    # Проверяем повышение уровня (например, каждые 100 очков)
                    if user.points // 100 > (user.points - challenge.points) // 100:
                        user.level += 1
                        await message.answer(f"🎉 Поздравляем! Вы достигли {user.level} уровня!")
                
                session.commit()
                
                # Мотивация после завершения
                motivation = await ai_service.get_motivation_phrase(
                    user_id=user.id if user else None,
                    context={"situation": "challenge_completed"}
                )
                
                await message.answer(
                    f"✅ Челлендж выполнен!\n"
                    f"🎁 Получено: {challenge.points} очков\n\n"
                    f"💫 {motivation}",
                    parse_mode="Markdown"
                )
            else:
                await message.answer("Челлендж не найден.")
        else:
            await message.answer("У вас нет активных челленджей.")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка завершения челленджа: {e}")
        await message.answer("Ошибка при завершении челленджа.")
    finally:
        session.close()

@router.message(F.text.contains("?"))
async def handle_question(message: Message):
    """Обработчик вопросов с '?'"""
    question = message.text
    
    try:
        # Собираем контекст
        context = {}
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == message.from_user.id).first()
            if user:
                context = {
                    "user_name": user.name,
                    "user_level": user.level
                }
        finally:
            session.close()
        
        # Показываем индикатор
        typing_msg = await message.answer("🤔 Думаю...")
        
        # ВАЖНО: используем ПЕРЕИМЕНОВАННЫЙ метод
        answer = await ai_service.get_ai_response(question, context)
        
        await typing_msg.delete()
        await message.answer(answer, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка обработки вопроса: {e}")
        await message.answer("🤖 Вопросы с '?' временно не работают. Используйте /ask")

@router.message(Command("progress"))
async def show_progress(message: Message):
    """Показать прогресс пользователя с AI-анализом"""
    user_id = message.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await message.answer("Сначала пройдите регистрацию /start")
            return
        
        # AI-анализ прогресса
        typing_msg = await message.answer("📈 Анализирую ваш прогресс...")
        
        # Используем экземпляр ai_service
        analysis = await ai_service.analyze_user_progress(user_id=user.id)
        
        await typing_msg.delete()
        
        # Безопасно получаем данные
        try:
            surveys = session.query(Survey).filter(Survey.user_id == user.id).all()
            survey_count = len(surveys)
        except:
            survey_count = 0
        
        try:
            challenges = session.query(Challenge).filter(Challenge.user_id == user.id).all()
            challenge_count = len(challenges)
            completed_count = len([c for c in challenges if hasattr(c, 'status') and c.status == "COMPLETED"])
        except:
            challenge_count = 0
            completed_count = 0
        
        progress_text = f"""
📊 *Ваш прогресс - {user.name}*

{analysis.get('executive_summary', 'Вот ваша статистика:')}

🏆 *Достижения*:
{chr(10).join(f"• {ach}" for ach in analysis.get('key_achievements', ['Пока нет достижений']))}

🌟 *Ваши сильные стороны*:
{chr(10).join(f"• {strength}" for strength in analysis.get('strengths', ['Мотивация', 'Регулярность']))}

🎯 *Над чем поработать*:
{chr(10).join(f"• {area}" for area in analysis.get('growth_areas', ['Нет данных']))}

📈 *Рекомендации на неделю*:
{chr(10).join(f"• {rec}" for rec in analysis.get('weekly_recommendations', ['Выполнить новый челлендж']))}

💪 *Мотивация*:
{analysis.get('personalized_motivation', 'Продолжайте в том же духе!')}

🔢 *Статистика*:
• Уровень: {getattr(user, 'level', 1)}
• Очки: {getattr(user, 'points', 0)}
• Выполнено челленджей: {completed_count}/{challenge_count}
• Пройдено опросов: {survey_count}
        """
        
        # Рассчитываем прогресс до следующего уровня
        level = getattr(user, 'level', 1)
        points = getattr(user, 'points', 0)
        level_progress = (points % 100) / 100 * 100
        
        # Добавляем визуальный прогресс-бар
        progress_bar = _create_progress_bar(level_progress)
        progress_text += f"\n\n📊 Прогресс до {level + 1} уровня: {progress_bar}"
        
        await message.answer(progress_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка показа прогресса: {e}")
        await message.answer("Не удалось загрузить прогресс. Попробуйте позже.")
    finally:
        session.close()

@router.callback_query(F.data == "get_motivation")
async def send_motivation_callback(callback: CallbackQuery):
    """Отправка мотивационной фразы по запросу"""
    user_id = callback.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if user:
            motivation = await ai_service.get_motivation_phrase(
                user_id=user.id,
                context={"situation": "on_demand"}
            )
        else:
            motivation = "Каждый шаг имеет значение. Начни свой путь к успеху сегодня! 🚀"
        
        await callback.message.answer(f"💫 *Мотивация для тебя*:\n\n{motivation}", parse_mode="Markdown")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка отправки мотивации: {e}")
        await callback.message.answer("Не удалось получить мотивацию. Попробуйте позже.")
    finally:
        session.close()

@router.message(Command("report"))
async def generate_report(message: Message):
    """Генерация и скачивание отчетов"""
    user_id = message.from_user.id
    
    await message.answer(
        "📋 Выберите тип отчета:",
        reply_markup=report_types()
    )

@router.callback_query(F.data.startswith("report_"))
async def process_report(callback: CallbackQuery):
    """Обработка выбора типа отчета"""
    report_type = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.message.edit_text("Пользователь не найден.")
            return
        
        await callback.message.edit_text(f"📊 Готовлю {report_type} отчет...")
        
        if report_type == "personal":
            # AI-анализ для детального персонального отчета
            analysis = await ai_service.analyze_user_progress(user_id=user.id)
            
            # Создание PDF отчета
            try:
                report_generator = ReportGenerator()
                report_path = await report_generator.create_personal_report(
                    user=user,
                    ai_analysis=analysis
                )
                
                # Отправка файла пользователю
                document = FSInputFile(report_path, filename=f"отчет_{user.name}_{datetime.now().strftime('%d.%m.%Y')}.pdf")
                await callback.message.answer_document(
                    document=document,
                    caption=f"📄 Ваш персональный отчет\nДата: {datetime.now().strftime('%d.%m.%Y')}"
                )
                
                await callback.message.answer(
                    f"✅ Отчет готов!\n\n{analysis.get('executive_summary', 'Ваш прогресс впечатляет!')}"
                )
                
            except Exception as e:
                logger.error(f"Ошибка создания отчета: {e}")
                await callback.message.edit_text("❌ Не удалось создать PDF отчет. Вот текстовый вариант:")
                await callback.message.answer(
                    f"📊 *Персональный отчет*\n\n"
                    f"{analysis.get('executive_summary', 'Нет данных')}\n\n"
                    f"*Достижения:* {', '.join(analysis.get('key_achievements', []))}\n\n"
                    f"*Рекомендации:* {', '.join(analysis.get('weekly_recommendations', []))}"
                )
            
        elif report_type == "team" and user.org_id:
            # AI-анализ команды
            team_analysis = await ai_service.generate_team_report(org_id=user.org_id)
            
            if "error" in team_analysis:
                await callback.message.edit_text(team_analysis["error"])
                return
            
            # Создание командного отчета
            try:
                report_generator = ReportGenerator()
                report_path = await report_generator.create_team_report(
                    org_id=user.org_id,
                    ai_analysis=team_analysis
                )
                
                document = FSInputFile(report_path, filename=f"отчет_команды_{datetime.now().strftime('%d.%m.%Y')}.pdf")
                await callback.message.answer_document(
                    document=document,
                    caption=f"📊 Отчет команды\nДата: {datetime.now().strftime('%d.%m.%Y')}"
                )
                
                await callback.message.answer(
                    f"✅ Командный отчет готов!\n\n{team_analysis.get('executive_summary', 'Команда показывает хорошие результаты!')}"
                )
                
            except Exception as e:
                logger.error(f"Ошибка создания командного отчета: {e}")
                await callback.message.edit_text("❌ Не удалось создать PDF отчет. Вот текстовый вариант:")
                await callback.message.answer(
                    f"👥 *Командный отчет*\n\n"
                    f"{team_analysis.get('executive_summary', 'Нет данных')}\n\n"
                    f"*Рекомендации:* {', '.join(team_analysis.get('recommendations', []))}"
                )
        else:
            await callback.message.edit_text("У вас нет команды или выбран неверный тип отчета.")
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета: {e}")
        await callback.message.edit_text("❌ Не удалось сгенерировать отчет. Попробуйте позже.")
    finally:
        session.close()

# Хэндлер для опросов с мотивацией
@router.callback_query(F.data == "survey_completed")
async def survey_completed(callback: CallbackQuery):
    """Мотивация после прохождения опроса"""
    user_id = callback.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        # Получаем мотивационную фразу
        motivation = await ai_service.get_motivation_phrase(
            user_id=user.id,
            context={"situation": "after_survey"}
        )
        
        # Анимированная отправка
        messages = [
            "✨ Отлично! Анализирую ответы...",
            "📈 Добавляю очки прогресса...",
            "💫 Готово! Ваша мотивация на сегодня:"
        ]
        
        for msg in messages:
            sent_msg = await callback.message.answer(msg)
            await asyncio.sleep(1.5)
            await sent_msg.delete()
        
        await callback.message.answer(
            f"🎯 *{motivation}*\n\n"
            f"Ваши усилия ведут к росту! Проверьте прогресс: /progress",
            parse_mode="Markdown"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в survey_completed: {e}")
        await callback.message.answer("Спасибо за прохождение опроса! Проверьте ваш прогресс /progress")
    finally:
        session.close()

@router.message(F.text == '💬 Спросить AI')
async def ask_to_ai (message: Message):
    """"Спросить ИИ"""
    text = (
        '*Задать вопрос Искуственному интелекту*\n\n'
        'Чтобы спросить введите команду `/ask` и задайте свой вопрос\n\n'
        '*Пример:* /ask Кто ты?'
                )
    
    await message.answer (text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]))

# Дополнительные команды
@router.message(Command("ask"))
async def handle_ask_command(message: Message):
    """Обработчик команды /ask"""
    if len(message.text.split()) < 2:
        await message.answer("Напишите вопрос после команды /ask")
        return
    
    question = message.text.split(maxsplit=1)[1]
    
    try:
        # Собираем контекст
        context = {}
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == message.from_user.id).first()
            if user:
                context = {
                    "user_name": user.name,
                    "user_level": user.level
                }
        finally:
            session.close()
        
        typing_msg = await message.answer("🤔 Думаю над ответом...")
        
        # Используем тот же метод что и для "?"
        answer = await ai_service.get_ai_response(question, context)
        
        await typing_msg.delete()
        await message.answer(answer, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка команды /ask: {e}")
        await message.answer("❌ Не удалось получить ответ. Попробуйте позже.")

@router.message(Command("motivation"))
async def send_motivation_command(message: Message):
    """Команда для получения мотивации"""
    user_id = message.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if user:
            motivation = await ai_service.get_motivation_phrase(
                user_id=user.id,
                context={"situation": "on_demand"}
            )
        else:
            motivation = "Каждый день - новая возможность стать лучше! 🌟"
        
        await message.answer(f"💫 *Мотивация для тебя*:\n\n{motivation}", parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка отправки мотивации: {e}")
        await message.answer("Держись! У тебя все получится! 💪")
    finally:
        session.close()

@router.message(Command("test_ai"))
async def test_ai(message: Message):
    """Тест всех AI функций"""
    await message.answer("🧪 Тестирую AI функции...")
    
    try:
        # 1. Тест простого ответа
        await message.answer("1️⃣ Тест простого ответа...")
        
        # Используем helper для теста
        response = await ai_helper.get_simple_response("Привет")
        await message.answer(f"✅ Ответ: {response[:100]}...")
        
        # 2. Тест генерации челленджа
        await message.answer("2️⃣ Тест генерации челленджа...")
        challenge = await ai_service.generate_personalized_challenge(
            user_id=message.from_user.id,
            direction="football",
            user_data={"level": 1, "points": 0}
        )
        await message.answer(f"✅ Челлендж: {challenge['text'][:100]}...")
        
        # 3. Тест мотивации
        await message.answer("3️⃣ Тест мотивации...")
        motivation = await ai_service.get_motivation_phrase()
        await message.answer(f"✅ Мотивация: {motivation}")
        
        await message.answer("🎉 Все AI функции работают отлично!")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка теста: {str(e)}")