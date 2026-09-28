# Runbook

> Version: v1.0　Date: 2026-09-18
> Chinese version: [RUNBOOK.md](RUNBOOK.md)
> See also: [README.md](README.en.md) (deliverable index), [TECH-STACK-SELECTION.md](docs/TECH-STACK-SELECTION.en.md) (selection), [EXECUTION-PLAN.md](docs/EXECUTION-PLAN.en.md) (plan)

## 1. Environment

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.12 | The system Python 3.8.2 is too old; manage with `uv` |
| uv | ≥ 0.10 | Installed |
| Docker | Optional | Only needed for the Qdrant / Redis backends |
| Disk | ≥ 2 GB | OCR and model dependencies dominate |

```bash
uv sync --extra ocr        # Required: OCR dependencies (RapidOCR)
uv sync --extra models     # Optional: real embedding / rerank models (needs PyTorch)
uv sync --extra stores     # Optional: Qdrant / Redis clients
```

## 2. One-click run

```bash
bash scripts/run_all.sh
```

This runs, in order: ingest → build evaluation set → three-config evaluation → comparison report →
operations report → 5-concurrency load test → issue diagnosis → documentation generation.

## 3. Step-by-step commands

| Step | Command | Output |
|---|---|---|
| Ingest | `uv run python scripts/ingest.py --rebuild-corpus` | `data/index/kb_v1/`, `data/corpus/raw/` |
| Evaluation set | `uv run python scripts/eval.py --rebuild-dataset` | `data/eval/*.jsonl` |
| Single-config evaluation | `uv run python scripts/eval.py --configs configs/c2_hybrid.yaml` | `reports/eval_c2_hybrid.json` |
| Three-config evaluation | `uv run python scripts/eval.py --all` | `reports/comparison.md` |
| Scope threshold calibration | `uv run python scripts/calibrate_scope.py` | Recommended thresholds |
| Operations report | `uv run python scripts/report.py --config-version c3_hybrid_rerank` | `reports/ops_report_*.txt/.csv` |
| Load test | `uv run python scripts/loadtest.py --concurrency 5 --requests 200` | `reports/loadtest.json` |
| Issue diagnosis | `uv run python scripts/diagnose.py` | `reports/diagnosis_report.md` |
| Log dictionary | `uv run python scripts/gen_log_docs.py` | `docs/LOG-FIELD-DICTIONARY.md` |
| Evaluation report | `uv run python scripts/gen_eval_report.py` | `reports/EVALUATION-REPORT.md` |
| API service | `uv run uvicorn rag.api:app --port 8000` | `POST /ask`, `GET /healthz` |

Single-question debugging:

```bash
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/c3_hybrid_rerank.yaml
uv run curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"API 网关的超时时间是多少？","session_id":"demo"}'
```

## 4. Configuration reference (`configs/base.yaml`)

| Key | Values | Purpose |
|---|---|---|
| `retrieval.mode` | `vector` / `hybrid` | Retrieval mode (requirement FR1) |
| `retrieval.fusion` | `rrf` / `weighted` | Two-channel fusion (use `weighted` with vector_weight 0.7 once real embeddings are in) |
| `retrieval.conversation_rewrite` | `rules` / `llm` | How multi-turn follow-ups are rewritten |
| `retrieval.top_k` / `top_n` | integer | Recall size / evidence passed to generation |
| `rerank.enabled` | `true` / `false` | Reranker switch, **no code change required** |
| `rerank.backend` | `lexical` / `onnx_cross_encoder` / `cross_encoder` | Reranker implementation (a cross-encoder is required with semantic embeddings) |
| `rerank.max_candidates` | integer | Candidates sent to the reranker; measured: 20 candidates need 1553 ms (times out), 10 need ~370–610 ms |
| `rerank.timeout_ms` | ms | On timeout, fall back to the fused result (protects P90) |
| `embedding.backend` | `hashing` / `onnx` / `sentence_transformers` | Embedding backend (`onnx` needs no PyTorch) |
| `generation.backend` | `offline` / `openai` | Generation backend |
| `guardrails.scope_check` | `true` / `false` | Lexical out-of-scope gate; with a real model prefer `false` and let the model decide |
| `guardrails.scope_coverage_min` / `scope_oov_max` | 0–1 | Lexical scope thresholds (produced by the calibration script) |
| `guardrails.pii.*` | boolean / mode | Output and log redaction |
| `cache.enabled` / `mode` | `exact` / `semantic` | Caching strategy |
| `chunking.child_tokens` etc. | integer | Chunking parameters (changing these requires re-ingesting) |

The configuration fingerprint is written into every request log, so evaluation and diagnosis can be
traced back to the exact configuration used.

## 5. Switching to real models

### 5.1 Real embeddings (ONNX route, no PyTorch)

**Why ONNX**: PyTorch no longer ships wheels for macOS x86_64, so `sentence-transformers` cannot be
installed. ONNX Runtime + `tokenizers` runs a genuine multilingual embedding model —
108–113 MB, and 64 texts encode in 0.05 s on CPU.

```bash
uv add tokenizers huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com        # mainland-China network

# Download the multilingual embedding model (int8, ~113 MB)
mkdir -p models/multilingual-minilm/onnx && cd models/multilingual-minilm
BASE=https://hf-mirror.com/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main
for f in tokenizer.json tokenizer_config.json special_tokens_map.json config.json; do
  curl -sL -o "$(basename $f)" "$BASE/$f"
done
curl -sL -o onnx/model_int8.onnx "$BASE/onnx/model_int8.onnx"
cd ../..

# Configuration (already preset in configs/llm_*.yaml)
#   embedding.backend: onnx
#   embedding.model: models/multilingual-minilm
#   embedding.onnx_file: onnx/model_int8.onnx
#   app.corpus_version: kb_v1_onnx        # different vector space → separate index

uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml
uv run python scripts/eval.py --rebuild-dataset --eval-dir data/eval_onnx
```

> If the index and the embedding backend do not match, the program raises an error instead of
> degrading silently (see `pipeline._check_index_meta`).
> To move up to bge-m3 (stronger, ~2.2 GB) simply change `embedding.model` and `onnx_file`
> and re-ingest.

### 5.2 Real reranking

A lexical reranker **lowers** the metrics once semantic embeddings are in place
(measured: Context Precision 0.4346 → 0.4115), so a real cross-encoder is required:

```yaml
rerank:
  enabled: true
  backend: onnx_cross_encoder
  model: models/bge-reranker-base
  onnx_file: onnx/model_int8.onnx
  max_candidates: 10      # critical: 20 candidates need 1553 ms and blow the 800 ms budget
  max_length: 256
  timeout_ms: 800
```

Model download:

```bash
mkdir -p models/bge-reranker-base/onnx && cd models/bge-reranker-base
BASE=https://hf-mirror.com/Xenova/bge-reranker-base/resolve/main
for f in tokenizer.json tokenizer_config.json special_tokens_map.json config.json; do
  curl -sL -o "$(basename $f)" "$BASE/$f"
done
curl -sL -o onnx/model_int8.onnx "$BASE/onnx/model_int8.onnx"
```

### 5.3 Real generation model

```yaml
generation:
  backend: openai
  model: <model-id>
  base_url: <OpenAI-compatible endpoint>   # domestic compatible services supported
  api_key_env: OPENAI_API_KEY
  max_tokens_field: max_tokens     # newer OpenAI reasoning models need max_completion_tokens
  timeout_seconds: 30
  fallback_to_offline: false       # keep false in evaluations: a bad key must not degrade silently
  price_in_per_1m: 0.15            # must be replaced with the provider's current price
  price_out_per_1m: 0.60
```

```bash
cp .env.example .env && vi .env   # option 1: write to .env (loaded automatically)
export OPENAI_API_KEY=...          # option 2: shell environment variable (higher precedence)
```

**Detailed steps, provider endpoint table, error-code triage and verification are in
[docs/API-KEY-SETUP.md](docs/API-KEY-SETUP.en.md).**

With `fallback_to_offline: false` a misconfiguration raises an error; with `true` the program logs a
warning and falls back to the offline generator, in which case `model_id` in the logs becomes
`offline-extractive` — use that to tell whether the real model was actually called.

When there is no outbound network, verify the wiring with the bundled mock service:

```bash
uv run python scripts/mock_llm_server.py --port 8123     # terminal 1
export OPENAI_API_KEY=mock-key-for-verification
uv run python scripts/eval.py --configs configs/mock_local.yaml
```

## 6. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `索引由 X 生成，当前配置为 Y` (index/config mismatch) | embedding backend does not match the index | Re-ingest, or point the config back to the matching backend |
| Scanned-document engine reports `sidecar` | OCR dependencies not installed | `uv sync --extra ocr`, then re-ingest |
| Cost report still uses example prices | `price_*_per_1m` not updated | Replace with the provider's current prices and re-run |
| Latency far below 10 s | Offline generation backend in use | Attach a real model and re-run `scripts/loadtest.py` |
| Anchor-not-found error | Chunking cut the evidence apart, or OCR text is corrupted | Adjust `chunking.*` or inspect OCR output quality |

## 7. Deliverables

| Deliverable | Location |
|---|---|
| Complete code and configuration | `src/rag/`, `configs/`, `scripts/` |
| One-click evaluation script | `scripts/eval.py` (full pipeline: `scripts/run_all.sh`) |
| Evaluation report (with before/after) | `reports/EVALUATION-REPORT.md`, `reports/comparison.md`, `reports/diagnosis_report.md` |
| Log field dictionary and sample logs | `docs/LOG-FIELD-DICTIONARY.md` |
| Operations report | `reports/ops_report_llm_c3_hybrid_rerank.txt/.csv` |
| Load-test results | `reports/loadtest.json` |

## 8. Known limitations

1. **Answer compliance is below target**: best measured 0.7824 against a 0.80 target. About half of
   the non-compliant items are cases where the system refused a question it should have answered;
   the fix is to relax the grounding threshold and tighten the citation format in the prompt.
2. **Cost uses example prices**: `price_in_per_1m` / `price_out_per_1m` are still placeholders and
   must be replaced with the provider's current prices before the cost figure means anything.
3. **The embedding model is lightweight**: MiniLM-L12 int8 at 384 dimensions caps retrieval quality;
   moving to bge-m3 would raise it further but requires re-ingesting.
4. **Reranking still times out for some requests**: under 5-way concurrency P90 is ~4.2 s versus
   2.4 s single-threaded, because reranking and embedding inference compete for CPU.
5. **The corpus is synthetic**: scanned documents are rendered, so the OCR noise distribution differs
   from real scans.
6. **The offline backend path is retained** for environments without network or API keys, to validate
   the pipeline end-to-end (its lower absolute metrics come from missing semantic ability, not from a
   pipeline defect); those artefacts live in `reports/archive/`.
