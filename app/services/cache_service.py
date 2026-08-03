# app/services/cache_service.py
import json
import logging
import pickle
from typing import Optional, Any
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self):
        self.redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        self.default_ttl = 300
        self._client = None
        self._available = False  # Флаг доступности Redis
    
    async def get_client(self) -> Optional[aioredis.Redis]:
        """Получение клиента Redis с поддержкой RESP2 протокола"""
        if self._client is None:
            try:
                # Явно указываем RESP2 протокол для совместимости со старыми версиями Redis
                self._client = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False,
                    protocol=2,  # ← RESP2 протокол (решает проблему с HELLO)
                    socket_connect_timeout=3,
                    socket_timeout=3,
                    retry_on_timeout=True,
                    max_connections=10
                )
                # Проверяем подключение
                await self._client.ping()
                self._available = True
                logger.info(f"✅ Redis connected to {self.redis_url} (RESP2)")
            except Exception as e:
                self._client = None
                self._available = False
                logger.warning(f"⚠️ Redis unavailable: {str(e)}. Cache will be disabled.")
        return self._client if self._available else None
    
    async def get(self, key: str) -> Optional[Any]:
        """Получение данных из кэша с graceful fallback"""
        if not self._available:
            return None
        
        try:
            client = await self.get_client()
            if client is None:
                return None
            data = await client.get(key)
            if data:
                return pickle.loads(data)
            return None
        except Exception as e:
            logger.debug(f"Redis get error for key {key}: {str(e)}")
            self._available = False
            return None
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """Сохранение данных в кэш с graceful fallback"""
        if not self._available:
            return False
        
        try:
            client = await self.get_client()
            if client is None:
                return False
            ttl = ttl or self.default_ttl
            
            serialized = pickle.dumps(value)
            await client.setex(key, ttl, serialized)
            logger.debug(f"✅ Cached: {key} (TTL: {ttl}s, size: {len(serialized)} bytes)")
            return True
        except Exception as e:
            logger.debug(f"Redis set error for key {key}: {str(e)}")
            self._available = False
            return False
    
    async def delete(self, key: str) -> bool:
        """Удаление данных из кэша"""
        if not self._available:
            return False
        
        try:
            client = await self.get_client()
            if client is None:
                return False
            await client.delete(key)
            logger.debug(f"🗑️ Deleted cache key: {key}")
            return True
        except Exception as e:
            logger.debug(f"Redis delete error: {str(e)}")
            return False
    
    async def delete_pattern(self, pattern: str) -> bool:
        """Удаление данных по шаблону"""
        if not self._available:
            return False
        
        try:
            client = await self.get_client()
            if client is None:
                return False
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
                logger.info(f"🗑️ Deleted {len(keys)} cache keys by pattern: {pattern}")
            return True
        except Exception as e:
            logger.debug(f"Redis delete_pattern error: {str(e)}")
            return False
    
    async def clear_all(self) -> bool:
        """Очистка всего кэша"""
        if not self._available:
            return False
        
        try:
            client = await self.get_client()
            if client is None:
                return False
            await client.flushdb()
            logger.info("🗑️ All cache cleared")
            return True
        except Exception as e:
            logger.debug(f"Redis clear_all error: {str(e)}")
            return False
    
    def generate_key(self, *parts: str) -> str:
        """Генерация ключа для кэша"""
        return ":".join(parts)


cache_service = CacheService()


def cached(ttl: int = 300, key_prefix: str = None):
    """
    Декоратор для кэширования результатов функций.
    Использует pickle для сериализации, поддерживает любые Python объекты.
    
    Теперь правильно обрабатывает:
    - position arguments (args) - для path parameters
    - keyword arguments (kwargs) - для query parameters
    - Исключает большие объекты (db, request, response)
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                # Получаем имена параметров функции
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                
                # Формируем ключ кэша из всех аргументов
                # Исключаем зависимости, которые не должны влиять на кэш
                exclude_params = {'db', 'current_user', 'request', 'response', 'session'}
                
                # Собираем все аргументы в один словарь
                all_args = {}
                
                # Добавляем позиционные аргументы
                for i, value in enumerate(args):
                    if i < len(param_names):
                        param_name = param_names[i]
                        # Пропускаем исключенные параметры
                        if param_name not in exclude_params:
                            all_args[param_name] = value
                
                # Добавляем именованные аргументы
                for key, value in kwargs.items():
                    if key not in exclude_params:
                        all_args[key] = value
                
                # Формируем ключ
                cache_key = key_prefix or func.__name__
                
                # Добавляем параметры в ключ
                if all_args:
                    # Сортируем для стабильности
                    param_parts = []
                    for k, v in sorted(all_args.items()):
                        # Пропускаем None значения
                        if v is None:
                            continue
                        # Безопасное преобразование в строку
                        try:
                            param_parts.append(f"{k}={v}")
                        except:
                            param_parts.append(f"{k}=...")
                    
                    if param_parts:
                        cache_key = f"{cache_key}:{':'.join(param_parts)}"
                
                cache = cache_service
                
                # Пробуем получить из кэша
                cached_data = await cache.get(cache_key)
                if cached_data is not None:
                    logger.debug(f"📦 Cache HIT: {cache_key}")
                    return cached_data
                
                logger.debug(f"💾 Cache MISS: {cache_key}")
                
                # Выполняем функцию
                result = await func(*args, **kwargs)
                
                # Сохраняем в кэш
                if result is not None:
                    success = await cache.set(cache_key, result, ttl)
                    if not success:
                        logger.debug(f"⚠️ Failed to cache {cache_key}")
                
                return result
                
            except Exception as e:
                logger.error(f"Cache wrapper error: {str(e)}")
                # В случае ошибки кэширования — просто выполняем функцию
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator