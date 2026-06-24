"""
Docker 容器执行器
隔离级别更高，每次执行使用独立容器
"""
from __future__ import annotations
from sandbox_mcp.executor.base import BaseExecutor, ExecutionResult
from sandbox_mcp.config import (
    SANDBOX_TIMEOUT, DOCKER_IMAGE, DOCKER_MEM_LIMIT, DOCKER_CPU_LIMIT,
)
import asyncio
import time
import uuid
import logging

logger = logging.getLogger("sandbox-mcp.executor.docker")


class DockerExecutor(BaseExecutor):
    """
    Docker 容器执行器
    每段代码启动一个临时容器，执行完毕自动销毁
    依赖: docker CLI（docker ps 可用）
    """

    @property
    def name(self) -> str:
        return "docker"

    async def _check_docker(self) -> bool:
        """检查 docker CLI 是否可用"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return proc.returncode == 0
        except Exception:
            return False

    async def execute(self, code: str, execution_id: str, **kwargs) -> ExecutionResult:
        if not await self._check_docker():
            return ExecutionResult(
                success=False,
                error="Docker 不可用，请确认 Docker 已安装并运行",
                execution_id=execution_id,
            )

        start = time.monotonic()
        container_name = f"sandbox-{uuid.uuid4().hex[:12]}"
        # 将代码通过 base64 传入 Docker
        import base64
        code_b64 = base64.b64encode(code.encode()).decode()

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", DOCKER_MEM_LIMIT,
            "--cpus", str(DOCKER_CPU_LIMIT),
            "--network", "none",                     # 无网络
            "--read-only",                           # 只读文件系统
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            DOCKER_IMAGE,
            "python3", "-c",
            f"import base64; exec(base64.b64decode('{code_b64}').decode())",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=SANDBOX_TIMEOUT,
                )
            except asyncio.TimeoutError:
                proc.kill()
                # 清理容器
                await asyncio.create_subprocess_exec("docker", "rm", "-f", container_name)
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

    async def health(self) -> dict:
        docker_ok = await self._check_docker()
        return {
            "status": "ok" if docker_ok else "degraded",
            "executor": self.name,
            "docker_available": docker_ok,
            "image": DOCKER_IMAGE,
            "memory_limit": DOCKER_MEM_LIMIT,
            "cpu_limit": DOCKER_CPU_LIMIT,
        }
