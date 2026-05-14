"""
cache.py - Redis caching utilities for high-performance data access.

Non-breaking additions that can be selectively applied to routes
without modifying existing code paths.

Example:
    from utils.cache import cached
    
    @cached(ttl=3600, key_prefix="health")
    def get_health_score(session_id: str) -> Dict:
        # Expensive computation here
        return calculate_health_score(df)
    
    # Function now checks Redis before executing
"""

import json
import functools
from typing import Any, Callable, Optional, TypeVar
from utils.logger import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from config import settings

# Redis client (lazy initialization)
_redis_client: Optional[Any] = None


def get_redis_client() -> Optional[Any]:
    """Get or create Redis client. Returns None if Redis is unavailable."""
    global _redis_client
    
    if not REDIS_AVAILABLE or redis is None:
        return None
    
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL or "redis://localhost:6379/0")  # type: ignore
            _redis_client.ping()
            logger.info("Redis cache connected")
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            _redis_client = False  # Marker for "tried and failed"
    
    return _redis_client if _redis_client is not False else None


F = TypeVar('F', bound=Callable[..., Any])


def cached(ttl: int = 3600, key_prefix: str = "cache"):
    """
    Decorator to cache function results in Redis.
    
    If Redis is unavailable, function executes normally without caching.
    This makes caching opt-in and non-breaking.
    
    Args:
        ttl: Time-to-live in seconds (default: 1 hour)
        key_prefix: Redis key prefix for organization
    
    Example:
        @cached(ttl=3600, key_prefix="health")
        def calculate_score(session_id: str) -> Dict:
            return expensive_operation(session_id)
        
        # With positional args:
        result = calculate_score("session-123")  # Cached!
        
        # With keyword args:
        result = calculate_score(session_id="session-123")  # Also cached!
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            redis_client = get_redis_client()
            
            if redis_client is None:
                # Redis unavailable - execute function normally
                return func(*args, **kwargs)
            
            # Generate cache key from function name and arguments
            cache_key = _make_cache_key(key_prefix, func.__name__, args, kwargs)
            
            try:
                # Try to get from cache
                cached_value = redis_client.get(cache_key)
                if cached_value:
                    logger.debug(f"Cache hit: {cache_key}")
                    return json.loads(cached_value)
            except Exception as e:
                logger.warning(f"Cache read error for {cache_key}: {e}")
                # Fall through to execute function
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Try to store in cache
            try:
                redis_client.setex(
                    cache_key,
                    ttl,
                    json.dumps(result, default=str)  # default=str handles non-JSON types
                )
                logger.debug(f"Cached {cache_key} with TTL {ttl}s")
            except Exception as e:
                logger.warning(f"Cache write error for {cache_key}: {e}")
                # Return result anyway - caching is best-effort
            
            return result
        
        return wrapper  # type: ignore
    
    return decorator


def clear_cache(key_prefix: str) -> int:
    """
    Clear all cached entries with a given prefix.
    
    Args:
        key_prefix: Redis key prefix to clear
    
    Returns:
        Number of keys deleted
    
    Example:
        # Clear all health score caches
        count = clear_cache("health")
        logger.info(f"Cleared {count} cache entries")
    """
    redis_client = get_redis_client()
    
    if redis_client is None:
        return 0
    
    try:
        pattern = f"{key_prefix}:*"
        keys = redis_client.keys(pattern)
        if keys:
            deleted = redis_client.delete(*keys)
            logger.info(f"Cleared {deleted} cache entries matching {pattern}")
            return deleted
        return 0
    except Exception as e:
        logger.error(f"Error clearing cache for {key_prefix}: {e}")
        return 0


def invalidate_cache(key_prefix: str, *identifiers) -> bool:
    """
    Invalidate specific cache entries.
    
    Args:
        key_prefix: Redis key prefix
        identifiers: Function arguments that were used to create the key
    
    Returns:
        True if invalidated, False if not found or error
    
    Example:
        # Invalidate health score for session "abc123"
        invalidate_cache("health", "calculate_score", "abc123")
    """
    redis_client = get_redis_client()
    
    if redis_client is None:
        return False
    
    try:
        cache_key = _make_cache_key(key_prefix, *identifiers) if identifiers else f"{key_prefix}:*"
        deleted = redis_client.delete(cache_key)
        if deleted:
            logger.info(f"Invalidated cache key: {cache_key}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        return False


def _make_cache_key(prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    """
    Generate a cache key from function arguments.
    
    Strategy: Use function name + stringified args to create key
    Example: "health:calculate_score:session-123:arg2"
    """
    arg_str = ":".join(str(arg) for arg in args if arg is not None)
    kwarg_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None)
    
    parts = [prefix, func_name]
    if arg_str:
        parts.append(arg_str)
    if kwarg_str:
        parts.append(kwarg_str)
    
    return ":".join(parts)


class CacheManager:
    """Context manager for cache operations."""
    
    def __init__(self, key_prefix: str):
        self.key_prefix = key_prefix
        self.redis_client = get_redis_client()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # No exception - keep cache
            return False
        else:
            # Exception occurred - invalidate cache
            clear_cache(self.key_prefix)
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if self.redis_client is None:
            return None
        try:
            value = self.redis_client.get(f"{self.key_prefix}:{key}")
            return json.loads(value) if value else None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache."""
        if self.redis_client is None:
            return False
        try:
            self.redis_client.setex(
                f"{self.key_prefix}:{key}",
                ttl,
                json.dumps(value, default=str)
            )
            return True
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if self.redis_client is None:
            return False
        try:
            return bool(self.redis_client.delete(f"{self.key_prefix}:{key}"))
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False
