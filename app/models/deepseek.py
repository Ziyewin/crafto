"""DeepSeek LLM 客户端 —— 使用 OpenAI 兼容接口调用 DeepSeek API
支持非流式和流式两种调用模式，自动处理 token 统计和错误
"""
from __future__ import annotations
from app.models.llm_client import BaseLLMClient, LLMConfig, LLMResponse, LLMUsage
from app.config import settings
from typing import AsyncIterator, Optional
import logging

logger = logging.getLogger("deepseek")


class DeepSeekClient(BaseLLMClient):
    """DeepSeek API 客户端 —— 基于 OpenAI SDK 实现"""

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            # 从全局配置加载默认参数
            config = LLMConfig(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
        super().__init__(config)
        self._client = None  # 懒加载 AsyncOpenAI 客户端

    def _get_client(self):
        """获取或创建 AsyncOpenAI 客户端"""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        stream: bool = False,
    ) -> LLMResponse:
        """发送对话请求（非流式模式）"""
        client = self._get_client()
        kwargs = dict(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            stream=stream,
        )
        if tools:
            kwargs["tools"] = tools

        try:
            if stream:
                return await self._handle_stream(client, **kwargs)

            # 非流式调用
            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content or ""
            usage = response.usage

            # 调试日志：查看原始响应
            logger.debug("DeepSeek finish_reason=%s, has_tool_calls=%s",
                         choice.finish_reason,
                         bool(choice.message.tool_calls))

            # 提取原生 tool_calls
            tool_calls_data = None
            if choice.message.tool_calls:
                tool_calls_data = []
                for tc in choice.message.tool_calls:
                    tc_dict = {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    tool_calls_data.append(tc_dict)
                    logger.debug("工具调用: %s(%s)", tc.function.name, tc.function.arguments)

            return LLMResponse(
                content=content,
                usage=LLMUsage(
                    prompt_tokens=usage.prompt_tokens or 0,
                    completion_tokens=usage.completion_tokens or 0,
                    total_tokens=(usage.prompt_tokens or 0) + (usage.completion_tokens or 0),
                ),
                finish_reason=choice.finish_reason or "stop",
                tool_calls=tool_calls_data,
            )
        except Exception as e:
            logger.error("DeepSeek API 调用失败: %s", e)
            raise

    async def _handle_stream(self, client, **kwargs) -> LLMResponse:
        """处理流式响应，聚合成完整 LLMResponse"""
        content_parts = []
        usage = LLMUsage()
        finish_reason = "stop"
        kwargs["stream"] = True

        response = await client.chat.completions.create(**kwargs)
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
            if chunk.usage:
                usage.prompt_tokens = chunk.usage.prompt_tokens or 0
                usage.completion_tokens = chunk.usage.completion_tokens or 0
                usage.total_tokens = (chunk.usage.prompt_tokens or 0) + (chunk.usage.completion_tokens or 0)

        return LLMResponse(
            content="".join(content_parts),
            usage=usage,
            finish_reason=finish_reason,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """流式对话 —— 逐 chunk 产出文本"""
        client = self._get_client()
        kwargs = dict(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools

        try:
            response = await client.chat.completions.create(**kwargs)
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error("DeepSeek 流式输出错误: %s", e)
            raise

    def count_tokens(self, text: str) -> int:
        """估算 token 数 —— 中英文混合约 4 字符/token"""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except ImportError:
            return len(text) // 4 + 1


# ── 全局工厂 ──

_llm_instance = None


def get_llm_client() -> DeepSeekClient:
    """获取全局 LLM 客户端单例"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = DeepSeekClient()
    return _llm_instance
