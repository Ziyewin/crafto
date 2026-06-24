"""
本地子进程执行器（Mock 模式）
与原 app/sandbox/client.py 的 _mock_execute 功能一致
"""
from __future__ import annotations
from sandbox_mcp.executor.base import BaseExecutor, ExecutionResult
from sandbox_mcp.config import SANDBOX_TIMEOUT, SANDBOX_TMP_DIR
import asyncio
import sys
import tempfile
import os
import time
import logging

logger = logging.getLogger("sandbox-mcp.executor.mock")


class MockExecutor(BaseExecutor):
    """
    本地子进程执行器
    将代码写入临时文件 → 子进程执行 → 捕获 stdout/stderr → 清理
    """

    @property
    def name(self) -> str:
        return "mock"

    async def execute(self, code: str, execution_id: str, **kwargs) -> ExecutionResult:
        start = time.monotonic()
        os.makedirs(SANDBOX_TMP_DIR, exist_ok=True)

        # 写入临时文件
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False,
            dir=SANDBOX_TMP_DIR,
        )
        try:
            tmp.write(code)
            tmp_path = tmp.name
            tmp.close()

            # 子进程执行
            proc = await asyncio.create_subprocess_exec(
                sys.executable, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=SANDBOX_TMP_DIR,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=SANDBOX_TIMEOUT,
                )
            except asyncio.TimeoutError:
                proc.kill()
                elapsed = int((time.monotonic() - start) * 1000)
                return ExecutionResult(
                    success=False, error=f"执行超时（{SANDBOX_TIMEOUT}s）",
                    execution_id=execution_id, execution_time_ms=elapsed,
                )

            elapsed = int((time.monotonic() - start) * 1000)
            if proc.returncode != 0:
                return ExecutionResult(
                    success=False,
                    output=stdout.decode("utf-8", errors="replace"),
                    error=stderr.decode("utf-8", errors="replace"),
                    execution_id=execution_id, execution_time_ms=elapsed,
                )
            return ExecutionResult(
                success=True,
                output=stdout.decode("utf-8", errors="replace"),
                execution_id=execution_id, execution_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ExecutionResult(
                success=False, error=str(e),
                execution_id=execution_id, execution_time_ms=elapsed,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    async def health(self) -> dict:
        return {
            "status": "ok",
            "executor": self.name,
            "python": sys.version,
            "tmp_dir": SANDBOX_TMP_DIR,
            "timeout": SANDBOX_TIMEOUT,
        }
