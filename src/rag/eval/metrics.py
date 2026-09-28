"""指标计算。

所有指标口径与 METRIC-DEFINITIONS.md 一致，实现即文档，
避免"报告里写的定义"与"代码里算的东西"不一致。
"""

from __future__ import annotations


def context_precision(retrieved: list[str], gold: list[str], k: int | None = None) -> float:
    """排序加权 Context Precision：命中越靠前得分越高。"""
    if not gold:
        return 0.0
    considered = retrieved[:k] if k else retrieved
    if not considered:
        return 0.0
    gold_set = set(gold)
    hits = 0
    total = 0.0
    for index, chunk_id in enumerate(considered, start=1):
        if chunk_id in gold_set:
            hits += 1
            total += hits / index
    return total / len(gold_set) if gold_set else 0.0


def recall_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    if not gold:
        return 0.0
    gold_set = set(gold)
    return len(gold_set & set(retrieved[:k])) / len(gold_set)


def reciprocal_rank(retrieved: list[str], gold: list[str]) -> float:
    gold_set = set(gold)
    for index, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in gold_set:
            return 1.0 / index
    return 0.0


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def refusal_metrics(correct_refusal_rate: float, correct_answer_rate: float) -> dict:
    """双向拒答指标：只报单向会被"全部拒答"策略刷满。"""
    if correct_refusal_rate + correct_answer_rate == 0:
        f1 = 0.0
    else:
        f1 = 2 * correct_refusal_rate * correct_answer_rate / (correct_refusal_rate + correct_answer_rate)
    return {
        "correct_refusal_rate": round(correct_refusal_rate, 4),
        "correct_answer_rate": round(correct_answer_rate, 4),
        "refusal_appropriateness": round(f1, 4),
    }
