"""请求上下文 — contextvars 实现，全链路传播。

P1 pre-flight 已经规划了 RequestContext，P2 在这里落地。
RequestContext 定义移到 app.contracts，这里只导出供导入。
"""

from __future__ import annotations

import contextvars
from typing import Optional

from app.contracts import RequestContext

# 全局 contextvar
_request_ctx: contextvars.ContextVar[Optional[RequestContext]] = contextvars.ContextVar("request_ctx")


def get_current_context() -> Optional[RequestContext]:
    """获取当前请求上下文。"""
    return _request_ctx.get(None)


def set_current_context(ctx: RequestContext) -> contextvars.Token:
    """设置当前请求上下文，返回 token 用于恢复。"""
    return _request_ctx.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    """恢复上下文（中间件 exit 时调用）。"""
    _request_ctx.reset(token)
