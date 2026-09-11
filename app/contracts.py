"""
contracts.py — P0: 层间契约定义

本文件是项目的"层间宪法"，所有跨层调用的数据结构与接口签名均在此钉死。
任何层都不得 import 另一层的实现类，只能 import 此文件中的 Protocol 和 dataclass。

分层规则（参照架构文档 9.2）：
  ingest 层  →  IndexRepository (写)  →  index 层
  retrieve 层  →  IndexRepository (读)  →  index 层
  generate 层  →  LLMClient           →  access 层
  cross 层     →  RequestContext       →  所有层
"""

from __future__ import annotations

import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

# ============================================================
# 枚举
# ============================================================


class ChunkType(str, Enum):
    """文档切片类型"""

    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"


class ChunkTypeClassification(str, Enum):
    """文档密级（用于多租户权限过滤）"""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


# 密级数值映射：数值越大密级越高，用于 ChromaDB $lte 过滤
CLASSIFICATION_LEVELS: dict[ChunkTypeClassification, int] = {
    ChunkTypeClassification.PUBLIC: 0,
    ChunkTypeClassification.INTERNAL: 1,
    ChunkTypeClassification.CONFIDENTIAL: 2,
    ChunkTypeClassification.SECRET: 3,
}


class FallbackMatchMode(str, Enum):
    """兜底规则匹配模式"""

    ALL = "all"  # 关键词全部命中
    ANY = "any"  # 关键词任一命中
    EXACT = "exact"  # 整句精确匹配


class VerifyStatus(str, Enum):
    """答案验证状态"""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


# ============================================================
# 核心数据结构
# ============================================================


@dataclass
class ChunkMeta:
    """文档切片的元数据（统一字段名，不再各层混用）"""

    doc_name: str
    doc_id: str
    mcu_model: str
    page_num: int
    heading_number: str
    heading_title: str
    heading_level: int
    chunk_type: ChunkType
    chunk_index: int
    token_count: int
    classification: ChunkTypeClassification = ChunkTypeClassification.PUBLIC

    # 扩展字段（各层可写入，但必须预先声明类型）
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """统一的文档切片——ingest 输出的产物，index 存储的单元"""

    chunk_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    content: str = ""
    meta: ChunkMeta = field(default_factory=lambda: ChunkMeta(  # type: ignore[arg-type]
        doc_name="", doc_id="", mcu_model="", page_num=0,
        heading_number="", heading_title="", heading_level=0,
        chunk_type=ChunkType.TEXT, chunk_index=0, token_count=0,
    ))


@dataclass
class Hit:
    """检索结果——index 层返回给 retrieve 层的统一格式"""

    chunk_id: str
    content: str
    meta: ChunkMeta
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rerank_score: float = 0.0

    @property
    def final_score(self) -> float:
        """最终排序分数（rerank 优先，其次 fusion，最后 dense）"""
        if self.rerank_score:
            return self.rerank_score
        return max(self.dense_score, self.sparse_score)


@dataclass
class SourceRef:
    """答案来源引用"""

    chunk_id: str
    doc_name: str
    page_num: int
    chapter: str
    relevance_score: float


@dataclass
class Question:
    """用户问题"""

    text: str
    mcu_model: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)
    session_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Answer:
    """系统回答"""

    text: str
    sources: List[SourceRef] = field(default_factory=list)
    latency_ms: int = 0
    verify_status: Optional[VerifyStatus] = None


@dataclass
class FallbackRule:
    """兜底规则——从 JSON 配置文件加载，不再硬编码在代码中"""

    keywords: List[str]
    answer: str
    exclude_keywords: List[str] = field(default_factory=list)
    mode: FallbackMatchMode = FallbackMatchMode.ANY


@dataclass
class VerifyResult:
    """答案验证结果"""

    status: VerifyStatus
    reason: str = ""
    source_hits: List[str] = field(default_factory=list)  # 命中 chunk_id 列表


@dataclass
class MetaFilter:
    """元数据权限过滤器——用于检索前过滤用户不可见的数据"""

    tenant_id: Optional[str] = None
    allowed_depts: List[str] = field(default_factory=list)
    max_classification: Optional[ChunkTypeClassification] = None


@dataclass
class RequestContext:
    """跨层请求上下文——通过 contextvars 传播，不污染函数签名"""

    request_id: str = ""
    start_time: float = 0.0
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str = ""
    tenant_id: str = ""
    dept: str = ""
    clearance: Optional[ChunkTypeClassification] = None
    meta_filter: Optional[MetaFilter] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HybridConfig:
    """混合检索配置"""

    dense_weight: float = 0.5
    sparse_weight: float = 0.5
    rrf_k: int = 60
    top_n: int = 18


@dataclass
class QAState:
    """LangGraph 工作流状态（P1 薄切片阶段的初始形态）"""

    question: Question = field(default_factory=Question)
    context: RequestContext = field(default_factory=RequestContext)

    # 检索阶段
    rewrite_query: str = ""
    keywords: List[str] = field(default_factory=list)
    hits: List[Hit] = field(default_factory=list)
    mcu_model: Optional[str] = None

    # 生成阶段
    context_text: str = ""
    answer: str = ""
    sources: List[SourceRef] = field(default_factory=list)

    # 验证阶段
    verify_result: Optional[VerifyResult] = None

    # 元数据
    error: Optional[str] = None
    is_fallback: bool = False
    latency_ms: int = 0


# ============================================================
# 协议接口（Protocol）—— 层间接缝
# ============================================================


@runtime_checkable
class SourceReader(Protocol):
    """资料来源接口——所有数据来源（PDF、Word、网页等）都要实现此接口。

    ingest 层依赖此接口，不依赖具体实现。
    加新来源时只需新建一个文件实现此接口，不改现有代码。
    """

    @abstractmethod
    def read(self, source: str, doc_name: str = "") -> List[Chunk]:
        """读取数据来源，返回 Chunk 列表。

        参数:
            source: 数据来源路径或标识符（如 PDF 文件路径、URL）
            doc_name: 文档名称（留空时由实现自动提取）
        """
        ...


@runtime_checkable
class Embedder(Protocol):
    """向量化抽象——ingest 和 retrieve 依赖同一个接口"""

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """批量文本向量化"""
        ...

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """单条查询向量化"""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        ...


@runtime_checkable
class SparseIndex(Protocol):
    """稀疏检索（BM25）抽象——独立于稠密向量检索"""

    @abstractmethod
    def search(self, query: str, top_k: int) -> List[Hit]:
        """稀疏检索"""
        ...

    @abstractmethod
    def index(self, chunks: Sequence[Chunk]) -> None:
        """批量索引构建"""
        ...


@runtime_checkable
class IndexRepository(Protocol):
    """索引层统一接口——ingest 和 retrieve 之间的唯一接缝

    职责边界：
    - ingest 层：PDF 提取 → 分块 → 构造 Chunk → 调用 upsert
    - retrieve 层：embedding → 调用 search → 拿到 Hit
    - index 层：实现此接口，封装 ChromaDB / Qdrant 等细节
    """

    @abstractmethod
    def upsert(self, chunks: Sequence[Chunk]) -> int:
        """批量写入/更新切片，返回成功写入数量"""
        ...

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        meta_filter: Optional[MetaFilter] = None,
    ) -> List[Hit]:
        """稠密向量检索"""
        ...

    @abstractmethod
    def delete_by_doc_id(self, doc_id: str) -> int:
        """按文档删除所有切片"""
        ...

    @abstractmethod
    def get_all_chunks(self) -> List[Chunk]:
        """返回索引中所有切片（供 BM25 构建语料库）"""
        ...

    @abstractmethod
    def count(self) -> int:
        """返回已索引切片总数"""
        ...

    @abstractmethod
    def rebuild(self, embedder: Embedder, chunks: Sequence[Chunk]) -> None:
        """重建索引（embedding 版本升级时调用）"""
        ...


@runtime_checkable
class Reranker(Protocol):
    """重排序抽象"""

    @abstractmethod
    def rerank(self, query: str, hits: List[Hit], top_n: int = 5) -> List[Hit]:
        """对检索结果重排序，返回前 top_n 条"""
        ...


@runtime_checkable
class QueryUnderstanding(Protocol):
    """查询理解抽象"""

    @abstractmethod
    def rewrite(self, question: str, history: List[Dict[str, str]]) -> str:
        """基于对话历史重写问题"""
        ...

    @abstractmethod
    def extract_keywords(self, query: str) -> List[str]:
        """提取检索关键词"""
        ...


@runtime_checkable
class ContextAssembler(Protocol):
    """上下文组装抽象"""

    @abstractmethod
    def assemble(self, hits: List[Hit], max_chars: int = 4000) -> str:
        """将检索结果组装为 LLM 上下文"""
        ...


@runtime_checkable
class LLMClient(Protocol):
    """LLM 调用抽象——支持主模型 + 备用模型 + 降级"""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """非流式生成"""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
    ):
        """流式生成（异步生成器）"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查模型是否可用"""
        ...


@runtime_checkable
class Verifier(Protocol):
    """答案验证抽象——基于检索结果验证生成内容"""

    @abstractmethod
    def verify(self, answer: str, hits: List[Hit]) -> VerifyResult:
        """验证 answer 是否可被 hits 支撑"""
        ...


@runtime_checkable
class FallbackProvider(Protocol):
    """兜底规则提供者——从配置文件加载规则"""

    @abstractmethod
    def match(self, question: str) -> Optional[FallbackRule]:
        """匹配最合适的兜底规则，未命中返回 None"""
        ...

    @abstractmethod
    def reload(self) -> int:
        """重新加载配置文件，返回规则数量"""
        ...


# ============================================================
# 空实现（供 P1 独立测试用）
# ============================================================


class FakeRepository:
    """Fake 实现——检索层可以不依赖真实 ChromaDB 做单测"""

    def __init__(self) -> None:
        self._chunks: Dict[str, Chunk] = {}

    def upsert(self, chunks: Sequence[Chunk]) -> int:
        for c in chunks:
            self._chunks[c.chunk_id] = c
        return len(chunks)

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        meta_filter: Optional[MetaFilter] = None,
    ) -> List[Hit]:
        import random
        all_chunks = list(self._chunks.values())
        random.shuffle(all_chunks)
        top = all_chunks[:top_k]
        return [
            Hit(
                chunk_id=c.chunk_id,
                content=c.content,
                meta=c.meta,
                dense_score=random.random(),
            )
            for c in top
        ]

    def delete_by_doc_id(self, doc_id: str) -> int:
        ids = [cid for cid, c in self._chunks.items() if c.meta.doc_id == doc_id]
        for cid in ids:
            del self._chunks[cid]
        return len(ids)

    def get_all_chunks(self) -> List[Chunk]:
        return list(self._chunks.values())

    def count(self) -> int:
        return len(self._chunks)

    def rebuild(self, embedder: Embedder, chunks: Sequence[Chunk]) -> None:
        self._chunks.clear()
        for c in chunks:
            self._chunks[c.chunk_id] = c