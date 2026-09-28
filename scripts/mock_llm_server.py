#!/usr/bin/env python
"""本地模拟 LLM 服务（OpenAI 兼容）。

用途：在没有真实 API Key / 无法访问外网的机器上，验证"真实模型接入路径"是否正确，
包括请求格式、鉴权头、响应解析、token 计费与错误处理。

它**不产生真实模型效果**，只验证链路。接入真实服务后请用真实服务复测。

启动：uv run python scripts/mock_llm_server.py --port 8123
"""

from __future__ import annotations

import argparse
import os
import re
import time
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock OpenAI-compatible server")

# 只有这个 key 会被接受；其余一律 401，用于验证客户端的鉴权与错误处理路径
ACCEPTED_KEY = os.environ.get("MOCK_API_KEY", "mock-key-for-verification")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None


def estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return int(cjk + len(re.findall(r"[A-Za-z]", text)) / 4) + 1


@app.post("/v1/chat/completions")
def chat(request: ChatRequest, authorization: str | None = Header(default=None)) -> dict:
    if not authorization or authorization != f"Bearer {ACCEPTED_KEY}":
        raise HTTPException(status_code=401, detail="missing or invalid api key")

    user_content = request.messages[-1].content
    context_match = re.search(r"<context>(.*?)</context>", user_content, re.S)
    question_match = re.search(r"Question:\s*(.*)$", user_content, re.S)
    context = (context_match.group(1) if context_match else "").strip()
    question = (question_match.group(1) if question_match else "").strip()

    # 模拟"基于证据作答"：取上下文中最相关的一段，并附引用标记
    blocks = re.findall(r"\[(\d+)\][^\n]*\n(.+)", context)
    answer_body = blocks[0][1][:180] if blocks else "资料不足"
    citation = blocks[0][0] if blocks else "1"
    if re.search(r"[\u4e00-\u9fff]", question):
        content = f"根据内部文档：{answer_body}[{citation}]"
    else:
        content = f"According to the internal documents: {answer_body}[{citation}]"

    prompt_tokens = sum(estimate_tokens(m.content) for m in request.messages)
    completion_tokens = estimate_tokens(content)
    # 模拟真实服务的响应耗时
    time.sleep(0.05)
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": "mock-model", "object": "model"}]}


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
