# Metric Definitions and Evaluation Method

> Chinese version: [METRIC-DEFINITIONS.md](METRIC-DEFINITIONS.md)

The brief says "define your evaluation method", so the definitions below are themselves part of the
deliverable. Each metric comes with: target, definition, formula, implementation, data requirements
and caveats.

## 0. Evaluation dataset design (prerequisite for every metric)

This is the largest work item in the whole deliverable and must be done first.

| Subset | Suggested size | Content | Metrics it supports |
|---|---|---|---|
| Single-turn answerable | ≥ 100 | Question, gold answer, gold evidence chunk ids | Context Precision, Faithfulness, Compliance, Style |
| Multi-turn conversations | ≥ 20 conversations | 3–5 turns each, containing anaphora and ellipsis | Context Precision, Compliance |
| Out-of-scope | ≥ 30 | Questions with no answer in the corpus | Refusal Appropriateness |
| Unsafe | ≥ 20 | Injection, privilege escalation, disallowed requests | Refusal Appropriateness, injection defence |
| Low confidence | ≥ 20 | Semantically close but without firm support | Refusal Appropriateness |
| Chinese / English / mixed | balanced | Covers the bilingual requirement | All metrics |

Labelling requirements:

- Evidence spans must be labelled at chunk granularity and match the real production chunking
  strategy (re-label or build a mapping if chunking changes).
- The gold answer is a reference for the judge, not the only correct answer (so answer variety is not
  scored as an error).
- The dataset is frozen and version-controlled; changing it during tuning invalidates before/after
  comparisons.

## 1. RAG metrics

### 1.1 Faithfulness (target ≥ 0.85)

**Definition**: the proportion of atomic claims in the answer that are supported by the retrieved context.

**Formula**:

```
Faithfulness = supported claims / total claims in the answer
```

**Implementation**:

1. Use the judge model to decompose the answer into atomic claims (one fact each).
2. Classify each claim against the retrieved context as entailed / contradicted / not-mentioned.
3. Compute the entailed proportion.

**Caveat**: refusals are excluded from the denominator; refusal quality is measured separately by
Refusal Appropriateness.

### 1.2 Context Precision (target ≥ 0.70)

**Definition**: the proportion of retrieved passages that are genuinely relevant, weighted by rank
(higher ranks weigh more).

**Formula** (rank-weighted):

```
ContextPrecision@k = Σ_{i=1..k} ( Precision@i × rel(i) ) / number of relevant passages
Precision@i        = relevant passages among the first i / i
rel(i) ∈ {0,1}
```

**Implementation**: use the labelled evidence chunk ids as ground truth and check whether retrieved
passages hit them.

**Caveats**:

- Fix `k` (recommended: the same top_n passed to the generation model) and additionally report the
  k=5/10/20 curve.
- In cross-lingual retrieval, a Chinese question hitting an English passage counts as relevant.
- In multi-turn conversations the rewritten question drives retrieval; the metric evaluates the
  end-to-end effect of the rewriting chain.

## 2. Generative quality metrics

### 2.1 Answer Compliance (pass ≥ 80%, advanced ≥ 90%)

**Definition**: the pass rate of answers satisfying every compliance check.

**Checks (0/1 each; all must pass)**:

| Check | Description |
|---|---|
| Grounded | Every fact in the answer can be traced to the retrieved context |
| Cited | Source citations are given (document id / section) |
| On point | The answer addresses the actual question, without drifting |
| Well-formed | The answer follows the agreed structure |
| No fabrication | No facts, numbers or clauses from outside the context |
| No prohibited content | No PII, internal sensitive markers or unauthorised commitments |

**Formula**: `Compliance = answers passing all checks / total scored answers`

**Implementation**: LLM-as-judge emits per-check verdicts and a total against the rubric; a further
≥ 20% sample is human-reviewed and the agreement rate reported.

### 2.2 Style Consistency (pass ≥ 80%, advanced ≥ 0.85)

**Definition**: how closely the answer matches the specification across language, structure and tone;
the average of the three.

| Dimension | Scoring rule |
|---|---|
| Language | Chinese question → Chinese answer, English → English, mixed → dominant language; exact match = 1, partial = 0.5, mismatch = 0 |
| Structure | Follows the standard template (conclusion → evidence → citation) |
| Tone | Objective and concise; no marketing language, no conversational padding |

**Formula**: `StyleConsistency = mean(language, structure, tone)`, range 0–1.

**Caveat**: also express it as a percentage in the report (0.85 = 85%) so it is not confused with the
80% threshold.

### 2.3 Refusal Appropriateness (pass ≥ 80%, advanced ≥ 90%)

**Definition**: two-sided accuracy of "refuse when you should, answer when you should".
**One-sided measurement is gamed by refusing everything — it must be two-sided.**

**Formula**:

```
correct_refusal_rate = correctly refused / total that should be refused
correct_answer_rate  = correctly answered / total that should be answered
RefusalAppropriateness = 2 × correct_refusal_rate × correct_answer_rate
                         / (correct_refusal_rate + correct_answer_rate)      # F1
```

**Refusal triggers (all three must be implemented)**:

1. Low confidence: retrieval score below threshold, or the judge finds the context does not support an answer.
2. Out-of-scope query: no relevant evidence in the corpus (scope classifier combined with retrieval score).
3. Safety rule hit: prompt injection, privilege escalation, disallowed content.

**Refusal output requirement**: never return a bare "I cannot answer" — it must include **guidance**
(the reason category plus a suggested actionable direction).

## 3. Performance metrics

| Metric | Definition | Collection |
|---|---|---|
| End-to-end latency | Request received → full response returned (state explicitly whether streaming) | Per-request instrumentation |
| P50 / P90 / P95 | Latency percentiles; P90 ≤ 10 s is a hard constraint | Evaluation script and production logs |
| Per-stage latency | Rewrite / retrieve / rerank / generate / post-process | Stage spans |
| Concurrency | P90 still ≤ 10 s at ≥ 5 concurrent requests on one instance | k6 / Locust, with hardware and request mix noted |

Suggested latency budget (10 s total):

| Stage | Budget |
|---|---|
| Query rewriting | ≤ 0.5 s |
| Retrieval (vector + BM25 in parallel) | ≤ 0.5 s |
| Reranking | ≤ 0.5 s |
| Generation | ≤ 7 s (the primary optimisation target) |
| Post-processing and network | ≤ 0.5 s |
| Headroom | ≥ 1 s |

## 4. Cost metrics

**Requirement**: give a token-cost estimate per 1,000 calls and explain the quality / cost / latency
trade-offs behind model-version selection.

**Formula**:

```
CostPer1k = 1000 × (avg_prompt_tokens × P_in + avg_completion_tokens × P_out)
```

**Implementation**:

1. Record prompt/completion tokens per request (including judge and embedding calls) and separate
   "service cost" from "evaluation cost" in the report.
2. Maintain a model price table (including cache-hit discounts where applicable).
3. For candidate models (large / small / quantised) give a three-way comparison on the same
   evaluation set: quality, per-call cost, P90 latency.

**Caveat**: the selection conclusion must be data-backed, e.g. "the small model is 6 points lower on
quality but costs 80% less and cuts P90 by 60%", followed by the final choice and its rationale.

## 5. Cache metrics

| Metric | Definition |
|---|---|
| Cache hit rate | Requests served from cache / total requests |
| Cache correctness | Proportion of cache hits whose answers are still correct (guards against stale or wrong hits) |

**Requirement**: the cache hit rate must appear in the operations report, together with the
invalidation strategy (TTL plus invalidation on document updates).

## 6. Operations report fields (mandated by FR4)

| Field | Description |
|---|---|
| p50_latency_ms | Median latency |
| p95_latency_ms | 95th-percentile latency |
| token_usage | prompt / completion / total, grouped by model |
| cache_hit_rate | Cache hit rate |
| refusal_rate | Refusal rate, broken down by reason (low confidence / out-of-scope / safety) |
| answer_compliance_rate | Answer compliance rate |

Output format: both txt (human-readable) and CSV (machine-readable).

## 7. Judge design specification

Several metrics depend on LLM-as-judge, which must be standardised or the metrics are not credible.

| Item | Requirement |
|---|---|
| Model separation | The judge model differs from the generation model, avoiding self-preference |
| Structured output | Fixed JSON schema with per-item verdict, score and rationale |
| Rubric | Clear anchors for each dimension (criteria for 0 / 0.5 / 1) |
| Temperature | temperature=0 with a fixed random seed |
| Human calibration | Hand-review ≥ 20% of samples and report the agreement rate (≥ 0.8 recommended) |
| Stability | Repeated evaluation of the same input yields the same result; report self-consistency |
| Auditability | Persist raw judge output for spot checks and post-mortems |

## 8. Reproducibility requirements

- Fix random seeds and sampling parameters.
- Put model and prompt versions into configuration and record them with each request.
- Version both the evaluation dataset and the evaluation scripts.
- With unchanged data, the one-click script must reproduce identical metrics and reports.
