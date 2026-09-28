# 验收指标核对

> 快照日期：2026-09-19　数据来源：`reports/eval_*.json`、`reports/ops_report_*.txt`、`reports/loadtest.json`、`reports/diagnosis_report.md`
> 被测配置：c3 hybrid + rerank（三配置中最优）；后端为**离线后端**（哈希向量 + 词法重排 + 抽取式生成）

## 结论

| 分组 | 达成 | 未达成 |
|---|---|---|
| 全局约束（及格线） | Style Consistency、Refusal Appropriateness、P90 延迟、并发、成本、日志、安全机制 | Faithfulness、Context Precision、Answer Compliance（80% 线） |
| 非功能进阶目标 | Style Consistency（0.85 线） | Answer Compliance（90%）、Refusal Appropriateness（90%） |
| 功能需求 FR1–FR4 | 全部达成 | — |
| 交付物 | 全部达成 | — |

**一句话**：机制与工程类验收项全部达成；质量类指标未达成，原因是离线后端缺乏语义能力，
不是链路缺陷（详见最后一节）。

## 一、全局约束（及格线）

| 指标 | 目标 | 实测（c3） | 结论 |
|---|---|---|---|
| Faithfulness | ≥ 0.85 | 0.7383 | **未达标** |
| Context Precision | ≥ 0.70 | 0.3509 | **未达标** |
| Answer Compliance | ≥ 80% | 0.6435 | **未达标** |
| Style Consistency | ≥ 80% | 0.8858 | 达标 |
| Refusal Appropriateness | ≥ 80% | 0.8385 | 达标 |
| P90 端到端延迟 | ≤ 10 s | 7.03 ms | 达标（仅离线链路） |
| 单实例并发 | ≥ 5 | 5 并发 / 200 请求 / 0 错误，P90 23.41 ms | 达标（仅离线链路） |
| 每千次调用成本 | 需给出估算与选型权衡 | $0.1043 / 千次（示例价格） | 达标（口径见下） |
| 结构化日志 | 足以支撑监控与诊断 | 38 个字段，JSONL | 达标 |
| 安全 | 注入防御 / PII / 严格接地 | 注入拦截 20/20，PII 双路脱敏，答案强制引用 | 达标 |

> 延迟与成本口径说明：价格使用配置中的示例单价（$0.15/$0.60 每 1M token），
> **落地前必须替换为官方当期价格**；延迟不包含真实大模型生成耗时，接入真实模型后需重测。

## 二、功能需求 FR1–FR4

| 编号 | 需求 | 实测证据 | 结论 |
|---|---|---|---|
| FR1 | 至少两种检索模式；重排可配置启停（不改代码） | `configs/c1|2|3_*.yaml` 三份配置仅改 `retrieval.mode` 与 `rerank.enabled` | 达标 |
| FR2 | 低置信度 / 越界 / 安全触发时拒答并给出引导 | 拒答率 32.31%，按原因分布：out_of_scope 861、safety 138、no_evidence 21；三类模板均含引导语 | 达标 |
| FR3 | 输出与日志双路 PII 脱敏 | 日志中 16 条命中 `CN_HOTLINE`、13 条命中 `CN_HOTLINE+EMAIL_PARTIAL`；答案中热线已替换为 `[REDACTED:CN_HOTLINE]` | 达标 |
| FR4 | txt/CSV 运维报告含 p50/p95、token、缓存命中率、拒答率、合规率 | `reports/ops_report_c3_hybrid_rerank.txt/.csv`，六个字段齐全 | 达标 |

## 三、非功能与量化指标

| 编号 | 需求 | 实测 | 结论 |
|---|---|---|---|
| NFR1 | 三配置量化对比并给出结论 | CP@5：0.2437 → 0.2872 → 0.3509；Recall@5：0.3090 → 0.3542 → 0.4271 | 达标 |
| NFR2 | 可演进（换检索策略、换模型、扩指标） | 检索/重排/生成/向量/缓存/切分全部配置化；有索引-embedding 一致性校验 | 达标 |
| NFR3 | Answer Compliance ≥ 90%；Refusal Appropriateness ≥ 90%；Style Consistency ≥ 0.85 | 0.6435 / 0.8385 / 0.8858 | 仅 Style 达标 |
| NFR4 | 至少 2 个问题诊断，含证据、修复理由、修复后提升 ≥ 10% | 见下表 | 达标 |

### NFR4 诊断前后对比

| 问题 | 修复前 | 修复后 | 提升 |
|---|---|---|---|
| 切分粒度过小（120 → 320 token） | Recall@5 0.3438 | 0.4271 | **+24.2%** |
| 越界阈值过严（标定前 → 标定后） | 正确应答率 0.3281；拒答适当性 0.4889 | 0.8438；0.8385 | **+157.2%；+71.5%** |

## 四、交付物

| 交付物 | 位置 | 结论 |
|---|---|---|
| 完整代码与配置 | `src/rag/`、`configs/`、`scripts/` | 达标 |
| 一键评测脚本 | `scripts/eval.py --all`、`scripts/run_all.sh` | 达标 |
| 评测报告（含前后对比） | `reports/EVALUATION-REPORT.md`、`reports/comparison.md`、`reports/diagnosis_report.md` | 达标 |
| 日志字段字典 + 样例日志 | `docs/LOG-FIELD-DICTIONARY.md`（由代码生成） | 达标 |

## 五、未达标项：原因与解除条件

| 未达标项 | 实测 | 根本原因 | 解除条件 |
|---|---|---|---|
| Faithfulness ≥ 0.85 | 0.7383 | 抽取式生成器会把上下文里"词面相近但语义无关"的句子选进答案 | 接入真实生成模型 + 语义 embedding |
| Context Precision ≥ 0.70 | 0.3509 | 哈希向量无语义能力；**中文问英文文档无法跨语言匹配**；语料含大量近似干扰文档 | `embedding.backend=sentence_transformers`，用 bge-m3 重新入库 |
| Answer Compliance ≥ 80% / 90% | 0.6435 | 检索质量受限导致部分答案不切题；规则评判对"是否直接回答问题"要求严格 | 真实 embedding + 真实生成模型 + LLM judge 复核 |
| Refusal Appropriateness ≥ 90% | 0.8385 | 词法越界判定的上限约 0.80（平衡准确率），无法识别语义等价改写 | 换语义判据（真实 embedding 或 LLM 范围判定） |

### 已确认的限制（不是缺陷，但需在交付说明中声明）

1. **延迟与并发达标不代表生产环境达标**：当前无真实大模型调用，7 ms 与 23 ms 只反映检索与本地计算。
   按延迟预算，生成阶段预计占 5–7 s，需接入真实模型后重跑 `scripts/loadtest.py` 才能给出最终结论。
2. **成本为示例价格**：`configs/base.yaml` 中 `price_in_per_1m` / `price_out_per_1m` 必须替换为官方当期价。
3. **扫描件为合成渲染**：OCR 噪声分布与真实扫描件不同；实测 150 DPI 会导致 OCR 吞掉英文词间空格，
   已提高到 300 DPI 并在匹配层做空白归一化处理。
4. **语料为自建**：需求文档未提供语料，评测结论的绝对数值依赖这份语料，换语料需重跑。

## 六、复现命令

```bash
uv sync --extra ocr
uv run python scripts/ingest.py --rebuild-corpus
uv run python scripts/eval.py --rebuild-dataset
uv run python scripts/eval.py --all
uv run python scripts/report.py --config-version c3_hybrid_rerank
uv run python scripts/loadtest.py --concurrency 5 --requests 200
uv run python scripts/diagnose.py
uv run python scripts/gen_log_docs.py && uv run python scripts/gen_eval_report.py
```
