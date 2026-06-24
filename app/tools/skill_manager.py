"""Dynamic skill manager — LLM-generated code skills, user-private."""
from __future__ import annotations
from app.models.db_models import Skill, SkillType
from app.db.database import get_db_sync
from app.db.vector_store import store_skill_embedding, search_skills
from app.sandbox.client import execute_in_sandbox
from app.config import settings
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger("tools.skill_manager")


class SkillManager:
    """Manages user-private skills — temporary and persistent."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def match_skill(self, skill_name: str) -> dict | None:
        """Try to find a persistent skill by exact name."""
        try:
            db = get_db_sync()
            skill = db.query(Skill).filter_by(
                user_id=self.user_id,
                name=skill_name,
                skill_type=SkillType.persistent,
                is_active=True,
            ).first()
            db.close()
            if skill:
                return {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "code": skill.code,
                    "language": skill.language,
                    "description": skill.description,
                }
        except Exception as e:
            logger.error("Skill match error: %s", e)
        return None

    async def search_skills(self, query: str, top_k: int = None) -> list[dict]:
        """Search user's persistent skills by semantic similarity."""
        if top_k is None:
            top_k = settings.top_k_skills
        try:
            results = search_skills(self.user_id, query, top_k=top_k)
            db = get_db_sync()
            matched = []
            for r in results:
                skill_id = r["payload"].get("skill_id")
                if skill_id:
                    skill = db.query(Skill).filter_by(skill_id=skill_id, is_active=True).first()
                    if skill:
                        matched.append({
                            "skill_id": skill.skill_id,
                            "name": skill.name,
                            "description": skill.description,
                            "code": skill.code,
                            "language": skill.language,
                            "score": r["score"],
                        })
            db.close()
            return matched
        except Exception as e:
            logger.error("Skill search error: %s", e)
            return []

    async def save_skill(
        self,
        name: str,
        description: str,
        code: str,
        language: str = "python",
        skill_type: SkillType = SkillType.temporary,
        tags: list[str] = None,
    ) -> str:
        """Save a skill to DB and vector store. Returns skill_id."""
        skill_id = str(uuid.uuid4())
        try:
            db = get_db_sync()
            skill = Skill(
                skill_id=skill_id,
                user_id=self.user_id,
                name=name,
                description=description,
                code=code,
                language=language,
                tags=tags or [],
                skill_type=skill_type,
                usage_count=0,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(skill)
            db.commit()
            db.close()

            # Store embedding for semantic search (persistent only)
            if skill_type == SkillType.persistent:
                embed_text = f"{name}: {description}\n{code[:500]}"
                store_skill_embedding(skill_id, embed_text, self.user_id)

            logger.info(
                "Saved skill '%s' (type=%s) for user %s",
                name, skill_type, self.user_id,
            )
        except Exception as e:
            logger.error("Failed to save skill: %s", e)
            raise
        return skill_id

    async def execute_skill(self, skill_id: str, arguments: dict) -> str:
        """Execute a saved skill in the sandbox."""
        db = get_db_sync()
        skill = db.query(Skill).filter_by(skill_id=skill_id).first()
        db.close()

        if not skill:
            raise ValueError(f"Skill {skill_id} not found")

        # Build the execution code: inject arguments as variables
        code = skill.code
        arg_vars = "\n".join(f"{k} = {repr(v)}" for k, v in arguments.items())
        full_code = f"# Auto-injected arguments\n{arg_vars}\n\n# Skill code\n{code}"

        # Update usage count
        try:
            db = get_db_sync()
            db.query(Skill).filter_by(skill_id=skill_id).update(
                {"usage_count": Skill.usage_count + 1}
            )
            db.commit()
            db.close()
        except Exception:
            pass

        result = await execute_in_sandbox(full_code, self.user_id)
        return result.get("output", "") or result.get("error", "No output")

    async def extract_and_persist(
        self,
        code: str,
        description: str,
        session_context: str = "",
    ) -> str | None:
        """AI decides if a temporary code snippet is worth persisting as a skill.
        Returns skill_id if persisted, None otherwise."""
        # Heuristic: persist if code has function definitions and is non-trivial
        has_function = "def " in code or "async def " in code
        is_substantial = len(code) > 80 and has_function

        if not is_substantial:
            return None

        # Auto-generate name from first function
        import re
        match = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", code)
        name = match.group(1) if match else f"auto_skill_{uuid.uuid4().hex[:8]}"

        skill_id = await self.save_skill(
            name=name,
            description=description[:200] if description else "自动生成技能",
            code=code,
            language="python",
            skill_type=SkillType.persistent,
            tags=["auto-generated"],
        )
        logger.info("Auto-persisted skill '%s' (%s) from session", name, skill_id)
        return skill_id
