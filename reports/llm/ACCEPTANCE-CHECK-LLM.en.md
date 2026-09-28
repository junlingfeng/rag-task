# Acceptance Check (real-model run)

> Chinese version: [ACCEPTANCE-CHECK-LLM.md](ACCEPTANCE-CHECK-LLM.md)
> Snapshot: 2026-09-25 (re-run after the multi-turn rewriting fixes)
> Stack: ONNX multilingual embeddings (MiniLM-L12 int8) + bge-reranker-base (ONNX int8) + DeepSeek + LLM judge
> Source: `reports/llm/eval_llm_c*.json`; pre-fix results are archived in `reports/llm/archive_broken_gold/`

## 1. Target compliance

| Metric | Target (pass / advanced) | Measured (C3 / best) | Verdict |
|---|---|---|---|
| Faithfulness | ≥ 0.85 | **1.0000** | Met |
| Context Precision@5 | ≥ 0.70 | **0.8437** (C3) | Met |
| Style Consistency | ≥ 0.80 / 0.85 | **0.8852** (C1) | Met (incl. advanced) |
| Refusal Appropriateness | ≥ 0.80 / 0.90 | **0.9381** (C1) | Met (all three configs ≥ 0.90) |
| Answer Compliance | ≥ 0.80 / 0.90 | 0.7824 (C1) / 0.7500 (C3) | Not met (97.8% of target) |
| P90 end-to-end latency | ≤ 10 s | 2.42 s (C3) | Met |
| Single-instance concurrency | ≥ 5 | 0 errors | Met |
| Cost | Estimate plus rationale | $0.2661–$0.2806 per 1,000 calls (example prices) | Met (pending real prices) |

**Four of five quality metrics are met, all at the advanced tier; compliance is 2.2% short.**

## 2. Three-configuration comparison

| Metric | C1 vector-only | C2 hybrid | C3 hybrid+rerank |
|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | **0.8437** |
| Recall@5 | 0.8681 | 0.8160 | **0.9062** |
| MRR | 0.6817 | 0.6843 | **0.8472** |
| Faithfulness | 0.9984 | 1.0000 | **1.0000** |
| Answer Compliance | **0.7824** | 0.7361 | 0.7500 |
| Style Consistency | **0.8852** | 0.8827 | 0.8766 |
| Refusal Appropriateness | **0.9381** | 0.9094 | 0.9211 |
| P90 latency | 1.56 s | 1.71 s | 2.42 s |
| Cost / 1k calls (example prices) | $0.2806 | $0.2661 | $0.2682 |
| LLM judge coverage | 125 items / 0 failures | 114 / 0 | 117 / 0 |

**Reranking delivers a large retrieval gain**: versus C2, Context Precision +24%, Recall +11%,
MRR +24%, at the cost of about +0.7 s on P90.

> Note: the best-retrieval configuration is not the best-compliance configuration. C3 retrieves much
> better but C1 has higher compliance (C3's stronger retrieval makes the model attempt more answers,
> some of which fail the strict rubric). The two metrics must be weighed together.

## 3. Improvement over the initial implementation

| Metric | Initial (hash embeddings + rule judging + offline generation) | Final (real embeddings + cross-encoder + real model + LLM judge) |
|---|---|---|
| Context Precision@5 | 0.3509 | **0.8437** (+140%) |
| Recall@5 | 0.4271 | **0.9062** (+112%) |
| Faithfulness | 0.7434 | **1.0000** |
| Answer Compliance | 0.6111 | **0.7824** |
| Refusal Appropriateness | 0.8385 | **0.9381** |
| Multi-turn rewrite-turn CP@5 | 0.463 (mis-labelled) | **0.7812** |
| Injection interception | 20/20 | 20/20 |

## 4. Remaining gaps and causes

| Not met | Measured | Main cause | Next step |
|---|---|---|---|
| Answer Compliance 0.80 | 0.7824 (C1, best) | Of C1's 47 non-compliant items, 21 are "should have answered but refused" and 25 are answers failing the judge rubric (C3: 29 / 24) | Reduce over-refusal (relax grounding threshold and prompt); tighten citation formatting |
| Cost basis | $0.2661–$0.2806 / 1k | Example unit prices still in use ($0.15 / $0.60 per 1M tokens) | Replace with DeepSeek's current prices |

Subset detail (C1, the highest-compliance config): single-turn compliance 0.906 (58/64 answered),
multi-turn compliance 0.812 (65/80 answered).

## 5. Defects found and fixed (cumulative)

1. Cross-lingual retrieval failure: hash embeddings could not match English questions to Chinese documents — the root cause of a Context Precision of only 0.38.
2. Weighted fusion suppressing the semantic channel: with lexical weight 0.7, correct cross-lingual results present only in the vector channel were pushed out.
3. Lexical reranking destroying semantic ordering: after real embeddings were introduced, lexical reranking dropped CP from 0.4346 to 0.4115.
4. Reranking timing out and degrading wholesale: 20 candidates needed 1553 ms against an 800 ms budget; 10 candidates take 370–610 ms.
5. Cache hits losing citations and retrieval context: cached answers returned empty citations and corrupted the retrieval metrics.
6. Cache left enabled during evaluation: hits skipped retrieval and masked real retrieval quality.
7. Judge evidence truncated: a 280-character cut hid supporting sentences and made correct answers look fabricated.
8. Model self-refusal not recognised: when the model said "not in the material", the pipeline still recorded "answered", corrupting both refusal and compliance metrics.
9. Lexical scope gate causing mass false refusals: 37 of 50 over-refusals came from that gate, 18 of them with perfect retrieval; switching to model self-judgement raised refusal appropriateness from 0.859 to 0.918.
10. Multi-turn labels missing the cross-language fallback: single-turn had it, multi-turn did not, so English items had empty gold and correct retrieval scored 0.
11. Turn gating misclassification: using "question shorter than 24 characters" as the rewrite signal made standalone new-topic questions look like follow-ups, which the fallback then replaced, answering the wrong topic.
12. Rewriting implemented as concatenation: produced malformed compound questions; replaced with LLM conversational rewriting including strict retry and deterministic fallback.
13. Wrong generation input: A/B testing confirmed generation must use the rewritten question
    (rules mode 0.825 vs 0.675; LLM mode 0.750 vs 0.700), because a follow-up carries no topic of its
    own and conversation history alone is not enough to resolve references reliably.

## 6. Reproduction commands

```bash
uv sync --extra ocr && uv add tokenizers huggingface_hub
# ONNX model files (via hf-mirror)
uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml
uv run python scripts/eval.py --rebuild-dataset --eval-dir data/eval_onnx --report-dir reports/llm
uv run python scripts/eval.py \
  --configs configs/llm_c1_vector.yaml configs/llm_c2_hybrid.yaml configs/llm_c3_hybrid_rerank.yaml \
  --eval-dir data/eval_onnx --report-dir reports/llm
uv run python scripts/report.py --config-version llm_c3_hybrid_rerank --report-dir reports/llm
```
