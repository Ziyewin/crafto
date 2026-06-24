"""
执行器抽象基类
所有执行器（mock / docker / e2b）必须实现 execute 方法
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExecutionResult:
    """标准化的执行结果"""
    success: bool
    output: str = ""
    error: str = ""
    execution_id: str = ""
    execution_time_ms: int = 0
    metadata: dict = field(default_factory=dict)


class BaseExecutor(ABC):
    """执行器基类"""

    @abstractmethod
    async def execute(self, code: str, execution_id: str, **kwargs) -> ExecutionResult:
        """
        执行代码
        Args:
            code: Python 代码
            execution_id: 唯一执行 ID
            **kwargs: 执行器特定参数
        Returns:
            ExecutionResult
        """
        ...

    @abstractmethod
    async def health(self) -> dict:
        """返回执行器健康状态"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """执行器名称标识"""
        ...
