"""ORM 模型定义 — 8 张企业级表。

表关系：
  documents 1───n chunks
  documents 1───n ingestion_tasks
  query_logs 1───n query_sources
  query_logs 1───n user_feedback
  query_logs 1───1 evaluation_results
  users（独立表：账号即密级来源）

设计原则：
  - 主键用 BIGINT AUTOINCREMENT（PostgreSQL 迁移无碍）
  - 时间戳统一 UTC + ISO8601 字符串（SQLite 无原生 DateTime）
  - 枚举值用字符串存储（避免跨库枚举兼容问题）
  - 软删除用 deleted_at 字段，不物理删除
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pk():
    """主键列：SQLite 用 Integer autoincrement，PostgreSQL 用 BigInteger。"""
    from sqlalchemy import Integer
    return mapped_column(Integer, primary_key=True, autoincrement=True)


# ============================================================
# 1. 文档管理表
# ============================================================
class Document(Base):
    """文档元信息：管理入库文档的全生命周期。"""

    __tablename__ = "documents"

    id: Mapped[int] = _pk()
    doc_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf/docx/md/txt
    classification: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending → processing → ready / failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list[ChunkMeta]] = relationship(back_populates="document", cascade="all, delete-orphan")
    ingestion_tasks: Mapped[list[IngestionTask]] = relationship(back_populates="document")

    __table_args__ = (
        Index("ix_documents_tenant_status", "tenant_id", "status"),
    )


# ============================================================
# 2. 切片元信息表
# ============================================================
class ChunkMeta(Base):
    """切片元信息：ChromaDB 的结构化镜像，支持 SQL 查询和统计。"""

    __tablename__ = "chunks"

    id: Mapped[int] = _pk()
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # ChromaDB 中的 ID
    heading_number: Mapped[str] = mapped_column(String(128), nullable=True)
    heading_title: Mapped[str] = mapped_column(String(256), nullable=True)
    heading_level: Mapped[int] = mapped_column(Integer, default=1)
    content_preview: Mapped[str] = mapped_column(Text, nullable=True)  # 前 200 字符
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_doc_chunk", "document_id", "chunk_index"),
    )


# ============================================================
# 3. 查询日志表
# ============================================================
class QueryLog(Base):
    """每次问答请求的完整日志：用于可观测性和评测。"""

    __tablename__ = "query_logs"

    id: Mapped[int] = _pk()
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    user_clearance: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    sources_count: Mapped[int] = mapped_column(Integer, default=0)
    answer_preview: Mapped[str] = mapped_column(Text, nullable=True)  # 前 500 字符
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(default=False)
    degraded: Mapped[bool] = mapped_column(default=False)
    injection_blocked: Mapped[bool] = mapped_column(default=False)
    llm_used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    sources: Mapped[list[QuerySource]] = relationship(back_populates="query_log", cascade="all, delete-orphan")
    feedbacks: Mapped[list[UserFeedback]] = relationship(back_populates="query_log", cascade="all, delete-orphan")
    evaluation: Mapped[EvaluationResult | None] = relationship(back_populates="query_log", uselist=False)

    __table_args__ = (
        Index("ix_query_logs_tenant_created", "tenant_id", "created_at"),
    )


# ============================================================
# 4. 查询来源表
# ============================================================
class QuerySource(Base):
    """每次查询返回的检索来源：记录排名和分数，用于评测。"""

    __tablename__ = "query_sources"

    id: Mapped[int] = _pk()
    query_log_id: Mapped[int] = mapped_column(ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = Top-1
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=True)
    doc_name: Mapped[str] = mapped_column(String(256), nullable=True)
    heading_number: Mapped[str] = mapped_column(String(128), nullable=True)
    dense_score: Mapped[float] = mapped_column(Float, default=0.0)
    sparse_score: Mapped[float] = mapped_column(Float, default=0.0)
    rrf_score: Mapped[float] = mapped_column(Float, default=0.0)

    query_log: Mapped[QueryLog] = relationship(back_populates="sources")


# ============================================================
# 5. 用户反馈表
# ============================================================
class UserFeedback(Base):
    """用户对回答的反馈：点赞/点踩/纠正，用于 bad case 回流。"""

    __tablename__ = "user_feedback"

    id: Mapped[int] = _pk()
    query_log_id: Mapped[int] = mapped_column(ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)  # up / down / correction
    corrected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    query_log: Mapped[QueryLog] = relationship(back_populates="feedbacks")

    __table_args__ = (
        Index("ix_feedback_type_created", "feedback_type", "created_at"),
    )


# ============================================================
# 6. 评测结果表
# ============================================================
class EvaluationResult(Base):
    """自动评测指标：recall@k / faithfulness / 幻觉率。"""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = _pk()
    query_log_id: Mapped[int] = mapped_column(ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False, unique=True)
    recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0.0 ~ 1.0
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0.0 ~ 1.0
    hallucination_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0.0 ~ 1.0
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    query_log: Mapped[QueryLog] = relationship(back_populates="evaluation")


# ============================================================
# 7. 入库任务表
# ============================================================
class IngestionTask(Base):
    """Celery 入库任务追踪：记录异步入库的执行状态。"""

    __tablename__ = "ingestion_tasks"

    id: Mapped[int] = _pk()
    celery_task_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    classification: Mapped[str] = mapped_column(String(20), default="public")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending → started → success / failure
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped[Document | None] = relationship(back_populates="ingestion_tasks")

    __table_args__ = (
        Index("ix_ingest_tasks_status", "status"),
    )


# ============================================================
# 8. 用户表（账号密码登录 → 密级由账号决定）
# ============================================================
class User(Base):
    """用户账号。

    密级（clearance）由账号本身决定，客户端无法通过请求头篡改。
    口令用 PBKDF2-HMAC-SHA256 + 随机盐存储，不保存明文。
    """

    __tablename__ = "users"

    id: Mapped[int] = _pk()
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    clearance: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", index=True)
    dept: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_users_tenant", "tenant_id"),
    )
