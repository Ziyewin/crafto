"""
MCP 沙箱客户端
============
连接 MCP Sandbox Server 实现代码远程沙箱执行。
自动管理服务器生命周期，支持执行失败降级。

使用方式:
    from app.sandbox.mcp_client import sandbox_client
    result = await sandbox_client.execute_code("print('hello')")
"""
from __future__ import annotations
import sys
import os
import asyncio
import logging
from typing import Any
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.sandbox.code_scanner import scan_code, is_code_safe
from app.sandbox.client import execute_in_sandbox as _direct_execute

logger = logging.getLogger("sandbox.mcp_client")


class SandboxMCPClient:
    """
    MCP 沙箱客户端
    启动 MCP 服务器子进程 → stdio 通信 → 调用远程工具
    如果 MCP 服务器不可用，自动降级到本地直接执行
    """

    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._server_params: StdioServerParameters | None = None
        self._connected = False
        self._server_path = self._find_server()

    def _find_server(self) -> str:
        """查找 MCP 服务器脚本路径"""
        # 尝试多个可能路径
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "sandbox_mcp", "server.py"),
            os.path.join(os.getcwd(), "sandbox_mcp", "server.py"),
        ]
        for path in candidates:
            resolved = os.path.abspath(path)
            if os.path.isfile(resolved):
                logger.info("MCP 服务器路径: %s", resolved)
                return resolved
        logger.warning("MCP 服务器脚本未找到，将使用本地降级模式")
        return ""

    async def start(self) -> bool:
        """
        启动 MCP 连接
        Returns: 是否成功连接到 MCP 服务器
        """
        if not self._server_path:
            logger.info("MCP 服务器未找到，使用本地降级模式")
            return False

        try:
            self._server_params = StdioServerParameters(
                command=sys.executable,
                args=[self._server_path],
                env={**os.environ},
            )
            stdio_transport = await self._exit_stack.enter_async_context(
                stdio_client(self._server_params)
            )
            read, write = stdio_transport
            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self._session = session
            self._connected = True
            logger.info("MCP 沙箱服务器连接成功")
            return True
        except Exception as e:
            logger.warning("MCP 服务器连接失败，使用本地降级模式: %s", e)
            self._connected = False
            return False

    async def execute_code(
        self,
        code: str,
        user_id: str = "",
        executor_mode: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        远程执行代码
        Args:
            code: Python 代码
            user_id: 用户 ID（用于审计日志）
            executor_mode: 执行器模式 mock/docker/e2b
        Returns:
            {"success": bool, "output": str, "error": str, ...}
        """
        if not self._connected or not self._session:
            # 降级: 直接本地执行
            logger.info("MCP 不可用，降级到本地执行")
            return await _direct_execute(code, user_id)

        try:
            args = {"code": code}
            if executor_mode:
                args["executor_mode"] = executor_mode

            result = await self._session.call_tool("execute_code", args)
            # MCP 返回 TextContent，提取文本并解析 JSON
            content = result.content[0].text if result.content else "{}"
            import json
            data = json.loads(content)
            return data

        except Exception as e:
            logger.error("MCP 调用失败，降级到本地执行: %s", e)
            return await _direct_execute(code, user_id)

    async def scan_code(self, code: str) -> dict[str, Any]:
        """远程代码扫描"""
        if not self._connected or not self._session:
            violations = await scan_code(code)
            return {"safe": len(violations) == 0, "violations": violations, "total": len(violations)}

        try:
            result = await self._session.call_tool("scan_code", {"code": code})
            content = result.content[0].text if result.content else "{}"
            import json
            return json.loads(content)
        except Exception:
            violations = await scan_code(code)
            return {"safe": len(violations) == 0, "violations": violations, "total": len(violations)}

    async def get_status(self) -> dict:
        """获取 MCP 沙箱服务器状态"""
        if not self._connected or not self._session:
            return {"server": "local-fallback", "mode": "mock", "executors": {}}

        try:
            result = await self._session.call_tool("get_sandbox_status", {})
            content = result.content[0].text if result.content else "{}"
            import json
            return json.loads(content)
        except Exception:
            return {"server": "local-fallback", "mode": "mock", "error": "query_failed"}

    async def stop(self):
        """关闭 MCP 连接"""
        self._connected = False
        self._session = None
        try:
            await self._exit_stack.aclose()
        except Exception:
            pass
        logger.info("MCP 客户端已关闭")


# ── 全局单例 ──
sandbox_client: SandboxMCPClient = SandboxMCPClient()


async def init_mcp() -> bool:
    """初始化 MCP 客户端（应用启动时调用）"""
    return await sandbox_client.start()


async def close_mcp():
    """关闭 MCP 客户端（应用关闭时调用）"""
    await sandbox_client.stop()
