# 需求分析
> English version: [REQUIREMENTS-ANALYSIS.en.md](REQUIREMENTS-ANALYSIS.en.md)


源文档：`Asst Manager, Backend Developer,AKP.docx`（原文见 [SOURCE-DOC.md](SOURCE-DOC.md)）

## 一、文档定性

这份文档是**技术评估型 Case Study（面试/考核题）**，不是甲方需求规格书。判断依据：

- 标题为 `Case Study – RAG + Generative AI Service`，副标题为 `Role: Mid-Level Developer`。
- 全文没有业务方、上下文背景、既有系统、数据来源等真实项目必有的信息。
- 明确写着 "Candidates may choose any tech stack, but all key technical choices must be justified in the deliverables with clear, quantitative evidence and validation" —— 这是考核语言，说明**评分点不在技术选型本身，而在支撑选型的量化证据链**。

**文件名与正文不一致**：文件名包含 `Asst Manager`、`Backend Developer`、`AKP` 三个标识，但正文只覆盖 `Mid-Level Developer` 一个角色，没有管理岗或 AKP 相关章节。因此不要假设文档中还有隐藏要求；若确实需要其他角色的要求，需另行索取。

## 二、需求结构地图

文档可按四层理解，其中 L1 是及格线，L3 的第 3 条是进阶加分线。

### L1 全局约束（Global Constraints）

适用于本角色，除非被下方条款覆盖。

| 类别 | 要求 |
|---|---|
| 性能 | 90% 的 QA 请求端到端 ≤ 10 秒；单实例支持 ≥ 5 并发 |
| 成本 | 给出每 1000 次调用的 token 成本估算；模型版本选型需说明质量/成本/延迟权衡 |
| 质量 | RAG：Faithfulness ≥ 0.85（需自定义评测方法）；Context Precision ≥ 0.70 |
| 生成质量 | Answer Compliance ≥ 80%；Style Consistency ≥ 80%；Refusal Appropriateness ≥ 80% |
| 日志与追踪 | 结构化日志，足以支撑生成监控与问题诊断 |
| 安全 | 最小化 prompt 注入防御；基础 PII 处理；所有答案必须严格基于检索上下文 |

### L2 功能需求（Functional Requirements）

| 编号 | 需求 | 关键点 |
|---|---|---|
| FR1 | 检索控制 | 至少两种模式：vector-only、hybrid；重排器开关**必须通过配置控制，不允许改代码** |
| FR2 | 拒答与安全 | 三种触发条件：置信度低、query 越界、安全规则命中 → 返回**带引导的拒答** |
| FR3 | 隐私 | PII 脱敏必须**同时覆盖输出与日志** |
| FR4 | 运维报告 | 产出 txt/CSV，字段强制包含：p50/p95 延迟、token 用量、缓存命中率、拒答率、答案合规率 |

### L3 非功能与量化指标

| 编号 | 需求 | 关键点 |
|---|---|---|
| NFR1 | 检索质量 | 必须对比三种配置：vector-only / hybrid / hybrid+rerank，**给出量化结果和结论** |
| NFR2 | 可演进性 | 检索策略可换、模型版本可换、指标与日志可扩展 |
| NFR3 | 生成质量（进阶目标） | Answer Compliance ≥ 90%；Refusal Appropriateness ≥ 90%；Style Consistency ≥ 0.85 |
| NFR4 | 问题诊断 | 至少 2 个问题，含日志/指标证据、修复理由、**修复后提升 ≥ 10%** |

### L4 交付物

| 交付物 | 说明 |
|---|---|
| 完整代码与配置 | 含配置化检索/重排/模型/阈值 |
| 一键评测脚本 | 单条命令跑出全部指标 |
| 评测报告 | 必须含前后对比（before/after） |
| 日志字段字典 + 样例日志 | 字段含义、类型、示例 |

## 三、硬性指标全貌

| 维度 | 及格线（L1） | 进阶线（L3.3） |
|---|---|---|
| 端到端延迟 | P90 ≤ 10s | — |
| 并发 | ≥ 5 并发 / 单实例 | — |
| 成本 | 每千次调用 token 成本 + 选型权衡 | — |
| Faithfulness | ≥ 0.85 | — |
| Context Precision | ≥ 0.70 | — |
| Answer Compliance | ≥ 80% | ≥ 90% |
| Style Consistency | ≥ 80% | ≥ 0.85 |
| Refusal Appropriateness | ≥ 80% | ≥ 90% |
| 修复后提升 | — | ≥ 10% × 2 处 |

注意阈值量纲不一致：Compliance 用百分比（80%/90%），Style Consistency 用 0–1（80%/0.85），二者数值等价，但**报告里应统一口径**，避免验收方误读。

## 四、文档没写但必须实现的隐含需求

1. **标注评测数据集（最高优先级）**。文档未提供任何语料。Faithfulness、Context Precision、Compliance 都需要"问题 + 标准答案 + 标准证据片段"，Refusal Appropriateness 还需要 out-of-scope / 不安全 / 低置信度的对抗样本。这套数据集需自建，且必须在写检索代码之前启动。
2. **多轮对话能力**。仅在第 3 段出现一次，但这是全篇的业务前提。需要会话状态管理、指代消解与查询改写（把"它的生效时间呢？"补全为独立查询），以及多轮场景的评测样本。漏掉它会直接压制 Context Precision。
3. **扫描件 OCR 入库链路**。第 3 段提到 "a small portion of scanned PDFs"，意味着入库阶段需要解析 + OCR + 版面清洗 + 质量校验。OCR 质量是检索质量的上限因素。
4. **双语处理**。中英混排语料意味着需要多语言 embedding、语言识别、跨语言检索支持；BM25 侧必须有中文分词，否则 hybrid 退化为英文关键词匹配。
5. **缓存**。"caching" 只在 Objective 出现一次，未列为功能需求，但 FR4 强制要求报告 cache hit rate —— 缓存是硬性隐含需求，且必须可度量（精确匹配 vs 语义缓存、TTL、文档更新后的失效策略）。
6. **可诊断的日志深度**。NFR4 要求"用日志/指标证据定位 2 个问题"，反推日志至少需要：trace/request ID、分阶段耗时、检索与重排分数、**每次请求的配置快照**、token 用量。配置快照尤其关键——没有它，三配置对比与前后对比的数据不可信。
7. **强制引用（grounding）**。"all answers must strictly ground to retrieved context" 意味着答案必须附证据引用，且"无证据 → 拒答"应作为默认策略。
8. **可复现性**。Objective 中 "reproducible diagnosis" 要求固定随机种子、固定模型版本、配置参数化，一键脚本重跑应得到一致报告。
9. **成本核算能力**。每千次调用成本需要逐请求 token 统计 + 价格表 + 平均 token 假设，不能拍脑袋估算。

## 五、模糊点与建议口径

文档把最难定义的部分留白了。交付物中必须显式给出"定义 + 实现方式"，否则指标无法验收。完整定义见 [METRIC-DEFINITIONS.md](METRIC-DEFINITIONS.md)，此处仅列总览：

| 模糊表述 | 问题 | 建议口径 |
|---|---|---|
| Answer Compliance | 未定义 | 带评分表的 LLM-as-judge 通过率：严格基于检索证据、给出引用、符合回答格式、无编造事实 |
| Style Consistency | 未定义 | 多维度 0–1 评分：语言跟随提问语言、结构统一、语气一致 |
| Faithfulness | 说"define your evaluation method" | claim 级蕴含判定：拆原子断言，逐条对照上下文 |
| Context Precision | 未定义 | 标注证据片段上的 rank-weighted 命中率 |
| Refusal Appropriateness | 未定义 | **双向**统计：正确拒答 + 未过度拒答，取平衡准确率 |
| 端到端延迟 | 未定义边界 | 明确为"请求进入 → 完整响应返回"（或声明首 token），并给出实测 |
| ≥5 并发 | 未定义场景 | 定义并发模型、请求分布、时长与硬件规格 |
| "置信度低" | 未定义阈值 | 检索分数阈值 + 判定器 + 范围分类器的组合策略 |
| 语料规模 | 未给出 | 假设文档数/页数/总 token，并在报告中声明 |

## 六、评分陷阱与高风险点

1. **"2 个问题诊断"必须主动制造**。若所有指标一次做绿，这条需求无法交付。必须在开发过程中主动记录真实退化事件并保留修复前后数据（候选剧本见 [ARCHITECTURE-AND-ROADMAP.md](ARCHITECTURE-AND-ROADMAP.md)）。
2. **自评闭环**。用同一模型同时生成与打分会被质疑。建议生成与评判使用不同模型，并抽人工核验子集，报告 judge 与人工的一致率。
3. **三配置对比不可比**。必须固定评测集、prompt、生成模型，只变检索配置，并用配置快照 + 版本号锁定。
4. **延迟约束叠加**。10s P90 同时要满足重排 + 生成，需要并行检索、超时降级、结果缓存，否则 P90 容易失守。
5. **PII 脱敏与排障矛盾**。日志既要脱敏又要可追踪，建议保留哈希或占位符，而不是直接删除字段。
6. **指标量纲混用**。百分比与 0–1 混排，报告中需统一并注明。
7. **hybrid 不等于更好**。引入 BM25 会带来词法噪声，Context Precision 可能下降；这既是风险，也是 NFR4 的天然诊断素材。

## 七、建议推进顺序

| 阶段 | 内容 | 为什么在这个位置 |
|---|---|---|
| M0 | 评测数据集 + 日志/指标骨架 | 没有它，后面所有"量化证据"都无从谈起 |
| M1 | vector-only 基线 + 结构化日志 | 建立可对比的起点 |
| M2 | hybrid + 可配置重排 | 满足 FR1，产出三配置对比 |
| M3 | 拒答、安全、PII | 满足 FR2/FR3 与安全约束 |
| M4 | 一键评测脚本 + 三配置报告 | 满足 NFR1 与交付物要求 |
| M5 | 缓存 + 运维报告 | 满足 FR4 与 Objective |
| M6 | 2 处问题诊断 + 前后对比 | 满足 NFR4（依赖 M1–M5 的日志） |
| M7 | 文档、配置说明、日志字典 | 收口交付物 |

详细任务拆分见 [ARCHITECTURE-AND-ROADMAP.md](ARCHITECTURE-AND-ROADMAP.md)。
