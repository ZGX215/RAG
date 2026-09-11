"""混合检索测试 - 用 FakeRepository + FakeEmbedder 测试 RRF 融合和权限过滤。

不依赖真实 ChromaDB 或 embedding 模型，全部用内存 Mock。

测试覆盖：
1. RRF 融合：稠密和稀疏结果合并后按 RRF 排序
2. boost_sparse 提高稀疏权重
3. 空查询返回空列表
4. 权限过滤：BM25 检索时过滤掉越权切片
5. 去重：相同 chunk 在稠密和稀疏结果中都出现时只保留一个
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from unittest.mock import patch

import pytest

from app.contracts import (
    Chunk,
    ChunkMeta,
    ChunkType,
    ChunkTypeClassification,
    Hit,
    MetaFilter,
)
from app.retrieve.hybrid import HybridRetriever


class FakeEmbedder:
    """假向量化器：返回固定维度的随机向量。"""

    def embed_texts(self, texts):
        import random
        return [[random.random() for _ in range(10)] for _ in texts]

    def embed_query(self, query):
        import random
        return [random.random() for _ in range(10)]

    @property
    def dimension(self):
        return 10


def _make_chunk(chunk_id, content, heading_number="", doc_id="doc1",
                classification=ChunkTypeClassification.PUBLIC,
                heading_title="", chunk_index=0):
    """快速构造测试用 Chunk。"""
    return Chunk(
        chunk_id=chunk_id,
        content=content,
        meta=ChunkMeta(
            doc_name="test", doc_id=doc_id, mcu_model="", page_num=0,
            heading_number=heading_number, heading_title=heading_title or heading_number,
            heading_level=1, chunk_type=ChunkType.TEXT, chunk_index=chunk_index,
            token_count=len(content),
            classification=classification,
        ),
    )


@pytest.fixture
def repo_with_chunks():
    """构造含 3 个切片的 FakeRepository。"""
    from app.contracts import FakeRepository

    repo = FakeRepository()
    chunks = [
        _make_chunk("c1", "算力基础设施是AI发展的底座", "第一章",
                     heading_title="算力基础设施", chunk_index=0),
        _make_chunk("c2", "安全合规是企业的红线要求", "第二章",
                     heading_title="安全合规", chunk_index=1),
        _make_chunk("c3", "人才培养是产业发展的关键", "第三章",
                     heading_title="人才培养", chunk_index=2),
    ]
    repo.upsert(chunks)
    return repo


@pytest.fixture
def retriever(repo_with_chunks):
    """构造 HybridRetriever，mock 掉 jieba 分词。"""
    embedder = FakeEmbedder()
    with patch("app.retrieve.hybrid.jieba"):
        r = HybridRetriever(
            repo=repo_with_chunks,
            embedder=embedder,
            rrf_k=5,
        )
    return r


class TestHybridSearch:

    def test_search_returns_results(self, retriever):
        """正常搜索返回结果。"""
        with patch.object(retriever, "_tokenize", return_value=["算力", "基础设施"]):
            results = retriever.search("算力基础设施", top_k=3)
        assert len(results) > 0
        assert all(isinstance(h, Hit) for h in results)

    def test_empty_query(self, retriever):
        """空查询返回空列表。"""
        results = retriever.search("", top_k=5)
        assert results == []

    def test_results_have_rrf_score(self, retriever):
        """融合后结果有 rerank_score（RRF 分数）。"""
        with patch.object(retriever, "_tokenize", return_value=["算力"]):
            results = retriever.search("算力", top_k=3)
        assert len(results) > 0
        assert all(h.rerank_score > 0 for h in results)

    def test_results_sorted_by_rrf(self, retriever):
        """结果按 RRF 分数降序排列。"""
        with patch.object(retriever, "_tokenize", return_value=["算力", "安全", "人才"]):
            results = retriever.search("算力安全人才", top_k=3)
        scores = [h.rerank_score for h in results]
        assert scores == sorted(scores, reverse=True)


class TestRRFFusion:

    def test_rrf_dedup(self, retriever):
        """稠密和稀疏返回相同 chunk 时，RRF 去重后只保留一个。"""
        dense_hits = [
            Hit(chunk_id="c1", content="content1",
                meta=ChunkMeta(doc_name="d", doc_id="doc1", mcu_model="",
                               page_num=0, heading_number="1", heading_title="t1",
                               heading_level=1, chunk_type=ChunkType.TEXT,
                               chunk_index=0, token_count=10),
                dense_score=0.9),
        ]
        sparse_hits = [
            Hit(chunk_id="c1", content="content1",
                meta=ChunkMeta(doc_name="d", doc_id="doc1", mcu_model="",
                               page_num=0, heading_number="1", heading_title="t1",
                               heading_level=1, chunk_type=ChunkType.TEXT,
                               chunk_index=0, token_count=10),
                sparse_score=0.8),
        ]
        result = retriever._rrf_fuse(dense_hits, sparse_hits, top_k=10)
        assert len(result) == 1
        # 去重后仍保留两个分数
        assert result[0].dense_score == 0.9
        assert result[0].sparse_score == 0.8

    def test_rrf_boost_sparse_increases_score(self, retriever):
        """boost_sparse=True 时稀疏排名权重更高。"""
        dense_hits = [
            Hit(chunk_id="c1", content="c1",
                meta=ChunkMeta(doc_name="d", doc_id="doc1", mcu_model="",
                               page_num=0, heading_number="1", heading_title="t1",
                               heading_level=1, chunk_type=ChunkType.TEXT,
                               chunk_index=0, token_count=10),
                dense_score=0.5),
        ]
        sparse_hits = [
            Hit(chunk_id="c2", content="c2",
                meta=ChunkMeta(doc_name="d", doc_id="doc2", mcu_model="",
                               page_num=0, heading_number="2", heading_title="t2",
                               heading_level=1, chunk_type=ChunkType.TEXT,
                               chunk_index=0, token_count=10),
                sparse_score=0.5),
        ]
        normal = retriever._rrf_fuse(dense_hits, sparse_hits, top_k=10, boost_sparse=False)
        boosted = retriever._rrf_fuse(dense_hits, sparse_hits, top_k=10, boost_sparse=True)

        # boost 后稀疏结果排名应该更高
        normal_sparse_score = next(h.rerank_score for h in normal if h.chunk_id == "c2")
        boosted_sparse_score = next(h.rerank_score for h in boosted if h.chunk_id == "c2")
        assert boosted_sparse_score > normal_sparse_score


class TestPermissionFilter:

    def test_bm25_filters_secret_chunks(self):
        """BM25 检索时过滤掉 SECRET 切片（用户只有 PUBLIC 权限）。

        ⚠️ 语料不能少于 3 个切片：rank_bm25 在 N=2 且每个词 df=1 时 idf 会算成 0，
        所有切片得分都是 0，会被 _bm25_search 的 `if score > 0` 全部丢弃。那种情况下
        "secret 被过滤"会【假通过】（结果集本来就是空的）。故这里刻意放足量
        中性切片把 idf 顶起来，并先断言结果非空，杜绝此类假通过。
        """
        from app.contracts import FakeRepository

        repo = FakeRepository()
        chunks = [
            _make_chunk("pub1", "公开信息内容关于算力", "第一章",
                         classification=ChunkTypeClassification.PUBLIC,
                         heading_title="公开章节"),
            _make_chunk("secret1", "机密信息内容关于薪资", "第二章",
                         classification=ChunkTypeClassification.SECRET,
                         heading_title="机密章节"),
            # 中性切片：仅为凑足语料规模，保证 BM25 的 idf > 0
            _make_chunk("filler1", "无关内容甲关于流程规范", "第三章",
                         classification=ChunkTypeClassification.PUBLIC,
                         heading_title="流程规范", chunk_index=2),
            _make_chunk("filler2", "无关内容乙关于设备维护", "第四章",
                         classification=ChunkTypeClassification.PUBLIC,
                         heading_title="设备维护", chunk_index=3),
            _make_chunk("filler3", "无关内容丙关于培训安排", "第五章",
                         classification=ChunkTypeClassification.PUBLIC,
                         heading_title="培训安排", chunk_index=4),
        ]
        repo.upsert(chunks)

        embedder = FakeEmbedder()
        r = HybridRetriever(repo=repo, embedder=embedder, rrf_k=5)

        mf = MetaFilter(tenant_id="default", max_classification=ChunkTypeClassification.PUBLIC)

        hits = r._bm25_search("算力", top_k=10, meta_filter=mf)

        # 先确认检索确实有结果，否则下面的越权过滤断言毫无意义（假通过）
        assert hits, "BM25 必须返回非空结果，否则越权过滤断言无意义"
        # SECRET 切片被过滤掉
        assert all(h.chunk_id != "secret1" for h in hits)
        # PUBLIC 切片保留
        assert any(h.chunk_id == "pub1" for h in hits)

