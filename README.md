# RAG + Generative AI Service — 需求分析交付包
> English version: [README.en.md](README.en.md)


本目录既是 `Asst Manager, Backend Developer,AKP.docx` 的需求分析产出，也包含按分析结论完整实现的
代码、配置、评测与报告。分析与实现一一对应，见下方"实现状态"。

## 实现状态

已按 [REQUIREMENTS-ANALYSIS.md](docs/REQUIREMENTS-ANALYSIS.md) 的建议推进顺序 M0–M7 全部执行完毕。

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 评测数据集 + 日志/指标骨架 | 完成（216 个评测单元、38 个日志字段） |
| M1 | vector-only 基线 + 结构化日志 | 完成 |
| M2 | hybrid + 配置化重排 | 完成（零代码切换） |
| M3 | 拒答、安全、PII | 完成（三类触发 + 双路脱敏） |
| M4 | 一键评测 + 三配置报告 | 完成（`scripts/eval.py --all`） |
| M5 | 缓存 + 运维报告 | 完成（txt/CSV，六个强制字段） |
| M6 | 2 处问题诊断 + 前后对比 | 完成（真实实验，见诊断报告） |
| M7 | 文档收口 | 完成（日志字典、运行手册、评测报告） |

### 三配置评测结果（真实技术栈）

技术栈：ONNX 多语言向量（MiniLM-L12 int8）+ bge-reranker-base（ONNX int8 交叉编码器）+ DeepSeek + LLM judge。

| 指标 | C1 vector-only | C2 hybrid | C3 hybrid+重排 | 目标 |
|---|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | **0.8437** | ≥ 0.70 ✅ |
| Recall@5 | 0.8681 | 0.8160 | **0.9062** | — |
| MRR | 0.6817 | 0.6843 | **0.8472** | — |
| Faithfulness | 0.9984 | **1.0000** | **1.0000** | ≥ 0.85 ✅ |
| Answer Compliance | **0.7824** | 0.7361 | 0.7500 | ≥ 0.80（差 2.2%） |
| Style Consistency | **0.8852** | 0.8827 | 0.8766 | ≥ 0.85 ✅ |
| Refusal Appropriateness | **0.9381** | 0.9094 | 0.9211 | ≥ 0.90 ✅ |
| P90 延迟 | 1.56 s | 1.71 s | 2.42 s | ≤ 10 s ✅ |

> 结论：hybrid 优于 vector-only，重排对检索类指标提升最大（Context Precision +24% vs C2）。
> **五项质量指标达成四项且全部达到进阶线**，合规率差 2.2%。
> 注意检索最优（C3）与合规最优（C1）**不是同一配置**——检索更准会让模型更多尝试作答，
> 其中一部分未通过严格细则；两项指标需联合权衡。
> 离线链路验证阶段的数字（哈希向量 + 规则评判）见 `reports/archive/`，用于证明链路与评测方法本身可跑通。

完整报告：[reports/EVALUATION-REPORT.md](reports/EVALUATION-REPORT.md)　运行方式：[RUNBOOK.md](RUNBOOK.md)

## 目录结构

根目录只保留入口文档与工程文件，其余文档集中在 `docs/`，评测产物集中在 `reports/`。

```
rag_task/
├── README.md                  # 入口与核心结论
├── RUNBOOK.md                 # 运行手册
├── docs/                      # 分析、设计与操作文档
├── reports/                   # 评测、验收、运维报告（llm/ 为真实模型产物）
├── src/rag/                   # 服务实现
├── scripts/                   # 一键脚本（入库 / 评测 / 报告 / 诊断）
├── configs/                   # 配置（三配置、真实模型、Key 示例）
├── data/                      # 语料、索引、评测集
├── models/                    # 本地 ONNX 模型
├── logs/                      # 结构化日志（JSONL）
├── pyproject.toml / uv.lock   # 依赖与锁文件
├── docker-compose.yml         # 可选组件（Qdrant / Redis）
└── .env.example               # API Key 与端点配置模板
```

### 根目录

| 文件 | 内容 |
|---|---|
| [README.md](README.md) | 索引与核心结论 |
| [RUNBOOK.md](RUNBOOK.md) | 运行手册：环境、命令、配置参考、真实模型切换、常见问题 |

### docs/

| 文件 | 内容 | 用途 |
|---|---|---|
| [SOURCE-DOC.md](docs/SOURCE-DOC.md) | 需求文档原文提取（含提取方式与完整性核对） | 溯源，避免理解偏差 |
| [REQUIREMENTS-ANALYSIS.md](docs/REQUIREMENTS-ANALYSIS.md) | 需求定性、结构地图、隐含需求、模糊点、评分陷阱 | 主分析 |
| [METRIC-DEFINITIONS.md](docs/METRIC-DEFINITIONS.md) | 全部量化指标的口径定义、公式、评测方法、Judge 设计 | 解决"指标未定义"风险 |
| [ARCHITECTURE-AND-ROADMAP.md](docs/ARCHITECTURE-AND-ROADMAP.md) | 目标架构、配置模型、日志字段字典、里程碑与实验设计 | 实现指南 |
| [TRACEABILITY-MATRIX.md](docs/TRACEABILITY-MATRIX.md) | 需求 → 交付物 → 证据 → 验收方式 的追踪矩阵 | 验收自查 |
| [RISKS-AND-OPEN-QUESTIONS.md](docs/RISKS-AND-OPEN-QUESTIONS.md) | 风险清单、需向出题方确认的问题、默认假设 | 风险控制 |
| [TECH-STACK-SELECTION.md](docs/TECH-STACK-SELECTION.md) | 技术选型：逐层论证、被排除方案、成本模型、模型对照实验设计 | 选型决策 |
| [EXECUTION-PLAN.md](docs/EXECUTION-PLAN.md) | 执行计划：M0 任务拆解、目录结构、验收标准、明确的禁区 | 下一步行动 |
| [LOG-FIELD-DICTIONARY.md](docs/LOG-FIELD-DICTIONARY.md) | 日志字段字典与样例日志（由代码生成） | 交付物 |
| [API-KEY-SETUP.md](docs/API-KEY-SETUP.md) | 真实模型 API Key 配置指南：注入方式、厂商对照、错误排查 | 操作指南 |
| [Asst Manager, Backend Developer,AKP.docx](<docs/Asst Manager, Backend Developer,AKP.docx>) | 原始需求文档 | 溯源 |

### reports/

| 文件 | 内容 | 用途 |
|---|---|---|
| [EVALUATION-REPORT.md](reports/EVALUATION-REPORT.md) | 评测报告：方法、三配置对比、达标情况、诊断、局限 | 交付物 |
| [ACCEPTANCE-CHECK.md](reports/ACCEPTANCE-CHECK.md) | 验收指标逐项核对（当前结论） | 验收自查 |
| [llm/ACCEPTANCE-CHECK-LLM.md](reports/llm/ACCEPTANCE-CHECK-LLM.md) | 真实模型版验收细节与缺陷修复记录 | 交付物 |
| [comparison.md](reports/comparison.md) | 三配置对比表与结论 | 交付物 |
| [diagnosis_report.md](reports/diagnosis_report.md) | 两处问题的受控实验与前后对比 | 交付物 |
| [ops_report_llm_c3_hybrid_rerank.txt](reports/ops_report_llm_c3_hybrid_rerank.txt) | 运维报告（txt/CSV 双份） | 交付物 |
| [archive/](reports/archive/) | 离线阶段与标注修复前的历史产物 | 追溯 |

## 核心结论

1. **文档性质**：技术评估型案例（Case Study），正文只覆盖 `Mid-Level Developer` 一个角色。文件名中的 Asst Manager、AKP 在正文中没有对应章节，不存在隐藏要求。

2. **交付物本质**：一个可配置的多轮 RAG 问答 + 生成服务，跑在中英双语、含部分扫描件的内部知识库上。技术栈自由，**评分点不在技术选型本身，而在支撑选型的量化证据链**。

3. **指标是分层的**：全局约束给出及格线（Faithfulness ≥ 0.85、Context Precision ≥ 0.70、生成三项 ≥ 80%），非功能章节给出进阶线（三项提升到 90% / 90% / 0.85）。目标应直接按进阶线设计。

4. **最大的隐含成本是评测数据集**：文档未提供任何语料与标注。Faithfulness、Context Precision、Answer Compliance、Refusal Appropriateness 全部依赖"问题 + 标准答案 + 标准证据片段 + 对抗样本"的标注集，这是必须自建、且应最先启动的工作。

5. **三个最容易被漏掉的需求**：多轮对话的查询改写（正文只出现一次）、扫描件的 OCR 入库链路、缓存（仅在 Objective 中提及，但运维报告强制要求 cache hit rate）。

6. **一个必须主动制造的交付物**："至少 2 个问题诊断 + 修复后提升 ≥ 10%"。如果所有指标一次做绿，这条需求就无法交付——必须在过程中主动记录真实退化并留下前后对比证据。

## 建议的下一步

1. 先确认 [RISKS-AND-OPEN-QUESTIONS.md](docs/RISKS-AND-OPEN-QUESTIONS.md) 中的待确认问题，无法确认的按其中"默认假设"推进。
2. 按 [ARCHITECTURE-AND-ROADMAP.md](docs/ARCHITECTURE-AND-ROADMAP.md) 的 M0 开始：先建评测数据集与日志/指标骨架，再写检索代码。
3. 每条需求完成后，用 [TRACEABILITY-MATRIX.md](docs/TRACEABILITY-MATRIX.md) 逐项自查证据是否齐备。
