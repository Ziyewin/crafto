"""向量数据库抽象层 —— 支持 Qdrant，自动降级为内存向量检索
嵌入模型使用简化版字符 Bigram 哈希（128维），生产环境需替换为 BGE/OpenAI 嵌入
"""
from __future__ import annotations
from app.config import settings
import logging
import json
from typing import Optional
import numpy as np

logger = logging.getLogger("vector_store")

_vector_client = None  # 全局向量存储客户端


def get_vector_store():
    """获取向量存储客户端（懒加载单例）"""
    global _vector_client
    if _vector_client is None:
        try:
            # 优先连接 Qdrant
            from qdrant_client import QdrantClient
            client = QdrantClient(url=settings.vector_db_url, timeout=5)
            client.get_collections()
            _vector_client = _QdrantStore(client, settings.vector_db_collection)
            logger.info("Qdrant 向量库连接成功")
        except Exception as e:
            logger.warning("Qdrant 不可用，使用内存向量库降级方案: %s", e)
            _vector_client = _InMemoryVectorStore()
    return _vector_client


# ── 嵌入向量生成 ──

def _mock_embed(text: str) -> list[float]:
    """简化版文本嵌入：基于字符 Bigram 哈希生成 128 维向量
    生产环境应替换为 DeepSeek/OpenAI/BGE 等专业嵌入模型
    """
    dim = 128
    vec = np.zeros(dim, dtype=np.float32)
    for i, ch in enumerate(text):
        idx = (hash(ch) % (dim - 1) + dim) % (dim - 1)
        vec[idx] += 1.0
    # L2 归一化
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec.tolist()


# ── Qdrant 客户端封装 ──

class _QdrantStore:
    """Qdrant 向量数据库封装"""

    def __init__(self, client, collection: str):
        self._client = client
        self._collection = collection
        from qdrant_client.http import models as qmodels
        self._qm = qmodels
        self._ensure_collection()

    def _ensure_collection(self):
        """确保 collection 存在，不存在则创建"""
        try:
            self._client.get_collection(self._collection)
        except Exception:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=self._qm.VectorParams(size=128, distance=self._qm.Distance.COSINE),
            )

    def upsert(self, vector_id: str, vector: list[float], payload: dict):
        """插入或更新向量"""
        self._client.upsert(
            collection_name=self._collection,
            points=[self._qm.PointStruct(id=vector_id, vector=vector, payload=payload)],
        )

    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        """向量相似度检索"""
        results = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
        )
        return [
            {"id": p.id, "score": p.score, "payload": p.payload}
            for p in results
        ]

    def delete(self, vector_id: str):
        """删除向量"""
        self._client.delete(
            collection_name=self._collection,
            points_selector=self._qm.Filter(
                must=[self._qm.FieldCondition(key="id", match=self._qm.MatchValue(value=vector_id))]
            ),
        )


# ── 内存版向量库降级 ──

class _InMemoryVectorStore:
    """内存版向量检索 —— 开发调试用"""

    def __init__(self):
        self._points: dict[str, tuple[list[float], dict]] = {}

    def upsert(self, vector_id: str, vector: list[float], payload: dict):
        self._points[vector_id] = (vector, payload)

    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        """暴力余弦相似度检索"""
        scored = []
        vec_arr = np.array(vector, dtype=np.float32)
        for vid, (v, payload) in self._points.items():
            v_arr = np.array(v, dtype=np.float32)
            dot = float(np.dot(vec_arr, v_arr))  # 归一化后点积=余弦
            scored.append((dot, vid, payload))
        scored.sort(key=lambda x: -x[0])
        return [
            {"id": vid, "score": sc, "payload": payload}
            for sc, vid, payload in scored[:top_k]
        ]

    def delete(self, vector_id: str):
        self._points.pop(vector_id, None)


# ── 统一公共接口 ──

def store_memory(memory_id: str, text: str, user_id: str, memory_type: str, metadata: dict = None):
    """存储一条记忆到向量库"""
    vs = get_vector_store()
    vec = _mock_embed(text)
    payload = {
        "user_id": user_id,
        "memory_type": memory_type,
        "text": text[:512],
        **(metadata or {}),
    }
    vs.upsert(memory_id, vec, payload)


def search_memory(user_id: str, query: str, top_k: int = 5) -> list[dict]:
    """根据语义检索用户记忆"""
    vs = get_vector_store()
    vec = _mock_embed(query)
    results = vs.search(vec, top_k=top_k)
    # 客户端过滤 user_id（Qdrant 应在服务端用 filter）
    filtered = [r for r in results if r["payload"].get("user_id") == user_id]
    return filtered[:top_k]


def store_skill_embedding(skill_id: str, text: str, user_id: str, metadata: dict = None):
    """存储 Skill 的向量嵌入（用于语义检索匹配）"""
    vs = get_vector_store()
    vec = _mock_embed(text)
    payload = {
        "user_id": user_id,
        "memory_type": "skill",
        "text": text[:512],
        "skill_id": skill_id,
        **(metadata or {}),
    }
    vs.upsert(f"skill:{skill_id}", vec, payload)


def search_skills(user_id: str, query: str, top_k: int = 3) -> list[dict]:
    """语义检索用户私有的持久化 Skill"""
    vs = get_vector_store()
    vec = _mock_embed(query)
    results = vs.search(vec, top_k=top_k * 2)
    filtered = [
        r for r in results
        if r["payload"].get("user_id") == user_id
        and r["payload"].get("memory_type") == "skill"
    ]
    return filtered[:top_k]
