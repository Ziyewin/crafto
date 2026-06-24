"""Global preset tool: weather query (mock)."""
from __future__ import annotations
import random

META = {
    "description": "查询指定城市的天气信息。支持中国主要城市。",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 北京、上海、深圳"
            }
        },
        "required": ["city"]
    }
}


async def execute(city: str) -> str:
    conditions = ["晴朗", "多云", "小雨", "阴天", "微风"]
    temp = random.randint(10, 35)
    condition = random.choice(conditions)
    humidity = random.randint(40, 90)
    return (
        f"📍 {city} 天气预报\n"
        f"🌡 温度：{temp}°C\n"
        f"🌤 天气：{condition}\n"
        f"💧 湿度：{humidity}%\n"
        f"📅 更新时间：当前\n"
        f"（此为模拟数据，实际应用需接入真实天气API）"
    )
