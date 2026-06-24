"""统一 LLM 客户端接口抽象层 —— 支持 DeepSeek、OpenAI、通义千问等模型无缝切换
所有模型实现都必须继承 BaseLLMClient，实现 chat、chat_stream、count_tokens 方法
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Any
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """LLM 模型连接配置"""
    api_key: str                    # API 密钥
    base_url: str                   # API 基础地址
    model: str                      # 模型名称
    max_tokens: int = 8192          # 最大生成 token 数
    temperature: float = 0.7        # 温度参数
    top_p: float = 0.9             # top_p 采样参数


@dataclass
class LLMUsage:
    """Token 使用统计"""
    prompt_tokens: int = 0         # 输入 token 数
    completion_tokens: int = 0     # 输出 token 数
    total_tokens: int = 0          # 总 token 数


@dataclass
class LLMResponse:
    """LLM 响应封装"""
    content: str                    # 生成内容
    usage: LLMUsage                # 用量统计
    finish_reason: str = "stop"    # 结束原因
    thinking: Optional[str] = None # 思考过程（如果有）
    tool_calls: Optional[list[dict]] = None  # 工具调用列表（原生）


class BaseLLMClient(ABC):
    """抽象 LLM 客户端 —— 所有模型提供商必须实现的接口"""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False,
    ) -> LLMResponse:
        """发送对话请求（非流式）"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """发送对话请求（流式）"""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """估算文本 token 数"""
        ...

    def get_model_name(self) -> str:
        """获取当前模型名称"""
        return self.config.model
