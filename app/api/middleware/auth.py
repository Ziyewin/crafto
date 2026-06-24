"""认证中间件 —— 解析用户身份，注入请求状态"""
from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.models.db_models import User
from app.db.database import get_db_sync
import hashlib
import hmac
import logging

logger = logging.getLogger("middleware.auth")

# 公开端点前缀列表（无需认证）
PUBLIC_PREFIXES = ["/health", "/docs", "/openapi.json", "/redoc", "/static", "/api/v1/auth/login", "/api/v1/auth/register", "/favicon"]


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件 —— 通过 X-API-Key 头或 Bearer Token 识别用户"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path

        # 公开路径跳过认证
        if path == "/" or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # 获取认证凭证
        api_key = request.headers.get("X-API-Key") or ""
        auth_header = request.headers.get("Authorization", "")

        user_id = None
        # 先试 X-API-Key
        if api_key:
            user_id = self._resolve_api_key(api_key)
        # 再试 Bearer Token（作为 fallback）
        if not user_id and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user_id = self._resolve_token(token)

        if not user_id:
            return JSONResponse(
                status_code=401,
                content={"detail": "未提供有效的认证凭证", "code": "UNAUTHORIZED"},
            )

        # 注入用户信息到请求
        request.state.user_id = user_id
        request.state.user_role = self._get_user_role(user_id)

        return await call_next(request)

    def _resolve_api_key(self, api_key: str) -> str | None:
        """通过 API Key 查找用户（简化版：API Key = user_id 的哈希）"""
        try:
            db = get_db_sync()
            users = db.query(User).all()
            for user in users:
                expected = hashlib.sha256(f"{user.user_id}:{user.created_at.isoformat()}".encode()).hexdigest()[:32]
                if hmac.compare_digest(api_key, expected):
                    db.close()
                    return user.user_id
            db.close()
        except Exception as e:
            logger.error("API Key 解析失败: %s", e)
        return None

    def _resolve_token(self, token: str) -> str | None:
        """解析 Bearer Token（简化版：token 就是 user_id）"""
        try:
            db = get_db_sync()
            user = db.query(User).filter_by(user_id=token).first()
            db.close()
            if user and user.is_active:
                return user.user_id
        except Exception:
            pass
        return None

    def _get_user_role(self, user_id: str) -> str:
        """获取用户角色"""
        try:
            db = get_db_sync()
            user = db.query(User).filter_by(user_id=user_id).first()
            db.close()
            if user:
                return user.role.value if hasattr(user.role, 'value') else str(user.role)
        except Exception:
            pass
        return "normal"
