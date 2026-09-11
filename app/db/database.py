"""数据库引擎、会话工厂、Base 声明类、FastAPI 依赖注入。

架构设计：
  - Engine：全局单例，进程启动时创建一次
  - SessionFactory：sessionmaker 工厂，每次请求从中取一个 session
  - get_db()：FastAPI Depends 依赖，自动管理 session 生命周期（请求结束自动关闭）
  - Base：所有 ORM 模型的声明基类

连接池策略：
  - SQLite：不用连接池（SQLite 单写者限制），用 StaticPool 保证线程安全
  - PostgreSQL：QueuePool，pool_size=5, max_overflow=10
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config.settings import settings
from app.cross.logging import get_logger

logger = get_logger(__name__)

# 确保 SQLite 文件目录存在
_db_url = settings.database.url
if _db_url.startswith("sqlite:///"):
    _db_file = Path(_db_url.replace("sqlite:///", ""))
    _db_file.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# 引擎创建
# ============================================================
_is_sqlite = _db_url.startswith("sqlite")

if _is_sqlite:
    # SQLite 不用连接池，StaticPool 保证多线程共享同一个连接
    engine = create_engine(
        _db_url,
        echo=settings.database.echo,
        connect_args={"check_same_thread": False},
        poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    )
    # WAL 模式：允许多读单写，提高并发
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # PostgreSQL 用标准连接池
    engine = create_engine(
        _db_url,
        echo=settings.database.echo,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_recycle=settings.database.pool_recycle,
    )

# ============================================================
# 会话工厂
# ============================================================
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ============================================================
# 声明基类
# ============================================================
class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""
    pass


# ============================================================
# FastAPI 依赖注入
# ============================================================
def get_db() -> Generator:
    """FastAPI Depends 依赖：自动管理 session 生命周期。

    用法::

        @router.post("/feedback")
        async def feedback(db: Session = Depends(get_db)):
            crud.create_feedback(db, ...)
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """建表：在应用启动时调用一次。"""
    from app.db import models  # noqa: F401 — 触发模型注册
    Base.metadata.create_all(bind=engine)
    logger.info("database tables created: %s", engine.url)
