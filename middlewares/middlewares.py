
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from aiogram.fsm.context import FSMContext
from utils.cache import UserCache, user_cache
import logging


logger = logging.getLogger(__name__)

class ClearStateMiddleware(BaseMiddleware):
    """Мидлварь для очистки состояния при определенных callback данных"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, CallbackQuery):
            clear_triggers = [
                'back_to_profile', 
                'back_button_to_profile', 
                'back_from_photo_change',
                'back_to_menu',
                'back_to_activity',
                'back_to_vacansies',
                'back_to_admin_panel',
                'cancel_photo_change'
            ]
            
            if event.data in clear_triggers:
                state: FSMContext = data.get('state')
                if state:
                    current_state = await state.get_state()
                    if current_state:
                        await state.clear()
                        logger.debug(f"Состояние очищено для callback: {event.data}")
        
        return await handler(event, data)


class AutoRegisterUserMiddleware(BaseMiddleware):
    """Автоматическая регистрация пользователя при первом взаимодействии"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        from database import get_session, User, UserRole
        
        user_id = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        if user_id:
            session = get_session()
            try:
                user = session.query(User).filter(User.user_id == user_id).first()
                if not user:
                    from_user = event.from_user
                    user = User(
                        user_id=user_id,
                        name=f"{from_user.first_name or ''} {from_user.last_name or ''}".strip() or f"User_{user_id}",
                        username=from_user.username or f"user_{user_id}",
                        role=UserRole.MEMBER.value,
                        points=0,
                        level=1
                    )
                    session.add(user)
                    session.commit()
                    logger.info(f"Auto-registered user {user_id}")
            except Exception as e:
                logger.error(f"Error in AutoRegisterUserMiddleware: {e}")
                session.rollback()
            finally:
                session.close()
        
        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """Логирование всех событий"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            logger.info(f"Message: {event.text} from {event.from_user.id} ({event.from_user.username})")
        elif isinstance(event, CallbackQuery):
            logger.info(f"Callback: {event.data} from {event.from_user.id} ({event.from_user.username})")
        
        return await handler(event, data)


class AntiFloodMiddleware(BaseMiddleware):
    """Защита от флуда"""
    
    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.last_time = {}
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        import asyncio
        from datetime import datetime
        
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        if user_id:
            current_time = datetime.now().timestamp()
            last_time = self.last_time.get(user_id, 0)
            
            if current_time - last_time < self.delay:
                logger.warning(f"Flood detected from user {user_id}")
                return
            
            self.last_time[user_id] = current_time
        
        return await handler(event, data)


class DatabaseSessionMiddleware(BaseMiddleware):
    """Мидлварь для управления сессиями БД"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        from database import get_session
        
        session = get_session()
        data['session'] = session
        
        try:
            result = await handler(event, data)
        finally:
            session.close()
        
        return result
    
class CacheMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Добавляем кэш в данные
        data['user_cache'] = user_cache
        return await handler(event, data)
