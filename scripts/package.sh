#!/usr/bin/env bash
# 打包交付物。
#
#   bash scripts/package.sh            # 精简包（默认）：代码 + 配置 + 文档 + 报告 + 数据 + .env
#   bash scripts/package.sh --full     # 全量包：额外包含本地 ONNX 模型与原始日志
#   bash scripts/package.sh --no-env   # 不含 .env（接收方需自备 API Key）
#
# 无论哪种模式都会排除：虚拟环境、字节码缓存、系统垃圾文件。
#
# 注意：默认会打包 .env，其中包含真实 API Key，等于明文分发凭证。
#       分发范围不可控时请改用 --no-env，让对方按 docs/API-KEY-SETUP.md 自行填写。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
NAME="$(basename "$ROOT")"
STAMP="$(date +%Y%m%d)"
FULL=0
NO_ENV=0
for arg in "$@"; do
  [ "$arg" = "--full" ] && FULL=1
  [ "$arg" = "--no-env" ] && NO_ENV=1
done

SUFFIX="deliverable"
[ "$FULL" = "1" ] && SUFFIX="full"
OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/${NAME}-${SUFFIX}-${STAMP}.zip"

mkdir -p "$OUT_DIR"
rm -f "$OUT"

# 始终排除：虚拟环境、字节码、系统文件、打包产物自身
EXCLUDES=(
  "$NAME/.venv/*"
  "*/__pycache__/*" "*.pyc" "*/.DS_Store"
  "$NAME/dist/*"
)

if [ "$NO_ENV" = "1" ]; then
  EXCLUDES+=("$NAME/.env")
fi

# 默认再排除体积大且可再生的内容
if [ "$FULL" = "0" ]; then
  EXCLUDES+=(
    "$NAME/models/*"
    "$NAME/logs/*.jsonl"
  )
fi

ARGS=()
for pattern in "${EXCLUDES[@]}"; do
  ARGS+=(-x "$pattern")
done

cd "$(dirname "$ROOT")"
zip -r -q "$OUT" "$NAME" "${ARGS[@]}"

echo "已生成: $OUT"
echo "大小:   $(du -h "$OUT" | cut -f1)"
echo "条目数: $(unzip -l "$OUT" | tail -1 | awk '{print $2}')"
if [ "$NO_ENV" = "0" ]; then
  echo
  echo "⚠ 已包含 .env（内含真实 API Key）。分发前请确认接收方可信；"
  echo "  若对方无需直接调用，请改用 --no-env 重新打包。"
fi
if [ "$FULL" = "0" ]; then
  cat <<'EOF'

精简包已排除（可再生或体积过大）：
  models/                  本地 ONNX 模型，按 RUNBOOK 第 5 节下载（约 385MB）
  logs/*.jsonl             原始日志（运维报告已聚合进 reports/）
已保留 data/index/ 与 data/eval_experiments/（合计约 1.7MB），
因此解包后无需先跑入库，即可直接执行问答与评测。
需要包含以上内容时改用：bash scripts/package.sh --full
EOF
fi
