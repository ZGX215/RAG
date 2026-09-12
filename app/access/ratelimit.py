"""接口限流：内存滑动窗口。

适用规模说明（重要）：
    本实现为**单进程内存计数**，适用于单副本部署。若将来横向扩展为多副本，
    必须把计数迁到 Redis —— 否则每个副本各自计数，实际配额会被放大到
    「副本数 × 阈值」。这里显式写明，避免被误认为已经支持分布式限流。

策略：
    - 按身份限流：已登录用户按 uid，未登录按客户端 IP
    - 窗口内超过阈值返回 429 + Retry-After
    - 健康检查与指标端点不限流（探活/抓取频率高，限流反而造成误判）
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.cross.logging import get_logger

logger = get_logger(__name__)

EXEMPT_PREFIXES = (
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
)


class SlidingWindowLimiter:
    """内存滑动窗口计数器。

    每个 key 只保留窗口内请求的时间戳，因此内存占用正比于"窗口内的请求数"，
    而不是历史请求总量。key 数量超过上限时做一次惰性回收，避免被大量
    伪造 IP 撑爆内存。
    """

    def __init__(self, limit: int, window_seconds: int = 60, max_keys: int = 10000) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """返回 (是否放行, Retry-After 秒数)。"""
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        cutoff = now - self._window
        while q and q[0] <= cutoff:
            q.popleft()

        if len(q) >= self._limit:
            retry_after = max(1, int(q[0] + self._window - now) + 1)
            return False, retry_after

        q.append(now)
        self._maybe_gc(now)
        return True, 0

    def _maybe_gc(self, now: float) -> None:
        if len(self._hits) <= self._max_keys:
            return
        cutoff = now - self._window
        for k in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[k]

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)

    @property
    def tracked_keys(self) -> int:
        return len(self._hits)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按用户/IP 限流的中间件。

    必须注册在 SecurityMiddleware **之后**（即更靠内层），否则拿不到
    request.state.auth_user，只能退化为纯 IP 限流 —— 多个用户共用出口 IP
    （公司网络/NAT）时会互相影响。
    """

    def __init__(self, app, limit: int = 60, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limiter = SlidingWindowLimiter(limit=limit, window_seconds=window_seconds)
        self._limit = limit
        self._window = window_seconds

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)

        key = self._client_key(request)
        allowed, retry_after = self.limiter.check(key)
        if not allowed:
            logger.warning(
                "rate limit exceeded: key=%s path=%s limit=%d/%ds",
                key, path, self._limit, self._window,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "error": f"请求过于频繁，请 {retry_after} 秒后重试",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)

    @staticmethod
    def _client_key(request: Request) -> str:
        user = getattr(request.state, "auth_user", None)
        if isinstance(user, dict) and user.get("uid"):
            return f"u:{user['uid']}"
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"
