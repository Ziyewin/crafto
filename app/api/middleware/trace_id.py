"""TraceID 中间件 —— 为每个请求生成唯一追踪 ID，串联全流程日志"""
from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from app.logging_module.logger import set_trace_id
import uuid


class TraceIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 TraceID，注入日志上下文和响应头"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 优先使用客户端传入的 TraceID，否则生成新的
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        set_trace_id(trace_id)

        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
