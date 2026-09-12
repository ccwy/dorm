"""
线程安全的内存缓存模块
支持TTL过期机制，替代频繁的数据库查询
"""
import time
import threading
import logging
from typing import Any, Optional, Callable


class MemoryCache:
    """线程安全的内存缓存，支持TTL过期"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式，确保全局只有一个缓存实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._cache_lock = threading.RLock()
                    cls._instance._stats = {'hits': 0, 'misses': 0}
        return cls._instance

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，如果过期或不存在返回None"""
        with self._cache_lock:
            if key not in self._cache:
                self._stats['misses'] += 1
                return None

            entry = self._cache[key]
            if entry['expires_at'] is not None and time.time() > entry['expires_at']:
                # 已过期，删除并返回None
                del self._cache[key]
                self._stats['misses'] += 1
                return None

            self._stats['hits'] += 1
            return entry['value']

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """
        设置缓存值
        :param key: 缓存键
        :param value: 缓存值
        :param ttl: 过期时间（秒），默认300秒（5分钟），0表示永不过期
        """
        with self._cache_lock:
            self._cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl if ttl > 0 else None,
                'created_at': time.time()
            }

    def delete(self, key: str) -> bool:
        """删除缓存键，返回是否成功删除"""
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def delete_pattern(self, prefix: str) -> int:
        """删除所有以prefix开头的缓存键，返回删除数量"""
        with self._cache_lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    def clear(self) -> int:
        """清空所有缓存，返回清除的条目数"""
        with self._cache_lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_or_set(self, key: str, factory: Callable, ttl: int = 300) -> Any:
        """
        获取缓存值，如果不存在则通过factory函数生成并缓存
        :param key: 缓存键
        :param factory: 生成缓存值的函数（仅在缓存未命中时调用）
        :param ttl: 过期时间（秒）
        """
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value, ttl)
        return value

    def cleanup_expired(self) -> int:
        """清理所有过期的缓存条目，返回清理数量"""
        with self._cache_lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._cache.items()
                if v['expires_at'] is not None and now > v['expires_at']
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logging.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")
            return len(expired_keys)

    @property
    def size(self) -> int:
        """当前缓存条目数"""
        with self._cache_lock:
            return len(self._cache)

    @property
    def stats(self) -> dict:
        """缓存统计信息"""
        with self._cache_lock:
            return {
                'size': len(self._cache),
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': (
                    self._stats['hits'] / (self._stats['hits'] + self._stats['misses']) * 100
                    if (self._stats['hits'] + self._stats['misses']) > 0 else 0
                )
            }

    def reset_stats(self) -> None:
        """重置统计信息"""
        with self._cache_lock:
            self._stats = {'hits': 0, 'misses': 0}


# 全局缓存实例（单例）
cache = MemoryCache()


def cached(key_prefix: str, ttl: int = 300):
    """
    缓存装饰器，用于缓存函数返回值
    :param key_prefix: 缓存键前缀
    :param ttl: 过期时间（秒）
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 生成缓存键：前缀 + 函数名 + 参数哈希
            cache_key = f"{key_prefix}:{func.__name__}"
            if args:
                cache_key += f":{hash(args)}"
            if kwargs:
                cache_key += f":{hash(tuple(sorted(kwargs.items())))}"

            result = cache.get(cache_key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator