"""
Weather MCP Server — 真实天气数据
使用 wttr.in 免费 API（无需 API Key）
"""
import os, sys
_p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _p not in sys.path: sys.path.insert(0, _p)

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="weather-mcp", instructions="实时天气查询服务（基于 wttr.in）")

WTTR_BASE = "https://wttr.in"


@mcp.tool()
async def get_current_weather(city: str) -> str:
    """获取指定城市的当前天气实况"""
    url = f"{WTTR_BASE}/{city}?format=%l:+%t,+%C,+%h+湿度,+%w+风速,+%p+降水"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text.strip()


@mcp.tool()
async def get_weather_json(city: str) -> dict:
    """获取指定城市的完整天气 JSON 数据（含当前+未来3天预报）"""
    url = f"{WTTR_BASE}/{city}?format=j1"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        cc = data.get("current_condition", [{}])[0]
        forecasts = data.get("weather", [])[:3]
        return {
            "city": data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", city),
            "country": data.get("nearest_area", [{}])[0].get("country", [{}])[0].get("value", ""),
            "current": {
                "temp": cc.get("temp_C", "?"),
                "feels_like": cc.get("FeelsLikeC", "?"),
                "condition": cc.get("weatherDesc", [{}])[0].get("value", "?"),
                "humidity": f"{cc.get('humidity', '?')}%",
                "wind_speed": f"{cc.get('windspeedKmph', '?')} km/h",
                "uv_index": cc.get("uvIndex", "?"),
                "visibility": f"{cc.get('visibility', '?')} km",
            },
            "forecast": [
                {
                    "date": f.get("date", "?"),
                    "max_temp": f.get("maxtempC", "?"),
                    "min_temp": f.get("mintempC", "?"),
                    "condition": f.get("hourly", [{}])[0].get("weatherDesc", [{}])[0].get("value", "?"),
                    "sunrise": f.get("astronomy", [{}])[0].get("sunrise", "?"),
                    "sunset": f.get("astronomy", [{}])[0].get("sunset", "?"),
                }
                for f in forecasts
            ],
        }


@mcp.tool()
async def get_forecast(city: str, days: int = 3) -> str:
    """获取指定城市的天气预报（1-3天）"""
    url = f"{WTTR_BASE}/{city}?format=%l|%t|%C|%h&lang=zh"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text.strip()


@mcp.tool()
async def get_moon_phase(city: str) -> dict:
    """获取指定城市的月相信息"""
    url = f"{WTTR_BASE}/{city}?format=j1"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        cc = data.get("current_condition", [{}])[0]
        return {
            "moon_phase": cc.get("moon_phase", "?"),
            "moon_illumination": f"{cc.get('moon_illumination', '?')}%",
            "current_temp": f"{cc.get('temp_C', '?')}°C",
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8102)
    args = parser.parse_args()
    # 设置 FastMCP 运行参数
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)
