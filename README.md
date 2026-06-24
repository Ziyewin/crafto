# 工业级智能 Agent 平台

多租户工业级智能 Agent 平台，融合**传统工具调用**与 **LLM 动态自研技能**机制。
内置完整的多轮对话、分层记忆、用户画像、动态 Skill 生成、安全沙箱执行、全链路日志监控能力。

---

## 一、系统架构 

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端交互层                                │
│           index.html · style.css · app.js                       │
│   对话界面 · 流式展示 · 工具执行可视化 · 管理后台                │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼───────────────────────────────────────┐
│                        API 网关层                                │
│    CORS → TraceIDMiddleware → AuthMiddleware                     │
│    认证鉴权 · TraceID 生成 · 限流 · 路由分发                     │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                     Agent 核心调度层                              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Agent.process_message(message)                         │    │
│  │  │                                                      │    │
│  │  ├─ MemoryOrchestrator (三级记忆)                       │    │
│  │  │   ├─ ShortTermMemory  (Redis / 内存降级)            │    │
│  │  │   ├─ SummaryMemory     (SQLite)                     │    │
│  │  │   └─ LongTermMemory    (Qdrant / 内存向量降级)       │    │
│  │  │                                                      │    │
│  │  ├─ ToolRegistry (三工具体系)                           │    │
│  │  │   ├─ MCP 服务工具 (自动发现, service__)              │    │
│  │  │   ├─ 用户私有 Skill (DB持久, 一次性执行)                   │    │
│  │  │   └─ execute_python_code → MCP 沙箱                  │    │
│  │  │                                                      │    │
│  │  └─ ReAct 循环 (最多5轮)                                │    │
│  │      思考 → 工具/代码执行 → 结果观察 → 迭代            │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                      能力支撑层                                  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  MCP Manager（统一管理器，自动连接所有服务）               │    │
│  │                                                          │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────┐       │    │
│  │  │ sandbox  │ │ weather  │ │ search │ │  geo   │       │    │
│  │  │ 代码沙箱  │ │ 实时天气  │ │ 网页搜索│ │IP地理  │       │    │
│  │  │ 3 个工具  │ │ 4 个工具  │ │ 3个工具 │ │3个工具 │       │    │
│  │  └────┬─────┘ └────┬─────┘ └────┬───┘ └────┬───┘       │    │
│  │       │            │            │           │             │    │
│  │  ┌────▼────────────▼────────────▼───────────▼───┐        │    │
│  │  │       MCP 服务集群（2 种运行模式）              │        │    │
│  │  │  ① 集成模式：子进程（默认）                    │        │    │
│  │  │  ② 独立模式：HTTP 服务（所有项目可用）          │        │    │
│  │  └───────────────────────────────────────────────┘        │    │
│  │                                                          │    │
│  │  所有工具自动注册为 service__tool_name 前缀格式            │    │
│  │  应用启动时自动连接，无需手动操作                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  模型调用 · 向量检索 · 日志采集 · 异常追踪               │    │
│  │  DeepSeek API · Qdrant · 结构化 JSON 日志 · TraceID     │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                      数据存储层                                  │
│  SQLite/PostgreSQL · Redis · Qdrant · 内存降级                   │
│  用户 · 会话 · 消息 · 技能 · 日志 · 异常 · 预置工具             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、核心业务流程

### 2.1 用户发送消息 → 得到回复

```
用户输入 → Enter
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│ 前端 app.js                                                      │
│ sendMessage()                                                    │
│  ├─ addMessage('user', text)             显示用户气泡            │
│  ├─ fetch('POST /api/v1/chat/send')      调用后端 API            │
│  │   └─ headers: getAuthHeaders()        从 localStorage 读认证  │
│  └─ 添加 AI 占位气泡（"思考中..."动画）                          │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP POST
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/api/middleware/auth.py                                       │
│ AuthMiddleware.dispatch()                                        │
│  ├─ 检查路由是否公开（/api/v1/auth/login 跳过）                  │
│  ├─ 尝试 _resolve_api_key()  ← 优先 X-API-Key                    │
│  ├─ 失败 → 尝试 _resolve_token()  ← Bearer Token fallback        │
│  └─ 通过 → 注入 request.state.user_id + user_role                │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/api/routes/chat.py                                           │
│ send_message(req, request)                                       │
│  ├─ SessionManager(user_id).create_session()  如无会话则创建      │
│  └─ Agent(user_id, session_id, user_role)                        │
│       └─ agent.process_message(text)                             │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/core/agent.py                                                │
│ Agent.process_message(text)                                      │
│                                                                   │
│ ① MemoryOrchestrator.initialize()        加载摘要/长期记忆       │
│ ② MemoryOrchestrator.add_user_message()  存短时记忆 + DB         │
│ ③ SessionManager.save_message("user")    INSERT INTO messages    │
│ ④ result = await self._react_loop()      核心 ReAct 循环         │
│ ⑤ MemoryOrchestrator.add_assistant_msg() 存回复到短时记忆        │
│ ⑥ SessionManager.save_message("assistant")                      │
│ ⑦ MemoryOrchestrator.summarize_if_needed() 自动摘要              │
│ ⑧ LongTermMemory.extract_and_store()     提取关键信息到向量库    │
│ ⑨ return { session_id, reply, tool_calls, token_usage }         │
└──────────────────────────┬───────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ Agent._react_loop() (最多 5 轮)                                   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 第 1 轮: 思考                                             │    │
│  │  ├─ build_context() → [system + short_term messages]     │    │
│  │  ├─ get_available_tools() → MCP + 预设 + Skill + code_gen    │    │
│  │  └─ DeepSeekClient.chat(messages, tools)                 │    │
│  │     └─ POST api.deepseek.com → finish_reason?            │    │
│  │                                                          │    │
│  │ 如果 finish_reason == "tool_calls":                      │    │
│  │  ├─ add_assistant_message(..., tool_calls)  存一次       │    │
│  │  └─ 遍历执行每个工具:                                    │    │
│  │     ├─ query_weather     → weather.py (预设)             │    │
│  │     ├─ execute_python_code → sandbox_mcp (MCP 客户端)    │    │
│  │     │   sandbox_client.execute_code(code, user_id)       │    │
│  │     │   ├─ MCP 连接可用 → sandbox_mcp/server.py         │    │
│  │     │   │   ├─ scanner.scan_code()   安全检查            │    │
│  │     │   │   ├─ MockExecutor.execute()  子进程执行        │    │
│  │     │   │   └─ 返回 { success, output, error }          │    │
│  │     │   └─ MCP 不可用 → 降级本地直接执行                 │    │
│  │     ├─ 用户私有 Skill → SkillManager.execute_skill()    │    │
│  │     └─ add_tool_message(result) + save_message()        │    │
│  │                                                          │    │
│  │ 如果 finish_reason == "stop":                            │    │
│  │  └─ return content   ← 最终回复                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│ 第 2..N 轮: 工具结果回传 → LLM 再推理...                          │
│ 最多 5 轮后返回超时提示                                           │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 注册 / 登录流程

```
用户填写表单 → 点击"注册"或"登录"
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│ app.js                                                           │
│ handleLogin() / handleRegister()                                 │
│  └─ API.post('/api/v1/auth/login', { username, password })       │
│      └─ fetch + getAuthHeaders()                                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │ POST
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ AuthMiddleware → 路由公开 → 跳过                                 │
│ app/api/routes/user.py                                           │
│  login() / register()                                            │
│  └─ 验证 → 写入 DB → 返回 { user_id, username, role, api_key } │
└──────────────────────────┬───────────────────────────────────────┘
                           │ 200 JSON
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ app.js                                                           │
│  store.userId = res.user_id    → localStorage                   │
│  showApp() → enableChatInput() → loadSessions()                 │
│  用户看到主界面，输入框可用 ↓                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、MCP 服务集群

MCP 服务支持**两种运行模式**，可随时切换：

### 3.1 集成模式（默认）

MCP 服务作为主应用的子进程运行，由 **MCP Manager** (`app/sandbox/mcp_manager.py`) 自动管理：

- 应用启动时**自动连接**所有配置的 MCP 服务，无需手动操作
- 自动调用 `list_tools()` 发现每个服务的工具列表
- 工具以 `service__tool_name` 前缀注册到 Agent，避免命名冲突
- 连接失败时自动跳过，不影响其他服务

### 3.2 独立服务集群模式

MCP 服务作为独立 HTTP 服务运行，**任何 MCP 客户端**（不限本项目）都可连接使用。

```bash
# 启动所有服务
python mcp-servers/launcher.py start

# 查看状态
python mcp-servers/launcher.py status

# 停止所有服务
python mcp-servers/launcher.py stop
```

**服务端口：**

| 服务 | 端口 | SSE 端点 |
|------|------|----------|
| sandbox | 8101 | `http://127.0.0.1:8101/sse` |
| weather | 8102 | `http://127.0.0.1:8102/sse` |
| search | 8103 | `http://127.0.0.1:8103/sse` |
| geo | 8104 | `http://127.0.0.1:8104/sse` |

**切换模式：** 修改 `MCP_SERVICE_DEFS` 中的 `type` 和 `url`：

```python
# 集成模式（子进程，默认）
{"name": "weather", "type": "stdio", "path": "mcp-services/weather/server.py"}

# 独立模式（远程 HTTP）
{"name": "weather", "type": "sse", "url": "http://127.0.0.1:8102/sse"}
```

### 3.1 sandbox-mcp — 代码沙箱执行

| 项目 | 说明 |
|------|------|
| 路径 | `sandbox_mcp/` |
| 工具 | `execute_code` · `scan_code_tool` · `get_sandbox_status` |
| 执行器 | mock(子进程) / docker(容器) / e2b(云端) 三种模式 |
| 安全 | 18 条危险模式规则，执行前静态扫描 |
| 降级 | MCP 不可用时自动回退到本地直接执行 |

**启动**：`python sandbox_mcp/server.py`

### 3.2 weather-mcp — 实时天气

| 项目 | 说明 |
|------|------|
| 路径 | `mcp-services/weather/server.py` |
| 数据源 | wttr.in（免费，无需 API Key） |
| 工具 | `get_current_weather` · `get_weather_json` · `get_forecast` · `get_moon_phase` |

**启动**：`python mcp-services/weather/server.py`

### 3.3 search-mcp — 网页搜索

| 项目 | 说明 |
|------|------|
| 路径 | `mcp-services/search/server.py` |
| 数据源 | DuckDuckGo（免费，无需 API Key） |
| 工具 | `search_web` · `search_news` · `search_images` |

**启动**：`python mcp-services/search/server.py`

### 3.4 geo-mcp — IP 地理信息

| 项目 | 说明 |
|------|------|
| 路径 | `mcp-services/geo/server.py` |
| 数据源 | ip-api.com（免费，无需 API Key） |
| 工具 | `get_ip_info` · `batch_ip_info` |

**启动**：`python mcp-services/geo/server.py`

---

## 四、目录结构

```
crafto/
├── app/                          # 主应用
│   ├── main.py                   # FastAPI 入口 + MCP 生命周期
│   ├── config.py                 # 配置加载 (.env)
│   ├── api/
│   │   ├── middleware/
│   │   │   ├── auth.py           # 认证（双方法 fallback）
│   │   │   └── trace_id.py       # TraceID 全链路追踪
│   │   └── routes/
│   │       ├── chat.py           # 对话 (/send, /sessions)
│   │       ├── user.py           # 注册/登录/个人信息
│   │       ├── skill.py          # 私有 Skill CRUD
│   │       └── admin.py          # 管理后台
│   ├── core/
│   │   ├── agent.py              # Agent 核心 + ReAct 循环
│   │   ├── session.py            # 会话管理
│   │   └── memory.py             # 三级记忆编排
│   ├── memory/
│   │   ├── short_term.py         # 短时记忆（Redis）
│   │   ├── summary.py            # 摘要记忆（LLM 压缩）
│   │   └── long_term.py          # 长期向量记忆（Qdrant）
│   ├── skills/                   # Skill 示例定义
│   │   └── examples/
│   ├── tools/
│   │   ├── registry.py           # 工具注册+调度 (→ MCP 客户端)
│   │   ├── skill_manager.py      # 动态技能管理
│   │   └── preset/               # 全局预置工具
│   │       ├── weather.py        # 天气（mock）
│   │       ├── date_calc.py      # 日期计算
│   │       └── text_processing.py # 文本处理
│   ├── sandbox/
│   │   ├── mcp_manager.py        # ★ MCP 管理器（自动连接所有服务）
│   ├── mcp_client.py         # MCP 客户端（自动降级）
│   │   ├── client.py             # 直接执行（降级路径）
│   │   └── code_scanner.py       # 代码安全扫描
│   ├── models/
│   │   ├── llm_client.py         # 统一 LLM 接口
│   │   ├── deepseek.py           # DeepSeek API 实现
│   │   ├── schemas.py            # Pydantic 模型
│   │   └── db_models.py          # SQLAlchemy 模型（7 表）
│   ├── logging_module/
│   │   ├── logger.py             # 结构化 JSON 日志
│   │   └── anomaly.py            # 异常故障追踪
│   ├── db/
│   │   ├── database.py           # SQLite/PostgreSQL 连接
│   │   ├── redis_client.py       # Redis + 内存降级
│   │   └── vector_store.py       # Qdrant + 内存向量降级
│   └── static/                   # 前端 SPA
│       ├── index.html            # 页面结构
│       ├── css/style.css         # 炫酷暗色玻璃主题
│       └── js/app.js             # 前端主逻辑
│
├── sandbox_mcp/                  # ★ MCP 代码沙箱服务
│   ├── server.py                 # FastMCP 服务入口
│   ├── config.py                 # 独立配置
│   ├── scanner.py                # 代码安全扫描
│   └── executor/
│       ├── base.py               # 抽象执行器
│       ├── mock.py               # 本地子进程
│       ├── docker.py             # Docker 容器
│       └── e2b.py                # E2B 云端沙箱
│
├── mcp-servers/                  # ★ MCP 独立服务启动器
│   └── launcher.py            #  start/stop/status
mcp-services/                 # 真实数据 MCP 服务
│   ├── weather/server.py         # 实时天气 (wttr.in)
│   ├── search/server.py          # 网页搜索 (DuckDuckGo)
│   └── geo/server.py             # IP 地理信息 (ip-api.com)
│
├── data/                         # SQLite 数据库
├── test_deepseek.py              # 集成测试脚本
├── .env                          # 配置（API Key 等）
├── README.md                     # 本文档
├── 项目问题总结.md                # 开发问题记录
├── 项目流程与架构介绍.md           # 架构详解
└── 程序调用流程详解.md             # 函数调用链路
```

---

## 五、API 路由一览

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/v1/auth/register` | 注册 | 公开 |
| POST | `/api/v1/auth/login` | 登录 | 公开 |
| GET | `/api/v1/auth/profile` | 个人信息 | ✅ |
| POST | `/api/v1/chat/send` | 发送消息 | ✅ |
| POST | `/api/v1/chat/send/stream` | 流式发送 | ✅ |
| GET | `/api/v1/chat/sessions` | 会话列表 | ✅ |
| GET | `/api/v1/chat/sessions/{id}/messages` | 历史消息 | ✅ |
| DELETE | `/api/v1/chat/sessions/{id}` | 删除会话 | ✅ |
| GET | `/api/v1/skills/` | Skill 列表 | ✅ |
| DELETE | `/api/v1/skills/{id}` | 删除 Skill | ✅ |
| GET | `/api/v1/admin/anomalies` | 异常记录 | admin |
| GET | `/api/v1/admin/logs` | 日志查询 | admin |
| GET | `/api/v1/admin/users` | 用户管理 | admin |
| GET | `/health` | 健康检查 | 公开 |
| GET | `/` | 前端首页 | 公开 |
| GET | `/static/*` | 静态文件 | 公开 |

---

## 六、开发问题修复记录

共修复 **11 个核心问题**，详见 `项目问题总结.md`：

| 类别 | 数量 | 代表性 Bug |
|------|------|-----------|
| 前端 JS | 5 | 输入框 disabled、箭头函数 this 丢失、模板字面量语法错误 |
| 认证架构 | 1 | X-API-Key 优先于 Bearer Token 导致 _resolve_token 永远不执行 |
| Agent ReAct | 4 | tool_calls 未提取、格式不兼容、循环内重复存储 assistant 消息 |
| 多轮对话 | 1 | 切换会话不加载历史消息 |

---

## 七、快速开始

```bash
# 1. 激活环境
conda activate crafto

# 2. 配置 API Key（编辑 .env 或 export）
export DEEPSEEK_API_KEY=sk-your-key-here

# 3. 启动服务（自动连接 MCP 沙箱）
cd /Users/ye/code/crafto
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload

# 4. 打开浏览器
open http://localhost:8100

# 5. （可选）启动独立 MCP 服务集群
python mcp-servers/launcher.py start    # 所有项目可用的 HTTP 服务
```

### 测试

```bash
# 注册
curl -X POST http://localhost:8100/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"123456","role":"advanced"}'

# 对话
curl -X POST http://localhost:8100/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {user_id}" \
  -d '{"message":"今天广州的天气怎么样？"}'
```

---

## 八、技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | **FastAPI** (Python 3.11) |
| 前端 | 原生 JS SPA + CSS3 动画 |
| AI 模型 | **DeepSeek API**（OpenAI 兼容） |
| MCP 协议 | **FastMCP**（Anthropic MCP SDK） |
| 数据库 | SQLite（开发）→ PostgreSQL（生产） |
| 缓存 | Redis（降级为内存） |
| 向量库 | Qdrant（降级为内存暴力检索） |
| 沙箱 | 子进程 / Docker / E2B |
| 外部 API | wttr.in / DuckDuckGo / ip-api.com |

---

## 九、项目状态

| 阶段 | 状态 | 功能 |
|------|------|------|
| 阶段 1：基础底座 | ✅ | 多用户 · 对话 · 日志 · 预置工具 · DeepSeek |
| 阶段 2：记忆与画像 | ✅ | 三级记忆 · 摘要 · 异常存储 |
| 阶段 3：核心特色 | ✅ | MCP 代码沙箱 · 动态 Skill · 私有持久化 |
| 阶段 4：MCP 服务集群 | ✅ | 4 个 MCP 服务 12 个工具，管理器自动连接 |
| 阶段 5：工业运维 | 🚧 | 日志检索 · 监控告警 · 限流熔断 |
| 阶段 6：生产优化 | 📅 | 集群部署 · 弹性扩容 · 加密灾备 |

---

## 十、Skill 技能系统

### 10.1 Skill 是什么

Skill 是**预封装的 Python 计算工具**，存储在数据库中，由 LLM 一键调用，在沙箱中一次性执行完毕。

**与 MCP 工具的核心区别：**

| 维度 | MCP 工具 | Skill |
|------|----------|-------|
| 执行方式 | 多轮 ReAct（LLM 每步决定下一步） | 一次性执行（LLM 只调用一次） |
| 决策主体 | LLM 逐轮推理 | LLM 一次调用，Python 代码自主运行 |
| Token 消耗 | 高（中间结果反复传回对话上下文） | 低（只在沙箱内计算） |
| 适用场景 | 需要实时数据的操作（天气/股价/门店查询） | 纯计算/格式化输出（分摊/规划/数据处理） |
| 数据来源 | 远程 API（外部服务） | 参数传进去，代码算出来 |
| 发现机制 | MCP Manager 自动连接 + list_tools() | ToolRegistry 从 DB 加载 |
| 生命周期 | 随 MCP 服务启停 | 持久化在 SQLite，随时 seed |

### 10.2 运行时流程

```
用户："帮我分摊一下，三个人吃饭花了428"

LLM 工具列表：
  ├─ weather__*          (描述：实时天气 — 不匹配)
  ├─ luckin__*           (描述：瑞幸咖啡 — 不匹配)
  ├─ query_weather       (描述：天气查询 — 不匹配)
  ├─ expense_splitter    (描述：费用分摊计算器 — 匹配！)
  ├─ investment_planner  (描述：定投计划 — 不匹配)
  └─ execute_python_code (兜底)

LLM 选择 expense_splitter
    → ToolRegistry 精确名称匹配
    → SkillManager.execute_skill(skill_id, arguments)
    → 参数注入为 Python 变量
    → 沙箱执行 → stdout 返回结果
    → LLM 看到结果，直接回复用户
```

判断完全由 LLM 的语义理解完成：每个 Skill 注册时都带一段 description 和参数 schema，LLM 把用户问题和这些描述做语义匹配，选中最合适的工具。

### 10.3 内置示例 Skill

| Skill | 描述 | 参数 | 代码量 |
|-------|------|------|--------|
| expense_splitter | 智能费用分摊计算器，支持 AA 制 + 特殊消费项 | total_amount, participants, paid_by, [special_items] | ~2000 字 |
| investment_planner | 定投计划计算器，按月复利，双模式（目标→时长/时长→终值） | monthly_amount, annual_return_rate, [target_amount, target_months] | ~4100 字 |

### 10.4 如何添加新 Skill

三步走：

1. 在 `app/skills/examples/` 下新建 Python 文件，定义 META 和 CODE：

```python
"""my_skill — 我的新技能"""

META = {
    "description": "技能描述（LLM 看到这个决定调用你）",
    "parameters": {
        "type": "object",
        "properties": {
            "input_a": {"type": "string", "description": "参数说明"},
        },
        "required": ["input_a"]
    }
}

CODE = r'''
# 注入变量：input_a
result = do_something(input_a)
print(f"结果: {result}")
'''
```

2. 在 `app/skills/examples/__init__.py` 的 EXAMPLE_SKILLS 列表中添加一条：

```python
from app.skills.examples import my_skill
EXAMPLE_SKILLS.append({
    "name": "my_skill",
    "description": my_skill.META["description"],
    "parameters": my_skill.META["parameters"],
    "code": my_skill.CODE,
    "language": "python",
    "tags": ["标签1"],
})
```

3. 运行 seed 脚本注册到数据库：

```bash
python scripts/seed_skills.py
```

重新启动应用后，LLM 就能看到并调用这个新 Skill 了。

### 10.5 变量注入规则

Skill 的代码在沙箱中以 exec() 方式执行。参数以 Python 变量形式直接注入：

```python
# 如果 LLM 传了 {"city": "上海", "days": 5}
# 沙箱里等价于先执行：
city = "上海"
days = 5

# 再执行你的 CODE
# ... 你的代码可以直接使用 city 和 days
```

代码通过 stdout 输出结果（print()），stdout 被捕获后返回给 LLM。

### 10.6 文件索引

```
app/skills/examples/
  __init__.py               # 示例 Skill 注册表
  expense_splitter.py       # 费用分摊计算器（生活工具）
  investment_planner.py     # 定投计划计算器（财务规划）

scripts/
  seed_skills.py            # Seed 脚本：注册示例 Skill 到 SQLite + 向量库
```
