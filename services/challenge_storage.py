import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import and_, or_
from database import get_session, PendingChallenge

logger = logging.getLogger(__name__)


class ChallengeStorageService:
    """Сервис для работы с временным хранилищем челленджей"""
    
    def __init__(self, default_ttl_hours: int = 24):
        """
        Args:
            default_ttl_hours: Время жизни данных в часах (по умолчанию 24 часа)
        """
        self.default_ttl_hours = default_ttl_hours
    
    async def save_challenges(
        self,
        user_id: int,
        chat_id: int,
        org_id: int,
        challenges: List[Dict[str, Any]],
        ttl_hours: Optional[int] = None
    ) -> int:
        """
        Сохранить сгенерированные челленджи
        """
        session = get_session()
        try:
            # Очищаем старые записи этого пользователя
            self._cleanup_user_entries(session, user_id)
            
            # Рассчитываем время жизни с часовым поясом
            ttl = ttl_hours or self.default_ttl_hours
            expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)  # ✅ aware datetime
            
            # Создаем новую запись
            pending = PendingChallenge(
                user_id=user_id,
                chat_id=chat_id,
                org_id=org_id,
                challenges=challenges,
                expires_at=expires_at,  # ✅ уже с часовым поясом
                status="PENDING"
            )
            
            session.add(pending)
            session.commit()
            
            logger.info(
                f"Сохранены челленджи для user_id={user_id}, "
                f"org_id={org_id}, count={len(challenges)}"
            )
            
            return pending.id
                
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка сохранения челленджей: {e}")
            raise
        finally:
            session.close()
    
    async def get_challenges(
        self,
        user_id: int,
        include_expired: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Получить сохраненные челленджи пользователя
        """
        session = get_session()
        try:
            query = session.query(PendingChallenge).filter(
                PendingChallenge.user_id == user_id,
                PendingChallenge.status == "PENDING"
            )
            
            if not include_expired:
                now_utc = datetime.now(timezone.utc)
                query = query.filter(
                    PendingChallenge.expires_at > now_utc
                )
            
            pending = query.order_by(PendingChallenge.created_at.desc()).first()
            
            if not pending:
                return None
            
            def check_expired(pending_challenge):
                """Безопасная проверка истечения срока"""
                try:
                    now_utc = datetime.now(timezone.utc)
                    
                    if pending_challenge.expires_at.tzinfo is None:
                        expires_utc = pending_challenge.expires_at.replace(tzinfo=timezone.utc)
                    else:
                        expires_utc = pending_challenge.expires_at.astimezone(timezone.utc)
                    
                    return now_utc > expires_utc
                except Exception as e:
                    logger.warning(f"Ошибка проверки срока: {e}")
                    return False 

            if check_expired(pending):
                pending.status = "EXPIRED"
                session.commit()
                return None
            
            try:
                now_utc = datetime.now(timezone.utc)
                
                if pending.expires_at.tzinfo is None:
                    expires_utc = pending.expires_at.replace(tzinfo=timezone.utc)
                else:
                    expires_utc = pending.expires_at.astimezone(timezone.utc)
                
                expires_in = (expires_utc - now_utc).total_seconds() / 3600
            except:
                expires_in = 0
            
            return {
                "id": pending.id,
                "org_id": pending.org_id,
                "chat_id": pending.chat_id,
                "challenges": pending.challenges,
                "created_at": pending.created_at,
                "expires_at": pending.expires_at,
                "expires_in": expires_in
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения челленджей: {e}")
            return None
        finally:
            session.close()
    
    async def update_status(
        self,
        record_id: int,
        status: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Обновить статус записи
        
        Args:
            record_id: ID записи
            status: Новый статус
            metadata: Дополнительные данные
        
        Returns:
            Успешно ли обновлено
        """
        session = get_session()
        try:
            pending = session.query(PendingChallenge).filter(
                PendingChallenge.id == record_id
            ).first()
            
            if not pending:
                logger.warning(f"Запись {record_id} не найдена")
                return False
            
            pending.status = status
            
            if metadata:
                current_challenges = pending.challenges
                if current_challenges and isinstance(current_challenges, list):
                    for i, challenge in enumerate(current_challenges):
                        if i < len(metadata.get("updates", [])):
                            current_challenges[i].update(metadata["updates"][i])
                    pending.challenges = current_challenges
            
            session.commit()
            logger.info(f"Обновлен статус записи {record_id} на {status}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления статуса: {e}")
            return False
        finally:
            session.close()
    
    async def delete_challenges(self, user_id: int) -> bool:
        """
        Удалить все челленджи пользователя
        
        Args:
            user_id: ID пользователя
        
        Returns:
            Успешно ли удалено
        """
        session = get_session()
        try:
            deleted_count = session.query(PendingChallenge).filter(
                PendingChallenge.user_id == user_id
            ).delete()
            
            session.commit()
            logger.info(f"Удалено {deleted_count} записей для user_id={user_id}")
            return deleted_count > 0
            
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления челленджей: {e}")
            return False
        finally:
            session.close()
    
    async def cleanup_expired(self) -> int:
        """
        Очистка просроченных записей
        """
        session = get_session()
        try:
            # Используем aware datetime для сравнения
            now_utc = datetime.now(timezone.utc)
            
            expired_count = session.query(PendingChallenge).filter(
                PendingChallenge.expires_at <= now_utc
            ).delete()
            
            session.commit()
            
            if expired_count > 0:
                logger.info(f"Очищено {expired_count} просроченных записей")
            
            return expired_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка очистки просроченных записей: {e}")
            return 0
        finally:
            session.close()
    
    def _cleanup_user_entries(self, session, user_id: int):
        """Очистить старые записи пользователя"""
        try:
            # Удаляем старые записи этого пользователя
            session.query(PendingChallenge).filter(
                PendingChallenge.user_id == user_id,
                PendingChallenge.status == "PENDING"
            ).delete()
            
            session.flush()
        except Exception as e:
            logger.warning(f"Ошибка очистки старых записей: {e}")
            session.rollback()
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику хранилища"""
        session = get_session()
        try:
            total = session.query(PendingChallenge).count()
            pending = session.query(PendingChallenge).filter(
                PendingChallenge.status == "PENDING"
            ).count()
            
            expired = session.query(PendingChallenge).filter(
                PendingChallenge.expires_at <= datetime.now(timezone.utc)
            ).count()
            
            # Самые старые записи
            oldest = session.query(PendingChallenge).filter(
                PendingChallenge.status == "PENDING"
            ).order_by(PendingChallenge.created_at.asc()).first()
            
            return {
                "total_records": total,
                "pending": pending,
                "expired": expired,
                "oldest_record_age": (
                    (datetime.now(timezone.utc) - oldest.created_at).total_seconds() / 3600
                    if oldest else 0
                )
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}
        finally:
            session.close()



challenge_storage = ChallengeStorageService()