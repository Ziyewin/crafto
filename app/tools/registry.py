"""Tool registry — dual-system: global preset tools + user private dynamic skills."""
from __future__ import annotations
from app.tools.preset import get_preset_tools, execute_preset_tool
from app.tools.skill_manager import SkillManager
from typing import Optional
import json
import logging

logger = logging.getLogger("tools.registry")


from app.sandbox.mcp_manager import mcp_manager


class ToolRegistry:
    """Central tool dispatcher.
    Priority: User persistent skill > Global preset tool > LLM-generated temp code.
    """

    def __init__(self, user_id: str, mcp_enabled: bool = True):
        self.user_id = user_id
        self.skill_mgr = SkillManager(user_id)
        self.mcp_enabled = mcp_enabled

    def _load_user_skills(self) -> list[dict]:
        """同步加载用户持久化 Skill，转为 OpenAI function calling 格式"""
        try:
            from app.db.database import get_db_sync
            from app.models.db_models import Skill, SkillType
            db = get_db_sync()
            skills = db.query(Skill).filter_by(
                user_id=self.user_id,
                skill_type=SkillType.persistent,
                is_active=True,
            ).all()
            db.close()
            result = []
            for s in skills:
                params = s.parameters or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
                result.append({
                    "type": "function",
                    "function": {
                        "name": s.name,
                        "description": s.description or f"用户私有 Skill: {s.name}",
                        "parameters": params,
                    }
                })
            return result
        except Exception as e:
            logger.warning("加载用户 Skill 失败: %s", e)
            return []

    def get_available_tools(self, include_code_gen: bool = False) -> list[dict]:
        """Return all available tools as OpenAI-compatible function definitions."""
        tools = []

        # 0. MCP 服务工具（自动发现的）
        if self.mcp_enabled:
            mcp_tools = mcp_manager.get_openai_tools()
            tools.extend(mcp_tools)

        # 1. Global preset tools
        for name, meta in get_preset_tools().items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": meta["description"],
                    "parameters": meta["parameters"],
                }
            })

        # 2. User private persistent Skills —— 按名称匹配，在沙箱中一次性执行
        user_skills = self._load_user_skills()
        tools.extend(user_skills)

        # 3. If user has code generation permission, add a generic code executor
        if include_code_gen:
            tools.append({
                "type": "function",
                "function": {
                    "name": "execute_python_code",
                    "description": "编写并执行 Python 代码（仅限数据处理、计算、图表绘制、文件操作等无专用工具的场景使用；查询实时行情/天气/地理等数据请优先使用其他专用工具）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute in the sandbox"
                            },
                            "description": {
                                "type": "string",
                                "description": "Brief description of what this code does"
                            }
                        },
                        "required": ["code", "description"]
                    }
                }
            })

        return tools

    async def execute_tool(self, tool_name: str, arguments: dict, session_id: str = None) -> dict:
        """Execute a tool by name. Routes to the correct handler."""
        from app.models.schemas import ToolResult

        import time
        start = time.time()

        try:
            # 1. Try user persistent skills first
            skill = await self.skill_mgr.match_skill(tool_name)
            if skill:
                result = await self.skill_mgr.execute_skill(skill["skill_id"], arguments)
                elapsed = int((time.time() - start) * 1000)
                return {
                    "tool_name": tool_name,
                    "success": True,
                    "output": result,
                    "execution_time_ms": elapsed,
                }

            # 2. Try global preset tools
            preset_tools = get_preset_tools()
            if tool_name in preset_tools:
                result = await execute_preset_tool(tool_name, arguments)
                elapsed = int((time.time() - start) * 1000)
                return {
                    "tool_name": tool_name,
                    "success": True,
                    "output": str(result),
                    "execution_time_ms": elapsed,
                }

            # 3. If it's the generic code executor
            if tool_name == "execute_python_code":
                from app.sandbox.mcp_client import sandbox_client
                code = arguments.get("code", "")
                result = await sandbox_client.execute_code(code=code, user_id=self.user_id)
                elapsed = int((time.time() - start) * 1000)
                return {
                    "tool_name": tool_name,
                    "success": result.get("success", False),
                    "output": result.get("output", ""),
                    "error": result.get("error"),
                    "execution_time_ms": elapsed,
                }

            # MCP 工具路由（带 service__tool 前缀）
            if tool_name in mcp_manager._tool_map or "__" in tool_name:
                result = await mcp_manager.execute_tool(tool_name, arguments)
                elapsed = int((time.time() - start) * 1000)
                return {
                    "tool_name": tool_name,
                    "success": result.get("success", result.get("output", "") is not None),
                    "output": result.get("output", json.dumps(result, ensure_ascii=False)),
                    "execution_time_ms": elapsed,
                }
            raise ValueError(f"Unknown tool: {tool_name}")

        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            logger.error("Tool execution failed: %s", e)
            return {
                "tool_name": tool_name,
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time_ms": elapsed,
            }
