"""
HybridRetriever — 向量检索 + BM25 混合检索，RRF 融合排序。

P2 原则：从 P1 已验证的稠密检索逻辑 lift 过来，不是重写。
P1 已经跑通的 embed_query + repo.search 直接复用。
P2 只加 BM25 + RRF 融合。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

import jieba
from rank_bm25 import BM25Okapi

from app.contracts import Chunk, Embedder, Hit, IndexRepository, MetaFilter, Reranker
from app.cross.logging import get_logger
from app.retrieve.query_understanding import QueryUnderstanding, QueryIntent

logger = get_logger(__name__)


class HybridRetriever:
    """向量检索 + BM25 稀疏检索，RRF 融合排序。

    用法:
        retriever = HybridRetriever(repo=repo, embedder=embedder)
        hits = retriever.search("个人信息保护法的适用范围", top_k=5)

    设计点:
    - 稠密检索从 P1 的 p1_demo.py lift 过来，不做改动
    - BM25 索引惰性构建（首次 search 时从 ChromaDB 拉取全部文本）
    - RRF k=60（业界标准值）
    """

    def __init__(
        self,
        repo: IndexRepository,
        embedder: Embedder,
        rrf_k: int = 5,
        query_understanding: Optional[QueryUnderstanding] = None,
        reranker: Optional[Reranker] = None,
    ):
        self._repo = repo
        self._embedder = embedder
        self._rrf_k = rrf_k
        self._qu = query_understanding
        self._reranker = reranker

        # BM25 惰性初始化
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_chunks: List[Chunk] = []  # 与 BM25 索引位置一一对应
        self._bm25_ready: bool = False
        self._bm25_chunk_count: int = 0  # 构建时的 chunk 总数，用于检测变更

        # 英文术语正则：匹配连续的英文单词
        self._ENGLISH_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

    # ---------------------------------------------------------------
    # 公开接口
    # ---------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
        meta_filter: Optional[MetaFilter] = None,
        boost_sparse: bool = False,
    ) -> List[Hit]:
        """混合检索：稠密 + 稀疏 → RRF 融合。

        参数:
            query: 用户查询文本
            top_k: 返回结果数
            meta_filter: 权限过滤（P2 留空，P3 再填）
            boost_sparse: 是否提高稀疏检索权重（检测到条款号时启用）
        """
        if not query.strip():
            return []

        top_k = max(1, top_k)

        # 0. 查询理解（可选）
        intent: Optional[QueryIntent] = None
        if self._qu:
            intent = self._qu.analyze(query)
            if intent.boost_sparse:
                logger.debug("query_understanding: boost_sparse (clause=%s)", intent.clause_number)

        # 1. 稠密检索（从 P1 lift）
        query_vec = self._embedder.embed_query(query)
        dense_hits = self._repo.search(query_vec, top_k=top_k * 2, meta_filter=meta_filter)
        logger.debug("dense retrieved %d hits", len(dense_hits))

        # 2. 稀疏检索
        sparse_hits = self._bm25_search(query, top_k=top_k * 2, meta_filter=meta_filter)
        logger.debug("sparse retrieved %d hits", len(sparse_hits))

        # 3. RRF 融合
        # 优先使用内部 QueryUnderstanding 的分析结果，否则用外部传入的 boost_sparse
        boost = intent.boost_sparse if intent else boost_sparse
        fused = self._rrf_fuse(dense_hits, sparse_hits, top_k * 2, boost_sparse=boost)

        # 4. 可选 reranker 重排
        if self._reranker and fused:
            try:
                fused = self._reranker.rerank(query, fused, top_n=top_k)
                logger.debug("rerank applied: %d hits", len(fused))
            except Exception as e:
                logger.warning("rerank failed, using fused results: %s", e)

        logger.debug("fused %d hits", len(fused))
        return fused[:top_k]

    # ---------------------------------------------------------------
    # 关键词海绵优化：总起段检测 + 标题匹配加分
    # ---------------------------------------------------------------

    _OVERVIEW_PATTERNS = [
        "总体要求", "总则", "前言", "概述", "总论", "引言",
        "背景", "起草说明", "说明",
        "组织实施",  # 总结段，包含大量实施类关键词
        "保障措施",  # 保障措施段，包含大量政策类关键词
    ]

    _STRONG_OVERVIEW_PATTERNS = [
        "组织实施",  # 总结段，内容短但关键词泛，对无关查询干扰最大
    ]

    def _is_overview_section(self, heading: str) -> bool:
        """判断是否为总起/总结段（关键词海绵段）。"""
        if not heading:
            return False
        for pat in self._OVERVIEW_PATTERNS:
            if pat in heading:
                return True
        return False

    def _is_strong_overview(self, heading: str) -> bool:
        """判断是否为强海绵段（需要更强降权）。"""
        if not heading:
            return False
        for pat in self._STRONG_OVERVIEW_PATTERNS:
            if pat in heading:
                return True
        return False

    def _overview_penalty(self, heading: str) -> float:
        """返回总起段降权系数。"""
        if self._is_strong_overview(heading):
            return 0.2  # 强海绵段（"组织实施"）：更强降权
        if self._is_overview_section(heading):
            return 0.5  # 一般总起段（"总体要求"等）：轻度降权
        return 1.0

    def _title_matches_query(self, heading: str, query_tokens: list[str]) -> float:
        """计算标题对查询关键词的匹配度，返回加分系数。

        如果标题包含查询中的关键词，说明这个 chunk 就是专门讲这个主题的。
        排除通用词（的、了、是、有、在...），避免"总体要求"的"要"匹配所有查询。
        """
        if not heading:
            return 1.0

        stop_words = {"的", "了", "是", "有", "在", "和", "与", "或", "不",
                      "就", "都", "而", "及", "及", "等", "之", "以",
                      "为", "上", "下", "中", "大", "小", "多", "少",
                      "好", "要", "能", "会", "可", "对", "从", "被",
                      "把", "让", "给", "向", "用", "到", "去", "来",
                      "个", "人", "这", "那", "哪", "什", "么", "怎",
                      "也", "还", "又", "再", "已", "将", "没", "很",
                      "一", "二", "三", "四", "五", "六", "七", "八",
                      "九", "十", "第", "的", "化", "性", "型", "力",
                      "新", "行动", "工作", "发展", "建设", "推进", "工程",
                      "人工智能"}  # 文档主题词，出现在几乎所有标题中，无区分度

        matched = 0
        for token in query_tokens:
            token = token.strip()
            if len(token) < 2 or token in stop_words:
                continue
            if token in heading:
                matched += 1

        if matched >= 2:
            return 2.0  # 标题匹配多个关键词 → 大加分（排除"人工智能"后更精准）
        elif matched == 1:
            return 1.2  # 标题匹配一个关键词 → 轻微加分
        return 1.0      # 标题不匹配 → 不加分

    def _tokenize(self, text: str) -> list[str]:
        """分词：英文术语整体保留 + jieba 中文分词 + 全部小写。"""
        terms = self._ENGLISH_TERM_RE.findall(text)
        words = [t for t in jieba.lcut(text) if t.strip() and len(t) > 1]
        return [t.lower() for t in terms] + [w.lower() for w in words]

    def _ensure_bm25(self) -> None:
        """惰性构建 BM25 索引，检测 chunk 数量变化后自动重建。"""
        if self._bm25_ready:
            current_count = self._repo.count()
            if current_count == self._bm25_chunk_count:
                return
            logger.info("chunk count changed (%d -> %d), rebuilding BM25", self._bm25_chunk_count, current_count)

        self._bm25 = None
        self._bm25_chunks = []

        chunks = self._repo.get_all_chunks()
        if not chunks:
            logger.warning("no chunks found for BM25 index")
            self._bm25 = BM25Okapi([])
            self._bm25_chunks = []
            self._bm25_ready = True
            self._bm25_chunk_count = 0
            return

        logger.info("building BM25 index from %d chunks", len(chunks))
        tokenized_corpus = []
        for c in chunks:
            text = f"{c.meta.heading_number} {c.content}" if c.meta.heading_number else c.content
            tokens = self._tokenize(text)
            tokenized_corpus.append(tokens)
            self._bm25_chunks.append(c)

        self._bm25 = BM25Okapi(tokenized_corpus)
        self._bm25_ready = True
        self._bm25_chunk_count = len(chunks)
        logger.info("BM25 index ready: %d docs, %d tokens", len(chunks), sum(len(t) for t in tokenized_corpus))

    def _bm25_search(self, query: str, top_k: int, meta_filter: Optional[MetaFilter] = None) -> List[Hit]:
        """BM25 稀疏检索，带可选的权限过滤和关键词海绵优化。"""
        self._ensure_bm25()

        query_tokens = self._tokenize(query)
        scores = self._bm25.get_scores(query_tokens)

        # 收集所有 chunk 的索引，带权限过滤、总起段降权、标题匹配加分
        scored_indices = []
        for idx, c in enumerate(self._bm25_chunks):
            if meta_filter and not self._check_bm25_access(c, meta_filter):
                continue

            score = scores[idx]
            heading = c.meta.heading_number or ""
            heading_title = c.meta.heading_title or heading

            # 标题匹配加分：优先用 heading_title（语义标题），回退到 heading_number
            title_boost = self._title_matches_query(heading_title, query_tokens)
            score *= title_boost

            # 总起段降权：分层降权，强海绵段（"组织实施"）降更多
            penalty = self._overview_penalty(heading_title)
            score *= penalty

            # 练习块降权：练习块抢知识点排名
            if "练习" in heading_title:
                score *= 0.2

            if score > 0:
                scored_indices.append((-score, idx))

        scored_indices.sort()
        top_indices = [idx for (neg_score, idx) in scored_indices[:top_k]]

        hits = []
        for idx in top_indices:
            score = scores[idx]
            c = self._bm25_chunks[idx]
            heading = c.meta.heading_number or ""
            heading_title = c.meta.heading_title or heading

            # 重新计算最终的权重调整
            title_boost = self._title_matches_query(heading_title, query_tokens)
            score *= title_boost
            penalty = self._overview_penalty(heading_title)
            score *= penalty
            if "练习" in heading_title:
                score *= 0.2

            if score <= 0:
                continue
            hits.append(Hit(
                chunk_id=c.chunk_id,
                content=c.content,
                meta=c.meta,
                sparse_score=float(score),
            ))
        return hits

    def _check_bm25_access(self, chunk: Chunk, filter: MetaFilter) -> bool:
        """检查 BM25 内存中的 Chunk 是否通过权限过滤。"""
        from app.contracts import CLASSIFICATION_LEVELS

        # 租户过滤
        if filter.tenant_id:
            stored_tenant = chunk.meta.extras.get("tenant_id", "default")
            if stored_tenant != filter.tenant_id:
                return False

        # 密级过滤
        if filter.max_classification:
            chunk_level = CLASSIFICATION_LEVELS.get(chunk.meta.classification, 0)
            user_level = CLASSIFICATION_LEVELS.get(filter.max_classification, 0)
            if chunk_level > user_level:
                return False

        return True

    # ---------------------------------------------------------------
    # RRF 融合
    # ---------------------------------------------------------------

    def _rrf_fuse(
        self,
        dense_hits: List[Hit],
        sparse_hits: List[Hit],
        top_k: int,
        boost_sparse: bool = False,
    ) -> List[Hit]:
        """Reciprocal Rank Fusion — 不依赖分数，只依赖排名。

        score(d) = 1/(k + rank_dense(d)) + boost_weight * 1/(k + rank_sparse(d))

        其中 k = rrf_k（默认 60），rank 从 1 开始计数。
        boost_sparse=True 时，BM25 排名权重提高到 3 倍（用于条款号查询）。

        去重键: (doc_id, heading_number, chunk_index) — 与 get_all_chunks() 一致。
        """
        def _dedup_key(h: Hit) -> tuple:
            return (h.meta.doc_id, h.meta.heading_number, h.meta.chunk_index)

        # 去重：保留首次出现的（rank 更靠前）
        seen_dense: set[tuple] = set()
        seen_sparse: set[tuple] = set()
        unique_dense: list[Hit] = []
        unique_sparse: list[Hit] = []

        for h in dense_hits:
            k = _dedup_key(h)
            if k not in seen_dense:
                seen_dense.add(k)
                unique_dense.append(h)

        for h in sparse_hits:
            k = _dedup_key(h)
            if k not in seen_sparse:
                seen_sparse.add(k)
                unique_sparse.append(h)

        # 构建 rank 映射
        dense_rank: Dict[tuple, int] = {
            _dedup_key(h): i + 1 for i, h in enumerate(unique_dense)
        }
        sparse_rank: Dict[tuple, int] = {
            _dedup_key(h): i + 1 for i, h in enumerate(unique_sparse)
        }

        # 收集所有唯一 key
        all_keys = set(dense_rank.keys()) | set(sparse_rank.keys())

        # 构建 key → Hit 映射
        key_to_hit: Dict[tuple, Hit] = {}
        for h in unique_dense:
            key_to_hit[_dedup_key(h)] = h
        for h in unique_sparse:
            k = _dedup_key(h)
            if k not in key_to_hit:
                key_to_hit[k] = h

        # 计算 RRF 分数
        # 对关键词查询，默认提高 BM25 权重（因为我们文档少，关键词匹配更可靠）
        sparse_weight = 5.0 if boost_sparse else 1.0
        key_to_score: Dict[tuple, float] = {}
        for k in all_keys:
            score = 0.0
            if k in dense_rank:
                score += 1.0 / (self._rrf_k + dense_rank[k])
            if k in sparse_rank:
                score += sparse_weight / (self._rrf_k + sparse_rank[k])
            key_to_score[k] = score

        # 按 RRF 分数排序
        sorted_keys = sorted(all_keys, key=lambda k: key_to_score[k], reverse=True)

        # 构造结果 — 把 RRF 融合分数存入 rerank_score，让 final_score 返回真实融合分
        # 同时合并 dense_score 和 sparse_score（之前只取了其中一个 hit 的分数）
        dense_score_map = {_dedup_key(h): h.dense_score for h in unique_dense}
        sparse_score_map = {_dedup_key(h): h.sparse_score for h in unique_sparse}

        result = []
        for k in sorted_keys[:top_k]:
            h = key_to_hit[k]
            result.append(Hit(
                chunk_id=h.chunk_id,
                content=h.content,
                meta=h.meta,
                dense_score=dense_score_map.get(k, 0.0),
                sparse_score=sparse_score_map.get(k, 0.0),
                rerank_score=key_to_score[k],
            ))

        return result