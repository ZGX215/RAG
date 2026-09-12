"""FastAPI 应用创建 + 中间件注册 + 健康检查 + CORS 配置。"""

from __future__ import annotations

import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.access.middleware import (
    ExceptionMiddleware,
    RequestIDMiddleware,
    SecurityMiddleware,
    TimingMiddleware,
)
from app.access.ratelimit import RateLimitMiddleware
from app.access.routes import router

# 初始化日志（需在 app 创建之前，lifespan 内也要用）
from app.cross.logging import get_logger, setup_logging
from app.cross.metrics import MetricsMiddleware, metrics_endpoint
from config.settings import settings

setup_logging(log_level=settings.general.log_level)
logger = get_logger(__name__)

# ============================================================
# 全局单例：ChromaRepository（在 main 入口初始化）
# ============================================================
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder

_embedder: Optional[SentenceEmbedder] = None
_repo: Optional[ChromaRepository] = None


def init_repo():
    """在 main 入口初始化，避免模块加载时打开数据库失败。"""
    global _embedder, _repo
    _embedder = SentenceEmbedder(
        model_name=settings.embedding.model,
        device=settings.embedding.device,
    )
    _repo = ChromaRepository(
        embedder=_embedder,
        persist_dir=settings.index.persist_dir,
        collection_name=settings.index.collection_name,
    )
    logger.info("repo initialized: %d chunks", _repo.count())


def _get_repo():
    return _repo


def _shutdown_resources() -> None:
    """释放进程持有的资源。

    进程退出时若不显式释放，模型、向量库句柄、数据库连接池、缓存连接都依赖
    操作系统回收 —— 容器里表现为停止缓慢甚至最终被 SIGKILL，本地则表现为
    文件锁 / 端口偶发残留。显式释放让关闭过程可控且可观测。

    逐项 try/except：单项失败不应阻止其余资源释放。
    """
    global _embedder, _repo

    try:
        close = getattr(_repo, "close", None)
        if callable(close):
            close()
        _repo = None
        _embedder = None
        logger.info("released: vector store / embedder")
    except Exception as e:
        logger.warning("release vector store failed: %s", e)

    try:
        from app.db.database import engine
        engine.dispose()
        logger.info("released: database connection pool")
    except Exception as e:
        logger.warning("release database pool failed: %s", e)

    try:
        from app.cross.answer_cache import get_answer_cache
        close = getattr(get_answer_cache(), "close", None)
        if callable(close):
            close()
        logger.info("released: answer cache")
    except Exception as e:
        logger.warning("release answer cache failed: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动记录 + 关闭时释放资源。"""
    logger.info("service starting (env=%s)", settings.general.env)
    yield
    logger.info("service shutting down, releasing resources...")
    _shutdown_resources()
    logger.info("shutdown complete")


# 创建 FastAPI app
app = FastAPI(
    title="企业级 RAG 知识库问答 API",
    description="检索增强生成（RAG）问答服务：多格式入库、双重检索、密级权限过滤、多级降级",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 中间件注册
# ============================================================
# ⚠️ 顺序极易搞反：Starlette 把**后添加**的中间件放在外层，即"后注册的先执行"。
#    期望的执行顺序（从外到内）：
#        Exception → Metrics → RequestID → Timing → Security → RateLimit → 路由
#    因此下面按"从内到外"倒序注册。
#
#    历史问题（本轮修正）：原注释写的是"先注册的先执行"，于是 RequestID 被注册在
#    最前、实际却排在最内层，Timing 反而在它外层 → 取不到 RequestContext 直接跳过，
#    耗时日志从未真正打印过（已实测确认：请求不会输出 "request completed"）。
if settings.api.rate_limit_per_minute > 0:
    app.add_middleware(
        RateLimitMiddleware,
        limit=settings.api.rate_limit_per_minute,
        window_seconds=settings.api.rate_limit_window_seconds,
    )
    logger.info(
        "rate limit enabled: %d requests / %ds per identity",
        settings.api.rate_limit_per_minute,
        settings.api.rate_limit_window_seconds,
    )

app.add_middleware(SecurityMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(ExceptionMiddleware)

# 注册路由
app.include_router(router, prefix="/api/v1")


# ============================================================
# 健康检查：liveness 与 readiness 分离
# ============================================================
# 为什么必须分开：
#   liveness 回答"这个进程要不要重启"，所以**不能**探外部依赖 —— 数据库挂了
#   重启进程毫无帮助，只会让容器陷入反复重启。它只表示进程还没死。
#   readiness 回答"现在能不能接流量"，必须逐项探依赖，未就绪返回 503，
#   让上游（负载均衡 / 容器编排）把该实例摘出去，而不是把请求打进来失败。


def _check_dependencies() -> list[dict]:
    """逐项探测依赖，返回可读结果。

    单项失败不抛异常 —— readiness 的职责是"报告状态"，不是"让探活本身崩掉"。
    """
    checks: list[dict] = []

    # 向量库（核心依赖）
    try:
        if _repo is None:
            checks.append({"name": "vector_store", "ok": False,
                           "detail": "not initialized", "required": True})
        else:
            checks.append({"name": "vector_store", "ok": True,
                           "detail": f"{_repo.count()} chunks", "required": True})
    except Exception as e:
        checks.append({"name": "vector_store", "ok": False,
                       "detail": f"{type(e).__name__}: {e}", "required": True})

    # 关系型数据库（核心依赖）
    try:
        from sqlalchemy import text

        from app.db.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks.append({"name": "database", "ok": True, "detail": "ok", "required": True})
    except Exception as e:
        checks.append({"name": "database", "ok": False,
                       "detail": f"{type(e).__name__}: {e}", "required": True})

    # Redis（可选依赖）：不可用时答案缓存自动降级为进程内 L1，服务仍可正常工作，
    # 因此 required=False，不因它拖垮 readiness。用 socket 探测而非引入客户端依赖，
    # 以免探活本身受客户端版本影响。
    try:
        parsed = urlparse(settings.cache.redis_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=1.0):
            pass
        checks.append({"name": "redis", "ok": True, "detail": "reachable", "required": False})
    except Exception as e:
        checks.append({"name": "redis", "ok": False,
                       "detail": f"{type(e).__name__}（可选依赖，服务会降级为进程内缓存）",
                       "required": False})

    return checks


@app.get("/health/live")
async def health_live():
    """liveness 探针：仅表示进程存活，不检查任何外部依赖。"""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """readiness 探针：依赖未就绪时返回 503，供上游摘除流量。"""
    checks = _check_dependencies()
    ready = all(c["ok"] for c in checks if c["required"])
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )


@app.get("/health")
async def health():
    """综合健康检查：始终返回 200 并给出各项明细。

    保留给人工排查与既有调用方（脚本/编排用它看总数）。
    与 /health/ready 的区别：这里不做状态码语义，只如实报告。
    """
    checks = _check_dependencies()
    ready = all(c["ok"] for c in checks if c["required"])

    total_chunks = 0
    if _repo is not None:
        try:
            total_chunks = _repo.count()
        except Exception:
            total_chunks = 0

    return {
        "status": "ok" if ready else "degraded",
        "total_chunks": total_chunks,
        "checks": checks,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点（QPS/延迟/错误率）。"""
    return metrics_endpoint()


# 单进程部署：把前端静态页面也托管在 8000，避免跨端口访问与 CORS 问题。
# 必须放在所有 API 路由之后注册，确保 /api/v1、/health、/metrics 优先匹配。
_static_dir = _PROJECT_ROOT / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="frontend")
