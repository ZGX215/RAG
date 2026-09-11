"""认证服务测试 — 口令哈希 + Token 签发/校验/过期/篡改。

测试覆盖：
1. hash_password + verify_password：正确密码验证通过，错误密码失败
2. new_salt：每次生成的盐不同
3. create_token + verify_token：正常签发和校验
4. verify_token 篡改：修改 payload 后签名校验失败
5. verify_token 格式错误：空 token、无点分隔符
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.auth.service import (
    create_token,
    hash_password,
    new_salt,
    verify_password,
    verify_token,
)


class TestPasswordHash:
    """口令哈希测试。"""

    def test_correct_password(self):
        """正确密码验证通过。"""
        salt = new_salt()
        password_hash = hash_password("my_secret_123", salt)
        assert verify_password("my_secret_123", salt, password_hash) is True

    def test_wrong_password(self):
        """错误密码验证失败。"""
        salt = new_salt()
        password_hash = hash_password("correct_password", salt)
        assert verify_password("wrong_password", salt, password_hash) is False

    def test_different_salt_different_hash(self):
        """不同盐生成不同哈希。"""
        salt1 = new_salt()
        salt2 = new_salt()
        h1 = hash_password("same_password", salt1)
        h2 = hash_password("same_password", salt2)
        assert h1 != h2

    def test_same_salt_same_hash(self):
        """相同盐和密码生成相同哈希（可重现）。"""
        salt = "fixed_salt_for_testing"
        h1 = hash_password("same_password", salt)
        h2 = hash_password("same_password", salt)
        assert h1 == h2

    def test_new_salt_is_hex(self):
        """new_salt 返回 hex 字符串。"""
        salt = new_salt()
        assert isinstance(salt, str)
        # hex 编码：只包含 0-9 a-f
        assert all(c in "0123456789abcdef" for c in salt)
        assert len(salt) == 32  # 16 bytes = 32 hex chars


class TestToken:
    """Token 签发和校验测试。"""

    def setup_method(self):
        """Mock settings.auth.secret_key 和 token_ttl。"""
        self._patcher1 = patch("config.settings.settings.auth.secret_key", "test-secret-key-12345")
        self._patcher2 = patch("config.settings.settings.auth.token_ttl", 3600)
        self._patcher1.start()
        self._patcher2.start()

    def teardown_method(self):
        self._patcher1.stop()
        self._patcher2.stop()

    def test_create_and_verify_token(self):
        """正常签发和校验 token。"""
        token, ttl = create_token(
            uid=1, username="testuser", clearance="internal",
            tenant_id="tenant_a", dept="dev",
        )
        assert ttl == 3600
        payload = verify_token(token)
        assert payload is not None
        assert payload.uid == 1
        assert payload.username == "testuser"
        assert payload.clearance == "internal"
        assert payload.tenant_id == "tenant_a"
        assert payload.dept == "dev"

    def test_verify_tampered_payload(self):
        """篡改 payload 后签名校验失败。"""
        token, _ = create_token(
            uid=1, username="admin", clearance="public",
            tenant_id="default", dept="ops",
        )
        # 篡改 payload 部分
        parts = token.rpartition(".")
        tampered_payload = parts[0] + "tampered"
        tampered_token = f"{tampered_payload}.{parts[2]}"
        assert verify_token(tampered_token) is None

    def test_verify_tampered_signature(self):
        """篡改签名后校验失败。"""
        token, _ = create_token(
            uid=1, username="admin", clearance="secret",
            tenant_id="default", dept="ops",
        )
        parts = token.rpartition(".")
        tampered_sig = "a" * 64  # 随机签名
        tampered_token = f"{parts[0]}.{tampered_sig}"
        assert verify_token(tampered_token) is None

    def test_verify_empty_token(self):
        """空 token 校验失败。"""
        assert verify_token("") is None

    def test_verify_no_dot_token(self):
        """没有点分隔符的 token 校验失败。"""
        assert verify_token("just_a_string_without_dot") is None

    def test_verify_expired_token(self):
        """过期 token 校验失败。"""
        # 先签发一个 token
        token, _ = create_token(
            uid=1, username="testuser", clearance="internal",
            tenant_id="t", dept="d",
        )
        # 手动构造过期 token
        import base64
        import hashlib
        import hmac
        import json

        secret = "test-secret-key-12345"
        data = {
            "uid": 1, "username": "testuser", "clr": "internal",
            "tid": "t", "dept": "d",
            "exp": int(time.time()) - 100,  # 100 秒前过期
        }
        payload = base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        expired_token = f"{payload}.{sig}"
        assert verify_token(expired_token) is None
