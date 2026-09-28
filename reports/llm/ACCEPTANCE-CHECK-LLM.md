# 验收指标核对（真实模型版）
> English version: [ACCEPTANCE-CHECK-LLM.en.md](ACCEPTANCE-CHECK-LLM.en.md)


> 快照：2026-09-25（多轮改写修复后重跑）
> 技术栈：ONNX 多语言向量（MiniLM-L12 int8）+ bge-reranker-base（ONNX int8）+ DeepSeek + LLM judge
> 数据来源：`reports/llm/eval_llm_c*.json`；多轮标注修复前的旧结果已归档到 `reports/llm/archive_broken_gold/`

## 一、达成情况

| 指标 | 目标（及格 / 进阶） | 实测（C3 / 最优配置） | 结论 |
|---|---|---|---|
| Faithfulness | ≥ 0.85 | **1.0000** | 达成 |
| Context Precision@5 | ≥ 0.70 | **0.8437**（C3） | 达成 |
| Style Consistency | ≥ 0.80 / 0.85 | **0.8852**（C1） | 达成（含进阶线） |
| Refusal Appropriateness | ≥ 0.80 / 0.90 | **0.9381**（C1） | 达成（三配置全部 ≥ 0.90） |
| Answer Compliance | ≥ 0.80 / 0.90 | 0.7824（C1）/ 0.7500（C3） | 未达成（达目标的 97.8%） |
| P90 端到端延迟 | ≤ 10 s | 2.42 s（C3） | 达成 |
| 并发 | ≥ 5 | 0 错误 | 达成 |
| 成本 | 给出估算与选型权衡 | $0.2661–$0.2806 / 千次（示例价） | 达成（待换真实价） |

**五项质量指标中四项达成，且这四项全部达到进阶线；合规率差 2.2%。**

## 二、三配置对比

| 指标 | C1 vector-only | C2 hybrid | C3 hybrid+重排 |
|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | **0.8437** |
| Recall@5 | 0.8681 | 0.8160 | **0.9062** |
| MRR | 0.6817 | 0.6843 | **0.8472** |
| Faithfulness | 0.9984 | 1.0000 | **1.0000** |
| Answer Compliance | **0.7824** | 0.7361 | 0.7500 |
| Style Consistency | **0.8852** | 0.8827 | 0.8766 |
| Refusal Appropriateness | **0.9381** | 0.9094 | 0.9211 |
| P90 延迟 | 1.56 s | 1.71 s | 2.42 s |
| 成本 / 千次（示例价） | $0.2806 | $0.2661 | $0.2682 |
| LLM judge 覆盖 | 125 条 / 0 失败 | 114 条 / 0 失败 | 117 条 / 0 失败 |

**重排带来检索质量的大幅提升**：相对 C2，Context Precision +24%、Recall +11%、MRR +24%，代价是 P90 增加约 0.7s。

> 注意：检索最好的配置不等于合规最好的配置。C3 检索明显更强，但 C1 的合规率反而更高
> （C3 检索更准 → 模型尝试作答的比例更高，其中一部分未通过严格的 judge 细则）。
> 两个指标需要联合权衡，不能只看检索。

## 三、相对初始实现的提升

| 指标 | 初始（哈希向量 + 规则评判 + 离线生成） | 最终（真实向量 + 交叉编码器 + 真实模型 + LLM judge） |
|---|---|---|
| Context Precision@5 | 0.3509 | **0.8437**（+140%） |
| Recall@5 | 0.4271 | **0.9062**（+112%） |
| Faithfulness | 0.7434 | **1.0000** |
| Answer Compliance | 0.6111 | **0.7824** |
| Refusal Appropriateness | 0.8385 | **0.9381** |
| 多轮改写轮 CP@5 | 0.463（且标注有误） | **0.7812** |
| 注入拦截 | 20/20 | 20/20 |

## 四、剩余差距与原因

| 未达成项 | 实测 | 主要原因 | 下一步 |
|---|---|---|---|
| Answer Compliance 0.80 | 0.7824（C1，最优） | C1 的 47 条未合规中 21 条"该答却拒答"、25 条作答但未过 judge 细则；C3 为 29 / 24 | 降低过度拒答（放宽 grounding 阈值与提示词），补齐引用规范 |
| 成本口径 | $0.2661–$0.2806 / 千次 | 仍使用示例单价（$0.15 / $0.60 每 1M token） | 替换为 DeepSeek 官方当期价 |

子集明细（C1，合规率最高）：单轮合规 0.906（作答 58/64），多轮合规 0.812（作答 65/80）。

## 五、累计修复的真实缺陷

1. 跨语言检索失败：哈希向量使英文问题检索不到中文文档，是 CP 仅 0.38 的根因。
2. 加权融合压制语义通道：词法权重 0.7 时，只在向量通道出现的正确跨语言结果被挤出。
3. 词法重排破坏语义排序：接入真实向量后，词法重排让 CP 从 0.4346 降到 0.4115。
4. 重排超时整批降级：20 候选需 1553ms > 800ms 预算，重排完全失效；改为 10 候选后 370–610ms。
5. 缓存命中丢失引用与检索上下文：响应引用为空，评测检索指标失真。
6. 评测未禁缓存：缓存命中跳过检索，掩盖真实检索质量。
7. judge 证据被截断：280 字符截断使支持句不可见，正确回答被误判为"编造"。
8. 模型自拒答未被识别：模型说"资料中没有"时管线仍记为"已作答"，拒答率与合规率同时失真。
9. 词法越界门大量误伤：50 条误拒答中 37 条来自该门，其中 18 条检索完全正确；改用模型自判后拒答适当性 0.859 → 0.918。
10. 多轮标注缺少跨语言回退：单轮有锚点回退、多轮没有，导致英文题目 gold 为空，检索命中却判 0 分。
11. 轮次门控误判：用"问句短于 24 字符"判断是否需要改写，把独立新话题问题误判为追问并被兜底替换，答错话题。
12. 改写方式为拼接：把追问与上一轮问题直接拼接成畸形复合问句；改为 LLM 会话式改写（含严格重试与确定性兜底）。
13. 生成输入选择错误：A/B 实测确认生成必须使用改写后的问句（规则模式 0.825 vs 0.675，LLM 模式 0.750 vs 0.700），
    因为追问本身不携带话题，仅靠会话历史不足以稳定消解指代。

## 六、复现命令

```bash
uv sync --extra ocr && uv add tokenizers huggingface_hub
# ONNX 模型文件（走 hf-mirror）
uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml
uv run python scripts/eval.py --rebuild-dataset --eval-dir data/eval_onnx --report-dir reports/llm
uv run python scripts/eval.py \
  --configs configs/llm_c1_vector.yaml configs/llm_c2_hybrid.yaml configs/llm_c3_hybrid_rerank.yaml \
  --eval-dir data/eval_onnx --report-dir reports/llm
uv run python scripts/report.py --config-version llm_c3_hybrid_rerank
```
