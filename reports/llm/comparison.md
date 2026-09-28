# 三配置对比报告

> English version: [comparison.en.md](comparison.en.md)

| 指标 | llm_c1_vector | llm_c2_hybrid | llm_c3_hybrid_rerank |
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

> 延迟与成本为单机单实例实测；价格为配置中的示例单价，需替换为官方当期价。
> 评测时缓存已关闭，避免缓存命中跳过检索、掩盖真实检索质量。

## 结论

1. Context Precision 最优配置为 **llm_c3_hybrid_rerank**（0.8437），相对 llm_c1_vector（0.6738）提升 16.99 个百分点。
2. P95 延迟最低的是 **llm_c1_vector**（1859.5 ms）。若引入重排后延迟上升，需要靠超时降级与缓存抵消。
3. 选择建议：以 Context Precision 与 Faithfulness 的联合最优为准，在延迟预算（P90 ≤ 10s）内优先保留重排；超出预算则回退到次优配置。
