#!/usr/bin/env python
"""越界判定阈值标定。

在标注数据上比较 ScopeDetector 分数在 in-scope 与越界两类上的分布，
选择最大化平衡准确率的阈值，并输出可直接写入配置的值。

这一步是把"拒答阈值"从拍脑袋变成有依据的参数，也是评测报告里
"阈值如何确定"这一问题的答案。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.config import load_config  # noqa: E402
from rag.eval.dataset import EVAL_DIR  # noqa: E402
from rag.guardrails import ScopeDetector  # noqa: E402
from rag.retrieve.lexical import BM25  # noqa: E402
from rag.retrieve.store import INDEX_ROOT, LocalStore  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    config = load_config("configs/base.yaml")
    store = LocalStore.load(INDEX_ROOT / config.app.corpus_version)
    bm25 = BM25([c.text for c in store.chunks])

    positives = load_jsonl(EVAL_DIR / "single_turn.jsonl")
    negatives = [
        item
        for item in load_jsonl(EVAL_DIR / "negatives.jsonl")
        if item["subset"] in ("out_of_scope", "low_confidence")
    ]
    detector = ScopeDetector(store.chunks, bm25)
    positive_signals = [detector.evaluate(item["question"]) for item in positives]
    negative_signals = [detector.evaluate(item["question"]) for item in negatives]

    def out_of_scope(signal: dict, coverage_min: float, oov_max: float, uni_max: float) -> bool:
        return signal["coverage"] < coverage_min or (
            signal["oov"] > oov_max and signal["oov_unigram"] > uni_max
        )

    rows = []
    best = {"balanced_accuracy": 0.0}
    for coverage_min in [i / 20 for i in range(0, 13)]:
        for oov_max in [i / 20 for i in range(4, 19, 2)]:
            for uni_max in [i / 20 for i in range(2, 19, 2)]:
                accept_in = sum(
                    1
                    for s in positive_signals
                    if not out_of_scope(s, coverage_min, oov_max, uni_max)
                ) / len(positive_signals)
                reject_out = sum(
                    1
                    for s in negative_signals
                    if out_of_scope(s, coverage_min, oov_max, uni_max)
                ) / len(negative_signals)
                balanced = (accept_in + reject_out) / 2
                row = {
                    "coverage_min": round(coverage_min, 2),
                    "oov_max": round(oov_max, 2),
                    "oov_unigram_max": round(uni_max, 2),
                    "in_scope_accept": round(accept_in, 4),
                    "out_of_scope_reject": round(reject_out, 4),
                    "balanced_accuracy": round(balanced, 4),
                }
                rows.append(row)
                if balanced > best["balanced_accuracy"]:
                    best = row

    result = {
        "positives": len(positives),
        "negatives": len(negatives),
        "current_config": {
            "coverage_min": config.guardrails.scope_coverage_min,
            "oov_max": config.guardrails.scope_oov_max,
        },
        "current_config_score": next(
            (
                row
                for row in rows
                if row["coverage_min"] == round(config.guardrails.scope_coverage_min, 2)
                and row["oov_max"] == round(config.guardrails.scope_oov_max, 2)
                and row["oov_unigram_max"] == round(config.guardrails.scope_oov_unigram_max, 2)
            ),
            None,
        ),
        "recommended": best,
        "top10": sorted(rows, key=lambda r: -r["balanced_accuracy"])[:10],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
