# services/reminder_service.py
import logging
from datetime import datetime, timedelta
from typing import List

from database import get_session
from database.models import Challenge, User, ChallengeStatus, Organization
from utils.time import get_current_org_time, get_org_timezone

logger = logging.getLogger(__name__)

class SimpleReminderService:
    """ПРОСТОЙ сервис напоминаний о невыполненных челленджах"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active = True
    
    async def send_daily_reminders(self):
        """Отправляем напоминания всем организациям"""
        logger.info("🔔 Запуск простых напоминаний о челленджах")
        
        session = get_session()
        try:
            # Получаем все организации
            organizations = session.query(Organization).all()
            
            for org in organizations:
                try:
                    await self._check_and_send_for_org(org)
                except Exception as e:
                    logger.error(f"❌ Ошибка для организации {org.name}: {e}")
                    continue
            
            logger.info("✅ Напоминания отправлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки напоминаний: {e}")
        finally:
            session.close()
    
    async def _check_and_send_for_org(self, org: Organization):
        """Проверяем и отправляем напоминания для одной организации"""
        if not org.timezone:
            return
        
        # Получаем время организации из твоего time.py
        try:
            org_time = get_current_org_time(org.id)
        except:
            return
        
        # Отправляем в 18:00 по местному времени (просто вечером)
        if org_time.hour != 18:
            return
        
        session = get_session()
        try:
            # Получаем пользователей с невыполненными челленджами
            users = self._get_users_with_pending_challenges(org.id)
            
            logger.info(f"📋 Организация {org.name}: {len(users)} пользователей с челленджами")
            
            for user in users:
                try:
                    await self._send_simple_reminder(user)
                    # Пауза между сообщениями
                    import asyncio
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"❌ Не удалось отправить пользователю {user.get('user_id')}: {e}")
                    continue
                    
        finally:
            session.close()
    
    def _get_users_with_pending_challenges(self, org_id: int) -> List[dict]:
        """Получаем пользователей с невыполненными челленджами"""
        session = get_session()
        try:
            # Простой запрос - находим пользователей с активными челленджами
            users = session.query(User).filter(
                User.org_id == org_id,
                User.chat_id.isnot(None),
                User.is_active == True
            ).all()
            
            result = []
            
            for user in users:
                # Считаем активные челленджи для пользователя
                challenge_count = session.query(Challenge).filter(
                    Challenge.user_id == user.user_id,
                    Challenge.status.in_([ChallengeStatus.PENDING.value, ChallengeStatus.ACTIVE.value])
                ).count()
                
                if challenge_count > 0:
                    # Получаем первые 3 челленджа для примера
                    challenges = session.query(Challenge).filter(
                        Challenge.user_id == user.user_id,
                        Challenge.status.in_([ChallengeStatus.PENDING.value, ChallengeStatus.ACTIVE.value])
                    ).order_by(Challenge.created_at.desc()).limit(3).all()
                    
                    result.append({
                        'user_id': user.user_id,
                        'name': user.name,
                        'chat_id': user.chat_id,
                        'challenge_count': challenge_count,
                        'challenges': [challenge.text for challenge in challenges]
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователей: {e}")
            return []
        finally:
            session.close()
    
    async def _send_simple_reminder(self, user_data: dict):
        """Отправляем ПРОСТОЕ напоминание без кнопок"""
        try:
            chat_id = user_data['chat_id']
            name = user_data['name'] or "друг"
            count = user_data['challenge_count']
            challenges = user_data['challenges']
            
            # Самое простое сообщение
            message = f"👋 {name}, привет!\n\n"
            
            if count == 1:
                message += "У тебя есть 1 невыполненный челлендж:\n"
            else:
                message += f"У тебя есть {count} невыполненных челленджа:\n"
            
            # Добавляем примеры (максимум 3)
            for i, challenge_text in enumerate(challenges[:3], 1):
                short_text = challenge_text[:50] + "..." if len(challenge_text) > 50 else challenge_text
                message += f"{i}. {short_text}\n"
            
            message += "\n🎯 Проверь в разделе 'Активность'"
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=message
            )
            
            logger.info(f"📨 Напоминание отправлено пользователю {user_data['user_id']}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            raise