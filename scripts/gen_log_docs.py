#!/usr/bin/env python
"""生成日志字段字典与样例日志（交付物要求）。

字段表直接来自 rag.observability.LOG_FIELD_DICTIONARY，
样例日志直接从真实日志文件里截取，保证文档与实际实现不会漂移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.observability import LOG_FIELD_DICTIONARY  # noqa: E402


def main() -> None:
    log_path = Path("logs/rag.jsonl")
    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 日志字段字典与样例日志",
        "",
        "> 本文件由 `scripts/gen_log_docs.py` 从代码常量与真实日志生成，请勿手工编辑。",
        "> English version: [LOG-FIELD-DICTIONARY.en.md](LOG-FIELD-DICTIONARY.en.md)",
        "",
        "## 1. 字段字典",
        "",
        "| 字段 | 类型 | 说明 |",
        "|---|---|---|",
    ]
    for name, type_name, description in LOG_FIELD_DICTIONARY:
        lines.append(f"| `{name}` | {type_name} | {description} |")

    lines += [
        "",
        "## 2. 日志结构",
        "",
        "每次请求产生两类记录：",
        "",
        "- `event=span`：单个阶段的埋点（rewrite / cache / retrieve / guardrail / generate / postprocess），",
        "  每条都带 `trace_id` 与 `stage`，用于定位耗时与阶段行为。",
        "- `event=request`：一次请求的汇总记录，运维报告的全部指标都来自这类记录。",
        "",
        "## 3. 样例日志",
        "",
    ]

    if log_path.exists():
        raw = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        spans = [r for r in raw if r.get("event") == "span"][-4:]
        requests = [r for r in raw if r.get("event") == "request"]
        samples = spans + requests[-2:]
        if samples:
            lines.append("```json")
            for record in samples:
                lines.append(json.dumps(record, ensure_ascii=False))
            lines.append("```")
        else:
            lines.append("（日志文件为空，先运行一次 `scripts/ask.py` 或 `scripts/eval.py`）")
        lines += [
            "",
            f"日志总行数：{len(raw)}；请求数：{len(requests)}。",
        ]
    else:
        lines.append("（尚未产生日志）")

    lines += [
        "",
        "## 4. 脱敏说明",
        "",
        "`user_query` 与答案在落盘前经过 PII 脱敏（邮箱、手机号、身份证、银行卡、工号、内部编码），",
        "命中记录写入 `pii_redacted_fields`。默认使用哈希模式，保留可追踪性而不落明文。",
    ]

    output = docs_dir / "LOG-FIELD-DICTIONARY.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[docs] 已写入 {output}")


if __name__ == "__main__":
    main()
