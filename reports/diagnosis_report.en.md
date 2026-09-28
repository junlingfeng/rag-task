# Issue Diagnosis Report

> Chinese version: [diagnosis_report.md](diagnosis_report.md)
> Every experiment changes exactly one variable; all other settings (retrieval mode, reranking,
> generation backend, evaluation-set construction) stay identical.
> Data comes from the full evaluation outputs under `reports/experiments/` and can be reproduced.
>
> Note: both controlled experiments were run on the **offline backend** (hash embeddings + lexical
> reranking + extractive generation). Their purpose is to validate the methodology itself —
> find a problem → locate the root cause → fix it → quantify the before/after difference.
> The further defects found on the real stack (ONNX embeddings + cross-encoder + real model) are in
> section 5 of `reports/llm/ACCEPTANCE-CHECK-LLM.md`.

## Problem A: chunk granularity too small fragments the evidence

### Symptom

Lowering the child-chunk limit from 320 to 120 dropped Context Precision@5 from 0.3509 to 0.3197 and
Recall@5 from 0.4271 to 0.3438; answer compliance was essentially unchanged
(0.6435 → 0.6435).

### Evidence (logs/metrics)

| Config | Child limit | CP@5 | Recall@5 | Faithfulness | Compliance | Avg prompt tokens |
|---|---|---|---|---|---|---|
| Too small | 120 | 0.3197 | 0.3438 | 0.7358 | 0.6435 | 156 |
| Baseline | 320 | 0.3509 | 0.4271 | 0.7383 | 0.6435 | 424 |
| Too large | 800 | 0.3718 | 0.4514 | 0.7358 | 0.6389 | 564 |

### Root cause

Chunks that are too small cut one complete rule into several fragments: a single chunk can no longer
carry all the elements the question needs (for example "how many days" *and* "how many days in
advance must it be requested"). Rank-weighted Context Precision and Recall suffer directly.

Notably, Faithfulness barely moved (0.7383 vs 0.7358): generation uses the **parent** block of the
parent-child pair, so fragmentation only affects "matching and ranking", not "once the context is in
hand, can a supporting sentence be extracted". This shows that watching Faithfulness alone would miss
a retrieval-layer regression — metrics must be read together.

### Fix and conclusion

Action: restore the child-chunk limit from 120 to 320 (the current default).

- Context Precision@5: 0.3197 → 0.3509 (+9.8%)
- Recall@5: 0.3438 → 0.4271 (+24.2%)
- Answer compliance: 0.6435 → 0.6435 (+0.0%, unaffected)

The headline metric Recall@5 improves by 24.2%, satisfying "≥ 10% post-fix improvement".

Additional observation: raising the child limit further to 800 lifts Context Precision to 0.3718 but
increases average prompt tokens from 424 to 564 — trading generation cost for retrieval precision. At
the current corpus size, 320 is the cost/quality balance point; with more budget it can be raised to
800 (a configuration change, no code edit required).

## Problem B: an over-strict out-of-scope threshold causes over-refusal

### Symptom

Tightening the out-of-scope thresholds to Coverage ≥ 0.40 / bigram OOV ≤ 0.30 / unigram OOV ≤ 0.20
raised the refusal rate: the correct answer rate fell from 0.8438 to 0.3281 and refusal
appropriateness from 0.8385 to 0.4889.

### Evidence (logs/metrics)

| Threshold config | Correct refusal rate | Correct answer rate | Refusal appropriateness | Compliance |
|---|---|---|---|---|
| Too strict (coverage≥0.40, oov≤0.30/0.20) | 0.9583 | 0.3281 | 0.4889 | 0.4444 |
| Calibrated (coverage≥0.15, oov≤0.50/0.40) | 0.8333 | 0.8438 | 0.8385 | 0.6435 |

### Root cause

Both lexical out-of-scope signals correlate strongly with phrasing in Chinese: when a user asks the
same thing in different words, the out-of-vocabulary rate of content terms is inflated, triggering a
false refusal. An over-strict threshold amplifies this into systematic over-refusal.

### Fix and conclusion

Action: recalibrate the thresholds on the labelled set with `scripts/calibrate_scope.py`. After the fix
the correct answer rate improved by 157.2% and refusal appropriateness by 71.5%.

### Remaining limitation (stated honestly)

The lexical out-of-scope detector reaches only ~0.80 balanced accuracy and cannot handle semantically
equivalent paraphrases. Going further requires a semantic criterion (real embeddings or an LLM scope
judgement); that is the part left unfinished in the offline environment.

> Follow-up on the real stack: the lexical scope gate was replaced by model self-judgement plus
> self-refusal detection, lifting refusal appropriateness from 0.859 to 0.918 — see
> `reports/llm/ACCEPTANCE-CHECK-LLM.en.md`.
