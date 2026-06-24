"""
MCP 全流程测试脚本
测试：服务连接 → 工具调用 → Agent ReAct 循环
"""
import os, sys, json, asyncio, time, urllib.request

BASE = "http://127.0.0.1:8100"
PASS = 0
FAIL = 0


def log(msg: str, ok: bool = True):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL += 1
        print(f"  ❌ {msg}")


async def test_mcp_flow():
    global PASS, FAIL
    print("=" * 60)
    print("MCP 全流程测试")
    print("=" * 60)

    # ── 1. 健康检查 ──
    print("\n📡 [1] 服务健康检查")
    try:
        r = urllib.request.urlopen(f"{BASE}/health")
        d = json.loads(r.read())
        log(f"服务状态: {d.get('status')}", d.get('status') == 'ok')
    except Exception as e:
        log(f"健康检查失败: {e}", False)

    # ── 2. 注册/登录 ──
    print("\n👤 [2] 用户注册与登录")
    username = f"tester_{int(time.time())}"
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/auth/register",
            data=json.dumps({"username": username, "password": "123456", "role": "advanced"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        UID = resp["user_id"]
        log(f"注册成功: {username}")

        # 登录
        req2 = urllib.request.Request(
            f"{BASE}/api/v1/auth/login",
            data=json.dumps({"username": username, "password": "123456"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp2 = json.loads(urllib.request.urlopen(req2).read())
        log(f"登录成功: {resp2.get('role')}")
    except Exception as e:
        log(f"认证失败: {e}", False)
        return

    # ── 3. MCP 工具直接调用 ──
    print("\n🛠 [3] MCP 工具直接调用（绕过 Agent）")

    # 3a. weather__get_current_weather
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chat/send",
            data=json.dumps({"message": "请用 weather__get_current_weather 工具查广州天气"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {UID}"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        has_tool = bool(resp.get("tool_calls"))
        log(f"weather 工具调用: {'有' if has_tool else '无'}工具调用", has_tool)
        if resp.get("tool_calls"):
            for tc in resp["tool_calls"]:
                sn = tc.get("tool_name", "?")
                log(f"  → 调用: {sn}", True)
    except Exception as e:
        log(f"weather 测试失败: {e}", False)

    # 3b. geo__get_city_location
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chat/send",
            data=json.dumps({"message": "请用 geo__get_city_location 查南昌的位置"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {UID}"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        has_tool = bool(resp.get("tool_calls"))
        log(f"geo 工具调用: {'有' if has_tool else '无'}工具调用", has_tool)
    except Exception as e:
        log(f"geo 测试失败: {e}", False)

    # 3c. luckin 门店查询
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chat/send",
            data=json.dumps({"message": "请用 luckin__queryShopList 查一下瑞幸咖啡门店"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {UID}"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        has_tool = bool(resp.get("tool_calls"))
        log(f"luckin 工具调用: {'有' if has_tool else '无'}工具调用", has_tool)
        if resp.get("tool_calls"):
            for tc in resp["tool_calls"]:
                sn = tc.get("tool_name", "?")
                log(f"  → 调用: {sn}", True)
    except Exception as e:
        log(f"luckin 测试失败: {e}", False)

    # ── 4. ReAct 循环测试（自主选择工具） ──
    print("\n🤖 [4] Agent ReAct 循环（自主选择工具）")

    # 4a. 天气查询（应选 weather__* 而不是 search）
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chat/send",
            data=json.dumps({"message": "北京今天天气怎么样？"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {UID}"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        tool_names = [t.get("tool_name", "") for t in resp.get("tool_calls", [])]
        is_weather = any("weather" in t for t in tool_names)
        is_search = any("search" in t for t in tool_names)
        log(f"天气查询: weather={'是' if is_weather else '否'} search={'是' if is_search else '否'}", is_weather and not is_search)
    except Exception as e:
        log(f"天气查询失败: {e}", False)

    # 4b. 地理查询（应选 geo__* 而不是 search）
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chat/send",
            data=json.dumps({"message": "南昌的地理位置信息"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {UID}"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        tool_names = [t.get("tool_name", "") for t in resp.get("tool_calls", [])]
        is_geo = any("geo" in t for t in tool_names)
        is_search = any("search" in t for t in tool_names)
        log(f"地理查询: geo={'是' if is_geo else '否'} search={'是' if is_search else '否'}", is_geo and not is_search)
    except Exception as e:
        log(f"地理查询失败: {e}", False)

    # ── 5. 会话历史 ──
    print("\n💬 [5] 会话管理")
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {UID}"},
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        sessions = resp.get("sessions", [])
        log(f"会话列表: {len(sessions)} 个会话")
    except Exception as e:
        log(f"会话列表失败: {e}", False)

    # ── 结果 ──
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"📊 测试结果: {PASS}/{total} 通过, {FAIL}/{total} 失败")
    if FAIL == 0:
        print("🎉 全部通过!")
    else:
        print(f"⚠️  有 {FAIL} 个测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_mcp_flow())
