import os
import sys
_pkg_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_path not in sys.path:
    sys.path.insert(0, _pkg_path)

"""
MCP Sandbox Server — 代码沙箱独立服务
通过 MCP 协议暴露工具：execute_code / scan_code / get_sandbox_status

启动方式:
  python sandbox_mcp/server.py                # stdio 模式
  python sandbox_mcp/server.py --transport sse --port 8101  # SSE 模式
"""
import argparse
import logging
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from sandbox_mcp.config import *
from sandbox_mcp.scanner import scan_code
from sandbox_mcp.executor.base import BaseExecutor
from sandbox_mcp.executor.mock import MockExecutor
from sandbox_mcp.executor.docker import DockerExecutor
from sandbox_mcp.executor.e2b import E2BExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sandbox-mcp.server")


def _get_executor(mode=None):
    mode = mode or SANDBOX_MODE
    executors = {"mock": MockExecutor, "docker": DockerExecutor, "e2b": E2BExecutor}
    cls = executors.get(mode, MockExecutor)
    if mode not in executors:
        logger.warning("未知执行器模式 '%s'，回退到 mock", mode)
    return cls()


mcp = FastMCP(name=MCP_SERVER_NAME, instructions="工业级代码沙箱执行 MCP 服务")


@mcp.tool()
async def execute_code(code: str, executor_mode=None) -> dict:
    """在隔离沙箱中执行 Python 代码（支持 mock/docker/e2b）"""
    import uuid
    execution_id = uuid.uuid4().hex[:12]
    logger.info("执行代码 [%s] mode=%s", execution_id, executor_mode or SANDBOX_MODE)

    violations = await scan_code(code)
    if violations:
        return {"success": False, "output": "", "error": "安全检查未通过",
                "execution_id": execution_id, "violations": violations}

    executor = _get_executor(executor_mode or SANDBOX_MODE)
    result = await executor.execute(code, execution_id)
    return {"success": result.success, "output": result.output, "error": result.error,
            "execution_id": execution_id, "execution_time_ms": result.execution_time_ms,
            "mode": executor.name, "violations": []}


@mcp.tool()
async def scan_code_tool(code: str) -> dict:
    """扫描 Python 代码中的危险模式"""
    violations = await scan_code(code)
    return {"safe": len(violations) == 0, "violations": violations, "total": len(violations)}


@mcp.tool()
async def get_sandbox_status() -> dict:
    """获取所有可用执行器的健康状态"""
    results = {}
    for mode_name in ("mock", "docker", "e2b"):
        try:
            results[mode_name] = await _get_executor(mode_name).health()
        except Exception as e:
            results[mode_name] = {"status": "error", "error": str(e)}
    return {"server": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION,
            "default_mode": SANDBOX_MODE, "executors": results}


def main():
    parser = argparse.ArgumentParser(description="MCP Sandbox Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default=MCP_TRANSPORT)
    parser.add_argument("--host", default=MCP_HOST)
    parser.add_argument("--port", type=int, default=MCP_PORT)
    parser.add_argument("--test", help="直接执行测试代码")
    args = parser.parse_args()

    if args.test:
        import asyncio
        asyncio.run(_run_test(args.test))
        return

    logger.info("启动 MCP Server (transport=%s)", args.transport)
    if args.transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


async def _run_test(code):
    import uuid
    violations = await scan_code(code)
    if violations:
        print(f"不安全: {len(violations)} 个违规")
        for v in violations:
            print(f"  [{v['severity']}] 第{v['line']}行: {v['description']}")
        return
    r = await MockExecutor().execute(code, uuid.uuid4().hex[:12])
    print(f"{'OK' if r.success else 'FAIL'} ({r.execution_time_ms}ms)")
    print(r.output or r.error)


if __name__ == "__main__":
    main()
