"""baseline schema

Revision ID: 47335cb7e12e
Revises:
Create Date: 2026-09-12 16:22:13.195691

本迁移是**基线**：建立当前全部表结构。

为什么此处用 metadata 建表，而不是把 autogenerate 的建表语句抄进来：
    现有约 10 张表，逐表手抄既冗长，又容易随着模型改动而悄悄漂移。
    基线用 `Base.metadata.create_all()` 生成，能保证"从零建库"的结果
    与模型定义永远一致。
    后续的表结构变更仍走标准流程 —— `alembic revision --autogenerate`
    由 alembic 生成显式 DDL，不再依赖 metadata。

对**已经存在这些表**的数据库（例如本地已有数据的开发库）：
    不要直接 upgrade，请先执行 `alembic stamp head` 把它标记为"基线已应用"，
    否则会因表已存在而报错。全新环境则直接 `alembic upgrade head`。
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "47335cb7e12e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _metadata():
    """延迟导入，避免 alembic 加载迁移模块时就要解析应用配置。"""
    from app.db import models  # noqa: F401  —— 导入以注册全部表
    from app.db.database import Base

    return Base.metadata


def upgrade() -> None:
    """创建当前全部表结构。"""
    _metadata().create_all(bind=op.get_bind())


def downgrade() -> None:
    """删除全部表（注意：会丢失数据）。"""
    _metadata().drop_all(bind=op.get_bind())
