from datetime import datetime, time, timedelta
import pytz
from typing import List, Optional, Dict, Tuple
from database import get_session
from database.models import MessageSchedule, Organization, User, MessageScheduleStatus
import logging

logger = logging.getLogger(__name__)

class ScheduleManager:
    """Менеджер расписания сообщений"""
    
    @staticmethod
    def get_organization_timezone(org_id: int) -> str:
        """Получить часовой пояс организации"""
        session = get_session()
        try:
            org = session.query(Organization).filter(Organization.id == org_id).first()
            return org.timezone if org and org.timezone else "Asia/Novosibirsk"
        finally:
            session.close()
    
    @staticmethod
    def convert_to_utc(local_time: time, timezone_str: str, date: datetime = None) -> datetime:
        """Конвертировать локальное время в UTC"""
        if date is None:
            date = datetime.now()
        
        # Создаем datetime с локальным временем
        local_dt = datetime.combine(date.date(), local_time)
        
        # Применяем часовой пояс
        local_tz = pytz.timezone(timezone_str)
        local_dt = local_tz.localize(local_dt)
        
        # Конвертируем в UTC
        utc_dt = local_dt.astimezone(pytz.UTC)
        return utc_dt
    
    @staticmethod
    def get_schedules_page(org_id: int, page: int = 0, page_size: int = 5) -> Tuple[List[MessageSchedule], int, int]:
        """Получить страницу расписаний"""
        session = get_session()
        try:
            # Общее количество
            total = session.query(MessageSchedule).filter(
                MessageSchedule.org_id == org_id
            ).count()
            
            # Рассчитываем общее количество страниц
            total_pages = (total + page_size - 1) // page_size
            
            # Получаем расписания для страницы
            schedules = session.query(MessageSchedule).filter(
                MessageSchedule.org_id == org_id
            ).order_by(
                MessageSchedule.order_index,
                MessageSchedule.scheduled_time
            ).offset(page * page_size).limit(page_size).all()
            
            return schedules, page, total_pages
        finally:
            session.close()
    
    @staticmethod
    def create_default_schedules(org_id: int):
        """Создать расписания по умолчанию для организации"""
        from services.scheduler_service import MESSAGE_TEMPLATES
        
        default_schedules = [
            {
                "title": "🎯 Приветствие",
                "content": MESSAGE_TEMPLATES.get("morning_greeting", ""),
                "scheduled_time": time(12, 30),
                "message_type": "morning_greeting",
                "order_index": 0
            },
            {
                "title": "🏟️ Напоминание о тренировке",
                "content": MESSAGE_TEMPLATES.get("training_reminder", ""),
                "scheduled_time": time(15, 30),
                "message_type": "training_reminder",
                "order_index": 1
            },
            {
                "title": "⚡ Челлендж",
                "content": MESSAGE_TEMPLATES.get("challenge_1", ""),
                "scheduled_time": time(18, 30),
                "message_type": "challenge",
                "order_index": 2
            },
            {
                "title": "📋 Выполнили ли задание?",
                "content": MESSAGE_TEMPLATES.get("evening_summary", ""),
                "scheduled_time": time(23, 30),
                "message_type": "evening_summary",
                "order_index": 3
            },
            {
                "title": "💬 Запрос обратной связи",
                "content": MESSAGE_TEMPLATES.get("feedback_request", ""),
                "scheduled_time": time(23, 59),
                "message_type": "feedback_request",
                "order_index": 4
            }
        ]
        
        session = get_session()
        try:
            for schedule_data in default_schedules:
                schedule = MessageSchedule(
                    org_id=org_id,
                    **schedule_data,
                    status=MessageScheduleStatus.ACTIVE.value,
                    is_daily=True
                )
                session.add(schedule)
            
            session.commit()
            logger.info(f"Созданы расписания по умолчанию для организации {org_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка создания расписаний: {e}")
            raise
        finally:
            session.close()
    
    @staticmethod
    def get_schedule_by_id(schedule_id: int) -> Optional[MessageSchedule]:
        """Получить расписание по ID"""
        session = get_session()
        try:
            return session.query(MessageSchedule).filter(
                MessageSchedule.id == schedule_id
            ).first()
        finally:
            session.close()
    
    @staticmethod
    def update_schedule_time(schedule_id: int, new_time: time) -> bool:
        """Обновить время расписания"""
        session = get_session()
        try:
            schedule = session.query(MessageSchedule).filter(
                MessageSchedule.id == schedule_id
            ).first()
            
            if schedule:
                schedule.scheduled_time = new_time
                schedule.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления времени: {e}")
            return False
        finally:
            session.close()
    
    @staticmethod
    def update_schedule_content(schedule_id: int, new_content: str, new_title: str = None) -> bool:
        """Обновить содержимое расписания"""
        session = get_session()
        try:
            schedule = session.query(MessageSchedule).filter(
                MessageSchedule.id == schedule_id
            ).first()
            
            if schedule:
                schedule.content = new_content
                if new_title:
                    schedule.title = new_title
                schedule.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления контента: {e}")
            return False
        finally:
            session.close()
    
    @staticmethod
    def toggle_schedule_status(schedule_id: int) -> bool:
        """Переключить статус расписания"""
        session = get_session()
        try:
            schedule = session.query(MessageSchedule).filter(
                MessageSchedule.id == schedule_id
            ).first()
            
            if schedule:
                if schedule.status == MessageScheduleStatus.ACTIVE.value:
                    schedule.status = MessageScheduleStatus.INACTIVE.value
                else:
                    schedule.status = MessageScheduleStatus.ACTIVE.value
                
                schedule.updated_at = datetime.utcnow()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка переключения статуса: {e}")
            return False
        finally:
            session.close()

    @staticmethod
    def get_next_send_time(schedule: MessageSchedule, org_timezone: str = None) -> datetime:
        """Получить следующее время отправки с учетом часового пояса"""
        if not org_timezone:
            org_timezone = ScheduleManager.get_organization_timezone(schedule.org_id)
        
        # Получаем текущее время в часовом поясе организации
        org_tz = pytz.timezone(org_timezone)
        now_org = datetime.now(pytz.UTC).astimezone(org_tz)
        
        # Создаем datetime для времени отправки
        send_time_local = schedule.scheduled_time
        send_datetime_local = org_tz.localize(datetime.combine(now_org.date(), send_time_local))
        
        # Если время уже прошло сегодня, планируем на завтра
        if send_datetime_local < now_org:
            send_datetime_local += timedelta(days=1)
        
        # Конвертируем в UTC для хранения
        return send_datetime_local.astimezone(pytz.UTC)