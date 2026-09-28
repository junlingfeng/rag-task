# Risk Register and Open Questions

> Chinese version: [RISKS-AND-OPEN-QUESTIONS.md](RISKS-AND-OPEN-QUESTIONS.md)

## 1. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No ready-made corpus or label set | No quality metric can be computed; nothing can be delivered | Build the dataset first (M0); if the scale is short, state it and describe the sampling method in the report |
| Self-judging loop (same model generates and scores) | Metric credibility is challenged | Separate generation and judging models; hand-verify ≥ 20% and report the agreement rate |
| Three-config comparison is not comparable | Conclusions are invalid | Fix evaluation set, prompt, model, top_n and seed; record configuration snapshots and version numbers |
| "2 issue diagnoses" required but metrics go green first time | NFR4 cannot be delivered | Deliberately design and record real regression events with before/after data |
| Reranker inflates P90 | Breaches the 10 s hard constraint | Timeout fallback, batched reranking, cache safety net; measure P90 |
| Poor Chinese tokenisation | hybrid degrades into English keyword matching | Use mature Chinese tokenisation / multilingual retrieval; validate on the bilingual subset |
| Low OCR quality | Scanned content can never be retrieved | Sample-based OCR quality assessment; manual correction where necessary, or record it as a known limitation |
| PII in logs | Security and compliance exposure | Redact before logging, hash values; never put plaintext in cache keys either |
| Cache returns stale answers | Compliance drops | TTL plus invalidation on re-index; monitor judge scores for cache-hit requests |
| Mixed metric units (% and 0–1) | Reviewer misreads results | Normalise units in the report and annotate the mapping explicitly |
| Latency boundary left undeclared | The P90 conclusion can be challenged | Define the end-to-end boundary (streaming or not) and fix it in the report |
| Evaluation and production code paths diverge | Evaluation results do not represent production | Share one retrieval/generation code path, differentiated only by configuration |

## 2. Questions for the requester

1. Where does the corpus come from? Are sample documents provided? What is the scale (documents / pages / total tokens)?
2. What is the end-to-end latency boundary — full response returned? Is streaming allowed?
3. How is "≥ 5 concurrent" verified: concurrency model, request mix, duration, target hardware?
4. Are there model or budget constraints (is calling external APIs allowed, is there a cost cap)?
5. Is there a designated evaluation dataset, or is it entirely candidate-built?
6. Do Answer Compliance / Style Consistency have official definitions, or are they defined by the candidate in the report?
7. Must the "2 issue diagnoses" be genuinely occurring problems, or are controlled experiments that produce regressions acceptable?
8. Delivery format and deadline: repository, report format, does it need to be deployed and running?
9. Is a front end required, or is an API sufficient?
10. How deep must security go: is "minimal injection defence" enough, or is a specific attack-type checklist expected?

## 3. Default assumptions (proceed on these if no answer is obtained)

| Item | Default assumption |
|---|---|
| Corpus | Build from public documents plus synthesised internal material, with a self-built label set; state the scale in the report |
| Latency boundary | Non-streaming; end-to-end = request received → full response returned |
| Concurrency | Single instance, constant 5-way concurrency, mixed request distribution, load test lasting ≥ 5 minutes |
| Model | External APIs allowed; a cost-effective model as the primary and a larger model as the judge |
| Evaluation set | Fully self-built, with a fixed, versioned split |
| Metric definitions | Use the definitions in [METRIC-DEFINITIONS.en.md](METRIC-DEFINITIONS.en.md) and declare them explicitly in the report |
| Issue diagnosis | Produce real regressions via controlled experiments and record the data faithfully |
| Delivery format | Code repository + one-click scripts + Markdown/CSV reports |
| Front end | API only (plus curl examples and a minimal demo) |
| Security depth | Common injection patterns + PII redaction + refusal without evidence; not a complete offensive/defensive framework |
