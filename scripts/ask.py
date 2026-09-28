#!/usr/bin/env python
"""单次问答（调试用）：打印答案、引用、各阶段耗时与一次日志摘要。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.config import load_config  # noqa: E402
from rag.pipeline import RagPipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--config", default="configs/c2_hybrid.yaml")
    parser.add_argument("--session", default="cli")
    parser.add_argument("--json", action="store_true", help="输出完整结构化结果")
    args = parser.parse_args()

    pipeline = RagPipeline(load_config(args.config))
    result = pipeline.ask(args.question, session_id=args.session)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"Q: {args.question}")
    print(f"A: {result.answer}")
    print(f"status={result.status} refusal_reason={result.refusal_reason}")
    print(f"citations={result.citations}")
    print(
        "contexts="
        + json.dumps(
            [
                {"id": c.chunk_id, "score": c.score, "rerank": c.rerank_score, "section": c.chunk.section_path}
                for c in result.contexts
            ],
            ensure_ascii=False,
        )
    )
    print(f"latency_ms={result.latency_ms}")
    print(f"tokens={result.token_usage} cost_usd={result.cost_usd}")


if __name__ == "__main__":
    main()
