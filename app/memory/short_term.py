"""Short-term (session-level) memory — current conversation rounds, rolling window."""
from __future__ import annotations
from app.db.redis_client import session_push, session_get
from app.config import settings
import json
import logging

logger = logging.getLogger("memory.short_term")


class ShortTermMemory:
    """Manages the current session conversation window.
    Stored in Redis with a rollover/truncation policy."""

    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self._cache: list[dict] = []

    def add_message(self, role: str, content: str, tool_calls: list = None, tool_call_id: str = None):
        msg = {
            "role": role,
            "content": content or "",
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id

        self._cache.append(msg)
        # Persist to Redis
        try:
            session_push(self.session_id, json.dumps(msg, ensure_ascii=False))
        except Exception as e:
            logger.warning("Failed to persist to Redis: %s", e)

    def get_messages(self, limit: int = 50) -> list[dict]:
        """Get recent messages — try Redis first, fall back to in-memory cache."""
        try:
            raw = session_get(self.session_id, 0, limit - 1)
            if raw:
                return [json.loads(m) for m in reversed(raw)]
        except Exception as e:
            logger.warning("Redis read failed: %s", e)
        return self._cache[-limit:]

    def get_context_messages(self, max_tokens: int = None) -> list[dict]:
        """Get messages within token budget, oldest-first for LLM context."""
        if max_tokens is None:
            max_tokens = settings.max_memory_tokens

        messages = self.get_messages()
        # Rough token estimate
        total = 0
        keep = []
        for msg in reversed(messages):
            tokens = len(msg.get("content", "")) // 4 + 1
            if total + tokens > max_tokens:
                break
            keep.append(msg)
            total += tokens
        return list(reversed(keep))

    def clear(self):
        self._cache.clear()
        try:
            from app.db.redis_client import get_redis
            get_redis().delete(f"session:{self.session_id}:messages")
        except Exception:
            pass

    def count_tokens(self) -> int:
        total = sum(len(m.get("content", "")) for m in self._cache)
        return total // 4 + len(self._cache)
