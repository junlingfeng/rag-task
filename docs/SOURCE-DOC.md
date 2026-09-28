# 需求文档原文提取
> English version: [SOURCE-DOC.en.md](SOURCE-DOC.en.md)


## 溯源信息

| 项目 | 值 |
|---|---|
| 源文件 | `Asst Manager, Backend Developer,AKP.docx` |
| 大小 | 52,523 bytes |
| 提取方式 | `unzip` 解包后直接解析 `word/document.xml`，并用 `textutil -convert txt` 交叉验证 |
| 正文段落数 | 38 |
| 表格 / 图片 / 附件 | 无 |
| 页脚 | 3 个页脚均为 `[AIA - INTERNAL]`（无正文信息） |
| 结论 | 正文已完整提取，无遗漏内容 |

## 原文（逐字提取，未做改写；行首数字为段落序号，便于引用）

```
 0  Case Study – RAG + Generative AI Service
 1  Role: Mid-Level Developer
 2  Unified Business Scenario & Global Constraints
 3  Build a multi-turn RAG QA + generative service over the internal knowledge base (employee handbook, compliance guides, technical specifications, architecture documents). The corpus is bilingual (CN/EN) and includes a small portion of scanned PDFs. Candidates may choose any tech stack, but all key technical choices must be justified in the deliverables with clear, quantitative evidence and validation.
 4  Global Constraints (apply to this role unless overridden below)
 5  Performance
 6  90% of QA requests must complete end-to-end within 10 seconds; support ≥ 5 concurrent requests on a single instance.
 7  Cost
 8  Provide token-cost estimates per 1,000 calls, and explain your model-version selection rationale with explicit trade-offs (quality, cost, latency).
 9  Quality Metrics (must be quantified)
10  RAG: Faithfulness ≥ 0.85 (define your evaluation method); Context Precision ≥ 0.70.
11  Generative answers: define the evaluation standard and implementation. Target thresholds: Answer Compliance ≥ 80%; Style Consistency ≥ 80%; Refusal Appropriateness ≥ 80%.
12  Logging & Tracing
13  Emit structured logs sufficient for generation monitoring and issue diagnosis.
14  Security
15  Minimal prompt-injection defenses; basic PII handling; all answers must strictly ground to retrieved context.
16  Objective
17  Extend and harden the service to include configurable retrieval modes, reranking, generative quality controls, complete observability, caching, and reproducible diagnosis.
18  Functional Requirements
19  1) Retrieval Controls
20  Support at least two retrieval modes: vector-only and hybrid. Allow enabling/disabling reranker via configuration (no code change).
21  2) Refusal & Safety Handling
22  When confidence is low, the query is out-of-scope, or safety rules trigger, return a refusal with guidance.
23  3) Privacy
24  Apply basic PII redaction to outputs and logs.
25  4) Minimal Operations Report
26  Produce a simple text/CSV report including: p50/p95 latency, token usage, cache hit rate, refusal rate, and answer compliance rate.
27  Non-Functional & Quantitative Metrics
28  1) Retrieval Quality
29  Compare three configurations: vector-only, hybrid, hybrid+rerank. Provide quantitative results and conclusions
30  2) Evolvability
31  Design for iterative optimization: retrieval strategy changes, model version swaps, metric/logging enhancements.
32  3) Generative Quality (advanced targets)
33  Answer Compliance ≥ 90%; Refusal Appropriateness ≥ 90%; Style Consistency ≥ 0.85 (describe your evaluation method).
34  4) Issue Diagnosis
35  Document at least two issues (e.g., compliance drop, refusal spike) with log/metric evidence, fix rationale, and post-fix improvement ≥ 10%.
36  Deliverables
37  • Complete code and configs • One-click evaluation script.• Evaluation report with before/after comparisons.• Log field dictionary and sample logs.
```
