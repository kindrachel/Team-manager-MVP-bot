import logging
from typing import Dict, List, Optional
from datetime import datetime, time, timedelta
import asyncio
import json
import random
import traceback

from services.ai_service import AIService
from database import get_session, User, Organization, Challenge, Survey
from config import load_config

logger = logging.getLogger(__name__)

class AIChallengePlanner:
    """AI-планировщик челленджей для команд"""
    
    CHALLENGE_TIMES = {
        "morning": time(9, 0),   # 09:00 утра
        "afternoon": time(14, 0), # 14:00 дня
        "evening": time(19, 0)    # 19:00 вечера
    }
    
    CHALLENGE_POINTS = {
        "easy": {"min": 3, "max": 3},
        "medium": {"min": 3, "max": 3},
        "hard": {"min": 3, "max": 3}
    }
    
    def __init__(self):
        self.ai_service = AIService()
        logger.info("AIChallengePlanner инициализирован с Hugging Face")
    
    async def analyze_team_level(self, org_id: int) -> Dict:
        """
        Анализ уровня команды для определения сложности челленджей
        """
        session = get_session()
        try:
            users = session.query(User).filter(User.org_id == org_id).all()
            
            if not users:
                logger.warning(f"В команде {org_id} нет пользователей")
                return {"error": "В команде нет пользователей"}
            
            # Собираем статистику команды
            total_points = 0
            user_count = 0
            
            for user in users:
                if hasattr(user, 'points'):
                    total_points += user.points
                    user_count += 1
            
            avg_points = total_points / user_count if user_count > 0 else 0
            
            # Определяем уровень команды на основе средних очков
            if avg_points < 100:
                team_level = "beginner"
            elif avg_points < 300:
                team_level = "intermediate"
            else:
                team_level = "advanced"
            
            # Определяем уровень активности
            # Анализируем выполненные челленджи
            completed_challenges = 0
            total_challenges = 0
            
            for user in users:
                try:
                    user_challenges = session.query(Challenge).filter(
                        Challenge.user_id == user.id
                    ).all()
                    
                    total_challenges += len(user_challenges)
                    
                    for challenge in user_challenges:
                        if hasattr(challenge, 'status') and challenge.status == "COMPLETED":
                            completed_challenges += 1
                except Exception as e:
                    logger.warning(f"Ошибка получения челленджей для пользователя {user.id}: {e}")
                    continue
            
            completion_rate = (completed_challenges / total_challenges * 100) if total_challenges > 0 else 0
            
            if completion_rate < 30:
                activity_level = "low"
            elif completion_rate < 70:
                activity_level = "medium"
            else:
                activity_level = "high"
            
            # Fallback анализ (упрощенный, без запроса к AI)
            if team_level == "beginner":
                ai_analysis = {
                    "team_assessment": f"Новичковая команда ({len(users)} игроков)",
                    "team_level": team_level,
                    "strengths": ["Энтузиазм", "Потенциал для роста"],
                    "weaknesses": ["Недостаток опыта", "Низкая регулярность"],
                    "recommended_difficulty": "easy",
                    "training_focus": "Базовые навыки",
                    "motivational_note": "Каждый великий игрок когда-то начинал с нуля!",
                    "recommendations_for_coach": ["Сосредоточиться на основах"]
                }
            elif team_level == "intermediate":
                ai_analysis = {
                    "team_assessment": f"Средняя команда ({len(users)} игроков)",
                    "team_level": team_level,
                    "strengths": ["Стабильная активность", "Хорошие базовые навыки"],
                    "weaknesses": ["Недостаток сложных задач", "Средняя мотивация"],
                    "recommended_difficulty": "medium",
                    "training_focus": "Техническое совершенствование",
                    "motivational_note": "Вы на правильном пути!",
                    "recommendations_for_coach": ["Вводить более сложные задачи"]
                }
            else:  # advanced
                ai_analysis = {
                    "team_assessment": f"Продвинутая команда ({len(users)} игроков)",
                    "team_level": team_level,
                    "strengths": ["Высокая мотивация", "Отличные результаты"],
                    "weaknesses": ["Возможное выгорание", "Необходимость новых вызовов"],
                    "recommended_difficulty": "hard",
                    "training_focus": "Сложные тактические комбинации",
                    "motivational_note": "Вы лидеры! Продолжайте совершенствоваться!",
                    "recommendations_for_coach": ["Давать сложные специализированные задачи"]
                }
            
            # Объединяем данные
            result = {
                "team_level": team_level,
                "avg_points": round(avg_points, 2),
                "completion_rate": round(completion_rate, 2),
                "total_members": len(users),
                "analysis": ai_analysis
            }
            
            logger.info(f"Анализ команды {org_id} завершен: уровень {team_level}, сложность {ai_analysis.get('recommended_difficulty', 'medium')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка анализа команды {org_id}: {e}", exc_info=True)
            return {"error": f"Ошибка анализа: {str(e)}"}
        finally:
            session.close()
    
    async def generate_daily_challenges(self, org_id: int) -> List[Dict]:
        """Генерация 3 челленджей на день"""
        # Получаем уровень команды
        team_analysis = await self.analyze_team_level(org_id)
        
        if "error" in team_analysis:
            difficulty = "medium"
            team_level = "intermediate"
        else:
            difficulty = team_analysis["analysis"].get("recommended_difficulty", "medium")
            team_level = team_analysis["team_level"]
        
        # Упрощенный промпт для AI
        prompt = f"""Создай 3 футбольных челленджа на день.
        
    Уровень команды: {team_level}
    Сложность: {difficulty}
        
    СОЗДАЙ 3 ЧЕЛЛЕНДЖА для разных времен:
    1. УТРЕННИЙ (утренняя разминка)
    2. ДНЕВНОЙ (дневная тренировка)
    3. ВЕЧЕРНИЙ (вечернее закрепление)
        
    Каждый челлендж должен быть коротким и понятным.
        
    Верни JSON в таком формате:
    {{
    "challenges": [
    {{
    "time": "morning",
    "title": "Короткое название",
    "description": "Простое описание задания",
    "difficulty": "{difficulty}",
    "duration": "15-20 минут",
    "focus": "разминка",
    "success_criteria": "Выполнить все пункты"
    }},
    {{
    "time": "afternoon", 
    "title": "Короткое название",
    "description": "Простое описание задания",
    "difficulty": "{difficulty}",
    "duration": "15-20 минут",
    "focus": "тренировка",
    "success_criteria": "Выполнить все пункты"
    }},
    {{
    "time": "evening",
    "title": "Короткое название",
    "description": "Простое описание задания",
    "difficulty": "{difficulty}",
    "duration": "15-20 минут",
    "focus": "закрепление",
    "success_criteria": "Выполнить все пункты"
    }}
    ]
    }}"""
        
        try:
            logger.info(f"Запрос AI для генерации челленджей")
            
            response = await self.ai_service.get_json_response(prompt)
            
            if "error" in response:
                logger.error(f"Ошибка AI: {response['error']}")
                return self._get_fallback_challenges(difficulty)
            
            challenges = response.get("challenges", [])
            
            if not challenges:
                logger.warning("AI не вернул челленджи")
                return self._get_fallback_challenges(difficulty)
            
            # Добавляем очки в зависимости от сложности
            points_config = self.CHALLENGE_POINTS.get(difficulty, self.CHALLENGE_POINTS["medium"])
            
            for challenge in challenges:
                challenge["points"] = random.randint(points_config["min"], points_config["max"])
                challenge["generated_at"] = datetime.now().isoformat()
                challenge["team_level"] = team_level
            
            logger.info(f"✅ Сгенерировано {len(challenges)} челленджей")
            return challenges
            
        except Exception as e:
            logger.error(f"Ошибка генерации челленджей: {e}")
            return self._get_fallback_challenges(difficulty)
    
    def _get_fallback_challenges(self, difficulty: str) -> List[Dict]:
        """Fallback челленджи если AI недоступен"""
        import random  # Локальный импорт для fallback
        
        challenges = {
            "easy": [
                {
                    "time": "morning",
                    "title": "Утренняя зарядка",
                    "description": "Сделайте 20 приседаний и 10 отжиманий",
                    "difficulty": "easy",
                    "points": random.randint(10, 20),
                    "duration": "10 минут",
                    "focus": "разминка",
                    "success_criteria": "Выполнить все упражнения",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "beginner"
                },
                {
                    "time": "afternoon", 
                    "title": "Работа с мячом",
                    "description": "Прокатите мяч вокруг конусов 10 раз",
                    "difficulty": "easy",
                    "points": random.randint(10, 20),
                    "duration": "15 минут",
                    "focus": "техника",
                    "success_criteria": "Завершить 10 кругов",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "beginner"
                },
                {
                    "time": "evening",
                    "title": "Растяжка",
                    "description": "Выполните 5 минут растяжки основных групп мышц",
                    "difficulty": "easy",
                    "points": random.randint(10, 20),
                    "duration": "5 минут",
                    "focus": "восстановление",
                    "success_criteria": "Завершить растяжку всех групп мышц",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "beginner"
                }
            ],
            "medium": [
                {
                    "time": "morning",
                    "title": "Интервальная разминка",
                    "description": "30 секунд высокого темпа, 30 секунд отдыха - 5 циклов",
                    "difficulty": "medium",
                    "points": random.randint(20, 35),
                    "duration": "15 минут",
                    "focus": "выносливость",
                    "success_criteria": "Завершить все 5 циклов",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "intermediate"
                },
                {
                    "time": "afternoon",
                    "title": "Точность паса",
                    "description": "Сделайте 20 точных пасов в цель с 10 метров",
                    "difficulty": "medium",
                    "points": random.randint(20, 35),
                    "duration": "20 минут",
                    "focus": "техника",
                    "success_criteria": "Выполнить 20 точных пасов",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "intermediate"
                },
                {
                    "time": "evening",
                    "title": "Силовая подготовка",
                    "description": "3 подхода по 10 приседаний с собственным весом",
                    "difficulty": "medium",
                    "points": random.randint(20, 35),
                    "duration": "15 минут",
                    "focus": "сила",
                    "success_criteria": "Завершить все 3 подхода",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "intermediate"
                }
            ],
            "hard": [
                {
                    "time": "morning",
                    "title": "Кардио-разминка",
                    "description": "Бег на месте 5 минут + 20 бёрпи",
                    "difficulty": "hard",
                    "points": random.randint(30, 50),
                    "duration": "20 минут",
                    "focus": "кардио",
                    "success_criteria": "Завершить все упражнения",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "advanced"
                },
                {
                    "time": "afternoon",
                    "title": "Тактическое упражнение",
                    "description": "Отработайте комбинацию из 3-х пасов с партнером",
                    "difficulty": "hard",
                    "points": random.randint(30, 50),
                    "duration": "25 минут",
                    "focus": "тактика",
                    "success_criteria": "Отработать комбинацию 10 раз",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "advanced"
                },
                {
                    "time": "evening",
                    "title": "Интенсивная растяжка",
                    "description": "Глубокая растяжка всех групп мышц по 1 минуте на каждую",
                    "difficulty": "hard",
                    "points": random.randint(30, 50),
                    "duration": "20 минут",
                    "focus": "гибкость",
                    "success_criteria": "Выполнить растяжку всех основных групп мышц",
                    "generated_at": datetime.now().isoformat(),
                    "team_level": "advanced"
                }
            ]
        }
        
        return challenges.get(difficulty, challenges["medium"])
        
    
    async def schedule_team_challenges(self, org_id: int):
        """Планирование отправки челленджей команде"""
        # Генерируем челленджи на день
        challenges = await self.generate_daily_challenges(org_id)
        
        if not challenges:
            logger.warning(f"Не удалось сгенерировать челленджи для команды {org_id}")
            return
        
        # Сохраняем в БД для отправки по расписанию
        session = get_session()
        try:
            org = session.query(Organization).filter(Organization.id == org_id).first()
            
            for challenge_data in challenges:
                # Создаем запись в БД
                team_challenge = Challenge(
                    org_id=org_id,
                    title=challenge_data["title"],
                    description=challenge_data["description"],
                    difficulty=challenge_data["difficulty"],
                    points=challenge_data["points"],
                    duration=challenge_data["duration"],
                    focus=challenge_data["focus"],
                    challenge_time=challenge_data["time"],
                    scheduled_for=datetime.now().date(),
                    ai_generated=True,
                    status="SCHEDULED"
                )
                session.add(team_challenge)
            
            session.commit()
            logger.info(f"Создано {len(challenges)} челленджей для команды {org.name}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения челленджей: {e}")
            session.rollback()
        finally:
            session.close()