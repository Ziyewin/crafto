"""Agent 核心引擎 —— 标准 ReAct 闭环：思考 → 工具/代码执行 → 结果反思 → 迭代优化
支持简单任务（工具调用）和复杂任务（代码生成 + 沙箱执行）
"""
from __future__ import annotations
from app.models.deepseek import get_llm_client
from app.models.schemas import ToolResult
from app.core.memory import MemoryOrchestrator
from app.core.session import SessionManager
from app.tools.registry import ToolRegistry
from app.tools.skill_manager import SkillManager
from app.logging_module.logger import get_logger, get_trace_id
from app.logging_module.anomaly import record_anomaly
from app.models.db_models import SkillType
from app.config import settings
import json
import uuid
import time
from typing import AsyncIterator

logger = get_logger("core.agent")

# ── System prompt for the agent ──

REACT_SYSTEM_PROMPT = """你是一个工业级智能 AI Agent，采用 ReAct（思考-行动-观察）模式工作。

## 工作流程

### 简单任务（单步工具调用）
对于简单问题（查天气、日期计算、文本处理），直接调用预置工具。

### 复杂任务（代码生成 + 沙箱执行）
对于多步骤、需要计算/数据处理/循环/分支的复杂任务：
1. 使用 `execute_python_code` 工具生成完整的 Python 代码
2. 代码会在远端沙箱中隔离执行，结果会返回给你
3. 根据执行结果决定是否进一步迭代优化

### MCP 工具（第三方远程服务）
工具列表中带 `service__tool` 前缀的是远程 MCP 服务，可直接调用：
- `luckin__*` — 瑞幸咖啡（可查门店/搜商品/预览订单/创建订单/取消订单）
- `akshare__*` — A 股行情查询（股价/K线/北向资金/财报/板块）
- `weather__*` — 实时天气数据
- `search__*` — 只读网页搜索，不能执行操作
- `geo__*` — IP 地理信息 + 城市位置查询

### 工具选择优先级（从高到低）
1. 特定领域 MCP 工具（`luckin__*` / `weather__*` / `geo__*` 等）— 优先使用
2. 预设工具（query_weather / date_calc / text_process）
3. 用户私有 Skill（`expense_splitter` / `investment_planner` 等）— **一次性计算类任务优先使用 Skill**

### 关于 Skill
Skill 是预封装的 Python 计算工具，在沙箱中一次性执行完毕。
- **与 MCP 的区别**：MCP 需要多轮"思考→调用→观察"往返，一轮只调一个工具；
  Skill 是"一步到位"——LLM 只需决定调哪个 Skill 和传什么参数，剩下的计算全在沙箱里完成。
- **优势**：省 token（减少 LLM 往返次数），快，不需要中间结果塞回对话上下文。
- **适用场景**：数学计算、金融规划、数据处理、格式化输出等"给你参数出结果"的任务。
- **不适用场景**：需要实时外部数据（天气、股价、门店查询等）——那些该用 MCP。

4. `search__search_web` — 只读搜索，不能执行操作
5. `execute_python_code` — 最后手段

### 关键规则

#### 🛑 唯一停止规则（最重要）
**当用户请求已完成时（如下单成功、查询完成），立即回复用户。不要再调用任何工具。** 不要 search、不要 verify、不要 confirm。

#### 📋 瑞幸咖啡下单工作流（严格按照这个顺序）
1. `luckin__queryShopList` → 查门店（用建筑名称或地址搜索）
2. `luckin__searchProductForMcp` → 搜商品（用第一步返回的 deptId）
3. `luckin__previewOrder` → 预览订单（用上一步的 deptId + productList）
4. `luckin__createOrder` → 创建订单（用上一步的 deptId + productList）

**完成第 4 步后，立即回复用户下单结果。不要调用 search 或其他任何工具。**

#### 🚫 搜索规则
- `search__search_web` 是**只读搜索**，不能用于下单、查天气、查地理信息、执行任何操作
- **在执行瑞幸下单工作流的过程中，绝对不要调用 `search__search_web`**
- 如果需要查地点坐标，用 `geo__get_city_location`，不用 search

#### ✅ 一般规则
- 优先使用远程 MCP 工具（`service__` 前缀），而不是自己写代码实现
- 优先尝试用户已有的私有 Skill
- 全局预置工具可以直接调用
- 复杂任务优先写代码，而不是多轮 Function Call
- 所有代码必须是安全的 Python
- 执行失败时分析错误并修复代码重试
"""


class Agent:
    """核心 Agent —— 管理对话生命周期、ReAct 循环、任务规划"""

    def __init__(self, user_id: str, session_id: str, user_role: str = "normal"):
        self.user_id = user_id
        self.session_id = session_id
        self.user_role = user_role
        self.memory = MemoryOrchestrator(user_id, session_id)
        self.session_mgr = SessionManager(user_id)
        self.tool_registry = ToolRegistry(user_id, mcp_enabled=True)
        self.skill_mgr = SkillManager(user_id)
        self.llm = get_llm_client()
        self.trace_id = get_trace_id() or str(uuid.uuid4())
        self.max_iterations = 15  # 最大 ReAct 循环次数，防止无限循环

    async def process_message(self, message: str) -> dict:
        """处理用户消息的主入口 —— 完整的 ReAct 循环"""
        start_time = time.time()
        logger.info("Agent 处理消息: session=%s, trace=%s", self.session_id, self.trace_id)

        # 1. 初始化记忆系统
        await self.memory.initialize()

        # 2. 记录用户消息
        await self.memory.add_user_message(message)
        await self.session_mgr.save_message(
            self.session_id, "user", message, trace_id=self.trace_id
        )

        # 3. 执行 ReAct 循环
        final_reply, tool_results, token_usage = await self._react_loop()

        # 4. 记录助手回复（tool_calls 已在 react 循环中以独立 tool 消息存储，这里不重复传入）
        await self.memory.add_assistant_message(final_reply)
        await self.session_mgr.save_message(
            self.session_id, "assistant", final_reply,
            prompt_tokens=token_usage.get("prompt_tokens", 0),
            completion_tokens=token_usage.get("completion_tokens", 0),
            trace_id=self.trace_id,
        )

        # 5. 检查是否需要生成摘要
        await self.memory.summarize_if_needed()

        # 6. 检查是否需要提取长期记忆
        await self.memory.store_long_term_memories()

        elapsed = time.time() - start_time
        logger.info(
            "Agent 处理完成: elapsed=%.2fs, tokens=%s",
            elapsed, token_usage,
        )

        return {
            "session_id": self.session_id,
            "reply": final_reply,
            "tool_calls": tool_results,
            "token_usage": token_usage,
            "trace_id": self.trace_id,
        }

    async def _react_loop(self) -> tuple[str, list[dict], dict]:
        """核心 ReAct 循环：思考 → 行动 → 观察 → 迭代"""
        full_tool_results = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0}

        for iteration in range(self.max_iterations):
            logger.debug("ReAct 迭代 %d/%d", iteration + 1, self.max_iterations)

            # 判断是否是高级用户（开放代码生成权限）
            can_generate_code = self.user_role in ("advanced", "admin")

            # 构建本次调用的工具列表
            tools = self.tool_registry.get_available_tools(
                include_code_gen=can_generate_code
            )

            # 构建上下文
            messages = await self.memory.build_context()

            # 调用 LLM
            try:
                response = await self.llm.chat(
                    messages=messages,
                    tools=tools if tools else None,
                    stream=False,
                )
            except Exception as e:
                logger.error("LLM 调用失败: %s", e)
                record_anomaly(
                    error_type="LLM_CALL_FAILURE",
                    context={"session_id": self.session_id, "iteration": iteration},
                    user_id=self.user_id,
                    trace_id=self.trace_id,
                    exc_info=e,
                )
                return (
                    f"抱歉，AI 模型调用出错了：{str(e)}",
                    full_tool_results,
                    total_usage,
                )

            # 统计 token
            total_usage["prompt_tokens"] += response.usage.prompt_tokens
            total_usage["completion_tokens"] += response.usage.completion_tokens

            content = response.content or ""
            finish_reason = response.finish_reason

            # 优先使用 LLM 返回的原生 tool_calls（OpenAI/DeepSeek 格式）
            tool_calls_in_response = []
            raw_tool_calls_for_memory = []  # 保留 OpenAI 格式用于对话历史
            if response.tool_calls:
                for tc_raw in response.tool_calls:
                    # 保留完整 OpenAI 格式用于记忆（含 type/function）
                    raw_tc = {
                        "id": tc_raw.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc_raw.get("function", {}).get("name", ""),
                            "arguments": tc_raw.get("function", {}).get("arguments", "{}"),
                        }
                    }
                    raw_tool_calls_for_memory.append(raw_tc)
                    # 提取简化格式用于工具执行
                    try:
                        args = json.loads(tc_raw.get("function", {}).get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    tool_calls_in_response.append({
                        "name": tc_raw.get("function", {}).get("name", ""),
                        "arguments": args,
                    })
            else:
                # 兼容旧格式：从文本中尝试解析 JSON 工具调用
                tool_calls_in_response = self._parse_tool_calls(content)

            if not tool_calls_in_response:
                # 没有工具调用 → 最终回复
                return content, full_tool_results, total_usage

            # 有工具调用 → 执行工具
            # 先把 assistant 消息（含 tool_calls）存一次，不要在循环里重复存
            tool_names = [tc["name"] for tc in tool_calls_in_response]
            await self.memory.add_assistant_message(
                f"正在调用工具: {', '.join(tool_names)}",
                tool_calls=raw_tool_calls_for_memory
            )

            for idx, tc in enumerate(tool_calls_in_response):
                tool_name = tc["name"]
                arguments = tc["arguments"]

                logger.info("执行工具: %s, 参数: %s", tool_name, arguments)

                # 使用 OpenAI 格式中的原始 call_id（用于 tool response 匹配）
                call_id = raw_tool_calls_for_memory[idx]["id"] if idx < len(raw_tool_calls_for_memory) else tool_name

                # 执行工具
                result = await self.tool_registry.execute_tool(
                    tool_name, arguments, self.session_id
                )

                # 记录工具执行结果（使用正确的 call_id）
                tool_result_str = json.dumps(result, ensure_ascii=False)
                await self.memory.add_tool_message(tool_result_str, call_id)
                await self.session_mgr.save_message(
                    self.session_id, "tool", tool_result_str,
                    tool_call_id=call_id,
                    trace_id=self.trace_id,
                )

                full_tool_results.append(result)

            # 继续下一轮 ReAct 循环
            # 循环检测：最近 4 次调用中有 3 次以上 search 则提前终止
            if len(full_tool_results) >= 4:
                recent_tools = [r.get("tool_name", "") for r in full_tool_results[-4:]]
                search_cnt = sum(1 for t in recent_tools if "search" in t)
                if search_cnt >= 3:
                    logger.warning("检测到搜索循环(%d次search)，提前终止", search_cnt)
                    break

        # 达到最大迭代次数 → 返回已完成的工具调用结果摘要
        accomplished = []
        for r in full_tool_results:
            tn = r.get("tool_name", "")
            if "createOrder" in tn: accomplished.append("✅ 已下单")
            elif "previewOrder" in tn: accomplished.append("📋 已预览订单")
            elif "searchProduct" in tn: accomplished.append("🔍 已查询商品")
            elif "queryShopList" in tn: accomplished.append("🏪 已查询门店")
            elif "get_city_location" in tn: accomplished.append("📍 已查位置")
            elif "get_current_weather" in tn: accomplished.append("🌤 已查天气")
            elif "search_web" in tn: accomplished.append("🌐 已搜索网页")
            elif "get_ip_info" in tn: accomplished.append("📍 已查IP")
            else: accomplished.append(f"🛠 {tn.split('__')[-1] if '__' in tn else tn}")
        
        if accomplished:
            summary = " → ".join(accomplished)
            return (summary, full_tool_results, total_usage)
        return ("抱歉，任务处理达到最大迭代次数。", full_tool_results, total_usage)

    def _parse_tool_calls(self, content: str) -> list[dict]:
        """解析 LLM 输出中的工具调用。
        支持两种格式：
        1. JSON function call 格式
        2. 文本中标记的 {{tool:name, args:{...}}} 格式
        """
        tool_calls = []

        # 尝试解析 JSON function call
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    if "tool" in item or "name" in item:
                        tool_calls.append({
                            "name": item.get("name") or item.get("tool"),
                            "arguments": item.get("arguments") or item.get("args", {}),
                        })
            elif isinstance(data, dict):
                if "name" in data or "tool" in data:
                    tool_calls.append({
                        "name": data.get("name") or data.get("tool"),
                        "arguments": data.get("arguments") or data.get("args", {}),
                    })
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试解析 OpenAI 格式的 tool_calls（从消息的 tool_calls 字段）
        # 这个由 LLM 客户端的原生 tool calling 处理

        return tool_calls

    async def process_stream(self, message: str) -> AsyncIterator[str]:
        """流式处理消息 —— 逐步输出思考和结果"""
        # 初始化记忆
        await self.memory.initialize()
        await self.memory.add_user_message(message)

        # 构建上下文
        messages = await self.memory.build_context()
        can_generate_code = self.user_role in ("advanced", "admin")
        tools = self.tool_registry.get_available_tools(
            include_code_gen=can_generate_code
        )

        # 流式调用 LLM
        try:
            async for chunk in self.llm.chat_stream(
                messages=messages,
                tools=tools if tools else None,
            ):
                yield chunk
        except Exception as e:
            yield f"\n\n[错误] 流式输出失败: {str(e)}"
