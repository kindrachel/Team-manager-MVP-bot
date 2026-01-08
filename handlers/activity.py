from aiogram import Router, F, types, Dispatcher
from aiogram.fsm.context import FSMContext
from services import MetricsCollector
from database import User, Challenge, ChallengeStatus, SurveyType, get_session
from keyboards import (
    sleep_quality_keyboard, energy_keyboard, readiness_keyboard, 
    mood_keyboard, back_to_activity_keyboard, yes_no_keyboard
)

from utils import get_level_name
from utils.time import get_current_survey_period_for_user, get_period_display_name, get_period_time_range, get_org_timezone, SUPPORTED_TIMEZONES
from utils.states import SurveyStates, ChallengeWaitStates
from datetime import datetime, timezone as tz, timedelta
from aiogram.types import FSInputFile
from database import Survey
import logging

activity_pic= FSInputFile('pictures/Activity.png')
challenge_pic = FSInputFile("pictures/challenges.png")

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.text == "📈 Активность")
async def show_activity_menu(message: types.Message) -> None:
    """Меню активности и опросов с учетом часового пояса организации"""
    try:
        user_id = message.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы")
            session.close()
            return
        
        current_period = get_current_survey_period_for_user(user_id)
        
        # Формируем информацию об опросах
        survey_info = ""
        
        if current_period == "none":
            survey_info = "🌙 Ночью опросы недоступны\nДоступны с 6:00 до 22:00"
        else:
            period_name = get_period_display_name(current_period)
            time_range = get_period_time_range(current_period)
            
            from sqlalchemy import func
            today = datetime.now(tz.utc).date()
            
            # Проверяем, проходил ли уже этот опрос сегодня
            already_taken = session.query(Survey).filter(
                Survey.user_id == user.id,
                Survey.survey_type == current_period,
                func.date(Survey.date) == today
            ).first()
            
            # Получаем все опросы за сегодня для счетчика
            today_surveys = session.query(Survey).filter(
                Survey.user_id == user.id,
                func.date(Survey.date) == today
            ).all()
            
            completed_count = len(today_surveys)
            
            if already_taken:
                survey_info = f"✅ {period_name} уже пройден"
            else:
                survey_info = f"🎯 {period_name} доступен!"
            
            if completed_count > 0:
                survey_info += f"\n\n📊 Сегодня пройдено: {completed_count}/3 опросов"
        
        # 🔴 ДОПОЛНИТЕЛЬНО: Показываем текущее время организации
        from utils.time import get_current_org_time
        if user.org_id:
            org_time = get_current_org_time(user.org_id)
            time_str = org_time.strftime("%H:%M")
            timezone_str = get_org_timezone(user.org_id)
            timezone_display = [name for name, tz in SUPPORTED_TIMEZONES if tz == timezone_str]
            timezone_display = timezone_display[0] if timezone_display else timezone_str
            survey_info += f"\n\n🕐 Часовой пояс: {timezone_display}\n⏰ Местное время: {time_str}"
        
        activity_text = (
            f"📈 ВАША АКТИВНОСТЬ\n\n"
            f"👤 {user.name}\n"
            f"💎 Очки: {user.points}\n"
            f"🥇 Уровень: {get_level_name(user.level)}\n\n"
            f"{survey_info}\n\n"
            f"Выбери действие:"
        )
        
        # Определяем доступность опроса
        can_survey = False
        if current_period != "none":
            from sqlalchemy import func
            today = datetime.now(tz.utc).date()
            already_taken = session.query(Survey).filter(
                Survey.user_id == user.id,
                Survey.survey_type == current_period,
                func.date(Survey.date) == today
            ).first()
            can_survey = not already_taken
        
        inline_keyboard = []
        
        if can_survey:
            inline_keyboard.append([types.InlineKeyboardButton(
                text=f"📝 {get_period_display_name(current_period)}", 
                callback_data="survey_start"
            )])
        else:
            if current_period == "none":
                inline_keyboard.append([types.InlineKeyboardButton(
                    text="🌙 Ночью опросы недоступны", 
                    callback_data="survey_unavailable"
                )])
            else:
                inline_keyboard.append([types.InlineKeyboardButton(
                    text=f"✅ {get_period_display_name(current_period)} пройден", 
                    callback_data="survey_unavailable"
                )])
        
        inline_keyboard.extend([
            [types.InlineKeyboardButton(text="📊 История опросов", callback_data="survey_history")],
            [types.InlineKeyboardButton(text="📋 Опросы метрик", callback_data="user_survey")],
            [types.InlineKeyboardButton(text="⚡ Активные челленджи", callback_data="challenges_view")],
            [types.InlineKeyboardButton(text="👥 Лидерборд команды", callback_data="leaderboard_view")],
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ])
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        
        await message.answer_photo(photo=activity_pic, caption=activity_text, reply_markup=kb)
        session.close()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "survey_start")
async def start_survey(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Начать опрос - проверяем период и доступность"""
    try:
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.message.delete()
            await callback.message.answer("❌ Вы не зарегистрированы")
            session.close()
            return
        
        # 🔴 ИЗМЕНЕНИЕ: Используем новую функцию
        from utils.time import get_current_survey_period_for_user, get_period_display_name
        
        current_period = get_current_survey_period_for_user(user_id)
        
        print(f"\n🔍 DEBUG start_survey:")
        print(f"   User: {user.name} (DB ID: {user.id}, Telegram ID: {user.user_id})")
        print(f"   Current period: {current_period}")
        print(f"   Org ID: {user.org_id}")
        
        if current_period == "none":
            await callback.message.delete()
            # 🔴 Показываем время организации
            from utils.time import get_current_org_time, SUPPORTED_TIMEZONES, get_org_timezone
            if user.org_id:
                org_time = get_current_org_time(user.org_id)
                time_str = org_time.strftime("%H:%M")
                timezone_str = get_org_timezone(user.org_id)
                timezone_display = [name for name, tz in SUPPORTED_TIMEZONES if tz == timezone_str]
                timezone_display = timezone_display[0] if timezone_display else timezone_str
                time_message = f"\n🕐 Сейчас {time_str} (часовой пояс: {timezone_display})"
            else:
                time_message = ""
            
            await callback.message.answer(
                f"🌙 Сейчас не время для опросов{time_message}\n\n"
                "Опросы доступны:\n"
                "🌅 Утро: 6:00 - 12:00\n"
                "☀️ День: 12:00 - 18:00\n"
                "🌙 Вечер: 18:00 - 22:00",
                reply_markup=back_to_activity_keyboard()
            )
            session.close()
            return
        
        # Остальной код остается без изменений...
        from sqlalchemy import func
        today = datetime.now(tz.utc).date()
        
        already_taken = session.query(Survey).filter(
            Survey.user_id == user.id,
            Survey.survey_type == current_period,
            func.date(Survey.date) == today
        ).first()
        
        if already_taken:
            await callback.message.delete()
            await callback.message.answer(
                f"⏳ Вы уже проходили {get_period_display_name(current_period)} сегодня\n\n"
                f"Следующий опрос будет доступен в следующий период.",
                reply_markup=back_to_activity_keyboard()
            )
            session.close()
            return
        
        session.close()
        
        await state.update_data(survey_type=current_period)
        
        print(f"   ✅ Начинаем {current_period} опрос...")
        await callback.message.delete()
        await callback.message.answer(
            f"{get_period_display_name(current_period)}\n\n"
            "😴 Как качество вашего сна? (оцени от 1 до 10)",
            reply_markup=sleep_quality_keyboard()
        )
        await state.set_state(SurveyStates.waiting_for_sleep)
        
    except Exception as e:
        print(f"❌ Ошибка в start_survey: {e}")
        import traceback
        traceback.print_exc()
        await callback.message.answer(f"❌ Ошибка: {e}")

@router.callback_query(SurveyStates.waiting_for_sleep, F.data.startswith("sleep_"))
async def process_sleep(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка качества сна"""
    try:
        sleep_value = int(callback.data.replace("sleep_", ""))
        await state.update_data(sleep=sleep_value)
        
        await callback.message.edit_text(
            "⚡ Какой у тебя уровень энергии? (1-10)",
            reply_markup=energy_keyboard()
        )
        await state.set_state(SurveyStates.waiting_for_energy)
        
    except ValueError:
        await callback.answer("❌ Пожалуйста, выберите число от 1 до 10", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(SurveyStates.waiting_for_energy, F.data.startswith("energy_"))
async def process_energy(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка энергии"""
    energy_value = int(callback.data.replace("energy_", ""))
    await state.update_data(energy=energy_value)
    
    await callback.message.edit_text(
        "🎯 Насколько вы готовы к тренировке? (1-10)",
        reply_markup=readiness_keyboard()
    )
    await state.set_state(SurveyStates.waiting_for_readiness)

@router.callback_query(SurveyStates.waiting_for_readiness, F.data.startswith("readiness_"))
async def process_readiness(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка готовности"""
    readiness_value = int(callback.data.replace("readiness_", ""))
    await state.update_data(readiness=readiness_value)
    
    await callback.message.edit_text(
        "😊 Какое ваше настроение?",
        reply_markup=mood_keyboard()
    )
    await state.set_state(SurveyStates.waiting_for_mood)

@router.callback_query(SurveyStates.waiting_for_mood, F.data.startswith("mood_"))
async def process_mood(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка настроения - сохраняем с типом опроса"""
    import traceback
    
    try:
        mood_value = callback.data.replace("mood_", "")
        mood_map = {
            "happy": "Счастлив",
            "neutral": "Обычно",
            "sad": "Грустно"
        }
        mood_text = mood_map.get(mood_value, mood_value)
        await state.update_data(mood=mood_text)
        
        data = await state.get_data()
        user_id = callback.from_user.id
        
        print(f"\n🔍 DEBUG process_mood:")
        print(f"   User ID (Telegram): {user_id}")
        print(f"   Data from state: {data}")
        
        session = get_session()
        
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            
            if not user:
                print(f"❌ User not found in DB for telegram_id={user_id}")
                await callback.message.edit_text("❌ Пользователь не найден")
                return
            
            print(f"✅ User found: {user.name}, DB ID: {user.id}")
            
            survey_type = data.get("survey_type", "morning")
            
            print(f"📝 Saving survey type: {survey_type}")
            print(f"   Energy: {data.get('energy')}")
            print(f"   Sleep: {data.get('sleep')}")
            print(f"   Readiness: {data.get('readiness')}")
            print(f"   Mood: {mood_text}")
            
            # Отладочный вызов
            print(f"🔍 Calling MetricsCollector.record_survey...")
            success = MetricsCollector.record_survey(
            user_db_id=user.id,
                survey_type=survey_type,
                energy=data.get("energy"),
                sleep=data.get("sleep"),
                readiness=data.get("readiness"),
                mood=mood_text
            )
            
            print(f"✅ MetricsCollector.record_survey returned: {success}")
            
            if success:
                # Обновляем пользователя напрямую (на всякий случай)
                user.last_survey_at = datetime.now()
                user.last_survey_type = survey_type
                user.energy = data.get("energy")
                user.sleep_quality = data.get("sleep")  # Используем sleep_quality!
                user.readiness = data.get("readiness")
                user.mood = mood_text
                
                session.commit()
                print(f"✅ User updated in DB")
                
                # Добавляем очки
                try:
                    MetricsCollector.add_points(user.user_id, 1, "survey_completed")
                    print(f"✅ Points added")
                except Exception as e:
                    print(f"⚠️ Error adding points: {e}")
                
                from utils.time import get_period_display_name, get_current_survey_period
                
                response_text = (
                    f"✅ {get_period_display_name(survey_type)} завершен!\n\n"
                    f"📊 Ваши показатели:\n"
                    f"⚡ Энергия: {data.get('energy')}/10\n"
                    f"😴 Сон: {data.get('sleep')}/10\n"
                    f"🎯 Готовность: {data.get('readiness')}/10\n"
                    f"😊 Настроение: {mood_text}\n\n"
                    f"💎 +1 очков за активность!\n\n"
                    f"Спасибо за вашу активность! 💪"
                )
            else:
                response_text = "❌ Ошибка при сохранении опроса"
            
            await callback.message.delete()
            await callback.message.answer(response_text, reply_markup=back_to_activity_keyboard())
            
        except Exception as e:
            print(f"❌ Error in process_mood DB operations: {e}")
            traceback.print_exc()
            await callback.message.answer(f"❌ Ошибка при сохранении: {e}", reply_markup=back_to_activity_keyboard())
        finally:
            session.close()
            await state.clear()
            
    except Exception as e:
        print(f"❌ General error in process_mood: {e}")
        traceback.print_exc()
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_activity_keyboard())


@router.callback_query(F.data == "survey_unavailable")
async def survey_unavailable(callback: types.CallbackQuery) -> None:
    """Обработка нажатия на недоступный опрос"""
    try:
        from utils.time import get_current_survey_period_for_user, get_period_display_name, get_period_time_range
        
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            session.close()
            return
        
        current_period = get_current_survey_period_for_user(user_id)
        
        if current_period == "none":
            await callback.answer(
                "🌙 Ночью опросы недоступны\nДоступны с 6:00 до 22:00",
                show_alert=True
            )
            session.close()
            return
        
        from sqlalchemy import func
        today = datetime.now(tz.utc).date()
        
        already_taken = session.query(Survey).filter(
            Survey.user_id == user.id,
            Survey.survey_type == current_period,
            func.date(Survey.date) == today
        ).first()
        
        if already_taken:
            # Определяем следующий период
            next_periods = {
                "morning": "12:00 (дневной)",
                "afternoon": "18:00 (вечерний)", 
                "evening": "завтра в 6:00 (утренний)"
            }
            next_time = next_periods.get(current_period, "в следующем периоде")
            
            await callback.answer(
                f"✅ Вы уже прошли {get_period_display_name(current_period)} сегодня\n",
                show_alert=True
            )
        else:
            # Опрос доступен
            await callback.answer(
                f"🎯 {get_period_display_name(current_period)} доступен!\n",
                show_alert=True
            )
        
        session.close()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == "challenges_view")
async def show_challenges(callback: types.CallbackQuery) -> None:
    """Показать активные челленджи (только PENDING, не OFFERED)"""
    try:
        user_telegram_id = callback.from_user.id
        session = get_session()
        
        user = session.query(User).filter(User.user_id == user_telegram_id).first()
        
        if not user:
            await callback.message.delete()
            await callback.message.answer("❌ Пользователь не найден")
            session.close()
            return
        
        # Показываем только челленджи со статусом PENDING (НЕ OFFERED)
        challenges = session.query(Challenge).filter(
            Challenge.user_id == user.user_id, 
            Challenge.status == ChallengeStatus.PENDING.value  # Только принятые
        ).all()
        
        session.close()
        
        if not challenges:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=challenge_pic,
                caption="😋 У тебя нет активных челленджей.\n\n"
                       "🎯 Новые челленджи будут приходить от тренера.\n"
                       "📝 Или создайте свой челлендж!",
                reply_markup=back_to_activity_keyboard()
            )
            return
        
        MAX_CAPTION_LENGTH = 1024
        challenges_text = f"⚡ АКТИВНЫЕ ЧЕЛЛЕНДЖИ ({len(challenges)})\n\n"
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[])
        
        for idx, challenge in enumerate(challenges, 1):
            challenge_line = f"{idx}. {challenge.text}\n   💎 {challenge.points} очков\n\n"
            
            if len(challenges_text) + len(challenge_line) > MAX_CAPTION_LENGTH - 100:
                challenges_text += f"\n... и еще {len(challenges) - idx + 1} челленджей"
                break
            
            challenges_text += challenge_line

            kb.inline_keyboard.append([
                types.InlineKeyboardButton(
                    text=f"✅ #{idx} Выполнил", 
                    callback_data=f"challenge_complete_{challenge.id}"
                ),
                types.InlineKeyboardButton(
                    text=f"⛔ #{idx} Отказываюсь", 
                    callback_data=f"challenge_reject_{challenge.id}"
                )
            ])
        
        kb.inline_keyboard.append([
            types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_activity")
        ])
        
        if len(challenges_text) > MAX_CAPTION_LENGTH:
            challenges_text = challenges_text[:MAX_CAPTION_LENGTH - 3] + "..."
        
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=challenge_pic, 
            caption=challenges_text, 
            reply_markup=kb
        )
        
    except Exception as e:
        print(f"🔴 Ошибка в show_challenges: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_activity_keyboard())

@router.callback_query(F.data.startswith("challenge_complete_"))
async def complete_challenge(callback: types.CallbackQuery) -> None:
    """Отметить челлендж как выполненный"""
    try:
        challenge_id = int(callback.data.replace("challenge_complete_", ""))
        user_telegram_id = callback.from_user.id
        
        session = get_session()
        
        user = session.query(User).filter(User.user_id == user_telegram_id).first()
        
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            session.close()
            return
        
        challenge = session.query(Challenge).filter(
            Challenge.id == challenge_id,
            Challenge.user_id == user.user_id  
        ).first()
        
        if challenge:
            challenge.status = ChallengeStatus.COMPLETED.value
            challenge.completed_at = datetime.now(tz.utc)
            
            user.points += challenge.points
            
            new_level = min((user.points // 100) + 1, 5)
            if new_level > user.level:
                user.level = new_level
                level_up_msg = f"\n🎊 Поздравляем! Вы достигли уровня {get_level_name(new_level)}! 🏆"
            else:
                level_up_msg = ""
            
            session.commit()
            
            completion_text = (
                f"🎉 Отлично выполнено!\n\n"
                f"'{challenge.text}'\n\n"
                f"💎 Получено: +{challenge.points} очков!"
                f"{level_up_msg}"
            )
        else:
            completion_text = "❌ Челлендж не найден или не принадлежит вам"
        
        session.close()
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=challenge_pic,
            caption=completion_text,
            reply_markup=back_to_activity_keyboard()
        )
        
    except Exception as e:
        print(f"🔴 Ошибка в complete_challenge: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_activity_keyboard())

@router.callback_query(F.data.startswith("challenge_reject_"))
async def reject_challenge(callback: types.CallbackQuery) -> None:
    """Отказаться от челленджа"""
    try:
        challenge_id = int(callback.data.replace("challenge_reject_", ""))
        
        session = get_session()
        challenge = session.query(Challenge).filter(Challenge.id == challenge_id).first()
        
        if challenge:
            challenge.status = ChallengeStatus.FAILED.value
            session.commit()
            
            reject_text = (
                f"⛔Вы отказались от челленджа:\n\n"
                f"'{challenge.text}'\n\n"
                f"🤝 Не переживай! Следующий получится! 💪"
            )
        else:
            reject_text = "❌ Челлендж не найден"
        
        session.close()
        await callback.message.delete()
        await callback.message.answer(reject_text, reply_markup=back_to_activity_keyboard())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_activity_keyboard())

@router.callback_query(F.data == "leaderboard_view")
async def show_leaderboard(callback: types.CallbackQuery) -> None:
    """Показать лидерборд команды"""
    try:
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            session.close()
            return
        
        leaderboard = MetricsCollector.get_leaderboard(user.org_id, limit=10)
        session.close()
        
        leaderboard_text = "🏆 ЛИДЕРБОРД КОМАНДЫ\n\n"
        
        for place in leaderboard:
            medal = "🥇" if place["position"] == 1 else "🥈" if place["position"] == 2 else "🥉" if place["position"] == 3 else f"#{place['position']}"
            leaderboard_text += (
                f"{medal} {place['position']}. {place['name']}\n"
                f"   💎 {place['points']} очков | {get_level_name(place['level'])}\n"
                f"   ⚽ {place['position_role']}\n\n"
            )
        await callback.message.delete()
        await callback.message.answer(leaderboard_text, reply_markup=back_to_activity_keyboard())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_activity_keyboard())

@router.callback_query(F.data == 'back_to_activity')
async def back_to_activity(call: types.CallbackQuery) -> None:
    """Обработчик кнопки назад для активности"""
    try:
        user_id = call.from_user.id  # 🔴 Исправлено: call.from_user.id вместо call.message.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # 🔴 ВАЖНО: Проверяем, что пользователь найден
        if not user:
            await call.message.answer("❌ Пользователь не найден. Пройдите регистрацию.")
            session.close()
            return
        
        current_period = get_current_survey_period_for_user(user_id)
        
        # Формируем информацию об опросах
        survey_info = ""
        
        if current_period == "none":
            survey_info = "🌙 Ночью опросы недоступны\nДоступны с 6:00 до 22:00"
        else:
            period_name = get_period_display_name(current_period)
            time_range = get_period_time_range(current_period)
            
            from sqlalchemy import func
            today = datetime.now(tz.utc).date()
            
            # 🔴 Теперь user точно не None, можем безопасно использовать user.id
            already_taken = session.query(Survey).filter(
                Survey.user_id == user.id,
                Survey.survey_type == current_period,
                func.date(Survey.date) == today
            ).first()
            
            # Получаем все опросы за сегодня для счетчика
            today_surveys = session.query(Survey).filter(
                Survey.user_id == user.id,
                func.date(Survey.date) == today
            ).all()
            
            completed_count = len(today_surveys)
            
            if already_taken:
                survey_info = f"✅ {period_name} уже пройден"
            else:
                survey_info = f"🎯 {period_name} доступен!"
            
            if completed_count > 0:
                survey_info += f"\n\n📊 Сегодня пройдено: {completed_count}/3 опросов"
        
        # 🔴 ДОПОЛНИТЕЛЬНО: Показываем текущее время организации
        from utils.time import get_current_org_time
        if user.org_id:
            org_time = get_current_org_time(user.org_id)
            time_str = org_time.strftime("%H:%M")
            timezone_str = get_org_timezone(user.org_id)
            timezone_display = [name for name, tz in SUPPORTED_TIMEZONES if tz == timezone_str]
            timezone_display = timezone_display[0] if timezone_display else timezone_str
            survey_info += f"\n\n🕐 Часовой пояс: {timezone_display}\n⏰ Местное время: {time_str}"
        
        activity_text = (
            f"📈 *ВАША АКТИВНОСТЬ*\n\n"
            f"👤 {user.name}\n"
            f"💎 Баллы: {user.points}\n"
            f"📌 Опыт: {get_level_name(user.level)}\n\n"
            f"{survey_info}\n\n"
            f"Выбери действие:"
        )
        
        # Определяем доступность опроса
        can_survey = False
        if current_period != "none":
            from sqlalchemy import func
            today = datetime.now(tz.utc).date()
            already_taken = session.query(Survey).filter(
                Survey.user_id == user.id,
                Survey.survey_type == current_period,
                func.date(Survey.date) == today
            ).first()
            can_survey = not already_taken
        
        inline_keyboard = []
        
        if can_survey:
            inline_keyboard.append([types.InlineKeyboardButton(
                text=f"📝 {get_period_display_name(current_period)}", 
                callback_data="survey_start"
            )])
        else:
            if current_period == "none":
                inline_keyboard.append([types.InlineKeyboardButton(
                    text="🌙 Ночью опросы недоступны", 
                    callback_data="survey_unavailable"
                )])
            else:
                inline_keyboard.append([types.InlineKeyboardButton(
                    text=f"✅ {get_period_display_name(current_period)} пройден", 
                    callback_data="survey_unavailable"
                )])
        
        inline_keyboard.extend([
            [types.InlineKeyboardButton(text="📊 История опросов", callback_data="survey_history")],
            [types.InlineKeyboardButton(text="⚡ Активные челленджи", callback_data="challenges_view")],
            [types.InlineKeyboardButton(text="👥 Лидерборд команды", callback_data="leaderboard_view")],
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ])
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        
        await call.message.answer_photo(photo=activity_pic, parse_mode = 'Markdown', caption=activity_text, reply_markup=kb)
        session.close()
        
    except Exception as e:
        await call.message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "survey_history")
async def show_survey_history(callback: types.CallbackQuery) -> None:
    """Показать историю опросов"""
    try:
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            session.close()
            return
        
        from utils.time import get_period_display_name
        
        surveys = MetricsCollector.get_today_surveys(user.id)
        
        if not surveys:
            await callback.message.delete()
            await callback.message.answer(
                "📊 Вы еще не проходили опросы сегодня\n\n"
                "Доступные периоды:\n"
                "🌅 Утро: 6:00 - 12:00\n"
                "☀️ День: 12:00 - 18:00\n"
                "🌙 Вечер: 18:00 - 22:00",
                reply_markup=back_to_activity_keyboard()
            )
            session.close()
            return
        
        history_text = "📊 ИСТОРИЯ ОПРОСОВ СЕГОДНЯ\n\n"
        
        for survey in surveys:
            period_name = get_period_display_name(survey['type'])
            time_str = survey['time'].strftime('%H:%M')
            
            history_text += (
                f"{period_name} ({time_str})\n"
                f"⚡ Энергия: {survey['energy']}/10\n"
                f"😴 Сон: {survey['sleep']}/10\n"
                f"🎯 Готовность: {survey['readiness']}/10\n"
                f"😊 Настроение: {survey['mood']}\n"
                f"──────────────\n"
            )
        
        history_text += f"\n✅ Пройдено: {len(surveys)}/3 опросов"
        
        await callback.message.delete()
        await callback.message.answer(history_text, reply_markup=back_to_activity_keyboard())
        session.close()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("challenge_accept_"))
async def accept_challenge(callback: types.CallbackQuery):
    """Принять предложенный челлендж"""
    try:
        challenge_id = int(callback.data.replace("challenge_accept_", ""))
        user_id = callback.from_user.id
        
        session = get_session()
        
        # Находим предложенный челлендж
        challenge = session.query(Challenge).filter(
            Challenge.id == challenge_id,
            Challenge.status == "OFFERED"
        ).first()
        
        if not challenge:
            await callback.answer("❌ Челлендж не найден или уже обработан", show_alert=True)
            session.close()
            return
        
        # Проверяем, что челлендж предназначен этому пользователю
        if challenge.user_id != user_id:
            await callback.answer("❌ Этот челлендж не для вас", show_alert=True)
            session.close()
            return
        
        # Меняем статус на PENDING (активный)
        challenge.status = ChallengeStatus.PENDING.value
        
        session.commit()
        
        # Показываем полный текст челленджа
        challenge_text = f"🎯 *ВЫ ПРИНЯЛИ ЧЕЛЛЕНДЖ!*\n\n{challenge.text}\n\n💎 Награда: {challenge.points} баллов\n\n✅ Выполните его в разделе 'Активность' → 'Активные челленджи'"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Перейти к активным челленджам", callback_data="challenges_view")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ])
        
        await callback.message.edit_text(challenge_text, parse_mode="Markdown")
        await callback.message.answer("Челлендж добавлен в ваши активные задания!", reply_markup=kb)
        
        session.close()
        
    except Exception as e:
        logger.error(f"Ошибка в accept_challenge: {e}")
        await callback.answer("❌ Ошибка при принятии челленджа", show_alert=True)

@router.callback_query(F.data.startswith("challenge_decline_"))
async def decline_challenge(callback: types.CallbackQuery):
    """Отклонить предложенный челлендж"""
    try:
        challenge_id = int(callback.data.replace("challenge_decline_", ""))
        user_id = callback.from_user.id
        
        session = get_session()
        
        # Находим предложенный челлендж
        challenge = session.query(Challenge).filter(
            Challenge.id == challenge_id,
            Challenge.status == "OFFERED"
        ).first()
        
        if not challenge:
            await callback.answer("❌ Челлендж не найден или уже обработан", show_alert=True)
            session.close()
            return
        
        # Проверяем, что челлендж предназначен этому пользователю
        if challenge.user_id != user_id:
            await callback.answer("❌ Этот челлендж не для вас", show_alert=True)
            session.close()
            return
        
        # Удаляем челлендж (или меняем статус на DECLINED)
        session.delete(challenge)
        session.commit()
        
        await callback.message.edit_text("❌ Вы отклонили челлендж.\n\nНовые челленджи будут приходить позже!")
        
        session.close()
        
    except Exception as e:
        logger.error(f"Ошибка в decline_challenge: {e}")
        await callback.answer("❌ Ошибка при отклонении челленджа", show_alert=True)

@router.callback_query(F.data.startswith("challenge_custom_"))
async def create_custom_challenge(callback: types.CallbackQuery, state: FSMContext):
    """Создать свой челлендж"""
    try:
        original_challenge_id = int(callback.data.replace("challenge_custom_", ""))
        user_id = callback.from_user.id
        
        session = get_session()
        
        # Удаляем оригинальный предложенный челлендж если он есть
        if original_challenge_id > 0:
            original_challenge = session.query(Challenge).filter(
                Challenge.id == original_challenge_id,
                Challenge.status == "OFFERED",
                Challenge.user_id == user_id
            ).first()
            
            if original_challenge:
                session.delete(original_challenge)
        
        await state.update_data(
            creating_custom_challenge=True,
            user_id=user_id
        )
        
        await callback.message.edit_text(
            "📝 *НАПИШИТЕ СВОЙ ЧЕЛЛЕНДЖ*\n\n"
            "Опишите задание, которое хотите выполнить.\n"
            "Пример: 'Сделать 50 отжиманий за день' или 'Пробежать 3 км'\n\n"
            "💡 Совет: Челлендж должен быть конкретным и измеримым.",
            parse_mode="Markdown"
        )
        
        await state.set_state(ChallengeWaitStates.waiting_for_custom_challenge)
        
        session.commit()
        session.close()
        
    except Exception as e:
        logger.error(f"Ошибка в create_custom_challenge: {e}")
        await callback.answer("❌ Ошибка при создании своего челленджа", show_alert=True)

@router.message(ChallengeWaitStates.waiting_for_custom_challenge)
async def process_custom_challenge_text(message: types.Message, state: FSMContext):
    """Обработать текст кастомного челленджа и сразу создать его"""
    try:
        challenge_text = message.text.strip()
        user_id = message.from_user.id
        
        if len(challenge_text) < 5:
            await message.answer("❌ Текст челленджа слишком короткий. Напишите подробнее:")
            return
        
        if len(challenge_text) > 500:
            await message.answer("❌ Текст челленджа слишком длинный. Сократите до 500 символов:")
            return
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return
        
        # Создаем кастомный челлендж с 0 баллов
        from database import Challenge, ChallengeStatus
        from datetime import datetime, timezone as tz
        
        custom_challenge = Challenge(
            user_id=user.user_id,
            text=challenge_text,
            points=0,  # 0 баллов за свой челлендж
            status=ChallengeStatus.PENDING.value,
            created_by=user.user_id,
            created_at=datetime.now(tz.utc),
            is_custom=True,
            difficulty="custom",
            duration="на ваш выбор"
        )
        
        session.add(custom_challenge)
        session.commit()
        
        success_text = (
            f"✅ *ВАШ ЧЕЛЛЕНДЖ СОЗДАН!*\n\n"
            f"📝 Задание: {challenge_text}\n"
            f"💎 Награда: 0 баллов (свой челлендж)\n\n"
            f"Теперь вы можете найти его в разделе 'Активность' → 'Активные челленджи'\n\n"
            f"💡 *Примечание:* Свой челлендж создается для личной мотивации, поэтому баллы не начисляются."
        )
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Перейти к активным челленджам", callback_data="challenges_view")],
            [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")]
        ])
        
        await message.answer(success_text, parse_mode="Markdown", reply_markup=kb)
        
        await state.clear()
        session.close()
        
    except Exception as e:
        logger.error(f"Ошибка в process_custom_challenge_text: {e}")
        await message.answer("❌ Ошибка при создании челленджа. Попробуйте снова:")
        await state.clear()

def register_activity_handlers(dp: Dispatcher):
    dp.include_router(router)