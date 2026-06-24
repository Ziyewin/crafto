"""Redis 客户端 —— 短时会话缓存、限流、任务状态管理
如果 Redis 不可用，自动降级为内存存储（开发友好）
"""
from __future__ import annotations
from app.config import settings
import json
import logging
from typing import Optional

logger = logging.getLogger("redis_client")

_redis = None  # 全局 Redis 客户端实例


def get_redis():
    """获取 Redis 客户端（首次调用时初始化）"""
    global _redis
    if _redis is None:
        try:
            import redis as r
            _redis = r.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                decode_responses=True,
            )
            _redis.ping()
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.warning("Redis 不可用，使用内存存储降级方案: %s", e)
            _redis = _InMemoryRedis()
    return _redis


class _InMemoryRedis:
    """内存版 Redis 降级方案 —— 实现 Redis 常用接口的子集"""

    def __init__(self):
        self._data: dict[str, str] = {}
        self._expiry: dict[str, float] = {}

    def ping(self): return True

    def get(self, key: str) -> Optional[str]:
        """获取键值，自动检查过期"""
        if key in self._expiry and self._expiry[key] < __import__("time").time():
            self._data.pop(key, None)
            self._expiry.pop(key, None)
        return self._data.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = None):
        self._data[key] = value
        if ex:
            self._expiry[key] = __import__("time").time() + ex

    def delete(self, key: str):
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    def expire(self, key: str, seconds: int):
        self._expiry[key] = __import__("time").time() + seconds

    def setex(self, key: str, seconds: int, value: str):
        """设置键值并指定过期时间"""
        self.set(key, value, ex=seconds)

    def exists(self, key: str) -> int:
        return 1 if key in self._data else 0

    def lpush(self, key: str, *values):
        """列表左推入"""
        if key not in self._data:
            self._data[key] = json.dumps(list(values))
        else:
            lst = json.loads(self._data[key])
            lst = list(values) + lst
            self._data[key] = json.dumps(lst)
        return len(values)

    def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """获取列表范围内的元素"""
        if key not in self._data:
            return []
        lst = json.loads(self._data[key])
        return lst[start:stop] if stop >= 0 else lst[start:]

    def ltrim(self, key: str, start: int, stop: int):
        """修剪列表到指定范围"""
        if key in self._data:
            lst = json.loads(self._data[key])
            self._data[key] = json.dumps(lst[start:stop])

    def incr(self, key: str) -> int:
        val = int(self._data.get(key, "0")) + 1
        self._data[key] = str(val)
        return val

    def ttl(self, key: str) -> int:
        """获取键剩余生存时间"""
        if key in self._expiry:
            remaining = int(self._expiry[key] - __import__("time").time())
            return max(0, remaining)
        return -1

    def pipeline(self):
        return self


# ── 统一缓存接口 ──

def cache_get(key: str) -> Optional[str]:
    """获取缓存"""
    return get_redis().get(key)


def cache_set(key: str, value: str, ttl: int = 3600):
    """设置缓存（默认1小时过期）"""
    get_redis().setex(key, ttl, value)


def cache_delete(key: str):
    """删除缓存"""
    get_redis().delete(key)


def session_push(session_id: str, message_json: str, max_len: int = 100):
    """向会话消息列表推入一条消息（自动裁剪）"""
    r = get_redis()
    key = f"session:{session_id}:messages"
    r.lpush(key, message_json)
    r.ltrim(key, 0, max_len - 1)
    r.expire(key, 86400)  # 24 小时 TTL


def session_get(session_id: str, start: int = 0, stop: int = 99) -> list[str]:
    """获取会话消息列表"""
    r = get_redis()
    key = f"session:{session_id}:messages"
    return r.lrange(key, start, stop) or []
