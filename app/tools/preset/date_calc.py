"""Global preset tool: date & time calculation."""
from __future__ import annotations
from datetime import datetime, timedelta

META = {
    "description": "日期时间计算工具：获取当前时间、计算日期差、推算日期。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["now", "date_diff", "date_add", "weekday"],
                "description": "操作类型"
            },
            "date1": {
                "type": "string",
                "description": "日期1，格式 YYYY-MM-DD（date_diff/weekday 需要）"
            },
            "date2": {
                "type": "string",
                "description": "日期2，格式 YYYY-MM-DD（date_diff 需要）"
            },
            "days": {
                "type": "integer",
                "description": "天数（date_add 需要）"
            }
        },
        "required": ["action"]
    }
}


async def execute(action: str, date1: str = None, date2: str = None, days: int = None) -> str:
    now = datetime.now()
    if action == "now":
        return f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n星期{['一','二','三','四','五','六','日'][now.weekday()]}"
    elif action == "date_diff":
        d1 = datetime.strptime(date1, "%Y-%m-%d") if date1 else now
        d2 = datetime.strptime(date2, "%Y-%m-%d") if date2 else now
        diff = abs((d2 - d1).days)
        return f"{d1.date()} 到 {d2.date()} 相差 {diff} 天"
    elif action == "date_add":
        base = datetime.strptime(date1, "%Y-%m-%d") if date1 else now
        result = base + timedelta(days=days or 0)
        return f"{base.date()} 加上 {days} 天后是 {result.date()}"
    elif action == "weekday":
        d = datetime.strptime(date1, "%Y-%m-%d") if date1 else now
        return f"{d.date()} 是星期{['一','二','三','四','五','六','日'][d.weekday()]}"
    else:
        raise ValueError(f"Unknown date action: {action}")
