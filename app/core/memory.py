"""记忆编排模块 —— 协调短时记忆、摘要记忆、长期向量记忆三级体系"""
from __future__ import annotations
from app.memory.short_term import ShortTermMemory
from app.memory.summary import SummaryMemory
from app.memory.long_term import LongTermMemory
from app.config import settings
import logging

logger = logging.getLogger("core.memory")


class MemoryOrchestrator:
    """三级记忆编排器：
    - 短时记忆：当前会话的消息窗口，存 Redis
    - 摘要记忆：对话超阈值后自动压缩摘要，存 SQLite
    - 长期记忆：跨会话的向量记忆，存 Qdrant/向量库
    """

    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.short_term = ShortTermMemory(session_id, user_id)
        self.summary = SummaryMemory(session_id)
        self.long_term = LongTermMemory(user_id)

    async def initialize(self):
        """初始化：加载已有的摘要和长期记忆"""
        await self.summary.load()

    async def add_user_message(self, content: str):
        """记录用户消息到短时记忆"""
        self.short_term.add_message("user", content)

    async def add_assistant_message(self, content: str, tool_calls: list = None):
        """记录助手回复到短时记忆"""
        self.short_term.add_message("assistant", content, tool_calls=tool_calls)

    async def add_tool_message(self, content: str, tool_call_id: str):
        """记录工具执行结果到短时记忆"""
        self.short_term.add_message("tool", content, tool_call_id=tool_call_id)

    async def build_context(self) -> list[dict]:
        """构建 LLM 上下文：摘要(长期) + 记忆提示 + 短时消息"""
        messages = []

        # 1. 系统提示（用 agent.py 中的 REACT_SYSTEM_PROMPT）
        from app.core.agent import REACT_SYSTEM_PROMPT
        system_parts = [REACT_SYSTEM_PROMPT]

        # 加载摘要记忆
        summary_text = self.summary.get_summary()
        if summary_text:
            system_parts.append(f"\n## 当前会话摘要\n{summary_text}")

        # 检索长期记忆
        # 从短时记忆中提取最近用户消息作为查询
        recent_msgs = self.short_term.get_messages(limit=5)
        for msg in reversed(recent_msgs):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                if query:
                    memories = await self.long_term.retrieve(query)
                    memory_prompt = self.long_term.build_context_prompt(memories)
                    if memory_prompt:
                        system_parts.append(f"\n{memory_prompt}")
                break

        messages.append({"role": "system", "content": "\n".join(system_parts)})

        # 2. 短时消息（在 token 预算内）
        context_msgs = self.short_term.get_context_messages(
            max_tokens=settings.max_memory_tokens
        )
        # 3. 校验消息顺序：过滤孤立 tool 消息
        # DeepSeek/OpenAI API 要求每个 tool 消息前面必须有对应 tool_calls 的 assistant 消息
        expected_tool_call_ids: set[str] = set()
        validated_msgs: list[dict] = []
        for msg in context_msgs:
            if msg.get("role") == "assistant":
                if msg.get("tool_calls"):
                    expected_tool_call_ids = {tc.get("id", "") for tc in msg["tool_calls"]}
                else:
                    expected_tool_call_ids = set()
                validated_msgs.append(msg)
            elif msg.get("role") == "tool":
                if msg.get("tool_call_id") in expected_tool_call_ids:
                    validated_msgs.append(msg)
                else:
                    logger.warning(
                        "过滤孤立 tool 消息: tool_call_id=%s (无前置 tool_calls)",
                        msg.get("tool_call_id"),
                    )
            else:
                validated_msgs.append(msg)
        messages.extend(validated_msgs)

        return messages

    async def summarize_if_needed(self):
        """检查是否需要生成摘要，需要时自动触发"""
        messages = self.short_term.get_messages()
        should = await self.summary.should_summarize(messages)
        if should:
            conversation_text = "\n".join(
                f"{m['role']}: {m['content'][:500]}"
                for m in messages[-30:]  # 最近30条
            )
            await self.summary.generate_summary(conversation_text)
            logger.info("已为会话 %s 生成摘要", self.session_id)

    async def store_long_term_memories(self):
        """从对话中提取并存储长期记忆"""
        messages = self.short_term.get_messages(limit=20)
        count = await self.long_term.extract_and_store(messages)
        if count > 0:
            logger.info("为会话 %s 存储了 %d 条长期记忆", self.session_id, count)

    def get_short_term_messages(self, limit: int = 50) -> list[dict]:
        """获取短时消息"""
        return self.short_term.get_messages(limit=limit)
