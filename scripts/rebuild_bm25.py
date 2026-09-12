"""重新构建 BM25 索引。

注意：BM25 索引是**进程内的内存结构**，服务重启时会自动从 Chroma 重建，
因此通常不需要单独执行本脚本。它只适用于"在同一个进程内向 repo 写入数据后，
想让该进程内的 BM25 索引立即生效"的场景。

（此前本脚本硬编码了 E:/trae/cede/mcu-rag-qa-v2 绝对路径，换机器即失效，
现改为从 config.settings 读取，与项目其它入口保持一致。）
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.index.chroma_repo import ChromaRepository  # noqa: E402
from app.index.embedder import SentenceEmbedder  # noqa: E402
from app.retrieve.hybrid import HybridRetriever  # noqa: E402
from config.settings import settings  # noqa: E402

embedder = SentenceEmbedder()
repo = ChromaRepository(
    embedder=embedder,
    persist_dir=settings.index.persist_dir,
    collection_name=settings.index.collection_name,
)

retriever = HybridRetriever(repo=repo, embedder=embedder)
retriever._ensure_bm25()  # noqa: SLF001 —— 本脚本的目的就是强制触发索引构建
print(f"BM25 索引重新构建完成：{len(retriever._bm25_chunks)} chunks")
