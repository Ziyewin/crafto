"""应用配置 —— 从 .env 文件和环境变量加载所有配置项"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── 模型 API 配置 ──
    deepseek_api_key: str = ""                     # DeepSeek API 密钥
    deepseek_base_url: str = "https://api.deepseek.com"  # API 基础地址
    llm_model: str = "deepseek-chat"               # 默认模型名称
    llm_max_tokens: int = 8192                     # 最大生成 token 数
    llm_temperature: float = 0.7                   # 生成温度

    # ── Redis 缓存 ──
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # ── 向量数据库 ──
    vector_db_url: str = "http://localhost:6333"
    vector_db_collection: str = "agent_memory"

    # ── 沙箱模式 ──
    sandbox_mode: str = "mock"                     # mock | docker | e2b
    sandbox_timeout: int = 30                      # 沙箱执行超时（秒）

    # ── 第三方 MCP 服务密钥 ──
    luckin_mcp_key: str = ""                       # 瑞幸咖啡 MCP Bearer Token

    # ── 应用基础 ──
    secret_key: str = "dev-secret-key"             # JWT/加密密钥
    log_level: str = "DEBUG"                       # 日志级别
    max_memory_tokens: int = 4096                  # 短时记忆最大 token
    summary_trigger_tokens: int = 2048             # 触发摘要的 token 阈值
    top_k_memory: int = 5                          # 检索长期记忆条数
    top_k_skills: int = 3                          # 检索 Skill 条数


settings = Settings()
