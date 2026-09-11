"""可观测指标 — QPS/延迟/错误率，Prometheus 原生格式。

提供 /metrics 端点，被 Prometheus 抓取。
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware

from app.cross.logging import get_logger

logger = get_logger(__name__)

# ============================================================
# Prometheus 指标定义
# ============================================================

# 请求计数（按方法 + 路径 + 状态码）
REQUEST_COUNT = Counter(
    "mcu_rag_requests_total",
    "Total request count",
    ["method", "path", "status"],
)

# 请求延迟（按方法 + 路径）
REQUEST_LATENCY = Histogram(
    "mcu_rag_request_duration_ms",
    "Request duration in milliseconds",
    ["method", "path"],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000],
)

# 检索结果数（按方法）
RETRIEVAL_HITS = Histogram(
    "mcu_rag_retrieval_hits",
    "Number of retrieval hits per request",
    buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
)

# 缓存命中
CACHE_HITS = Counter(
    "mcu_rag_cache_hits_total",
    "Cache hit count by namespace",
    ["namespace"],
)

# 降级次数
DEGRADE_COUNT = Counter(
    "mcu_rag_degrade_total",
    "Degradation count by layer",
    ["layer"],  # vector_fallback, bm25_fallback, llm_fallback, raw_snippet
)

# 注入检测
INJECTION_COUNT = Counter(
    "mcu_rag_injection_total",
    "Prompt injection detection count by category",
    ["category"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录请求指标：QPS、延迟、状态码。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        path = request.url.path
        method = request.method
        status = str(response.status_code)

        REQUEST_COUNT.labels(method=method, path=path, status=status).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed_ms)

        return response


def metrics_endpoint() -> Response:
    """Prometheus /metrics 端点。"""
    from fastapi.responses import Response
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


class Metrics:
    """指标命名空间，方便路由层引用。"""

    requests_total = REQUEST_COUNT
    request_duration_ms = REQUEST_LATENCY
    retrieval_hits = RETRIEVAL_HITS
    cache_hits_total = CACHE_HITS
    degrade_total = DEGRADE_COUNT
    injection_total = INJECTION_COUNT


metrics = Metrics()