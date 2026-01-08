
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict

import asyncio

class CacheManager:
    """Менеджер кэширования для AI запросов"""
    
    def __init__(self, ttl: int = 3600, max_size: int = 1000):
        self.ttl = ttl 
        self.max_size = max_size
        self.cache = {}
        self.access_times = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Получение значения из кэша"""
        if key not in self.cache:
            return None
        
        if self._is_expired(key):
            self._delete(key)
            return None
    
        self.access_times[key] = datetime.now()
        return self.cache[key]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Сохранение значения в кэш"""
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = value
        self.access_times[key] = datetime.now()
        self.ttl_values[key] = ttl or self.ttl
    
    def _is_expired(self, key: str) -> bool:
        """Проверка истекло ли время жизни"""
        if key not in self.access_times:
            return True
        
        ttl = self.ttl_values.get(key, self.ttl)
        expiration_time = self.access_times[key] + timedelta(seconds=ttl)
        return datetime.now() > expiration_time
    
    def _delete(self, key: str):
        """Удаление ключа из кэша"""
        if key in self.cache:
            del self.cache[key]
        if key in self.access_times:
            del self.access_times[key]
        if key in self.ttl_values:
            del self.ttl_values[key]
    
    def _evict_oldest(self):
        """Удаление самого старого элемента"""
        if not self.access_times:
            return
        
        oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
        self._delete(oldest_key)
    
    def clear(self):
        """Очистка всего кэша"""
        self.cache.clear()
        self.access_times.clear()
        self.ttl_values.clear()


class UserCache:
    """Кэш пользователей в памяти"""
    
    def __init__(self, ttl_minutes: int = 5):
        self._cache: Dict[int, dict] = {}
        self._lock = asyncio.Lock()
        self.ttl = timedelta(minutes=ttl_minutes)
    
    async def get(self, user_id: int) -> Optional[dict]:
        """Получить пользователя из кэша"""
        async with self._lock:
            if user_id in self._cache:
                cached = self._cache[user_id]
                if datetime.now() - cached['timestamp'] < self.ttl:
                    return cached['user']
                else:
                    del self._cache[user_id]
            return None
    
    async def set(self, user_id: int, user_data: dict):
        """Сохранить пользователя в кэш"""
        async with self._lock:
            self._cache[user_id] = {
                'user': user_data,
                'timestamp': datetime.now()
            }
    
    async def delete(self, user_id: int):
        """Удалить пользователя из кэша"""
        async with self._lock:
            self._cache.pop(user_id, None)

# Глобальный кэш
user_cache = UserCache()