# services/ai_service.py
import openai
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib

from database import User, Challenge, Survey, Organization, get_session
from config import load_config

logger = logging.getLogger(__name__)

class AIService:
    """Фасад для AI сервисов"""

    def __init__(self):
        self.client = None  # Добавляем инициализацию client
        self.is_active = False
        self.use_cache = True  # Включаем кэширование
        self._cache = {}  # Кэш для ответов
        self._cache_timestamps = {}  # Временные метки кэша

        # Импортируем здесь, чтобы избежать циклических зависимостей
        try:
            from services.hf_service import HuggingFaceService
            self.hf_service = HuggingFaceService()
            self.is_active = self.hf_service.is_active

            # Если hf_service имеет client, используем его
            if hasattr(self.hf_service, 'client'):
                self.client = self.hf_service.client

            logger.info("✅ AIService инициализирован с Hugging Face")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации AIService: {e}")
            self.hf_service = None
            self.is_active = False
    
    async def generate_personalized_challenge(self, user_id: int, direction: str, user_data: Dict) -> Dict:
        """Генерация персонализированного челленджа"""
        if not self.is_active:
            return self._get_fallback_challenge(direction, user_data.get('level', 1))
        
        try:
            return await self.hf_service.generate_challenge(direction, user_data.get('level', 1))
        except Exception as e:
            logger.error(f"Ошибка генерации челленджа: {e}")
            return self._get_fallback_challenge(direction, user_data.get('level', 1))
    
    async def answer_user_question(self, question: str, context: Dict = None) -> str:
        """Ответ на вопрос пользователя"""
        if not self.is_active or not self.hf_service:
            return "AI-помощник временно недоступен. Попробуйте позже."
        
        return await self.hf_service.answer_question(question, context)
    
    async def get_json_response(self, prompt: str) -> Dict:
        """Получение JSON ответа"""
        if not self.is_active or not self.hf_service:
            return {"error": "AI сервис недоступен"}

        try:
            return await self.hf_service.get_json_response(prompt)
        except Exception as e:
            logger.error(f"Ошибка в get_json_response: {e}")
            return {"error": f"Ошибка AI сервиса: {str(e)[:100]}"}
    

    
    async def get_motivation_phrase(self, user_id: int = None, context: Dict = None) -> str:
        """Получение мотивационной фразы"""
        if not self.is_active or not self.hf_service:
            return "Каждый шаг имеет значение. Начни свой путь к успеху сегодня! 🚀"
        
        situation = context.get("situation", "general") if context else "general"
        prompt = f"Создай короткую мотивационную фразу для ситуации: {situation}. Фраза должна быть на русском с 1-2 эмодзи."
        
        try:
            return await self.hf_service.generate_response(prompt, 
                system_prompt="Ты мастер мотивационных речей.")
        except:
            return "Ты делаешь отличную работу! Продолжай двигаться вперед! 🔥"
    
    def _get_fallback_challenge(self, direction: str, level: int) -> Dict:
        """Fallback челлендж"""
        import random
        
        challenges = {
            "football": [
                "Отработайте 20 точных пасов с партнером с расстояния 10 метров",
                "Сделайте 3 круга дриблинга вокруг конусов",
                "Выполните 15 ударов по воротам с разных позиций"
            ],
            "company": [
                "Проведите 15-минутный мозговой штурм по улучшению рабочих процессов",
                "Составьте план личного развития на неделю",
                "Поделитесь полезным советом с коллегой"
            ],
            "growth": [
                "Прочитайте 10 страниц книги по саморазвитию",
                "Запишите 3 цели на завтра вечером",
                "Сделайте 10-минутную медитацию для концентрации"
            ]
        }
        
        text = random.choice(challenges.get(direction, ["Выполните полезное задание для развития"]))
        points = random.randint(10, 30)
        
        return {
            "text": text,
            "points": points,
            "difficulty": "easy" if level < 3 else "medium" if level < 5 else "hard",
            "estimated_time": "15-30 минут",
            "success_criteria": ["Завершить все пункты", "Выполнить качественно"],
            "success_tips": ["Не торопитесь", "Сосредоточьтесь на качестве"]
        }
    
    def _generate_cache_key(self, task_type: str, params: Dict) -> str:
        """Генерация ключа кэша на основе параметров запроса"""
        params_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
        hash_input = f"{task_type}:{params_str}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _get_from_cache(self, key: str, ttl: int = 3600) -> Optional[Any]:
        """Получение данных из кэша"""
        if not self.use_cache or key not in self._cache:
            return None
        
        # Проверяем TTL
        if key in self._cache_timestamps:
            cache_time = self._cache_timestamps[key]
            if datetime.now() - cache_time > timedelta(seconds=ttl):
                # Удаляем просроченный кэш
                del self._cache[key]
                del self._cache_timestamps[key]
                return None
        
        return self._cache[key]
    
    def _set_to_cache(self, key: str, value: Any, ttl: int = 3600):
        """Сохранение данных в кэш"""
        if not self.use_cache:
            return
        
        # Очистка устаревших записей (опционально)
        if len(self._cache) > 1000:  # Ограничение размера кэша
            self._cache.clear()
            self._cache_timestamps.clear()
        
        self._cache[key] = value
        self._cache_timestamps[key] = datetime.now()
    
    async def generate_personalized_challenge(
        self, 
        user_id: int,
        direction: str,
        user_data: Dict
    ) -> Dict[str, Any]:
        """
        Генерация персонализированного челленджа с учетом направления
        
        Args:
            user_id: ID пользователя в БД
            direction: Направление (football/company/growth)
            user_data: Данные пользователя
        
        Returns:
            Словарь с челленджем
        """
        # Проверка доступности основного сервиса
        if not self.is_active or not self.client:
            logger.info("Использую fallback для генерации челленджа")
            return self._get_fallback_challenge(direction, user_data.get('level', 1))

        # Проверяем флаг превышения квоты
        if hasattr(self, 'hf_service') and self.hf_service and hasattr(self.hf_service, 'quota_exceeded') and self.hf_service.quota_exceeded:
            logger.warning("Квота AI превышена, возвращаем fallback челлендж")
            return self._get_fallback_challenge(direction, user_data.get('level', 1))
        
        # Генерация ключа кэша
        cache_key = None
        if self.use_cache:
            cache_key = self._generate_cache_key("challenge_generation", {
                "user_id": user_id,
                "direction": direction,
                "level": user_data.get('level', 1)
            })
            cached = self._get_from_cache(cache_key, ttl=1800)  # 30 минут для челленджей
            if cached:
                logger.info(f"Использую кэшированный челлендж для пользователя {user_id}")
                return cached
        
        # Промпты для разных направлений
        direction_prompts = {
            "football": """
            Ты футбольный тренер с опытом подготовки профессиональных игроков.
            Создай футбольный челлендж, который улучшит:
            1. Технические навыки (дриблинг, пас, удар)
            2. Физическую подготовку (выносливость, скорость, сила)
            3. Тактическое мышление
            4. Командное взаимодействие
            
            Учти уровень игрока и доступное оборудование.
            """,
            "company": """
            Ты бизнес-коуч и эксперт по корпоративному развитию.
            Создай рабочий челлендж, который поможет:
            1. Развить профессиональные навыки
            2. Улучшить коммуникацию в команде
            3. Повысить продуктивность
            4. Развить лидерские качества
            
            Челендж должен быть выполним в рабочей среде.
            """,
            "growth": """
            Ты ментор по личностному росту и развитию.
            Создай челлендж для самосовершенствования, который поможет:
            1. Развить новые привычки
            2. Улучшить ментальное здоровье
            3. Повысить осознанность
            4. Достичь личных целей
            
            Учитывай текущий ритм жизни пользователя.
            """
        }
        
        system_prompt = direction_prompts.get(
            direction, 
            "Ты тренер по развитию навыков. Создай полезный и выполнимый челлендж."
        )
        
        user_prompt = f"""
        Создай персонализированный челлендж для пользователя.
        
        Информация о пользователе:
        - Направление: {direction}
        - Уровень: {user_data.get('level', 1)} из 10
        - Очки: {user_data.get('points', 0)}
        - Последние показатели: {json.dumps(user_data.get('last_metrics', {}), ensure_ascii=False)}
        - Предыдущие успехи: {json.dumps(user_data.get('previous_successes', []), ensure_ascii=False)}
        
        Челендж должен быть:
        1. Соответствовать направлению "{direction}"
        2. Соответствовать уровню {user_data.get('level', 1)}
        3. Занять {user_data.get('available_time', '15-30')} минут
        4. Быть конкретным и измеримым
        5. Приносить реальную пользу
        6. Иметь четкие критерии успеха
        
        Формат ответа JSON:
        {{
            "text": "Текст челленджа с четкими инструкциями",
            "points": 10-50,  // Очки за выполнение
            "difficulty": "easy/medium/hard",
            "estimated_time": "15-30 минут",
            "required_resources": ["ресурс 1", "ресурс 2"],  // Что нужно для выполнения
            "success_criteria": ["критерий 1", "критерий 2"],  // Как понять что челлендж выполнен
            "why_this_challenge": "Объяснение почему этот челлендж подходит",
            "success_tips": ["Совет 1", "Совет 2", "Совет 3"],
            "related_skills": ["навык 1", "навык 2"]  // Какие навыки развивает
        }}
        """
        
        max_retries = 2
        for retry in range(max_retries + 1):
            # Проверяем квоту перед каждой попыткой
            if hasattr(self, 'hf_service') and self.hf_service and hasattr(self.hf_service, 'quota_exceeded') and self.hf_service.quota_exceeded:
                logger.warning("Квота AI превышена во время генерации челленджа")
                break

            try:
                model = self._get_model("challenge_generation", retry)

                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=800,
                    response_format={"type": "json_object"}
                )

                result = json.loads(response.choices[0].message.content)

                # Валидация результата
                required_fields = ["text", "points", "difficulty", "estimated_time"]
                if all(field in result for field in required_fields):
                    # Добавляем метаданные
                    result["ai_model"] = model
                    result["generated_at"] = datetime.now().isoformat()
                    result["direction"] = direction

                    # Сохраняем в кэш
                    if self.use_cache and cache_key:
                        self._set_to_cache(cache_key, result, ttl=1800)

                    logger.info(f"Челлендж сгенерирован через модель {model}")
                    return result
                else:
                    logger.warning(f"Модель вернула неполный ответ: {result}")
                    # Пробуем другую модель
                    continue

            except Exception as e:
                logger.error(f"Попытка {retry + 1} не удалась для модели {model}: {e}")
                # Проверяем на 402 ошибку и устанавливаем флаг
                if "402" in str(e) or "quota" in str(e).lower():
                    if hasattr(self, 'hf_service') and self.hf_service:
                        self.hf_service.quota_exceeded = True
                        logger.warning("Установлен флаг quota_exceeded из-за 402 ошибки")
                    break
                if retry == max_retries:
                    logger.error("Все попытки генерации челленджа провалились")
                    break

        # Fallback если все попытки провалились
        return self._get_fallback_challenge(direction, user_data.get('level', 1))
    
    async def get_ai_response(self, question: str, context: Optional[Dict] = None) -> str:
        """
        Основной метод для получения ответа от AI
        (переименован с answer_user_question чтобы избежать рекурсии)
        """
        if not self.is_active or not self.client:
            return "🤖 AI сервис временно недоступен. Попробуйте позже!"

        # Проверяем флаг превышения квоты
        if hasattr(self, 'hf_service') and self.hf_service and hasattr(self.hf_service, 'quota_exceeded') and self.hf_service.quota_exceeded:
            logger.warning("Квота AI превышена, возвращаем fallback ответ")
            return "🤖 Квота AI запросов исчерпана. Попробуйте позже или обратитесь к администратору."

        try:
            # Системный промпт
            system_prompt = """Ты помощник в боте для развития команд и личного роста.
            Отвечай дружелюбно, профессионально и мотивирующе на русском языке.
            Используй эмодзи для выразительности. Будь конкретным и полезным."""

            # Формируем контекст
            context_str = ""
            if context:
                if context.get("user_name"):
                    context_str += f"Пользователь: {context['user_name']}\n"
                if context.get("user_level"):
                    context_str += f"Уровень: {context['user_level']}\n"

            user_prompt = f"""{context_str}
            Вопрос пользователя: {question}

            Дай полезный и мотивирующий ответ."""

            logger.info(f"🤖 AI запрос: {question[:100]}...")

            response = self.client.chat.completions.create(
                model="deepseek-ai/DeepSeek-V3.2",  # Основная модель
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )

            answer = response.choices[0].message.content
            logger.info(f"✅ AI ответ получен ({len(answer)} символов)")

            return answer

        except openai.APIConnectionError as e:
            logger.error(f"❌ Ошибка подключения к Hugging Face Router: {e}")
            return "🤖 Не удалось подключиться к AI. Проверьте интернет-соединение."
        except openai.RateLimitError as e:
            logger.error(f"❌ Лимит запросов: {e}")
            return "🤖 Слишком много запросов. Попробуйте через минуту."
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка AI: {e}")
            return "🤖 Произошла ошибка. Попробуйте задать вопрос позже."

    async def analyze_user_progress(self, user_id: int) -> Dict[str, Any]:
        """
        Детальный анализ прогресса пользователя - исправленная версия
        """
        # Проверка доступности
        if not self.is_active:
            return self._get_fallback_analysis(user_id)

        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"error": "Пользователь не найден"}

            # Безопасно получаем surveys и challenges
            try:
                surveys = session.query(Survey).filter(Survey.user_id == user_id).all()
            except:
                surveys = []

            try:
                challenges = session.query(Challenge).filter(Challenge.user_id == user_id).all()
            except:
                challenges = []

            # Генерация анализа через AI
            analysis = await self._generate_ai_analysis(user, surveys, challenges)

            return analysis

        except Exception as e:
            logger.error(f"Ошибка анализа прогресса: {e}")
            return self._get_fallback_analysis(user_id)
        finally:
            session.close()
    
    async def _generate_ai_analysis(self, user, surveys, challenges):
        """Генерация AI анализа - исправленная версия"""
        completed_challenges = [c for c in challenges if c.status == "COMPLETED"]

        # Используем safe_get для безопасного получения атрибутов
        def safe_get(obj, attr, default=None):
            return getattr(obj, attr, default) if hasattr(obj, attr) else default

        progress_data = {
            "user_info": {
                "name": safe_get(user, 'name', 'Пользователь'),
                "level": safe_get(user, 'level', 1),
                "points": safe_get(user, 'points', 0),
            },
            "metrics": {
                "total_surveys": len(surveys),
                "completed_challenges": len(completed_challenges),
                "challenge_completion_rate": len(completed_challenges) / len(challenges) * 100 if challenges else 0,
                "survey_count": len(surveys)
            }
        }

        # Если у Survey есть score, добавляем
        if surveys and hasattr(surveys[0], 'score'):
            progress_data["metrics"]["avg_survey_score"] = sum(safe_get(s, 'score', 0) for s in surveys) / len(surveys)

        prompt = f"""
        Ты опытный аналитик и коуч. Проанализируй данные пользователя и создай мотивирующий отчет.

        ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
        {json.dumps(progress_data, ensure_ascii=False, indent=2)}

        СОЗДАЙ ОТЧЕТ КОТОРЫЙ ВКЛЮЧАЕТ:
        1. Краткий обзор прогресса
        2. Ключевые достижения
        3. Сильные стороны пользователя
        4. Области для роста
        5. Конкретные рекомендации

        Формат ответа JSON:
        {{
            "executive_summary": "Краткий обзор",
            "key_achievements": ["достижение 1", "достижение 2"],
            "strengths": ["сильная сторона 1", "сильная сторона 2"],
            "growth_areas": ["область роста 1", "область роста 2"],
            "weekly_recommendations": ["рекомендация 1", "рекомендация 2"],
            "personalized_motivation": "Мотивационное сообщение"
        }}
        """

        for retry in range(2):
            try:
                model = self._get_model("analysis", retry)

                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Ты аналитик данных и мотивационный коуч."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.6,
                    max_tokens=800,
                    response_format={"type": "json_object"}
                )

                analysis = json.loads(response.choices[0].message.content)
                analysis["generated_at"] = datetime.now().isoformat()
                analysis["model_used"] = model

                return analysis

            except Exception as e:
                logger.error(f"Попытка {retry + 1} анализа не удалась: {e}")

        # Fallback - ЭТА СТРОКА ДОЛЖНА БЫТЬ ЗА ЦИКЛОМ!
        return self._generate_fallback_analysis(progress_data)

    def _get_model(self, task_type: str, retry: int = 0) -> str:
        """
        Выбор модели в зависимости от типа задачи и номера попытки
        """
        models = {
            "challenge_generation": [
                "deepseek-ai/DeepSeek-V3.2",
                "meta-llama/llama-3.1-70b-instruct",
                "anthropic/claude-3-haiku"
            ],
            "analysis": [
                "deepseek-ai/DeepSeek-V3.2",
                "meta-llama/llama-3.1-70b-instruct",
                "anthropic/claude-3-haiku"
            ],
            "chat": [
                "deepseek-ai/DeepSeek-V3.2",
                "meta-llama/llama-3.1-70b-instruct",
                "anthropic/claude-3-haiku"
            ]
        }

        available_models = models.get(task_type, ["deepseek-ai/DeepSeek-V3.2"])
        model_index = min(retry, len(available_models) - 1)
        return available_models[model_index]

    def _get_fallback_analysis(self, user_id: int) -> Dict[str, Any]:
        """
        Fallback анализ прогресса пользователя
        """
        from database import get_session, User

        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return {"error": "Пользователь не найден"}

            return {
                "executive_summary": f"Привет, {user.name}! Ты на уровне {user.level} с {user.points} очками.",
                "key_achievements": [
                    f"Достигнут уровень {user.level}",
                    f"Заработано {user.points} очков"
                ],
                "strengths": ["Активное участие", "Регулярность"],
                "growth_areas": ["Повышение сложности заданий"],
                "weekly_recommendations": ["Попробуй новый челлендж", "Пригласи друга в команду"],
                "personalized_motivation": "Продолжай в том же духе! 💪"
            }
        finally:
            session.close()

    def _generate_fallback_analysis(self, progress_data: Dict) -> Dict[str, Any]:
        """
        Генерация fallback анализа на основе данных прогресса
        """
        user_info = progress_data.get("user_info", {})
        metrics = progress_data.get("metrics", {})

        return {
            "executive_summary": f"Привет, {user_info.get('name', 'Пользователь')}! Ты на уровне {user_info.get('level', 1)} с {user_info.get('points', 0)} очками.",
            "key_achievements": [
                f"Достигнут уровень {user_info.get('level', 1)}",
                f"Заработано {user_info.get('points', 0)} очков",
                f"Выполнено {metrics.get('completed_challenges', 0)} челленджей"
            ],
            "strengths": ["Активное участие", "Регулярность"],
            "growth_areas": ["Повышение сложности заданий"],
            "weekly_recommendations": ["Попробуй новый челлендж", "Пригласи друга в команду"],
            "personalized_motivation": "Продолжай в том же духе! 💪"
        }
