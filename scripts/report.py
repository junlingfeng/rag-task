#!/usr/bin/env python
"""运维报告：从结构化日志聚合出需求 FR4 要求的全部字段。

这是"日志字段字典决定报告能力"的验证：报告里的每个数字都直接来自日志，
不需要额外埋点，也不需要数据库。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.eval.metrics import percentile  # noqa: E402


def load_requests(log_path: Path, config_version: str | None) -> list[dict]:
    records = []
    if not log_path.exists():
        return records
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") != "request":
            continue
        if config_version and record.get("config_version") != config_version:
            continue
        records.append(record)
    return records


def build_report(records: list[dict]) -> dict:
    if not records:
        return {}
    latencies = [float(r.get("latency_ms", 0.0)) for r in records]
    total = len(records)
    refusals = [r for r in records if r.get("answer_status") == "refused"]
    refusal_reasons: dict[str, int] = defaultdict(int)
    for record in refusals:
        refusal_reasons[record.get("refusal_reason") or "unknown"] += 1

    prompt_tokens = sum(int(r.get("prompt_tokens", 0)) for r in records)
    completion_tokens = sum(int(r.get("completion_tokens", 0)) for r in records)
    cost = sum(float(r.get("cost_usd", 0.0)) for r in records)
    cache_hits = sum(1 for r in records if r.get("cache_hit"))
    answered = [r for r in records if r.get("answer_status") == "answered"]
    supported = [float(r.get("support_score", 0.0)) for r in answered]
    rerank_timeouts = sum(1 for r in records if r.get("rerank_timeout"))
    # 在线合规率代理指标：从日志字段直接计算，用于无需金标准数据时的持续监控。
    # 离线评测中的 exact 合规率（含人工/judge 判定）见 reports/eval_*.json。
    compliant = sum(
        1
        for r in answered
        if float(r.get("support_score", 0.0)) >= 0.30 and r.get("citation_ids")
    )
    compliance_proxy = compliant / len(answered) if answered else 0.0

    return {
        "requests": total,
        "p50_latency_ms": round(percentile(latencies, 0.5), 2),
        "p90_latency_ms": round(percentile(latencies, 0.9), 2),
        "p95_latency_ms": round(percentile(latencies, 0.95), 2),
        "latency_max_ms": round(max(latencies), 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "avg_prompt_tokens": round(prompt_tokens / total, 1),
        "avg_completion_tokens": round(completion_tokens / total, 1),
        "cache_hit_rate": round(cache_hits / total, 4),
        "refusal_rate": round(len(refusals) / total, 4),
        "refusal_by_reason": dict(refusal_reasons),
        "answer_rate": round(len(answered) / total, 4),
        "mean_support_score": round(sum(supported) / len(supported), 4) if supported else 0.0,
        "answer_compliance_rate": round(compliance_proxy, 4),
        "answer_compliance_source": "online_proxy(support_score>=0.30 & has_citation)",
        "cost_usd_total": round(cost, 6),
        "cost_usd_per_1k_calls": round(cost / total * 1000, 4),
        "rerank_timeout_rate": round(rerank_timeouts / total, 4),
        "config_versions": sorted({r.get("config_version", "") for r in records}),
    }


def write_report(report: dict, report_dir: Path, config_version: str | None) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix = config_version or "all"
    text_path = report_dir / f"ops_report_{suffix}.txt"
    csv_path = report_dir / f"ops_report_{suffix}.csv"

    lines = [
        "运维报告 (Minimal Operations Report)",
        f"配置版本: {suffix}",
        "",
        f"请求总数: {report['requests']}",
        f"P50 延迟: {report['p50_latency_ms']} ms",
        f"P90 延迟: {report['p90_latency_ms']} ms",
        f"P95 延迟: {report['p95_latency_ms']} ms",
        f"最大延迟: {report['latency_max_ms']} ms",
        f"Token 用量: prompt={report['prompt_tokens']} completion={report['completion_tokens']} "
        f"total={report['total_tokens']}",
        f"平均 Token: prompt={report['avg_prompt_tokens']} completion={report['avg_completion_tokens']}",
        f"每千次调用成本: {report['cost_usd_per_1k_calls']} USD",
        f"缓存命中率: {report['cache_hit_rate']}",
        f"拒答率: {report['refusal_rate']}（未作答占比，按原因细分见下）",
        f"拒答原因分布: {json.dumps(report['refusal_by_reason'], ensure_ascii=False)}",
        f"作答率: {report['answer_rate']}",
        f"平均接地分数: {report['mean_support_score']}",
        f"答案合规率(在线代理): {report['answer_compliance_rate']}",
        f"重排超时率: {report['rerank_timeout_rate']}",
    ]
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for key, value in report.items():
            writer.writerow([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
    return text_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="logs/rag.jsonl")
    parser.add_argument("--config-version", default=None)
    parser.add_argument("--report-dir", default="reports")
    args = parser.parse_args()

    records = load_requests(Path(args.log), args.config_version)
    report = build_report(records)
    if not report:
        print("没有匹配的请求日志")
        return
    text_path = write_report(report, Path(args.report_dir), args.config_version)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[report] 已写入 {text_path}")


if __name__ == "__main__":
    main()
