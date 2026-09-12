"""Alembic 迁移环境。

与官方模板的差别（两处都是为了避开常见事故）：

1. **数据库 URL 从 `config.settings` 读取**，不在 `alembic.ini` 里再写一份。
   否则改了 `.env` 却没改 `alembic.ini`，就会出现"迁移打在 A 库、服务连着 B 库"
   —— 这是迁移类事故最常见的原因。

2. **显式导入 `app.db.models`**，确保 `Base.metadata` 收齐所有表定义。
   若漏导入，autogenerate 会认为这些表不存在，从而生成一堆 DROP TABLE。

另：SQLite 对多数 `ALTER TABLE` 不支持，故启用 `render_as_batch`（以重建表的方式
实现字段变更）。若将来切到 PostgreSQL，该选项无副作用，可保留。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import models  # noqa: F401,E402 —— 导入以注册所有表到 metadata
from app.db.database import Base  # noqa: E402
from config.settings import settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 与运行时同源，避免"迁移的库"与"服务连的库"不一致
config.set_main_option("sqlalchemy.url", settings.database.url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只输出 SQL，不连接数据库。"""
    context.configure(
        url=settings.database.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移（默认）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
