import logging
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.metrics_analyzer import ProffKonstaltingMetrics
from database import UserRole
from database import get_session, User, Survey, MetricsSurvey
from datetime import datetime
import json

logger = logging.getLogger(__name__)
router = Router()

class SurveyStates(StatesGroup):
    """Состояния для прохождения опроса"""
    choosing_metric = State()
    answering_questions = State()
    viewing_results = State()

metrics_analyzer = ProffKonstaltingMetrics()

# Клавиатуры для ответов
def get_rating_keyboard(metric_key: str, question_index: int, max_rating: int) -> InlineKeyboardMarkup:
    """Клавиатура для оценки по шкале"""
    builder = InlineKeyboardBuilder()

    # Создаем кнопки с оценками
    buttons = []
    for i in range(1, max_rating + 1):
        buttons.append(
            InlineKeyboardButton(
                text=str(i),
                callback_data=f"survey_rate_{metric_key}_{question_index}_{i}"
            )
        )

    # Разбиваем на ряды по 5 кнопок
    for i in range(0, len(buttons), 5):
        builder.row(*buttons[i:i+5])

    return builder.as_markup()

def get_metrics_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора метрики для опроса"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📊 Пройти полный опрос",
            callback_data="survey_start_full"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="📈 Посмотреть мои результаты",
            callback_data="survey_view_results"
        )
    )

    return builder.as_markup()

@router.callback_query(F.data == 'user_survey')
async def start_survey_menu(call: types.CallbackQuery):
    """Начало меню опросов"""
    await call.answer()

    text = (
        "📊 *Опросы ProffKonstalting*\n\n"
        "Оцените себя по ключевым метрикам профессионального развития.\n\n"
        "Выберите опцию:\n\n"
        "Результаты помогут вам лучше понять свои сильные и слабые стороны.\n"
        "**Опрос может занять больше 10 минут.**"
    )

    try:
        await call.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    try:
        await call.message.answer(
            text,
            reply_markup=get_metrics_selection_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")
        await call.bot.send_message(
            chat_id=call.from_user.id,
            text=text,
            reply_markup=get_metrics_selection_keyboard(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith('survey_start_'))
async def start_survey(call: types.CallbackQuery, state: FSMContext):
    """Начало опроса по выбранной метрике"""
    await call.answer()

    data = call.data.replace('survey_start_', '')

    if data == 'full':
        # Проверяем квоту AI перед началом полного опроса
        if hasattr(metrics_analyzer.ai_service, 'hf_service') and metrics_analyzer.ai_service.hf_service:
            if metrics_analyzer.ai_service.hf_service.quota_exceeded:
                await call.message.edit_text(
                    "❌ Квота AI запросов исчерпана. Полный AI-опрос требует большого количества запросов.\n\n"
                    "Попробуйте:\n"
                    "• Пройти опрос по одной метрике\n"
                    "• Повторить попытку позже\n"
                    "• Обратиться к администратору",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📊 Одиночная метрика", callback_data="user_survey")],
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
                    ])
                )
                return

        # Полный AI-опрос по всем метрикам
        try:
            await call.message.edit_text("🤖 Начинаем полный AI-опрос по всем метрикам...")
        except Exception as e:
            logger.warning(f"Не удалось редактировать сообщение: {e}")
            await call.bot.send_message(
                chat_id=call.from_user.id,
                text="🤖 Начинаем полный AI-опрос по всем метрикам..."
            )

        # Получаем контекст пользователя для генерации вопросов
        user_context = await get_user_context(call.from_user.id)

        # Генерируем AI-вопросы на основе начальных ответов пользователя
        ai_questions = await metrics_analyzer.generate_ai_questions_based_on_answers(user_context)

        # Преобразуем в плоский список вопросов с метриками
        all_questions = []
        for metric_key, questions in ai_questions.items():
            for question in questions:
                all_questions.append({
                    'metric': metric_key,
                    'question': question
                })

        await state.update_data(
            survey_type='full',
            all_questions=all_questions,
            current_question_index=0,
            user_context=user_context
        )
        await ask_next_ai_question(call.from_user.id, call.bot, state)
    else:
        # Опрос по конкретной метрике
        try:
            await call.message.edit_text("📊 Начинаем опрос...")
        except Exception as e:
            logger.warning(f"Не удалось редактировать сообщение: {e}")
            await call.bot.send_message(
                chat_id=call.from_user.id,
                text="📊 Начинаем опрос..."
            )

        await state.update_data(
            survey_type='single',
            current_metric=data,
            question_index=0,
            responses={data: []}
        )
        await ask_question(call, state, data, 0)

@router.callback_query(F.data.startswith('survey_rate_'))
async def process_rating(call: types.CallbackQuery, state: FSMContext):
    """Обработка ответа на вопрос"""
    await call.answer()

    try:
        _, _, metric_key, question_index_str, rating_str = call.data.split('_')
        question_index = int(question_index_str)
        rating = int(rating_str)

        # Получаем текущие данные
        data = await state.get_data()
        responses = data.get('responses', {})
        current_metric = data.get('current_metric')

        # Добавляем ответ
        if current_metric not in responses:
            responses[current_metric] = []
        responses[current_metric].append(rating)

        await state.update_data(responses=responses)

        # Проверяем, есть ли еще вопросы по этой метрике
        questions = metrics_analyzer.get_survey_questions(current_metric)
        if question_index + 1 < len(questions):
            # Следующий вопрос
            await ask_question(call, state, current_metric, question_index + 1)
        else:
            # Метрика завершена
            if 'current_metric_index' in data:
                # Это полный опрос, переходим к следующей метрике
                current_index = data['current_metric_index']
                all_metrics = list(metrics_analyzer.get_all_metrics().keys())

                if current_index + 1 < len(all_metrics):
                    # Следующая метрика
                    await state.update_data(current_metric_index=current_index + 1)
                    await start_next_metric(call, state)
                else:
                    # Все метрики пройдены
                    await finish_full_survey(call, state)
            else:
                # Одиночная метрика завершена
                await finish_single_metric_survey(call, state, current_metric)

    except Exception as e:
        logger.error(f"Ошибка обработки рейтинга: {e}")
        try:
            await call.message.edit_text("❌ Произошла ошибка. Попробуйте начать опрос заново.")
        except Exception as e:
            logger.warning(f"Не удалось редактировать сообщение: {e}")
            await call.bot.send_message(
                chat_id=call.from_user.id,
                text="❌ Произошла ошибка. Попробуйте начать опрос заново."
            )

@router.message(SurveyStates.answering_questions)
async def process_text_answer(message: types.Message, state: FSMContext):
    """Обработка текстового ответа на AI-вопрос"""
    try:
        data = await state.get_data()
        survey_type = data.get('survey_type')
        user_context = data.get('user_context', {})

        # Добавляем ответ в контекст пользователя
        user_context['answers'] = user_context.get('answers', [])
        user_context['answers'].append({
            'question': data.get('current_question', ''),
            'answer': message.text,
            'timestamp': datetime.now().isoformat()
        })

        await state.update_data(user_context=user_context)

        if survey_type == 'full':
            # Полный опрос - переходим к следующему вопросу
            await process_next_ai_question(message, state)
        else:
            # Одиночный опрос - завершаем
            await finish_ai_single_metric_survey(message, state)

    except Exception as e:
        logger.error(f"Ошибка обработки текстового ответа: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте ответить еще раз.")

async def process_next_ai_question(message: types.Message, state: FSMContext):
    """Обработка следующего AI-вопроса в полном опросе"""
    data = await state.get_data()
    all_questions = data.get('all_questions', [])
    current_question_index = data.get('current_question_index', 0)

    if current_question_index + 1 < len(all_questions):
        # Есть еще вопросы
        await state.update_data(current_question_index=current_question_index + 1)
        await ask_next_ai_question(message.chat.id, message.bot, state)
    else:
        # Все вопросы заданы, завершаем опрос
        await finish_ai_full_survey(message, state)

async def ask_next_ai_question(chat_id: int, bot, state: FSMContext):
    """Задаем следующий AI-вопрос"""
    data = await state.get_data()
    all_questions = data.get('all_questions', [])
    current_index = data.get('current_question_index', 0)

    if current_index < len(all_questions):
        question_data = all_questions[current_index]

        text = (
            f"🤖 *AI-ВОПРОС*\n\n"
            f"*{current_index + 1}/{len(all_questions)}*\n\n"
            f"{question_data['question']}\n\n"
            f"💡 _Ответьте подробно для точного анализа_"
        )

        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        await state.update_data(current_question=question_data['question'])
        await state.set_state(SurveyStates.answering_questions)

async def ask_ai_question(call: types.CallbackQuery, state: FSMContext, metric_key: str, question_index: int):
    """Задаем AI-вопрос пользователю"""
    data = await state.get_data()
    questions = data.get('questions', [])
    user_context = data.get('user_context', {})

    if question_index < len(questions):
        question_data = questions[question_index]
        metric_def = metrics_analyzer.get_all_metrics()[metric_key]

        text = (
            f"🤖 *AI-ОПРОС: {metric_def['name']}*\n\n"
            f"*{question_index + 1}/{len(questions)}*\n\n"
            f"{question_data['question']}\n\n"
            f"💡 _Ответьте подробно для персонального анализа_"
        )

        await call.message.edit_text(text, parse_mode="Markdown")
        await state.update_data(current_question=question_data['question'])
        await state.set_state(SurveyStates.answering_questions)

async def finish_ai_single_metric_survey(message: types.Message, state: FSMContext):
    """Завершение AI-опроса по одной метрике"""
    data = await state.get_data()
    user_context = data.get('user_context', {})
    current_metric = data.get('current_metric')

    await message.answer("🤖 Анализирую ваши ответы...")

    # Генерируем анализ на основе ответов
    try:
        analysis = await metrics_analyzer.generate_ai_metric_analysis(current_metric, user_context)
    except Exception as e:
        logger.error(f"Ошибка генерации AI-анализа: {e}")
        # Fallback анализ
        analysis = f"Благодарим за прохождение опроса по метрике '{metrics_analyzer.get_all_metrics()[current_metric]['name']}'! Ваши ответы помогут нам лучше понять ваши сильные стороны. Для детального анализа обратитесь к полному AI-опросу."

    text = (
        f"✅ *AI-ОПРОС ЗАВЕРШЕН!*\n\n"
        f"📊 *{metrics_analyzer.get_all_metrics()[current_metric]['name']}*\n\n"
        f"{analysis}\n\n"
        f"Хотите пройти опрос по другой метрике?"
    )

    keyboard = get_metrics_selection_keyboard()
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

    # Сохраняем результаты
    await save_ai_survey_results(message.from_user.id, user_context, survey_type='single', metric=current_metric)
    await state.clear()

async def finish_ai_full_survey(message: types.Message, state: FSMContext):
    """Завершение полного AI-опроса"""
    data = await state.get_data()
    user_context = data.get('user_context', {})

    await message.answer("🤖 Проводим комплексный анализ ваших ответов...")

    # Вычисляем метрики на основе ответов пользователя перед анализом
    answers = user_context.get('answers', [])
    if answers:
        try:
            # Генерируем вопросы и оцениваем ответы
            ai_questions = await metrics_analyzer.generate_ai_questions_based_on_answers(user_context)
            scores = await metrics_analyzer.score_answers_with_ai(answers, ai_questions)
        except Exception as e:
            logger.error(f"Ошибка AI-оценки ответов: {e}")
            scores = {}

        if not scores:
            # Fallback: use default scores if AI failed
            scores = {metric_key: 1 for metric_key in metrics_analyzer.metrics_definitions.keys() if metric_key != "professional_values"}

        # Создаем responses на основе оценок
        responses = {metric_key: [score] for metric_key, score in scores.items()}

        # Анализируем все метрики
        metrics_results = metrics_analyzer.analyze_user_responses(message.from_user.id, responses)

        # Добавляем результаты в user_context для анализа
        user_context['metrics_results'] = metrics_results
        user_context['name'] = user_context.get('profile', {}).get('name', 'Пользователь')

    # Генерируем полный анализ
    full_analysis = await metrics_analyzer.generate_comprehensive_ai_analysis(user_context)

    # Проверяем, является ли результат сообщением о недостатке данных
    if full_analysis.startswith("Недостаточно данных для анализа"):
        # Если данных недостаточно, показываем соответствующее сообщение
        text = (
            f"❌ *АНАЛИЗ НЕВОЗМОЖЕН*\n\n"
            f"{full_analysis}\n\n"
            f"💡 _Для комплексного анализа необходимо ответить на вопросы опроса_"
        )
    else:
        # Экранируем только проблемные символы, сохраняя форматирование Markdown
        escaped_analysis = full_analysis.replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')

        text = (
            f"🎉 *КОМПЛЕКСНЫЙ AI-АНАЛИЗ ЗАВЕРШЕН!*\n\n"
            f"{escaped_analysis}\n\n"
            f"💡 _Анализ создан на основе ваших детальных ответов_"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Пройти еще раз", callback_data="user_survey")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

    # Сохраняем результаты
    await save_ai_survey_results(message.from_user.id, user_context, survey_type='full')
    await state.clear()

async def get_user_context(user_id: int) -> dict:
    """Получаем структурированный контекст пользователя с группировкой по метрикам"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()

        # 1. Группируем предыдущие ответы ПО МЕТРИКАМ
        answers_by_metric = {}

        # Загружаем последние AI-опросы (MetricsSurvey)
        metrics_surveys = session.query(MetricsSurvey).filter(
            MetricsSurvey.user_id == user_id
        ).order_by(MetricsSurvey.created_at.desc()).limit(3).all()

        for survey in metrics_surveys:
            if survey.responses:
                for metric_key, responses in survey.responses.items():
                    if metric_key not in answers_by_metric:
                        answers_by_metric[metric_key] = []

                    # Преобразуем ответы в структурированный формат
                    if isinstance(responses, list):
                        for i, answer_text in enumerate(responses):
                            answers_by_metric[metric_key].append({
                                'question': f"Вопрос {i+1} по метрике {metric_key}",
                                'answer': answer_text,
                                'survey_id': survey.id,
                                'date': survey.created_at.isoformat()
                            })

        # 2. Добавляем профиль пользователя
        profile = {
            'name': user.name if user else 'Пользователь',
            'direction': user.direction if user else None,
            'sport_type': user.sport_type if user else None,
            'position': user.position if user else None,
            'role': user.role if user else UserRole.MEMBER.value,
            'level': user.level if user else 1
        }

        return {
            'profile': profile,
            'answers_by_metric': answers_by_metric,  # Группированные ответы!
            'has_history': bool(answers_by_metric)
        }

    finally:
        session.close()

async def save_ai_survey_results(user_id: int, user_context: dict, survey_type: str, metric: str = None):
    """Сохраняем результаты AI-опроса в новую модель MetricsSurvey"""
    try:
        session = get_session()
        try:
            # Анализируем ответы пользователя для получения результатов
            answers = user_context.get('answers', [])
            responses = {}
            results = {}

            # Группируем ответы по метрикам и анализируем
            if survey_type == 'full':
                # Для AI-опроса сначала оцениваем текстовые ответы
                ai_questions = await metrics_analyzer.generate_ai_questions_based_on_answers(user_context)
                user_answers = answers
                scores = await metrics_analyzer.score_answers_with_ai(user_answers, ai_questions)

                # Создаем responses на основе оценок
                responses = {metric_key: [score] for metric_key, score in scores.items()}

                # Анализируем все метрики
                results = metrics_analyzer.analyze_user_responses(user_id, responses)
                overall = metrics_analyzer.calculate_overall_score(results)

                # Сохраняем в MetricsSurvey
                metrics_survey = MetricsSurvey(
                    user_id=user_id,
                    survey_type=survey_type,
                    responses=responses,
                    results=results,
                    overall_score=overall.get('overall_score'),
                    category=overall.get('category'),
                    user_context=user_context
                )

            else:
                # Для одиночной метрики AI-опроса
                metric_key = metric
                user_answers = answers

                if metric_key and user_answers:
                    # Оцениваем текстовые ответы с помощью AI
                    ai_questions = await metrics_analyzer.generate_ai_questions_based_on_answers(user_context)
                    # Фильтруем вопросы только для данной метрики
                    metric_questions = ai_questions.get(metric_key, [])
                    if metric_questions:
                        scores = await metrics_analyzer.score_answers_with_ai(user_answers, {metric_key: metric_questions})
                        score = scores.get(metric_key, 1)
                        responses[metric_key] = [score]
                    else:
                        responses[metric_key] = [1]  # Значение по умолчанию

                    results = metrics_analyzer.analyze_user_responses(user_id, responses)

                    if metric_key in results:
                        result = results[metric_key]
                        # Проверяем тип score и конвертируем в число
                        score = result['score']
                        if isinstance(score, str):
                            try:
                                score = float(score)
                            except ValueError:
                                score = 1  # Значение по умолчанию при ошибке конвертации
                        elif not isinstance(score, (int, float)):
                            score = 1  # Значение по умолчанию для других типов
                        overall_score = score * 20  # Примерное преобразование к шкале 0-100

                        metrics_survey = MetricsSurvey(
                            user_id=user_id,
                            survey_type=survey_type,
                            metric_key=metric_key,
                            responses=responses,
                            results=results,
                            overall_score=overall_score,
                            user_context=user_context
                        )

                    if metric_key in results:
                        result = results[metric_key]
                        # Проверяем тип score и конвертируем в число
                        score = result['score']
                        if isinstance(score, str):
                            try:
                                score = float(score)
                            except ValueError:
                                score = 1  # Значение по умолчанию при ошибке конвертации
                        elif not isinstance(score, (int, float)):
                            score = 1  # Значение по умолчанию для других типов
                        overall_score = score * 20  # Примерное преобразование к шкале 0-100

                        metrics_survey = MetricsSurvey(
                            user_id=user_id,
                            survey_type=survey_type,
                            metric_key=metric_key,
                            responses=responses,
                            results=results,
                            overall_score=overall_score,
                            user_context=user_context
                        )

            if 'metrics_survey' in locals():
                session.add(metrics_survey)
                session.commit()

                logger.info(f"Результаты AI-опроса сохранены в MetricsSurvey для пользователя {user_id}")

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Ошибка сохранения результатов AI-опроса: {e}")

async def start_next_metric_ai(call: types.CallbackQuery, state: FSMContext):
    """Начало AI-опроса по следующей метрике"""
    data = await state.get_data()
    all_questions = data.get('all_questions', [])
    current_question_index = data.get('current_question_index', 0)

    if current_question_index < len(all_questions):
        question_data = all_questions[current_question_index]

        text = (
            f"🤖 *AI-ВОПРОС*\n\n"
            f"*{current_question_index + 1}/{len(all_questions)}*\n\n"
            f"{question_data['question']}\n\n"
            f"💡 _Ответьте подробно для точного анализа_"
        )

        await call.message.edit_text(text, parse_mode="Markdown")
        await state.update_data(current_question=question_data['question'])
        await state.set_state(SurveyStates.answering_questions)
    else:
        await finish_ai_full_survey(call, state)

async def start_next_metric(call: types.CallbackQuery, state: FSMContext):
    """Начало следующей метрики в полном опросе"""
    data = await state.get_data()
    current_index = data.get('current_metric_index', 0)
    all_metrics = list(metrics_analyzer.get_all_metrics().keys())

    if current_index < len(all_metrics):
        next_metric = all_metrics[current_index]
        responses = data.get('responses', {})
        responses[next_metric] = []
        await state.update_data(responses=responses, current_metric=next_metric, question_index=0)
        await ask_question(call, state, next_metric, 0)
    else:
        await finish_full_survey(call, state)

async def ask_question(call: types.CallbackQuery, state: FSMContext, metric_key: str, question_index: int):
    """Задаем вопрос пользователю"""
    questions = metrics_analyzer.get_survey_questions(metric_key)
    metric_def = metrics_analyzer.get_all_metrics()[metric_key]

    if question_index >= len(questions):
        return

    question = questions[question_index]

    # Определяем максимальный рейтинг
    max_rating = metric_def["scale"][-1]

    text = (
        f"📊 *{metric_def['name']}*\n\n"
        f"*{question_index + 1}/{len(questions)}*\n\n"
        f"{question}\n\n"
        f"Оцените по шкале от 1 до {max_rating}:\n"
        f"_{metric_def['description']}_"
    )

    keyboard = get_rating_keyboard(metric_key, question_index, max_rating)

    try:
        await call.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось редактировать сообщение: {e}")
        await call.bot.send_message(
            chat_id=call.from_user.id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

async def finish_single_metric_survey(call: types.CallbackQuery, state: FSMContext, metric_key: str):
    """Завершение опроса по одной метрике"""
    data = await state.get_data()
    responses = data.get('responses', {})

    # Анализируем результаты
    results = metrics_analyzer.analyze_user_responses(call.from_user.id, responses)

    if metric_key in results:
        result = results[metric_key]
        vip_text = "⭐ VIP метрика" if result['vip'] else "Обычная метрика"

        text = (
            f"✅ *Опрос завершен!*\n\n"
            f"📊 *{result['name']}*\n"
            f"{vip_text}\n\n"
            f"🏆 *Ваш балл:* {result['score']}\n"
            f"📝 *Интерпретация:* {result['interpretation']}\n\n"
            f"Хотите пройти опрос по другой метрике?"
        )

        try:
            await call.message.edit_text(
                text,
                reply_markup=get_metrics_selection_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Не удалось редактировать сообщение: {e}")
            await call.bot.send_message(
                chat_id=call.from_user.id,
                text=text,
                reply_markup=get_metrics_selection_keyboard(),
                parse_mode="Markdown"
            )

    # Сохраняем результаты в базу данных
    await save_survey_results(call.from_user.id, responses)

    await state.clear()

async def finish_full_survey(call: types.CallbackQuery, state: FSMContext):
    """Завершение полного опроса"""
    data = await state.get_data()
    responses = data.get('responses', {})

    # Анализируем все результаты
    results = metrics_analyzer.analyze_user_responses(call.from_user.id, responses)
    overall = metrics_analyzer.calculate_overall_score(results)
    recommendations = metrics_analyzer.generate_personal_recommendations(results)

    # Формируем текст результатов
    results_text = "📊 *РЕЗУЛЬТАТЫ ПОЛНОГО ОПРОСА*\n\n"

    # Общий балл
    results_text += f"🎯 *Общий балл:* {overall['overall_score']}/100\n"
    results_text += f"📈 *Категория:* {overall['category']}\n\n"

    # Детальные результаты
    results_text += "📋 *ПО МЕТРИКАМ:*\n"
    for key, result in results.items():
        vip_mark = "⭐" if result['vip'] else ""
        results_text += f"{vip_mark} {result['name']}: {result['score']} - {result['interpretation']}\n"

    results_text += "\n💡 *РЕКОМЕНДАЦИИ:*\n"
    for rec in recommendations[:3]:
        results_text += f"• {rec}\n"

    results_text += "\nХотите посмотреть детальный AI-анализ?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 AI-анализ", callback_data="survey_ai_analysis")],
        [InlineKeyboardButton(text="📋 Пройти еще раз", callback_data="user_survey")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])

    try:
        await call.message.edit_text(
            results_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось редактировать сообщение: {e}")
        await call.bot.send_message(
            chat_id=call.from_user.id,
            text=results_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    # Сохраняем результаты
    await save_survey_results(call.from_user.id, responses)
    await state.update_data(survey_results=results, overall_score=overall)

@router.callback_query(F.data == 'survey_ai_analysis')
async def show_ai_analysis(call: types.CallbackQuery, state: FSMContext):
    """Показать AI-анализ профиля"""
    await call.answer()

    data = await state.get_data()
    results = data.get('survey_results', {})

    if not results:
        await call.message.edit_text("❌ Результаты опроса не найдены. Пройдите опрос заново.")
        return

    # Получаем имя пользователя
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == call.from_user.id).first()
        user_name = user.name if user and user.name else "Пользователь"
    finally:
        session.close()

    await call.message.edit_text("🤖 Генерирую персональный анализ...")

    # Генерируем AI-анализ
    analysis = await metrics_analyzer.generate_ai_analysis(user_name, results)

    # Экранируем только проблемные символы, сохраняя форматирование Markdown
    escaped_analysis = analysis.replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')

    text = (
        f"🤖 *AI-АНАЛИЗ ПРОФИЛЯ*\n\n"
        f"👤 *{user_name}*\n\n"
        f"{escaped_analysis}\n\n"
        f"💡 _Анализ создан на основе ваших ответов в опросе_"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Новый опрос", callback_data="user_survey")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])

    await call.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    await state.clear()

@router.callback_query(F.data == 'survey_view_results')
async def view_previous_results(call: types.CallbackQuery):
    """Просмотр предыдущих результатов из Survey или MetricsSurvey моделей"""
    await call.answer()

    session = get_session()
    try:
        # Сначала проверяем MetricsSurvey (новая модель для AI-опросов)
        metrics_survey = session.query(MetricsSurvey).filter(
            MetricsSurvey.user_id == call.from_user.id
        ).order_by(MetricsSurvey.created_at.desc()).first()

        if metrics_survey:
            # Используем данные из MetricsSurvey
            results = metrics_survey.results or {}
            overall_score = metrics_survey.overall_score
            category = metrics_survey.category
            survey_date = metrics_survey.created_at

            text = "📊 *ВАШИ ПОСЛЕДНИЕ РЕЗУЛЬТАТЫ (AI-ОПРОС)*\n\n"

            if overall_score is not None:
                text += f"🎯 *Общий балл:* {overall_score}/100\n"
                if category:
                    text += f"📈 *Категория:* {category}\n\n"
                else:
                    text += "\n"

            if results:
                text += "📋 *МЕТРИКИ:*\n"
                for key, result in results.items():
                    metric_def = metrics_analyzer.get_all_metrics().get(key, {})
                    vip_mark = "⭐" if metric_def.get("vip", False) else ""
                    score = result.get('score', 0) if isinstance(result, dict) else result
                    text += f"{vip_mark} {result.get('name', key) if isinstance(result, dict) else metric_def.get('name', key)}: {score}\n"

            text += f"\n📅 *Дата:* {survey_date.strftime('%d.%m.%Y %H:%M')}"

        else:
            # Проверяем старую модель Survey
            survey = session.query(Survey).filter(
                Survey.user_id == call.from_user.id
            ).order_by(Survey.date.desc()).first()

            if not survey or not hasattr(survey, 'survey_data'):
                await call.message.edit_text(
                    "❌ У вас пока нет сохраненных результатов опросов.\n\n"
                    "Пройдите опрос, чтобы получить анализ!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 Пройти опрос", callback_data="user_survey")],
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
                    ])
                )
                return

            # Парсим сохраненные данные из старой модели
            try:
                survey_data = json.loads(survey.survey_data)
                responses = survey_data.get('responses', {})
                results = survey_data.get('results', {})
                overall = survey_data.get('overall', {})
            except:
                await call.message.edit_text("❌ Ошибка загрузки результатов.")
                return

            text = "📊 *ВАШИ ПОСЛЕДНИЕ РЕЗУЛЬТАТЫ*\n\n"

            if overall:
                text += f"🎯 *Общий балл:* {overall.get('overall_score', 0)}/100\n"
                text += f"📈 *Категория:* {overall.get('category', 'Не определена')}\n\n"

            if results:
                text += "📋 *МЕТРИКИ:*\n"
                for key, result in results.items():
                    metric_def = metrics_analyzer.get_all_metrics().get(key, {})
                    vip_mark = "⭐" if metric_def.get("vip", False) else ""
                    text += f"{vip_mark} {result.get('name', key)}: {result.get('score', 0)}\n"

            text += f"\n📅 *Дата:* {survey.date.strftime('%d.%m.%Y %H:%M')}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Пройти заново", callback_data="user_survey")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
        ])

        await call.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    finally:
        session.close()

async def save_survey_results(user_id: int, responses: dict):
    """Сохраняем результаты опроса в базу данных"""
    try:
        # Анализируем результаты
        results = metrics_analyzer.analyze_user_responses(user_id, responses)
        overall = metrics_analyzer.calculate_overall_score(results)

        # Сохраняем в базу
        session = get_session()
        try:
            survey_data = {
                'responses': responses,
                'results': results,
                'overall': overall,
                'completed_at': datetime.now().isoformat()
            }

            survey = Survey(
                user_id=user_id,
                survey_data=json.dumps(survey_data),
                created_at=datetime.now()
            )

            session.add(survey)
            session.commit()

            logger.info(f"Результаты опроса сохранены для пользователя {user_id}")

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Ошибка сохранения результатов опроса: {e}")
