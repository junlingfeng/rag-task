"""HTTP API（FastAPI）。

需求只要求 API，不要求前端；这里提供最小但完整的对外接口。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from .config import load_config
from .pipeline import RagPipeline

CONFIG_PATH = os.environ.get("RAG_CONFIG", "configs/base.yaml")

app = FastAPI(title="RAG QA Service", version="0.1.0")
pipeline: RagPipeline | None = None


class AskRequest(BaseModel):
    question: str
    session_id: str = "api"


class AskResponse(BaseModel):
    trace_id: str
    answer: str
    status: str
    refusal_reason: str | None
    citations: list[str]
    rewritten_question: str
    latency_ms: dict[str, float]
    token_usage: dict[str, int]
    cache_hit: bool
    cost_usd: float
    config_version: str


def get_pipeline() -> RagPipeline:
    global pipeline
    if pipeline is None:
        pipeline = RagPipeline(load_config(CONFIG_PATH))
    return pipeline


@app.on_event("startup")
def _startup() -> None:
    get_pipeline()


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "config": CONFIG_PATH,
        "index": str(Path("data/index")),
    }


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    result = get_pipeline().ask(request.question, session_id=request.session_id)
    return AskResponse(
        trace_id=result.trace_id,
        answer=result.answer,
        status=result.status,
        refusal_reason=result.refusal_reason,
        citations=result.citations,
        rewritten_question=result.rewritten_question,
        latency_ms=result.latency_ms,
        token_usage=result.token_usage,
        cache_hit=result.cache_hit,
        cost_usd=result.cost_usd,
        config_version=result.config_version,
    )
