from aiogram import Bot
import asyncio
import logging
from datetime import datetime, time, timedelta
import pytz
from typing import Dict, List, Set, Tuple
import hashlib

from database import get_session
from database.models import MessageSchedule, User, Organization, MessageScheduleStatus, MessageSentLog

logger = logging.getLogger(__name__)

class TimezoneMessageScheduler:
    """Планировщик сообщений с учетом часового пояса организации"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
        self.last_check_date = None
        logger.info("✅ TimezoneMessageScheduler инициализирован")
    
    async def start(self):
        """Запуск планировщика"""
        self.is_running = True
        logger.info("🚀 Планировщик сообщений (с учетом часового пояса) запущен")
        
        while self.is_running:
            try:
                # Получаем текущее время с часовым поясом UTC
                current_utc = datetime.now(pytz.UTC)
                
                # Проверяем, наступил ли новый день
                await self._check_new_day(current_utc)
                
                # Проверяем и отправляем сообщения
                await self._check_and_send_messages(current_utc)
                
                # Ждем 60 секунд
                await asyncio.sleep(60)
                    
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def stop(self):
        """Остановка планировщика"""
        self.is_running = False
        logger.info("⏹️ Планировщик остановлен")
    
    async def _check_new_day(self, current_utc: datetime):
        """Проверяем, наступил ли новый день"""
        if self.last_check_date is None or self.last_check_date.date() != current_utc.date():
            self.last_check_date = current_utc
            logger.info(f"🗓️ Новый день: {current_utc.date()}")
    
    async def _check_and_send_messages(self, current_utc: datetime):
        """Проверка времени и отправка сообщений с учетом часового пояса"""
        session = get_session()
        try:
            # Убедимся, что current_utc осведомленный
            if current_utc.tzinfo is None:
                current_utc_aware = current_utc.replace(tzinfo=pytz.UTC)
            else:
                current_utc_aware = current_utc
            
            # Получаем все активные расписания
            schedules = session.query(MessageSchedule).filter(
                MessageSchedule.status == MessageScheduleStatus.ACTIVE.value
            ).all()
            
            if not schedules:
                return
            
            logger.debug(f"Проверяю {len(schedules)} активных расписаний")
            
            for schedule in schedules:
                try:
                    # Получаем организацию для часового пояса
                    org = session.query(Organization).filter(
                        Organization.id == schedule.org_id
                    ).first()
                    
                    if not org:
                        continue
                    
                    # Получаем часовой пояс организации
                    org_timezone = org.timezone if org.timezone else "Asia/Novosibirsk"
                    
                    # Получаем текущее время в часовом поясе организации
                    try:
                        org_tz = pytz.timezone(org_timezone)
                        current_org_time = current_utc_aware.astimezone(org_tz)
                    except pytz.exceptions.UnknownTimeZoneError:
                        logger.error(f"Неизвестный часовой пояс: {org_timezone}, использую Asia/Novosibirsk")
                        org_tz = pytz.timezone("Asia/Novosibirsk")
                        current_org_time = current_utc_aware.astimezone(org_tz)
                        org_timezone = "Asia/Novosibirsk"
                    
                    # Проверяем, нужно ли отправлять сообщение
                    should_send = await self._should_send_schedule(
                        schedule, 
                        current_utc_aware, 
                        current_org_time, 
                        org_tz
                    )
                    
                    if should_send:
                        logger.info(
                            f"⏰ ВРЕМЯ ОТПРАВКИ! Организация: {org.name} ({org_timezone})\n"
                            f"   Сообщение: {schedule.title}\n"
                            f"   Время по расписания: {schedule.scheduled_time.strftime('%H:%M')}\n"
                            f"   Текущее время организации: {current_org_time.strftime('%H:%M')}"
                        )
                        
                        # Отправляем сообщение
                        sent_count = await self._send_scheduled_message(schedule, org, current_utc_aware)
                        
                        if sent_count > 0:
                            logger.info(f"✅ Сообщение '{schedule.title}' отправлено {sent_count} пользователям")
                        else:
                            logger.warning(f"⚠️ Сообщение '{schedule.title}' не отправлено никому")
                            
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки расписания {schedule.id}: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка проверки расписания: {e}", exc_info=True)
        finally:
            session.close()
    
    async def _should_send_schedule(
        self, 
        schedule: MessageSchedule, 
        current_utc: datetime,
        current_org_time: datetime,
        org_tz: pytz.BaseTzInfo
    ) -> bool:
        """Проверить, нужно ли отправлять сообщение по расписанию"""
        session = get_session()
        try:
            # Проверяем по времени
            schedule_time = schedule.scheduled_time
            
            # Создаем datetime для времени расписания на текущий день в часовом поясе организации
            schedule_datetime_local = org_tz.localize(
                datetime.combine(current_org_time.date(), schedule_time)
            )
            
            # Конвертируем в UTC для сравнения
            schedule_datetime_utc = schedule_datetime_local.astimezone(pytz.UTC)
            
            # Убеждаемся, что current_utc также осведомленный (aware)
            if current_utc.tzinfo is None:
                current_utc_aware = current_utc.replace(tzinfo=pytz.UTC)
            else:
                current_utc_aware = current_utc
            
            # Проверяем, находится ли текущее время в пределах +-5 минут от времени отправки
            time_diff = abs((current_utc_aware - schedule_datetime_utc).total_seconds())
            
            if time_diff > 300:  # 5 минут
                return False
            
            # Проверяем, не отправлялось ли уже сегодня это сообщение
            # Ищем запись в логах за сегодня
            today_start_utc = current_utc_aware.replace(hour=0, minute=0, second=0, microsecond=0)
            
            existing_log = session.query(MessageSentLog).filter(
                MessageSentLog.schedule_id == schedule.id,
                MessageSentLog.sent_at >= today_start_utc
            ).first()
            
            if existing_log:
                logger.debug(f"Сообщение {schedule.id} уже отправлено сегодня в {existing_log.sent_at}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки отправки: {e}", exc_info=True)
            return False
        finally:
            session.close()
    
    async def _send_scheduled_message(
        self, 
        schedule: MessageSchedule, 
        org: Organization,
        sent_time: datetime
    ) -> int:
        """Отправить запланированное сообщение"""
        session = get_session()
        sent_count = 0
        
        try:
            # Получаем пользователей организации
            users = session.query(User).filter(
                User.org_id == org.id,
                User.chat_id.isnot(None)
            ).all()
            
            if not users:
                logger.warning(f"❌ Нет пользователей в организации {org.id} ({org.name})")
                return 0
            
            logger.info(f"📤 Отправка сообщения '{schedule.title}' для организации {org.name} ({len(users)} пользователей)")
            
            for user in users:
                try:
                    await self.bot.send_message(
                        chat_id=user.chat_id,
                        text=f"{schedule.title}\n\n{schedule.content}"
                    )
                    
                    # Логируем отправку
                    log_entry = MessageSentLog(
                        schedule_id=schedule.id,
                        user_id=user.id,
                        sent_at=sent_time,
                        status="sent"
                    )
                    session.add(log_entry)
                    
                    sent_count += 1
                    
                    # Небольшая задержка, чтобы не превышать лимиты Telegram
                    if sent_count % 20 == 0:
                        await asyncio.sleep(1)
                    elif sent_count % 5 == 0:
                        await asyncio.sleep(0.2)
                        
                except Exception as e:
                    error_msg = str(e).lower()
                    log_entry = MessageSentLog(
                        schedule_id=schedule.id,
                        user_id=user.id,
                        sent_at=sent_time,
                        status="failed",
                        error_message=str(e)[:500]
                    )
                    session.add(log_entry)
                    
                    if "chat not found" in error_msg or "user is deactivated" in error_msg:
                        logger.warning(f"Пользователь {user.user_id} недоступен (org: {org.id})")
                    elif "bot was blocked" in error_msg:
                        logger.warning(f"Бот заблокирован пользователем {user.user_id}")
                    else:
                        logger.warning(f"Ошибка отправки пользователю {user.user_id}: {e}")
            
            session.commit()
            return sent_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Ошибка отправки сообщения {schedule.id}: {e}")
            return 0
        finally:
            session.close()
    
    async def send_test_with_timezone(self, schedule_id: int, test_chat_id: int) -> str:
        """Отправить тестовое сообщение с информацией о часовом поясе"""
        try:
            session = get_session()
            schedule = session.query(MessageSchedule).filter(
                MessageSchedule.id == schedule_id
            ).first()
            
            if not schedule:
                return "❌ Расписание не найдено"
            
            org = session.query(Organization).filter(
                Organization.id == schedule.org_id
            ).first()
            
            if not org:
                return "❌ Организация не найдена"
            
            org_timezone = org.timezone if org.timezone else "Asia/Novosibirsk"
            
            # Получаем текущее время
            current_utc = datetime.utcnow()
            try:
                org_tz = pytz.timezone(org_timezone)
                current_org_time = current_utc.replace(tzinfo=pytz.UTC).astimezone(org_tz)
                org_time_str = current_org_time.strftime('%H:%M:%S')
                
                # Рассчитываем время следующей отправки
                schedule_time = schedule.scheduled_time
                schedule_datetime_local = org_tz.localize(
                    datetime.combine(current_org_time.date(), schedule_time)
                )
                
                # Если время уже прошло сегодня, показываем завтра
                if schedule_datetime_local < current_org_time:
                    schedule_datetime_local += timedelta(days=1)
                
                next_send_str = schedule_datetime_local.strftime('%d.%m.%Y %H:%M')
                next_send_utc = schedule_datetime_local.astimezone(pytz.UTC).strftime('%d.%m.%Y %H:%M UTC')
                
            except Exception as tz_error:
                org_time_str = f"ошибка: {tz_error}"
                next_send_str = "не определено"
                next_send_utc = "не определено"
            
            test_message = (
                f"🔄 ТЕСТОВОЕ СООБЩЕНИЕ С ЧАСОВЫМ ПОЯСОМ\n\n"
                f"📝 {schedule.title}\n"
                f"⏰ Запланировано на: {schedule.scheduled_time.strftime('%H:%M')}\n"
                f"🏢 Организация: {org.name}\n"
                f"🌍 Часовой пояс: {org_timezone}\n"
                f"🕐 Текущее время ({org_timezone}): {org_time_str}\n"
                f"🕐 Текущее время UTC: {current_utc.strftime('%H:%M:%S')}\n"
                f"📅 Следующая отправка: {next_send_str} ({next_send_utc})\n\n"
                f"{schedule.content[:300]}..."
            )
            
            await self.bot.send_message(
                chat_id=test_chat_id,
                text=test_message
            )
            
            return f"✅ Тестовое сообщение отправлено. Часовой пояс: {org_timezone}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки тестового сообщения: {e}")
            return f"❌ Ошибка: {str(e)}"
        finally:
            if 'session' in locals():
                session.close()