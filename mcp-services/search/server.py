"""
Search MCP Server — 网页搜索
使用 DuckDuckGo 搜索引擎（无需 API Key）
"""
import os, sys
_p = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _p not in sys.path: sys.path.insert(0, _p)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="search-mcp", instructions="网页搜索引擎（基于 DuckDuckGo）")


@mcp.tool()
async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """[只读] 仅搜索公开网页信息，不能下单/查天气/执行操作"""
    from duckduckgo_search import DDGS
    results = []
    try:
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                results.append({
                    "index": i + 1,
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as e:
        return [{"error": str(e)}]
    return results


@mcp.tool()
async def search_news(query: str, max_results: int = 5) -> list[dict]:
    """[只读] 仅搜索新闻信息，不能执行操作"""
    from duckduckgo_search import DDGS
    results = []
    try:
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.news(query, max_results=max_results)):
                results.append({
                    "index": i + 1,
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", ""),
                    "date": r.get("date", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as e:
        return [{"error": str(e)}]
    return results


@mcp.tool()
async def search_images(query: str, max_results: int = 3) -> list[dict]:
    """搜索图片，返回图片标题、链接和缩略图"""
    from duckduckgo_search import DDGS
    results = []
    try:
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.images(query, max_results=max_results)):
                results.append({
                    "index": i + 1,
                    "title": r.get("title", ""),
                    "image_url": r.get("image", ""),
                    "thumbnail_url": r.get("thumbnail", ""),
                    "source_url": r.get("url", ""),
                })
    except Exception as e:
        return [{"error": str(e)}]
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    # 设置 FastMCP 运行参数
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)
