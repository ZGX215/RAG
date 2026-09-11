"""配置 schema 骨架（P0 契约）

本文件只定义配置的 schema（字段名、类型、默认值、来源 .env），
不包含任何业务逻辑或运行时消费逻辑。

P0 原则：
  - 只写"有什么配置项"
  - 不写"怎么用配置项"（那是 P1 各层实现的事）
  - 占位符检测与启动校验见文件末尾的 validate_runtime_config()（P4 生产化补入）

.ENV 映射规则：
  每个子模型的字段通过 Field(alias=...) 映射到 .env 中的扁平键。
  例如 LLMSettings.api_key 对应 .env 中的 LLM_API_KEY。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger(__name__)

# 项目根目录（config/settings.py → config/ → 项目根）
# 默认路径一律基于它推导，杜绝写死某台机器的绝对路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 在 Settings 实例化前先把 .env 加载到 os.environ，
# 确保各嵌套子模型能通过 alias 读到对应的 env 值。
_ENV_PATH = _PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)


# ============================================================
# 占位符判定（供模型校验与启动校验共用）
# ============================================================
# 开发默认密钥：只用于本地，生产必须替换——否则任何人都能伪造任意密级的 token
DEV_AUTH_SECRET = "dev-only-secret-change-me-in-production"

# LLM key 的备用环境变量名：**显式声明**的受支持来源，不再隐式改写 os.environ。
# 背景：历史配置把真实 key 放在系统环境变量里，而 .env 中的 LLM_API_KEY 只是占位符。
LLM_KEY_FALLBACK_ENV_VARS = ("DEEPSEEK_API_KEY", "deepseek_api_key")


def is_placeholder_llm_key(value: str | None) -> bool:
    """判断 LLM key 是否为空或明显是占位符。"""
    v = (value or "").strip()
    if not v:
        return True
    if "xxxx" in v.lower():
        return True
    # 真实 key 通常 30+ 字符；sk- 开头但明显过短的视为占位符
    return v.startswith("sk-") and len(v) < 30


def is_placeholder_auth_secret(value: str | None) -> bool:
    """判断 token 签名密钥是否为空、或仍是开发默认值。"""
    v = (value or "").strip()
    return (not v) or v == DEV_AUTH_SECRET


# ============================================================
# 子模型（各配置分组）
# ============================================================


class LLMSettings(BaseSettings):
    """大模型配置（主模型 + 备用模型）。"""

    # 默认留空：不再给"看起来能跑"的假 key，缺配置由启动校验明确报错
    api_key: str = Field(default="", alias="LLM_API_KEY")
    base_url: str = Field(default="https://api.deepseek.com", alias="LLM_BASE_URL")
    model: str = Field(default="deepseek-chat", alias="LLM_MODEL")

    # 备用模型（可选，为空时不启用降级）
    fallback_api_key: str = Field(default="", alias="LLM_FALLBACK_API_KEY")
    fallback_base_url: str = Field(default="", alias="LLM_FALLBACK_BASE_URL")
    fallback_model: str = Field(default="", alias="LLM_FALLBACK_MODEL")

    @model_validator(mode="after")
    def _resolve_api_key_fallback(self):
        """LLM_API_KEY 为空/占位符时，回退到**显式声明的**环境变量名。

        与旧实现的区别：只回退 key 本身，不改 base_url / model、不写 os.environ，
        因此"配置到底从哪来"始终可追溯（旧实现会在 import 期改写全局环境）。
        """
        if is_placeholder_llm_key(self.api_key):
            for name in LLM_KEY_FALLBACK_ENV_VARS:
                candidate = (os.environ.get(name) or "").strip()
                if not is_placeholder_llm_key(candidate):
                    _log.warning(
                        "LLM_API_KEY 为空或为占位符，已回退使用环境变量 %s —— "
                        "建议把真实 key 直接写进 .env 的 LLM_API_KEY", name
                    )
                    self.api_key = candidate
                    break
        return self


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
    # 运行环境：development（默认）/ production。
    # production 走严格模式——关键配置缺失时拒绝启动（fail-fast）。
    env: str = Field(default="development", alias="APP_ENV")


class AuthSettings(BaseSettings):
    """认证配置（账号密码登录 → token → 服务端密级）。

    - secret_key：token 签名密钥。**生产环境必须换成随机值**，
      泄露后任何人都能伪造任意密级的 token。
    - token_ttl：token 有效期（秒），默认 8 小时。
    - required：是否强制登录。
        False（默认）= 未登录也能访问，按旧的 X-User-Clearance 走，便于本地调试；
        True = 未携带有效 token 一律拒绝，生产环境必须开。
    """

    # 默认留空：不再内嵌开发密钥。生产缺配置会被 validate_runtime_config() 拒绝启动，
    # 开发环境仅告警（本地调试不受阻）。
    secret_key: str = Field(default="", alias="AUTH_SECRET_KEY")
    token_ttl: int = Field(default=28800, alias="AUTH_TOKEN_TTL")
    required: bool = Field(default=False, alias="AUTH_REQUIRED")


class DatabaseSettings(BaseSettings):
    """关系型数据库配置（SQLAlchemy）。

    开发环境用 SQLite（零安装），生产环境切换 PostgreSQL：
      DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/rag_db
    """

    # 默认值基于项目根推导，不写死任何一台机器的绝对路径：
    # 换机器 / 进容器 / CI（无 .env）都能落到 <项目根>/data/structured.db
    url: str = Field(
        default=f"sqlite:///{(_PROJECT_ROOT / 'data' / 'structured.db').as_posix()}",
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


# ============================================================
# 启动校验（fail-fast）
# ============================================================

def is_production() -> bool:
    """当前是否为生产环境（APP_ENV=production / prod）。"""
    return settings.general.env.strip().lower() in ("production", "prod")


def validate_runtime_config(strict: bool | None = None) -> list[str]:
    """校验运行必需的配置，返回问题清单。

    - **生产环境**（strict 默认为 True）：任一问题 → 抛 ``ConfigError``，拒绝启动。
      宁可起不来，也不要带着假 key / 默认密钥上线。
    - **开发环境**：只打 WARNING，不阻断启动，保证本地调试不被挡。

    用法（在应用入口调用一次）::

        from config.settings import validate_runtime_config
        validate_runtime_config()
    """
    if strict is None:
        strict = is_production()

    problems: list[str] = []

    if is_placeholder_llm_key(settings.llm.api_key):
        problems.append("LLM_API_KEY 未配置或仍是占位符 —— 所有 LLM 调用都会失败")
    if is_placeholder_auth_secret(settings.auth.secret_key):
        problems.append(
            "AUTH_SECRET_KEY 未配置或仍是开发默认值 —— 任何人都能伪造任意密级的 token"
        )

    if problems:
        detail = "；".join(problems)
        if strict:
            # 惰性导入：config 层不反向依赖 app 层，避免循环导入
            from app.cross.exceptions import ConfigError

            raise ConfigError(
                f"生产环境配置校验未通过（APP_ENV={settings.general.env}）：{detail}"
            )
        _log.warning(
            "配置校验告警（APP_ENV=%s，开发模式不阻断启动）：%s",
            settings.general.env, detail,
        )
    else:
        _log.info("配置校验通过（APP_ENV=%s）", settings.general.env)

    return problems
