"""限流逻辑测试（app/access/ratelimit.py）。

只测纯逻辑、不起服务：滑动窗口行为不依赖 HTTP 层，单独测更快也更稳定。
限流一旦写错，后果是"正常用户被误伤"或"限流形同虚设"，因此边界都要卡住。
"""

from __future__ import annotations

from types import SimpleNamespace

from app.access.ratelimit import RateLimitMiddleware, SlidingWindowLimiter


class TestSlidingWindowLimiter:
    """滑动窗口计数器的边界行为。"""

    def test_allows_up_to_limit(self):
        lim = SlidingWindowLimiter(limit=3, window_seconds=60)
        for i in range(3):
            allowed, _ = lim.check("k", now=1000.0 + i)
            assert allowed, f"阈值内的第 {i + 1} 次应放行"

    def test_rejects_over_limit(self):
        lim = SlidingWindowLimiter(limit=3, window_seconds=60)
        for i in range(3):
            lim.check("k", now=1000.0 + i)
        allowed, retry_after = lim.check("k", now=1004.0)
        assert not allowed, "超过阈值必须拒绝"
        assert retry_after >= 1, "必须给出 Retry-After，否则客户端只能盲目重试"

    def test_window_slides(self):
        """最早的请求滑出窗口后应重新放行——否则限流会退化成永久封禁。"""
        lim = SlidingWindowLimiter(limit=2, window_seconds=10)
        lim.check("k", now=1000.0)
        lim.check("k", now=1001.0)
        assert lim.check("k", now=1002.0)[0] is False
        assert lim.check("k", now=1011.5)[0] is True

    def test_keys_are_independent(self):
        """一个用户被限流不应影响其他用户。"""
        lim = SlidingWindowLimiter(limit=1, window_seconds=60)
        assert lim.check("a", now=1000.0)[0] is True
        assert lim.check("b", now=1000.0)[0] is True
        assert lim.check("a", now=1000.1)[0] is False

    def test_retry_after_stays_within_window(self):
        lim = SlidingWindowLimiter(limit=1, window_seconds=30)
        lim.check("k", now=1000.0)
        _, retry_after = lim.check("k", now=1005.0)
        assert 1 <= retry_after <= 30

    def test_reset(self):
        lim = SlidingWindowLimiter(limit=1, window_seconds=60)
        lim.check("k", now=1000.0)
        assert lim.check("k", now=1000.1)[0] is False
        lim.reset("k")
        assert lim.check("k", now=1000.2)[0] is True

    def test_gc_drops_stale_keys(self):
        """key 数量超上限时回收过期条目，避免被大量伪造 IP 撑爆内存。"""
        lim = SlidingWindowLimiter(limit=1, window_seconds=5, max_keys=3)
        for i in range(3):
            lim.check(f"k{i}", now=1000.0 + i * 0.1)
        assert lim.tracked_keys == 3

        lim.check("new", now=1100.0)  # 此时 k0~k2 均已过期

        assert lim.tracked_keys == 1, "过期 key 应被回收，只留下未过期的"


class TestClientKey:
    """限流键的选择：已登录按用户，未登录按 IP。"""

    @staticmethod
    def _req(user=None, host="1.2.3.4"):
        req = SimpleNamespace()
        req.state = SimpleNamespace(auth_user=user)
        req.client = SimpleNamespace(host=host)
        return req

    def test_uses_uid_when_authenticated(self):
        """已登录按 uid 计数，避免同一出口 IP 的多个用户互相影响。"""
        assert RateLimitMiddleware._client_key(self._req(user={"uid": 7})) == "u:7"

    def test_falls_back_to_ip(self):
        assert RateLimitMiddleware._client_key(self._req(user=None)) == "ip:1.2.3.4"

    def test_uid_zero_falls_back_to_ip(self):
        """uid=0 是 SecurityMiddleware 给匿名请求填的占位值，不能当成真实用户。

        否则所有匿名请求都会被归到 "u:0" 这一个桶里，互相挤占配额。
        """
        req = self._req(user={"uid": 0}, host="9.9.9.9")
        assert RateLimitMiddleware._client_key(req) == "ip:9.9.9.9"

    def test_missing_client_info(self):
        """拿不到 client 信息时不能崩，退化为固定 key。"""
        req = SimpleNamespace()
        req.state = SimpleNamespace(auth_user=None)
        req.client = None
        assert RateLimitMiddleware._client_key(req) == "ip:unknown"
