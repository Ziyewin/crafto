"""数据库连接管理 —— 开发环境使用 SQLite，生产环境切换 PostgreSQL"""
from __future__ import annotations
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session as SASession
from app.models.db_models import Base
from pathlib import Path

_engine = None           # 全局数据库引擎
_SessionLocal = None     # 全局 Session 工厂


def get_db_path() -> str:
    """获取数据库文件路径（自动创建 data 目录）"""
    db_dir = Path(__file__).resolve().parent.parent.parent / "data"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "agent_platform.db")


def get_engine():
    """获取或创建数据库引擎（单例）"""
    global _engine
    if _engine is None:
        db_url = f"sqlite:///{get_db_path()}"
        _engine = create_engine(db_url, connect_args={"check_same_thread": False}, echo=False)
        # 启用 SQLite WAL 模式提升并发性能
        event.listen(_engine, "connect", _set_sqlite_pragma)
    return _engine


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """设置 SQLite 性能优化参数"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")       # WAL 模式，读写不互斥
    cursor.execute("PRAGMA synchronous=NORMAL")     # 平衡性能与安全
    cursor.execute("PRAGMA foreign_keys=ON")        # 启用外键约束
    cursor.close()


def get_session_local() -> sessionmaker:
    """获取 Session 工厂"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def init_db():
    """初始化数据库：创建所有表"""
    Base.metadata.create_all(bind=get_engine())


def get_db() -> SASession:
    """FastAPI 依赖注入：获取数据库 session（自动关闭）"""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def get_db_sync() -> SASession:
    """同步获取数据库 session（非 FastAPI 环境下使用）"""
    db = get_session_local()()
    return db
