"""
Debug 测试：瑞幸咖啡下单全流程
============================
测试"在广州市黄埔区的南电卓越大厦店下单一杯生椰拿铁"
显示每次迭代的工具调用和结果
"""
import os, sys, json, time, urllib.request

BASE = "http://127.0.0.1:8100"


def log(msg: str, color: str = ""):
    """带颜色的终端输出"""
    colors = {"green": "\033[92m", "yellow": "\033[93m", "red": "\033[91m",
              "blue": "\033[94m", "cyan": "\033[96m", "bold": "\033[1m", "end": "\033[0m"}
    c = colors.get(color, "")
    e = colors["end"]
    print(f"{c}{msg}{e}")


def print_sep(char: str = "=", n: int = 60):
    print(char * n)


async def main():
    # ── 注册/登录 ──
    log("🔐 [1] 用户注册", "bold")
    username = f"debug_{int(time.time())}"
    req = urllib.request.Request(
        f"{BASE}/api/v1/auth/register",
        data=json.dumps({"username": username, "password": "123456", "role": "advanced"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    UID = resp["user_id"]
    log(f"  用户: {username} ({resp['role']})", "green")

    log(f"\n🔐 [2] 登录", "bold")
    req2 = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=json.dumps({"username": username, "password": "123456"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp2 = json.loads(urllib.request.urlopen(req2).read())
    log(f"  token: {resp2['user_id'][:12]}...", "green")

    # ── 发送订单请求 ──
    MESSAGE = "帮我在广州市黄埔区的南电卓越大厦店下单一杯生椰拿铁"
    print_sep()
    log(f"☕ [3] 发送订单请求", "bold")
    log(f"  消息: {MESSAGE}", "yellow")
    print_sep()

    start_time = time.time()
    req3 = urllib.request.Request(
        f"{BASE}/api/v1/chat/send",
        data=json.dumps({"message": MESSAGE}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {UID}"},
    )
    resp = json.loads(urllib.request.urlopen(req3).read())
    elapsed = time.time() - start_time

    tool_calls = resp.get("tool_calls", [])

    # ── 打印 Debug 流程 ──
    log(f"\n📊 [4] Debug 流程 ({len(tool_calls)} 次工具调用, {elapsed:.1f}s)", "bold")
    print_sep("-")

    for i, tc in enumerate(tool_calls, 1):
        name = tc.get("tool_name", "?")
        success = tc.get("success", False)
        ms = tc.get("execution_time_ms", 0)
        
        # 工具名美化
        display_name = name.split("__")[-1] if "__" in name else name
        status = "✅" if success else "❌"
        color = "green" if success else "red"
        
        log(f"\n  {'─' * 40}", "cyan")
        log(f"  第{i}步: {status} {display_name} ({ms}ms)", color)
        log(f"  工具: {name}", "cyan")
        
        # 显示输出摘要（截断长内容）
        output = tc.get("output", "") or tc.get("error", "")
        if output:
            snippet = output[:300].replace("\\n", "\n      ")
            if len(output) > 300:
                snippet += "..."
            log(f"  结果: {snippet}", "yellow")

    # ── 最终回复 ──
    print_sep()
    log(f"\n💬 [5] 最终回复", "bold")
    reply = resp.get("reply", "")
    log(f"  {reply[:600]}", "green")
    if len(reply) > 600:
        log(f"  ...（共 {len(reply)} 字）")

    # ── Token 统计 ──
    print_sep()
    log(f"\n📈 [6] Token 统计", "bold")
    usage = resp.get("token_usage", {})
    log(f"  prompt:     {usage.get('prompt_tokens', 0):>6}", "cyan")
    log(f"  completion: {usage.get('completion_tokens', 0):>6}", "cyan")
    log(f"  总耗时:     {elapsed:.1f}s", "cyan")

    print_sep()
    log(f"\n🎉 测试完成!\n", "bold")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
