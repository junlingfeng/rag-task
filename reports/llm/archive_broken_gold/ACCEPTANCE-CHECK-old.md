# 验收指标核对（真实模型版）

> 快照：2026-09-19　被测配置：C3（hybrid + 交叉编码器重排）
> 技术栈：ONNX 多语言向量（MiniLM-L12）+ bge-reranker-base(ONNX int8) + DeepSeek + LLM judge
> 数据来源：`reports/llm/eval_llm_c3_hybrid_rerank.json`、`reports/llm/items_llm_c3_hybrid_rerank.jsonl`

## 一、达成情况

| 指标 | 目标（及格 / 进阶） | 实测 | 结论 |
|---|---|---|---|
| Faithfulness | ≥ 0.85 | **0.9900** | 达成 |
| Style Consistency | ≥ 0.80 / 0.85 | **0.8755** | 达成（含进阶线） |
| Refusal Appropriateness | ≥ 0.80 / 0.90 | **0.9184** | 达成（含进阶线） |
| Context Precision@5 | ≥ 0.70 | 0.6678 | 未达成（达目标的 95.4%） |
| Answer Compliance | ≥ 0.80 / 0.90 | 0.7176 | 未达成（达目标的 89.7%） |
| P90 端到端延迟 | ≤ 10 s | 2.39 s | 达成 |
| 并发 | ≥ 5 | 0 错误 | 达成 |

## 二、三配置对比

| 指标 | C1 vector-only | C2 hybrid | C3 hybrid+重排 |
|---|---|---|---|
| Context Precision@5 | 0.5162 | 0.5477 | **0.6678** |
| Recall@5 | 0.6597 | 0.6528 | **0.7083** |
| MRR | 0.5229 | 0.5530 | **0.6748** |
| Faithfulness | 0.9914 | 0.9950 | 0.9900 |
| Answer Compliance | **0.7454** | 0.7222 | 0.7176 |
| Style Consistency | **0.8799** | 0.8768 | 0.8755 |
| Refusal Appropriateness | **0.9184** | 0.9094 | 0.9184 |
| P90 延迟 | 1.81 s | 1.62 s | 2.39 s |
| 成本 / 千次（示例价） | $0.2851 | $0.2649 | $0.2680 |

结论：重排显著提升检索类指标（CP +22%、MRR +22%），代价是 P90 增加约 0.6s；
合规与风格类指标三配置接近，说明它们主要由生成模型决定，而非检索配置。

## 三、相对初始实现的提升

| 指标 | 初始（哈希向量 + 规则评判 + 离线生成） | 最终（真实向量 + 交叉编码器 + 真实模型 + LLM judge） |
|---|---|---|
| Context Precision@5 | 0.3509 | **0.6678**（+90%） |
| Recall@5 | 0.4271 | **0.7083**（+66%） |
| Faithfulness | 0.7434 | **0.9900** |
| Answer Compliance | 0.6111 | **0.7176** |
| Refusal Appropriateness | 0.8385 | **0.9184** |
| 注入拦截 | 20/20 | 20/20 |

> 注：Faithfulness 的提升同时来自"检索变好"和"评判换成 LLM judge"，
> 两者不可分离地归因；规则评判会惩罚合法改写，本身不适用于生成式模型。

## 四、剩余差距与原因

| 未达成项 | 实测 | 主要原因 | 下一步 |
|---|---|---|---|
| Context Precision 0.70 | 0.6678 | 语料存在大量近似干扰文档；向量模型为轻量版（384 维 int8） | 换 bge-m3（更强多语言向量）后重新入库 |
| Answer Compliance 0.80 | 0.7176 | 61 条未合规中：34 条"该答却拒答"、25 条作答但未通过 judge 细则；多轮子集合规率仅 0.675 | 提升多轮改写质量（当前改写轮次检索精度 0.469） |
| 成本口径 | $0.268/千次 | 仍使用示例单价（$0.15/$0.60 每 1M token） | 替换为 DeepSeek 官方当期价 |

## 五、本轮修复的真实缺陷

1. **跨语言检索失败**：哈希向量使英文问题检索不到中文文档，是 CP 仅 0.38 的根因。
2. **加权融合压制语义通道**：词法权重 0.7 时，只在向量通道出现的正确跨语言结果被挤出。
3. **词法重排破坏语义排序**：接入真实向量后，词法重排让 CP 从 0.4346 降到 0.4115。
4. **重排超时整批降级**：20 候选需 1553ms > 800ms 预算，导致重排完全失效；改为 10 候选后 370-610ms。
5. **缓存命中丢失引用与检索上下文**：响应引用为空，评测检索指标失真。
6. **评测未禁缓存**：缓存命中跳过检索，掩盖真实检索质量。
7. **judge 证据被截断**：280 字符截断使支持句不可见，正确回答被误判为"编造"。
8. **模型自拒答未被识别**：模型说"资料中没有"时管线仍记为"已作答"，拒答率与合规率同时失真。
9. **词法越界门大量误伤**：50 条误拒答中 37 条来自该门，其中 18 条检索完全正确；改用模型自判后拒答适当性 0.859 → 0.918。

## 六、复现命令

```bash
uv sync --extra ocr && uv add tokenizers huggingface_hub
# 模型文件（hf-mirror）
uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml
uv run python scripts/eval.py --rebuild-dataset            # 默认索引
uv run python scripts/eval.py \
  --configs configs/llm_c1_vector.yaml configs/llm_c2_hybrid.yaml configs/llm_c3_hybrid_rerank.yaml \
  --report-dir reports/llm
uv run python scripts/report.py --config-version llm_c3_hybrid_rerank
```
