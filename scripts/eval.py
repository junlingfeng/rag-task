#!/usr/bin/env python
"""一键评测：跑指定配置，或跑三配置对比并输出结论。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.eval.dataset import EVAL_DIR, build_dataset  # noqa: E402
from rag.eval.runner import run_eval  # noqa: E402
from rag.eval.compare import write_comparison  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="*", default=None)
    parser.add_argument("--all", action="store_true", help="跑三种检索配置并生成对比报告")
    parser.add_argument("--rebuild-dataset", action="store_true")
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument(
        "--eval-dir",
        default=None,
        help="评测集目录（默认 data/eval；用 ONNX 索引实验时建议显式指定以区分口径）",
    )
    args = parser.parse_args()

    if args.rebuild_dataset:
        stats = build_dataset()
        print(f"[dataset] {json.dumps(stats, ensure_ascii=False)}")

    eval_dir = Path(args.eval_dir) if args.eval_dir else EVAL_DIR

    configs = args.configs
    if args.all or not configs:
        configs = ["configs/c1_vector.yaml", "configs/c2_hybrid.yaml", "configs/c3_hybrid_rerank.yaml"]

    results = []
    for path in configs:
        metrics = run_eval(path, eval_dir=eval_dir, report_dir=Path(args.report_dir))
        results.append(metrics)
        print(f"[eval] {json.dumps(metrics, ensure_ascii=False)}")

    if len(results) > 1:
        report = write_comparison(results, Path(args.report_dir))
        print(f"[compare] 已生成 {report}")


if __name__ == "__main__":
    main()
