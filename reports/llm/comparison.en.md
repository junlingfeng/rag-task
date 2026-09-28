# Three-Configuration Comparison

> Chinese version: [comparison.md](comparison.md)

| Metric | llm_c1_vector | llm_c2_hybrid | llm_c3_hybrid_rerank |
|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | 0.8437 |
| Recall@5 | 0.8681 | 0.8160 | 0.9062 |
| MRR | 0.6817 | 0.6843 | 0.8472 |
| Faithfulness | 0.9984 | 1.0000 | 1.0000 |
| Answer Compliance | 0.7824 | 0.7361 | 0.7500 |
| Style Consistency | 0.8852 | 0.8827 | 0.8766 |
| Refusal Appropriateness | 0.9381 | 0.9094 | 0.9211 |
| Correct Answer Rate | 0.9062 | 0.8438 | 0.8750 |
| P50 (ms) | 1029.7 | 1095.4 | 1790.1 |
| P95 (ms) | 1859.5 | 1950.4 | 2685.4 |
| Cost / 1k calls (USD) | 0.2806 | 0.2661 | 0.2682 |

> Latency and cost are measured on a single local instance; prices are the example unit prices from
> configuration and must be replaced with the provider's current prices.
> Caching is disabled during evaluation so that cache hits cannot skip retrieval and mask real
> retrieval quality.

## Conclusions

1. The best Context Precision comes from **llm_c3_hybrid_rerank** (0.8437), 16.99 percentage points
   above llm_c1_vector (0.6738).
2. The lowest P95 latency belongs to **llm_c1_vector** (1859.5 ms). The latency added by reranking must
   be offset by timeout fallback and caching.
3. Recommendation: choose on the joint optimum of Context Precision and Faithfulness, keeping
   reranking as long as it fits the latency budget (P90 ≤ 10 s); fall back to the next-best
   configuration when it does not.
