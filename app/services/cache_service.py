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
    
    async def get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False
            )
            logger.info(f"✅ Redis connected to {self.redis_url}")
        return self._client
    
    async def get(self, key: str) -> Optional[Any]:
        try:
            client = await self.get_client()
            data = await client.get(key)
            if data:
                return pickle.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {str(e)}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        try:
            client = await self.get_client()
            ttl = ttl or self.default_ttl
            
            serialized = pickle.dumps(value)
            await client.setex(key, ttl, serialized)
            logger.debug(f"✅ Cached: {key} (TTL: {ttl}s, size: {len(serialized)} bytes)")
            return True
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        try:
            client = await self.get_client()
            await client.delete(key)
            logger.debug(f"🗑️ Deleted cache key: {key}")
            return True
        except Exception as e:
            logger.error(f"Redis delete error: {str(e)}")
            return False
    
    async def delete_pattern(self, pattern: str) -> bool:
        try:
            client = await self.get_client()
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
                logger.info(f"🗑️ Deleted {len(keys)} cache keys by pattern: {pattern}")
            return True
        except Exception as e:
            logger.error(f"Redis delete_pattern error: {str(e)}")
            return False
    
    async def clear_all(self) -> bool:
        try:
            client = await self.get_client()
            await client.flushdb()
            logger.info("🗑️ All cache cleared")
            return True
        except Exception as e:
            logger.error(f"Redis clear_all error: {str(e)}")
            return False
    
    def generate_key(self, *parts: str) -> str:
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
                        logger.warning(f"⚠️ Failed to cache {cache_key}")
                
                return result
                
            except Exception as e:
                logger.error(f"Cache wrapper error: {str(e)}")
                # В случае ошибки кэширования — просто выполняем функцию
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator