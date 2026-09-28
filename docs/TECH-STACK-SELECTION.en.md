# Technology Stack Selection

> Version: v1.0　Date: 2026-09-18
> Chinese version: [TECH-STACK-SELECTION.md](TECH-STACK-SELECTION.md)
> Upstream: [REQUIREMENTS-ANALYSIS.en.md](REQUIREMENTS-ANALYSIS.en.md), [METRIC-DEFINITIONS.en.md](METRIC-DEFINITIONS.en.md), [ARCHITECTURE-AND-ROADMAP.en.md](ARCHITECTURE-AND-ROADMAP.en.md)
>
> **Post-implementation deltas** (added 2026-09-25): this document is the selection-stage analysis.
> Four choices differ from what is recommended here, each adjusted on measured data — see section 5 of
> [RUNBOOK.md](../RUNBOOK.en.md) and `reports/llm/ACCEPTANCE-CHECK-LLM.en.md`:
> 1. **Vector store**: an in-process NumPy store was shipped (zero dependencies, one-click
>    reproducibility); Qdrant/Redis remain optional backends.
> 2. **Embeddings**: MiniLM-L12 int8 (ONNX, 113 MB) instead of bge-m3 — this machine has no PyTorch and
>    bge-m3 needs 2.2 GB; measured cross-lingual similarity is 0.821, which is workable.
> 3. **Reranking**: bge-reranker-base as selected, but via ONNX int8; the critical parameter is
>    `max_candidates: 10` (20 candidates need 1553 ms and blow the 800 ms budget).
> 4. **Fusion**: once real embeddings were in place, weighted fusion (vector_weight 0.7) measured
>    better than RRF and became the default.

## 0. What the selection is judged against

The brief states: "Candidates may choose any tech stack, but all key technical choices must be
justified in the deliverables with clear, quantitative evidence and validation." So **correctness is
not decided by technical sophistication but by whether you can prove with data that a choice is
optimal under the constraints.** Four selection criteria follow:

| Criterion | Source | Meaning |
|---|---|---|
| C1 Latency and concurrency | §6: P90 ≤ 10 s, ≥ 5 concurrent on one instance | Any component with unbounded latency must have a timeout fallback |
| C2 Quantifiable comparison | §29: three-config quantitative comparison | Retrieval / rerank / generation must be swappable on the same evaluation set for controlled experiments |
| C3 Evolvability | §31: change retrieval strategy or model, extend metrics, without architectural change | Components must be interface- and configuration-driven; models behind an OpenAI-compatible abstraction |
| C4 Runs and reproduces locally | Objective: reproducible diagnosis | The one-click script must run end-to-end on a single machine |

### 0.1 Measured local environment (decides what can actually run)

| Item | Measured | Impact on selection |
|---|---|---|
| CPU | Intel i9-9880H (2.3 GHz, 8 cores / 16 threads) | No CUDA, no Metal GPU acceleration |
| Memory | 16 GB | Tight budget for Docker + vector store + local models |
| OS | macOS 14.8.9 (Intel) | Apple Silicon MPS acceleration unavailable |
| Python | System 3.8.2 | **Too old**; bge-m3, Pydantic v2 and PaddleOCR all need ≥ 3.9/3.10 |
| Package manager | `uv` installed | Can fetch Python 3.11/3.12 without touching the system environment |
| Docker | 24.0.7 + Compose v2.23.3 | Single-machine multi-container is viable |
| Node | v22.22.1 | Can run k6 / a front-end demo |
| Java | JDK 8 only | Rules out modern Spring AI on JDK 8 (needs 17+) |
| Ollama | Installed, not running, no models | Local generation would need a multi-GB download first |

**Two hard conclusions follow**:

1. **Local generation models are not viable.** A quantised 7B model on a 16 GB Intel CPU typically
   reaches single-digit tokens/s (measure it yourself), while one answer needs ~250 tokens and the
   target is P90 ≤ 10 s at 5-way concurrency — the orders of magnitude do not match. Generation must go
   through an API; a local model survives only as a "data never leaves the intranet" fallback, stated
   honestly as failing the target.
2. **The Python version must be provisioned locally.** `uv python install 3.12` for a project-level
   environment is the first action of M0.

## 1. Selection at a glance

| Layer | Primary | Alternative | Rejected | Core reason |
|---|---|---|---|---|
| Service language/framework | Python 3.12 + FastAPI + Pydantic v2 | Node + NestJS | Spring Boot (only JDK 8 here) | The RAG ecosystem (models, evaluation, parsing) is most complete in Python, with the least glue |
| Document parsing | PyMuPDF + Docling | Unstructured | Pure regex parsing | Preserves layout and reading order, handles tables, works bilingually |
| OCR | RapidOCR (ONNXRuntime) | PaddleOCR (accuracy first) | Tesseract | Chinese accuracy plus no heavy paddlepaddle dependency; Intel-CPU friendly |
| Chunking | Structure-aware recursive + parent-child (small-to-big) | Fixed length | Pure semantic | Balances Context Precision (small hits) and Faithfulness (parent fills context) |
| Embeddings | bge-m3 (local ONNX int8) | text-embedding-3-large (API) | Monolingual models | CN/EN bilingual, long context, emits both dense and sparse vectors |
| Vector store and retrieval | Qdrant single node (dense + sparse + RRF fusion) | OpenSearch / Elasticsearch | Milvus, faiss-only | Native hybrid fusion, small footprint, single-machine Docker friendly |
| Reranking | bge-reranker-base / jina-reranker-v2-base (local) | Cohere Rerank API | No reranker | A 278M-class cross-encoder is manageable on CPU; larger models need a GPU |
| Generation model | Small model primary + mid model fallback (OpenAI-compatible API) | Flagship model | Local 7B model | Latency and cost are viable, and switching enables the three-way comparison |
| Orchestration | Thin in-house pipeline | LlamaIndex (ingestion only) | Heavy LangChain chains | Per-stage latency and scores must be attributable; a black-box framework destroys diagnosability |
| Caching | Redis (exact) + vector semantic cache | Exact only | No cache | Hit rate is mandated by FR4 |
| Logging/tracing | structlog JSONL + OpenTelemetry spans | Self-hosted Langfuse | Plain-text logs | Structured logs serve both the operations report and issue diagnosis |
| Evaluation | In-house metric scripts + LLM-as-judge, cross-checked with RAGAS | Use RAGAS directly | Manual scoring | Keep ownership of the metric definitions; RAGAS is a second opinion |
| Security | Rules + classifier for injection, Presidio/regex for PII | Rules only | No protection | Must report both interception and false-interception rates |
| Load testing | k6 | Locust | Hand-written scripts | Concurrency and P90 need reproducible evidence |
| Deployment | Single-machine Docker Compose | Single process + local deps | K8s | The brief only requires ≥ 5 concurrency on one instance |

## 2. Layer-by-layer argumentation

### 2.1 Language and framework: Python 3.12 + FastAPI (and why not Java)

The precise version of the conclusion: **Java can absolutely build this service. This is not a
question of feasibility but of how much verifiable evidence each unit of work buys.** Python wins not
because of language performance but because **the deliverable's centre of gravity sits in the model
and evaluation toolchain, where Python is the first-class citizen.**

#### 2.1.1 Candidates

| Candidate | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| Python + FastAPI | embedding / rerank / OCR / evaluation / data analysis all first-class; async IO covers 5-way concurrency; Pydantic for config validation | Requires provisioning Python (system 3.8.2; `uv` solves it) | **Primary** |
| Java + Spring Boot | Most mature engineering governance (DI, transactions, Actuator, Micrometer); Lucene/ES native on the JVM; strong Chinese tokenisers | JDK 8 only here; no first-class OCR; no evaluation frameworks; model adapters must be built | Alternative, better only under specific conditions (2.1.7) |
| Node + NestJS | Same stack as k6 / the front end | Almost every critical capability would fall back to a Python service — two runtimes | Rejected |

#### 2.1.2 The decisive factor: where the work actually sits

The case study looks like "a service" but its centre of gravity is **experimentation and evaluation**.
Decomposing the deliverable (estimates, to be calibrated during execution):

| Work block | Estimated share | Which language wins |
|---|---|---|
| Evaluation dataset construction and labelling | ~25% | Language-neutral (human work) |
| Parsing / OCR / chunking experiments | ~15% | **Python** (docling, PyMuPDF, RapidOCR, MinerU are Python-only) |
| Retrieval and reranking implementation | ~15% | Even, leaning Python (model side is smoother) |
| Generation and guardrails | ~15% | Even (both have SDKs) |
| Evaluation, metric computation and reporting | ~20% | **Python** (RAGAS / DeepEval / pandas / matplotlib are Python-only) |
| Service, configuration, logging, caching | ~10% | **Java** |

**The part Java wins is only ~10%, while Python's advantage or monopoly covers over 50%.** A
deliverable has one language, so choosing Python concentrates effort where most of the work is. For a
high-concurrency transactional service the ratio would invert — which is why I would pick Java in
other scenarios.

#### 2.1.3 Capability-by-capability comparison

| Capability | Python | Java | Winner |
|---|---|---|---|
| PDF parsing, layout and reading order | PyMuPDF, pdfplumber, docling, MinerU, marker | PDFBox, Tika (good text extraction, weak layout/tables) | Python |
| OCR (Chinese + tables) | PaddleOCR, RapidOCR, docling | Tess4J (a Tesseract wrapper); no PaddleOCR equivalent | **Python (largest gap)** |
| Running embedding models | FlagEmbedding, sentence-transformers, transformers out of the box | DJL + ONNX Runtime works and `ai.djl.huggingface:tokenizers` provides tokenisation, but export, quantisation and pooling are yours to handle | Python |
| Running rerank models | Same, cross-encoders ready-made | As embeddings; build it yourself | Python |
| Chinese tokenisation / BM25 | jieba, pkuseg | HanLP, ansj, jieba-analysis, Lucene IK/smartcn | **Java** (but bge-m3 sparse vectors can bypass the dependency) |
| Vector store clients | Qdrant / Milvus / ES all have clients | Equally complete; the ES client is first-class | Even |
| Hybrid fusion | Relies on server-side fusion | Can embed Lucene and build it | Even, leaning Java |
| LLM SDKs | The OpenAI Python SDK is the de-facto standard | openai-java, LangChain4j, Spring AI all available | Even, leaning Python |
| Evaluation frameworks (Faithfulness / Context Precision) | **RAGAS, DeepEval, TruLens, Phoenix** | **No mature equivalent; everything self-built** | **Python (unique)** |
| PII detection | Presidio, spaCy | No equivalent; write the rules yourself | Python |
| Prompt-injection classifiers | Load a HF model in one line | ONNX + tokeniser, self-built | Python |
| Experiment iteration (error analysis, plotting) | Jupyter + pandas + matplotlib | Compile-run loops, or bolt on Python | **Python (unique)** |
| Service framework maturity | FastAPI is sufficient | **Spring Boot is clearly stronger** | **Java** |
| Concurrency model | asyncio suffices (I/O-bound) | JDK 21 virtual threads + reactive | Java |
| Configuration governance | pydantic-settings + YAML suffices | Spring Config is more mature | Java |
| Observability | structlog + OTel suffices | Micrometer + OTel more mature | Java |

**Summary**: Java wins on "service engineering", Python wins on "models and experiments". This
deliverable asks very little of service engineering (5 concurrent, single instance, no distributed
transactions, no HA requirement) and a great deal of models and experiments (three-config comparison,
four quality metrics, at least two issue diagnoses).

#### 2.1.4 Performance is not a selection argument

The usual reason for choosing Java is "the JVM is faster", which does not hold under this task's
constraints:

| Aspect | Reality | Conclusion |
|---|---|---|
| Concurrency requirement | ≥ 5 concurrent on one instance | Trivial for both languages; Python with asyncio + httpx is enough |
| Latency composition | LLM generation takes 5–7 s (see the latency budget), retrieval and reranking under 1 s, framework overhead in the millisecond range | **The language difference is drowned by generation, contributing under 1%** |
| Workload nature | Network-I/O-bound (LLM and vector-store calls), not CPU-bound | The JVM throughput advantage appears at thousands of QPS; this task caps at 5 concurrent |
| What actually moves P90 | Caching, parallel retrieval, rerank timeout fallback, output-length limits | None of these are language-specific |

**In one line**: changing language will not save the latency; changing architecture will.

#### 2.1.5 Java's genuine advantages (not dodged)

1. **Engineering governance maturity**: Spring's transactions, DI, layered configuration, Actuator,
   Micrometer and security modules work out of the box; long-term maintainability beats FastAPI.
2. **Strong typing and compile-time checks**: safer for large-team collaboration and refactoring.
3. **Chinese retrieval heritage**: Lucene / Elasticsearch live inside the JVM, and Chinese tokenisers
   such as HanLP are mature — if ES is definitely the hybrid engine, Java feels better there.
4. **Organisational and team factors**: if the team is a Java team, operations only support the JVM,
   and integration with an existing Java platform is required, Java's integration and troubleshooting
   costs are lower. **This is a real and important selection input and should not be erased by
   "technical sophistication"** (this workspace contains several Spring/Maven projects, so the factor
   genuinely applies here).

#### 2.1.6 The real cost of choosing Java for this task

| Cost | Concrete impact | How to verify |
|---|---|---|
| JDK version barrier | Only JDK 8 here; Spring AI 1.x needs Spring Boot 3.x + JDK 17+, and LangChain4j 1.x likewise needs 17+ | `java -version` (already measured) |
| No first-class OCR | Requires a Python sidecar or cloud OCR, which breaks the single-process simplicity and adds cross-language serialisation and failure points | Try implementing scanned-document ingestion in pure Java |
| No evaluation framework | RAGAS / DeepEval have no Java version, so the one-click evaluation script must be built end-to-end by hand | Search Maven Central for equivalent coordinates |
| Self-built model adapters | bge-m3's dense/sparse/ColBERT channels, pooling and quantisation must be implemented and validated | Compare vectors one-by-one against the Python side |
| Slower experiment iteration | Tuning chunk size, top_k, running the three-config comparison and doing error analysis take a few notebook cells in Python versus a compile-run loop in Java | Compare completion time for the same experiment |
| Thinner ecosystem | Far fewer reference implementations and community answers, making troubleshooting time unpredictable | — |

Note the knock-on effect of the first item: if OCR pulls in a Python sidecar, the system is already
polyglot — and **insisting on Java for the main service then keeps the dual-runtime cost while
forfeiting the consistency benefit of a single language.** That is the most awkward part of the Java
route here.

#### 2.1.7 Decision rule: when Java should be chosen instead

| Trigger | Explanation |
|---|---|
| The organisation mandates a JVM stack | A compliance or operations red line; not up for debate |
| The service must embed into an existing Java platform and cross-language calls are costly | Integration-boundary cost exceeds model-toolchain cost |
| The team is strong in Java and weak in Python | **Delivery speed and controllability are real gains**, especially in a time-boxed assessment |
| Elasticsearch/OpenSearch is already decided for hybrid, with JVM operational capability | Lucene is native to the JVM and the retrieval side feels better |
| A Python sidecar may cover only OCR and evaluation | Then a Java main service plus Python sidecar is a sound split |

Under those conditions, the recommended Java stack is: **Spring Boot 3 + JDK 21 (virtual threads) +
LangChain4j or Spring AI + OpenSearch/Lucene + DJL/ONNX Runtime (reranking) + Redis (cache) + a Python
sidecar (OCR and evaluation scripts only)**. It can deliver every capability; the model side simply
requires more self-built work.

#### 2.1.8 Conclusion of this section

Three reasons to choose Python, in order of weight:

1. **Capability coverage**: OCR, embeddings, reranking and evaluation are first-class in Python and
   require self-built or sidecar work in Java (table 2.1.3).
2. **Work distribution**: the deliverable is centred on experimentation and evaluation (> 50%), while
   Java's advantage zone — the service framework — is about 10% (table 2.1.2).
3. **Constraint fit**: the only performance constraint is 5 concurrent / P90 10 s, whose bottleneck is
   LLM generation and therefore independent of the language (table 2.1.4).

**It must also be acknowledged**: if the team is a Java team, the legitimate reason to choose Java is
"lowering delivery and troubleshooting risk", not "Java is technically stronger for this task". That
reason is valid in an assessment context and should be stated honestly rather than dressed up in
technical language. **This document's conclusion is framed as "optimal capability and evidence
output"; under an organisational-preference frame, Java plus a Python sidecar is a defensible
alternative.**

### 2.2 Document parsing and OCR

The corpus spans four document types (handbook, compliance guide, technical spec, architecture doc) and
**includes scans**. Parsing quality is the ceiling on retrieval quality.

| Candidate | Chinese OCR | Dependency weight | Layout/tables | Verdict |
|---|---|---|---|---|
| PyMuPDF | — (text layer only) | Very light | Fair | First choice for digital PDFs |
| Docling | Can integrate OCR | Medium | Strong (reading order, tables, heading hierarchy) | First choice for structured parsing |
| Unstructured | Can integrate | Heavy (many dependencies) | Fair | Alternative |
| RapidOCR | Good (PaddleOCR models + ONNX) | Light | Handle it yourself | **Primary OCR** |
| PaddleOCR | Best | Heavy (paddlepaddle) | Fair | Enable when accuracy matters most |
| Tesseract | Weak Chinese, poor vertical text and tables | Light | Poor | Rejected |

**Design point**: OCR output must carry confidence scores; blocks below a threshold are tagged
`low_ocr_confidence` and their hit rate is reported separately. That turns "are scans actually
retrievable?" into a quantified result rather than a subjective claim.

### 2.3 Chunking strategy

| Strategy | Context Precision | Faithfulness | Verdict |
|---|---|---|---|
| Fixed length (e.g. 512 tokens) | Medium (cuts semantics) | Medium (context may be incomplete) | Baseline |
| Structure-aware recursive (heading hierarchy + paragraphs) | Higher | Higher | **Primary** |
| Pure semantic | High | Medium | Expensive and unstable; rejected |
| Parent-child small-to-big | High (small units hit) | High (parent supplies context) | **Combined with structure-aware recursive** |

**Size guidance**: child 300–500 tokens, parent 1200–2000 tokens, 10–15% overlap. Metadata must include
`doc_id / section_path / lang / doc_type / page / effective_date / ocr_confidence`, where `lang` and
`effective_date` directly serve bilingual retrieval and compliance-timeliness questions.

There is a bonus: **chunk size / parent strategy is itself the number-one diagnosis material for
NFR4** (too fragmented → Faithfulness drops; too large → Context Precision drops), naturally producing
before/after data.

### 2.4 Embedding model

| Candidate | Chinese | English | Sparse vectors | Runs locally | Verdict |
|---|---|---|---|---|---|
| bge-m3 | Strong | Strong | ✅ dense/sparse/ColBERT together | ✅ (568M, ONNX int8) | **Primary** |
| multilingual-e5-large | Strong | Strong | ❌ | ✅ | Alternative |
| text-embedding-3-large | Strong | Strong | ❌ | ❌ (API) | Fallback when privacy permits |
| Monolingual (e.g. bge-large-zh) | Strong | Weak | ❌ | ✅ | Fails the bilingual requirement |

**Three hard reasons for bge-m3**:

1. **Bilingual**: the brief requires a mixed CN/EN corpus and cross-lingual retrieval (Chinese question,
   English source); monolingual models are out immediately.
2. **One model, two channels**: bge-m3 emits both dense vectors and learned sparse weights, making the
   lexical channel of hybrid retrieval far better than hand-rolled BM25 + tokenisation, while
   maintaining a single model.
3. **Privacy**: the knowledge base is internal compliance material and FR3 explicitly requires PII
   handling. Local embedding means **document text never leaves the intranet**, which external API
   embeddings cannot offer — an argument that carries more weight in the report than cost savings.

**Implementation note**: single-query encoding on CPU is in the hundreds of milliseconds (measure it);
indexing needs batch encoding — ONNX int8 with multi-process batching is recommended, roughly minutes
for ~10k chunks, a one-off cost.

### 2.5 Vector store and hybrid retrieval

| Candidate | Native hybrid | Single-machine footprint | Chinese BM25 | Verdict |
|---|---|---|---|---|
| Qdrant | ✅ sparse + dense + native RRF | Low (hundreds of MB) | Via bge-m3 sparse vectors; no tokeniser needed | **Primary** |
| OpenSearch / Elasticsearch | ✅ (ES 8.8+ has an RRF retriever; OpenSearch 2.11+ has hybrid query — verify RRF per version) | High (JVM 2–4 GB) | ✅ built-in CJK analysers, most mature | Alternative (strong enterprise credibility) |
| pgvector + ParadeDB | Partial (fusion hand-written) | Low | Needs zhparser/chinese_compatible tokenisation | Choose if consolidating on Postgres |
| Redis Stack | Partial | Low | Fair | Consolidates components if Redis is already used |
| Milvus | ✅ | High (etcd + MinIO) | Fair | Too heavy for a single machine |
| faiss (in-memory) | ❌ hand-written | Very low | Build it yourself | Only for very small corpora |

**Decision rule** (state it in the report to show engineering judgement rather than a hunch):

| Condition | Choice |
|---|---|
| Corpus < 5M chunks, single-machine deployment, low latency and low ops overhead | **Qdrant** |
| Mature Chinese tokenisation / synonyms / analyser control, or existing in-house ES operations | OpenSearch |
| Already committed to Postgres, want one store, accept hand-written fusion | pgvector + ParadeDB |

Qdrant's footprint matters especially on this machine (Docker Desktop + 16 GB): OpenSearch would run,
but it would eat into the memory budget for embedding and reranking, whereas a single Qdrant node uses
only a few hundred MB. That is exactly the kind of quantified argument "derived backwards from local
constraints" that the report should contain.

**Fusion algorithm**: RRF as primary (insensitive to score scale, no weight tuning, naturally handles
heterogeneous dense+sparse scores), normalised weighted fusion as the alternative. Both can be added to
the report as an extra independent variable in the comparison.

### 2.6 Reranker

Reranking is the main lever for Context Precision and the biggest threat to the latency budget.

| Candidate | Parameters | Chinese | CPU viability | Verdict |
|---|---|---|---|---|
| bge-reranker-v2-m3 | 568M | Strong | Marginal (int8 + candidate cap required) | First choice with a GPU or budget |
| bge-reranker-base | 278M | Usable CN/EN | Good | **Primary on this machine** |
| jina-reranker-v2-base-multilingual | 278M | Strong | Good | **Primary on this machine (tied)** |
| Cohere / Jina Rerank API | — | Strong | No local compute, low latency | Alternative when data may leave the network |
| Score with the generation model itself | — | Strong | Very high latency | Rejected |

**The three-part latency defence** (criterion C1):

1. Cap candidates at 15–20 (rerank latency is roughly linear in candidate count).
2. Hard timeout at 800 ms; on timeout fall straight back to the fused result and log
   `rerank_timeout=true`.
3. Batched inference with ONNX int8; write rerank scores to logs so the gain can be quantified.

**The trade-off must appear in the report**: reranking raises Context Precision but also P90. The
conclusion should read "at X candidates and Y timeout, Context Precision improves by Z points while P90
increases by W milliseconds".

### 2.7 Generation model

Three constraints must hold simultaneously (quality, cost, latency) and §8 demands explicit
trade-offs. The approach is not to pick the "best model" but to **run the same evaluation set across
candidates first, then conclude**.

| Tier | Role | Quality | Per-call cost | Latency | Use |
|---|---|---|---|---|---|
| Small (mini-class) | Primary | Medium | Low | Low | Simple factual Q&A (routable) |
| Mid | Fallback | High | Medium | Medium | Complex / multi-hop / multi-turn questions |
| Flagship | Offline judge | Highest | High | High | Evaluation scoring; not on the serving path |
| Local 7B quantised | Degradation plan | Medium-low | Very low | **Fails the target** | Demonstrates the "data stays inside" path only |

**Model selection experiment design** (produces the evidence §8 requires):

| Item | Design |
|---|---|
| Independent variable | 3–4 candidate models (small/mid/flagship; include Qwen/DeepSeek/GLM-class for China, OpenAI/Anthropic-class otherwise) |
| Controlled variables | Same evaluation set, prompt version, top_n, temperature=0, retrieval config |
| Dependent variables | Answer Compliance, Faithfulness, Style, P90 latency, cost per 1,000 calls |
| Output | Three-way table plus an explicit trade-off conclusion (e.g. "6 points lower quality, 80% cheaper, 60% lower P90") |
| Extra | Query-routing experiment: simple questions to the small model, complex to the mid model, reporting blended cost and quality |

**Engineering requirement**: all model calls go through one OpenAI-compatible abstraction with the
model id in configuration, so "swap the model version" is a one-line change (satisfying C3/NFR2) and
the comparison experiment above comes for free.

### 2.8 Orchestration framework

| Candidate | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| Thin in-house pipeline (a few hundred lines) | Full control of per-stage latency, scores and retries; log fields map one-to-one to stages | You write the retry and concurrency logic | **Primary** |
| LlamaIndex | Convenient ingestion connectors and parsing | The abstraction hides true latency attribution | Ingestion only |
| LangChain | Large ecosystem | Fast-moving versions, many black boxes, diagnosability suffers | Rejected |

The reason is that **the diagnosis requirements (§13, §35) are in direct conflict with framework
abstraction**: when compliance drops, it must be immediately clear whether recall worsened, rerank
ordering changed, or prompt assembly changed. A thin pipeline keeps log fields aligned with pipeline
stages, which is the precondition for NFR4 to be deliverable at all.

### 2.9 Caching

| Approach | Hit rate | Risk | Verdict |
|---|---|---|---|
| Exact match (Redis, normalised query hash) | Low | Almost none | Required as the baseline |
| Semantic cache (embedding similarity ≥ 0.95) | High | Similar-but-different questions falsely hit | **Primary (layered on top)** |
| No cache | 0 | Latency and cost pressure | Rejected |

**The cache key must include**: normalised query + `config_version` + prompt version + KB version +
model id. Omitting any one of them returns stale answers after a configuration switch or document
update — exactly the candidate source of the "compliance drop" diagnosis scenario, and the reason a
cache-correctness metric must exist.

### 2.10 Observability

| Candidate | Purpose | Verdict |
|---|---|---|
| structlog → JSONL file | Structured logs that directly feed operations-report aggregation | **Primary** |
| OpenTelemetry spans | Stage latency and end-to-end tracing | **Primary** |
| Langfuse (self-hosted) | Per-call LLM tracing, prompt version comparison | Optional enhancement |
| Prometheus + Grafana | Live monitoring dashboards | Heavier than this case needs; can be skipped |

This case's operations report only needs aggregation from JSONL (p50/p95, tokens, hit rate, refusal
rate, compliance rate), so a full monitoring stack is unnecessary; any extra component must be
justified in the report or it just adds complexity.

### 2.11 Evaluation implementation

| Candidate | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| In-house metric scripts + LLM judge | Full control of metric definitions, consistent with the report | Must be implemented and validated yourself | **Primary** |
| RAGAS | Works out of the box | Its faithfulness / context precision definitions differ from this document's, weakening "define your evaluation method" | Cross-check |

**Recommended combination**: in-house scripts as the primary definition, RAGAS run a second time on
the same subset, reporting their agreement rate. That proves the method is self-consistent and shows
awareness of the uncertainty in the measurement itself.

### 2.12 Security

| Layer | Approach | Measure |
|---|---|---|
| Input rules | Length/format limits + injection regexes ("ignore previous instructions", requests for the system prompt, delimiter injection) | Interception rate |
| Input classifier | `protectai/deberta-v3-base-prompt-injection-v2` (184M, runs on CPU) | Recall gain complementary to the rules |
| Context side | Spotlighting: wrap retrieved content in explicit delimiters marked "the following is untrusted data" | Injection success rate |
| Output side | Claim-level grounding check (reusing the same judge as Faithfulness) | Unsupported-answer rate |
| PII | Presidio (English) + Chinese regexes (national ID / mobile / bank card / email) + internal identifiers | Redaction miss rate |

**Both directions must be reported**: attack interception rate (missed defences) and false-interception
rate on normal questions (friendly fire). Reporting only the former encourages over-blocking, and
over-blocking is precisely the cause of the "refusal spike" diagnosis scenario.

## 3. Cost model

§8 requires a "token-cost estimate per 1,000 calls", so cost must be computable and re-computable —
not an isolated number.

**Formula**:

```
CostPer1k = 1000 × ( avg_prompt_tokens × P_in / 1e6 + avg_completion_tokens × P_out / 1e6 )
```

**Token profile assumption** (to be calibrated with real logs and stated in the report): prompt
≈ 2,500 tokens (system + 5 evidence blocks + history + question), completion ≈ 250 tokens.

**Worked example** (prices are illustrative only — **calibrate against current official prices before
delivery and record the price date**):

| Tier | Example price (input/output per 1M tokens) | Per-call cost | Per 1,000 calls |
|---|---|---|---|
| Small | $0.15 / $0.60 | 2500×0.15 + 250×0.60 = 525 units → $0.000525 | **$0.53** |
| Mid | $0.50 / $1.50 | 1250 + 375 = 1625 units → $0.001625 | **$1.63** |
| Flagship | $2.50 / $10.00 | 6250 + 2500 = 8750 units → $0.00875 | **$8.75** |
| Routed blend (60% small / 40% mid) | as above | — | **$0.97** |

**Other cost lines** (must be listed too, otherwise the estimate is incomplete):

| Item | Magnitude | Notes |
|---|---|---|
| Embedding | ~$0.05 per 1,000 calls (external API) or $0 (local) | Local bge-m3 goes to zero — one economic argument for the local option |
| Reranking | $0 local; ~$2 per 1,000 searches via API | Zero marginal cost for the local option |
| Cache savings | Deducted linearly by hit rate | A 30% hit rate cuts cost by 30%; must show up in the report |
| Evaluation (judge) cost | Offline, scaled by sample count | Must be reported separately from serving cost to avoid confusion |

**Cost-reduction levers and their quantified effect**: reducing top_n from 10 to 5 (halves the prompt),
cache hits, query routing, a hard `max_output_tokens` cap. Each needs "X% cheaper, Y quality change" in
the report.

## 4. Rejected options and why

| Option | Reason for rejection |
|---|---|
| Local 7B model for generation | No GPU, 16 GB RAM, and P90 ≤ 10 s at 5-way concurrency — orders of magnitude off; retained only as a stay-on-premises fallback |
| Milvus | Needs etcd + MinIO on one machine; operational cost far exceeds the benefit for a single-instance requirement |
| Pure faiss in-memory index | No persistence, no filtering, no native hybrid; incremental updates and cache invalidation are painful |
| Monolingual embedding models | Fail the CN/EN bilingual and cross-lingual retrieval requirement |
| Heavy LangChain chains | Hide per-stage latency and directly damage issue diagnosis |
| One model for both generation and judging | Self-preference bias makes metrics untrustworthy; separate models plus manual spot checks are required |
| Fine-tuning | No labelled data, no GPU, high time cost, and the payoff for this task is disproportionate |
| Tesseract OCR | Insufficient Chinese and table/layout quality; would directly cap retrieval quality |

## 5. Risks and switch conditions

| Risk | Trigger | Switch action |
|---|---|---|
| Embedding too slow on CPU | Single-query encoding > 300 ms | Move to a smaller model or API embeddings |
| Local reranking times out frequently | `rerank_timeout` share > 10% | Cut candidate count / smaller model / API reranking |
| Qdrant recall and fusion underperform | Context Precision < 0.70 | Move to OpenSearch with its analysers and RRF |
| Not enough memory on one machine | Total Docker usage > 12 GB | Drop OpenSearch-class components, limit batch sizes, use int8 |
| API network unreachable | Request failure rate rises | Switch to a directly reachable OpenAI-compatible service, or enable the local fallback path |
| Semantic cache false hits | Judge scores for cache hits materially below misses | Raise the similarity threshold / add entity-consistency checks |

## 6. Mapping to requirement clauses

| Clause | How this selection satisfies it |
|---|---|
| §6 Latency and concurrency | Local embedding/rerank + API generation; rerank timeout fallback; cache safety net; k6 evidence |
| §8 Cost and selection rationale | One cost formula + three-way model comparison + routed blend cost |
| §10 Faithfulness / Context Precision | Parent-child chunking + bge-m3 hybrid + configurable reranking + labelled evaluation set |
| §11 / §33 Generative quality | Compliance checklist + three-dimension style scoring + two-sided refusal metric + judge separation |
| §13 Structured logs | structlog JSONL + OTel spans + field dictionary |
| §15 Security | Rules + classifier injection detection + spotlighting + output grounding check + dual-path PII redaction |
| §20 Retrieval modes and rerank switch | YAML-driven; native hybrid in the vector store; zero-code rerank switch |
| §22 Refusal | Three triggers judged separately, all producing guidance |
| §24 PII | Output and logs both redacted; cache keys contain no plaintext either |
| §26 Operations report | All six mandatory fields aggregated from JSONL |
| §29 Three-config comparison | Same code path with configuration switching, keeping the experiment comparable |
| §31 Evolvability | OpenAI-compatible abstraction + interface-driven retrieval + versioned configuration |
| §35 Issue diagnosis | Independent instrumentation per stage, configuration snapshot in logs, reproducible before/after |

## 7. Three things to do before implementation

1. `uv python install 3.12` and create the project virtualenv (the system Python 3.8.2 cannot support
   the dependencies above).
2. `docker compose up` Qdrant + Redis, get the minimal "ingest → retrieve → generate" path running, and
   measure single-call embedding and rerank latency — this is the real baseline for every latency
   budget downstream.
3. Replace every "example / estimate" figure in this document with measured latency and current prices,
   noting the price date and measurement environment, to form the final selection argument.

> Reminder: the prices in this document are illustrative and the latencies are order-of-magnitude
> estimates. The deliverable requires "clear, quantitative evidence", so **every estimate must be
> replaced with measured data during implementation**, otherwise that part of the argument does not
> hold.
