# services/monthly_reports.py
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from database import get_session
from database.models import User, Challenge, Survey, Organization, ChallengeStatus

logger = logging.getLogger(__name__)

async def generate_user_monthly_report(user_id: int) -> Dict:
    """Создать месячный отчет для пользователя - ФУНКЦИЯ"""
    session = get_session()
    try:
        logger.info(f"🔍 Ищем пользователя Telegram ID: {user_id}")

        # Ищем по telegram user_id
        user = session.query(User).filter(User.user_id == user_id).first()

        if not user:
            logger.warning(f"❌ Пользователь Telegram ID {user_id} не найден в базе данных")
            return {"error": "Пользователь не найден в системе. Пожалуйста, зарегистрируйтесь или обратитесь к администратору."}
        
        print(f"✅ Найден пользователь: {user.name}")
        
        # Период: последние 30 дней
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # 1. Выполненные челленджи
        completed_challenges = session.query(Challenge).filter(
            Challenge.user_id == user.user_id,
            Challenge.status == ChallengeStatus.COMPLETED.value,
            Challenge.completed_at >= start_date,
            Challenge.completed_at <= end_date
        ).order_by(Challenge.completed_at.desc()).all()
        
        print(f"📊 Выполнено челленджей: {len(completed_challenges)}")
        
        # 2. Опросы за период
        surveys = session.query(Survey).filter(
            Survey.user_id == user.id,
            Survey.date >= start_date,
            Survey.date <= end_date
        ).all()
        
        print(f"📋 Пройдено опросов: {len(surveys)}")
        
        # 3. Простая статистика
        total_points = sum(c.points for c in completed_challenges)
        avg_energy = sum(s.energy for s in surveys) / len(surveys) if surveys else 0
        
        # 4. Рассчитываем прогресс
        days_active = len(set(s.date.date() for s in surveys)) if surveys else 0
        completion_rate = (len(completed_challenges) / 30) * 100 if completed_challenges else 0
        
        # 5. Формируем отчет для ReportFormatter (личный отчет)
        # Используем MonthlyReportService для генерации рекомендаций
        service = MonthlyReportService()
        recommendations = service._generate_simple_recommendations(
            challenges_count=len(completed_challenges),
            active_days=days_active,
            avg_energy=avg_energy
        )

        report = {
            "user_name": user.name or "Вы",
            "period": f"{start_date.strftime('%d.%m')} - {end_date.strftime('%d.%m.%Y')}",
            "stats": {
                "total_challenges": len(completed_challenges),
                "surveys_completed": len(surveys),
                "total_points": total_points,
                "avg_energy": round(avg_energy, 1),
                "active_days": days_active,
                "completion_rate": round(completion_rate, 1)
            },
            "progress": {
                "level": user.level,
                "current_points": user.points,
                "challenges_this_month": len(completed_challenges),
                "surveys_this_month": len(surveys),
                "avg_energy_trend": "стабильный" if avg_energy > 6 else "требует внимания"
            },
            "ai_analysis": {
                "executive_summary": f"{user.name}, за месяц вы выполнили {len(completed_challenges)} челленджей и заработали {total_points} очков!",
                "team_mood": "Отличное" if avg_energy > 7 else "Хорошее",
                "key_achievements": [
                    f"Выполнено {len(completed_challenges)} челленджей",
                    f"Заработано {total_points} очков",
                    f"Пройдено {len(surveys)} опросов",
                    f"Средний уровень энергии: {avg_energy:.1f}/10"
                ],
                "personal_recommendations": recommendations,
                "motivational_message": "Отличная работа за месяц! 🚀 Продолжайте развиваться!"
            }
        }
        
        print(f"✅ Отчет сгенерирован для {user.name}")
        return report
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета пользователя: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Ошибка: {str(e)[:100]}"}
    finally:
        session.close()

async def generate_trainer_monthly_report(org_id: int) -> Dict:
    """Создать месячный отчет для тренера - ФУНКЦИЯ"""
    session = get_session()
    try:
        print(f"🔍 Генерация отчета тренера для организации ID: {org_id}")
        
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            print("❌ Организация не найдена")
            return {"error": "Организация не найдена"}
        
        print(f"✅ Организация: {org.name}")
        
        # Получаем всех пользователей
        users = session.query(User).filter(User.org_id == org_id).all()
        
        if not users:
            print("❌ Нет пользователей в организации")
            return {"error": "В организации нет пользователей"}
        
        print(f"📊 Найдено пользователей: {len(users)}")
        
        # Период
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        member_reports = []
        total_challenges = 0
        
        for user in users:
            # Выполненные челленджи
            challenges = session.query(Challenge).filter(
                Challenge.user_id == user.user_id,
                Challenge.status == ChallengeStatus.COMPLETED.value,
                Challenge.completed_at >= start_date,
                Challenge.completed_at <= end_date
            ).all()
            
            surveys = session.query(Survey).filter(
                Survey.user_id == user.id,
                Survey.date >= start_date,
                Survey.date <= end_date
            ).all()
            
            user_challenges = len(challenges)
            total_challenges += user_challenges
            
            member_reports.append({
                "user_data": {
                    "name": user.name or f"Участник {user.user_id}",
                    "level": user.level,
                    "points": user.points,
                    "total_challenges": user_challenges,
                    "completed_challenges": user_challenges,
                    "completion_rate": round((user_challenges / 30) * 100, 1),
                    "recent_surveys": len(surveys),
                    "avg_energy": sum(s.energy for s in surveys) / len(surveys) if surveys else 0
                },
                "ai_analysis": {
                    "player_summary": f"Выполнил {user_challenges} челленджей за месяц",
                    "strengths": ["Активность"] if user_challenges > 0 else ["Нужна активация"],
                    "improvement_areas": ["Увеличить активность"] if user_challenges < 5 else ["Продолжать рост"],
                    "personal_recommendations": ["Ставить больше целей"],
                    "motivational_note": "Работать над развитием!"
                }
            })
        
        # Форматируем для ReportFormatter
        report = {
            "team_analysis": {
                "team_assessment": f"Команда {org.name}",
                "training_recommendations": ["Провести командный тренинг"],
                "motivation_strategies": ["Ввести систему поощрений"],
                "coach_notes": f"Всего выполнено челленджей: {total_challenges}"
            },
            "member_reports": member_reports,
            "total_members": len(users)
        }
        
        print(f"✅ Отчет тренера сгенерирован! Пользователей: {len(users)}")
        return report
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета тренера: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Ошибка: {str(e)[:100]}"}
    finally:
        session.close()

class MonthlyReportService:
    """УПРОЩЕННЫЙ сервис для генерации месячных отчетов (только данные)"""
    
    def _generate_simple_recommendations(self, challenges_count: int, active_days: int, avg_energy: float) -> List[str]:
        """Простые рекомендации без AI"""
        recommendations = []
        
        if challenges_count < 10:
            recommendations.append("Попробуйте выполнять хотя бы 1 челлендж в 3 дня")
        elif challenges_count < 20:
            recommendations.append("Хороший темп! Можно увеличить до 1 челленджа в день")
        else:
            recommendations.append("Отличная активность! Продолжайте в том же духе")
        
        if active_days < 10:
            recommendations.append("Старайтесь проходить опросы регулярнее")
        elif active_days < 20:
            recommendations.append("Хорошая регулярность опросов")
        else:
            recommendations.append("Отличная регулярность! Вы очень дисциплинированы")
        
        if avg_energy < 5:
            recommendations.append("Обратите внимание на уровень энергии, возможно нужен отдых")
        elif avg_energy < 7:
            recommendations.append("Энергия на среднем уровне")
        else:
            recommendations.append("Высокий уровень энергии! Отлично!")
        
        return recommendations
    
    def _generate_team_recommendations(self, inactive_count: int, low_performers: int, total_challenges: int) -> List[str]:
        """Простые рекомендации для команды"""
        recommendations = []
        
        if inactive_count > 0:
            recommendations.append(f"Вовлечь {inactive_count} неактивных участников")
        
        if low_performers > 0:
            recommendations.append(f"Помочь {low_performers} участникам с низкой активностью")
        
        if total_challenges < len(self._get_active_users()) * 10:
            recommendations.append("Увеличить общее количество выполняемых челленджей")
        
        recommendations.append("Поощрять регулярное прохождение опросов")
        recommendations.append("Ввести командные челленджи для повышения вовлеченности")
        
        return recommendations[:5]  # Максимум 5 рекомендаций
    
    def _get_active_users(self):
        """Вспомогательный метод для получения активных пользователей"""
        # Можно реализовать при необходимости
        return []