"""
Reranker — 基于 CrossEncoder 的重排序实现。

对混合检索（稠密 + BM25 + RRF）的候选结果做 cross-encoder 重排，
显著提升 Top-1 准确率（通常提升 10-20%）。

用法:
    reranker = BgeReranker()
    ranked = reranker.rerank(query, candidate_hits, top_n=5)

降级:
    如果模型加载失败（依赖缺失 / 模型未下载），自动降级为原序返回。
"""

from __future__ import annotations

from typing import List

from app.contracts import Hit, Reranker
from app.cross.logging import get_logger

logger = get_logger(__name__)


class BgeReranker(Reranker):
    """BGE CrossEncoder 重排序器。

    使用 BAAI/bge-reranker-base 对候选列表做 cross-encoder 重排。
    模型自动下载，首次使用需要联网。

    ReRank 的分数存回 Hit.rerank_score，供 final_score 属性使用。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base", device: str = "cpu"):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._available = False
        self._init_model()

    def _init_model(self) -> None:
        """尝试加载 CrossEncoder 模型，失败时标记为不可用。"""
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name, device=self._device)
            self._available = True
            logger.info("BgeReranker ready: model=%s device=%s", self._model_name, self._device)
        except Exception as e:
            logger.warning("BgeReranker init failed, will skip reranking: %s", e)
            self._available = False

    def rerank(self, query: str, hits: List[Hit], top_n: int = 5) -> List[Hit]:
        """对候选列表重排序，返回前 top_n 条。"""
        if not hits:
            return hits[:top_n]
        if not self._available:
            self._init_model()
        if not self._available or self._model is None:
            return hits[:top_n]

        try:
            pairs = [(query, h.content) for h in hits]
            scores = self._model.predict(pairs)

            # 按 cross-encoder 分数降序排列
            scored = list(zip(scores, hits))
            scored.sort(key=lambda x: -x[0])

            result = []
            for score, h in scored[:top_n]:
                result.append(Hit(
                    chunk_id=h.chunk_id,
                    content=h.content,
                    meta=h.meta,
                    dense_score=h.dense_score,
                    sparse_score=h.sparse_score,
                    rerank_score=float(score),
                ))

            logger.debug("rerank: %d→%d hits, top1=%.4f", len(hits), len(result), result[0].rerank_score if result else 0)
            return result

        except Exception as e:
            logger.warning("rerank failed, falling back to original order: %s", e)
            return hits[:top_n]