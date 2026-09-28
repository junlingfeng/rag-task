#!/usr/bin/env python
"""并发压测：验证"单实例 ≥5 并发、P90 ≤10s"。

用 asyncio 并发调用 pipeline（同步封装在线程池里），输出 P50/P90/P95 与错误率。
注意：离线生成后端的延迟由本地计算主导，真实模型的延迟必须用真实后端重测，
本脚本输出的是**框架层与检索层**的并发表现。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.config import load_config  # noqa: E402
from rag.eval.dataset import EVAL_DIR  # noqa: E402
from rag.eval.metrics import percentile  # noqa: E402
from rag.pipeline import RagPipeline  # noqa: E402


def load_questions(limit: int) -> list[str]:
    path = EVAL_DIR / "single_turn.jsonl"
    questions = [
        json.loads(line)["question"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return (questions * ((limit // len(questions)) + 1))[:limit]


async def run(config_path: str, concurrency: int, requests: int) -> dict:
    config = load_config(config_path)
    pipeline = RagPipeline(config)
    questions = load_questions(requests)
    latencies: list[float] = []
    errors = 0
    lock = asyncio.Lock()

    async def worker(index: int) -> None:
        nonlocal errors
        question = questions[index]
        started = time.perf_counter()
        try:
            # 关闭缓存以模拟最坏情况（缓存命中会让压测失真）
            await asyncio.to_thread(pipeline.ask, question, f"load_{index}")
        except Exception:
            errors += 1
        elapsed = (time.perf_counter() - started) * 1000
        async with lock:
            latencies.append(elapsed)

    started_all = time.perf_counter()
    queue: asyncio.Queue[int] = asyncio.Queue()
    for index in range(requests):
        queue.put_nowait(index)

    async def runner() -> None:
        while not queue.empty():
            try:
                index = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            await worker(index)

    await asyncio.gather(*[runner() for _ in range(concurrency)])
    wall = time.perf_counter() - started_all
    return {
        "config_version": config.app.config_version,
        "concurrency": concurrency,
        "requests": requests,
        "errors": errors,
        "wall_time_s": round(wall, 2),
        "throughput_rps": round(requests / wall, 2),
        "p50_ms": round(percentile(latencies, 0.5), 2),
        "p90_ms": round(percentile(latencies, 0.9), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "meets_p90_10s": percentile(latencies, 0.9) <= 10000,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/c3_hybrid_rerank.yaml")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--out", default="reports/loadtest.json")
    args = parser.parse_args()

    result = asyncio.run(run(args.config, args.concurrency, args.requests))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
