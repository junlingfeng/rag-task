"""核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """入库的最小检索单元。子块用于检索，父块用于补全上下文。"""

    chunk_id: str
    doc_id: str
    text: str
    lang: str                     # zh | en | mixed
    doc_type: str                 # handbook | compliance | tech_spec | architecture
    section_path: str
    page: int
    is_scanned: bool = False
    ocr_confidence: float | None = None
    effective_date: str | None = None
    parent_id: str | None = None
    parent_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "text": self.text,
            "lang": self.lang,
            "doc_type": self.doc_type,
            "section_path": self.section_path,
            "page": self.page,
            "is_scanned": self.is_scanned,
            "ocr_confidence": self.ocr_confidence,
            "effective_date": self.effective_date,
            "parent_id": self.parent_id,
            "parent_text": self.parent_text,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Chunk":
        return Chunk(**data)


@dataclass
class Retrieved:
    """一条召回结果及其各阶段分数。分数全部落日志，便于诊断。"""

    chunk: Chunk
    score: float
    rank: int
    vector_score: float | None = None
    lexical_score: float | None = None
    rerank_score: float | None = None
    vector_rank: int | None = None
    lexical_rank: int | None = None

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id


@dataclass
class AnswerResult:
    trace_id: str
    request_id: str
    session_id: str
    turn_index: int
    question: str
    rewritten_question: str
    answer: str
    status: str                    # answered | refused | error
    refusal_reason: str | None
    citations: list[str] = field(default_factory=list)
    contexts: list[Retrieved] = field(default_factory=list)
    support_score: float = 0.0
    latency_ms: dict[str, float] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    cache_hit: bool = False
    cost_usd: float = 0.0
    config_version: str = ""
    injection_flags: list[str] = field(default_factory=list)
    pii_redacted_fields: list[str] = field(default_factory=list)
    model_id: str = ""
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "question": self.question,
            "rewritten_question": self.rewritten_question,
            "answer": self.answer,
            "status": self.status,
            "refusal_reason": self.refusal_reason,
            "citations": self.citations,
            "contexts": [
                {
                    "chunk_id": c.chunk_id,
                    "score": c.score,
                    "rank": c.rank,
                    "vector_score": c.vector_score,
                    "lexical_score": c.lexical_score,
                    "rerank_score": c.rerank_score,
                    "doc_id": c.chunk.doc_id,
                    "section_path": c.chunk.section_path,
                    "page": c.chunk.page,
                }
                for c in self.contexts
            ],
            "support_score": self.support_score,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "cache_hit": self.cache_hit,
            "cost_usd": self.cost_usd,
            "config_version": self.config_version,
            "injection_flags": self.injection_flags,
            "pii_redacted_fields": self.pii_redacted_fields,
            "model_id": self.model_id,
            "error_type": self.error_type,
        }
