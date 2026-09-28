# Requirements Traceability Matrix and Acceptance Checklist

> Chinese version: [TRACEABILITY-MATRIX.md](TRACEABILITY-MATRIX.md)
> Paragraph references (§n) map to the numbering in [SOURCE-DOC.en.md](SOURCE-DOC.en.md).

## 1. Traceability matrix

| ID | Source | Requirement | Deliverable / implementation | Evidence | Verification |
|---|---|---|---|---|---|
| R1 | §3 | Multi-turn RAG QA + generative service | Service code + session management + query rewriting | Multi-turn conversation samples | Follow-ups resolve references correctly |
| R2 | §3 | Bilingual CN/EN corpus | Multilingual embeddings + Chinese tokenisation | Bilingual retrieval comparison | A Chinese question retrieves English documents |
| R3 | §3 | Scanned PDFs included | OCR ingestion path | OCR quality sampling report | Scanned content is retrievable |
| R4 | §3 | Technology choices must be quantitatively justified | Selection chapter | Controlled experiment data | Every key choice is data-backed |
| R5 | §6 | P90 ≤ 10 s | Parallel retrieval + timeout fallback + caching | Load test and production P90 | Measured P90 ≤ 10 s |
| R6 | §6 | ≥ 5 concurrent on one instance | Concurrency load test | Load-test report (with hardware) | P90 still ≤ 10 s at 5-way concurrency |
| R7 | §8 | Token cost per 1,000 calls | Cost computation + price table | CostPer1k table | Formula, assumptions and result given |
| R8 | §8 | Model-version trade-offs | Model comparison experiment | Quality/cost/latency comparison | Conclusion states explicit trade-offs |
| R9 | §10 | Faithfulness ≥ 0.85 | Judge process | Metric report | Target met and method defined |
| R10 | §10 | Context Precision ≥ 0.70 | Labelled evidence + rank-weighted computation | Metric report | Target met |
| R11 | §11 | Compliance ≥ 80% | Compliance checklist + judge | Metric report | Target met |
| R12 | §11 | Style Consistency ≥ 80% | Three-dimension scoring | Metric report | Target met |
| R13 | §11 | Refusal Appropriateness ≥ 80% | Two-sided measurement | Metric report | Target met |
| R14 | §13 | Structured logs | JSON logs + field dictionary | Field dictionary + sample logs | All fields present and parseable |
| R15 | §15 | Prompt-injection defence | Detection rules / classifier | Adversarial sample results | Injections are blocked or refused |
| R16 | §15 | PII handling | Dual-path redaction (output and logs) | Before/after samples | No plaintext PII in logs or responses |
| R17 | §15 | Strict grounding in retrieved context | Mandatory citations + refusal without evidence | Faithfulness metric | No fabrication outside the context |
| R18 | §17 | Configurable retrieval modes | Configuration file | Three config samples | Switching is a config change |
| R19 | §17 | Reranking | Rerank module + switch | Switch demonstration | Enable/disable without code change |
| R20 | §17 | Caching | Cache layer | Hit-rate report | Hit rate measurable, invalidation defined |
| R21 | §17 | Reproducible diagnosis | Fixed seeds + versioned config | Consistent rerun report | Two reruns agree |
| R22 | §20 | vector-only and hybrid | Two retrieval implementations | Three-config comparison | Both run |
| R23 | §20 | Configurable reranking | See R19 | Configuration file | No code change |
| R24 | §22 | Low-confidence refusal | Threshold + judge | Low-confidence subset test | Correctly refuses with guidance |
| R25 | §22 | Out-of-scope refusal | Scope determination | Out-of-scope subset test | Correctly refuses with guidance |
| R26 | §22 | Safety-rule refusal | Safety policy | Unsafe subset test | Correctly refuses with guidance |
| R27 | §24 | PII redaction (output + logs) | See R16 | Samples | Both paths redacted |
| R28 | §26 | Operations report (txt/CSV) | Report generator | Report files | All six mandatory fields present |
| R29 | §29 | Three-config quantitative comparison and conclusion | Comparison experiment | Comparison table + conclusion | A conclusion is drawn, not just data |
| R30 | §31 | Evolvable design | Interfaces + configuration | Code structure notes | Swapping model/retrieval does not touch callers |
| R31 | §33 | Advanced generative targets | See R11–R13 | Metric report | 90% / 90% / 0.85 reached |
| R32 | §35 | Two issue diagnoses | Diagnosis report | Log evidence + before/after | ≥ 10% improvement each |
| R33 | §37 | Complete code and configs | Repository | Runs | One-click start |
| R34 | §37 | One-click evaluation script | eval script | Single command produces a report | No manual steps |
| R35 | §37 | Evaluation report (before/after) | Report files | Before/after data | Comparisons are clear |
| R36 | §37 | Log field dictionary + sample logs | Documentation | Field table + JSON samples | Consistent with the implementation |

## 2. Final acceptance checklist

### Functionality

- [x] Multi-turn dialogue works and follow-ups are rewritten correctly (`rewrite_query`; rewrite-turn retrieval precision 0.7812 with the real stack)
- [x] Both vector-only and hybrid modes run
- [x] Reranking toggles by configuration, with zero code change
- [x] All three refusal triggers fire and include guidance (`refusal_reason` has counts for each class)
- [x] Output and logs are both PII-redacted
- [x] Operations report generates both txt and CSV

### Metrics

- [x] Faithfulness ≥ 0.85 — measured **1.0000** (real-model run, `reports/llm/`)
- [x] Context Precision ≥ 0.70 — measured **0.8437** (C3 hybrid+rerank)
- [ ] Answer Compliance ≥ 80% / 90% — measured 0.7824 (**2.2% short**; about half of failures are over-refusal)
- [x] Refusal Appropriateness ≥ 90% — measured **0.9381** (all three configs ≥ 0.90)
- [x] Style Consistency ≥ 0.85 — measured 0.8852
- [x] P90 ≤ 10 s and ≥ 5 concurrency — single-threaded P90 2.42 s; 5 concurrent / 50 requests / 0 errors, P90 4.18 s (real model)
- [x] Cost per 1,000 calls with selection rationale — $0.2661–$0.2806 (**example prices; replace with current official prices**)

### Experiments and diagnosis

- [x] Three-config comparison table with an explicit conclusion (hybrid > vector-only; reranking gives the largest gain)
- [x] Two issue diagnoses, each with log evidence and ≥ 10% improvement (Recall@5 +24.2%; correct answer rate +157.2%)
- [x] Results are reproducible (reruns under the same config agree)

### Deliverables

- [x] Complete code and configuration (`src/rag/`, `configs/`)
- [x] One-click evaluation script (`scripts/eval.py`, `scripts/run_all.sh`)
- [x] Evaluation report with before/after (`reports/EVALUATION-REPORT.md`)
- [x] Log field dictionary and sample logs (`docs/LOG-FIELD-DICTIONARY.md`)

### Causes and clearing conditions for the unmet item

| Unmet | Root cause | Clearing condition |
|---|---|---|
| Answer Compliance ≥ 80% | Of 47 non-compliant items, 21 are "should have answered but refused" and 25 are answers failing the judge's rubric | Relax the grounding threshold; strengthen the citation-format prompt |
| Cost basis | Example unit prices still in use | Replace `price_*_per_1m` with current official prices and recompute |

> Measured data and unmet-item causes for the offline stage (hash embeddings + rule judging) are in
> `reports/archive/ACCEPTANCE-CHECK-offline-20260919.md`. That stage validated the pipeline and the
> measurement method; it is not the final verdict.

## 3. Implementation evidence index (R1–R36 → code/data)

The table above is the design view of traceability; below is where each requirement landed in code.

| ID | Implementation | Measured evidence |
|---|---|---|
| R1 Multi-turn | `src/rag/pipeline.py` `rewrite_query` + `src/rag/rewrite.py` | Turns with `requires_rewrite=true` in `reports/llm/items_*.jsonl` |
| R2 Bilingual | `src/rag/retrieve/embedding.py`, `lexical.py` (CJK bigrams) | 78 zh + 78 en evaluation items |
| R3 Scans | `src/rag/ingest/scanned.py` + `parse.py` (RapidOCR) | Ingest log: scanned-document engine `['rapidocr']` |
| R4 Selection rationale | `TECH-STACK-SELECTION.en.md` | — |
| R5 Latency | `scripts/loadtest.py` | `reports/llm/loadtest.json` (5 concurrent / 50 requests, P90 4.18 s, real model) |
| R6 Concurrency | same | 5 concurrent, 0 errors |
| R7 Cost | `src/rag/pipeline.py` cost computation + price fields in `configs/base.yaml` | `cost_usd_per_1k_calls` in `reports/ops_report_*.txt` |
| R8 Model selection | `configs/base.yaml` generation section | Report section 6 (to be regenerated with current prices) |
| R9 Faithfulness | `src/rag/guardrails/support_score` + `eval/judge.py` (LLM judge) | `reports/llm/eval_llm_c*.json` |
| R10 Context Precision | `src/rag/eval/metrics.py` | `reports/llm/comparison.md` |
| R11–R13 Generative quality | `src/rag/eval/judge.py` (LLM judge) | `reports/llm/eval_llm_c*.json` |
| R14 Structured logs | `src/rag/observability.py` | `docs/LOG-FIELD-DICTIONARY.md` |
| R15 Injection defence | `src/rag/guardrails/INJECTION_PATTERNS` | 20-case unsafe subset (20/20 intercepted) |
| R16 PII | `src/rag/pii.py` + `observability._redact_processor` | `pii_redacted_fields` in logs |
| R17 Strict grounding | `pipeline` grounding check + citation requirement | `compliance.checks.grounded` in `reports/llm/items_*.jsonl` |
| R18–R19 Modes / rerank switch | `configs/llm_c1..c3*.yaml` | Change config only; `reports/llm/comparison.md` |
| R20 Caching | `src/rag/cache/` | Cache hit rate in `reports/ops_report_c3_hybrid_rerank.txt`; disabled during evaluation by design |
| R21 Reproducibility | `Config.fingerprint()` written to logs | `config_fingerprint` in logs |
| R22–R23 | as R18–R19 | as R18–R19 |
| R24–R26 Refusal | `src/rag/guardrails/` + pipeline guardrail stage | `refusal_reason` counts per class in logs |
| R27 Dual-path PII | as R16 | Both output and logs redacted |
| R28 Operations report | `scripts/report.py` | `reports/ops_report_*.txt/.csv` |
| R29 Three-config comparison | `scripts/eval.py --all` | `reports/llm/comparison.md` |
| R30 Evolvability | Fully parameterised `Config` + `Retriever`/`Generator` interfaces | Backend swaps are YAML-only |
| R31 Advanced targets | as R11–R13 | Section 4 of the evaluation report |
| R32 Issue diagnosis | `scripts/diagnose.py` | `reports/diagnosis_report.md` |
| R33–R34 Code and one-click scripts | `src/`, `scripts/run_all.sh` | — |
| R35 Evaluation report | `scripts/gen_eval_report.py` | `reports/EVALUATION-REPORT.md` |
| R36 Log dictionary | `scripts/gen_log_docs.py` | `docs/LOG-FIELD-DICTIONARY.md` |
