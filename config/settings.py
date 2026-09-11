"""配置 schema 骨架（P0 契约）

本文件只定义配置的 schema（字段名、类型、默认值、来源 .env），
不包含任何业务逻辑或运行时消费逻辑。

P0 原则：
  - 只写"有什么配置项"
  - 不写"怎么用配置项"（那是 P1 各层实现的事）
  - 不写占位符检测、配置校验等逻辑（那是 P1 的事）

.ENV 映射规则：
  每个子模型的字段通过 Field(alias=...) 映射到 .env 中的扁平键。
  例如 LLMSettings.api_key 对应 .env 中的 LLM_API_KEY。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 在 Settings 实例化前先把 .env 加载到 os.environ，
# 确保各嵌套子模型能通过 alias 读到对应的 env 值。
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)

# 兼容方案：如果 LLM_API_KEY 是占位符或未设置，优先用系统环境变量 deepseek_api_key
_llm_key = os.environ.get("LLM_API_KEY", "")
if _llm_key.startswith("sk-") and len(_llm_key) < 30:
    # 当前 LLM_API_KEY 是占位符 → 尝试用 deepseek_api_key 覆盖
    if os.environ.get("deepseek_api_key"):
        os.environ["LLM_API_KEY"] = os.environ["deepseek_api_key"]
        # key 切到 DeepSeek 时，base_url 和 model 也一起切，三者为同一厂商
        # 避免"用 DeepSeek 的 key 打火山方舟的 endpoint"的配置矛盾
        if not os.environ.get("LLM_BASE_URL") or "volces" in os.environ.get("LLM_BASE_URL", ""):
            os.environ["LLM_BASE_URL"] = "https://api.deepseek.com"
        if not os.environ.get("LLM_MODEL") or os.environ.get("LLM_MODEL", "").startswith("ep-"):
            os.environ["LLM_MODEL"] = "deepseek-chat"


# ============================================================
# 子模型（各配置分组）
# ============================================================


class LLMSettings(BaseSettings):
    """大模型配置（主模型 + 备用模型）。"""

    api_key: str = Field(default="sk-xxxxxxxxxxxxxxxxxxxx", alias="LLM_API_KEY")
    base_url: str = Field(default="https://api.deepseek.com", alias="LLM_BASE_URL")
    model: str = Field(default="deepseek-chat", alias="LLM_MODEL")

    # 备用模型（可选，为空时不启用降级）
    fallback_api_key: str = Field(default="", alias="LLM_FALLBACK_API_KEY")
    fallback_base_url: str = Field(default="", alias="LLM_FALLBACK_BASE_URL")
    fallback_model: str = Field(default="", alias="LLM_FALLBACK_MODEL")


class EmbeddingSettings(BaseSettings):
    """Embedding 模型配置。"""

    model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")
    device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")
    batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")


class IndexSettings(BaseSettings):
    """索引层配置（ChromaDB + SQLite）。"""

    persist_dir: str = Field(default="./data/chroma_db", alias="INDEX_PERSIST_DIR")
    collection_name: str = Field(default="mcu_qa", alias="INDEX_COLLECTION_NAME")
    structured_db_path: str = Field(default="./data/structured.db", alias="INDEX_STRUCTURED_DB_PATH")


class RetrievalSettings(BaseSettings):
    """检索层配置。"""

    top_k: int = Field(default=18, alias="RETRIEVAL_TOP_K")
    dense_weight: float = Field(default=0.5, alias="RETRIEVAL_DENSE_WEIGHT")
    sparse_weight: float = Field(default=0.5, alias="RETRIEVAL_SPARSE_WEIGHT")
    rrf_k: int = Field(default=60, alias="RETRIEVAL_RRF_K")
    rerank_top_n: int = Field(default=5, alias="RERANK_TOP_N")


class GenerateSettings(BaseSettings):
    """生成层配置。"""

    context_max_chars: int = Field(default=4000, alias="GENERATE_CONTEXT_MAX_CHARS")
    fallback_rules_path: str = Field(
        default="./config/fallback_rules.json", alias="GENERATE_FALLBACK_RULES_PATH"
    )


class ChunkSettings(BaseSettings):
    """文档分块配置。"""

    max_chars: int = Field(default=200, alias="CHUNK_MAX_CHARS")
    overlap: int = Field(default=20, alias="CHUNK_OVERLAP")


class ApiSettings(BaseSettings):
    """API 服务配置。"""

    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"], alias="API_CORS_ORIGINS"
    )


class CelerySettings(BaseSettings):
    """异步任务配置（Celery + Redis）。"""

    broker_url: str = Field(default="redis://localhost:6379/0", alias="CELERY_BROKER_URL")
    result_backend: str = Field(default="redis://localhost:6379/1", alias="CELERY_RESULT_BACKEND")
    task_serializer: str = Field(default="json", alias="CELERY_TASK_SERIALIZER")
    result_serializer: str = Field(default="json", alias="CELERY_RESULT_SERIALIZER")
    accept_content: list[str] = Field(default=["json"], alias="CELERY_ACCEPT_CONTENT")
    task_track_started: bool = Field(default=True, alias="CELERY_TASK_TRACK_STARTED")
    task_time_limit: int = Field(default=300, alias="CELERY_TASK_TIME_LIMIT")
    task_soft_time_limit: int = Field(default=240, alias="CELERY_TASK_SOFT_TIME_LIMIT")


class CacheSettings(BaseSettings):
    """缓存配置（Redis）。"""

    redis_url: str = Field(default="redis://localhost:6379/2", alias="CACHE_REDIS_URL")
    answer_ttl: int = Field(default=3600, alias="CACHE_ANSWER_TTL")
    embed_ttl: int = Field(default=86400, alias="CACHE_EMBED_TTL")


class GeneralSettings(BaseSettings):
    """通用配置。"""

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


class AuthSettings(BaseSettings):
    """认证配置（账号密码登录 → token → 服务端密级）。

    - secret_key：token 签名密钥。**生产环境必须换成随机值**，
      泄露后任何人都能伪造任意密级的 token。
    - token_ttl：token 有效期（秒），默认 8 小时。
    - required：是否强制登录。
        False（默认）= 未登录也能访问，按旧的 X-User-Clearance 走，便于本地调试；
        True = 未携带有效 token 一律拒绝，生产环境必须开。
    """

    secret_key: str = Field(
        default="dev-only-secret-change-me-in-production",
        alias="AUTH_SECRET_KEY",
    )
    token_ttl: int = Field(default=28800, alias="AUTH_TOKEN_TTL")
    required: bool = Field(default=False, alias="AUTH_REQUIRED")


class DatabaseSettings(BaseSettings):
    """关系型数据库配置（SQLAlchemy）。

    开发环境用 SQLite（零安装），生产环境切换 PostgreSQL：
      DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/rag_db
    """

    url: str = Field(
        default="sqlite:///E:/trae/cede/mcu-rag-qa-v2/data/structured.db",
        alias="DATABASE_URL",
    )
    echo: bool = Field(default=False, alias="DATABASE_ECHO")
    pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    pool_recycle: int = Field(default=3600, alias="DATABASE_POOL_RECYCLE")


# ============================================================
# 聚合类
# ============================================================


class Settings(BaseSettings):
    """全局配置聚合类。

    通过嵌套属性（llm / embedding / index / retrieval / generate /
    chunk / api / general）提供分组化的配置访问入口。

    用法::

        from config.settings import settings
        print(settings.llm.api_key)
        print(settings.retrieval.top_k)
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    generate: GenerateSettings = Field(default_factory=GenerateSettings)
    chunk: ChunkSettings = Field(default_factory=ChunkSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


# 模块级单例（各层统一引用此实例）
settings = Settings()