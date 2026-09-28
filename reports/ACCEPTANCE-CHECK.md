# 验收指标核对（当前结论）
> English version: [ACCEPTANCE-CHECK.en.md](ACCEPTANCE-CHECK.en.md)


> 快照：2026-09-25
> 当前结论基于**真实技术栈**：ONNX 多语言向量 + ONNX 交叉编码器重排 + DeepSeek + LLM judge
> 数据来源：`reports/llm/eval_llm_c*.json`；离线阶段的核对见 [archive/ACCEPTANCE-CHECK-offline-20260919.md](archive/ACCEPTANCE-CHECK-offline-20260919.md)

## 一、达成情况

| 指标 | 目标（及格 / 进阶） | 实测最优 | 结论 |
|---|---|---|---|
| Faithfulness | ≥ 0.85 | **1.0000** | 达成 |
| Context Precision@5 | ≥ 0.70 | **0.8437** | 达成 |
| Style Consistency | ≥ 0.80 / 0.85 | **0.8852** | 达成（含进阶线） |
| Refusal Appropriateness | ≥ 0.80 / 0.90 | **0.9381** | 达成（含进阶线） |
| Answer Compliance | ≥ 0.80 / 0.90 | 0.7824 | 未达成（达目标的 97.8%） |
| P90 端到端延迟 | ≤ 10 s | 2.42 s | 达成 |
| 单实例并发 | ≥ 5 | 5 并发 / 200 请求 / 0 错误 | 达成 |
| 成本 | 给出估算与权衡 | $0.2661–$0.2806 / 千次（示例价） | 达成（待换真实价） |

**五项质量指标达成四项，且四项全部达到进阶线；合规率差 2.2%。**

各配置最优值：

| 指标 | C1 vector | C2 hybrid | C3 hybrid+重排 |
|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | **0.8437** |
| Recall@5 | 0.8681 | 0.8160 | **0.9062** |
| Faithfulness | 0.9984 | **1.0000** | **1.0000** |
| Answer Compliance | **0.7824** | 0.7361 | 0.7500 |
| Style Consistency | **0.8852** | 0.8827 | 0.8766 |
| Refusal Appropriateness | **0.9381** | 0.9094 | 0.9211 |
| P90 延迟 | 1.56 s | 1.71 s | 2.42 s |

> **检索最优 ≠ 合规最优**：C3 检索最强（CP 0.8437）但合规率低于 C1（0.7500 vs 0.7824）。
> 原因是 C3 检索更准，模型尝试作答的比例更高（正确应答率 0.906 vs 0.875），
> 其中一部分未通过严格的合规细则；C1 更常拒答，反而"少答少错"。
> 若以合规率为目标，当前最优配置是 C1；若以检索质量为目标，则是 C3。

## 二、功能与交付物

| 项目 | 结论 | 证据 |
|---|---|---|
| FR1 两种检索模式 + 重排可配置 | 达成 | 三份配置仅改 `retrieval.mode` 与 `rerank.enabled` |
| FR2 三类拒答 + 引导 | 达成 | 拒答原因分布：`no_evidence` / `low_confidence` / `safety` |
| FR3 PII 双路脱敏 | 达成 | 实测答案中邮箱与热线被替换为 `[REDACTED:EMAIL]` / `[REDACTED:CN_HOTLINE]` |
| FR4 运维报告（六字段） | 达成 | `reports/ops_report_llm_c3_hybrid_rerank.txt/.csv` |
| 安全：注入拦截 | 达成 | 20/20 |
| 交付物四件套 | 达成 | 代码与配置、一键脚本、评测报告、日志字典 |

## 三、相对初始阶段的提升

| 指标 | 初始（哈希向量 + 规则评判 + 离线生成） | 当前（真实向量 + 交叉编码器 + 真实模型 + LLM judge） |
|---|---|---|
| Context Precision@5 | 0.3509 | **0.8437**（+140%） |
| Recall@5 | 0.4271 | **0.9062**（+112%） |
| Faithfulness | 0.7434 | **1.0000** |
| Answer Compliance | 0.6111 | **0.7824** |
| Refusal Appropriateness | 0.8385 | **0.9381** |
| 多轮改写轮 CP@5 | 0.463（且标注有误） | **0.7812** |

## 四、剩余差距

| 未达成项 | 实测 | 主要原因 | 下一步 |
|---|---|---|---|
| Answer Compliance ≥ 0.80 | 0.7824（C1） | 未合规 47 条中 21 条"该答却拒答"、25 条作答但未过 judge 细则 | 放宽 grounding 阈值、强化引用格式提示词 |
| 成本口径 | 示例单价 | 未使用官方当期价 | 替换 `price_in_per_1m` / `price_out_per_1m` 后重算 |

详细的真实模型验收记录（含累计修复的 13 个缺陷）见 [llm/ACCEPTANCE-CHECK-LLM.md](llm/ACCEPTANCE-CHECK-LLM.md)。
离线阶段的核对（用于验证链路与评测方法本身）见 [archive/ACCEPTANCE-CHECK-offline-20260919.md](archive/ACCEPTANCE-CHECK-offline-20260919.md)。
