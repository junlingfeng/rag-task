# Target Architecture and Implementation Roadmap

> Chinese version: [ARCHITECTURE-AND-ROADMAP.md](ARCHITECTURE-AND-ROADMAP.md)
> This is the design-time document. The configuration actually shipped lives in `configs/`; where the
> two differ, `configs/` is authoritative.

## 1. Overall architecture

```
                    ┌─────────────────────────────────────────────┐
                    │  Ingestion (offline, one-shot + incremental) │
                    │  PDF/Word/HTML → parse → OCR (scans) → clean │
                    │  → language ID → chunk (CN/EN strategies)    │
                    │  → metadata → embedding → vector store +     │
                    │  inverted index (BM25)                       │
                    └─────────────────────────────────────────────┘

   Client ──► API gateway ──► session management (multi-turn context)
                                │
                                ▼
                        query rewriting (coref / ellipsis)
                                │
                                ▼
                          cache lookup (exact / semantic)
                                │ miss
                                ▼
              ┌──────── retrieval layer (config-driven) ────────┐
              │  vector-only  or  hybrid                        │
              │  vector search ∥ BM25 → fusion (RRF)            │
              └──────────────┬─────────────────────────────────┘
                             ▼
                   reranker (configurable switch)
                             ▼
              ┌──────── guardrail layer ────────┐
              │ injection detection / scope     │
              │ check / low-confidence check    │
              └───────────┬─────────────────────┘
                          ▼
                 prompt assembly (numbered citations)
                          ▼
                    generation (model configurable)
                          ▼
              ┌──────── post-processing ────────┐
              │ citation validation / refuse    │
              │ when unsupported / PII redaction│
              │ (output and logs)               │
              └───────────┬─────────────────────┘
                          ▼
                       response + structured log

   ┌──────────────────────────────────────────────────────────┐
   │  Observability: trace/span, config snapshot, tokens        │
   └──────────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────┐
   │  Eval harness: dataset → multi-config batch → judge →      │
   │  metrics → report                                          │
   └──────────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────┐
   │  Ops report: p50/p95, tokens, cache hit rate, refusal rate,│
   │  compliance rate                                           │
   └──────────────────────────────────────────────────────────┘
```

Layering principle (NFR2 evolvability): retrieval, reranking, fusion, generation, judging and
evaluation are all decoupled behind interfaces plus configuration, so implementations can be replaced
without touching callers.

## 2. Configuration model (satisfies FR1 "switch without code changes")

Driven by a single YAML file; the configuration version is written into every request log.

```yaml
app:
  config_version: v1
  prompt_version: p1

retrieval:
  mode: hybrid            # vector | hybrid
  conversation_rewrite: rules   # rules | llm
  top_k: 20
  fusion: weighted        # rrf | weighted
  vector_weight: 0.7

rerank:
  enabled: true           # pure configuration switch
  backend: onnx_cross_encoder
  model: models/bge-reranker-base
  max_candidates: 10      # 20 candidates = 1553 ms > 800 ms budget
  max_length: 256
  timeout_ms: 800         # fall back to the fused result on timeout

embedding:
  backend: onnx           # hashing | onnx | sentence_transformers
  model: models/multilingual-minilm
  onnx_file: onnx/model_int8.onnx

generation:
  backend: openai
  model: <provider/model-id>
  temperature: 0
  max_output_tokens: 600
  fallback_to_offline: false

guardrails:
  injection_detection: true
  scope_check: false      # with a real model, let the model decide + detect self-refusal
  min_support_score: 0.10
  pii:
    redact_output: true
    redact_logs: true

cache:
  enabled: true
  mode: semantic          # exact | semantic
  similarity_threshold: 0.95
  ttl_seconds: 86400

observability:
  log_format: json
  log_redaction: hash     # hash | placeholder | drop
```

The three evaluation configurations are three variants of the same file:

| Config | retrieval.mode | rerank.enabled |
|---|---|---|
| C1 vector-only | vector | false |
| C2 hybrid | hybrid | false |
| C3 hybrid+rerank | hybrid | true |

## 3. Log field dictionary (deliverable requirement)

One JSON line per event; `trace_id` spans the whole chain. A sample appears at the end of this section.

| Field | Type | Description |
|---|---|---|
| ts | string (ISO8601) | Event time |
| trace_id | string | End-to-end trace id |
| request_id | string | Single HTTP request id |
| session_id | string | Session id (multi-turn) |
| turn_index | int | Turn number |
| stage | enum | rewrite / retrieve / rerank / guardrail / generate / postprocess / total |
| latency_ms | number | Stage duration |
| config_version | string | Configuration version snapshot |
| prompt_version | string | Prompt version |
| retrieval_mode | enum | vector / hybrid |
| rerank_enabled | bool | Whether reranking was on |
| top_k | int | Recall size |
| top_n | int | Evidence passed to generation |
| retrieved_chunk_ids | string[] | Chunk ids retrieved |
| retrieval_scores | number[] | Similarity / fused scores |
| rerank_scores | number[] | Rerank scores |
| cache_hit | bool | Whether the cache was hit |
| cache_key_hash | string | Cache key hash (no plaintext) |
| prompt_tokens | int | Input tokens |
| completion_tokens | int | Output tokens |
| total_tokens | int | Total tokens |
| cost_usd | number | Estimated cost for this request |
| model_id | string | Generation model version |
| answer_status | enum | answered / refused / error |
| refusal_reason | enum | low_confidence / out_of_scope / safety / no_evidence |
| citation_ids | string[] | Evidence ids cited by the answer |
| support_score | number | Degree to which the answer is supported |
| injection_flags | string[] | Injection signatures matched |
| pii_redacted_fields | string[] | Fields redacted (e.g. user_query, answer) |
| judge_scores | object | Offline evaluation scores |
| error_type | string | Exception type (nullable) |

Sample log line:

```json
{
  "ts": "2026-09-18T12:00:01.234+08:00",
  "trace_id": "tr_9f3c1a",
  "request_id": "req_88213",
  "session_id": "sess_4410",
  "turn_index": 2,
  "stage": "total",
  "latency_ms": 3120,
  "config_version": "v1",
  "prompt_version": "p1",
  "retrieval_mode": "hybrid",
  "rerank_enabled": true,
  "top_k": 20,
  "top_n": 5,
  "retrieved_chunk_ids": ["doc12#3", "doc07#1", "doc33#5"],
  "retrieval_scores": [0.83, 0.79, 0.71],
  "rerank_scores": [0.94, 0.88, 0.63],
  "cache_hit": false,
  "prompt_tokens": 1840,
  "completion_tokens": 210,
  "total_tokens": 2050,
  "cost_usd": 0.0021,
  "model_id": "gpt-4o-mini-2024-07-18",
  "answer_status": "answered",
  "refusal_reason": null,
  "citation_ids": ["doc12#3", "doc07#1"],
  "support_score": 0.91,
  "injection_flags": [],
  "pii_redacted_fields": ["user_query"],
  "error_type": null
}
```

## 4. Three-config comparison experiment design (NFR1)

| Item | Design |
|---|---|
| Independent variable | Retrieval configuration only (C1/C2/C3) |
| Controlled variables | Evaluation set, prompt version, generation model, top_n, temperature, seed |
| Dependent variables | Context Precision, Faithfulness, Compliance, Style, two-sided refusal metrics, P50/P90/P95, token cost, cache hit rate |
| Sample | The full evaluation set (single-turn, multi-turn, out-of-scope, unsafe) |
| Output | Comparison table plus a conclusion (which config wins in which scenario, and why) |
| Caveat | Reranking raises precision but adds latency; the conclusion must state that trade-off explicitly |

Expected direction (to be validated by data, not copied blindly): hybrid improves recall but may add
lexical noise; reranking repairs ordering and lifts Context Precision at the cost of higher P90; if
P90 breaches the budget, timeout fallback or a cache safety net is required.

## 5. Issue diagnosis scenarios (NFR4, at least 2)

The brief requires "at least 2 issues + log evidence + fix rationale + ≥ 10% post-fix improvement".
These are candidates; when executed, **record the real data faithfully**.

| Candidate | Symptom | Log evidence | Fix direction | Improvement measure |
|---|---|---|---|---|
| A: hybrid adds noise | Context Precision drops after switching to hybrid | retrieval_scores shift right while rerank_scores stay low; citation hit rate falls | Fix Chinese tokenisation + adjust fusion weights + score threshold | Context Precision +≥ 10% |
| B: refusal spike | After enabling injection filtering, refusal_rate jumps from 8% to 30% | refusal_reason=safety share spikes; injection_flags false-positive on normal questions | Tighten regex / switch to a classifier + allowlist | Correct answer rate +≥ 10% |
| C: stale cached answers | Compliance drops after documents are updated | Request with cache_hit=true scores materially lower than misses | Invalidate cache on re-index + shorten TTL | Compliance +≥ 10% |
| D: reranking breaks the P90 budget | P90 rises from 7.2 s to 11.5 s | rerank stage span p95 > 3 s | Timeout fallback + batched reranking + caching | P90 back below 10 s |

Every diagnosis report must contain: symptom → time window → log/metric evidence → root-cause analysis
→ fix and rationale → before/after data → conclusion.

## 6. Milestones and acceptance criteria

| Stage | Content | Acceptance criteria |
|---|---|---|
| M0 | Evaluation dataset + logging/metric skeleton | Dataset size met; log field dictionary formed; sample logs producible |
| M1 | vector-only baseline | End-to-end Q&A works; every request is instrumented; baseline metrics computable |
| M2 | hybrid + configurable reranking | Editing YAML switches between the three configs, with no code change |
| M3 | Refusal / safety / PII | All three refusal triggers fire with guidance; output and logs both redacted |
| M4 | One-click evaluation + three-config report | A single command produces the comparison report and conclusion |
| M5 | Caching + operations report | txt/CSV report contains every mandatory field |
| M6 | Two issue diagnoses with before/after | Each has log evidence and ≥ 10% improvement data |
| M7 | Documentation close-out | Code and configuration complete and runnable; log dictionary and samples present |

## 7. Engineering constraints to remember

- **Reranker timeout must degrade gracefully**: an external reranking service must not blow the 10 s budget.
- **Retrieval must be parallel**: vector and BM25 queries must be issued concurrently.
- **Configuration snapshots**: record the effective configuration on every request, otherwise both the
  comparison and the diagnoses are worthless.
- **Redact early**: PII in queries must be handled before it reaches logs or the cache; cache keys must
  not contain plaintext PII either.
- **Offline evaluation and the online service share one retrieval/generation code path**, so evaluation
  results cannot diverge from production behaviour.
