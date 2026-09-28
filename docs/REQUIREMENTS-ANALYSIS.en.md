# Requirements Analysis

> Chinese version: [REQUIREMENTS-ANALYSIS.md](REQUIREMENTS-ANALYSIS.md)

Source document: `Asst Manager, Backend Developer,AKP.docx` (verbatim text in [SOURCE-DOC.en.md](SOURCE-DOC.en.md))

## 1. What kind of document this is

This is a **technical assessment case study**, not a client requirements specification. Evidence:

- The title is `Case Study – RAG + Generative AI Service`, subtitle `Role: Mid-Level Developer`.
- There is no business owner, no background context, no existing system and no data source — none of
  the things a real specification always contains.
- It states plainly: "Candidates may choose any tech stack, but all key technical choices must be
  justified in the deliverables with clear, quantitative evidence and validation." That is assessment
  language: **the score is not about the stack, it is about the quantitative evidence chain behind it.**

**The filename does not match the content.** The filename carries three labels — `Asst Manager`,
`Backend Developer`, `AKP` — but the body covers only `Mid-Level Developer`. There are no management
or AKP sections, so do not assume hidden requirements; if those are genuinely needed, request them
separately.

## 2. Requirement map

The document reads at four levels. L1 is the pass line; item 3 of L3 is the advanced tier.

### L1 Global constraints

Apply to this role unless overridden below.

| Area | Requirement |
|---|---|
| Performance | 90% of QA requests complete end-to-end within 10 s; ≥ 5 concurrent requests on a single instance |
| Cost | Token-cost estimate per 1,000 calls; model-version rationale must state quality / cost / latency trade-offs |
| Quality | RAG: Faithfulness ≥ 0.85 (define your own evaluation method); Context Precision ≥ 0.70 |
| Generative quality | Answer Compliance ≥ 80%; Style Consistency ≥ 80%; Refusal Appropriateness ≥ 80% |
| Logging & tracing | Structured logs sufficient for generation monitoring and issue diagnosis |
| Security | Minimal prompt-injection defences; basic PII handling; all answers strictly grounded in retrieved context |

### L2 Functional requirements

| ID | Requirement | Key point |
|---|---|---|
| FR1 | Retrieval controls | At least two modes: vector-only and hybrid; the reranker switch **must be configuration-driven, with no code change** |
| FR2 | Refusal & safety | Three triggers — low confidence, out-of-scope query, safety rule hit — must return a **refusal with guidance** |
| FR3 | Privacy | PII redaction must cover **both outputs and logs** |
| FR4 | Operations report | txt/CSV output, mandatorily containing: p50/p95 latency, token usage, cache hit rate, refusal rate, answer compliance rate |

### L3 Non-functional and quantitative metrics

| ID | Requirement | Key point |
|---|---|---|
| NFR1 | Retrieval quality | Compare three configurations — vector-only / hybrid / hybrid+rerank — and **give quantitative results and a conclusion** |
| NFR2 | Evolvability | Retrieval strategy, model version, metrics and logging must all be replaceable/extensible |
| NFR3 | Generative quality (advanced) | Answer Compliance ≥ 90%; Refusal Appropriateness ≥ 90%; Style Consistency ≥ 0.85 |
| NFR4 | Issue diagnosis | At least 2 issues, each with log/metric evidence, a fix rationale, and **≥ 10% post-fix improvement** |

### L4 Deliverables

| Deliverable | Notes |
|---|---|
| Complete code and configuration | Including configurable retrieval / rerank / model / thresholds |
| One-click evaluation script | A single command produces every metric |
| Evaluation report | Must contain before/after comparisons |
| Log field dictionary + sample logs | Field meaning, type, example |

## 3. All hard targets at a glance

| Dimension | Pass line (L1) | Advanced line (L3.3) |
|---|---|---|
| End-to-end latency | P90 ≤ 10 s | — |
| Concurrency | ≥ 5 concurrent / single instance | — |
| Cost | Token cost per 1,000 calls + selection trade-offs | — |
| Faithfulness | ≥ 0.85 | — |
| Context Precision | ≥ 0.70 | — |
| Answer Compliance | ≥ 80% | ≥ 90% |
| Style Consistency | ≥ 80% | ≥ 0.85 |
| Refusal Appropriateness | ≥ 80% | ≥ 90% |
| Post-fix improvement | — | ≥ 10% × 2 issues |

Note the mixed units: compliance uses percentages (80%/90%) while Style Consistency uses 0–1
(80%/0.85). The values are equivalent, but **the report should normalise the notation** so the
reviewer cannot misread it.

## 4. Implicit requirements the brief never states

1. **A labelled evaluation dataset (highest priority).** The brief provides no corpus at all.
   Faithfulness, Context Precision and Compliance all need question + gold answer + gold evidence
   spans, and Refusal Appropriateness additionally needs out-of-scope, unsafe and low-confidence
   adversarial samples. This set must be built from scratch and started before any retrieval code.
2. **Multi-turn capability.** Mentioned once, in paragraph 3, yet it is the business premise of the
   whole brief. It requires session state, coreference resolution and query rewriting (turning "what
   about its effective date?" into a standalone query), plus multi-turn evaluation samples. Missing
   it directly suppresses Context Precision.
3. **An OCR ingestion path for scanned PDFs.** Paragraph 3 mentions "a small portion of scanned
   PDFs", which means parsing + OCR + layout cleanup + quality checks at ingestion. OCR quality is the
   ceiling on retrieval quality.
4. **Bilingual handling.** A mixed CN/EN corpus implies multilingual embeddings, language detection
   and cross-lingual retrieval; the BM25 side needs Chinese tokenisation, otherwise hybrid degrades
   into English keyword matching.
5. **Caching.** "caching" appears once, in the Objective, and is never listed as a functional
   requirement — yet FR4 mandates reporting a cache hit rate. Caching is therefore a hard implicit
   requirement, and it must be measurable (exact vs semantic cache, TTL, invalidation on document
   updates).
6. **Diagnosable log depth.** NFR4 requires locating 2 issues from log/metric evidence, which implies
   logs must at minimum carry: trace/request IDs, per-stage latency, retrieval and rerank scores,
   **a configuration snapshot per request**, and token usage. The configuration snapshot is the
   critical one — without it, neither the three-config comparison nor any before/after data is
   trustworthy.
7. **Mandatory grounding.** "all answers must strictly ground to retrieved context" means answers
   must carry evidence citations, and "no evidence → refuse" should be the default policy.
8. **Reproducibility.** "reproducible diagnosis" in the Objective requires fixed random seeds,
   pinned model versions and parameterised configuration, so that a one-click rerun yields a
   consistent report.
9. **Cost accounting capability.** Cost per 1,000 calls requires per-request token accounting, a
   price table and an average-token assumption — it cannot be estimated by guesswork.

## 5. Ambiguities and recommended definitions

The brief leaves the hardest parts undefined. The deliverables must state "definition + implementation"
explicitly, otherwise the metrics cannot be accepted. Full definitions are in
[METRIC-DEFINITIONS.en.md](METRIC-DEFINITIONS.en.md); overview below:

| Ambiguous term | Problem | Recommended definition |
|---|---|---|
| Answer Compliance | Undefined | Rubric-based LLM-as-judge pass rate: strictly grounded in retrieved evidence, cites sources, follows the answer format, contains no fabrication |
| Style Consistency | Undefined | Multi-dimensional 0–1 score: answer language follows the question, consistent structure, consistent tone |
| Faithfulness | Brief says "define your evaluation method" | Claim-level entailment: split into atomic claims, check each against the context |
| Context Precision | Undefined | Rank-weighted hit rate over labelled evidence spans |
| Refusal Appropriateness | Undefined | **Two-sided**: correct refusals plus non-over-refusal, combined as balanced accuracy |
| End-to-end latency | Boundary undefined | Define as "request received → full response returned" (or declare first-token), and measure it |
| ≥ 5 concurrent | Scenario undefined | Define the concurrency model, request mix, duration and hardware |
| "low confidence" | Threshold undefined | Retrieval-score threshold combined with a judge and a scope classifier |
| Corpus size | Not given | Assume document count / pages / total tokens and state it in the report |

## 6. Scoring traps and high-risk points

1. **The "2 issue diagnoses" must be engineered deliberately.** If every metric goes green first time,
   that requirement cannot be delivered; real regressions must be recorded during development with
   before/after data retained (candidate scenarios in [ARCHITECTURE-AND-ROADMAP.en.md](ARCHITECTURE-AND-ROADMAP.en.md)).
2. **Self-judging loop.** Using one model to both generate and score invites challenge. Use different
   models for generation and judging, hand-verify a subset, and report judge/human agreement.
3. **The three-config comparison can be non-comparable.** Fix the evaluation set, prompt and generation
   model; vary only the retrieval configuration; lock everything with configuration snapshots and
   version numbers.
4. **Compounding latency constraints.** The 10 s P90 must accommodate reranking *and* generation, so
   parallel retrieval, timeout fallback and result caching are required or P90 will slip.
5. **PII redaction versus debuggability.** Logs must be both redacted and traceable — prefer hashes or
   placeholders over deleting fields outright.
6. **Mixed metric units.** Percentages and 0–1 values are interleaved; normalise and annotate in the report.
7. **hybrid is not automatically better.** Adding BM25 introduces lexical noise and can lower Context
   Precision. That is both a risk and natural material for the NFR4 diagnosis.

## 7. Recommended execution order

| Stage | Content | Why here |
|---|---|---|
| M0 | Evaluation dataset + logging/metric skeleton | Without it, none of the later "quantitative evidence" exists |
| M1 | vector-only baseline + structured logs | Establishes a comparable starting point |
| M2 | hybrid + configurable reranking | Satisfies FR1 and produces the three-config comparison |
| M3 | Refusal, safety, PII | Satisfies FR2/FR3 and the security constraints |
| M4 | One-click evaluation script + three-config report | Satisfies NFR1 and the deliverable list |
| M5 | Caching + operations report | Satisfies FR4 and the Objective |
| M6 | Two issue diagnoses with before/after | Satisfies NFR4 (depends on M1–M5 logs) |
| M7 | Documentation, configuration notes, log dictionary | Closes out the deliverables |

Detailed task breakdown: [ARCHITECTURE-AND-ROADMAP.en.md](ARCHITECTURE-AND-ROADMAP.en.md).
