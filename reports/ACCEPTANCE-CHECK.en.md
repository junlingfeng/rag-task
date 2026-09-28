# Acceptance Check (current verdict)

> Chinese version: [ACCEPTANCE-CHECK.md](ACCEPTANCE-CHECK.md)
> Snapshot: 2026-09-25
> This verdict is based on the **real stack**: ONNX multilingual embeddings + ONNX cross-encoder
> reranking + DeepSeek + LLM judge.
> Source: `reports/llm/eval_llm_c*.json`. The offline-stage check is archived at
> [archive/ACCEPTANCE-CHECK-offline-20260919.md](archive/ACCEPTANCE-CHECK-offline-20260919.md).

## 1. Target compliance

| Metric | Target (pass / advanced) | Best measured | Verdict |
|---|---|---|---|
| Faithfulness | ≥ 0.85 | **1.0000** | Met |
| Context Precision@5 | ≥ 0.70 | **0.8437** | Met |
| Style Consistency | ≥ 0.80 / 0.85 | **0.8852** | Met (incl. advanced) |
| Refusal Appropriateness | ≥ 0.80 / 0.90 | **0.9381** | Met (incl. advanced) |
| Answer Compliance | ≥ 0.80 / 0.90 | 0.7824 | Not met (97.8% of target) |
| P90 end-to-end latency | ≤ 10 s | 2.42 s | Met |
| Single-instance concurrency | ≥ 5 | 5 concurrent / 200 requests / 0 errors | Met |
| Cost | Estimate plus rationale | $0.2661–$0.2806 per 1,000 calls (example prices) | Met (pending real prices) |

**Four of five quality metrics are met, and all four reach the advanced tier; compliance is 2.2% short.**

Per-configuration bests:

| Metric | C1 vector | C2 hybrid | C3 hybrid+rerank |
|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | **0.8437** |
| Recall@5 | 0.8681 | 0.8160 | **0.9062** |
| Faithfulness | 0.9984 | **1.0000** | **1.0000** |
| Answer Compliance | **0.7824** | 0.7361 | 0.7500 |
| Style Consistency | **0.8852** | 0.8827 | 0.8766 |
| Refusal Appropriateness | **0.9381** | 0.9094 | 0.9211 |
| P90 latency | 1.56 s | 1.71 s | 2.42 s |

> **Best retrieval ≠ best compliance**: C3 retrieves best (CP 0.8437) yet has lower compliance than C1
> (0.7500 vs 0.7824). C3's stronger retrieval makes the model attempt more answers (correct answer
> rate 0.906 vs 0.875), some of which fail the strict rubric, whereas C1 refuses more often.
> If the objective is compliance, C1 is currently the better configuration; if it is retrieval
> quality, C3 is.

## 2. Functional requirements and deliverables

| Item | Verdict | Evidence |
|---|---|---|
| FR1 Two retrieval modes + configurable reranking | Met | Three configs differ only in `retrieval.mode` and `rerank.enabled` |
| FR2 Three refusal triggers with guidance | Met | Refusal reasons: `no_evidence` / `low_confidence` / `safety` |
| FR3 Dual-path PII redaction | Met | Answers show `[REDACTED:EMAIL]` / `[REDACTED:CN_HOTLINE]` |
| FR4 Operations report (six fields) | Met | `reports/llm/ops_report_llm_c3_hybrid_rerank.txt/.csv` |
| Security: injection interception | Met | 20/20 |
| Four-part deliverable set | Met | Code and configs, one-click scripts, evaluation report, log dictionary |

## 3. Improvement over the initial stage

| Metric | Initial (hash embeddings + rule judging + offline generation) | Current (real embeddings + cross-encoder + real model + LLM judge) |
|---|---|---|
| Context Precision@5 | 0.3509 | **0.8437** (+140%) |
| Recall@5 | 0.4271 | **0.9062** (+112%) |
| Faithfulness | 0.7434 | **1.0000** |
| Answer Compliance | 0.6111 | **0.7824** |
| Refusal Appropriateness | 0.8385 | **0.9381** |
| Multi-turn rewrite-turn CP@5 | 0.463 (mis-labelled) | **0.7812** |

## 4. Remaining gaps

| Not met | Measured | Main cause | Next step |
|---|---|---|---|
| Answer Compliance ≥ 0.80 | 0.7824 (C1) | Of 47 non-compliant items, 21 are "should have answered but refused" and 25 are answers that fail the judge's rubric | Relax the grounding threshold; strengthen citation-format instructions |
| Cost basis | Example unit prices | Provider's current prices not applied | Replace `price_in_per_1m` / `price_out_per_1m` and recompute |

The detailed real-model acceptance record, including the 13 defects fixed along the way, is in
[llm/ACCEPTANCE-CHECK-LLM.en.md](llm/ACCEPTANCE-CHECK-LLM.en.md).
