# 运行手册
> English version: [RUNBOOK.en.md](RUNBOOK.en.md)


> 版本：v1.0　日期：2026-09-18
> 配套：[README.md](README.md)（交付物索引）、[TECH-STACK-SELECTION.md](docs/TECH-STACK-SELECTION.md)（选型）、[EXECUTION-PLAN.md](docs/EXECUTION-PLAN.md)（计划）

## 1. 环境准备

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.12 | 系统自带 3.8.2 不可用，用 `uv` 管理 |
| uv | ≥ 0.10 | 已安装 |
| Docker | 可选 | 只有使用 Qdrant / Redis 后端时才需要 |
| 磁盘 | ≥ 2 GB | OCR 与模型依赖占主要空间 |

```bash
uv sync --extra ocr        # 必需：OCR 依赖（RapidOCR）
uv sync --extra models     # 可选：真实 embedding / 重排模型（需 PyTorch）
uv sync --extra stores     # 可选：Qdrant / Redis 客户端
```

## 2. 一键运行

```bash
bash scripts/run_all.sh
```

依次完成：入库 → 评测集构建 → 三配置评测 → 对比报告 → 运维报告 → 5 并发压测 → 问题诊断 → 生成文档。

## 3. 分步命令

| 步骤 | 命令 | 产物 |
|---|---|---|
| 入库 | `uv run python scripts/ingest.py --rebuild-corpus` | `data/index/kb_v1/`、`data/corpus/raw/` |
| 评测集 | `uv run python scripts/eval.py --rebuild-dataset` | `data/eval/*.jsonl` |
| 单配置评测 | `uv run python scripts/eval.py --configs configs/c2_hybrid.yaml` | `reports/eval_c2_hybrid.json` |
| 三配置评测 | `uv run python scripts/eval.py --all` | `reports/comparison.md` |
| 越界阈值标定 | `uv run python scripts/calibrate_scope.py` | 推荐阈值 |
| 运维报告 | `uv run python scripts/report.py --config-version c3_hybrid_rerank` | `reports/ops_report_*.txt/.csv` |
| 压测 | `uv run python scripts/loadtest.py --concurrency 5 --requests 200` | `reports/loadtest.json` |
| 问题诊断 | `uv run python scripts/diagnose.py` | `reports/diagnosis_report.md` |
| 日志字典 | `uv run python scripts/gen_log_docs.py` | `docs/LOG-FIELD-DICTIONARY.md` |
| 评测报告 | `uv run python scripts/gen_eval_report.py` | `reports/EVALUATION-REPORT.md` |
| API 服务 | `uv run uvicorn rag.api:app --port 8000` | `POST /ask`、`GET /healthz` |

单次问答调试：

```bash
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/c3_hybrid_rerank.yaml
uv run curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"API 网关的超时时间是多少？","session_id":"demo"}'
```

## 4. 配置参考（`configs/base.yaml`）

| 配置项 | 取值 | 作用 |
|---|---|---|
| `retrieval.mode` | `vector` / `hybrid` | 检索模式（需求 FR1） |
| `retrieval.fusion` | `rrf` / `weighted` | 双通道融合方式（接入真实向量后用 `weighted`，vector_weight 0.7） |
| `retrieval.conversation_rewrite` | `rules` / `llm` | 多轮追问改写方式 |
| `retrieval.top_k` / `top_n` | 整数 | 召回数量 / 送入生成的证据数 |
| `rerank.enabled` | `true` / `false` | 重排开关，**零代码改动** |
| `rerank.backend` | `lexical` / `onnx_cross_encoder` / `cross_encoder` | 重排实现（语义向量下必须用交叉编码器） |
| `rerank.max_candidates` | 整数 | 送入重排的候选数；实测 20 条需 1553ms 会超时降级，10 条约 370–610ms |
| `rerank.timeout_ms` | 毫秒 | 超时即回退到融合结果（防拖垮 P90） |
| `embedding.backend` | `hashing` / `onnx` / `sentence_transformers` | 向量后端（本机用 `onnx`，无需 PyTorch） |
| `generation.backend` | `offline` / `openai` | 生成后端 |
| `guardrails.scope_check` | `true` / `false` | 词法越界判定开关；真实模型下建议 `false` 交由模型自判 |
| `guardrails.scope_coverage_min` / `scope_oov_max` | 0–1 | 词法越界判定阈值（由标定脚本产出） |
| `guardrails.pii.*` | 布尔 / 模式 | 输出与日志脱敏 |
| `cache.enabled` / `mode` | `exact` / `semantic` | 缓存策略 |
| `chunking.child_tokens` 等 | 整数 | 切分参数（改动需重新入库） |

配置指纹会写入每条请求日志，保证评测与诊断可追溯到具体配置。

## 5. 切换到真实模型

### 5.1 真实 Embedding（ONNX 路线，无需 PyTorch）

**为什么走 ONNX**：macOS x86_64 上 PyTorch 已不再提供 wheel，`sentence-transformers` 装不上。
ONNX Runtime + `tokenizers` 可以跑真正的多语言向量模型，108–113MB，CPU 推理 64 条仅 0.05s。

```bash
uv add tokenizers huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com        # 中国大陆网络

# 下载多语言向量模型（int8，约 113MB）
mkdir -p models/multilingual-minilm/onnx && cd models/multilingual-minilm
BASE=https://hf-mirror.com/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main
for f in tokenizer.json tokenizer_config.json special_tokens_map.json config.json; do
  curl -sL -o "$(basename $f)" "$BASE/$f"
done
curl -sL -o onnx/model_int8.onnx "$BASE/onnx/model_int8.onnx"
cd ../..

# 配置（configs/llm_*.yaml 已预置）
#   embedding.backend: onnx
#   embedding.model: models/multilingual-minilm
#   embedding.onnx_file: onnx/model_int8.onnx
#   app.corpus_version: kb_v1_onnx        # 向量空间变了，用独立索引

uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml
uv run python scripts/eval.py --rebuild-dataset --eval-dir data/eval_onnx
```

> 索引与 embedding 后端不一致时程序会直接报错而非静默劣化（见 `pipeline._check_index_meta`）。
> 若确实要换 bge-m3（更强但约 2.2GB），只需改 `embedding.model` 与 `onnx_file` 并重新入库。

### 5.2 真实重排

词法重排在语义向量下会**降低**指标（实测 Context Precision 0.4346 → 0.4115），
必须换成真实交叉编码器：

```yaml
rerank:
  enabled: true
  backend: onnx_cross_encoder
  model: models/bge-reranker-base
  onnx_file: onnx/model_int8.onnx
  max_candidates: 10      # 关键：20 条候选需 1553ms，超出 800ms 预算会整批降级
  max_length: 256
  timeout_ms: 800
```

模型下载：

```bash
mkdir -p models/bge-reranker-base/onnx && cd models/bge-reranker-base
BASE=https://hf-mirror.com/Xenova/bge-reranker-base/resolve/main
for f in tokenizer.json tokenizer_config.json special_tokens_map.json config.json; do
  curl -sL -o "$(basename $f)" "$BASE/$f"
done
curl -sL -o onnx/model_int8.onnx "$BASE/onnx/model_int8.onnx"
```

### 5.3 真实生成模型

```yaml
generation:
  backend: openai
  model: <model-id>
  base_url: <OpenAI 兼容地址>       # 支持国内兼容服务
  api_key_env: OPENAI_API_KEY
  max_tokens_field: max_tokens     # 新版 OpenAI 推理模型改为 max_completion_tokens
  timeout_seconds: 30
  fallback_to_offline: false       # 评测时务必 false，避免 key 配错导致静默降级
  price_in_per_1m: 0.15            # 必须替换为官方当期价格
  price_out_per_1m: 0.60
```

```bash
cp .env.example .env && vi .env   # 方式一：写入 .env（程序会自动加载）
export OPENAI_API_KEY=...          # 方式二：shell 环境变量（优先级更高）
```

**详细步骤、各厂商 base_url 对照、错误码排查与验证方法见 [docs/API-KEY-SETUP.md](docs/API-KEY-SETUP.md)。**

`fallback_to_offline: false` 时配置错误会直接报错；为 `true` 时程序会打印告警并回退到离线生成器，
此时日志中的 `model_id` 会变成 `offline-extractive`，可用于判定是否真的调用了真实模型。

无外网时可先用仓库内的模拟服务验证链路：

```bash
uv run python scripts/mock_llm_server.py --port 8123     # 终端 1
export OPENAI_API_KEY=mock-key-for-verification
uv run python scripts/eval.py --configs configs/mock_local.yaml
```

## 6. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `索引由 X 生成，当前配置为 Y` | embedding 后端与索引不匹配 | 重新入库，或把配置改回一致 |
| 扫描件解析引擎显示 `sidecar` | OCR 依赖未安装 | `uv sync --extra ocr` 后重跑入库 |
| 指标仍使用示例价格 | `price_*_per_1m` 未更新 | 替换为官方当期价格并重跑评测 |
| 延迟远低于 10s | 使用了离线生成后端 | 接入真实模型后重跑 `scripts/loadtest.py` |
| 锚点未命中报错 | 切分把证据切断，或 OCR 文本异常 | 调整 `chunking.*` 或检查 OCR 输出质量 |

## 7. 交付物清单

| 交付物 | 位置 |
|---|---|
| 完整代码与配置 | `src/rag/`、`configs/`、`scripts/` |
| 一键评测脚本 | `scripts/eval.py`（一键全流程：`scripts/run_all.sh`） |
| 评测报告（含前后对比） | `reports/EVALUATION-REPORT.md`、`reports/comparison.md`、`reports/diagnosis_report.md` |
| 日志字段字典与样例日志 | `docs/LOG-FIELD-DICTIONARY.md` |
| 运维报告 | `reports/ops_report_c3_hybrid_rerank.txt/.csv` |
| 压测结果 | `reports/loadtest.json` |

## 8. 已知限制

1. **合规率未达标**：当前最优 0.7824（目标 0.80）。未合规项约半数为"该答却拒答"，
   需要放宽 grounding 阈值并在提示词中强化引用格式。
2. **成本使用示例单价**：`price_in_per_1m` / `price_out_per_1m` 仍是占位值，
   必须替换为模型官方当期价，成本结论才成立。
3. **向量为轻量模型**：使用 MiniLM-L12 int8（384 维），检索上限受限；换 bge-m3 可进一步提升，
   但需重新入库。
4. **重排仍有超时降级**：5 并发压测下 P90 约 4.2s（单线程 2.4s），重排与向量推理争抢 CPU。
5. **语料为合成数据**：扫描件为渲染生成，OCR 噪声分布与真实扫描件存在差异。
6. **离线后端路径仍保留**：用于无外网/无 Key 环境验证链路（指标绝对值偏低是语义能力缺失所致，
   不是链路缺陷），对应产物在 `reports/archive/`。
