"""
MCP 服务集群启动器
==================
将 MCP 服务作为独立 HTTP 服务启动，支持所有项目连接。

使用方式:
    python mcp-servers/launcher.py start       # 启动所有服务
    python mcp-servers/launcher.py stop        # 停止所有服务
    python mcp-servers/launcher.py status      # 查看状态
"""
import os, sys, signal, time, json, subprocess

# ── 服务配置 ──
SERVERS = [
    {"name": "sandbox", "port": 8101, "path": "sandbox_mcp/server.py",
     "desc": "代码沙箱执行"},
    {"name": "weather", "port": 8102, "path": "mcp-services/weather/server.py",
     "desc": "实时天气数据"},
    {"name": "search",  "port": 8103, "path": "mcp-services/search/server.py",
     "desc": "网页搜索"},
    {"name": "geo",     "port": 8104, "path": "mcp-services/geo/server.py",
     "desc": "IP/城市地理信息"},
]

PID_FILE = os.path.join(os.path.dirname(__file__), ".mcp_pids.json")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_python():
    return sys.executable


def start():
    pids = {}
    for svc in SERVERS:
        path = os.path.join(BASE_DIR, svc["path"])
        if not os.path.isfile(path):
            print(f"  ⚠️  {svc['name']}: 文件不存在 {path}")
            continue
        proc = subprocess.Popen(
            [get_python(), path, "--transport", "sse", "--port", str(svc["port"])],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pids[svc["name"]] = proc.pid
        print(f"  ✅ {svc['name']:8s} → http://127.0.0.1:{svc['port']}/sse  (PID {proc.pid})")
        time.sleep(0.3)

    with open(PID_FILE, "w") as f:
        json.dump(pids, f)
    print(f"\n  📌 共 {len(pids)} 个服务已启动")
    print(f"  📌 主应用连接方式：修改 MCP_SERVICE_DEFS 中对应的 type 为 sse, url 为 http://.../sse")


def stop():
    if not os.path.isfile(PID_FILE):
        print("  ⚠️  没有运行中的服务")
        return
    with open(PID_FILE) as f:
        pids = json.load(f)
    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  ✅ {name:8s} (PID {pid}) 已停止")
        except ProcessLookupError:
            print(f"  ⚠️  {name:8s} (PID {pid}) 已不存在")
    os.remove(PID_FILE)


def status():
    if not os.path.isfile(PID_FILE):
        print("  📌 没有运行中的服务")
        return
    with open(PID_FILE) as f:
        pids = json.load(f)
    for name, pid in pids.items():
        try:
            os.kill(pid, 0)
            svc = next(s for s in SERVERS if s["name"] == name)
            print(f"  ✅ {name:8s} http://127.0.0.1:{svc['port']}/sse  (PID {pid})")
        except (ProcessLookupError, OSError):
            print(f"  ❌ {name:8s} (PID {pid}) 已停止")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    os.chdir(BASE_DIR)
    print(f"📦 MCP 服务集群 — {cmd}")
    print("=" * 50)
    {"start": start, "stop": stop, "status": status}.get(cmd, lambda: print(f"未知命令: {cmd}"))()
    print("=" * 50)
