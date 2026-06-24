"""
DeepSeek API 集成测试脚本 —— 验证平台核心能力
使用方法：
    export DEEPSEEK_API_KEY=sk-your-key-here
    python test_deepseek.py

测试覆盖：
1. 用户注册/登录
2. 创建会话
3. Agent 简单对话（预置工具调用）
4. Agent 复杂任务（代码生成 + 沙箱执行）
"""
import os
import sys
import json
import asyncio
import time
from pathlib import Path

# 加载 .env 文件（如果存在）
dotenv_path = Path(__file__).resolve().parent / ".env"
if dotenv_path.exists():
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# 确保能找到 app 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置 API Key（如未设置环境变量，将跳过 AI 调用测试）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
print(DEEPSEEK_API_KEY)
HAS_API_KEY = bool(DEEPSEEK_API_KEY)

if not HAS_API_KEY:
    print("⚠️  未设置 DEEPSEEK_API_KEY 环境变量，将跳过 AI 对话测试")
    print("   设置方式: export DEEPSEEK_API_KEY=sk-your-key-here")
    print()


async def test_full_platform():
    """完整平台流程测试"""
    from app.db.database import init_db, get_db_sync
    from app.models.db_models import User
    from app.core.agent import Agent
    from app.core.session import SessionManager

    print("=" * 60)
    print("🚀 工业级智能 Agent 平台 — 集成测试")
    print("=" * 60)

    # 1. 初始化数据库
    print("\n📦 [1/5] 初始化数据库...")
    init_db()
    print("   ✅ 数据库初始化完成（SQLite）")

    # 2. 创建测试用户
    print("\n👤 [2/5] 创建测试用户...")
    from app.models.db_models import User, UserRole
    from datetime import datetime, timezone
    import uuid

    db = get_db_sync()
    test_user_id = str(uuid.uuid4())
    existing = db.query(User).filter_by(username="test_user").first()

    if existing:
        test_user_id = existing.user_id
        print(f"   ℹ️  使用已有测试用户: {test_user_id}")
    else:
        user = User(
            user_id=test_user_id,
            username="test_user",
            password_hash="test_hash",
            role=UserRole.advanced,  # 高级用户，开放代码沙箱
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        print(f"   ✅ 创建高级用户（代码沙箱权限）: {test_user_id}")
    db.close()

    # 3. 创建测试会话
    print("\n💬 [3/5] 创建测试会话...")
    session_mgr = SessionManager(test_user_id)
    session_id = await session_mgr.create_session("集成测试对话")
    print(f"   ✅ 会话已创建: {session_id}")

    # 4. 创建 Agent 并测试简单对话
    print("\n🤖 [4/5] 测试 Agent 简单对话...")

    agent = Agent(user_id=test_user_id, session_id=session_id, user_role="advanced")
    result = await agent.process_message("你好！请介绍一下你自己。")
    print(f"   💬 用户: 你好！请介绍一下你自己。")
    print(f"   🤖 Agent: {result['reply'][:200]}...")
    if result.get("token_usage"):
        usage = result["token_usage"]
        print(f"   📊 Token: prompt={usage.get('prompt_tokens',0)}, "
              f"completion={usage.get('completion_tokens',0)}")

    # 5. 如果 API Key 存在，测试更多功能
    if HAS_API_KEY:
        print("\n🔧 [5/5] 测试复杂任务（需要 DeepSeek API 密钥）...")

        # 测试预置工具
        print("\n   📍 测试预置工具调用（查天气）...")
        result2 = await agent.process_message("北京今天的天气怎么样？")
        print(f"   💬 用户: 北京今天的天气怎么样？")
        print(f"   🤖 Agent: {result2['reply'][:300]}...")
        if result2.get("tool_calls"):
            for tc in result2["tool_calls"]:
                print(f"   🛠 工具调用: {tc.get('tool_name', 'unknown')}")
        if result2.get("token_usage"):
            usage = result2["token_usage"]
            print(f"   📊 Token累计: prompt={usage.get('prompt_tokens',0)}, "
                  f"completion={usage.get('completion_tokens',0)}")

        # 测试代码执行
        print("\n   💻 测试代码生成执行（复杂任务）...")
        result3 = await agent.process_message(
            "请写一个 Python 程序，计算斐波那契数列前20项并输出。"
        )
        print(f"   💬 用户: 请写一个 Python 程序，计算斐波那契数列前20项...")
        print(f"   🤖 Agent: {result3['reply'][:400]}...")
        if result3.get("tool_calls"):
            for tc in result3["tool_calls"]:
                print(f"   🛠 调用: {tc.get('tool_name', 'unknown')}")
    else:
        print("\n⚠️  [5/5] 跳过复杂任务测试（需要设置 DEEPSEEK_API_KEY）")

    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print()
    print("启动服务:  uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload")
    print("测试 API:  curl http://localhost:8100/health")
    print()


if __name__ == "__main__":
    asyncio.run(test_full_platform())
