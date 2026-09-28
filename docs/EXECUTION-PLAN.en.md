# Execution Plan

> Version: v1.0　Date: 2026-09-18
> Chinese version: [EXECUTION-PLAN.md](EXECUTION-PLAN.md)
> Upstream: [REQUIREMENTS-ANALYSIS.en.md](REQUIREMENTS-ANALYSIS.en.md), [ARCHITECTURE-AND-ROADMAP.en.md](ARCHITECTURE-AND-ROADMAP.en.md), [TECH-STACK-SELECTION.en.md](TECH-STACK-SELECTION.en.md)
>
> **Status note**: this is the plan written *before* implementation, kept verbatim as a historical
> artefact. It was executed in full (M0–M7); the outcome is recorded in
> [reports/EVALUATION-REPORT.md](../reports/EVALUATION-REPORT.en.md) and
> [README.md](../README.en.md).

## 1. Current state and critical path

Completed: requirements analysis, metric definitions, architecture and roadmap, traceability matrix,
risk register, technology selection.
Completion level: **100% on paper, 0% code, 0% corpus, 0% data.**

Every acceptance criterion in this case study is a quantitative metric, and quantitative metrics need
two things that do not yet exist: **a service that runs** and **an evaluation set that can be scored**.
The critical path is therefore:

```
Environment + skeleton ──► real latency baseline ──┐
                                                    ├──► three-config comparison ──► diagnosis ──► report
Corpus + evaluation set ───────────────────────────┘
```

Two parallel chains; missing either one means nothing can be delivered. They are also the two
longest-running chains and must be started first.

**The classic mistake**: spending days finishing retrieval, reranking, caching and logging, only to
discover there is no evaluation set and not a single metric can be computed — or discovering that
local embedding takes 800 ms per query, invalidating the entire latency budget.

## 2. Next step: the four M0 work items

### T0 Environment and walking skeleton (highest priority, ~half a day)

Goal: **drive the thinnest possible path from document → retrieval → generation → log**, purely to
obtain two real numbers.

| Step | Action | Output |
|---|---|---|
| Environment | `uv python install 3.12` + project virtualenv (system Python 3.8.2 is unusable) | `.python-version`, `pyproject.toml` |
| Dependencies | Qdrant + Redis via Docker Compose, single node | `docker-compose.yml` |
| Minimal path | 20 documents ingested → one question → one cited answer | `scripts/ingest.py`, `scripts/ask.py` |
| Instrumentation | One JSON log line per stage | `logs/*.jsonl` |

**Acceptance criteria (real measured numbers required)**:

- embedding latency for a single query (decides whether the estimates in §2.4 hold)
- reranking latency over 20 candidates (decides whether to cut to 10 candidates or use a smaller model)
- end-to-end latency breakdown for one full question-answer cycle

These three numbers **decide whether the latency budget is viable at all**, and whether the estimates
in [TECH-STACK-SELECTION.en.md](TECH-STACK-SELECTION.en.md) survive or must be discarded. Do not write
a second line of retrieval code before you have them.

### T1 Corpus construction (start in parallel, ~1 day)

The brief supplies no corpus at all — the largest vacuum in the task.

| Question | How to handle it |
|---|---|
| Are real internal documents available? | Prefer real documents; redact carefully and never use real PII |
| If not? | Synthesise a bilingual corpus across four types (handbook, compliance guide, technical spec, architecture doc) including 2–3 scanned (image-only) PDFs |
| Scale | 30–60 documents, 5k–20k chunks — enough to expose differences between hybrid and rerank |
| What must be synthetic | The scanned documents are mandatory, otherwise neither OCR nor the "small portion of scanned PDFs" requirement is exercised |

Output: `data/corpus/raw/` source documents, `data/corpus/processed/` parse results, and a corpus
manifest (doc_id, language, type, is_scanned, page count).

### T2 Evaluation set construction (start in parallel, most critical, ~1.5 days)

Build the six subsets defined in [METRIC-DEFINITIONS.en.md](METRIC-DEFINITIONS.en.md):

| Subset | Size | Key fields |
|---|---|---|
| Single-turn answerable | ≥ 100 | question, gold_answer, gold_chunk_ids, lang |
| Multi-turn conversations | ≥ 20 | turns[], follow-ups that require rewriting |
| Out-of-scope | ≥ 30 | no answer in the corpus |
| Unsafe | ≥ 20 | injection, privilege escalation |
| Low confidence | ≥ 20 | near-miss, no firm basis |
| Bilingual / mixed | balanced | Chinese question over an English document |

**Build a 20-item minimum viable version first**, use it to calibrate the metric scripts, then expand.
Do not label all 200 items only to discover the labelling convention was wrong.

Output: `data/eval/*.jsonl` plus `data/eval/README.md` (labelling convention and version).

### T3 Metric script skeleton (~1 day)

Implement the computation framework first, without chasing judge accuracy: read the evaluation set →
call the service → call the judge → emit metrics → produce CSV.

**Acceptance criterion**: Faithfulness and Context Precision can be produced on the 20-item set, even
if the values look bad.

## 3. Recommended directory layout

```
rag_task/
├── *.md                      # analysis documents (left in place)
├── configs/
│   ├── base.yaml             # shared configuration
│   ├── c1_vector.yaml        # vector-only
│   ├── c2_hybrid.yaml        # hybrid
│   └── c3_hybrid_rerank.yaml # hybrid + rerank
├── src/rag/
│   ├── ingest/               # parsing, OCR, chunking, indexing
│   ├── retrieve/             # vector, BM25/sparse, fusion
│   ├── rerank/
│   ├── generate/
│   ├── guardrails/           # injection detection, refusal, PII
│   ├── cache/
│   ├── observability/        # logging, spans, field definitions
│   ├── eval/                 # judge, metrics, reports
│   └── api/                  # FastAPI
├── data/
│   ├── corpus/raw/           # source documents (including scans)
│   ├── corpus/processed/     # parsed text and metadata
│   └── eval/                 # evaluation set
├── scripts/
│   ├── ingest.py
│   ├── ask.py                # single question (debugging)
│   ├── eval.py               # one-click evaluation
│   ├── report.py             # operations report
│   └── loadtest.js           # k6 load test
├── logs/                     # JSONL logs
└── reports/                  # evaluation and operations reports
```

## 4. What explicitly NOT to do now

| Don't | Why |
|---|---|
| Write the cache or semantic cache first | Cache hit rate is a reported metric, but without baseline data there is no way to tell whether caching improved anything |
| Build PII and injection detection first | That is M3, and it depends on the log fields being frozen |
| Integrate several generation models for comparison | Without an evaluation set the comparison is meaningless |
| Build a front end | The brief only requires an API |
| Refactor for code structure | Diagnosis needs observable real data first; refactoring belongs after M6 |
| Chase 90% on the metrics immediately | Hitting targets is an outcome — first make the pipeline run and produce trustworthy numbers |

## 5. Order after M0 completes

| Stage | Content | Prerequisite |
|---|---|---|
| M1 | vector-only baseline + structured logs | T0 + T1 + T2 |
| M2 | hybrid + configurable reranking | M1 |
| M3 | Refusal, safety, PII | M1 (log fields must be frozen) |
| M4 | One-click evaluation + three-config report | M2 + T3 |
| M5 | Caching + operations report | M4 (a baseline is needed to demonstrate the value of caching) |
| M6 | Two issue diagnoses with before/after | Logs accumulated through M1–M5 |
| M7 | Documentation close-out (log dictionary, README, configuration notes) | All of the above |

## 6. One decision to confirm

**Where does the corpus come from?** This changes how T1 is executed, but does not block T0:

| Option | Impact |
|---|---|
| A. Real internal documents are available | Redact first; high corpus quality, realistic OCR and bilingual scenarios |
| B. None available — synthesise | Generate four bilingual document types plus scanned files; fully controllable, but realism must be maintained |
| C. Substitute a public dataset | Fastest, but bilingual coverage and scanned files must be filled in manually |

**Default assumption: option B** — synthesise a bilingual corpus with self-made scanned documents,
because it depends on nothing external and covers exactly the four document types and the scanned-file
scenario the brief describes. If real documents exist, say so: switching to A materially improves how
much the evaluation can be trusted.

## 7. The first step that can start immediately

Regardless of which corpus option is chosen, T0 can start now, and its output — real latency numbers —
is the prerequisite for everything downstream.
