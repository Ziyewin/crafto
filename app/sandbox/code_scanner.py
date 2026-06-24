"""Dangerous code scanner — static analysis before sandbox execution."""
from __future__ import annotations
import re
import logging

logger = logging.getLogger("sandbox.scanner")

# ── Dangerous patterns — matched against AST/raw code ──

DANGEROUS_PATTERNS = [
    # File system abuse
    (r"os\.remove\s*\(", "File deletion (os.remove)"),
    (r"os\.rmdir\s*\(", "Directory removal (os.rmdir)"),
    (r"shutil\.rmtree\s*\(", "Recursive delete (shutil.rmtree)"),
    (r"__import__\s*\(\s*['\"]os['\"]\s*\)", "Dynamic os import"),
    (r"eval\s*\(", "Arbitrary eval"),
    (r"exec\s*\(", "Arbitrary exec"),
    (r"compile\s*\(", "Dynamic compile"),

    # Network / privilege escalation
    (r"socket\.", "Socket access"),
    (r"subprocess\.", "Subprocess execution"),
    (r"os\.system\s*\(", "OS system call"),
    (r"os\.popen\s*\(", "OS popen"),
    (r"ctypes\.", "C types (memory access)"),
    (r"pty\.", "Pseudo-terminal access"),

    # Cryptomining / resource abuse
    (r"(?:stratum|minerd|xmrig|cryptonight)", "Crypto mining pattern"),
    (r"while\s+True\s*:\s*pass", "Infinite loop (potential DoS)"),

    # Environment / secrets
    (r"os\.environ", "Environment variable access"),
    (r"open\s*\(\s*['\"](?:/etc|/var|~/?\.)", "Sensitive file access"),

    # Network scanning
    (r"(?:nmap|masscan|zmap|scan\s*port)", "Port scanning"),
    (r"requests?\.(?:get|post)\s*\(\s*['\"]https?://(?:10\.|172\.|192\.168\.|127\.)", "Internal network access"),
]


async def scan_code(code: str) -> list[dict]:
    """Scan code for dangerous patterns. Returns list of violations."""
    violations = []

    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            violations.append({
                "pattern": pattern,
                "description": description,
            })

    if violations:
        logger.warning("Code scanning found %d violations: %s", len(violations), violations)

    return violations


def is_code_safe(code: str) -> bool:
    """Quick check — returns True if no dangerous patterns found."""
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False
    return True


def sanitize_code(code: str) -> str:
    """Attempt to sanitize dangerous code by commenting out violations.
    Falls back to blocking if too severe."""
    lines = code.split("\n")
    sanitized = []
    blocked = False

    for line in lines:
        is_dangerous = False
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                is_dangerous = True
                if any(term in description for term in ["删除", "remove", "rmdir", "rmtree", "system", "popen", "subprocess"]):
                    blocked = True
                break

        if is_dangerous:
            sanitized.append(f"# [BLOCKED] {line.strip()}")
        else:
            sanitized.append(line)

    if blocked:
        raise ValueError("Code contains severe dangerous operations and has been blocked")

    return "\n".join(sanitized)
