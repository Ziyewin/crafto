"""会话管理模块 —— 管理用户会话的创建、存储、查询"""
from __future__ import annotations
from app.models.db_models import Session as SessionModel, Message
from app.db.database import get_db_sync
import uuid
from datetime import datetime, timezone
import logging

logger = logging.getLogger("core.session")


class SessionManager:
    """管理用户会话的生命周期"""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def create_session(self, title: str = "新对话") -> str:
        """创建一个新会话，返回 session_id"""
        session_id = str(uuid.uuid4())
        try:
            db = get_db_sync()
            session = SessionModel(
                session_id=session_id,
                user_id=self.user_id,
                title=title,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(session)
            db.commit()
            db.close()
            logger.info("为用户 %s 创建了新会话 %s", self.user_id, session_id)
        except Exception as e:
            logger.error("创建会话失败: %s", e)
            raise
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        """获取会话信息"""
        try:
            db = get_db_sync()
            session = db.query(SessionModel).filter_by(
                session_id=session_id, user_id=self.user_id
            ).first()
            db.close()
            if session:
                return {
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "title": session.title,
                    "message_count": session.message_count,
                    "summary": session.summary,
                    "is_active": session.is_active,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                }
        except Exception as e:
            logger.error("获取会话失败: %s", e)
        return None

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """列出用户的所有活跃会话"""
        try:
            db = get_db_sync()
            sessions = (
                db.query(SessionModel)
                .filter_by(user_id=self.user_id, is_active=True)
                .order_by(SessionModel.updated_at.desc())
                .limit(limit)
                .all()
            )
            db.close()
            return [
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "message_count": s.message_count,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in sessions
            ]
        except Exception as e:
            logger.error("列出会话失败: %s", e)
            return []

    async def delete_session(self, session_id: str):
        """软删除会话（标记为非活跃）"""
        try:
            db = get_db_sync()
            db.query(SessionModel).filter_by(
                session_id=session_id, user_id=self.user_id
            ).update({"is_active": False})
            db.commit()
            db.close()
        except Exception as e:
            logger.error("删除会话失败: %s", e)

    async def get_messages(self, session_id: str, limit: int = 50) -> list[dict]:
        """获取会话的历史消息"""
        try:
            db = get_db_sync()
            msgs = (
                db.query(Message)
                .filter_by(session_id=session_id, user_id=self.user_id)
                .order_by(Message.created_at.asc())
                .limit(limit)
                .all()
            )
            db.close()
            return [
                {
                    "message_id": m.message_id,
                    "role": m.role,
                    "content": m.content,
                    "tool_calls": m.tool_calls,
                    "tool_call_id": m.tool_call_id,
                    "prompt_tokens": m.prompt_tokens,
                    "completion_tokens": m.completion_tokens,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ]
        except Exception as e:
            logger.error("获取消息失败: %s", e)
            return []

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list = None,
        tool_call_id: str = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        trace_id: str = None,
    ):
        """保存一条消息到数据库"""
        try:
            db = get_db_sync()
            msg = Message(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                user_id=self.user_id,
                role=role,
                content=content or "",
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                trace_id=trace_id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(msg)

            # 更新会话的消息计数
            db.query(SessionModel).filter_by(session_id=session_id).update(
                {"message_count": SessionModel.message_count + 1}
            )
            db.commit()
            db.close()
        except Exception as e:
            logger.error("保存消息失败: %s", e)
