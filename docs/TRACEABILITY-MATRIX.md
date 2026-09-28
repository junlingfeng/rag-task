# 需求追踪矩阵与验收清单
> English version: [TRACEABILITY-MATRIX.en.md](TRACEABILITY-MATRIX.en.md)


参考段落号对应 [SOURCE-DOC.md](SOURCE-DOC.md) 中的原文编号。

## 一、追踪矩阵

| ID | 原文位置 | 需求 | 交付物 / 实现 | 证据 | 验收方式 |
|---|---|---|---|---|---|
| R1 | §3 | 多轮 RAG 问答 + 生成服务 | 服务代码 + 会话管理 + 查询改写 | 多轮会话样例 | 连续追问可正确指代消解 |
| R2 | §3 | 中英双语语料 | 多语言 embedding + 中文分词 | 双语检索结果对比 | 中文问检英文文档可用 |
| R3 | §3 | 含扫描件 PDF | OCR 入库链路 | OCR 质量抽样报告 | 扫描件内容可被检索命中 |
| R4 | §3 | 技术选型需量化论证 | 选型对比章节 | 对照实验数据 | 每个关键选型都有数据支撑 |
| R5 | §6 | P90 ≤ 10s | 并行检索 + 超时降级 + 缓存 | 压测与线上 P90 | P90 实测 ≤ 10s |
| R6 | §6 | 单实例 ≥ 5 并发 | 并发压测 | 压测报告（含硬件规格） | 5 并发下 P90 仍 ≤ 10s |
| R7 | §8 | 每千次调用 token 成本 | 成本核算脚本 + 价格表 | CostPer1k 表 | 给出公式、假设与结果 |
| R8 | §8 | 模型版本选型权衡 | 模型对比实验 | 质量/成本/延迟三方对照 | 结论有明确取舍理由 |
| R9 | §10 | Faithfulness ≥ 0.85 | judge 流程 | 指标报告 | 实测值达标且方法已定义 |
| R10 | §10 | Context Precision ≥ 0.70 | 标注证据 + 排序加权计算 | 指标报告 | 实测值达标 |
| R11 | §11 | Compliance ≥ 80% | 合规检查表 + judge | 指标报告 | 实测值达标 |
| R12 | §11 | Style Consistency ≥ 80% | 三维度评分 | 指标报告 | 实测值达标 |
| R13 | §11 | Refusal Appropriateness ≥ 80% | 双向统计 | 指标报告 | 实测值达标 |
| R14 | §13 | 结构化日志 | JSON 日志 + 字段字典 | 字段字典 + 样例日志 | 字段齐全、可解析 |
| R15 | §15 | prompt 注入防御 | 检测规则/分类器 | 对抗样本测试结果 | 注入样本被拦截或拒答 |
| R16 | §15 | PII 处理 | 输出与日志双路脱敏 | 脱敏前后样例 | 日志与响应中无明文 PII |
| R17 | §15 | 严格基于检索上下文 | 引用强制 + 无据拒答 | Faithfulness 指标 | 无上下文外编造 |
| R18 | §17 | 可配置检索模式 | 配置文件 | 三份配置样例 | 改配置即可切换 |
| R19 | §17 | 重排 | 重排模块 + 开关 | 配置开关演示 | 无代码改动启停重排 |
| R20 | §17 | 缓存 | 缓存层 | 命中率报告 | 命中率可统计、失效策略明确 |
| R21 | §17 | 可复现诊断 | 固定种子 + 版本化配置 | 重跑一致的报告 | 两次重跑结果一致 |
| R22 | §20 | vector-only 与 hybrid | 两种检索实现 | 三配置对比 | 两者均可运行 |
| R23 | §20 | 重排配置化 | 见 R19 | 配置文件 | 无需改代码 |
| R24 | §22 | 低置信度拒答 | 阈值 + 判定器 | 低置信度子集测试 | 正确拒答并给出引导 |
| R25 | §22 | 越界拒答 | 范围判定 | 越界子集测试 | 正确拒答并给出引导 |
| R26 | §22 | 安全规则拒答 | 安全策略 | 不安全子集测试 | 正确拒答并给出引导 |
| R27 | §24 | PII 脱敏（输出 + 日志） | 见 R16 | 样例 | 双路均脱敏 |
| R28 | §26 | 运维报告（txt/CSV） | 报告生成脚本 | 报告文件 | 六个强制字段齐全 |
| R29 | §29 | 三配置量化对比与结论 | 对比实验 | 对比表 + 结论段 | 有结论，不只给数据 |
| R30 | §31 | 可演进设计 | 接口化 + 配置化 | 代码结构说明 | 换模型/换检索不改调用方 |
| R31 | §33 | 进阶生成质量目标 | 见 R11–R13 | 指标报告 | 达到 90% / 90% / 0.85 |
| R32 | §35 | 2 处问题诊断 | 诊断报告 | 日志证据 + 前后对比 | 每处提升 ≥ 10% |
| R33 | §37 | 完整代码与配置 | 代码仓库 | 可运行 | 一键启动 |
| R34 | §37 | 一键评测脚本 | eval 脚本 | 单命令产出报告 | 无需手工步骤 |
| R35 | §37 | 评测报告（前后对比） | 报告文件 | before/after 数据 | 对比清晰 |
| R36 | §37 | 日志字段字典 + 样例日志 | 文档 | 字段表 + JSON 样例 | 与实现一致 |

## 二、最终验收清单

### 功能

- [x] 多轮对话可用，追问能正确改写（`rewrite_query`，多轮改写轮次检索精度 0.486）
- [x] vector-only 与 hybrid 两种模式可运行
- [x] 重排通过配置启停，零代码改动
- [x] 三类拒答均触发且输出带引导（`refusal_reason` 三分类均有日志计数）
- [x] 输出与日志双路 PII 脱敏
- [x] 运维报告可生成 txt 与 CSV

### 指标

- [x] Faithfulness ≥ 0.85 —— 实测 **1.0000**（真实模型评测，`reports/llm/`）
- [x] Context Precision ≥ 0.70 —— 实测 **0.8437**（C3 hybrid+重排）
- [ ] Answer Compliance ≥ 80% / 90% —— 实测 0.7824（**差 2.2%**，未合规项约半数为过度拒答）
- [x] Refusal Appropriateness ≥ 90% —— 实测 **0.9381**（三配置均 ≥ 0.90）
- [x] Style Consistency ≥ 0.85 —— 实测 0.8852
- [x] P90 ≤ 10s，5 并发下仍成立 —— 单线程 P90 2.42s；5 并发 50 请求 0 错误、P90 4.18s（真实模型实测）
- [x] 给出每千次调用成本与选型权衡 —— $0.2661–$0.2806/千次（**示例单价，待替换为官方当期价**）

### 实验与诊断

- [x] 三配置对比表 + 明确结论（hybrid > vector-only，重排收益最大）
- [x] 2 处问题诊断，各含日志证据与 ≥ 10% 提升数据（Recall@5 +24.2%；正确应答率 +157.2%）
- [x] 评测结果可复现（同一配置重跑指标一致）

### 交付物

- [x] 完整代码与配置（`src/rag/`、`configs/`）
- [x] 一键评测脚本（`scripts/eval.py`、`scripts/run_all.sh`）
- [x] 评测报告（含 before/after，`reports/EVALUATION-REPORT.md`）
- [x] 日志字段字典 + 样例日志（`docs/LOG-FIELD-DICTIONARY.md`）

### 未达标项的成因与解除条件

| 未达标项 | 根本原因 | 解除条件 |
|---|---|
| Answer Compliance ≥ 80% | 47 条未合规中 21 条"该答却拒答"、25 条作答未过 judge 细则 | 放宽 grounding 阈值、强化引用格式提示词 |
| 成本口径 | 仍使用示例单价 | 替换 `price_*_per_1m` 为官方当期价后重算 |

> 离线阶段（哈希向量 + 规则评判）的实测数据与未达标原因见 `reports/archive/ACCEPTANCE-CHECK-offline-20260919.md`，
> 该阶段用于验证链路与评测方法本身，不作为最终结论。

## 三、实现证据索引（R1–R36 → 代码/数据位置）

上表为需求追踪的设计视图；实现完成后，每条需求对应的落地位置如下。

| ID | 实现位置 | 实测证据 |
|---|---|---|
| R1 多轮 | `src/rag/pipeline.py` `rewrite_query` | `reports/items_c3_hybrid_rerank.jsonl` 中 `requires_rewrite=true` 的轮次 |
| R2 双语 | `src/rag/retrieve/embedding.py`、`lexical.py`（CJK 二元组） | 评测集 zh/en 各 78 项 |
| R3 扫描件 | `src/rag/ingest/scanned.py` + `parse.py`（RapidOCR） | 入库日志 `扫描件解析引擎：['rapidocr']` |
| R4 选型论证 | `TECH-STACK-SELECTION.md` | — |
| R5 延迟 | `scripts/loadtest.py` | `reports/llm/loadtest.json`（5 并发 50 请求，P90 4.18s，真实模型） |
| R6 并发 | 同上 | 5 并发 0 错误 |
| R7 成本 | `src/rag/pipeline.py` 成本计算 + `configs/base.yaml` 价格项 | `reports/ops_report_*.txt` 的 `cost_usd_per_1k_calls` |
| R8 模型选型 | `configs/base.yaml` generation 段 | 报告第 6 节（待接入真实模型后重跑） |
| R9 Faithfulness | `src/rag/guardrails/support_score` + `eval/judge.py`（LLM judge） | `reports/llm/eval_llm_c*.json` |
| R10 Context Precision | `src/rag/eval/metrics.py` | `reports/llm/comparison.md` |
| R11–R13 生成质量 | `src/rag/eval/judge.py`（LLM judge） | `reports/llm/eval_llm_c*.json` |
| R14 结构化日志 | `src/rag/observability.py` | `docs/LOG-FIELD-DICTIONARY.md` |
| R15 注入防御 | `src/rag/guardrails/INJECTION_PATTERNS` | 评测 unsafe 子集 20 项 |
| R16 PII | `src/rag/pii.py` + `observability._redact_processor` | 日志中 `pii_redacted_fields` |
| R17 严格接地 | `pipeline` 生成后 `support_score` 判定 + 引用要求 | `reports/items_*.jsonl` 的 `compliance.checks.grounded` |
| R18–R19 检索模式/重排开关 | `configs/c1..c3 yaml` | `configs` 切换即可，`reports/comparison.md` |
| R20 缓存 | `src/rag/cache/` | `reports/ops_report_c3_hybrid_rerank.txt` 的缓存命中率；评测时按方法学关闭 |
| R21 可复现 | `Config.fingerprint()` 写入日志 | 日志 `config_fingerprint` |
| R22–R23 | 同 R18–R19 | 同 R18–R19 |
| R24–R26 拒答 | `src/rag/guardrails/` + `pipeline` guardrail 段 | 日志 `refusal_reason` 三分类计数 |
| R27 PII 双路 | 同 R16 | 输出与日志均已脱敏 |
| R28 运维报告 | `scripts/report.py` | `reports/ops_report_*.txt/.csv` |
| R29 三配置对比 | `scripts/eval.py --all` | `reports/llm/comparison.md` |
| R30 可演进 | `Config` 全参数化 + `Retriever`/`Generator` 接口 | 换后端只改 YAML |
| R31 进阶目标 | 同 R11–R13 | 见评测报告第 4 节达标情况 |
| R32 问题诊断 | `scripts/diagnose.py` | `reports/diagnosis_report.md` |
| R33–R34 代码与一键脚本 | `src/`、`scripts/run_all.sh` | — |
| R35 评测报告 | `scripts/gen_eval_report.py` | `reports/EVALUATION-REPORT.md` |
| R36 日志字典 | `scripts/gen_log_docs.py` | `docs/LOG-FIELD-DICTIONARY.md` |
