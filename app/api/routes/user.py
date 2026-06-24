"""用户管理 API 路由 —— 注册、登录、个人信息、API Key"""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from app.models.db_models import User, UserRole
from app.models.schemas import UserCreate
from app.db.database import get_db_sync
import uuid
import hashlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger("routes.user")
router = APIRouter(prefix="/api/v1/auth", tags=["用户认证"])


def _hash_password(password: str) -> str:
    """密码哈希（生产环境应使用 bcrypt/argon2）"""
    return hashlib.sha256(password.encode()).hexdigest()


def _generate_api_key(user_id: str, created_at: datetime) -> str:
    """生成 API Key"""
    raw = f"{user_id}:{created_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class _LoginBody(BaseModel):
    """登录请求体"""
    username: str
    password: str


@router.post("/register")
async def register(user_data: UserCreate):
    """用户注册"""
    db = get_db_sync()

    existing = db.query(User).filter_by(username=user_data.username).first()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="用户名已存在")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    role_val = user_data.role.value if hasattr(user_data.role, 'value') else str(user_data.role)
    user = User(
        user_id=user_id,
        username=user_data.username,
        password_hash=_hash_password(user_data.password),
        role=UserRole(role_val),
        is_active=True,
        created_at=now,
        profile_summary="",
        long_term_features={},
    )
    db.add(user)
    db.commit()
    db.close()

    api_key = _generate_api_key(user_id, now)

    return {
        "user_id": user_id,
        "username": user_data.username,
        "role": role_val,
        "api_key": api_key,
        "message": "注册成功",
    }


@router.post("/login")
async def login(body: _LoginBody):
    """用户登录"""
    db = get_db_sync()
    user = db.query(User).filter_by(username=body.username).first()
    if not user or user.password_hash != _hash_password(body.password):
        db.close()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        db.close()
        raise HTTPException(status_code=403, detail="账号已被禁用")

    api_key = _generate_api_key(user.user_id, user.created_at)
    db.close()

    role_val = user.role.value if hasattr(user.role, 'value') else str(user.role)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": role_val,
        "api_key": api_key,
        "message": "登录成功",
    }


@router.get("/profile")
async def get_profile(request: Request):
    """获取当前用户信息"""
    user_id = request.state.user_id
    db = get_db_sync()
    user = db.query(User).filter_by(user_id=user_id).first()
    db.close()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "preferred_tools": user.preferred_tools or [],
    }
