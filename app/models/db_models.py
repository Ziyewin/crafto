"""SQLAlchemy ORM 模型 —— 所有数据库表定义，单文件统一管理"""
from __future__ import annotations
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, JSON, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone
import enum


class Base(DeclarativeBase):
    """声明式基类"""
    pass


def _utcnow():
    """获取当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── 数据库枚举 ──

class UserRole(enum.StrEnum):
    """用户角色"""
    normal = "normal"       # 普通用户
    advanced = "advanced"   # 高级用户
    admin = "admin"         # 管理员


class SkillType(enum.StrEnum):
    """技能类型"""
    temporary = "temporary"     # 临时（会话级）
    persistent = "persistent"   # 持久化


# ── 数据表定义 ──

class User(Base):
    """用户表 —— 多租户核心，所有数据归属 user_id"""
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True)              # 用户唯一ID
    username = Column(String(64), unique=True, nullable=False, index=True)  # 用户名
    password_hash = Column(String(128), nullable=False)         # 密码哈希
    role = Column(SAEnum(UserRole), default=UserRole.normal, nullable=False)  # 角色
    default_model = Column(String(64), default="deepseek-chat") # 默认模型
    conversation_style = Column(String(32), default="balanced") # 对话风格偏好
    preferred_tools = Column(JSON, default=list)                # 常用工具列表
    is_active = Column(Boolean, default=True)                   # 是否激活
    created_at = Column(DateTime, default=_utcnow)              # 创建时间
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)  # 更新时间

    # 用户画像字段
    profile_summary = Column(Text, default="")        # 用户习惯摘要（长期记忆）
    long_term_features = Column(JSON, default=dict)   # 用户长期特征提取


class Session(Base):
    """会话表 —— 用户会话信息"""
    __tablename__ = "sessions"

    session_id = Column(String(36), primary_key=True)                    # 会话ID
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)  # 所属用户
    title = Column(String(128), default="新对话")                         # 会话标题
    message_count = Column(Integer, default=0)                           # 消息数量
    summary = Column(Text, default="")                                   # 中期摘要记忆
    is_active = Column(Boolean, default=True)                            # 是否活跃
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Message(Base):
    """消息表 —— 存储对话历史"""
    __tablename__ = "messages"

    message_id = Column(String(36), primary_key=True)                               # 消息ID
    session_id = Column(String(36), ForeignKey("sessions.session_id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)          # user | assistant | system | tool
    content = Column(Text, default="")                 # 消息内容
    tool_calls = Column(JSON, default=None)             # 工具调用信息
    tool_call_id = Column(String(64), default=None)     # 工具调用ID
    prompt_tokens = Column(Integer, default=0)          # prompt token 数
    completion_tokens = Column(Integer, default=0)      # 生成 token 数
    trace_id = Column(String(36), default=None)          # 关联的 TraceID
    created_at = Column(DateTime, default=_utcnow)


class ToolPreset(Base):
    """全局预置工具表 —— 人工开发、安全审计的标准化工具"""
    __tablename__ = "tool_presets"

    tool_id = Column(String(36), primary_key=True)                  # 工具ID
    name = Column(String(64), unique=True, nullable=False)           # 工具名称
    description = Column(Text, default="")                           # 工具描述
    parameters = Column(JSON, default=dict)                          # JSON Schema 参数定义
    handler_module = Column(String(128), nullable=False)             # Python 模块路径
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


class Skill(Base):
    """用户私有动态技能表 —— LLM 自研 Skill，严格归属 user_id"""
    __tablename__ = "skills"

    skill_id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)        # Skill 名称
    description = Column(Text, default="")             # Skill 描述
    code = Column(Text, nullable=False)                # 源代码
    language = Column(String(32), default="python")    # 编程语言
    parameters = Column(JSON, default=dict)            # 参数 JSON Schema（OpenAI function calling 格式）
    tags = Column(JSON, default=list)                  # 标签
    skill_type = Column(SAEnum(SkillType), default=SkillType.temporary)  # 临时/持久
    embedding = Column(JSON, default=None)             # 向量嵌入（用于语义检索）
    usage_count = Column(Integer, default=0)           # 使用次数
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class LogRecord(Base):
    """全链路日志表 —— 结构化日志，TraceID 串联"""
    __tablename__ = "log_records"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(36), nullable=False, index=True)     # 唯一追踪ID
    user_id = Column(String(36), default=None, index=True)        # 用户ID
    session_id = Column(String(36), default=None, index=True)     # 会话ID
    level = Column(String(16), default="INFO")                    # 日志级别
    component = Column(String(64), default="system")              # 组件名称
    message = Column(Text, default="")                             # 日志内容
    metadata_json = Column(JSON, default=dict)                     # 扩展元数据
    created_at = Column(DateTime, default=_utcnow, index=True)


class AnomalyRecord(Base):
    """异常故障表 —— 与普通日志分离存储，支持独立复盘"""
    __tablename__ = "anomaly_records"

    anomaly_id = Column(String(36), primary_key=True)             # 异常唯一ID
    trace_id = Column(String(36), nullable=False, index=True)      # 关联 TraceID
    user_id = Column(String(36), default=None, index=True)         # 触发用户
    error_type = Column(String(64), nullable=False)                # 错误类型
    stack_trace = Column(Text, default=None)                       # 堆栈信息
    context = Column(JSON, default=dict)                           # 完整上下文
    problem_code = Column(Text, default=None)                      # 问题代码
    retry_status = Column(String(16), default="pending")           # 重试状态
    resolved = Column(Boolean, default=False)                      # 是否已解决
    created_at = Column(DateTime, default=_utcnow)                 # 发生时间
    resolved_at = Column(DateTime, default=None)                   # 解决时间
