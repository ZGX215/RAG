"""项目路径与目录就绪（P1 最小可用版）

确保 ``data/`` 下各子目录在首次运行前即存在。
"""

from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """返回项目根目录（包含 config/ 和 app/ 的上级目录）。"""
    return Path(__file__).resolve().parent.parent.parent


def ensure_data_dirs() -> dict[str, Path]:
    """确保 data/ 下各子目录存在，返回 {名称: 路径} 映射。

    P1 阶段只需:
      - data/chroma_db/   — ChromaDB 持久化目录
      - data/logs/         — 日志文件
      - data/              — 根目录（含 structured.db）
    """
    root = get_project_root()
    data_dir = root / "data"

    dirs = {
        "data": data_dir,
        "chroma": data_dir / "chroma_db",
        "logs": data_dir / "logs",
    }

    for name, path in dirs.items():
        path.mkdir(parents=True, exist_ok=True)

    return dirs


def get_chroma_path() -> str:
    """返回 ChromaDB 持久化路径（字符串形式，供 chromadb 客户端使用）。"""
    return str(ensure_data_dirs()["chroma"])