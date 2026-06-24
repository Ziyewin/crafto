"""
种子脚本：注册示例 Skill 到数据库
=================================
用法：python scripts/seed_skills.py

效果：
  - 确保 skills 表有 parameters 列（迁移）
  - 将 app/skills/examples/ 中的示例 Skill 注册到数据库
  - 为每个 Skill 生成向量嵌入（语义检索用）
"""
import sys
import os
import sqlite3
import uuid
import json
from datetime import datetime, timezone

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "agent_platform.db")
EXAMPLE_USERNAME = "ye"  # 将 Skill 注册到哪个用户名下


def get_embedding(text: str, dim: int = 128) -> list[float]:
    """Bigram 哈希嵌入（与 vector_store._mock_embed 一致）"""
    vec = [0.0] * dim
    for ch in text:
        h = hash(ch) % (dim - 1)
        if h < 0:
            h += dim - 1
        vec[h] += 1.0
    norm = (sum(v * v for v in vec)) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── 1. 迁移：添加 parameters 列 ──
    c.execute("PRAGMA table_info(skills)")
    cols = {row[1]: row for row in c.fetchall()}
    if "parameters" not in cols:
        c.execute("ALTER TABLE skills ADD COLUMN parameters TEXT DEFAULT '{}'")
        print("+ Added 'parameters' column to skills table")

    # ── 2. 获取目标用户 ──
    c.execute("SELECT user_id FROM users WHERE username=?", (EXAMPLE_USERNAME,))
    row = c.fetchone()
    if not row:
        print(f"! User '{EXAMPLE_USERNAME}' not found; creating...")
        uid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        c.execute(
            "INSERT INTO users (user_id, username, password_hash, role, is_active, created_at, updated_at) "
            "VALUES (?, ?, '', 'admin', 1, ?, ?)",
            (uid, EXAMPLE_USERNAME, now, now),
        )
        print(f"+ Created user '{EXAMPLE_USERNAME}': {uid}")
    else:
        uid = row[0]
        print(f"+ Using user '{EXAMPLE_USERNAME}': {uid}")

    # ── 3. 加载示例 Skill ──
    from app.skills.examples import EXAMPLE_SKILLS

    for sk in EXAMPLE_SKILLS:
        name = sk["name"]

        # 如果已存在则先删除（支持重新 seed）
        c.execute("DELETE FROM skills WHERE name=? AND user_id=?", (name, uid))

        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        c.execute(
            """INSERT INTO skills
               (skill_id, user_id, name, description, code, language,
                parameters, tags, skill_type, usage_count, is_active,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, uid, name, sk["description"], sk["code"], sk["language"],
                json.dumps(sk["parameters"], ensure_ascii=False),
                json.dumps(sk["tags"], ensure_ascii=False),
                "persistent", 0, 1, now, now,
            ),
        )

        # 向量嵌入（存于 vector store 和 skills.embedding 列）
        embed_text = f"{name}: {sk['description']}\n{sk['code'][:500]}"
        vec = get_embedding(embed_text)
        c.execute("UPDATE skills SET embedding=? WHERE skill_id=?", (json.dumps(vec), sid))

        # 也存入向量库（Qdrant / 内存）
        try:
            from app.db.vector_store import store_skill_embedding
            store_skill_embedding(sid, embed_text, uid)
        except Exception as e:
            print(f"  (vector store embedding skipped: {e})")

        print(f"+ Skill '{name}' registered ({sid[:8]}...)")

    conn.commit()
    conn.close()
    print("\n✅ Seed complete. Run 'python scripts/seed_skills.py' to re-seed anytime.")


if __name__ == "__main__":
    main()
