"""对话 API 路由 —— 用户消息处理、流式输出、会话管理"""
from __future__ import annotations
from fastapi import APIRouter, Request, HTTPException
from app.models.schemas import ChatRequest, ChatResponse
from app.core.agent import Agent
from app.core.session import SessionManager
import uuid
import logging

logger = logging.getLogger("routes.chat")
router = APIRouter(prefix="/api/v1/chat", tags=["对话"])


@router.post("/send")
async def send_message(req: ChatRequest, request: Request):
    """发送消息并获取 AI 回复（非流式）"""
    user_id = request.state.user_id
    user_role = getattr(request.state, "user_role", "normal")

    # 如果没有 session_id，创建新会话
    session_id = req.session_id
    if not session_id:
        session_mgr = SessionManager(user_id)
        session_id = await session_mgr.create_session()

    # 创建 Agent 并处理消息
    agent = Agent(user_id=user_id, session_id=session_id, user_role=user_role)
    result = await agent.process_message(req.message)

    return {
        "session_id": result["session_id"],
        "reply": result["reply"],
        "tool_calls": result.get("tool_calls", []),
        "token_usage": result.get("token_usage", {}),
        "trace_id": result.get("trace_id", ""),
    }


@router.post("/send/stream")
async def send_message_stream(req: ChatRequest, request: Request):
    """发送消息并获取 AI 回复（流式）"""
    from fastapi.responses import StreamingResponse

    user_id = request.state.user_id
    user_role = getattr(request.state, "user_role", "normal")

    # 如果没有 session_id，创建新会话
    session_id = req.session_id
    if not session_id:
        session_mgr = SessionManager(user_id)
        session_id = await session_mgr.create_session()

    # 创建 Agent 并流式处理
    agent = Agent(user_id=user_id, session_id=session_id, user_role=user_role)

    async def generate():
        async for chunk in agent.process_stream(req.message):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")


@router.get("/sessions")
async def list_sessions(request: Request):
    """获取用户的会话列表"""
    user_id = request.state.user_id
    session_mgr = SessionManager(user_id)
    sessions = await session_mgr.list_sessions()
    return {"sessions": sessions}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request):
    """获取会话的历史消息"""
    user_id = request.state.user_id
    session_mgr = SessionManager(user_id)
    messages = await session_mgr.get_messages(session_id)
    return {"messages": messages, "session_id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """删除会话"""
    user_id = request.state.user_id
    session_mgr = SessionManager(user_id)
    await session_mgr.delete_session(session_id)
    return {"detail": "会话已删除"}
