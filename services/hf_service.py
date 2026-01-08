import openai
import logging
from typing import Dict, Any, Optional
from config import load_config
import json
import re

logger = logging.getLogger(__name__)

class HuggingFaceService:
    """Сервис для работы с моделями через Hugging Face Inference API"""

    def __init__(self):
        self.config = load_config()
        self.is_active = True
        self.client = None
        self.quota_exceeded = False  # Флаг превышения квоты

        try:
            if not self.config.huggingface_api_key:
                logger.warning("Hugging Face API ключ не найден")
                self.is_active = False
                return

            # Используем OpenAI-совместимый клиент с Hugging Face эндпоинтом
            self.client = openai.OpenAI(
                api_key=self.config.huggingface_api_key,
                base_url="https://router.huggingface.co/v1",  # Hugging Face Router
                timeout=30.0
            )

            logger.info("✅ Hugging Face сервис инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Hugging Face: {e}")
            self.is_active = False
    
    async def generate_response(self, prompt: str, system_prompt: str = None,
                            model: str = "deepseek-ai/DeepSeek-V3.2",
                            max_tokens: int = 500,
                            temperature: float = 0.7) -> str:
        """Генерация ответа на промпт"""
        if not self.is_active or not self.client:
            return "AI сервис временно недоступен"

        # Проверяем флаг превышения квоты
        if self.quota_exceeded:
            logger.warning("Квота AI превышена, возвращаем fallback ответ")
            return "🤖 Квота AI запросов исчерпана. Попробуйте позже или обратитесь к администратору."

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=15.0  # Добавляем таймаут 15 секунд
            )

            return response.choices[0].message.content

        except openai.APIError as e:
            if hasattr(e, 'status_code') and e.status_code == 402:
                logger.warning("Квота Hugging Face API исчерпана (402 Payment Required)")
                return "Квота AI запросов исчерпана. Попробуйте позже или обратитесь к администратору."
            elif hasattr(e, 'status_code') and e.status_code == 429:
                logger.warning("Превышен лимит запросов к Hugging Face API (429)")
                return "Слишком много запросов. Попробуйте через минуту."
            else:
                logger.error(f"API ошибка Hugging Face: {e}")
                return f"Ошибка API: {str(e)[:100]}"
        except openai.Timeout as e:
            logger.error(f"Таймаут запроса к Hugging Face: {e}")
            return "Превышено время ожидания ответа от AI. Попробуйте позже."
        except Exception as e:
            logger.error(f"Ошибка генерации: {e}")
            return f"Ошибка генерации: {str(e)[:100]}"
    
    async def get_json_response(self, prompt: str, max_retries: int = 1) -> Dict:
        """Получение JSON ответа с улучшенной обработкой ошибок"""
        if not self.is_active:
            return {"error": "AI сервис недоступен"}

        # Проверяем флаг превышения квоты
        if self.quota_exceeded:
            logger.warning("Квота уже превышена, пропускаем JSON запрос")
            return {"error": "Квота AI запросов исчерпана"}

        # Формируем промпт с требованием JSON
        json_prompt = f"""{prompt}

    ВАЖНО: Твой ответ должен быть ТОЛЬКО в формате JSON.
    НЕ добавляй никакого текста кроме JSON.
    НЕ используй markdown, НЕ оборачивай в ```.
    Просто верни чистый JSON объект.

    Пример правильного ответа:
    {{"challenges": [{{"time": "morning", "title": "Название", "description": "Описание"}}]}}
    """

        for attempt in range(max_retries):
            try:
                response = await self.generate_response(
                    json_prompt,
                    system_prompt="""Ты всегда возвращаешь ТОЛЬКО JSON без дополнительного текста.
                    Твой ответ должен быть валидным JSON объектом.
                    Не используй комментарии, не добавляй лишний текст.""",
                    model="deepseek-ai/DeepSeek-V3.2",
                    max_tokens=1000,
                    temperature=0.3
                )

                logger.info(f"🔍 Получен сырой ответ (попытка {attempt + 1}): {response}")

                if not response or response.strip() == "":
                    logger.warning(f"Пустой ответ от AI (попытка {attempt + 1})")
                    continue

                cleaned_response = self._clean_json_response(response)
                logger.info(f"🔍 Очищенный ответ: {cleaned_response}")

                result = json.loads(cleaned_response)
                logger.info(f"✅ Успешно распарсен JSON")
                return result

            except json.JSONDecodeError as e:
                logger.warning(f"Попытка {attempt + 1}: Невалидный JSON: {str(e)[:100]}")
                logger.debug(f"Сырой ответ: {response[:500]}")

                if attempt < max_retries - 1:
                    try:
                        fixed_json = self._fix_json(response)
                        result = json.loads(fixed_json)
                        logger.info(f"✅ JSON исправлен и распарсен")
                        return result
                    except:
                        continue
                else:
                    return {"error": "AI вернул невалидный JSON формат", "raw_response": response[:500]}

            except Exception as e:
                logger.error(f"Попытка {attempt + 1} не удалась: {e}")
                # Проверяем, является ли ошибка связанной с квотой
                error_str = str(e).lower()
                if "402" in error_str or "payment required" in error_str or "quota" in error_str:
                    logger.warning("Квота исчерпана - прекращаем попытки")
                    self.quota_exceeded = True  # Устанавливаем флаг
                    return {"error": "Квота AI запросов исчерпана"}
                if attempt < max_retries - 1:
                    continue
                else:
                    return {"error": str(e)}

        return {"error": "Не удалось получить ответ от AI"}

    def _clean_json_response(self, response: str) -> str:
        """Очистка JSON ответа от лишнего текста"""
        response = response.strip()
        
        # Удаляем markdown обертки
        if response.startswith('```json'):
            response = response[7:-3]
        elif response.startswith('```'):
            response = response[3:-3]
        
        # Удаляем текст до первого {
        brace_pos = response.find('{')
        if brace_pos > 0:
            response = response[brace_pos:]
        
        # Удаляем текст после последнего }
        last_brace = response.rfind('}')
        if last_brace >= 0 and last_brace < len(response) - 1:
            response = response[:last_brace + 1]
        
        # Удаляем комментарии (// или /* */)
        response = re.sub(r'//.*$', '', response, flags=re.MULTILINE)
        response = re.sub(r'/\*.*?\*/', '', response, flags=re.DOTALL)
        
        return response.strip()

    def _fix_json(self, response: str) -> str:
        """Исправление распространенных ошибок в JSON"""
        try:
            # Заменяем одинарные кавычки на двойные (но не внутри текста)
            lines = []
            in_string = False
            for line in response.split('\n'):
                new_line = ''
                for char in line:
                    if char == '"':
                        in_string = not in_string
                        new_line += char
                    elif char == "'" and not in_string:
                        new_line += '"'
                    else:
                        new_line += char
                lines.append(new_line)
            response = '\n'.join(lines)
            
            # Исправляем незакрытые строки
            response = re.sub(r'(?<!\\)"(?=[^"]*$)', '"', response)
            
            # Удаляем лишние запятые
            response = re.sub(r',\s*}', '}', response)
            response = re.sub(r',\s*]', ']', response)
            
            # Исправляем незакрытые скобки
            open_braces = response.count('{')
            close_braces = response.count('}')
            if open_braces > close_braces:
                response += '}' * (open_braces - close_braces)
            
            open_brackets = response.count('[')
            close_brackets = response.count(']')
            if open_brackets > close_brackets:
                response += ']' * (open_brackets - close_brackets)
            
            return response
        except Exception as e:
            logger.error(f"Ошибка исправления JSON: {e}")
            raise
    
    async def answer_question(self, question: str, context: Dict = None) -> str:
        """Ответ на вопрос пользователя"""
        system_prompt = """Ты помощник в боте для развития команд и личного роста.
Отвечай дружелюбно, профессионально и мотивирующе.
Используй эмодзи для выразительности.
Если вопрос не по теме бота, вежливо перенаправь на релевантные функции."""
        
        context_str = ""
        if context:
            if "user_name" in context:
                context_str += f"Пользователь: {context['user_name']}\n"
            if "user_level" in context:
                context_str += f"Уровень: {context['user_level']}\n"
        
        full_prompt = f"{context_str}\n\nВопрос: {question}"
        
        return await self.generate_response(full_prompt, system_prompt)
    
    async def generate_challenge(self, direction: str, level: int = 1) -> Dict:
        """Генерация персонализированного челленджа"""
        system_prompt = f"""Ты тренер по развитию навыков. Создай полезный и выполнимый челлендж.
Направление: {direction}
Уровень сложности: {level}/10
        
Челендж должен быть:
1. Конкретным и измеримым
2. Выполнимым за 15-30 минут
3. Приносить реальную пользу
4. Иметь четкие критерии успеха"""
        
        prompt = f"""Создай персонализированный челлендж.
Формат ответа ТОЛЬКО JSON:
{{
    "text": "Текст челленджа с четкими инструкциями",
    "points": 10-50,
    "difficulty": "easy/medium/hard",
    "estimated_time": "15-30 минут",
    "success_criteria": ["критерий 1", "критерий 2"],
    "success_tips": ["Совет 1", "Совет 2"]
}}"""
        
        return await self.get_json_response(prompt, system_prompt)