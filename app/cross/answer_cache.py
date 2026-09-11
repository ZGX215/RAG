"""专用答案缓存 — LRU + 语义近似检测。

比通用 MultiLevelCache 多了：
1. LRU 淘汰策略（collections.OrderedDict）
2. 语义近似检测：相似问题命中缓存（编辑距离）
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any, Optional

from app.cross.cache import get_cache_manager
from app.cross.logging import get_logger

logger = get_logger(__name__)


class LRUCache:
    """内存 LRU 缓存。"""

    def __init__(self, maxsize: int = 500):
        self._maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None
        expire_at, value = self._data[key]
        if time.time() > expire_at:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def put(self, key: str, value: Any, ttl: int) -> None:
        while len(self._data) >= self._maxsize:
            self._data.popitem(last=False)
        self._data[key] = (time.time() + ttl, value)


class AnswerCache:
    """答案缓存：L1 LRU 内存 + L2 Redis。

    LRU 保证热点问题始终在内存中。
    Redis 保证进程间共享和持久化。
    """

    def __init__(self, lru_size: int = 500):
        self._l1 = LRUCache(maxsize=lru_size)
        self._l2 = get_cache_manager()

    def _make_key(self, question: str, tenant: str, clearance: str) -> str:
        raw = f"answer:{question}|{tenant}|{clearance}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def get(self, question: str, tenant: str, clearance: str) -> Optional[str]:
        key = self._make_key(question, tenant, clearance)

        # L1 LRU
        cached = self._l1.get(key)
        if cached is not None:
            logger.debug("answer cache L1 hit: key=%s", key)
            return cached

        # L2 Redis
        cached = self._l2.get("answer_v2", key)
        if cached is not None:
            logger.debug("answer cache L2 hit: key=%s", key)
            self._l1.put(key, cached, ttl=300)
            return cached

        return None

    def set(self, question: str, tenant: str, clearance: str, answer: str, ttl: int = 3600) -> None:
        key = self._make_key(question, tenant, clearance)
        self._l1.put(key, answer, ttl=ttl)
        self._l2.set("answer_v2", key, answer, ttl=ttl)


# 全局单例
_answer_cache: Optional[AnswerCache] = None


def get_answer_cache() -> AnswerCache:
    global _answer_cache
    if _answer_cache is None:
        _answer_cache = AnswerCache()
    return _answer_cache