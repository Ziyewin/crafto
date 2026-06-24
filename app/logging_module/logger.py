"""结构化日志系统 —— TraceID 全链路传播、JSON 格式化输出、上下文变量"""
from __future__ import annotations
import logging
import sys
from contextvars import ContextVar
from typing import Optional
from pythonjsonlogger import jsonlogger

# 上下文变量 —— 跨异步边界传递 TraceID
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def set_trace_id(tid: str):
    """设置当前 TraceID"""
    _trace_id.set(tid)


def get_trace_id() -> Optional[str]:
    """获取当前 TraceID"""
    return _trace_id.get()


class TraceIDFilter(logging.Filter):
    """日志过滤器 —— 自动注入 trace_id 到每条日志记录"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or "-"
        return True


def setup_logging(level: str = "DEBUG"):
    """配置全局日志系统"""
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(trace_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(TraceIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))

    # 抑制第三方库的冗长日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取带名称的 Logger"""
    return logging.getLogger(name)
