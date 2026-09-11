"""FastAPI 中间件：请求ID + 耗时统计 + 全局异常拦截 + 安全上下文。

P1 pre-flight 已经定义了业务异常基类，这里做 FastAPI 层面的拦截和封装。
遵循"演进不是新建"原则：复用 P1 已有的异常定义，不重新造轮子。
P3 新增 SecurityMiddleware 用于权限过滤。
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.cross.context import RequestContext, reset_context, set_current_context
from app.cross.exceptions import BaseAppException
from app.cross.logging import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """生成 request_id，注入到 RequestContext 中，沿链传播。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        request_id = str(uuid.uuid4())[:8]
        ctx = RequestContext(
            request_id=request_id,
            start_time=time.time(),
        )
        token = set_current_context(ctx)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_context(token)


class TimingMiddleware(BaseHTTPMiddleware):
    """记录请求耗时，打完日志再返回。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        from app.cross.context import get_current_context
        ctx = get_current_context()
        if ctx is None:
            return await call_next(request)

        start = ctx.start_time
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        logger.info(
            "request completed: method=%s path=%s request_id=%s elapsed_ms=%.1f status=%d",
            request.method,
            request.url.path,
            ctx.request_id,
            elapsed_ms,
            response.status_code,
        )

        return response


class ExceptionMiddleware(BaseHTTPMiddleware):
    """全局异常拦截，统一返回 JSON 格式。

    复用 P1 pre-flight 定义的 BaseAppException，业务异常继承它即可。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        from fastapi.responses import JSONResponse

        from app.cross.context import get_current_context

        try:
            return await call_next(request)
        except BaseAppException as e:
            # 业务异常 → 400 错误
            ctx = get_current_context()
            logger.error(
                "business exception: request_id=%s error=%s",
                ctx.request_id if ctx else "none",
                str(e),
                exc_info=True,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "code": 400,
                    "request_id": ctx.request_id if ctx else None,
                    "error": str(e),
                    "type": e.__class__.__name__,
                },
            )
        except Exception as e:
            # 系统异常 → 500 错误
            ctx = get_current_context()
            logger.error(
                "system exception: request_id=%s error=%s",
                ctx.request_id if ctx else "none",
                str(e),
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "code": 500,
                    "request_id": ctx.request_id if ctx else None,
                    "error": "Internal server error",
                    "detail": str(e),
                },
            )


class SecurityMiddleware(BaseHTTPMiddleware):
    """安全上下文中间件：解析用户身份，构建 MetaFilter 注入 RequestContext。

    身份来源（按优先级）：
      1. **Authorization: Bearer &lt;token&gt;** —— 登录模式。
         token 由服务端签发并验签，其中的密级/租户不可篡改；
         此时**完全忽略** X-User-Clearance 等请求头，杜绝越权伪造。
      2. 无有效 token —— 若 AUTH_REQUIRED=true 则直接 401；
         否则回落到旧的调试模式（API Key + X-User-Clearance），仅供本地使用。

    请求链: RequestIDMiddleware → SecurityMiddleware → TimingMiddleware → ExceptionMiddleware → 路由
    """

    # 不需要登录也能访问的路径
    PUBLIC_PATHS = (
        "/api/v1/auth/login",
        "/health",
        "/docs", "/redoc", "/openapi.json",
        "/metrics",
        "/api/v1/dashboard",
    )

    @staticmethod
    def _is_public(path: str) -> bool:
        return any(path.startswith(p) for p in SecurityMiddleware.PUBLIC_PATHS)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        from fastapi.responses import JSONResponse

        from app.auth.service import verify_token
        from app.cross.security import SecurityManager
        from config.settings import settings

        path = request.url.path

        # ---------- 1. 登录模式：Bearer token ----------
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            payload = verify_token(auth[7:].strip())
            if payload is None:
                if not self._is_public(path):
                    return JSONResponse(
                        status_code=401,
                        content={"code": 401, "error": "token 无效或已过期，请重新登录"},
                    )
            else:
                security = SecurityManager()
                identity = security.resolve_identity_from_token(payload)
                request.state.meta_filter = security.build_meta_filter(identity)
                request.state.auth_user = {
                    "uid": payload.uid,
                    "username": payload.username,
                    "clearance": payload.clearance,
                    "tenant_id": payload.tenant_id,
                    "dept": payload.dept,
                    "exp": payload.exp,
                }
                request.state.auth_mode = "token"
                # 安全：登录态下客户端自带的密级头一律无效
                if request.headers.get("X-User-Clearance"):
                    logger.warning(
                        "ignoring X-User-Clearance header in token mode (user=%s)",
                        payload.username,
                    )
                return await call_next(request)

        # ---------- 2. 未登录且要求强制认证 ----------
        if settings.auth.required and not self._is_public(path):
            return JSONResponse(
                status_code=401,
                content={"code": 401, "error": "未认证，请先登录"},
            )

        # ---------- 3. 调试回落：API Key + 请求头覆盖（仅供本地测试） ----------
        api_key = request.headers.get("X-API-Key", "")
        security = SecurityManager()
        identity = security.resolve_identity_from_api_key(api_key)

        # 测试用请求头覆盖（生产环境应移除）
        test_clearance = request.headers.get("X-User-Clearance", "")
        if test_clearance and identity:
            from app.contracts import ChunkTypeClassification
            try:
                identity.clearance = ChunkTypeClassification(test_clearance.lower())
                logger.info("test override: clearance=%s", identity.clearance.value)
            except ValueError:
                logger.warning("invalid X-User-Clearance: %s, using default", test_clearance)

        test_tenant = request.headers.get("X-User-Tenant", "")
        if test_tenant and identity:
            identity.tenant_id = test_tenant
            logger.info("test override: tenant=%s", identity.tenant_id)

        if identity:
            request.state.meta_filter = security.build_meta_filter(identity)
            request.state.auth_user = {
                "uid": 0,
                "username": identity.user_id,
                "clearance": identity.clearance.value,
                "tenant_id": identity.tenant_id,
                "dept": identity.dept,
                "exp": 0,
            }
            request.state.auth_mode = "anonymous"
            logger.info(
                "security context set: user=%s clearance=%s tenant=%s",
                identity.user_id,
                identity.clearance.value,
                identity.tenant_id,
            )

        return await call_next(request)
