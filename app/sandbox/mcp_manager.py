"""
MCP 管理器 — 统一管理所有 MCP 服务
==================================
支持两种传输模式：
  - stdio : 本地子进程（sandbox/weather/search/geo）
  - sse   : 远程 HTTP（瑞幸咖啡 / 其他第三方 MCP）

添加新服务只需在 MCP_SERVICE_DEFS 加一行配置。
"""
from __future__ import annotations
import os
import sys
import json
import logging
from typing import Any
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
import httpx

from app.config import settings

logger = logging.getLogger("sandbox.mcp_manager")

# ═══════════════════════════════════════════════════════════
# MCP 服务注册表
# ═══════════════════════════════════════════════════════════
# 在此添加新的 MCP 服务，管理器启动时自动连接
#   type: "stdio" = 本地子进程 | "sse" = 远程 HTTP
#
# stdio 服务需要 path（相对于项目根目录或绝对路径）
#   - 普通模式：填写 path，用当前 Python 执行
#   - 命令模式：填写 command + args，用指定的可执行文件启动（如 pip 包 CLI）
# sse   服务需要 url（完整的 HTTP(S) 地址）+ 可选 headers
#
# 示例：
#   {"name": "my-api", "type": "sse", "url": "https://api.example.com/mcp",
#    "headers": {"Authorization": "Bearer xxx"}}
# ═══════════════════════════════════════════════════════════

MCP_SERVICE_DEFS: list[dict] = [
    # ── 双模式：本地 stdio（集成）或远程 SSE（独立服务集群） ──
    # 默认使用 stdio 模式（由主应用管理子进程生命周期）
    # 如需连接独立 MCP 服务集群（见 mcp-servers/launcher.py），
    # 将 type 改为 "sse"，url 设为 http://127.0.0.1:PORT/sse

    # stdio 模式（本地子进程）                 # SSE 模式（独立 HTTP 服务）
    {"name": "sandbox", "type": "stdio",       # "type": "sse", "url": "http://127.0.0.1:8101/sse",
     "path": "sandbox_mcp/server.py",
     "description": "代码沙箱执行"},
    {"name": "weather", "type": "stdio",       # "type": "sse", "url": "http://127.0.0.1:8102/sse",
     "path": "mcp-services/weather/server.py",
     "description": "实时天气数据"},
    {"name": "geo",     "type": "stdio",       # "type": "sse", "url": "http://127.0.0.1:8104/sse",
     "path": "mcp-services/geo/server.py",
     "description": "IP 地理信息 + 城市位置"},

    # ── 远程 Streamable HTTP 服务 ──
    {
        "name": "luckin",
        "type": "streamable",
        "url": "https://gwmcp.lkcoffee.com/order/user/mcp",
        "headers": {},
        "description": "瑞幸咖啡 MCP 服务",
    },

    # ── 在这里添加更多 MCP 服务 ──
    # 本地子进程：{"name": "...", "type": "stdio", "path": "server.py"}
    # 远程 SSE：   {"name": "...", "type": "sse",  "url": "http://.../sse"}
    # Streamable：{"name": "...", "type": "streamable", "url": "https://...", "headers": {...}}
]


# ═══════════════════════════════════════════════════════════
# 单个 MCP 服务连接
# ═══════════════════════════════════════════════════════════

def _build_mcp_service_defs() -> list[dict]:
    """构建 MCP 服务配置列表，从 Settings 注入密钥"""
    defs = []
    for svc in MCP_SERVICE_DEFS:
        svc = dict(svc)  # shallow copy
        if svc.get("name") == "luckin" and settings.luckin_mcp_key:
            svc["headers"] = {
                "Authorization": f"Bearer {settings.luckin_mcp_key}",
            }
        defs.append(svc)
    return defs

class MCPServiceConnection:
    """一个 MCP 服务的连接（支持 stdio 或 sse）"""

    def __init__(self, config: dict):
        self.name: str = config["name"]
        self.service_type: str = config.get("type", "stdio")    # stdio | sse
        self.command: str = config.get("command", "")
        self.server_path: str = config.get("path", "")
        self.command: str = config.get("command", "")
        self.args: list[str] = config.get("args", [])
        self.url: str = config.get("url", "")
        self.headers: dict = config.get("headers", {}) or {}
        self.description: str = config.get("description", "")

        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self.tools: list[dict] = []
        self.connected: bool = False

        # stdio 路径解析
        if self.service_type == "stdio" and self.server_path and not self.command:
            self.server_path = self._resolve_path(self.server_path)

    def _resolve_path(self, path: str) -> str:
        candidates = [
            path,
            os.path.join(os.getcwd(), path),
            os.path.join(os.path.dirname(__file__), "..", "..", path),
        ]
        for c in candidates:
            if os.path.isfile(os.path.abspath(c)):
                return os.path.abspath(c)
        return os.path.abspath(path)

    async def start(self) -> bool:
        """连接 MCP 服务，自动发现工具列表"""
        # 前置检查：stdio 模式需要确认二进制/脚本存在
        if self.service_type == "stdio" and self.command:
            if not os.path.isfile(self.command):
                logger.warning("⚠️ MCP[%s] 二进制不存在: %s", self.name, self.command)
                return False

        try:
            # 根据类型选择传输方式
            if self.service_type == "stdio":
                if self.command:
                    # 自定义命令模式（如已安装的 pip 包 CLI）
                    cmd = self.command
                    args = self.args or []
                    logger.info("  MCP[%s] 启动命令: %s %s", self.name, cmd, " ".join(args))
                else:
                    cmd = sys.executable
                    args = [self.server_path]
                transport = await self._exit_stack.enter_async_context(
                    stdio_client(StdioServerParameters(
                        command=cmd, args=args,
                        env={**os.environ},
                    ))
                )
                read, write = transport
            elif self.service_type == "sse":
                transport = await self._exit_stack.enter_async_context(
                    sse_client(self.url, headers=self.headers)
                )
                read, write = transport
            elif self.service_type in ("streamable", "streamablehttp"):
                # 创建带自定义 headers 的 HTTP 客户端
                http_client = httpx.AsyncClient(
                    headers=self.headers,
                    timeout=httpx.Timeout(30.0),
                ) if self.headers else None
                transport = await self._exit_stack.enter_async_context(
                    streamable_http_client(self.url, http_client=http_client)
                )
                read, write, _ = transport
            else:
                raise ValueError(f"未知传输类型: {self.service_type}")
            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self._session = session

            # 自动发现工具
            tools_result = await session.list_tools()
            self.tools = []
            for t in tools_result.tools:
                self.tools.append({
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema or {},
                    "service": self.name,
                })
            self.connected = True
            logger.info("✅ MCP[%s] 已连接 (%d 工具)", self.name, len(self.tools))
            return True

        except BaseException as e:
            # 不吞掉键盘中断和系统退出
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            logger.warning("⚠️ MCP[%s] 连接失败: %s", self.name, e)
            return False

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用远程工具"""
        if not self._session:
            raise RuntimeError(f"MCP[{self.name}] 未连接")
        result = await self._session.call_tool(tool_name, arguments)
        if result.content:
            text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"output": text}
        return {"output": ""}

    async def stop(self):
        """断开连接"""
        self.connected = False
        self._session = None
        try:
            await self._exit_stack.aclose()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
# MCP 管理器
# ═══════════════════════════════════════════════════════════

class MCPManager:
    """MCP 管理器 — 统一管理所有服务的连接、发现、路由"""

    def __init__(self):
        self.connections: dict[str, MCPServiceConnection] = {}
        self._tool_map: dict[str, str] = {}   # tool_name → service_name
        self.PARAM_ALIASES: dict[str, str] = {}  # 参数名别名映射（空 = 不转译）

    async def start_all(self):
        """启动并连接所有配置的 MCP 服务（每个连接超时 10 秒）"""
        import asyncio
        for svc in _build_mcp_service_defs():
            conn = MCPServiceConnection(svc)
            try:
                ok = await asyncio.wait_for(conn.start(), timeout=20.0)
            except asyncio.TimeoutError:
                logger.warning("⏱️ MCP[%s] 连接超时(10s)，跳过", svc["name"])
                ok = False
            if ok:
                self.connections[svc["name"]] = conn
                for t in conn.tools:
                    full_name = f"{svc['name']}__{t['name']}"
                    self._tool_map[full_name] = svc["name"]
        logger.info("MCP 管理器就绪: %d/%d 服务已连接",
                     len(self.connections), len(MCP_SERVICE_DEFS))

    def get_openai_tools(self) -> list[dict]:
        """获取所有 MCP 工具的 OpenAI 函数定义（按优先级排序）"""
        tools = []
        # 优先级：luckin 等行动类工具排在最前
        priority = ["luckin", "weather", "geo", "sandbox", "search", "akshare"]
        for svc_name in priority:
            conn = self.connections.get(svc_name)
            if conn:
                for t in conn.tools:
                    full_name = f"{svc_name}__{t['name']}"
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": full_name,
                            "description": f"[{svc_name}] {t['description']}",
                            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                        },
                    })
        # 其余服务
        for svc_name, conn in self.connections.items():
            if svc_name not in priority:
                for t in conn.tools:
                    full_name = f"{svc_name}__{t['name']}"
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": full_name,
                            "description": f"[{svc_name}] {t['description']}",
                            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                        },
                    })
        return tools
    async def execute_tool(self, full_name: str, arguments: dict) -> dict:
        """根据完整工具名路由到对应的 MCP 服务执行"""
        svc_name = self._tool_map.get(full_name)
        if not svc_name:
            parts = full_name.split("__", 1)
            if len(parts) == 2:
                svc_name = parts[0]
                tool_name = parts[1]
            else:
                return {"success": False, "error": f"未知工具: {full_name}"}
        else:
            tool_name = full_name[len(svc_name) + 2:]

        conn = self.connections.get(svc_name)
        if not conn:
            return {"success": False, "error": f"MCP 服务 [{svc_name}] 未连接"}

        # 参数名别名转译：模型传的别名 → 工具实际参数名（避免参数名猜错导致执行失败）
        for alias, real in self.PARAM_ALIASES.items():
            if alias in arguments and real not in arguments:
                arguments[real] = arguments.pop(alias)

        try:
            result = await conn.call_tool(tool_name, arguments)
            if isinstance(result, dict):
                result["service"] = svc_name
                result["tool"] = tool_name
                return result
            return {"output": str(result), "service": svc_name, "tool": tool_name}
        except Exception as e:
            logger.error("MCP 调用失败 %s/%s: %s", svc_name, tool_name, e)
            return {"success": False, "error": str(e), "service": svc_name, "tool": tool_name}

    async def stop_all(self):
        """断开所有 MCP 服务"""
        for conn in self.connections.values():
            await conn.stop()
        self.connections.clear()
        self._tool_map.clear()
        logger.info("所有 MCP 服务已断开")


# ── 全局单例 ──
mcp_manager: MCPManager = MCPManager()
