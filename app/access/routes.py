"""API 路由 — POST /qa + POST /ingest + GET /health + GET /ingest/{task_id}

路由只做"请求 → 响应"的编排，不掺业务逻辑。
业务逻辑在 retrieve/generate 层，不在路由里。
P3 改造：POST /ingest 改为异步（Celery 后台处理），不阻塞问答。
"""

from __future__ import annotations

from typing import Any, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.contracts import MetaFilter
from app.cross.answer_cache import get_answer_cache
from app.cross.celery_app import celery_app
from app.cross.context import get_current_context
from app.cross.logging import get_logger
from app.cross.metrics import metrics
from app.db import crud
from app.db.database import get_db
from app.generate.prompt_injection_detector import PromptInjectionDetector
from config.settings import settings

logger = get_logger(__name__)

router = APIRouter()

# 全局单例（避免每次请求重复创建注入检测器、缓存、检索器）
_injection_detector = PromptInjectionDetector()
_answer_cache = get_answer_cache()
_retriever_instance = None  # 惰性初始化的全局检索器（含 BM25 索引）


# ============================================================
# 请求 / 响应模型
# ============================================================

class QARequest(BaseModel):
    question: str = Field(..., description="用户问题")
    top_k: int = Field(default=5, ge=1, le=50, description="检索返回的切片数量")
    stream: bool = Field(default=False, description="是否流式输出（SSE）")


class SourceItem(BaseModel):
    heading_number: str = ""
    doc_name: str = ""
    score: float = 0.0
    content: str = ""


class QAResponse(BaseModel):
    answer: str = ""
    sources: list[SourceItem] = []
    request_id: str = ""


class IngestRequest(BaseModel):
    # 必填：原先这里默认指向开发者本机的桌面文件，别人调用必然失败（且泄露本机路径）
    file_path: str = Field(
        description="文件路径（支持 PDF/Word/Markdown/TXT）",
    )
    doc_name: str = Field(default="", description="文档名称（留空则用文件名）")
    classification: str = Field(default="public", description="文档密级：public/internal/confidential/secret")


class IngestResponse(BaseModel):
    status: str = ""
    task_id: str = ""
    message: str = ""
    request_id: str = ""


class TaskStatusResponse(BaseModel):
    task_id: str = ""
    status: str = ""
    result: Optional[dict] = None
    request_id: str = ""


class BatchIngestRequest(BaseModel):
    file_paths: list[str] = Field(..., description="文件路径列表，每个文件名必须符合格式: 文件名_PUBLIC/INTERNAL/CONFIDENTIAL/SECRET.ext")


class BatchIngestErrorItem(BaseModel):
    file_path: str = ""
    error: str = ""


class BatchIngestResponse(BaseModel):
    status: str = ""  # ok/all_passed/partial_failed/rejected
    total_files: int = 0
    passed_files: int = 0
    rejected_files: list[BatchIngestErrorItem] = []
    task_ids: list[str] = []
    request_id: str = ""


# ============================================================
# 问答核心逻辑（非流式 + 流式共用）
# ============================================================


async def _qa_json(
    question: str,
    top_k: int,
    meta_filter: Optional[MetaFilter],
    request_id: str,
    answer_cache: Any,
    tenant: str,
    clearance: str,
    db: Session | None = None,
) -> QAResponse:
    """非流式问答：完整生成后返回 JSON。"""
    from app.generate.fallback_provider import FallbackProvider

    fallback_provider = FallbackProvider(rules_path=settings.generate.fallback_rules_path)

    # 降级链路 1：兜底规则匹配
    try:
        fallback_rule = fallback_provider.match(question)
        if fallback_rule:
            logger.info("fallback rule matched: request_id=%s", request_id)
            metrics.degrade_total.labels(layer="fallback_rule").inc()
            return QAResponse(answer=fallback_rule.answer, sources=[], request_id=request_id)
    except Exception as e:
        logger.warning("fallback rule match failed: %s", e)

    # 降级链路 2：检索
    hits = await _retrieve(question, top_k, meta_filter, request_id)
    # 最低分数过滤：RRF 分数低于 0.01 说明匹配度很差，不返回
    hits = [h for h in hits if h.final_score > 0.01]
    if not hits:
        return QAResponse(answer="未找到相关内容，请尝试更换关键词或换个说法。", sources=[], request_id=request_id)

    # 相关性过滤：dense_score 低于 0.3 且 RRF 分数低于 0.02 说明没有真正相关的文档
    hits = [h for h in hits if h.dense_score >= 0.3 or h.rerank_score > 0.02]
    if not hits:
        return QAResponse(
            answer="资料中没有找到相关内容，请换个说法或补充更多关键词。",
            sources=[], request_id=request_id,
        )

    # 降级链路 3：LLM 生成
    answer = await _llm_generate(question, hits, request_id, fallback_provider)

    # 缓存（仅缓存正常 LLM 生成结果，不缓存降级原文片段）
    if answer and "相关资料如下：" not in answer:
        try:
            answer_cache.set(question, tenant, clearance, answer, ttl=3600)
        except Exception as e:
            logger.warning("cache write failed: %s", e)

    sources = [
        SourceItem(heading_number=h.meta.heading_number, doc_name=h.meta.doc_name, score=h.final_score, content=h.content[:200])
        for h in hits[:5]
    ]
    logger.info("qa response: request_id=%s hits=%d answer_len=%d", request_id, len(hits), len(answer))

    # 记录查询日志到数据库
    is_degraded = "相关资料如下：" in answer
    if db is not None:
        try:
            log = crud.create_query_log(
                db=db, trace_id=request_id, tenant_id=tenant, user_clearance=clearance,
                question=question, top_k=top_k, sources_count=len(sources),
                answer_preview=answer, elapsed_ms=0, cache_hit=False,
                degraded=is_degraded, injection_blocked=False,
                llm_used=not is_degraded,
            )
            # 记录来源
            source_dicts = [
                {"rank": i + 1, "chunk_id": h.chunk_id, "doc_name": h.meta.doc_name,
                 "heading_number": h.meta.heading_number,
                 "dense_score": h.dense_score, "sparse_score": h.sparse_score,
                 "rrf_score": h.rerank_score}
                for i, h in enumerate(hits[:5])
            ]
            crud.add_query_sources(db, log.id, source_dicts)
        except Exception as e:
            logger.warning("query log write failed: %s", e)

    return QAResponse(answer=answer, sources=sources, request_id=request_id)


async def _qa_stream(
    question: str,
    top_k: int,
    meta_filter: Optional[MetaFilter],
    request_id: str,
    answer_cache: Any,
    tenant: str,
    clearance: str,
) -> StreamingResponse:
    """流式问答：SSE 逐 token 输出。"""
    from app.generate.fallback_provider import FallbackProvider
    from app.generate.llm_client import DeepSeekClient

    fallback_provider = FallbackProvider(rules_path=settings.generate.fallback_rules_path)

    async def event_stream():
        # 兜底规则匹配
        try:
            fallback_rule = fallback_provider.match(question)
            if fallback_rule:
                metrics.degrade_total.labels(layer="fallback_rule").inc()
                yield f"data: {fallback_rule.answer}\n\n"
                yield "data: [DONE]\n\n"
                return
        except Exception:
            pass

        # 检索
        hits = await _retrieve(question, top_k, meta_filter, request_id)
        if not hits:
            yield "data: 未找到相关内容，请尝试更换关键词或换个说法。\n\n"
            yield "data: [DONE]\n\n"
            return

        # 余弦相似度阈值过滤
        hits = [h for h in hits if h.dense_score >= 0.3 or h.rerank_score > 0.02]
        if not hits:
            yield "data: 资料中没有找到相关内容，请换个说法或补充更多关键词。\n\n"
            yield "data: [DONE]\n\n"
            return

        # LLM 流式生成
        llm = DeepSeekClient(
            api_key=settings.llm.api_key, base_url=settings.llm.base_url, model=settings.llm.model,
            fallback_api_key=settings.llm.fallback_api_key or None,
            fallback_base_url=settings.llm.fallback_base_url or None,
            fallback_model=settings.llm.fallback_model or None,
        )
        max_chars = settings.generate.context_max_chars // max(len(hits), 1)
        context = "\n\n".join(f"[{h.meta.heading_number}]\n{h.content[:max_chars]}" for h in hits)
        system_prompt = (
            "你是一个企业知识库助手，基于以下资料回答用户问题。"
            "只能依据提供的资料作答，不得臆测。"
            "如果资料中没有答案，请明确说明'资料中未提及'，不要编造。"
            "回答时注明所依据的资料出处。"
        )
        user_prompt = f"参考资料：\n{context}\n\n问题：{question}"

        full_answer = ""
        try:
            async for token in llm.generate_stream(system_prompt, user_prompt):
                full_answer += token
                yield f"data: {token}\n\n"
        except Exception as e:
            logger.error("stream generation failed: %s", e)
            # 降级为原文片段
            raw_parts = []
            for h in hits[:3]:
                header = h.meta.heading_number or h.meta.heading_title or ""
                raw_parts.append(f"[{header}]\n{h.content[:300]}")
            if raw_parts:
                fallback_text = "\n\n---\n相关资料如下：\n" + "\n\n".join(raw_parts)
                yield f"data: {fallback_text}\n\n"
                full_answer = fallback_text

        if not full_answer:
            yield "data: 系统暂时无法处理此问题，请稍后再试。\n\n"
            full_answer = "系统暂时无法处理此问题，请稍后再试。"

        # 缓存（仅缓存正常 LLM 生成结果，不缓存降级原文片段）
        try:
            if "相关资料如下：" not in full_answer:
                answer_cache.set(question, tenant, clearance, full_answer, ttl=3600)
        except Exception:
            pass

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Request-ID": request_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def _retrieve(
    question: str,
    top_k: int,
    meta_filter: Optional[MetaFilter],
    request_id: str,
) -> list:
    """检索：向量库 → BM25 兜底。

    P3 优化：retriever 全局单例，BM25 索引只构建一次，避免每次请求重建。
    """
    from app.access.app import _get_repo
    from app.index.embedder import CachedEmbedder
    from app.retrieve.hybrid import HybridRetriever
    from app.retrieve.query_understanding import QueryUnderstanding

    global _retriever_instance
    repo = _get_repo()
    embedder = CachedEmbedder(repo._embedder)

    if _retriever_instance is None:
        query_understanding = QueryUnderstanding()
        _retriever_instance = HybridRetriever(
            repo=repo, embedder=embedder,
            rrf_k=settings.retrieval.rrf_k,
            query_understanding=query_understanding,
        )
        logger.info("global retriever initialized (BM25 built once, rrf_k=%d)", settings.retrieval.rrf_k)

    retriever = _retriever_instance
    intent = retriever._qu.analyze(question)

    try:
        hits = retriever.search(question, top_k=top_k, meta_filter=meta_filter, boost_sparse=intent.boost_sparse)
        logger.info("retrieval ok: request_id=%s hits=%d", request_id, len(hits))
        return hits
    except Exception as e:
        logger.error("vector search failed, trying BM25: %s", e)
        metrics.degrade_total.labels(layer="bm25").inc()
        try:
            hits = retriever._bm25_search(question, top_k=top_k * 2, meta_filter=meta_filter)
            logger.info("BM25 fallback ok: request_id=%s hits=%d", request_id, len(hits))
            return hits
        except Exception as e2:
            logger.error("BM25 also failed: %s", e2)
            return []


async def _llm_generate(
    question: str,
    hits: list,
    request_id: str,
    fallback_provider: Any,
) -> str:
    """LLM 生成：主模型 → 备用 → 原文片段 → 通用兜底。"""
    from app.generate.llm_client import DeepSeekClient

    llm = DeepSeekClient(
        api_key=settings.llm.api_key, base_url=settings.llm.base_url, model=settings.llm.model,
        fallback_api_key=settings.llm.fallback_api_key or None,
        fallback_base_url=settings.llm.fallback_base_url or None,
        fallback_model=settings.llm.fallback_model or None,
    )
    max_chars = settings.generate.context_max_chars // max(len(hits), 1)
    context = "\n\n".join(f"[{h.meta.heading_number}]\n{h.content[:max_chars]}" for h in hits)
    system_prompt = (
        "你是一个企业知识库助手，基于以下资料回答用户问题。"
        "只能依据提供的资料作答，不得臆测。"
        "如果资料中没有答案，请明确说明'资料中未提及'，不要编造。"
        "回答时注明所依据的资料出处。"
    )
    user_prompt = f"参考资料：\n{context}\n\n问题：{question}"

    try:
        answer = await llm.generate(system_prompt, user_prompt)
        if answer:
            logger.info("LLM generation ok: request_id=%s answer_len=%d", request_id, len(answer))
            return answer
    except Exception as e:
        logger.error("LLM generation failed: %s", e)

    # 降级：原文片段
    metrics.degrade_total.labels(layer="llm_fallback").inc()
    logger.warning("LLM empty, using raw text snippets: request_id=%s", request_id)
    raw_parts = []
    max_chars = settings.generate.context_max_chars // len(hits[:3]) if hits else 500
    for h in hits[:3]:
        header = h.meta.heading_number or h.meta.heading_title or ""
        raw_parts.append(f"[{header}]\n{h.content[:max_chars]}")
    if raw_parts:
        return "\n\n---\n相关资料如下：\n" + "\n\n".join(raw_parts)

    # 通用兜底
    try:
        generic_rule = fallback_provider.get_fallback_rule()
        if generic_rule:
            return generic_rule.answer
    except Exception:
        pass

    return "系统暂时无法处理此问题，请稍后再试。"


# ============================================================
# 问答接口
# ============================================================
# 降级链路（全程有响应不 500）：
#   向量库挂 → BM25 兜底
#   LLM 挂 → 原文片段 → 通用兜底规则 → 友好提示
# ============================================================

@router.get("/dashboard")
async def dashboard():
    """返回测试面板 HTML 页面。"""
    from pathlib import Path

    from fastapi.responses import HTMLResponse
    html_path = Path(__file__).resolve().parent.parent.parent / "static" / "test_dashboard.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>test_dashboard.html not found</h1>", status_code=404)


@router.post("/qa", response_model=QAResponse)
async def qa(req: QARequest, request: Request, db: Session = Depends(get_db)):
    """问答：接收问题，返回答案 + 来源引用。"""
    ctx = get_current_context()
    request_id = ctx.request_id if ctx else ""

    logger.info("qa request: question=%s top_k=%d stream=%s", req.question[:50], req.top_k, req.stream)

    # 权限过滤
    meta_filter: Optional[MetaFilter] = getattr(request.state, "meta_filter", None)
    logger.info("qa meta_filter=%s", meta_filter)

    # ============================================================
    # 降级链路 0：提示词注入检测（防诱导套话）
    # ============================================================
    injection = _injection_detector.analyze(req.question)
    if injection.detected:
        logger.warning(
            "prompt injection blocked: request_id=%s category=%s confidence=%.2f",
            request_id, injection.category, injection.confidence,
        )
        metrics.injection_total.labels(category=injection.category).inc()
        try:
            tenant = meta_filter.tenant_id if meta_filter else "default"
            clearance = meta_filter.max_classification.value if meta_filter and meta_filter.max_classification else "none"
            crud.create_query_log(
                db=db, trace_id=request_id, tenant_id=tenant, user_clearance=clearance,
                question=req.question, top_k=req.top_k, injection_blocked=True,
            )
        except Exception:
            pass
        return QAResponse(
            answer="抱歉，我无法回答这个问题。请提出合规的问题。",
            sources=[],
            request_id=request_id,
        )

    # 检查缓存
    tenant = meta_filter.tenant_id if meta_filter else "default"
    clearance = meta_filter.max_classification.value if meta_filter and meta_filter.max_classification else "none"
    try:
        cached_answer = _answer_cache.get(req.question, tenant, clearance)
        if cached_answer:
            logger.info("qa answer cache hit: request_id=%s", request_id)
            metrics.cache_hits_total.labels(namespace="answer").inc()
            if req.stream:
                async def stream_cached():
                    yield f"data: {cached_answer}\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(
                    stream_cached(),
                    media_type="text/event-stream",
                    headers={
                        "X-Request-ID": request_id,
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
            return QAResponse(
                answer=cached_answer,
                sources=[],
                request_id=request_id,
            )
    except Exception as e:
        logger.warning("cache read failed, skipping: %s", e)

    # 流式输出
    if req.stream:
        return await _qa_stream(
            question=req.question,
            top_k=req.top_k,
            meta_filter=meta_filter,
            request_id=request_id,
            answer_cache=_answer_cache,
            tenant=tenant,
            clearance=clearance,
        )

    return await _qa_json(
        question=req.question,
        top_k=req.top_k,
        meta_filter=meta_filter,
        request_id=request_id,
        answer_cache=_answer_cache,
        tenant=tenant,
        clearance=clearance,
        db=db,
    )


# ============================================================
# 入库接口
# ============================================================

@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    """入库（异步）：提交文件路径，后台 Celery 处理，不阻塞问答。

    支持格式：PDF、Word (.docx)、Markdown (.md)、TXT (.txt)
    通过 ReaderFactory 自动识别文件类型，不需手动指定。
    """
    ctx = get_current_context()
    request_id = ctx.request_id if ctx else ""

    logger.info("ingest request: file_path=%s request_id=%s", req.file_path, request_id)

    from app.ingest.tasks import ingest_file_task

    task = ingest_file_task.delay(
        file_path=req.file_path,
        doc_name=req.doc_name or None,
        classification=req.classification,
    )
    logger.info("ingest task dispatched: task_id=%s", task.id)

    return IngestResponse(
        status="pending",
        task_id=task.id,
        message="入库任务已提交，请通过 GET /ingest/{task_id} 查询进度",
        request_id=request_id,
    )


@router.get("/ingest/{task_id}", response_model=TaskStatusResponse)
async def ingest_status(task_id: str):
    """查询入库任务状态。"""
    ctx = get_current_context()
    request_id = ctx.request_id if ctx else ""

    result = AsyncResult(task_id, app=celery_app)
    status = result.status.lower()

    response = TaskStatusResponse(
        task_id=task_id,
        status=status,
        request_id=request_id,
    )

    if result.ready():
        if result.successful():
            response.result = result.result
        else:
            response.result = {"error": str(result.result)}

    return response


# ============================================================
# 批量入库接口（按文件名解析密级）
# ============================================================

@router.post("/ingest/by-name", response_model=BatchIngestResponse)
async def ingest_by_name(req: BatchIngestRequest):
    """批量入库（按文件名解析密级）。

    文件名规范：{任意名称}_{PUBLIC|INTERNAL|CONFIDENTIAL|SECRET}.{ext}
    示例：
      公司简介_PUBLIC.txt      → 密级: public
      内部纪要_INTERNAL.docx   → 密级: internal
      核心财务_confidential.pdf → 密级: confidential

    校验规则：先校验全部文件名，全部合法才开始入库；
    有一个不合法就拒绝整批，不处理任何文件。
    """
    ctx = get_current_context()
    request_id = ctx.request_id if ctx else ""

    logger.info("batch ingest by-name: %d files request_id=%s", len(req.file_paths), request_id)

    from app.ingest.name_classifier import validate_batch_files

    # 1. 校验全部文件名
    results = validate_batch_files(req.file_paths)
    total = len(results)
    passed = [r for r in results if r.is_valid]
    rejected = [r for r in results if not r.is_valid]

    # 2. 有不合格的 -> 拒绝整批
    if rejected:
        logger.warning(
            "batch ingest rejected: %d/%d files failed name validation",
            len(rejected), total,
        )
        return BatchIngestResponse(
            status="rejected",
            total_files=total,
            passed_files=0,
            rejected_files=[
                BatchIngestErrorItem(file_path=r.file_path, error=r.error)
                for r in rejected
            ],
            request_id=request_id,
        )

    # 3. 全部合格 -> 逐个提交入库任务
    from app.ingest.tasks import ingest_file_task

    task_ids = []
    for r in passed:
        doc_name = r.clean_name
        task = ingest_file_task.delay(
            file_path=r.file_path,
            doc_name=doc_name,
            classification=r.classification.value,
        )
        task_ids.append(task.id)
        logger.info(
            "batch ingest dispatched: file=%s doc_name=%s classification=%s task_id=%s",
            r.file_path, doc_name, r.classification.value, task.id,
        )

    return BatchIngestResponse(
        status="all_passed",
        total_files=total,
        passed_files=len(passed),
        rejected_files=[],
        task_ids=task_ids,
        request_id=request_id,
    )


# ============================================================
# 管理 API（P4 新增）
# ============================================================

class FeedbackRequest(BaseModel):
    query_log_id: int = Field(..., description="查询日志 ID")
    feedback_type: str = Field(..., description="反馈类型：up / down / correction")
    corrected_answer: str = Field(default="", description="纠正后的答案（correction 类型时填写）")
    comment: str = Field(default="", description="补充说明")


class FeedbackResponse(BaseModel):
    status: str = ""
    feedback_id: int = 0
    message: str = ""


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    """用户反馈：点赞 / 点踩 / 纠正答案。"""
    valid_types = {"up", "down", "correction"}
    if req.feedback_type not in valid_types:
        return FeedbackResponse(status="error", message=f"feedback_type must be one of {valid_types}")

    fb = crud.create_feedback(
        db=db,
        query_log_id=req.query_log_id,
        feedback_type=req.feedback_type,
        corrected_answer=req.corrected_answer or None,
        comment=req.comment or None,
    )
    return FeedbackResponse(status="ok", feedback_id=fb.id, message="反馈已提交")


@router.get("/documents")
async def list_documents(
    status: str = "",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """文档列表：查看入库文档及其状态。"""
    docs = crud.get_documents(db, status=status or None, limit=limit, offset=offset)
    return {
        "total": len(docs),
        "documents": [
            {
                "id": d.id,
                "doc_name": d.doc_name,
                "file_type": d.file_type,
                "classification": d.classification,
                "chunk_count": d.chunk_count,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
    }


@router.get("/query-logs")
async def list_query_logs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """查询日志：查看最近的问答请求。"""
    logs = crud.get_query_logs(db, limit=limit, offset=offset)
    return {
        "total": len(logs),
        "logs": [
            {
                "id": log.id,
                "trace_id": log.trace_id,
                "question": log.question[:100],
                "sources_count": log.sources_count,
                "answer_preview": log.answer_preview[:200] if log.answer_preview else None,
                "elapsed_ms": log.elapsed_ms,
                "cache_hit": log.cache_hit,
                "degraded": log.degraded,
                "injection_blocked": log.injection_blocked,
                "llm_used": log.llm_used,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.get("/feedbacks")
async def list_feedbacks(
    feedback_type: str = "",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """反馈列表：查看用户反馈。"""
    fbs = crud.get_feedbacks(db, feedback_type=feedback_type or None, limit=limit, offset=offset)
    return {
        "total": len(fbs),
        "feedbacks": [
            {
                "id": f.id,
                "query_log_id": f.query_log_id,
                "feedback_type": f.feedback_type,
                "corrected_answer": f.corrected_answer,
                "comment": f.comment,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in fbs
        ],
    }


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """系统统计：文档数 / 切片数 / 查询数 / 反馈数。"""
    return crud.get_stats(db)

# ============================================================
# 认证接口（P5 新增：账号密码登录 → 密级由账号决定）
# ============================================================

class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    status: str = ""
    token: str = ""
    expires_in: int = 0
    user: dict = {}
    message: str = ""


@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """账号密码登录。

    登录成功后返回 token，token 中携带该账号的密级与租户。
    后续请求用 `Authorization: Bearer <token>` 携带，服务端据此过滤可见文档，
    客户端**无法**再通过请求头修改自己的密级。
    """
    from app.auth.service import create_token, verify_password

    user = crud.get_user_by_username(db, req.username)

    # 统一失败文案：不区分"用户不存在"与"密码错误"，避免账号枚举
    fail = LoginResponse(status="error", message="用户名或密码错误")

    if user is None or not user.is_active:
        logger.warning("login failed: unknown or inactive user=%s", req.username)
        return fail

    if not verify_password(req.password, user.salt, user.password_hash):
        logger.warning("login failed: bad password for user=%s", req.username)
        return fail

    token, ttl = create_token(
        uid=user.id,
        username=user.username,
        clearance=user.clearance,
        tenant_id=user.tenant_id,
        dept=user.dept,
    )
    crud.touch_last_login(db, user)

    logger.info("login ok: user=%s clearance=%s tenant=%s",
                user.username, user.clearance, user.tenant_id)
    return LoginResponse(
        status="ok",
        token=token,
        expires_in=ttl,
        user={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "clearance": user.clearance,
            "tenant_id": user.tenant_id,
            "dept": user.dept,
        },
        message="登录成功",
    )


@router.get("/auth/me")
async def auth_me(request: Request):
    """返回当前登录身份（未登录时返回匿名身份）。"""
    u = getattr(request.state, "auth_user", None)
    if not u:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": getattr(request.state, "auth_mode", "anonymous") == "token",
        "mode": getattr(request.state, "auth_mode", "anonymous"),
        "user": u,
    }
