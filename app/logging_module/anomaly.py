"""异常故障追踪模块 —— 与普通日志分离存储，独立复盘溯源
所有异常通过 TraceID 关联到完整上下文，支持故障定位和重试
"""
from __future__ import annotations
from app.models.db_models import AnomalyRecord, _utcnow
from app.db.database import get_db_sync
from app.logging_module.logger import get_trace_id
import uuid
import traceback
from typing import Optional


def record_anomaly(
    error_type: str,
    context: dict = None,
    problem_code: str = None,
    user_id: str = None,
    trace_id: str = None,
    exc_info: Optional[BaseException] = None,
) -> str:
    """记录一条异常故障，包含完整上下文，返回 anomaly_id"""
    anomaly_id = str(uuid.uuid4())
    tid = trace_id or get_trace_id() or anomaly_id

    # 提取堆栈信息
    stack = "".join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)) if exc_info else None

    record = AnomalyRecord(
        anomaly_id=anomaly_id,
        trace_id=tid,
        user_id=user_id,
        error_type=error_type,
        stack_trace=stack,
        context=context or {},
        problem_code=problem_code,
        retry_status="pending",
        resolved=False,
        created_at=_utcnow(),
    )
    try:
        db = get_db_sync()
        db.add(record)
        db.commit()
        db.close()
    except Exception as e:
        import logging
        logging.getLogger("anomaly").error("持久化异常记录失败: %s", e)
    return anomaly_id


def resolve_anomaly(anomaly_id: str):
    """标记异常为已解决"""
    try:
        db = get_db_sync()
        record = db.query(AnomalyRecord).filter_by(anomaly_id=anomaly_id).first()
        if record:
            record.resolved = True
            record.resolved_at = _utcnow()
            db.commit()
        db.close()
    except Exception as e:
        import logging
        logging.getLogger("anomaly").error("标记异常解决失败: %s", e)


def list_anomalies(user_id: str = None, limit: int = 50) -> list[dict]:
    """列出异常记录"""
    db = get_db_sync()
    query = db.query(AnomalyRecord)
    if user_id:
        query = query.filter_by(user_id=user_id)
    records = query.order_by(AnomalyRecord.created_at.desc()).limit(limit).all()
    db.close()
    return [
        {
            "anomaly_id": r.anomaly_id,
            "trace_id": r.trace_id,
            "error_type": r.error_type,
            "user_id": r.user_id,
            "retry_status": r.retry_status,
            "resolved": r.resolved,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
