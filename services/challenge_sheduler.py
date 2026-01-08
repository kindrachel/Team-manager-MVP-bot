import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import List

from aiogram import Bot
from database import get_session, User, Challenge, ChallengeStatus
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)

class ChallengeScheduler:
    """Сервис для отправки запланированных челленджей"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
    
    async def start(self):
        """Запуск планировщика"""
        if self.is_running:
            logger.warning("Планировщик уже запущен")
            return
            
        self.is_running = True
        logger.info("✅ Планировщик челленджей запущен")
        
        # Запускаем в фоновой задаче
        asyncio.create_task(self._run_scheduler())
    
    async def stop(self):
        """Остановка планировщика"""
        self.is_running = False
        logger.info("⏹️ Планировщик челленджей остановлен")
    
    async def _run_scheduler(self):
        """Основной цикл планировщика"""
        while self.is_running:
            try:
                await self._check_and_send_challenges()
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}", exc_info=True)
            
            # Проверяем каждую минуту
            await asyncio.sleep(60)
    
    async def _check_and_send_challenges(self):
        """Проверка и отправка запланированных челленджей"""
        session = get_session()
        try:
            now = datetime.now()
            current_minute = now.replace(second=0, microsecond=0)
            
            logger.debug(f"Проверка запланированных челленджей в {now.strftime('%H:%M:%S')}")
            
            # Находим челленджи, которые нужно отправить
            challenges = session.query(Challenge).filter(
                Challenge.scheduled_for.isnot(None),
                Challenge.status == ChallengeStatus.SCHEDULED.value,
                Challenge.scheduled_for <= current_minute + timedelta(minutes=1),
                Challenge.scheduled_for >= current_minute,
                Challenge.sent_at.is_(None)
            ).all()
            
            if not challenges:
                logger.debug("Нет челленджей для отправки")
                return
            
            logger.info(f"Найдено {len(challenges)} челленджей для отправки")
            
            sent_count = 0
            for challenge in challenges:
                try:
                    # Получаем пользователя
                    user = session.query(User).filter(
                        User.user_id == challenge.user_id,
                        User.chat_id.isnot(None)
                    ).first()
                    
                    if not user:
                        logger.warning(f"Пользователь {challenge.user_id} не найден")
                        challenge.status = ChallengeStatus.FAILED.value
                        session.add(challenge)
                        continue
                    
                    if not user.chat_id:
                        logger.warning(f"У пользователя {user.user_id} нет chat_id")
                        challenge.status = ChallengeStatus.FAILED.value
                        session.add(challenge)
                        continue
                    
                    # Отправляем челлендж
                    await self._send_challenge(challenge, user.chat_id)
                    
                    # Обновляем статус
                    challenge.sent_at = now
                    challenge.status = ChallengeStatus.PENDING.value
                    session.add(challenge)
                    sent_count += 1
                    
                    logger.info(f"✅ Челлендж отправлен пользователю {user.user_id}")
                    
                    # Небольшая задержка между отправками
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки челленджа {challenge.id}: {e}")
                    challenge.status = ChallengeStatus.FAILED.value
                    session.add(challenge)
            
            session.commit()
            logger.info(f"✅ Успешно отправлено {sent_count} челленджей")
            
        except Exception as e:
            logger.error(f"Ошибка проверки челленджей: {e}", exc_info=True)
            session.rollback()
        finally:
            session.close()
    
    async def _send_challenge(self, challenge: Challenge, chat_id: int):
        """Отправка одного челленджа пользователю"""
        try:
            # Определяем время дня
            time_info = {
                "morning": "🌅 УТРЕННИЙ",
                "afternoon": "☀️ ДНЕВНОЙ", 
                "evening": "🌙 ВЕЧЕРНИЙ",
                "": "🎯"
            }.get(challenge.challenge_time or "", "🎯")
            
            # Разделяем заголовок и описание
            challenge_text = challenge.text
            if '\n' in challenge_text:
                title = challenge_text.split('\n', 1)[0]
                description = challenge_text.split('\n', 1)[1]
            else:
                title = challenge_text
                description = ""
            
            # Формируем сообщение
            message_text = (
                f"{time_info} *НОВЫЙ ЧЕЛЛЕНДЖ!*\n\n"
                f"*{title}*\n\n"
            )
            
            if description:
                message_text += f"{description}\n\n"
            
            # Добавляем детали
            if challenge.difficulty:
                message_text += f"🎯 *Сложность:* {challenge.difficulty}\n"
            
            message_text += f"⭐ *Очки за выполнение:* {challenge.points}\n"
            
            if challenge.duration:
                message_text += f"⏰ *Время на выполнение:* {challenge.duration}\n"
            
            if challenge.focus_area:
                message_text += f"📌 *Фокус:* {challenge.focus_area}\n"
            
            message_text += "\nДля выполнения зайдите в меню ➡️ 📈 *Активность*"
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения для челленджа {challenge.id}: {e}")
            raise