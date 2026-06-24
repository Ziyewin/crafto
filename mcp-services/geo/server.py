"""
Geo MCP Server — IP 地理信息查询
使用 ip-api.com 免费 API（无需 API Key）
"""
import os, sys
_p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _p not in sys.path: sys.path.insert(0, _p)
import httpx
from mcp.server.fastmcp import FastMCP
mcp = FastMCP(name="geo-mcp", instructions="地理信息服务：IP 位置查询 + 城市经纬度查询（ip-api.com + OpenStreetMap）")
GEO_API = "http://ip-api.com/json"
@mcp.tool()
async def get_ip_info(ip: str = "") -> dict:
    """查询指定 IP 地址的地理位置（留空查当前 IP）。参数 ip 是 IP 地址，不是城市名！"""
    url = f"{GEO_API}/{ip}" if ip else f"{GEO_API}?fields=66846719"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "fail":
            return {"error": data.get("message", "查询失败")}
        return {
            "ip": data.get("query", ip or "current"),
            "country": data.get("country", ""),
            "country_code": data.get("countryCode", ""),
            "region": data.get("regionName", ""),
            "city": data.get("city", ""),
            "zip": data.get("zip", ""),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "timezone": data.get("timezone", ""),
            "isp": data.get("isp", ""),
            "org": data.get("org", ""),
            "as": data.get("as", ""),
        }
@mcp.tool()
async def batch_ip_info(ips: list[str]) -> list[dict]:
    """批量查询多个 IP 地址的地理位置"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(GEO_API, json=ips)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data if isinstance(data, list) else [data]:
            if item.get("status") == "fail":
                results.append({"ip": item.get("query", ""), "error": item.get("message", "")})
            else:
                results.append({
                    "ip": item.get("query", ""),
                    "country": item.get("country", ""),
                    "city": item.get("city", ""),
                    "region": item.get("regionName", ""),
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    "timezone": item.get("timezone", ""),
                    "isp": item.get("isp", ""),
                })
        return results
@mcp.tool()
async def get_city_location(city: str, country: str = "") -> dict:
    """查询城市的地理位置信息，返回经纬度、国家、时区等。参数 city 为城市名（支持中英文）"""
    query = f"{city}, {country}" if country else city
    headers = {
        "User-Agent": "AgentPlatform/1.0 (educational project)",
        "Accept-Language": "zh-CN,en;q=0.9",
    }
    params = {"q": query, "format": "json", "limit": 1, "addressdetails": 1}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params=params, headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {"error": f"未找到城市: {query}"}
        item = data[0]
        addr = item.get("address", {})
        return {
            "city": addr.get("city", addr.get("town", addr.get("village", item.get("display_name", city)))),
            "country": addr.get("country", ""),
            "country_code": addr.get("country_code", "").upper(),
            "state": addr.get("state", addr.get("region", "")),
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "display_name": item.get("display_name", ""),
            "boundingbox": item.get("boundingbox", []),
            "osm_type": item.get("osm_type", ""),
        }
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8104)
    args = parser.parse_args()
    # 设置 FastMCP 运行参数
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)