"""权限管理模块测试 — SecurityManager 的身份解析、MetaFilter 构建、切片访问检查。

测试覆盖：
1. resolve_identity_from_api_key → 总是返回 PUBLIC 权限
2. build_meta_filter → 正确构建 MetaFilter
3. check_chunk_access → 四级密级互斥检查（PUBLIC 能看 PUBLIC，不能看 INTERNAL）
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.contracts import ChunkTypeClassification, MetaFilter
from app.cross.security import SecurityManager, UserIdentity


class TestSecurityManager:
    """SecurityManager 单元测试。"""

    def setup_method(self):
        self.mgr = SecurityManager()

    # --- resolve_identity_from_api_key ---

    def test_api_key_returns_default_public(self):
        """API Key 解析：返回 default 用户 + PUBLIC 权限。"""
        identity = self.mgr.resolve_identity_from_api_key("any-key")
        assert identity is not None
        assert identity.user_id == "default"
        assert identity.tenant_id == "default"
        assert identity.clearance == ChunkTypeClassification.PUBLIC

    def test_api_key_empty_string(self):
        """空 API Key 也返回默认身份（P2 不做真实认证）。"""
        identity = self.mgr.resolve_identity_from_api_key("")
        assert identity is not None
        assert identity.clearance == ChunkTypeClassification.PUBLIC

    # --- build_meta_filter ---

    def test_build_meta_filter_public(self):
        """构建 PUBLIC 权限的 MetaFilter。"""
        identity = UserIdentity(
            user_id="u1", tenant_id="tenant_a", dept="dev",
            clearance=ChunkTypeClassification.PUBLIC,
        )
        mf = self.mgr.build_meta_filter(identity)
        assert mf.tenant_id == "tenant_a"
        assert mf.max_classification == ChunkTypeClassification.PUBLIC

    def test_build_meta_filter_secret(self):
        """构建 SECRET 权限的 MetaFilter。"""
        identity = UserIdentity(
            user_id="u2", tenant_id="tenant_b", dept="ops",
            clearance=ChunkTypeClassification.SECRET,
        )
        mf = self.mgr.build_meta_filter(identity)
        assert mf.tenant_id == "tenant_b"
        assert mf.max_classification == ChunkTypeClassification.SECRET

    # --- check_chunk_access: 四级密级互斥 ---

    def test_public_can_access_public(self):
        """PUBLIC 用户可以访问 PUBLIC 切片。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.PUBLIC)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.PUBLIC) is True

    def test_public_cannot_access_internal(self):
        """PUBLIC 用户不能访问 INTERNAL 切片。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.PUBLIC)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.INTERNAL) is False

    def test_public_cannot_access_confidential(self):
        """PUBLIC 用户不能访问 CONFIDENTIAL 切片。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.PUBLIC)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.CONFIDENTIAL) is False

    def test_public_cannot_access_secret(self):
        """PUBLIC 用户不能访问 SECRET 切片。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.PUBLIC)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.SECRET) is False

    def test_internal_can_access_public_and_internal(self):
        """INTERNAL 用户可以访问 PUBLIC 和 INTERNAL，但不能看 CONFIDENTIAL。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.INTERNAL)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.PUBLIC) is True
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.INTERNAL) is True
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.CONFIDENTIAL) is False

    def test_confidential_can_access_up_to_confidential(self):
        """CONFIDENTIAL 用户可以访问 PUBLIC/INTERNAL/CONFIDENTIAL。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.CONFIDENTIAL)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.PUBLIC) is True
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.INTERNAL) is True
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.CONFIDENTIAL) is True
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.SECRET) is False

    def test_secret_can_access_all(self):
        """SECRET 用户可以访问所有密级。"""
        mf = MetaFilter(tenant_id="t", max_classification=ChunkTypeClassification.SECRET)
        for level in ChunkTypeClassification:
            assert self.mgr.check_chunk_access(mf, level) is True

    def test_no_max_classification_denies_all(self):
        """没有设置 max_classification 时，默认拒绝非 PUBLIC 数据。"""
        mf = MetaFilter(tenant_id="t", max_classification=None)
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.PUBLIC) is True
        assert self.mgr.check_chunk_access(mf, ChunkTypeClassification.INTERNAL) is False
