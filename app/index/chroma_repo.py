"""ChromaRepository — IndexRepository 的 ChromaDB 实现。

P1 薄切片阶段对接 FakeEmbedder，验证通路。
P3 切换到真实 SentenceEmbedder。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import chromadb
from chromadb import Collection

from app.contracts import (
    Chunk,
    ChunkMeta,
    ChunkType,
    ChunkTypeClassification,
    CLASSIFICATION_LEVELS,
    Embedder,
    Hit,
    IndexRepository,
    MetaFilter,
)
from app.cross.logging import get_logger
from app.cross.paths import get_project_root

logger = get_logger(__name__)


class ChromaRepository:
    """基于 ChromaDB 的 IndexRepository 实现。

    P1 阶段使用 FakeEmbedder，确保通路可验证。
    """

    def __init__(
        self,
        embedder: Embedder,
        persist_dir: str = "./data/chroma_db",
        collection_name: str = "mcu_qa",
    ):
        self._embedder = embedder
        self._collection_name = collection_name

        # 解析路径：相对路径转为项目根目录下的绝对路径
        _path = Path(persist_dir)
        if not _path.is_absolute():
            _path = get_project_root() / _path
        self._persist_dir = _path.resolve().as_posix()

        logger.info(
            "initializing ChromaRepository: persist=%s collection=%s dim=%d",
            self._persist_dir, collection_name, embedder.dimension,
        )
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection: Collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB ready: %d docs", self._collection.count())

    def upsert(self, chunks: Sequence[Chunk]) -> int:
        """批量写入切片。"""
        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        ids = [c.chunk_id for c in chunks]
        embeddings = self._embedder.embed_texts(texts)
        metadatas = [_chunk_to_metadata(c) for c in chunks]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info("upserted %d chunks", len(chunks))
        return len(chunks)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        meta_filter: Optional[MetaFilter] = None,
    ) -> List[Hit]:
        """稠密向量检索。一次查询，不重复执行，按内容去重。"""
        where = _build_where(meta_filter) if meta_filter else None
        logger.debug("chroma search: where=%s meta_filter=%s", where, meta_filter)

        # 多查一些，去重后可能不够
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 3,
            where=where,
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        seen: set[tuple] = set()
        hits = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = _metadata_to_chunkmeta(results["metadatas"][0][i])
            dedup_key = (meta.doc_id, meta.heading_number, meta.chunk_index)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            hits.append(Hit(
                chunk_id=doc_id,
                content=results["documents"][0][i],
                meta=meta,
                dense_score=1.0 - results["distances"][0][i] if results["distances"] else 0.0,
            ))
            if len(hits) >= top_k:
                break
        return hits

    def delete_by_doc_id(self, doc_id: str) -> int:
        """按文档 ID 删除所有切片。"""
        results = self._collection.get(where={"doc_id": doc_id})
        ids = results["ids"]
        if ids:
            self._collection.delete(ids=ids)
            logger.info("deleted %d chunks for doc_id=%s", len(ids), doc_id)
        return len(ids)

    def get_all_chunks(self) -> List[Chunk]:
        """返回所有切片（供 BM25 构建语料库），按内容去重。

        去重键: (doc_id, heading_number, chunk_index)
        解决多次运行 p1_demo.py 产生 UUID 不同但内容相同的冗余数据。
        """
        results = self._collection.get()
        if not results["ids"]:
            return []
        seen: set[tuple[str, str, int]] = set()
        chunks: list[Chunk] = []
        for i, doc_id in enumerate(results["ids"]):
            meta = _metadata_to_chunkmeta(results["metadatas"][i])
            dedup_key = (meta.doc_id, meta.heading_number, meta.chunk_index)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            chunks.append(Chunk(
                chunk_id=doc_id,
                content=results["documents"][i],
                meta=meta,
            ))
        return chunks

    def count(self) -> int:
        return self._collection.count()

    def rebuild(self, embedder: Embedder, chunks: Sequence[Chunk]) -> None:
        """重建索引。"""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.upsert(chunks)

    def migrate_metadata(self) -> int:
        """迁移旧数据：补全 classification_level 字段。

        P3 Step 2 新增：旧数据入库时没有 classification_level，导致 $lte 过滤失效。
        遍历所有已有文档，只更新 metadata，不修改 embedding。
        Also adds default tenant_id="default" for backward compatibility.
        """
        results = self._collection.get()
        if not results["ids"]:
            return 0

        updated = 0
        for i, doc_id in enumerate(results["ids"]):
            meta = results["metadatas"][i]
            update_data = {}
            if "classification_level" not in meta:
                cls = meta.get("classification", "public")
                try:
                    level = CLASSIFICATION_LEVELS.get(
                        ChunkTypeClassification(cls), 0
                    )
                except ValueError:
                    level = 0
                update_data["classification_level"] = level
            if "tenant_id" not in meta:
                update_data["tenant_id"] = "default"
            if "dept" not in meta:
                update_data["dept"] = "default"
            if not update_data:
                continue
            self._collection.update(
                ids=[doc_id],
                metadatas=[update_data],
            )
            updated += 1

        if updated:
            logger.info("metadata migration: updated %d chunks with classification_level/tenant_id/dept", updated)
        return updated


# ============================================================
# 辅助函数
# ============================================================


def _build_where(f: MetaFilter) -> dict:
    """将 MetaFilter 转为 ChromaDB where 过滤条件。

    密级过滤用数值 $lte（ChromaDB 不支持字符串 <= 比较）。
    用户 clearance=CONFIDENTIAL → 可见 PUBLIC(0) + INTERNAL(1) + CONFIDENTIAL(2)。
    ChromaDB 要求多条件必须用 $and 包装。
    """
    conditions = []
    if f.tenant_id:
        conditions.append({"tenant_id": f.tenant_id})
    if f.allowed_depts:
        conditions.append({"dept": {"$in": f.allowed_depts}})
    if f.max_classification:
        max_level = CLASSIFICATION_LEVELS.get(f.max_classification, 0)
        conditions.append({"classification_level": {"$lte": max_level}})
    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _chunk_to_metadata(c: Chunk) -> dict:
    """Chunk → ChromaDB metadata dict。"""
    m = c.meta
    return {
        "doc_id": m.doc_id,
        "doc_name": m.doc_name,
        "mcu_model": m.mcu_model,
        "page_num": m.page_num,
        "heading_number": m.heading_number,
        "heading_title": m.heading_title,
        "heading_level": m.heading_level,
        "chunk_type": m.chunk_type.value,
        "chunk_index": m.chunk_index,
        "token_count": m.token_count,
        "classification": m.classification.value,
        "classification_level": CLASSIFICATION_LEVELS.get(m.classification, 0),
        "tenant_id": m.extras.get("tenant_id", "default"),
        "dept": m.extras.get("dept", "default"),
    }


def _metadata_to_chunkmeta(d: dict) -> ChunkMeta:
    """ChromaDB metadata dict → ChunkMeta。"""
    return ChunkMeta(
        doc_id=d.get("doc_id", ""),
        doc_name=d.get("doc_name", ""),
        mcu_model=d.get("mcu_model", ""),
        page_num=d.get("page_num", 0),
        heading_number=d.get("heading_number", ""),
        heading_title=d.get("heading_title", ""),
        heading_level=d.get("heading_level", 0),
        chunk_type=ChunkType(d.get("chunk_type", "text")),
        chunk_index=d.get("chunk_index", 0),
        token_count=d.get("token_count", 0),
        classification=__import__("app.contracts", fromlist=["ChunkTypeClassification"]).ChunkTypeClassification(
            d.get("classification", "public")
        ),
        extras={
            "tenant_id": d.get("tenant_id", "default"),
            "dept": d.get("dept", "default"),
        },
    )