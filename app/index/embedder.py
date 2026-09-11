"""Embedder 实现——基于 sentence-transformers 的向量化模块。

P1 薄切片阶段使用 paraphrase-multilingual-MiniLM-L12-v2（384 维，多语言）。
P3 正式切换到 BAAI/bge-base-zh-v1.5（768 维，中文优化，缓存到 E 盘）。
"""

from __future__ import annotations

import os
from typing import List, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from app.contracts import Embedder
from app.cross.logging import get_logger

from app.cross.paths import get_project_root

logger = get_logger(__name__)

# 模型缓存目录：强制放在 E 盘 data/ 下，不占用 C 盘
_MODEL_CACHE_DIR = str(get_project_root() / "data" / "models")
os.environ["HF_HOME"] = _MODEL_CACHE_DIR
os.environ["HF_HUB_CACHE"] = _MODEL_CACHE_DIR
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"


class SentenceEmbedder:
    """基于 sentence-transformers 的 Embedder 实现。

    优先使用本地缓存快照，不联网查询。模型已下载到 E 盘 data/models 目录。

    用法::

        embedder = SentenceEmbedder(model_name="BAAI/bge-base-zh-v1.5")
        vec = embedder.embed_query("个人信息保护法的适用范围是什么")
        vecs = embedder.embed_texts(["第一条", "第二条"])
    """

    _LOCAL_MODEL_PATHS: dict[str, str] = {}

    @classmethod
    def _resolve_local_path(cls, model_name: str) -> str:
        """将模型名解析为本地缓存快照路径，避免联网查询。"""
        if model_name not in cls._LOCAL_MODEL_PATHS:
            project_root = get_project_root()
            cache_root = project_root / "data" / "models"
            mappings = {
                "paraphrase-multilingual-MiniLM-L12-v2":
                    cache_root / "hub" / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
                    / "snapshots" / "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
                "BAAI/bge-m3":
                    cache_root / "hub" / "models--BAAI--bge-m3"
                    / "snapshots" / "5617a9f61b028005a4858fdac845db406aefb181",
                "BAAI/bge-base-zh-v1.5":
                    cache_root / "models--BAAI--bge-base-zh-v1.5"
                    / "snapshots" / "f03589ceff5aac7111bd60cfc7d497ca17ecac65",
            }
            for key, path in mappings.items():
                if key in model_name and path.exists():
                    cls._LOCAL_MODEL_PATHS[model_name] = str(path)
                    logger.info("resolved %s -> local cache: %s", model_name, path)
                    break
            else:
                cls._LOCAL_MODEL_PATHS[model_name] = model_name
        return cls._LOCAL_MODEL_PATHS[model_name]

    def __init__(self, model_name: str = "BAAI/bge-base-zh-v1.5", device: str = "cpu"):
        model_path = self._resolve_local_path(model_name)

        logger.info("loading embedding model: %s -> %s (device=%s)", model_name, model_path, device)
        self._model = SentenceTransformer(model_path, device=device, local_files_only=True)
        self._model_name = model_name
        self._device = device
        logger.info(
            "model loaded: %s | dim=%d | device=%s",
            model_name, self._model.get_embedding_dimension(), device,
        )

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """批量文本向量化。"""
        if not texts:
            return []
        embeddings = self._model.encode(
            list(texts),
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        """单条查询向量化（BGE 模型需要加官方指令前缀）。"""
        if not query:
            return []
        BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
        embedding = self._model.encode(
            BGE_QUERY_PREFIX + query,
            normalize_embeddings=True,
        )
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        return embedding

    @property
    def dimension(self) -> int:
        return self._model.get_embedding_dimension()


class CachedEmbedder:
    """带多级缓存的 Embedder 包装器。"""

    def __init__(self, inner: Embedder):
        self._inner = inner
        self._cache = None

    def _get_cache(self):
        if self._cache is None:
            from app.cross.cache import get_cache_manager
            self._cache = get_cache_manager()
        return self._cache

    def embed_query(self, query: str) -> List[float]:
        if not query:
            return []
        cache = self._get_cache()
        cached = cache.get("embed", query)
        if cached is not None:
            return cached
        vec = self._inner.embed_query(query)
        if vec:
            from config.settings import settings
            cache.set("embed", query, vec, ttl=settings.cache.embed_ttl)
        return vec

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        return self._inner.embed_texts(texts)

    @property
    def dimension(self) -> int:
        return self._inner.dimension


class FakeEmbedder:
    """Fake Embedder 实现——P1 薄切片通路验证模式。"""

    def __init__(self, dim: int = 384):
        import hashlib
        self._dim = dim
        self._hash = hashlib
        logger.warning("using FakeEmbedder (dim=%d) — P1 薄切片通路验证模式", dim)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        return [self._fake_vec(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        if not query:
            return []
        return self._fake_vec(query)

    @property
    def dimension(self) -> int:
        return self._dim

    def _fake_vec(self, text: str) -> List[float]:
        h = self._hash.sha256(text.encode()).hexdigest()
        seed = int(h[:8], 16)
        rng = __import__("random").Random(seed)
        vec = [rng.uniform(-0.1, 0.1) for _ in range(self._dim)]
        norm = sum(x * x for x in vec) ** 0.5
        return [x / norm for x in vec]
