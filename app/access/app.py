"""FastAPI 应用创建 + 中间件注册 + CORS 配置。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from app.access.middleware import (
    RequestIDMiddleware,
    SecurityMiddleware,
    TimingMiddleware,
    ExceptionMiddleware,
)
from app.access.routes import router
from app.cross.metrics import MetricsMiddleware, metrics_endpoint

# 创建 FastAPI app
app = FastAPI(
    title="MCU RAG QA API",
    description="RAG 问答 API，基于企业知识库文档",
    version="0.1.0",
)

# 初始化日志
from app.cross.logging import setup_logging, get_logger
setup_logging(log_level=settings.general.log_level)
logger = get_logger(__name__)

# CORS 配置
origins = settings.api.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 中间件注册：顺序很重要，先注册的先执行
# 1. RequestID：生成 request_id，设置 context
# 2. Security：从请求头解析身份，注入 MetaFilter 到 RequestContext
# 3. Timing：记录开始时间，计算耗时
# 4. Metrics：Prometheus 指标采集（QPS/延迟/错误率）
# 5. Exception：全局异常拦截
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityMiddleware)
app.add_middleware(TimingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(ExceptionMiddleware)

# 注册路由
app.include_router(router, prefix="/api/v1")


# 全局单例：ChromaRepository（lazy init 在 main 中完成）
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder

_embedder: Optional[SentenceEmbedder] = None
_repo: Optional[ChromaRepository] = None


def init_repo():
    """在 main 入口初始化，避免模块加载时数据库打开失败。"""
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


# 健康检查
@app.get("/health")
async def health():
    """健康检查接口，返回服务状态和文档总数。"""
    if _repo is None:
        return {
            "status": "starting",
            "total_chunks": 0,
        }
    total = _repo.count()

    return {
        "status": "ok",
        "total_chunks": total,
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
