# RAG + Generative AI Service — Requirements Analysis & Implementation

> Chinese version: [README.md](README.md)

This directory contains both the requirements analysis of `Asst Manager, Backend Developer,AKP.docx`
and a complete implementation built from that analysis — code, configuration, evaluation and reports.
Analysis and implementation map one-to-one; see "Implementation status" below.

## Implementation status

Milestones M0–M7 from [REQUIREMENTS-ANALYSIS.md](docs/REQUIREMENTS-ANALYSIS.en.md) are fully executed.

| Milestone | Content | Status |
|---|---|---|
| M0 | Evaluation dataset + logging/metric skeleton | Done (216 scored units, 38 log fields) |
| M1 | vector-only baseline + structured logs | Done |
| M2 | hybrid + configurable reranking | Done (zero code change) |
| M3 | Refusal, safety, PII | Done (three triggers + dual-path redaction) |
| M4 | One-click evaluation + three-config report | Done (`scripts/eval.py --all`) |
| M5 | Caching + operations report | Done (txt/CSV, all six mandatory fields) |
| M6 | Two issue diagnoses with before/after | Done (real experiments, see diagnosis report) |
| M7 | Documentation close-out | Done (log dictionary, runbook, evaluation report) |

### Three-configuration results (real stack)

Stack: ONNX multilingual embeddings (MiniLM-L12 int8) + bge-reranker-base (ONNX int8 cross-encoder)
+ DeepSeek + LLM judge.

| Metric | C1 vector-only | C2 hybrid | C3 hybrid+rerank | Target |
|---|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | **0.8437** | ≥ 0.70 ✅ |
| Recall@5 | 0.8681 | 0.8160 | **0.9062** | — |
| MRR | 0.6817 | 0.6843 | **0.8472** | — |
| Faithfulness | 0.9984 | **1.0000** | **1.0000** | ≥ 0.85 ✅ |
| Answer Compliance | **0.7824** | 0.7361 | 0.7500 | ≥ 0.80 (2.2% short) |
| Style Consistency | **0.8852** | 0.8827 | 0.8766 | ≥ 0.85 ✅ |
| Refusal Appropriateness | **0.9381** | 0.9094 | 0.9211 | ≥ 0.90 ✅ |
| P90 latency | 1.56 s | 1.71 s | 2.42 s | ≤ 10 s ✅ |

> Conclusion: hybrid beats vector-only, and reranking gives the largest gain on retrieval metrics
> (Context Precision +24% vs C2). **Four of five quality metrics are met, all at the advanced tier**;
> answer compliance is 2.2% short.
> Note that the best-retrieval config (C3) and the best-compliance config (C1) are **not the same**:
> better retrieval makes the model attempt more answers, some of which fail the strict rubric.
> Offline-stage numbers (hash embeddings + rule-based judging) live in `reports/archive/`
> and exist to prove the pipeline and the measurement method itself work.

Full report: [reports/EVALUATION-REPORT.md](reports/EVALUATION-REPORT.en.md)　How to run: [RUNBOOK.md](RUNBOOK.en.md)

## Repository layout

The root keeps only the entry documents and engineering files; documentation lives in `docs/`,
evaluation artefacts in `reports/`.

```
rag_task/
├── README.md                  # Entry point and core conclusions
├── RUNBOOK.md                 # Operations runbook
├── docs/                      # Analysis, design and operations documents
├── reports/                   # Evaluation, acceptance, ops reports (llm/ = real-model artefacts)
├── src/rag/                   # Service implementation
├── scripts/                   # One-click scripts (ingest / evaluate / report / diagnose)
├── configs/                   # Configurations (three configs, real-model, key template)
├── data/                      # Corpus, index, evaluation set
├── models/                    # Local ONNX models
├── logs/                      # Structured logs (JSONL)
├── pyproject.toml / uv.lock   # Dependencies and lock file
├── docker-compose.yml         # Optional components (Qdrant / Redis)
└── .env.example               # API key and endpoint template
```

### Root

| File | Content |
|---|---|
| [README.md](README.en.md) | Index and core conclusions |
| [RUNBOOK.md](RUNBOOK.en.md) | Runbook: environment, commands, configuration reference, real-model switch-over, troubleshooting |

### docs/

| File | Content | Purpose |
|---|---|---|
| [SOURCE-DOC.md](docs/SOURCE-DOC.en.md) | Verbatim extraction of the requirements document (method and completeness check included) | Traceability |
| [REQUIREMENTS-ANALYSIS.md](docs/REQUIREMENTS-ANALYSIS.en.md) | Document nature, requirement map, implicit requirements, ambiguities, scoring traps | Main analysis |
| [METRIC-DEFINITIONS.md](docs/METRIC-DEFINITIONS.en.md) | Metric definitions, formulas, evaluation method, judge design | Removes "undefined metric" risk |
| [ARCHITECTURE-AND-ROADMAP.md](docs/ARCHITECTURE-AND-ROADMAP.en.md) | Target architecture, config model, log field dictionary, milestones, experiment design | Implementation guide |
| [TRACEABILITY-MATRIX.md](docs/TRACEABILITY-MATRIX.en.md) | Requirement → deliverable → evidence → verification matrix | Acceptance self-check |
| [RISKS-AND-OPEN-QUESTIONS.md](docs/RISKS-AND-OPEN-QUESTIONS.en.md) | Risk register, questions for the requester, default assumptions | Risk control |
| [TECH-STACK-SELECTION.md](docs/TECH-STACK-SELECTION.en.md) | Technology selection: per-layer argumentation, rejected options, cost model, model comparison design | Selection decisions |
| [EXECUTION-PLAN.md](docs/EXECUTION-PLAN.en.md) | Execution plan: M0 task breakdown, directory layout, acceptance criteria, explicit no-go list | Next actions |
| [LOG-FIELD-DICTIONARY.md](docs/LOG-FIELD-DICTIONARY.en.md) | Log field dictionary and sample logs (generated from code) | Deliverable |
| [API-KEY-SETUP.md](docs/API-KEY-SETUP.en.md) | API key configuration guide: injection methods, provider endpoints, error triage | Operations guide |
| [Asst Manager, Backend Developer,AKP.docx](<docs/Asst Manager, Backend Developer,AKP.docx>) | Original requirements document | Traceability |

### reports/

| File | Content | Purpose |
|---|---|---|
| [EVALUATION-REPORT.md](reports/EVALUATION-REPORT.en.md) | Evaluation report: method, three-config comparison, target compliance, diagnosis, limitations | Deliverable |
| [ACCEPTANCE-CHECK.md](reports/ACCEPTANCE-CHECK.en.md) | Requirement-by-requirement acceptance check (current verdict) | Acceptance self-check |
| [llm/ACCEPTANCE-CHECK-LLM.md](reports/llm/ACCEPTANCE-CHECK-LLM.en.md) | Real-model acceptance detail and defect-fix log | Deliverable |
| [comparison.md](reports/comparison.en.md) | Three-config comparison table and conclusions | Deliverable |
| [diagnosis_report.md](reports/diagnosis_report.en.md) | Two controlled experiments with before/after data | Deliverable |
| [ops_report_llm_c3_hybrid_rerank.txt](reports/ops_report_llm_c3_hybrid_rerank.txt) | Operations report (txt + CSV) | Deliverable |
| [archive/](reports/archive/) | Historical artefacts from the offline stage and pre-fix labelling | Traceability |

## Core conclusions

1. **Nature of the document**: a technical assessment case study. Only the `Mid-Level Developer` role
   is covered; the "Asst Manager" and "AKP" in the filename have no corresponding sections, so there
   are no hidden requirements.

2. **What the deliverable really is**: a configurable multi-turn RAG QA + generative service over an
   internal bilingual (CN/EN) knowledge base that includes some scanned PDFs. The stack is free, but
   **the score is not about which stack you pick — it is about the quantitative evidence that
   justifies the choice.**

3. **Targets are tiered**: the global constraints give a pass line (Faithfulness ≥ 0.85,
   Context Precision ≥ 0.70, the three generative metrics ≥ 80%), while the non-functional section
   gives an advanced line (90% / 90% / 0.85). Design directly for the advanced line.

4. **The largest hidden cost is the evaluation dataset**: the brief provides no corpus and no labels.
   Faithfulness, Context Precision, Answer Compliance and Refusal Appropriateness all depend on a
   labelled set of questions, gold answers, gold evidence spans and adversarial samples. It must be
   built from scratch and should be the first thing started.

5. **Three requirements most easily missed**: conversational query rewriting for multi-turn (mentioned
   once in the brief), the OCR ingestion path for scanned PDFs, and caching (mentioned only in the
   Objective, yet the operations report mandates a cache hit rate).

6. **One deliverable that must be deliberately engineered**: "at least 2 issue diagnoses with ≥ 10%
   post-fix improvement". If every metric goes green on the first attempt, this requirement cannot be
   delivered — real regressions must be recorded and evidenced with before/after data.

## Suggested next steps

1. Confirm the open questions in [RISKS-AND-OPEN-QUESTIONS.md](docs/RISKS-AND-OPEN-QUESTIONS.en.md);
   for anything that cannot be confirmed, proceed with the documented default assumptions.
2. Start with M0 in [ARCHITECTURE-AND-ROADMAP.md](docs/ARCHITECTURE-AND-ROADMAP.en.md): build the
   evaluation dataset and the logging/metric skeleton before writing retrieval code.
3. As each requirement is completed, use [TRACEABILITY-MATRIX.md](docs/TRACEABILITY-MATRIX.en.md)
   to self-check that the evidence is complete.
