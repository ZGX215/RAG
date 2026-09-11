"""多级缓存管理器 — L1 内存缓存 + L2 Redis 缓存。

设计思想：
- L1 (内存): 最近访问的热点数据，访问快，过期快
- L2 (Redis): 全量数据持久化，进程间共享，过期慢
- 查找顺序：先 L1 → 命中返回，没找到查 L2 → 命中回填 L1 → 都没找到回源
"""

from __future__ import annotations

import hashlib
import json
import pickle
from functools import lru_cache
from typing import Any, Generic, Optional, TypeVar

import redis

from config.settings import settings
from app.cross.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheEntry(Generic[T]):
    """缓存条目，带过期时间。"""

    def __init__(self, value: T, expire_at: float):
        self.value = value
        self.expire_at = expire_at

    def is_expired(self) -> bool:
        import time
        return time.time() > self.expire_at


class MultiLevelCache:
    """多级缓存：L1 内存 + L2 Redis。

    用法::
        cache = MultiLevelCache()
        cached_answer = cache.get("answer:个人信息保护法的适用范围")
        if cached_answer:
            return cached_answer
        answer = compute_answer(question)
        cache.set("answer:个人信息保护法的适用范围", answer, ttl=3600)
    """

    def __init__(
        self,
        redis_url: str = settings.cache.redis_url,
        l1_max_size: int = 1000,
    ):
        self._l1_max_size = l1_max_size
        self._l1: dict[str, CacheEntry[Any]] = {}
        self._redis_connected = False

        try:
            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            self._redis_connected = True
            logger.info("MultiLevelCache connected to Redis: %s", redis_url)
        except Exception as e:
            self._redis_connected = False
            logger.warning(
                "Redis connection failed, falling back to L1 only cache: %s", e
            )

    def _make_key(self, namespace: str, key: str) -> str:
        """生成缓存键，防止冲突。"""
        return f"mcu_rag:{namespace}:{key}"

    def _hash_key(self, text: str) -> str:
        """对长文本生成哈希键。"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]

    def _evict_if_needed(self) -> None:
        """L1 缓存超过大小，删除过期条目和部分最近最少使用。"""
        if len(self._l1) <= self._l1_max_size:
            return

        # 先删过期的
        import time
        now = time.time()
        expired_keys = [k for k, v in self._l1.items() if v.is_expired()]
        for k in expired_keys:
            del self._l1[k]

        # 如果还是超，删一半（简单策略，LRU 留给 lru_cache 做）
        if len(self._l1) > self._l1_max_size:
            keys = list(self._l1.keys())
            half = len(keys) // 2
            for k in keys[:half]:
                del self._l1[k]

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """获取缓存：先 L1，再 L2。"""
        full_key = self._make_key(namespace, self._hash_key(key))

        # L1 查找
        entry = self._l1.get(full_key)
        if entry:
            if not entry.is_expired():
                logger.debug("cache L1 hit: %s", full_key)
                return entry.value
            del self._l1[full_key]

        # L1 没中，查 L2
        if not self._redis_connected:
            return None

        try:
            data = self._redis.get(full_key)
            if not data:
                logger.debug("cache miss: %s", full_key)
                return None

            # 反序列化
            try:
                value = pickle.loads(data)
            except pickle.UnpicklingError:
                # 尝试 JSON
                try:
                    value = json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    return None

            # 回填 L1（默认用 L2 TTL 的 1/10）
            ttl = self._redis.ttl(full_key)
            if ttl > 0:
                import time
                entry = CacheEntry(value, time.time() + ttl / 10)
                self._l1[full_key] = entry
                self._evict_if_needed()

            logger.debug("cache L2 hit: %s", full_key)
            return value
        except Exception as e:
            logger.warning("Redis get failed: %s", e)
            return None

    def set(self, namespace: str, key: str, value: Any, ttl: int) -> None:
        """写入缓存：写 L1 和 L2。"""
        full_key = self._make_key(namespace, self._hash_key(key))

        import time
        entry = CacheEntry(value, time.time() + ttl / 10)
        self._l1[full_key] = entry
        self._evict_if_needed()

        if not self._redis_connected:
            return

        try:
            # 序列化
            data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            self._redis.setex(full_key, ttl, data)
            logger.debug("cache set: %s, ttl=%d", full_key, ttl)
        except Exception as e:
            logger.warning("Redis set failed: %s", e)

    def delete(self, namespace: str, key: str) -> None:
        """删除缓存。"""
        full_key = self._make_key(namespace, self._hash_key(key))
        self._l1.pop(full_key, None)

        if not self._redis_connected:
            return

        try:
            self._redis.delete(full_key)
        except Exception as e:
            logger.warning("Redis delete failed: %s", e)

    def clear_l1(self) -> None:
        """清空 L1 缓存。"""
        self._l1.clear()
        logger.info("L1 cache cleared")

    @property
    def is_redis_connected(self) -> bool:
        return self._redis_connected


# 全局单例
_cache_instance: Optional[MultiLevelCache] = None


def get_cache_manager() -> MultiLevelCache:
    """获取全局缓存管理器单例。"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MultiLevelCache()
    return _cache_instance
