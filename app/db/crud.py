"""CRUD 操作层：封装所有数据库读写，上层不直接操作 ORM。

设计原则：
  - 每个函数接收 session 作为第一个参数（FastAPI Depends 注入）
  - 写操作自动 commit，异常自动 rollback
  - 查询返回 ORM 对象或列表，不返回 dict（由路由层序列化）
  - 所有操作都有日志记录
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.cross.logging import get_logger
from app.db.models import (
    ChunkMeta,
    Document,
    EvaluationResult,
    IngestionTask,
    QueryLog,
    QuerySource,
    User,
    UserFeedback,
)

logger = get_logger(__name__)


# ============================================================
# 文档管理
# ============================================================

def create_document(
    db: Session,
    doc_name: str,
    file_path: str,
    file_type: str,
    classification: str = "public",
    tenant_id: str = "default",
) -> Document:
    """创建文档记录。"""
    doc = Document(
        doc_name=doc_name,
        file_path=file_path,
        file_type=file_type,
        classification=classification,
        tenant_id=tenant_id,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info("document created: id=%d name=%s", doc.id, doc.doc_name)
    return doc


def update_document_status(
    db: Session,
    doc_id: int,
    status: str,
    chunk_count: int = 0,
    error_message: str | None = None,
) -> Optional[Document]:
    """更新文档状态。"""
    doc = db.get(Document, doc_id)
    if not doc:
        return None
    doc.status = status
    if chunk_count:
        doc.chunk_count = chunk_count
    if error_message:
        doc.error_message = error_message
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return doc


def get_documents(
    db: Session,
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Document]:
    """查询文档列表。"""
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if tenant_id:
        stmt = stmt.where(Document.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(Document.status == status)
    stmt = stmt.order_by(desc(Document.created_at)).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_document_by_id(db: Session, doc_id: int) -> Optional[Document]:
    return db.get(Document, doc_id)


# ============================================================
# 切片元信息
# ============================================================

def bulk_create_chunks(db: Session, document_id: int, chunks: list[dict]) -> int:
    """批量创建切片记录。

    Args:
        chunks: [{chunk_id, chunk_index, heading_number, heading_title,
                  heading_level, content_preview, token_count, classification}]
    Returns: 创建数量
    """
    if not chunks:
        return 0
    objects = [ChunkMeta(document_id=document_id, **c) for c in chunks]
    db.add_all(objects)
    db.commit()
    logger.info("chunks created: doc_id=%d count=%d", document_id, len(objects))
    return len(objects)


def get_chunks_by_doc(db: Session, document_id: int) -> list[ChunkMeta]:
    stmt = (
        select(ChunkMeta)
        .where(ChunkMeta.document_id == document_id)
        .order_by(ChunkMeta.chunk_index)
    )
    return list(db.execute(stmt).scalars().all())


# ============================================================
# 查询日志
# ============================================================

def create_query_log(
    db: Session,
    trace_id: str,
    tenant_id: str,
    user_clearance: str,
    question: str,
    top_k: int,
    sources_count: int = 0,
    answer_preview: str | None = None,
    elapsed_ms: int = 0,
    cache_hit: bool = False,
    degraded: bool = False,
    injection_blocked: bool = False,
    llm_used: bool = False,
) -> QueryLog:
    """记录一次问答请求。"""
    log = QueryLog(
        trace_id=trace_id,
        tenant_id=tenant_id,
        user_clearance=user_clearance,
        question=question,
        top_k=top_k,
        sources_count=sources_count,
        answer_preview=answer_preview[:500] if answer_preview else None,
        elapsed_ms=elapsed_ms,
        cache_hit=cache_hit,
        degraded=degraded,
        injection_blocked=injection_blocked,
        llm_used=llm_used,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def add_query_sources(db: Session, query_log_id: int, sources: list[dict]) -> int:
    """批量添加查询来源。

    Args:
        sources: [{rank, chunk_id, doc_name, heading_number,
                   dense_score, sparse_score, rrf_score}]
    """
    if not sources:
        return 0
    objects = [QuerySource(query_log_id=query_log_id, **s) for s in sources]
    db.add_all(objects)
    db.commit()
    return len(objects)


def get_query_logs(
    db: Session,
    tenant_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[QueryLog]:
    """查询日志列表。"""
    stmt = select(QueryLog)
    if tenant_id:
        stmt = stmt.where(QueryLog.tenant_id == tenant_id)
    stmt = stmt.order_by(desc(QueryLog.created_at)).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_query_log_by_trace(db: Session, trace_id: str) -> Optional[QueryLog]:
    stmt = select(QueryLog).where(QueryLog.trace_id == trace_id)
    return db.execute(stmt).scalar_one_or_none()


# ============================================================
# 用户反馈
# ============================================================

def create_feedback(
    db: Session,
    query_log_id: int,
    feedback_type: str,
    corrected_answer: str | None = None,
    comment: str | None = None,
) -> UserFeedback:
    """创建用户反馈。"""
    fb = UserFeedback(
        query_log_id=query_log_id,
        feedback_type=feedback_type,
        corrected_answer=corrected_answer,
        comment=comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    logger.info("feedback created: query_log_id=%d type=%s", query_log_id, feedback_type)
    return fb


def get_feedbacks(
    db: Session,
    feedback_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[UserFeedback]:
    """查询反馈列表。"""
    stmt = select(UserFeedback)
    if feedback_type:
        stmt = stmt.where(UserFeedback.feedback_type == feedback_type)
    stmt = stmt.order_by(desc(UserFeedback.created_at)).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_negative_feedbacks(db: Session, limit: int = 20) -> list[UserFeedback]:
    """获取点踩反馈（bad case 回流用）。"""
    stmt = (
        select(UserFeedback)
        .where(UserFeedback.feedback_type == "down")
        .order_by(desc(UserFeedback.created_at))
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


# ============================================================
# 评测结果
# ============================================================

def create_evaluation(
    db: Session,
    query_log_id: int,
    recall_at_k: float | None = None,
    faithfulness: float | None = None,
    hallucination_rate: float | None = None,
) -> EvaluationResult:
    """记录评测结果。"""
    ev = EvaluationResult(
        query_log_id=query_log_id,
        recall_at_k=recall_at_k,
        faithfulness=faithfulness,
        hallucination_rate=hallucination_rate,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


# ============================================================
# 入库任务
# ============================================================

def create_ingestion_task(
    db: Session,
    celery_task_id: str,
    file_path: str,
    doc_name: str | None = None,
    classification: str = "public",
) -> IngestionTask:
    """记录 Celery 入库任务。"""
    task = IngestionTask(
        celery_task_id=celery_task_id,
        file_path=file_path,
        doc_name=doc_name,
        classification=classification,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_ingestion_task(
    db: Session,
    celery_task_id: str,
    status: str,
    document_id: int | None = None,
    error_message: str | None = None,
) -> Optional[IngestionTask]:
    """更新入库任务状态。"""
    stmt = select(IngestionTask).where(IngestionTask.celery_task_id == celery_task_id)
    task = db.execute(stmt).scalar_one_or_none()
    if not task:
        return None
    task.status = status
    if document_id:
        task.document_id = document_id
    if error_message:
        task.error_message = error_message
    if status == "started" and not task.started_at:
        task.started_at = datetime.now(timezone.utc)
    if status in ("success", "failure"):
        task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


# ============================================================
# 统计
# ============================================================

def get_stats(db: Session) -> dict:
    """系统概览统计。"""
    doc_count = db.execute(select(func.count(Document.id)).where(Document.deleted_at.is_(None))).scalar() or 0
    chunk_count = db.execute(select(func.count(ChunkMeta.id))).scalar() or 0
    query_count = db.execute(select(func.count(QueryLog.id))).scalar() or 0
    feedback_count = db.execute(select(func.count(UserFeedback.id))).scalar() or 0
    up_count = db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.feedback_type == "up")
    ).scalar() or 0
    down_count = db.execute(
        select(func.count(UserFeedback.id)).where(UserFeedback.feedback_type == "down")
    ).scalar() or 0
    pending_tasks = db.execute(
        select(func.count(IngestionTask.id)).where(IngestionTask.status.in_(["pending", "started"]))
    ).scalar() or 0

    return {
        "documents": doc_count,
        "chunks": chunk_count,
        "queries": query_count,
        "feedbacks": feedback_count,
        "up_votes": up_count,
        "down_votes": down_count,
        "pending_ingestion_tasks": pending_tasks,
    }


# ============================================================
# 用户（认证）
# ============================================================

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """按用户名查用户（未找到返回 None）。"""
    return db.execute(select(User).where(User.username == username)).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def create_user(
    db: Session,
    username: str,
    password: str,
    clearance: str = "public",
    display_name: str = "",
    tenant_id: str = "default",
    dept: str = "default",
) -> User:
    """创建用户（口令在内部完成加盐哈希）。"""
    from app.auth.service import hash_password, new_salt

    salt = new_salt()
    u = User(
        username=username,
        password_hash=hash_password(password, salt),
        salt=salt,
        display_name=display_name or username,
        clearance=clearance,
        tenant_id=tenant_id,
        dept=dept,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    logger.info("user created: %s clearance=%s tenant=%s", username, clearance, tenant_id)
    return u


def touch_last_login(db: Session, user: User) -> None:
    """更新最后登录时间。"""
    try:
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("failed to update last_login_at: %s", e)


def count_users(db: Session) -> int:
    return db.execute(select(func.count(User.id))).scalar() or 0


def list_users(db: Session, limit: int = 100) -> list[User]:
    return list(db.execute(select(User).limit(limit)).scalars().all())
