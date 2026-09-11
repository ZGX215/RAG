"""异步入库任务（Celery task）。

P2 的入库是同步阻塞的——上传大文件时接口会卡死。
P3 改为异步：接受请求后立即返回 task_id，后台慢慢处理。
P3 新增：通过 ReaderFactory 自动识别文件格式（PDF/Word/Markdown/TXT）。
"""

from __future__ import annotations

from pathlib import Path

from app.cross.celery_app import celery_app
from app.cross.logging import get_logger
from app.index.chroma_repo import ChromaRepository
from app.index.embedder import SentenceEmbedder, CachedEmbedder
from app.ingest.reader_factory import get_reader_factory
from config.settings import settings

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_file_task(self, file_path: str, doc_name: str | None = None, classification: str = "public") -> dict:
    """通用异步入库：自动识别文件格式 → 读取分块 → 写入 ChromaDB。

    支持格式：.pdf, .docx, .md, .txt（通过 ReaderFactory）。
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "status": "error",
            "task_id": self.request.id,
            "error": f"file not found: {file_path}",
        }

    logger.info("ingest_file_task: reading %s classification=%s", file_path, classification)

    title = doc_name or path.stem
    try:
        factory = get_reader_factory()
        reader = factory.get_reader(str(path))
        chunks = reader.read(str(path), doc_name=title)
    except ValueError as e:
        logger.error("unsupported file format: %s", e)
        return {
            "status": "error",
            "task_id": self.request.id,
            "error": str(e),
        }
    except Exception as e:
        logger.error("failed to read file: %s", e)
        return {
            "status": "error",
            "task_id": self.request.id,
            "error": str(e),
        }

    if not chunks:
        return {
            "status": "error",
            "task_id": self.request.id,
            "error": "no content extracted from file",
        }

    logger.info("ingest_file_task: extracted %d chunks", len(chunks))

    # 应用密级标记
    from app.contracts import ChunkTypeClassification
    try:
        cls_level = ChunkTypeClassification(classification.lower())
    except ValueError:
        logger.warning("invalid classification=%s, using public", classification)
        cls_level = ChunkTypeClassification.PUBLIC
    for chunk in chunks:
        chunk.meta.classification = cls_level
        chunk.meta.extras["tenant_id"] = "default"
        chunk.meta.extras["dept"] = "default"

    embedder = CachedEmbedder(SentenceEmbedder())
    repo = ChromaRepository(
        embedder=embedder,
        persist_dir=settings.index.persist_dir,
        collection_name=settings.index.collection_name,
    )
    count = repo.upsert(chunks)
    logger.info("ingest_file_task: upserted %d chunks", count)

    return {
        "doc_name": title,
        "chunks": len(chunks),
        "upserted": count,
        "status": "done",
        "task_id": self.request.id,
    }


# 保留旧函数名给向下兼容
ingest_pdf_task = ingest_file_task