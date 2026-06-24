"""Remote sandbox client — executes code in isolated environment.
Currently supports mock mode (local subprocess) and can be extended to Docker/E2B."""
from __future__ import annotations
from app.sandbox.code_scanner import scan_code
from app.config import settings
import asyncio
import logging
import uuid
import json
from datetime import datetime, timezone

logger = logging.getLogger("sandbox.client")


async def execute_in_sandbox(code: str, user_id: str) -> dict:
    """Execute code in isolated sandbox. Returns execution result."""
    execution_id = str(uuid.uuid4())
    logger.info("Sandbox execution %s for user %s", execution_id, user_id)

    # Step 1: Code scanning
    violations = await scan_code(code)
    if violations:
        logger.warning("Code blocked for user %s: %s", user_id, violations)
        return {
            "success": False,
            "output": "",
            "error": f"代码安全检查未通过：发现 {len(violations)} 个危险模式\n" + "\n".join(
                f"- {v['description']}" for v in violations
            ),
            "execution_id": execution_id,
        }

    # Step 2: Execute in appropriate sandbox
    mode = settings.sandbox_mode

    if mode == "mock":
        result = await _mock_execute(code, execution_id)
    elif mode == "docker":
        result = await _docker_execute(code, execution_id)
    elif mode == "e2b":
        result = await _e2b_execute(code, execution_id)
    else:
        result = await _mock_execute(code, execution_id)

    logger.info("Sandbox %s completed: success=%s", execution_id, result.get("success"))
    return result


async def _mock_execute(code: str, execution_id: str) -> dict:
    """Mock sandbox — runs code in a subprocess with timeout."""
    import subprocess
    import sys
    import tempfile
    import os

    # Write code to temp file
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp")
    try:
        tmp.write(code)
        tmp.close()

        # Execute with timeout
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            tmp.name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/tmp",
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=settings.sandbox_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "output": "",
                "error": f"执行超时（限制 {settings.sandbox_timeout} 秒）",
                "execution_id": execution_id,
            }

        if proc.returncode != 0:
            return {
                "success": False,
                "output": stdout.decode("utf-8", errors="replace"),
                "error": stderr.decode("utf-8", errors="replace"),
                "execution_id": execution_id,
            }

        return {
            "success": True,
            "output": stdout.decode("utf-8", errors="replace"),
            "error": "",
            "execution_id": execution_id,
        }

    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
            "execution_id": execution_id,
        }
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


async def _docker_execute(code: str, execution_id: str) -> dict:
    """Docker-based sandbox execution. Requires Docker installed."""
    return {
        "success": False,
        "output": "",
        "error": "Docker sandbox mode not yet configured. Set SANDBOX_MODE=mock for development.",
        "execution_id": execution_id,
    }


async def _e2b_execute(code: str, execution_id: str) -> dict:
    """E2B (cloud sandbox) execution."""
    return {
        "success": False,
        "output": "",
        "error": "E2B sandbox mode not yet configured. Set SANDBOX_MODE=mock for development.",
        "execution_id": execution_id,
    }
