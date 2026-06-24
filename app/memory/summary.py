"""Mid-term summary memory — compresses long conversations into condensed summaries.
Triggered when token count or round count exceeds threshold."""
from __future__ import annotations
from app.models.deepseek import get_llm_client
from app.config import settings
from app.db.database import get_db_sync
from app.models.db_models import Session as SessionModel
import logging

logger = logging.getLogger("memory.summary")

SUMMARY_PROMPT = """请你仔细阅读以下对话内容，生成一个简洁的摘要（200字以内），包含：
1. 用户的核心需求/问题
2. 已经完成的步骤和结果
3. 未完成的事项或待办
4. 关键的事实性信息（如配置、偏好、数据等）

对话内容：
{conversation_text}

请直接输出摘要，不要额外说明。"""


class SummaryMemory:
    """Manages session-level summaries — generated when context grows large."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._summary: str = ""

    async def load(self) -> str:
        """Load existing summary from DB."""
        if self._summary:
            return self._summary
        try:
            db = get_db_sync()
            session = db.query(SessionModel).filter_by(session_id=self.session_id).first()
            if session and session.summary:
                self._summary = session.summary
            db.close()
        except Exception as e:
            logger.warning("Failed to load summary: %s", e)
        return self._summary

    async def should_summarize(self, conversation: list[dict]) -> bool:
        """Check if summary is needed — token threshold or 25+ rounds."""
        total_chars = sum(len(m.get("content", "")) for m in conversation)
        total_tokens = total_chars // 4
        return total_tokens > settings.summary_trigger_tokens or len(conversation) > 25

    async def generate_summary(self, conversation_text: str) -> str:
        """Call LLM to generate/update summary."""
        if not conversation_text.strip():
            return self._summary

        prompt = SUMMARY_PROMPT.format(conversation_text=conversation_text[:6000])

        try:
            client = get_llm_client()
            response = await client.chat([
                {"role": "system", "content": "你是一个善于总结的AI助手。"},
                {"role": "user", "content": prompt},
            ])
            new_summary = response.content.strip()
            # Merge with previous summary if exists
            if self._summary:
                self._summary = self._merge_summaries(self._summary, new_summary)
            else:
                self._summary = new_summary
        except Exception as e:
            logger.error("Summary generation failed: %s", e)

        await self._persist()
        return self._summary

    def _merge_summaries(self, old: str, new: str) -> str:
        """Simple concatenation with dedup prefix."""
        if new.startswith(old[:50]):
            return new  # new already contains old
        return f"[旧摘要] {old}\n[新摘要] {new}"

    async def _persist(self):
        try:
            db = get_db_sync()
            session = db.query(SessionModel).filter_by(session_id=self.session_id).first()
            if session:
                session.summary = self._summary
                db.commit()
            db.close()
        except Exception as e:
            logger.warning("Failed to persist summary: %s", e)

    def get_summary(self) -> str:
        return self._summary
