#!/usr/bin/env python
"""只重判、不重跑管线。

用途：评判标准或 judge 实现改进后，不需要再花一遍生成模型的调用费用——
检索结果（chunk id）已经记录在 items_*.jsonl 里，直接从索引取回证据重新评判即可。

用法：
    uv run python scripts/rejudge.py \
        --config configs/llm_c3_hybrid_rerank.yaml \
        --items reports/llm/items_llm_c3_hybrid_rerank.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.config import load_config  # noqa: E402
from rag.eval.judge import LLMJudge, RuleBasedJudge  # noqa: E402
from rag.eval.runner import aggregate_metrics  # noqa: E402
from rag.retrieve.store import INDEX_ROOT, LocalStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--items", required=True)
    parser.add_argument("--out-dir", default=None, help="默认与 items 同目录")
    parser.add_argument("--evidence-chars", type=int, default=1500)
    args = parser.parse_args()

    config = load_config(args.config)
    items_path = Path(args.items)
    out_dir = Path(args.out_dir) if args.out_dir else items_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    items = [
        json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    store = LocalStore.load(INDEX_ROOT / config.app.corpus_version)
    by_id = {chunk.chunk_id: chunk for chunk in store.chunks}

    # 用完整证据重建 judge 输入（原记录里的证据可能被截断过）
    missing = 0
    for item in items:
        evidence = []
        for chunk_id in item["retrieved_chunk_ids"]:
            chunk = by_id.get(chunk_id)
            if chunk is None:
                missing += 1
                continue
            evidence.append(
                {
                    "id": chunk.chunk_id,
                    "section": chunk.section_path,
                    "text": (chunk.parent_text or chunk.text)[: args.evidence_chars],
                }
            )
        item["_judge_input"] = {
            "item_id": item["item_id"],
            "question": item["question"],
            "evidence": evidence,
            "answer": item["answer"],
            "expected": "answer" if item["expected_status"] == "answered" else "refuse",
        }
    if missing:
        print(f"[warn] {missing} 个 chunk id 不在索引中（可能是切分策略变更）")

    # 先整体重置为规则评判，再让 LLM 评判覆盖作答项，保证口径一致
    rule = RuleBasedJudge()
    for item in items:
        verdict_answer = item["answer"] if item["expected_status"] == "answered" else "无法回答"
        item["compliance"] = {
            "compliance": 0.0,
            "checks": {"pending": True},
            "is_refusal": item["status"] == "refused",
        }
        item["style"] = rule.style(item["question"], verdict_answer)
        item["faithfulness"] = item.get("faithfulness") if item["status"] != "answered" else None

    stats = LLMJudge(config).apply(items) if config.eval.judge == "llm" else {"judged": 0}
    metrics = aggregate_metrics(items, config)
    metrics["judge_stats"] = stats

    suffix = items_path.stem.replace("items_", "")
    (out_dir / f"items_{suffix}.jsonl").write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8"
    )
    (out_dir / f"eval_{suffix}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
