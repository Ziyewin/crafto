"""Long-term vector memory — persists across sessions for user habits, preferences, key facts."""
from __future__ import annotations
from app.db.vector_store import store_memory, search_memory
from app.config import settings
import uuid
import logging

logger = logging.getLogger("memory.long_term")


class LongTermMemory:
    """Vector-based long-term memory — user-level, persists across sessions."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def store(self, content: str, metadata: dict = None) -> str:
        """Store a memory item into the vector DB."""
        memory_id = str(uuid.uuid4())
        try:
            store_memory(
                memory_id=memory_id,
                text=content,
                user_id=self.user_id,
                memory_type="long_term",
                metadata=metadata or {},
            )
            logger.debug("Stored long-term memory %s for user %s", memory_id, self.user_id)
        except Exception as e:
            logger.error("Failed to store long-term memory: %s", e)
        return memory_id

    async def retrieve(self, query: str, top_k: int = None) -> list[dict]:
        """Retrieve relevant memories by semantic similarity."""
        if top_k is None:
            top_k = settings.top_k_memory
        try:
            results = search_memory(self.user_id, query, top_k=top_k)
            return results
        except Exception as e:
            logger.error("Failed to retrieve long-term memory: %s", e)
            return []

    async def extract_and_store(self, conversation: list[dict]) -> int:
        """Analyze recent conversation and store important facts as memories.
        Returns count of new memories stored."""
        # Simple heuristic: user messages with factual content
        stored = 0
        for msg in conversation[-10:]:  # Check last 10
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            # Only store if substantial
            if len(content) > 30:
                await self.store(
                    content,
                    metadata={"source": "auto_extract", "conversation_extract": True},
                )
                stored += 1
        return stored

    def build_context_prompt(self, memories: list[dict]) -> str:
        """Build a contextual prompt from retrieved memories."""
        if not memories:
            return ""

        lines = ["## 用户长期记忆提示", "以下是与当前对话相关的历史记忆："]
        for i, mem in enumerate(memories[:5], 1):
            text = mem["payload"].get("text", "")
            score = mem.get("score", 0)
            lines.append(f"{i}. [{score:.2f}] {text}")
        return "\n".join(lines)
