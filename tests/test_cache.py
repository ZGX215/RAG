"""多级缓存测试 — L1 内存缓存 + L2 Redis（Mock）的读写删、过期淘汰、降级。

测试覆盖：
1. LRU 缓存 get/put/过期淘汰
2. AnswerCache L1 读写 + 权限感知缓存键
3. AnswerCache 缓存键隔离：不同密级不能互相读到
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.cross.answer_cache import LRUCache, AnswerCache


class TestLRUCache:
    """LRU 内存缓存测试。"""

    def test_put_and_get(self):
        """写入后能读到。"""
        cache = LRUCache(maxsize=10)
        cache.put("key1", "value1", ttl=60)
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        """不存在的 key 返回 None。"""
        cache = LRUCache(maxsize=10)
        assert cache.get("nonexistent") is None

    def test_expired_key(self):
        """过期的 key 返回 None。"""
        cache = LRUCache(maxsize=10)
        cache.put("key1", "value1", ttl=1)
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """超过 maxsize 时淘汰最早的。"""
        cache = LRUCache(maxsize=3)
        cache.put("k1", "v1", ttl=60)
        cache.put("k2", "v2", ttl=60)
        cache.put("k3", "v3", ttl=60)
        # k1 在最前面，加入 k4 后 k1 被淘汰
        cache.put("k4", "v4", ttl=60)
        assert cache.get("k1") is None
        assert cache.get("k4") == "v4"

    def test_lru_access_updates_order(self):
        """访问 key 后它不会被淘汰（移到末尾）。"""
        cache = LRUCache(maxsize=3)
        cache.put("k1", "v1", ttl=60)
        cache.put("k2", "v2", ttl=60)
        cache.put("k3", "v3", ttl=60)
        # 访问 k1，让它移到末尾
        cache.get("k1")
        # 加入 k4，此时 k2 被淘汰（因为它最早）
        cache.put("k4", "v4", ttl=60)
        assert cache.get("k1") == "v1"
        assert cache.get("k2") is None


class TestAnswerCache:
    """答案缓存测试 — 权限感知缓存键。"""

    def setup_method(self):
        """每个测试用独立的 AnswerCache，mock 掉 Redis 连接。"""
        with patch("app.cross.cache.redis.Redis.from_url") as mock_redis:
            mock_redis.return_value.ping.side_effect = Exception("no redis")
            self.cache = AnswerCache(lru_size=10)

    def test_set_and_get_same_permissions(self):
        """相同问题、相同权限：写入后能命中。"""
        self.cache.set("什么是算力", "tenant_a", "public", "算力是计算能力")
        result = self.cache.get("什么是算力", "tenant_a", "public")
        assert result == "算力是计算能力"

    def test_different_tenant_not_shared(self):
        """不同租户：相同问题不能互相读到。"""
        self.cache.set("什么是算力", "tenant_a", "public", "答案A")
        result = self.cache.get("什么是算力", "tenant_b", "public")
        assert result is None

    def test_different_clearance_not_shared(self):
        """不同密级：相同问题不能互相读到。"""
        self.cache.set("薪资数据", "tenant_a", "confidential", "机密答案")
        result = self.cache.get("薪资数据", "tenant_a", "public")
        assert result is None

    def test_get_missing_question(self):
        """没写过的 key 返回 None。"""
        result = self.cache.get("不存在的问题", "tenant_a", "public")
        assert result is None
