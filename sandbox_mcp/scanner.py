"""
危险代码扫描器
独立模块，从 app/sandbox/code_scanner.py 移植，无 app 依赖
"""
from __future__ import annotations
import re
import logging

logger = logging.getLogger("sandbox-mcp.scanner")

# ── 18 条危险模式规则 ──
DANGEROUS_PATTERNS: list[tuple[str, str, int]] = [
    # (正则, 描述, 严重级别 1-3)
    # ── 文件系统滥用 ──
    (r"os\.remove\s*\(",        "删除文件", 3),
    (r"os\.rmdir\s*\(",        "删除目录", 3),
    (r"shutil\.rmtree\s*\(",   "递归删除", 3),
    (r"__import__\s*\(\s*['\"]os['\"]\s*\)", "动态导入 os", 2),
    (r"eval\s*\(",             "eval 执行", 3),
    (r"exec\s*\(",             "exec 执行", 3),
    (r"compile\s*\(",          "动态编译", 2),

    # ── 网络 / 提权 ──
    (r"socket\.",              "Socket 访问", 3),
    (r"subprocess\.",          "子进程执行", 3),
    (r"os\.system\s*\(",       "系统调用", 3),
    (r"os\.popen\s*\(",        "OS popen", 3),
    (r"ctypes\.",              "C 内存访问", 3),
    (r"pty\.",                 "伪终端", 3),

    # ── 挖矿 / 资源滥用 ──
    (r"(?:stratum|minerd|xmrig|cryptonight)", "挖矿", 3),
    (r"while\s+True\s*:\s*pass", "死循环", 2),

    # ── 密钥 / 隐私 ──
    (r"os\.environ",           "环境变量读取", 2),
    (r"open\s*\(\s*['\"](?:/etc|/var|~/?\.)", "敏感文件", 3),

    # ── 内网扫描 ──
    (r"(?:nmap|masscan|zmap|scan\s*port)", "端口扫描", 3),
    (r"requests?\.(?:get|post)\s*\(\s*['\"]https?://(?:10\.|172\.|192\.168\.|127\.)", "内网请求", 2),
]


async def scan_code(code: str) -> list[dict]:
    """
    扫描代码中的危险模式
    返回: [{"pattern": ..., "description": ..., "severity": ..., "line": ...}, ...]
    """
    violations: list[dict] = []
    for pattern, description, severity in DANGEROUS_PATTERNS:
        for m in re.finditer(pattern, code, re.IGNORECASE):
            line_num = code[:m.start()].count("\n") + 1
            violations.append({
                "pattern": pattern,
                "description": description,
                "severity": severity,
                "line": line_num,
            })

    if violations:
        logger.warning("发现 %d 个危险模式", len(violations))

    return violations


def is_code_safe(code: str) -> bool:
    """快速检查代码是否安全"""
    for pattern, _, _ in DANGEROUS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False
    return True
