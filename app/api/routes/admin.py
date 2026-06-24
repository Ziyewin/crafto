"""管理后台 API 路由 —— 日志查询、异常监控、用户管理（仅管理员）"""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from app.models.db_models import AnomalyRecord, LogRecord, User
from app.db.database import get_db_sync
from app.logging_module.anomaly import list_anomalies
import logging

logger = logging.getLogger("routes.admin")
router = APIRouter(prefix="/api/v1/admin", tags=["管理后台"])


def _require_admin(request: Request):
    """检查管理员权限"""
    role = getattr(request.state, "user_role", "normal")
    if role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


@router.get("/anomalies")
async def get_anomalies(request: Request, user_id: str = None, limit: int = 50):
    """获取异常记录列表"""
    _require_admin(request)
    anomalies = list_anomalies(user_id=user_id, limit=limit)
    return {"anomalies": anomalies, "total": len(anomalies)}


@router.get("/logs")
async def get_logs(request: Request, trace_id: str = None, level: str = None, limit: int = 100):
    """查询日志记录"""
    _require_admin(request)
    db = get_db_sync()
    query = db.query(LogRecord)

    if trace_id:
        query = query.filter_by(trace_id=trace_id)
    if level:
        query = query.filter_by(level=level.upper())

    records = query.order_by(LogRecord.created_at.desc()).limit(limit).all()
    db.close()

    return {
        "logs": [
            {
                "log_id": r.log_id,
                "trace_id": r.trace_id,
                "user_id": r.user_id,
                "level": r.level,
                "component": r.component,
                "message": r.message[:200],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }


@router.get("/users")
async def list_users(request: Request):
    """获取所有用户列表"""
    _require_admin(request)
    db = get_db_sync()
    users = db.query(User).all()
    db.close()

    return {
        "users": [
            {
                "user_id": u.user_id,
                "username": u.username,
                "role": u.role.value if hasattr(u.role, 'value') else str(u.role),
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }


@router.post("/users/{user_id}/toggle-status")
async def toggle_user_status(user_id: str, request: Request):
    """启用/禁用用户"""
    _require_admin(request)
    db = get_db_sync()
    user = db.query(User).filter_by(user_id=user_id).first()
    if not user:
        db.close()
        raise HTTPException(status_code=404, detail="用户不存在")

    user.is_active = not user.is_active
    db.commit()
    db.close()
    return {
        "user_id": user_id,
        "is_active": user.is_active,
        "message": f"用户已{'启用' if user.is_active else '禁用'}"
    }
