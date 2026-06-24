"""工业级智能 Agent 平台 —— FastAPI 入口
架构：前端交互层 → API网关层 → Agent核心调度层 → 能力支撑层 → 数据存储层
"""
from __future__ import annotations
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from app.api.middleware.trace_id import TraceIDMiddleware
from app.api.middleware.auth import AuthMiddleware
from app.api.routes import chat, user, skill, admin
from app.db.database import init_db
from app.logging_module.logger import setup_logging
from app.config import settings
from app.sandbox.mcp_manager import mcp_manager
import logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    setup_logging(settings.log_level)
    logger = logging.getLogger("main")
    logger.info("正在初始化数据库...")
    init_db()
    await mcp_manager.start_all()
    logger.info("Agent 平台启动完成")
    yield
    # 关闭时执行
    await mcp_manager.stop_all()
    logger.info("Agent 平台正在关闭...")


app = FastAPI(
    title="工业级智能 Agent 平台",
    description="多租户工业级智能Agent平台，融合传统工具调用与LLM动态自研技能机制",
    version="1.0.0",
    lifespan=lifespan,
)

# ── 中间件（从外到内顺序） ──

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TraceID 生成
app.add_middleware(TraceIDMiddleware)

# 认证（在 TraceID 之后，确保日志有 TraceID）
app.add_middleware(AuthMiddleware)


# ── 静态文件服务 ──

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── 根路径重定向到前端 ──

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


# ── 注册 API 路由 ──

app.include_router(chat.router)
app.include_router(user.router)
app.include_router(skill.router)
app.include_router(admin.router)


# ── 全局异常处理 ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = logging.getLogger("main")
    logger.error("未捕获异常: %s | path=%s", exc, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"服务器内部错误: {str(exc)}",
            "code": "INTERNAL_ERROR",
            "path": request.url.path,
        },
    )


# ── 健康检查 ──

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "service": "industrial-agent-platform",
    }


# ── 直接运行入口 ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8100, reload=True)
