"""评测运行器：跑配置 → 打指标 → 出报告 → 做对比。

流程分三步，便于替换评判方式：
  1) 逐条跑管线，收集答案、检索结果与客观信号（耗时、token、拒答状态）；
  2) 评判（规则评判，或 LLM 评判覆盖）；
  3) 从条目聚合出全部指标。
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from ..config import Config, load_config
from ..pipeline import RagPipeline
from .dataset import EVAL_DIR
from .judge import LLMJudge, RuleBasedJudge
from .metrics import (
    context_precision,
    percentile,
    recall_at_k,
    reciprocal_rank,
    refusal_metrics,
)

REPORT_DIR = Path("reports")


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _record(
    item_id: str,
    subset: str,
    lang: str,
    question: str,
    result,
    expected_status: str,
    gold_chunk_ids: list[str],
    requires_rewrite: bool = False,
) -> dict:
    """把一次管线调用整理成可评判、可聚合的条目。"""
    retrieved_ids = [c.chunk_id for c in result.contexts]
    evidence = [
        {
            "id": c.chunk_id,
            "section": c.chunk.section_path,
            # 证据必须给足：截断会让 judge 看不到支持句，把正确回答误判为编造。
            # 实测截断到 280 字符时，"每页最多 200 条"这类位于 chunk 后半段的
            # 事实会被判成幻觉，因此这里保留父块级别的完整证据。
            "text": (c.chunk.parent_text or c.chunk.text)[:1500],
        }
        for c in result.contexts
    ]
    return {
        "item_id": item_id,
        "subset": subset,
        "lang": lang,
        "question": question,
        "effective_question": result.rewritten_question,
        "requires_rewrite": requires_rewrite,
        "expected_status": expected_status,
        "status": result.status,
        "refusal_reason": result.refusal_reason,
        "answer": result.answer,
        "gold_chunk_ids": gold_chunk_ids,
        "retrieved_chunk_ids": retrieved_ids,
        "context_precision": round(context_precision(retrieved_ids, gold_chunk_ids, k=5), 4),
        "recall_at_5": round(recall_at_k(retrieved_ids, gold_chunk_ids, 5), 4),
        "reciprocal_rank": round(reciprocal_rank(retrieved_ids, gold_chunk_ids), 4),
        "latency_ms": result.latency_ms.get("total", 0.0),
        "retrieve_ms": result.latency_ms.get("retrieve", 0.0),
        "generate_ms": result.latency_ms.get("generate", 0.0),
        "token_usage": result.token_usage,
        "cost_usd": result.cost_usd,
        "cache_hit": result.cache_hit,
        "pii_redacted_fields": result.pii_redacted_fields,
        "_judge_input": {
            "item_id": item_id,
            "question": question,
            "evidence": evidence,
            "answer": result.answer,
            "expected": "answer" if expected_status == "answered" else "refuse",
        },
    }


def _apply_rule_judge(judge: RuleBasedJudge, item: dict) -> None:
    contexts = _FakeContexts(item)
    verdict = judge.compliance(
        item["effective_question"] if item["requires_rewrite"] else item["question"],
        item["answer"],
        contexts,
        [c["id"] for c in item["_judge_input"]["evidence"] if c["id"] in item["retrieved_chunk_ids"]]
        if item["status"] == "answered"
        else [],
        item["expected_status"],
    )
    style = judge.style(item["question"], item["answer"] if item["expected_status"] == "answered" else "无法回答")
    item["compliance"] = verdict
    item["style"] = style
    item["faithfulness"] = (
        judge.faithfulness(item["answer"], contexts) if item["status"] == "answered" else None
    )


class _FakeContexts(list):
    """把条目里的证据还原成 judge 需要的 Retrieved 结构（只用到 text 字段）。"""

    def __init__(self, item: dict) -> None:
        super().__init__()
        for entry in item["_judge_input"]["evidence"]:
            self.append(_FakeRetrieved(entry))


class _FakeRetrieved:
    def __init__(self, entry: dict) -> None:
        self.chunk = _FakeChunk(entry)
        self.score = 0.0
        self.rank = 0


class _FakeChunk:
    def __init__(self, entry: dict) -> None:
        self.chunk_id = entry["id"]
        self.text = entry["text"]
        self.parent_text = None


def run_eval(
    config_path: str | Path | Config,
    eval_dir: Path = EVAL_DIR,
    report_dir: Path = REPORT_DIR,
    cache_probe_ratio: float = 0.25,
) -> dict:
    config = config_path if isinstance(config_path, Config) else load_config(config_path)
    pipeline = RagPipeline(config)
    report_dir.mkdir(parents=True, exist_ok=True)

    single = _load_jsonl(eval_dir / "single_turn.jsonl")
    multi = _load_jsonl(eval_dir / "multi_turn.jsonl")
    negatives = _load_jsonl(eval_dir / "negatives.jsonl")

    items: list[dict] = []

    for entry in single:
        result = pipeline.ask(entry["question"], session_id=f"eval_{entry['item_id']}")
        items.append(
            _record(
                entry["item_id"], "single_turn", entry["lang"], entry["question"],
                result, "answered", entry["gold_chunk_ids"],
            )
        )

    for conversation in multi:
        session_id = f"eval_{conversation['item_id']}"
        for index, turn in enumerate(conversation["turns"], start=1):
            result = pipeline.ask(turn["question"], session_id=session_id)
            # 追问本身没有内容词（"还有呢？"），评判用改写后的有效问题
            items.append(
                _record(
                    f"{conversation['item_id']}_t{index}", "multi_turn", conversation["lang"],
                    result.rewritten_question if turn["requires_rewrite"] else turn["question"],
                    result, "answered", turn["gold_chunk_ids"], turn["requires_rewrite"],
                )
            )

    for entry in negatives:
        result = pipeline.ask(entry["question"], session_id=f"eval_{entry['item_id']}")
        items.append(
            _record(
                entry["item_id"], entry["subset"], entry["lang"], entry["question"],
                result, "refused", [],
            )
        )

    # ---------- 评判 ----------
    rule_judge = RuleBasedJudge()
    for item in items:
        _apply_rule_judge(rule_judge, item)
    judge_stats = {"judged": 0, "failures": 0}
    if config.eval.judge == "llm":
        judge_stats = LLMJudge(config).apply(items)

    # ---------- 缓存探针 ----------
    probe_count = max(1, int(len(single) * cache_probe_ratio)) if cache_probe_ratio else 0
    probe_hits = 0
    for entry in single[:probe_count]:
        result = pipeline.ask(entry["question"], session_id=f"probe_{entry['item_id']}")
        if result.cache_hit:
            probe_hits += 1
    cache_hit_rate = probe_hits / probe_count if probe_count else 0.0

    metrics = aggregate_metrics(items, config, cache_hit_rate)
    metrics["judge_stats"] = judge_stats

    with open(report_dir / f"items_{config.app.config_version}.jsonl", "w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    (report_dir / f"eval_{config.app.config_version}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metrics


def aggregate_metrics(items: list[dict], config: Config, cache_hit_rate: float = 0.0) -> dict:
    """从条目聚合指标（与管线解耦，便于只重判不重跑）。"""
    retrieval_items = [i for i in items if i["subset"] in ("single_turn", "multi_turn")]
    answered_intent = [i for i in items if i["subset"] == "single_turn"]
    negative_items = [i for i in items if i["expected_status"] == "refused"]
    faithfulness = [
        i["faithfulness"]
        for i in retrieval_items
        if i["status"] == "answered" and i["faithfulness"] is not None
    ]
    latencies = [i["latency_ms"] for i in items]
    prompt_tokens = sum(i["token_usage"].get("prompt_tokens", 0) for i in items)
    completion_tokens = sum(i["token_usage"].get("completion_tokens", 0) for i in items)
    total_cost = sum(i["cost_usd"] for i in items)
    rewrite_turns = [i for i in retrieval_items if i.get("requires_rewrite")]

    return {
        "config_version": config.app.config_version,
        "config_fingerprint": config.fingerprint(),
        "retrieval_mode": config.retrieval.mode,
        "fusion": config.retrieval.fusion,
        "vector_weight": config.retrieval.vector_weight,
        "rerank_enabled": config.rerank.enabled,
        "rerank_backend": config.rerank.backend if config.rerank.enabled else None,
        "embedding_backend": config.embedding.backend,
        "generation_backend": config.generation.backend,
        "generation_model": config.generation.model,
        "judge": config.eval.judge,
        "items": len(items),
        "context_precision_at_5": round(
            statistics.mean(i["context_precision"] for i in retrieval_items), 4
        ),
        "recall_at_5": round(statistics.mean(i["recall_at_5"] for i in retrieval_items), 4),
        "mrr": round(statistics.mean(i["reciprocal_rank"] for i in retrieval_items), 4),
        "faithfulness": round(statistics.mean(faithfulness), 4) if faithfulness else 0.0,
        "answer_compliance": round(statistics.mean(i["compliance"]["compliance"] for i in items), 4),
        "style_consistency": round(statistics.mean(i["style"]["style"] for i in items), 4),
        **refusal_metrics(
            (sum(1 for i in negative_items if i["status"] == "refused") / len(negative_items))
            if negative_items
            else 0.0,
            (sum(1 for i in answered_intent if i["status"] == "answered") / len(answered_intent))
            if answered_intent
            else 0.0,
        ),
        "latency_p50_ms": round(percentile(latencies, 0.5), 2),
        "latency_p90_ms": round(percentile(latencies, 0.9), 2),
        "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        "retrieve_p95_ms": round(percentile([i["retrieve_ms"] for i in items], 0.95), 2),
        "generate_p95_ms": round(
            percentile([i["generate_ms"] for i in items if i["generate_ms"]], 0.95), 2
        ),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd_total": round(total_cost, 6),
        "cost_usd_per_1k_calls": round(total_cost / len(items) * 1000, 4),
        "cache_hit_rate": round(cache_hit_rate, 4),
        "rewrite_turns": len(rewrite_turns),
        "rewrite_turn_precision": round(
            statistics.mean(i["context_precision"] for i in rewrite_turns), 4
        )
        if rewrite_turns
        else 0.0,
        "refusals_by_reason": _count_reasons(items),
    }


def _count_reasons(items: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        if item["status"] == "refused" and item["refusal_reason"]:
            counts[item["refusal_reason"]] = counts.get(item["refusal_reason"], 0) + 1
    return counts
