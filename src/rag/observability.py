"""结构化日志与阶段埋点。

对应需求 §13（结构化日志）与 §26（运维报告）：
日志字段是运维报告的唯一数据来源，因此字段定义必须集中管理，
并由 LOG_FIELD_DICTIONARY 单向生成文档，避免文档与实现漂移。
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import structlog

from .pii import redact_fields

# 日志字段字典（交付物要求）。修改此表即修改交付文档。
LOG_FIELD_DICTIONARY: tuple[tuple[str, str, str], ...] = (
    ("ts", "string", "事件时间（ISO8601，本地时区）"),
    ("level", "string", "日志级别"),
    ("event", "string", "事件名：span 或 request"),
    ("trace_id", "string", "全链路追踪 id"),
    ("request_id", "string", "单次请求 id"),
    ("session_id", "string", "会话 id（多轮）"),
    ("turn_index", "int", "会话轮次序号"),
    ("stage", "enum", "rewrite/retrieve/rerank/guardrail/generate/postprocess/cache/total"),
    ("latency_ms", "number", "该阶段耗时（毫秒）"),
    ("config_version", "string", "配置版本"),
    ("config_fingerprint", "string", "配置指纹（内容哈希）"),
    ("prompt_version", "string", "Prompt 版本"),
    ("corpus_version", "string", "知识库版本"),
    ("retrieval_mode", "enum", "vector | hybrid"),
    ("rerank_enabled", "bool", "是否启用重排"),
    ("top_k", "int", "召回数量"),
    ("top_n", "int", "送入生成的证据数量"),
    ("retrieved_chunk_ids", "string[]", "召回命中的 chunk id"),
    ("retrieval_scores", "number[]", "融合后的最终分数"),
    ("vector_scores", "number[]", "向量通道分数"),
    ("lexical_scores", "number[]", "词法通道分数"),
    ("rerank_scores", "number[]", "重排分数"),
    ("rerank_timeout", "bool", "重排是否超时降级"),
    ("cache_hit", "bool", "是否命中缓存"),
    ("cache_key_hash", "string", "缓存键哈希（不落原文）"),
    ("prompt_tokens", "int", "输入 token 数"),
    ("completion_tokens", "int", "输出 token 数"),
    ("total_tokens", "int", "token 总数"),
    ("cost_usd", "number", "本次请求估算成本（美元）"),
    ("model_id", "string", "生成模型标识"),
    ("answer_status", "enum", "answered | refused | error"),
    ("refusal_reason", "enum", "low_confidence | out_of_scope | safety | no_evidence"),
    ("citation_ids", "string[]", "答案引用的证据 chunk id"),
    ("support_score", "number", "答案被证据支撑的程度"),
    ("injection_flags", "string[]", "命中的 prompt 注入特征"),
    ("pii_redacted_fields", "string[]", "被脱敏的字段"),
    ("user_query", "string", "用户问题（按配置脱敏）"),
    ("error_type", "string", "异常类型"),
)

_LOGGER: Any = None
_LOG_SETTINGS: dict[str, Any] = {"redact_query": True, "mode": "hash"}


def new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"


def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:10]}"


def setup_logging(
    log_dir: str | Path = "logs",
    filename: str = "rag.jsonl",
    redact_query: bool = True,
    mode: str = "hash",
) -> Any:
    """把结构化日志写入 JSONL 文件，同时保持 stdout 安静。"""
    global _LOGGER, _LOG_SETTINGS
    _LOG_SETTINGS = {"redact_query": redact_query, "mode": mode}

    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(directory / filename, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger("rag")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False, key="ts"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _LOGGER = structlog.get_logger("rag")
    return _LOGGER


def _redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """日志脱敏：在渲染前拦截，确保 PII 不会写入磁盘。"""
    if _LOG_SETTINGS.get("redact_query") and "user_query" in event_dict:
        redacted, hits = redact_fields(
            event_dict, ("user_query",), str(_LOG_SETTINGS.get("mode", "hash"))
        )
        event_dict.update(redacted)
        if hits:
            existing = list(event_dict.get("pii_redacted_fields") or [])
            event_dict["pii_redacted_fields"] = sorted(set(existing + hits))
    return event_dict


def get_logger() -> Any:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = setup_logging()
    return _LOGGER


@contextmanager
def span(stage: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """阶段埋点：自动记录耗时，返回可写的字段容器。"""
    started = time.perf_counter()
    payload: dict[str, Any] = {}
    try:
        yield payload
    finally:
        elapsed = (time.perf_counter() - started) * 1000.0
        payload["latency_ms"] = round(elapsed, 2)
        record = {"event": "span", "stage": stage}
        record.update(payload)
        record.update(fields)
        get_logger().info(**record)


def log_request(payload: dict[str, Any]) -> None:
    record = {"event": "request"}
    record.update(payload)
    get_logger().info(**record)
