"""Global preset tool: text processing utilities."""
from __future__ import annotations

META = {
    "description": "文本处理工具：统计字数、提取关键词、分词统计。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["count_chars", "count_words", "reverse", "uppercase", "lowercase"],
                "description": "要执行的操作"
            },
            "text": {
                "type": "string",
                "description": "待处理的文本"
            }
        },
        "required": ["action", "text"]
    }
}


async def execute(action: str, text: str) -> str:
    if action == "count_chars":
        return f"字符数（含空格）：{len(text)}\n字符数（不含空格）：{len(text.replace(' ', ''))}"
    elif action == "count_words":
        words = text.split()
        return f"单词/词数：{len(words)}"
    elif action == "reverse":
        return text[::-1]
    elif action == "uppercase":
        return text.upper()
    elif action == "lowercase":
        return text.lower()
    else:
        raise ValueError(f"Unknown text action: {action}")
