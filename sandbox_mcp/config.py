"""
MCP Sandbox Server — 独立配置
从环境变量加载，不依赖 app.config
"""
from __future__ import annotations
import os


def getenv(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ── 执行模式 ──
SANDBOX_MODE: str = getenv("MCP_SANDBOX_MODE", "mock")      # mock | docker | e2b
SANDBOX_TIMEOUT: int = int(getenv("MCP_SANDBOX_TIMEOUT", "30"))
SANDBOX_TMP_DIR: str = getenv("MCP_SANDBOX_TMP_DIR", "/tmp/sandbox-mcp")

# ── Docker ──
DOCKER_IMAGE: str = getenv("MCP_DOCKER_IMAGE", "python:3.11-slim")
DOCKER_MEM_LIMIT: str = getenv("MCP_DOCKER_MEM_LIMIT", "256m")
DOCKER_CPU_LIMIT: int = int(getenv("MCP_DOCKER_CPU_LIMIT", "1"))

# ── E2B ──
E2B_API_KEY: str = getenv("MCP_E2B_API_KEY", "")
E2B_TEMPLATE: str = getenv("MCP_E2B_TEMPLATE", "")

# ── Server ──
MCP_SERVER_NAME: str = getenv("MCP_SERVER_NAME", "sandbox-mcp")
MCP_SERVER_VERSION: str = getenv("MCP_SERVER_VERSION", "1.0.0")
MCP_TRANSPORT: str = getenv("MCP_TRANSPORT", "stdio")       # stdio | sse
MCP_HOST: str = getenv("MCP_HOST", "127.0.0.1")
MCP_PORT: int = int(getenv("MCP_PORT", "8101"))
