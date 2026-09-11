"""权限管理模块（权限过滤 + MetaFilter 落地）。

根据用户身份解析得到权限，构建 MetaFilter 给检索层过滤。
每个切片已经提前打了密级标签，检索时只保留用户权限范围内的数据。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.contracts import RequestContext, MetaFilter, ChunkTypeClassification
from app.cross.context import get_current_context
from app.cross.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UserIdentity:
    """用户身份——从 API Key 或 HTTP Header 解析出来。"""

    user_id: str
    tenant_id: str
    dept: str
    clearance: ChunkTypeClassification  # 最高允许密级


class SecurityManager:
    """权限管理器：解析身份 → 构建 MetaFilter → 检索层使用。"""

    def resolve_identity_from_api_key(self, api_key: str) -> Optional[UserIdentity]:
        """从 API Key 解析用户身份。

        P2 阶段简化：默认返回公共权限，不做真实认证。
        生产环境可以换成数据库查询。
        """
        # TODO: P3 已经预留接口，生产环境替换为真实认证
        return UserIdentity(
            user_id="default",
            tenant_id="default",
            dept="default",
            clearance=ChunkTypeClassification.PUBLIC,
        )

    def resolve_identity_from_token(self, payload) -> Optional[UserIdentity]:
        """从**已验签**的 token 载荷解析身份。

        这是登录模式下的身份来源：密级取自服务端签发的 token，
        客户端无法通过任何请求头篡改。
        """
        try:
            clearance = ChunkTypeClassification(payload.clearance)
        except ValueError:
            clearance = ChunkTypeClassification.PUBLIC
        return UserIdentity(
            user_id=payload.username,
            tenant_id=payload.tenant_id,
            dept=payload.dept,
            clearance=clearance,
        )

    def build_meta_filter(self, identity: UserIdentity) -> MetaFilter:
        """根据用户身份构建 MetaFilter（传给 IndexRepository.search()）。"""
        return MetaFilter(
            tenant_id=identity.tenant_id,
            max_classification=identity.clearance,
        )

    def check_chunk_access(self, filter: MetaFilter, chunk_classification: ChunkTypeClassification) -> bool:
        """检查切片是否允许用户访问。

        切片密级 <= 用户最高密级 → 允许，否则禁止。
        """
        # 密级顺序：PUBLIC < INTERNAL < CONFIDENTIAL < SECRET
        # 数值越大密级越高
        order = {
            ChunkTypeClassification.PUBLIC: 0,
            ChunkTypeClassification.INTERNAL: 1,
            ChunkTypeClassification.CONFIDENTIAL: 2,
            ChunkTypeClassification.SECRET: 3,
        }
        chunk_level = order.get(chunk_classification, 0)
        user_level = order.get(filter.max_classification, 0) if filter.max_classification else 0
        return chunk_level <= user_level


def get_current_meta_filter() -> Optional[MetaFilter]:
    """从当前请求上下文获取 MetaFilter。"""
    ctx = get_current_context()
    if not ctx:
        return None
    if hasattr(ctx, "meta_filter"):
        return ctx.meta_filter
    return None