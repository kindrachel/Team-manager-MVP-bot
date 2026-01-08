"""
AI Helper - вспомогательный сервис для работы с AI функциями
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AIHelper:
    """Вспомогательный класс для AI операций"""
    
    def __init__(self, ai_service):
        """
        Args:
            ai_service: Экземпляр AIService
        """
        self.ai_service = ai_service
        logger.info("AIHelper инициализирован")
    
    async def get_simple_response(self, message: str) -> str:
        """
        Получить простой ответ от AI
        
        Args:
            message: Сообщение пользователя
        
        Returns:
            Ответ AI
        """
        try:
            return await self.ai_service.get_ai_response(
                f"Ответь кратко на: {message}",
                context={"situation": "simple_chat"}
            )
        except Exception as e:
            logger.error(f"Ошибка получения ответа: {e}")
            return "Извините, не могу ответить сейчас. Попробуйте позже."
    
    async def analyze_text_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Анализ настроения текста
        
        Args:
            text: Текст для анализа
        
        Returns:
            Результат анализа
        """
        try:
            prompt = f"""
            Проанализируй настроение текста:
            "{text}"
            
            Верни JSON с анализом:
            {{
                "sentiment": "positive/negative/neutral",
                "confidence": 0-1,
                "keywords": ["ключевое слово 1", "ключевое слово 2"],
                "summary": "Краткое резюме настроения"
            }}
            """
            
            response = await self.ai_service.get_json_response(prompt)
            
            if "error" in response:
                return self._get_default_sentiment()
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка анализа настроения: {e}")
            return self._get_default_sentiment()
    
    async def summarize_progress(self, user_data: Dict[str, Any]) -> str:
        """
        Создать краткое резюме прогресса пользователя
        
        Args:
            user_data: Данные пользователя
        
        Returns:
            Текстовое резюме
        """
        try:
            prompt = f"""
            Создай краткое мотивационное резюме для пользователя.
            
            Данные:
            - Имя: {user_data.get('name', 'Пользователь')}
            - Уровень: {user_data.get('level', 1)}
            - Очки: {user_data.get('points', 0)}
            - Последняя активность: {user_data.get('last_activity', 'сегодня')}
            
            Сделай резюме коротким, мотивирующим и позитивным.
            """
            
            response = await self.ai_service.get_ai_response(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка создания резюме: {e}")
            return f"👋 {user_data.get('name', 'Пользователь')}, продолжайте двигаться вперед!"
    
    async def generate_quick_tip(self, category: str = "general") -> str:
        """
        Генерация быстрого совета
        
        Args:
            category: Категория совета
        
        Returns:
            Совет
        """
        categories = {
            "productivity": "продуктивности",
            "motivation": "мотивации", 
            "health": "здоровья",
            "learning": "обучения",
            "teamwork": "командной работы",
            "general": "саморазвития"
        }
        
        category_name = categories.get(category, "саморазвития")
        
        try:
            prompt = f"Дай один короткий практический совет по {category_name}. Только совет, без лишних слов."
            
            response = await self.ai_service.get_ai_response(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка генерации совета: {e}")
            return "🎯 Маленькие шаги каждый день ведут к большим результатам!"
    
    async def validate_challenge(self, challenge_text: str) -> Dict[str, Any]:
        """
        Валидация челленджа через AI
        
        Args:
            challenge_text: Текст челленджа
        
        Returns:
            Результат валидации
        """
        try:
            prompt = f"""
            Проверь челлендж на соответствие критериям:
            
            Челлендж: "{challenge_text}"
            
            Критерии:
            1. Конкретность (есть четкое задание)
            2. Измеримость (можно проверить выполнение)
            3. Достижимость (можно выполнить за разумное время)
            4. Релевантность (полезен для развития)
            
            Верни JSON:
            {{
                "is_valid": true/false,
                "score": 0-10,
                "strengths": ["сильная сторона 1", "сильная сторона 2"],
                "improvements": ["что улучшить 1", "что улучшить 2"],
                "suggested_fix": "исправленный вариант (если нужен)"
            }}
            """
            
            response = await self.ai_service.get_json_response(prompt)
            
            if "error" in response:
                return {
                    "is_valid": True,
                    "score": 7,
                    "strengths": ["Четкая формулировка"],
                    "improvements": [],
                    "suggested_fix": challenge_text
                }
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка валидации челленджа: {e}")
            return {
                "is_valid": True,
                "score": 7,
                "strengths": ["Принят без проверки"],
                "improvements": [],
                "suggested_fix": challenge_text
            }
    
    async def extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """
        Извлечение ключевых слов из текста
        
        Args:
            text: Текст
            max_keywords: Максимальное количество ключевых слов
        
        Returns:
            Список ключевых слов
        """
        try:
            prompt = f"""
            Извлеки {max_keywords} ключевых слов из текста:
            
            "{text}"
            
            Верни JSON:
            {{
                "keywords": ["слово1", "слово2", ...]
            }}
            """
            
            response = await self.ai_service.get_json_response(prompt)
            
            if "error" in response or "keywords" not in response:
                # Fallback: простой список слов
                words = text.lower().split()
                return list(set(words[:max_keywords]))
            
            return response["keywords"][:max_keywords]
            
        except Exception as e:
            logger.error(f"Ошибка извлечения ключевых слов: {e}")
            return []
    
    async def categorize_message(self, message: str) -> Dict[str, Any]:
        """
        Категоризация сообщения пользователя
        
        Args:
            message: Сообщение пользователя
        
        Returns:
            Категория и метаданные
        """
        try:
            prompt = f"""
            Определи категорию сообщения:
            
            "{message}"
            
            Возможные категории:
            - question (вопрос)
            - feedback (обратная связь)
            - complaint (жалоба)
            - suggestion (предложение)
            - greeting (приветствие)
            - farewell (прощание)
            - challenge_related (про челленджи)
            - progress_related (про прогресс)
            - other (другое)
            
            Верни JSON:
            {{
                "category": "название категории",
                "confidence": 0-1,
                "urgency": "low/medium/high",
                "needs_response": true/false
            }}
            """
            
            response = await self.ai_service.get_json_response(prompt)
            
            if "error" in response:
                return {
                    "category": "other",
                    "confidence": 0.5,
                    "urgency": "low",
                    "needs_response": True
                }
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка категоризации: {e}")
            return {
                "category": "other",
                "confidence": 0.5,
                "urgency": "low",
                "needs_response": True
            }
    
    async def format_ai_response(
        self, 
        raw_response: str, 
        style: str = "friendly"
    ) -> str:
        """
        Форматирование ответа AI
        
        Args:
            raw_response: Сырой ответ AI
            style: Стиль форматирования
        
        Returns:
            Отформатированный ответ
        """
        try:
            styles = {
                "friendly": "дружелюбный, с эмодзи",
                "professional": "профессиональный, без эмодзи",
                "motivational": "мотивационный, энергичный",
                "concise": "краткий, по делу"
            }
            
            style_desc = styles.get(style, "дружелюбный")
            
            prompt = f"""
            Отформатируй этот ответ в {style_desc} стиле:
            
            "{raw_response}"
            
            Верни только отформатированный текст, без объяснений.
            """
            
            response = await self.ai_service.get_ai_response(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка форматирования: {e}")
            # Просто возвращаем как есть с эмодзи
            if style == "friendly":
                return f"💬 {raw_response}"
            elif style == "motivational":
                return f"🚀 {raw_response}"
            else:
                return raw_response
    
    def _get_default_sentiment(self) -> Dict[str, Any]:
        """Получить дефолтный анализ настроения"""
        return {
            "sentiment": "neutral",
            "confidence": 0.5,
            "keywords": [],
            "summary": "Нейтральное настроение"
        }
    
    async def get_daily_insight(self, user_id: int) -> str:
        """
        Получить ежедневное прозрение/совет
        
        Args:
            user_id: ID пользователя
        
        Returns:
            Ежедневное прозрение
        """
        try:
            # Используем день недели для разнообразия
            days = [
                "понедельник", "вторник", "среду", "четверг", 
                "пятницу", "субботу", "воскресенье"
            ]
            day_of_week = datetime.now().weekday()
            day_name = days[day_of_week] if day_of_week < len(days) else "день"
            
            prompt = f"""
            Создай короткое мотивационное прозрение на {day_name}.
            Оно должно быть вдохновляющим, но практичным.
            Максимум 2 предложения.
            """
            
            response = await self.ai_service.get_ai_response(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Ошибка получения прозрения: {e}")
            return "Каждый день - новая возможность стать лучше! 💫"
    
    async def batch_process(
        self, 
        items: List[str], 
        process_type: str
    ) -> List[Dict[str, Any]]:
        """
        Пакетная обработка элементов
        
        Args:
            items: Список элементов
            process_type: Тип обработки
        
        Returns:
            Результаты обработки
        """
        results = []
        
        for item in items:
            try:
                if process_type == "sentiment":
                    result = await self.analyze_text_sentiment(item)
                elif process_type == "keywords":
                    keywords = await self.extract_keywords(item)
                    result = {"keywords": keywords}
                elif process_type == "categorize":
                    result = await self.categorize_message(item)
                else:
                    result = {"processed": item, "type": process_type}
                
                results.append({
                    "item": item,
                    "result": result,
                    "success": True
                })
                
            except Exception as e:
                results.append({
                    "item": item,
                    "result": {"error": str(e)},
                    "success": False
                })
        
        return results


# Создаем глобальный экземпляр (будет инициализирован позже)
ai_helper = None

def init_ai_helper(ai_service):
    """Инициализировать AIHelper"""
    global ai_helper
    ai_helper = AIHelper(ai_service)
    return ai_helper