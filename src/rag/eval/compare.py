"""三配置对比报告：不只要有数字，还要有结论。"""

from __future__ import annotations

import json
from pathlib import Path

COLUMNS = (
    ("context_precision_at_5", "Context Precision@5", "{:.4f}"),
    ("recall_at_5", "Recall@5", "{:.4f}"),
    ("mrr", "MRR", "{:.4f}"),
    ("faithfulness", "Faithfulness", "{:.4f}"),
    ("answer_compliance", "Answer Compliance", "{:.4f}"),
    ("style_consistency", "Style Consistency", "{:.4f}"),
    ("refusal_appropriateness", "Refusal Appropriateness", "{:.4f}"),
    ("correct_answer_rate", "Correct Answer Rate", "{:.4f}"),
    ("latency_p50_ms", "P50 (ms)", "{:.1f}"),
    ("latency_p95_ms", "P95 (ms)", "{:.1f}"),
    ("cost_usd_per_1k_calls", "Cost / 1k calls (USD)", "{:.4f}"),
)


def write_comparison(results: list[dict], report_dir: Path = Path("reports")) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "comparison.md"
    lines = [
        "# 三配置对比报告",
        "",
        "> English version: [comparison.en.md](comparison.en.md)",
        "",
    ]
    lines.append("| 指标 | " + " | ".join(r["config_version"] for r in results) + " |")
    lines.append("|" + "---|" * (len(results) + 1))
    for key, label, fmt in COLUMNS:
        cells = [fmt.format(r.get(key, 0.0)) for r in results]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("> 延迟与成本为单机单实例实测；价格为配置中的示例单价，需替换为官方当期价。")
    lines.append("> 评测时缓存已关闭，避免缓存命中跳过检索、掩盖真实检索质量。")
    lines.append("")

    best_precision = max(results, key=lambda r: r["context_precision_at_5"])
    baseline = results[0]
    lines.append("## 结论")
    lines.append("")
    lines.append(
        f"1. Context Precision 最优配置为 **{best_precision['config_version']}**"
        f"（{best_precision['context_precision_at_5']:.4f}），"
        f"相对 {baseline['config_version']}（{baseline['context_precision_at_5']:.4f}）"
        f"提升 {(best_precision['context_precision_at_5'] - baseline['context_precision_at_5']) * 100:.2f} 个百分点。"
    )
    fastest = min(results, key=lambda r: r["latency_p95_ms"])
    lines.append(
        f"2. P95 延迟最低的是 **{fastest['config_version']}**（{fastest['latency_p95_ms']:.1f} ms）。"
        "若引入重排后延迟上升，需要靠超时降级与缓存抵消。"
    )
    lines.append(
        "3. 选择建议：以 Context Precision 与 Faithfulness 的联合最优为准，"
        "在延迟预算（P90 ≤ 10s）内优先保留重排；超出预算则回退到次优配置。"
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (report_dir / "comparison.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
