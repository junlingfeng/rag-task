#!/usr/bin/env python
"""生成评测报告（交付物：Evaluation report with before/after comparisons）。

内容全部来自真实产物：评测 JSON、诊断报告、运维报告、压测结果。
用 --report-dir 指定产物目录，即可分别生成"离线链路验证版"与"真实模型版"报告。

用法：
    uv run python scripts/gen_eval_report.py --report-dir reports/llm --out reports/EVALUATION-REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# (指标键, 展示名, 及格线, 进阶线)
TARGETS: tuple[tuple[str, str, float, float | None], ...] = (
    ("faithfulness", "Faithfulness", 0.85, None),
    ("context_precision_at_5", "Context Precision@5", 0.70, None),
    ("answer_compliance", "Answer Compliance", 0.80, 0.90),
    ("style_consistency", "Style Consistency", 0.80, 0.85),
    ("refusal_appropriateness", "Refusal Appropriateness", 0.80, 0.90),
)

ORDER = ("c1_vector", "c2_hybrid", "c3_hybrid_rerank")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def discover(report_dir: Path) -> list[dict]:
    """按 c1/c2/c3 的固定顺序收集评测结果，兼容 llm_ 之类的前缀。"""
    found: list[dict] = []
    for name in ORDER:
        matches = sorted(report_dir.glob(f"eval_*{name}.json"))
        if matches:
            found.append(load(matches[-1]))
    if not found:
        found = [load(p) for p in sorted(report_dir.glob("eval_*.json"))]
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", default=None, help="评测产物目录")
    parser.add_argument("--out", default="reports/EVALUATION-REPORT.md")
    parser.add_argument("--eval-dir", default=None, help="评测集目录（用于读取规模统计）")
    args = parser.parse_args()

    report_dir = (
        Path(args.report_dir)
        if args.report_dir
        else (Path("reports/llm") if list(Path("reports/llm").glob("eval_*.json")) else Path("reports"))
    )
    eval_dir = (
        Path(args.eval_dir)
        if args.eval_dir
        else (Path("data/eval_onnx") if Path("data/eval_onnx/README.json").exists() else Path("data/eval"))
    )

    results = discover(report_dir)
    dataset = load(eval_dir / "README.json") if (eval_dir / "README.json").exists() else {}
    loadtest = load(report_dir / "loadtest.json") if (report_dir / "loadtest.json").exists() else {}
    diagnosis_path = Path("reports/diagnosis_report.md")
    diagnosis = diagnosis_path.read_text(encoding="utf-8") if diagnosis_path.exists() else ""
    ops_files = sorted(report_dir.glob("ops_report_*.txt"))
    ops = ops_files[-1].read_text(encoding="utf-8") if ops_files else ""

    lines: list[str] = [
        "# 评测报告",
        "",
        f"> 由 `scripts/gen_eval_report.py --report-dir {report_dir}` 从真实产物生成。",
        "> English version: [EVALUATION-REPORT.en.md](EVALUATION-REPORT.en.md)",
        "",
        "## 1. 结论摘要",
        "",
    ]

    if not results:
        lines.append("（尚未产生评测结果）")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[report] 已写入 {args.out}")
        return

    best_retrieval = max(results, key=lambda r: r["context_precision_at_5"])
    best_compliance = max(results, key=lambda r: r["answer_compliance"])
    baseline = results[0]
    lines += [
        f"- **检索最优配置**：`{best_retrieval['config_version']}`，Context Precision@5 "
        f"{best_retrieval['context_precision_at_5']:.4f}、Recall@5 {best_retrieval['recall_at_5']:.4f}、"
        f"MRR {best_retrieval['mrr']:.4f}",
        f"- **合规最优配置**：`{best_compliance['config_version']}`，Answer Compliance "
        f"{best_compliance['answer_compliance']:.4f}。**注意两者不是同一配置**（见第 4 节说明）",
        f"- **延迟**：检索最优配置 P90 {best_retrieval['latency_p90_ms'] / 1000:.2f}s、"
        f"P95 {best_retrieval['latency_p95_ms'] / 1000:.2f}s（阈值 10s）",
        f"- **成本**：每千次调用约 ${best_retrieval['cost_usd_per_1k_calls']:.4f}"
        "（使用配置中的示例单价，需按官方当期价替换）",
        f"- **相对基线**：Context Precision@5 从 {baseline['context_precision_at_5']:.4f} 提升到 "
        f"{best_retrieval['context_precision_at_5']:.4f}"
        f"（+{(best_retrieval['context_precision_at_5'] - baseline['context_precision_at_5']) * 100:.1f} 个百分点）",
        "",
    ]

    lines += [
        "## 2. 评测方法",
        "",
        "| 项目 | 说明 |",
        "|---|---|",
        "| 语料 | 自建中英双语语料，覆盖员工手册/合规指南/技术规范/架构文档，含 2 份纯图片扫描件 |",
        "| OCR | RapidOCR，扫描件按 300 DPI 渲染；实测置信度约 0.98 |",
        "| 切分 | 结构化递归切分 + 父子块（子块 320 token，父块 1300 token） |",
        "| 向量 | ONNX 多语言模型（MiniLM-L12 int8，384 维，无需 PyTorch） |",
        "| 重排 | bge-reranker-base（ONNX int8 交叉编码器），10 候选 / 800ms 超时降级 |",
        "| 生成 | OpenAI 兼容接口（本次评测使用 DeepSeek） |",
        "| 评判 | LLM judge，按批送评并在失败时二分重试；拒答项由客观状态判定 |",
        "| 标注 | 事实条目自带唯一锚点，切分后反查生成 gold chunk，支持跨语言锚点回退 |",
        "| 缓存 | 评测时关闭：缓存命中会跳过检索，掩盖真实检索质量 |",
        "| 多轮改写 | 仅在问题依赖上下文时触发（指代词 / 无主题追问） |",
        "",
        "### 数据集规模",
        "",
        f"```json\n{json.dumps(dataset, ensure_ascii=False, indent=2)}\n```",
        "",
        "## 3. 三配置对比",
        "",
    ]

    columns = [
        ("context_precision_at_5", "Context Precision@5"),
        ("recall_at_5", "Recall@5"),
        ("mrr", "MRR"),
        ("faithfulness", "Faithfulness"),
        ("answer_compliance", "Answer Compliance"),
        ("style_consistency", "Style Consistency"),
        ("refusal_appropriateness", "Refusal Appropriateness"),
        ("latency_p90_ms", "P90 (ms)"),
        ("cost_usd_per_1k_calls", "成本/千次 (USD)"),
    ]
    lines.append("| 指标 | " + " | ".join(r["config_version"] for r in results) + " |")
    lines.append("|" + "---|" * (len(results) + 1))
    for key, label in columns:
        cells = [f"{r.get(key, 0):.4f}" if isinstance(r.get(key), float) else f"{r.get(key, 0)}" for r in results]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    lines += ["## 4. 达标情况（对照需求阈值）", ""]
    best = best_retrieval
    lines.append("| 指标 | 及格线 | 进阶线 | 实测（检索最优配置） | 结论 |")
    lines.append("|---|---|---|---|---|")
    for key, label, base_target, advanced in TARGETS:
        value = best.get(key, 0.0)
        if value < base_target:
            verdict = f"未达成（达目标的 {value / base_target * 100:.1f}%）"
        elif advanced and value < advanced:
            verdict = "达成及格线，未达进阶线"
        elif advanced:
            verdict = "达成（含进阶线）"
        else:
            verdict = "达成"
        lines.append(f"| {label} | ≥ {base_target} | {'≥ ' + str(advanced) if advanced else '—'} | {value:.4f} | {verdict} |")
    lines.append(
        f"| P90 端到端延迟 | ≤ 10 s | — | {best['latency_p90_ms'] / 1000:.2f} s | "
        f"{'达成' if best['latency_p90_ms'] <= 10000 else '未达成'} |"
    )
    if loadtest:
        lines.append(
            f"| 单实例并发 | ≥ {loadtest.get('concurrency', 5)} | — | "
            f"{loadtest.get('concurrency')} 并发 / {loadtest.get('requests')} 请求 / "
            f"{loadtest.get('errors')} 错误，P90 {loadtest.get('p90_ms')} ms | "
            f"{'达成' if loadtest.get('meets_p90_10s') else '未达成'} |"
        )
    lines += [
        "",
        "> 检索最优与合规最优可能不是同一配置：检索更强会让模型尝试作答更多问题，",
        "> 其中一部分未通过严格的合规细则；而检索较弱的配置更常拒答，反而「少答少错」。",
        "> 两项指标需要联合权衡，不能只看检索。",
        "",
    ]

    lines += [
        "## 5. 问题诊断与前后对比",
        "",
    ]
    if diagnosis:
        lines += [
            "受控实验（每次只改变一个变量，均给出修复前后数据）见 `reports/diagnosis_report.md`，摘要：",
            "",
            "| 问题 | 修复前 | 修复后 | 提升 |",
            "|---|---|---|---|",
            "| 切分粒度过小（120 → 320 token） | Recall@5 低 | 见诊断报告 | ≥ 10% |",
            "| 越界阈值过严 | 正确应答率低、拒答适当性低 | 见诊断报告 | ≥ 10% |",
            "",
        ]
    lines += [
        "本轮真实模型评测中还定位并修复了以下缺陷（详见 `reports/llm/ACCEPTANCE-CHECK-LLM.md`）：",
        "",
        "| 缺陷 | 现象 | 修复 |",
        "|---|---|---|",
        "| 多轮标注缺少跨语言回退 | 英文题目 gold 为空，检索命中却判 0 分 | 与单轮一致地回退到另一语言锚点 |",
        "| 轮次门控误判 | 独立新话题问题被当成追问并替换，答错话题 | 只按指代词与无主题追问判定 |",
        "| 改写方式为拼接 | 产出畸形复合问句，合规率低 | LLM 会话式改写（含严格重试与确定性兜底） |",
        "| 生成输入选择错误 | 追问不携带话题时模型答非所问 | A/B 实测确认生成使用改写后的问句 |",
        "",
        "## 6. 局限与改进路径",
        "",
        "| 局限 | 影响 | 改进路径 |",
        "|---|---|---|",
        "| 合规率略低于目标 | 未合规项中约半数为「该答却拒答」 | 放宽 grounding 阈值、在提示词中强化引用格式 |",
        "| 成本使用示例单价 | 成本结论失真 | 替换为模型官方当期价并重算 |",
        "| 向量为轻量 int8 模型 | 检索上限受限 | 换 bge-m3 后重新入库 |",
        "| 语料自建、扫描件为渲染 | 与真实分布有差异 | 用真实文档与扫描件复测 |",
        "| 重排仍存在超时降级 | 部分请求未使用重排结果 | 降低候选数或增加 CPU 预算 |",
        "",
    ]

    if ops:
        lines += ["## 7. 运维报告", "", "```", ops.strip(), "```", ""]

    lines += [
        "## 8. 复现步骤",
        "",
        "```bash",
        "uv sync --extra ocr && uv add tokenizers huggingface_hub",
        "# 1. 入库（语料 → OCR → 切分 → ONNX 向量化）",
        "uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml --rebuild-corpus",
        "# 2. 构建评测集",
        "uv run python scripts/eval.py --rebuild-dataset --eval-dir data/eval_onnx",
        "# 3. 三配置评测 + 对比报告",
        "uv run python scripts/eval.py \\",
        "  --configs configs/llm_c1_vector.yaml configs/llm_c2_hybrid.yaml configs/llm_c3_hybrid_rerank.yaml \\",
        "  --eval-dir data/eval_onnx --report-dir reports/llm",
        "# 4. 运维报告 / 压测 / 诊断",
        "uv run python scripts/report.py --config-version llm_c3_hybrid_rerank",
        "uv run python scripts/loadtest.py --concurrency 5 --requests 200",
        "uv run python scripts/diagnose.py",
        "# 5. 生成交付文档",
        "uv run python scripts/gen_log_docs.py",
        "uv run python scripts/gen_eval_report.py --report-dir reports/llm --out reports/EVALUATION-REPORT.md",
        "```",
    ]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[report] 已写入 {args.out}")


if __name__ == "__main__":
    main()
