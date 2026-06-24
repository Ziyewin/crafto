"""
E2B 云端沙箱执行器
使用 E2B（https://e2b.dev）云计算沙箱
"""
from __future__ import annotations
from sandbox_mcp.executor.base import BaseExecutor, ExecutionResult
from sandbox_mcp.config import E2B_API_KEY, E2B_TEMPLATE, SANDBOX_TIMEOUT
import time
import logging

logger = logging.getLogger("sandbox-mcp.executor.e2b")


class E2BExecutor(BaseExecutor):
    """
    E2B 云端沙箱执行器
    需要 MCP_E2B_API_KEY 环境变量
    """

    @property
    def name(self) -> str:
        return "e2b"

    async def execute(self, code: str, execution_id: str, **kwargs) -> ExecutionResult:
        if not E2B_API_KEY:
            return ExecutionResult(
                success=False,
                error="E2B API Key 未配置，请设置 MCP_E2B_API_KEY 环境变量",
                execution_id=execution_id,
            )

        start = time.monotonic()
        try:
            from e2b_code_interpreter import Sandbox

            sb = Sandbox(api_key=E2B_API_KEY)
            result = sb.run_code(code)

            elapsed = int((time.monotonic() - start) * 1000)
            if result.error:
                return ExecutionResult(
                    success=False, error=str(result.error),
                    output=result.logs or "",
                    execution_id=execution_id, execution_time_ms=elapsed,
                )
            return ExecutionResult(
                success=True,
                output=result.text or result.logs or "",
                execution_id=execution_id, execution_time_ms=elapsed,
                metadata={"charts": result.charts if hasattr(result, "charts") else []},
            )
        except ImportError:
            return ExecutionResult(
                success=False,
                error="e2b_code_interpreter 未安装，请执行: pip install e2b-code-interpreter",
                execution_id=execution_id,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                success=False, error=str(e),
                execution_id=execution_id, execution_time_ms=elapsed,
            )

    async def health(self) -> dict:
        return {
            "status": "ok" if E2B_API_KEY else "disabled",
            "executor": self.name,
            "api_key_configured": bool(E2B_API_KEY),
        }
