"""技能管理 API 路由 —— 用户私有 Skill 的增删改查"""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from app.tools.skill_manager import SkillManager
from app.models.db_models import Skill, SkillType
from app.db.database import get_db_sync
import logging

logger = logging.getLogger("routes.skill")
router = APIRouter(prefix="/api/v1/skills", tags=["技能管理"])


@router.post("/")
async def create_skill(name: str, description: str, code: str, language: str = "python", tags: list[str] = None):
    """创建新的持久化 Skill"""
    # 这个端点应该需要请求体，这里简化处理
    pass


@router.get("/")
async def list_skills(request: Request, skill_type: str = None):
    """列出用户的私有 Skill"""
    user_id = request.state.user_id
    db = get_db_sync()

    query = db.query(Skill).filter_by(user_id=user_id, is_active=True)
    if skill_type:
        try:
            st = SkillType(skill_type)
            query = query.filter_by(skill_type=st)
        except ValueError:
            pass

    skills = query.order_by(Skill.updated_at.desc()).all()
    db.close()

    return {
        "skills": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "description": s.description,
                "language": s.language,
                "tags": s.tags,
                "skill_type": s.skill_type.value if hasattr(s.skill_type, 'value') else str(s.skill_type),
                "usage_count": s.usage_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in skills
        ]
    }


@router.get("/{skill_id}")
async def get_skill(skill_id: str, request: Request):
    """获取 Skill 详情"""
    user_id = request.state.user_id
    db = get_db_sync()
    skill = db.query(Skill).filter_by(skill_id=skill_id, user_id=user_id).first()
    db.close()

    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")

    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "code": skill.code,
        "language": skill.language,
        "tags": skill.tags,
        "skill_type": skill.skill_type.value if hasattr(skill.skill_type, 'value') else str(skill.skill_type),
        "usage_count": skill.usage_count,
        "created_at": skill.created_at.isoformat() if skill.created_at else None,
    }


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str, request: Request):
    """删除 Skill"""
    user_id = request.state.user_id
    db = get_db_sync()
    skill = db.query(Skill).filter_by(skill_id=skill_id, user_id=user_id).first()
    if not skill:
        db.close()
        raise HTTPException(status_code=404, detail="Skill 不存在")

    skill.is_active = False
    db.commit()
    db.close()
    return {"detail": "Skill 已删除"}
