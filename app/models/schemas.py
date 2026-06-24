"""数据模型定义 —— 请求/响应的 Pydantic Schema，贯穿全平台"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


# ── 枚举类型 ──

class UserRole(str, Enum):
    """用户角色权限等级"""
    normal = "normal"       # 普通用户：仅预置工具
    advanced = "advanced"   # 高级用户：开放代码沙箱
    admin = "admin"         # 管理员：全量权限


class SkillType(str, Enum):
    """技能类型：临时（会话级）vs 持久化"""
    temporary = "temporary"
    persistent = "persistent"


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ── 用户相关 ──

class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=2, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    role: UserRole = UserRole.normal


class UserProfile(BaseModel):
    """用户画像信息"""
    user_id: str
    username: str
    role: UserRole
    default_model: str = "deepseek-chat"
    conversation_style: str = "balanced"
    preferred_tools: list[str] = []
    created_at: datetime
    is_active: bool = True


# ── 记忆相关 ──

class MemoryItem(BaseModel):
    """单条记忆记录"""
    memory_id: str
    user_id: str
    session_id: str
    content: str
    memory_type: str  # short_term | summary | long_term
    embedding: Optional[list[float]] = None
    created_at: datetime
    metadata: dict[str, Any] = {}


class MemorySearchResult(BaseModel):
    """记忆检索结果"""
    content: str
    score: float
    memory_type: str
    metadata: dict[str, Any] = {}


# ── 技能相关 ──

class SkillBase(BaseModel):
    """技能基础信息"""
    name: str
    description: str
    code: str
    language: str = "python"
    tags: list[str] = []


class SkillCreate(SkillBase):
    """创建技能请求"""
    pass


class SkillRecord(SkillBase):
    """技能记录（含元数据）"""
    skill_id: str
    user_id: str
    skill_type: SkillType
    embedding: Optional[list[float]] = None
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime
    is_active: bool = True


# ── 工具相关 ──

class ToolCall(BaseModel):
    """工具调用请求"""
    tool_name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel):
    """工具执行结果"""
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None
    execution_time_ms: int = 0


# ── 会话 / 对话 ──

class Session(BaseModel):
    """会话信息"""
    session_id: str
    user_id: str
    title: str = "新对话"
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    is_active: bool = True


class ChatMessage(BaseModel):
    """单条聊天消息"""
    role: str  # user | assistant | system | tool
    content: str
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None
    thinking: Optional[str] = None


class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: Optional[str] = None
    message: str
    stream: bool = True


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: str
    reply: str
    thinking: Optional[str] = None
    tool_calls: list[dict] = []
    token_usage: dict[str, int] = {}


# ── 日志 / 异常 ──

class LogRecord(BaseModel):
    """结构化日志记录"""
    trace_id: str
    user_id: Optional[str]
    session_id: Optional[str]
    level: LogLevel
    component: str
    message: str
    metadata: dict[str, Any] = {}
    created_at: datetime


class AnomalyRecord(BaseModel):
    """异常故障记录（独立存储）"""
    anomaly_id: str
    trace_id: str
    user_id: Optional[str]
    error_type: str
    stack_trace: Optional[str]
    context: dict[str, Any] = {}
    problem_code: Optional[str] = None
    retry_status: str = "pending"
    resolved: bool = False
    created_at: datetime
    resolved_at: Optional[datetime] = None


# ── Agent 相关 ──

class AgentStep(BaseModel):
    """Agent 单步执行记录"""
    step_id: str
    step_type: str  # thought | tool_call | code_execution | reflection
    input: str
    output: str
    metadata: dict[str, Any] = {}


class TaskPlan(BaseModel):
    """任务规划"""
    task_id: str
    user_id: str
    session_id: str
    goal: str
    steps: list[AgentStep] = []
    status: str = "pending"  # pending | running | completed | failed
    created_at: datetime
    completed_at: Optional[datetime] = None
