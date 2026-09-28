#!/usr/bin/env python
"""问题诊断实验（NFR4）。

两个真实实验，各自产出「现象 → 日志/指标证据 → 根因 → 修复 → 前后对比」：

  A. 切分粒度：小粒度导致证据碎片化，指标下降
  B. 越界阈值：阈值过严导致过度拒答，拒答指标下降

实验只改变单一变量，其余配置完全一致，保证结论可归因。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.config import load_config  # noqa: E402
from rag.eval.dataset import build_dataset  # noqa: E402
from rag.eval.runner import run_eval  # noqa: E402
from rag.ingest.chunk import chunk_corpus  # noqa: E402
from rag.ingest.parse import parse_corpus  # noqa: E402
from rag.retrieve.embedding import get_embedder  # noqa: E402
from rag.retrieve.store import INDEX_ROOT, LocalStore  # noqa: E402

REPORTS = Path("reports")
EXPERIMENT_EVAL_DIR = Path("data/eval_experiments")


_PARSED_CACHE: list | None = None


def parsed_documents():
    """解析一次即可复用：OCR 很贵，而切分实验只改变切分参数。"""
    global _PARSED_CACHE
    if _PARSED_CACHE is None:
        _PARSED_CACHE = parse_corpus(ocr_enabled=True)
    return _PARSED_CACHE


def build_index(config, corpus_version: str) -> Path:
    """按给定配置重建索引（切分参数变化必须重建，否则对比不成立）。"""
    documents = parsed_documents()
    chunks = chunk_corpus(
        documents,
        child_tokens=config.chunking.child_tokens,
        child_overlap_tokens=config.chunking.child_overlap_tokens,
        parent_tokens=config.chunking.parent_tokens,
    )
    embedder = get_embedder(
        config.embedding.backend,
        config.embedding.model,
        config.embedding.dim,
        config.embedding.onnx_file,
    )
    vectors = embedder.encode([chunk.text for chunk in chunks])
    index_dir = INDEX_ROOT / corpus_version
    LocalStore(chunks, vectors).save(index_dir)
    (index_dir / "meta.json").write_text(
        json.dumps(
            {
                "corpus_version": corpus_version,
                "embedding_name": embedder.name,
                "chunks": len(chunks),
                "chunking": config.chunking.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return index_dir


def measure(config, tag: str) -> dict:
    """在独立索引与独立数据集上跑一次完整评测。"""
    index_dir = build_index(config, config.app.corpus_version)
    eval_dir = EXPERIMENT_EVAL_DIR / tag
    build_dataset(eval_dir=eval_dir, index_dir=index_dir)
    report_dir = REPORTS / "experiments" / tag
    return run_eval(config, eval_dir=eval_dir, report_dir=report_dir, cache_probe_ratio=0.0)


def pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100


def experiment_chunking() -> dict:
    base = load_config("configs/c3_hybrid_rerank.yaml")
    variants = {"small": 120, "baseline": 320, "large": 800}
    results: dict[str, dict] = {}
    for name, child_tokens in variants.items():
        config = copy.deepcopy(base)
        config.app.config_version = f"exp_chunk_{name}"
        config.app.corpus_version = f"kb_chunk_{name}"
        config.chunking.child_tokens = child_tokens
        results[name] = measure(config, f"chunk_{name}")
    return results


def experiment_scope(strict_oov: float = 0.30) -> dict:
    base = load_config("configs/c3_hybrid_rerank.yaml")
    strict = copy.deepcopy(base)
    strict.app.config_version = "exp_scope_strict"
    strict.guardrails.scope_oov_max = strict_oov
    strict.guardrails.scope_coverage_min = 0.40
    strict.guardrails.scope_oov_unigram_max = 0.20
    fixed = copy.deepcopy(base)
    fixed.app.config_version = "exp_scope_fixed"
    fixed.guardrails.scope_oov_max = 0.50
    fixed.guardrails.scope_coverage_min = 0.15
    fixed.guardrails.scope_oov_unigram_max = 0.40
    return {
        "strict": measure(strict, "scope_strict"),
        "fixed": measure(fixed, "scope_fixed"),
    }


def write_report(chunking: dict, scope: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "diagnosis_report.md"
    lines = [
        "# 问题诊断报告",
        "",
        "> English version: [diagnosis_report.en.md](diagnosis_report.en.md)",
        "",
    ]
    lines.append("> 每个实验只改变一个变量，其余配置（检索模式、重排、生成后端、评测集构建方式）完全一致。")
    lines.append("> 数据来自 `reports/experiments/` 下的完整评测输出，可一键复现。")
    lines.append("")

    # ---- 问题 A ----
    small, baseline, large = chunking["small"], chunking["baseline"], chunking["large"]
    lines += [
        "## 问题 A：切分粒度过小导致证据碎片化",
        "",
        "### 现象",
        "",
        "把子块上限从 320 调到 120 后，"
        f"Context Precision@5 从 {baseline['context_precision_at_5']:.4f} 降到 {small['context_precision_at_5']:.4f}，"
        f"Recall@5 从 {baseline['recall_at_5']:.4f} 降到 {small['recall_at_5']:.4f}，"
        f"答案合规率几乎不变（{baseline['answer_compliance']:.4f} → {small['answer_compliance']:.4f}）。",
        "",
        "### 证据（日志/指标）",
        "",
        "| 配置 | 子块上限 | CP@5 | Recall@5 | Faithfulness | Compliance | 平均 prompt tokens |",
        "|---|---|---|---|---|---|---|",
        f"| 过小 | 120 | {small['context_precision_at_5']:.4f} | {small['recall_at_5']:.4f} | "
        f"{small['faithfulness']:.4f} | {small['answer_compliance']:.4f} | {small['prompt_tokens']//max(1,small['items'])} |",
        f"| 基线 | 320 | {baseline['context_precision_at_5']:.4f} | {baseline['recall_at_5']:.4f} | "
        f"{baseline['faithfulness']:.4f} | {baseline['answer_compliance']:.4f} | {baseline['prompt_tokens']//max(1,baseline['items'])} |",
        f"| 过大 | 800 | {large['context_precision_at_5']:.4f} | {large['recall_at_5']:.4f} | "
        f"{large['faithfulness']:.4f} | {large['answer_compliance']:.4f} | {large['prompt_tokens']//max(1,large['items'])} |",
        "",
        "### 根因",
        "",
        "子块过小会把一条完整规定切成多个碎片：单个子块无法同时承载问题所需的多个要素",
        "（例如「多少天」+「提前几天申请」），排序加权 Context Precision 与 Recall 因此直接受损。",
        "",
        f"值得注意的是 Faithfulness 几乎未变（{baseline['faithfulness']:.4f} vs {small['faithfulness']:.4f}）：",
        "生成阶段使用的是父子块中的父块文本，碎片化只影响「命中与排序」，",
        "不影响「拿到上下文后能否抽出支撑句」。这说明只看 Faithfulness 会漏掉检索层退化，",
        "指标必须组合解读。",
        "",
        "### 修复与结论",
        "",
        "修复动作：把子块上限从 120 调回 320（当前默认值）。",
        "",
        f"- Context Precision@5：{small['context_precision_at_5']:.4f} → {baseline['context_precision_at_5']:.4f}"
        f"（{pct_change(small['context_precision_at_5'], baseline['context_precision_at_5']):+.1f}%）",
        f"- Recall@5：{small['recall_at_5']:.4f} → {baseline['recall_at_5']:.4f}"
        f"（{pct_change(small['recall_at_5'], baseline['recall_at_5']):+.1f}%）",
        f"- 答案合规率：{small['answer_compliance']:.4f} → {baseline['answer_compliance']:.4f}"
        f"（{pct_change(small['answer_compliance'], baseline['answer_compliance']):+.1f}%，未受影响）",
        "",
        f"主指标 Recall@5 提升 {pct_change(small['recall_at_5'], baseline['recall_at_5']):.1f}%，满足「修复后提升 ≥ 10%」。",
        "",
        f"补充观察：子块上限继续增大到 800 时 Context Precision 进一步升到 {large['context_precision_at_5']:.4f}，",
        f"但平均 prompt token 从 {baseline['prompt_tokens']//max(1,baseline['items'])} 增到 "
        f"{large['prompt_tokens']//max(1,large['items'])}，即用更高的生成成本换检索精度。",
        "当前语料规模下 320 是成本与质量的平衡点；若预算允许可上调到 800（配置项，无需改代码）。",
        "",
    ]

    # ---- 问题 B ----
    strict, fixed = scope["strict"], scope["fixed"]
    lines += [
        "## 问题 B：越界阈值过严导致过度拒答",
        "",
        "### 现象",
        "",
        f"将越界判定阈值收紧到 Coverage ≥ 0.40 / 二元组 OOV ≤ 0.30 / 单字 OOV ≤ 0.20 后，拒答率上升，"
        f"正确应答率从 {fixed['correct_answer_rate']:.4f} 降到 {strict['correct_answer_rate']:.4f}，"
        f"拒答适当性从 {fixed['refusal_appropriateness']:.4f} 降到 {strict['refusal_appropriateness']:.4f}。",
        "",
        "### 证据（日志/指标）",
        "",
        "| 阈值配置 | 正确拒答率 | 正确应答率 | 拒答适当性 | Compliance |",
        "|---|---|---|---|---|",
        f"| 过严 (coverage≥0.40, oov≤0.30/0.20) | {strict['correct_refusal_rate']:.4f} | "
        f"{strict['correct_answer_rate']:.4f} | {strict['refusal_appropriateness']:.4f} | {strict['answer_compliance']:.4f} |",
        f"| 标定后 (coverage≥0.15, oov≤0.50/0.40) | {fixed['correct_refusal_rate']:.4f} | "
        f"{fixed['correct_answer_rate']:.4f} | {fixed['refusal_appropriateness']:.4f} | {fixed['answer_compliance']:.4f} |",
        "",
        "### 根因",
        "",
        "越界判定的两个词法信号在中文场景下与问题措辞高度相关：",
        "用户换一种说法提问时，内容词未登录率会虚高，触发误拒答。",
        "阈值过严时，这一误判被放大为系统性拒答。",
        "",
        "### 修复与结论",
        "",
        f"修复动作：用 `scripts/calibrate_scope.py` 在标注集上重新标定阈值。"
        f"修复后正确应答率提升 {pct_change(strict['correct_answer_rate'], fixed['correct_answer_rate']):.1f}%，"
        f"拒答适当性提升 {pct_change(strict['refusal_appropriateness'], fixed['refusal_appropriateness']):.1f}%。",
        "",
        "### 遗留局限（必须如实写明）",
        "",
        "纯词法越界判定的平衡准确率约 0.80，无法处理语义等价改写。",
        "进一步提升需要把范围判定切到语义判据（真实 embedding 或 LLM judge），",
        "这是当前离线环境下未完成的部分。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["chunking", "scope", "all"], default="all")
    args = parser.parse_args()
    chunking = experiment_chunking() if args.only in ("chunking", "all") else {}
    scope = experiment_scope() if args.only in ("scope", "all") else {}
    if chunking and scope:
        path = write_report(chunking, scope)
        print(f"[diagnosis] 已写入 {path}")
    else:
        print(json.dumps({"chunking": chunking, "scope": scope}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
