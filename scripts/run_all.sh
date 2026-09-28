#!/usr/bin/env bash
# 一键跑完全部流程：入库 → 评测集 → 三配置评测 → 运维报告 → 压测 → 诊断 → 文档
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "[setup] 创建虚拟环境并安装依赖"
  uv sync --extra ocr
fi

echo "[1/7] 入库（含 OCR、切分、向量化）"
uv run python scripts/ingest.py --rebuild-corpus

echo "[2/7] 构建评测数据集"
uv run python scripts/eval.py --rebuild-dataset

echo "[3/7] 三配置评测并生成对比报告"
uv run python scripts/eval.py --all

echo "[4/7] 运维报告"
uv run python scripts/report.py --config-version c3_hybrid_rerank

echo "[5/7] 并发压测（5 并发 / 200 请求）"
uv run python scripts/loadtest.py --concurrency 5 --requests 200

echo "[6/7] 问题诊断实验"
uv run python scripts/diagnose.py

echo "[7/7] 生成交付文档"
uv run python scripts/gen_log_docs.py
uv run python scripts/gen_eval_report.py

echo "完成。产物见 reports/ 与 docs/"
