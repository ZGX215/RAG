"""认证服务——账号密码校验 + token 签发/校验。

设计要点：
  1. 口令用 PBKDF2-HMAC-SHA256（10 万次迭代）+ 每用户随机盐，不存明文；
  2. token 用 HMAC-SHA256 自签名，**不引入 pyjwt 等新依赖**；
     结构 = base64url(payload_json) + "." + hex(hmac_sha256)；
  3. payload 里带上 clearance / tenant_id，服务端签发后不可篡改 —— 这是
     "密级由账号决定而不是由请求头决定" 的关键：客户端改不了 token 内容，
     改了签名校验就失败。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from app.cross.logging import get_logger

logger = get_logger(__name__)

_PBKDF2_ROUNDS = 100_000


# ============================================================
# 口令哈希
# ============================================================

def new_salt() -> str:
    return os.urandom(16).hex()


def hash_password(password: str, salt: str) -> str:
    """PBKDF2-HMAC-SHA256 口令哈希。"""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    ).hex()


def verify_password(password: str, salt: str, expect_hash: str) -> bool:
    """校验口令（用 compare_digest 避免时序侧信道）。"""
    actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expect_hash)


# ============================================================
# Token
# ============================================================

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


@dataclass
class TokenPayload:
    """token 载荷（已验签，可信）。"""

    uid: int
    username: str
    clearance: str
    tenant_id: str
    dept: str
    exp: int


def create_token(uid: int, username: str, clearance: str,
                 tenant_id: str, dept: str) -> tuple[str, int]:
    """签发 token，返回 (token, 有效期秒数)。"""
    from config.settings import settings

    ttl = settings.auth.token_ttl
    data = {
        "uid": uid,
        "username": username,
        "clr": clearance,
        "tid": tenant_id,
        "dept": dept,
        "exp": int(time.time()) + ttl,
    }
    payload = _b64e(json.dumps(data, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload, settings.auth.secret_key)}", ttl


def verify_token(token: str) -> Optional[TokenPayload]:
    """校验 token 签名与有效期，失败返回 None。"""
    from config.settings import settings

    if not token or "." not in token:
        return None
    payload, _, sig = token.rpartition(".")
    if not payload or not sig:
        return None
    # 先比签名，再解 JSON，避免对伪造数据做解析
    if not hmac.compare_digest(_sign(payload, settings.auth.secret_key), sig):
        logger.warning("auth: token signature mismatch")
        return None
    try:
        d = json.loads(_b64d(payload))
    except Exception:
        return None
    if int(d.get("exp", 0)) < time.time():
        logger.debug("auth: token expired")
        return None
    return TokenPayload(
        uid=d.get("uid", 0),
        username=d.get("username", ""),
        clearance=d.get("clr", "public"),
        tenant_id=d.get("tid", "default"),
        dept=d.get("dept", "default"),
        exp=d.get("exp", 0),
    )
