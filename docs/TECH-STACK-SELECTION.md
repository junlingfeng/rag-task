# 技术选型分析
> English version: [TECH-STACK-SELECTION.en.md](TECH-STACK-SELECTION.en.md)


> 版本：v1.0　日期：2026-09-18
> 上游文档：[REQUIREMENTS-ANALYSIS.md](REQUIREMENTS-ANALYSIS.md)、[METRIC-DEFINITIONS.md](METRIC-DEFINITIONS.md)、[ARCHITECTURE-AND-ROADMAP.md](ARCHITECTURE-AND-ROADMAP.md)
>
> **实现后的偏差说明**（2026-09-25 补记）：本文件是选型阶段的分析，实施中有四处与当时推荐不同，
> 均基于实测数据调整，详见 [RUNBOOK.md](../RUNBOOK.md) 第 5 节与 `reports/llm/ACCEPTANCE-CHECK-LLM.md`：
> 1. **向量库**：实际采用进程内 numpy 存储（零依赖、一键可复现），Qdrant/Redis 保留为可选后端；
> 2. **Embedding**：实际使用 MiniLM-L12 int8（ONNX，113MB）而非 bge-m3 —— 本机无 PyTorch，
>    且 bge-m3 需 2.2GB；跨语言相似度实测 0.821，可用；
> 3. **重排**：按本文件选型使用 bge-reranker-base，但走 ONNX int8；关键参数是 `max_candidates: 10`
>    （20 候选需 1553ms，超出 800ms 预算会整批降级）；
> 4. **融合算法**：接入真实向量后，加权融合（vector_weight 0.7）实测优于 RRF，已改为默认。

## 0. 选型的判断依据

文档明确写了 "Candidates may choose any tech stack, but all key technical choices must be justified in the deliverables with clear, quantitative evidence and validation"。因此**选型的正确性不由技术先进性决定，而由"能否用数据证明它在约束下最优"决定**。据此确定四条选型准则：

| 准则 | 来源 | 含义 |
|---|---|---|
| C1 延迟与并发 | §6：P90 ≤ 10s、单实例 ≥ 5 并发 | 任何引入不可控时延的组件都必须有超时降级路径 |
| C2 可量化对比 | §29：三配置量化对比 | 检索/重排/生成必须能在同一评测集上自由切换，便于做对照实验 |
| C3 可演进 | §31：换检索策略、换模型、扩指标不改架构 | 组件必须接口化 + 配置化，模型走 OpenAI 兼容抽象 |
| C4 本机可跑可复现 | Objective：reproducible diagnosis | 一键脚本要在单机 Docker 内完整跑通 |

### 0.1 本机环境实测（决定"能不能真跑起来"）

| 项目 | 实测值 | 对选型的影响 |
|---|---|---|
| CPU | Intel i9-9880H（2.3GHz，8 核 16 线程） | 无 CUDA、无 Metal GPU 加速 |
| 内存 | 16 GB | Docker + 向量库 + 本地模型的预算很紧 |
| 系统 | macOS 14.8.9（Intel） | 无法使用 Apple Silicon 的 MPS 加速 |
| Python | 系统自带 3.8.2 | **过旧**，bge-m3、Pydantic v2、PaddleOCR 均需 ≥3.9/3.10 |
| 包管理器 | 已安装 `uv` | 可用 `uv` 直接拉取 Python 3.11/3.12，无需污染系统环境 |
| Docker | 24.0.7 + Compose v2.23.3 | 单机多容器方案可行 |
| Node | v22.22.1 | 可跑 k6/前端 demo |
| Java | 仅 JDK 8 | 排除 JDK 8 上的现代 Spring AI 方案（需 17+） |
| Ollama | 已安装，未启动，无模型 | 本地大模型生成需先下载（数 GB） |

**由此得到两条硬结论**：

1. **本地跑生成模型不可行**。16GB Intel CPU 上跑 7B 量化模型，实测吞吐通常在个位数 token/s 量级（需自测），而单次要生成约 250 token，且要求 5 并发下 P90 ≤ 10s —— 数量级不匹配。生成必须走 API，本地模型只能作为"数据不出内网"的降级预案并如实说明其不达标。
2. **Python 版本必须自建**。用 `uv python install 3.12` 生成项目级环境，这是 M0 的第一个动作。

## 1. 选型总览

| 层次 | 主选 | 备选 | 不选 | 核心理由 |
|---|---|---|---|---|
| 服务语言/框架 | Python 3.12 + FastAPI + Pydantic v2 | Node + NestJS | Spring Boot（本机仅 JDK 8） | RAG 生态（模型、评测、解析）Python 最全，改造最少 |
| 文档解析 | PyMuPDF + Docling | Unstructured | 纯正则解析 | 保留版面与阅读顺序，支持表格，兼容双语 |
| OCR | RapidOCR（ONNXRuntime） | PaddleOCR（精度优先） | Tesseract | 中文识别质量 + 无 paddlepaddle 重依赖，Intel CPU 友好 |
| 切分策略 | 结构化递归切分 + 父子块（small-to-big） | 纯固定长度 | 纯语义切分 | 兼顾 Context Precision（小块命中）与 Faithfulness（父块补全） |
| Embedding | bge-m3（本地 ONNX int8） | text-embedding-3-large（API） | 单语模型 | 中英双语 + 长上下文 + 同时产出稠密与稀疏向量 |
| 向量与检索 | Qdrant 单节点（稠密 + 稀疏 + RRF 融合） | OpenSearch / Elasticsearch | Milvus、faiss-only | 原生 hybrid 融合、占用小、单机 Docker 友好 |
| 重排 | bge-reranker-base / jina-reranker-v2-base（本地） | Cohere Rerank API | 不设重排 | 278M 级交叉编码器在 CPU 上可控；更大模型需 GPU |
| 生成模型 | 小模型主用 + 中模型兜底（OpenAI 兼容 API） | 旗舰模型 | 本地 7B 模型 | 延迟与成本可行，且可配置切换做三方对比 |
| 编排 | 自研薄管道 | LlamaIndex（仅用于入库） | 重型 LangChain 链 | 每个阶段的耗时与分数必须可归因，框架黑盒会破坏诊断能力 |
| 缓存 | Redis（精确）+ 向量语义缓存 | 仅精确缓存 | 无缓存 | 命中率是 FR4 强制指标 |
| 日志/追踪 | structlog JSONL + OpenTelemetry span | Langfuse 自托管 | 纯文本日志 | 结构化日志同时支撑运维报告与问题诊断 |
| 评测 | 自研指标脚本 + LLM-as-judge，RAGAS 交叉校验 | 直接用 RAGAS | 人工打分 | 指标定义权要握在自己手里，RAGAS 仅作第二意见 |
| 安全 | 规则 + 分类器双层注入检测 + Presidio/正则 PII | 仅规则 | 无防护 | 需同时报告攻击拦截率与误拦截率 |
| 压测 | k6 | Locust | 手写脚本 | 并发与 P90 需要可复现的压测证据 |
| 部署 | Docker Compose 单机 | 单进程 + 本地依赖 | K8s | 需求只要求单实例 ≥5 并发 |

## 2. 逐层论证

### 2.1 语言与框架：Python 3.12 + FastAPI（附：为什么不选 Java）

先给结论的准确表述：**Java 完全能做这个服务，这不是"能不能"的问题，而是"单位工作量能换来多少可验收证据"的问题。** 判定 Python 胜出的核心原因不是语言性能，而是**本交付物的重心落在模型与评测工具链上，而这些工具链的一等公民几乎全在 Python**。

#### 2.1.1 候选总览

| 候选 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| Python + FastAPI | embedding / rerank / OCR / 评测 / 数据分析全在一等生态内；异步 IO 足以支撑 5 并发；Pydantic 适配配置校验 | 需自建 Python 环境（本机仅 3.8.2，用 `uv` 可解） | **主选** |
| Java + Spring Boot | 工程治理最成熟（DI、事务、Actuator、Micrometer）；Lucene/ES 原生在 JVM 内；中文分词库强 | 本机仅 JDK 8；OCR 无一等库；评测框架缺位；本地模型适配需自建 | 备选，仅在特定条件下更优（见 2.1.7） |
| Node + NestJS | 与 k6 / 前端同栈 | 关键能力几乎全靠 Python 服务兜底，等于双运行时 | 不选 |

#### 2.1.2 决定性因素：交付物的工作量分布

这个 Case Study 的交付物看起来是"一个服务"，实际重心在**实验与评测**。按交付要求拆解工作量（估算，需在实施中校准）：

| 工作块 | 估算占比 | 哪门语言占优 |
|---|---|---|
| 评测数据集建设与标注 | ~25% | 无语言差异（人工活） |
| 解析 / OCR / 切分实验 | ~15% | **Python**（docling、PyMuPDF、RapidOCR、MinerU 仅 Python） |
| 检索与重排实现 | ~15% | 平手偏 Python（模型侧 Python 更顺） |
| 生成与护栏 | ~15% | 平手（SDK 双方都有） |
| 评测、指标计算与报告 | ~20% | **Python**（RAGAS / DeepEval / pandas / matplotlib 仅 Python） |
| 服务、配置、日志、缓存 | ~10% | **Java** |

**Java 占优的部分只占约 10%，Python 占优或独有的部分超过 50%。** 而交付物只有一套语言，因此选择 Python 等于把优势集中在占比更大的那一侧。若本任务是一个高并发交易类服务，这个比例会反过来 —— 这也是为什么在别的场景下我会选 Java。

#### 2.1.3 逐项能力对照

| 能力 | Python | Java | 胜出方 |
|---|---|---|---|
| PDF 解析与版面/阅读顺序 | PyMuPDF、pdfplumber、docling、MinerU、marker | PDFBox、Tika（文本提取好，版面与表格弱） | Python |
| OCR（中文 + 表格） | PaddleOCR、RapidOCR、docling | Tess4J（Tesseract 封装），无 PaddleOCR 等价物 | **Python（差距最大的一项）** |
| Embedding 模型运行 | FlagEmbedding、sentence-transformers、transformers 开箱即用 | DJL + ONNX Runtime 可行，`ai.djl.huggingface:tokenizers` 提供分词绑定，但需自行处理导出、量化、池化 | Python |
| 重排模型运行 | 同上，cross-encoder 现成 | 同 embedding，需自建 | Python |
| 中文分词 / BM25 | jieba、pkuseg | HanLP、ansj、jieba-analysis、Lucene IK/smartcn | **Java**（但用 bge-m3 稀疏向量可绕开该依赖） |
| 向量库客户端 | Qdrant / Milvus / ES 均有客户端 | 同样齐全，ES 客户端更是一等公民 | 平手 |
| 混合检索融合 | 依赖向量库服务端融合 | 可嵌入 Lucene 自建 | 平手偏 Java |
| LLM SDK | OpenAI Python SDK 是事实标准 | openai-java、LangChain4j、Spring AI 均已可用 | 平手偏 Python |
| 评测框架（Faithfulness / Context Precision 等） | **RAGAS、DeepEval、TruLens、Phoenix** | **无对应成熟框架，需全部自研** | **Python（独有）** |
| PII 检测 | Presidio、spaCy | 无等价库，需自写规则 | Python |
| Prompt 注入分类模型 | HF 模型一行加载 | 需 ONNX + 分词器自建 | Python |
| 实验迭代（误差分析、绘图） | Jupyter + pandas + matplotlib | 需编译-运行循环，或额外接 Python | **Python（独有）** |
| 服务框架成熟度 | FastAPI 够用 | **Spring Boot 明显更强** | **Java** |
| 并发模型 | asyncio 足够（I/O 密集） | JDK 21 虚拟线程 + 响应式 | Java |
| 配置治理 | pydantic-settings + YAML 够用 | Spring Config 更成熟 | Java |
| 可观测性 | structlog + OTel 够用 | Micrometer + OTel 更成熟 | Java |

**归纳**：Java 胜在"服务工程"，Python 胜在"模型与实验"。而本交付物对服务工程的要求很轻（5 并发、单实例、无分布式事务、无高可用要求），对模型与实验的要求很重（三条配置对比、四个质量指标、至少两处问题诊断）。

#### 2.1.4 性能不构成选型理由（量化说明）

常见的选 Java 理由是"JVM 性能更好"，但在本任务的约束下这个理由不成立：

| 指标 | 实际情况 | 结论 |
|---|---|---|
| 服务并发要求 | 单实例 ≥ 5 并发 | 这个量级对两门语言都是无压力的；Python 用 asyncio + httpx 即可 |
| 延迟构成 | LLM 生成占 5–7s（见延迟预算表），检索与重排占 1s 以内，服务框架自身开销在毫秒级 | **语言层差异被生成耗时淹没，占比不足 1%** |
| 工作负载性质 | 网络 I/O 密集（调 LLM、调向量库），非 CPU 密集 | JVM 的吞吐优势要到数千 QPS 才显现，本任务上限是 5 并发 |
| 真正影响 P90 的手段 | 缓存、检索并行、重排超时降级、输出长度限制 | 这些与语言无关 |

**一句话**：换语言救不了延迟，改善架构才能。

#### 2.1.5 Java 的真实优势（不回避）

1. **工程治理成熟度**：Spring 的事务、DI、配置分层、Actuator、Micrometer、安全模块开箱即用，长期维护性好于 FastAPI。
2. **强类型与编译期检查**：大型团队协作与重构安全性更好。
3. **中文检索底蕴**：Lucene / Elasticsearch 在 JVM 内，HanLP 等中文分词库成熟，若确定用 ES 做 hybrid，Java 侧体验更好。
4. **组织与团队因素**：若团队是 Java 团队、运维只支持 JVM、需要与既有 Java 中台对接，Java 的集成与排障成本更低。**这是真实且重要的选型依据，不应被"技术先进性"抹掉**（本工作区存在多个 Spring/Maven 工程，说明该因素在本例中确实存在）。

#### 2.1.6 选 Java 方案在本任务中的实际代价

| 代价 | 具体影响 | 可验证方式 |
|---|---|---|
| JDK 版本门槛 | 本机仅 JDK 8；Spring AI 1.x 需 Spring Boot 3.x + JDK 17+，LangChain4j 1.x 同样需 17+ | `java -version` 已实测 |
| OCR 无一等库 | 必须引 Python 边车或云 OCR，直接破坏"单实例单进程"的简洁性，引入跨语言序列化与额外故障点 | 尝试用纯 Java 实现扫描件入库即可验证 |
| 评测框架缺位 | RAGAS / DeepEval 无 Java 版本，"一键评测脚本"需从 judge 调用、指标计算到报告生成全部自研 | 搜索 Maven 中央仓库无对应坐标 |
| 模型适配自建 | bge-m3 的稠密/稀疏/ColBERT 三通道、池化、量化需自行实现并验证正确性 | 与 Python 侧输出做逐条向量比对 |
| 实验迭代慢 | 调 chunk size、调 top_k、跑三配置对比、做误差分析，Python 在 notebook 里几步完成，Java 需编译-运行循环 | 用同一实验的完成时间对比 |
| 生态样例少 | 遇到问题时可参考的实现与社区经验显著少于 Python，排障时间不可预测 | — |

注意第一项的连锁反应：如果为了 OCR 引入 Python 边车，那么已经变成多语言系统，此时**再坚持用 Java 写主服务，只是把双运行时的成本保留下来，却丢掉了单语言方案的一致性收益**。这是本任务里 Java 路线最尴尬的地方。

#### 2.1.7 决策规则：什么情况下应该改选 Java

| 触发条件 | 说明 |
|---|---|
| 组织强制要求 JVM 技术栈 | 合规或运维红线，此时无讨论余地 |
| 必须嵌入既有 Java 中台，跨语言调用成本高 | 集成边界成本高于模型工具链成本 |
| 团队 Java 能力强、Python 经验薄弱 | **交付速度与可控性是真实收益**，尤其在有时间限制的考核中 |
| 已确定用 Elasticsearch/OpenSearch 做 hybrid，且有 JVM 运维能力 | Lucene 原生在 JVM 内，检索侧体验更好 |
| 允许 Python 边车只承担 OCR 与评测 | 此时 Java 主服务 + Python 边车是合理的分工 |

若满足上述条件，推荐的 Java 技术栈为：**Spring Boot 3 + JDK 21（虚拟线程）+ LangChain4j 或 Spring AI + OpenSearch/Lucene + DJL/ONNX Runtime（重排）+ Redis（缓存）+ Python 边车（仅 OCR 与评测脚本）**。这套方案在能力上完全可交付，只是在模型侧需要更多自建工作。

#### 2.1.8 本节结论

选 Python 的三个理由，按权重排序：

1. **能力覆盖**：OCR、embedding、rerank、评测四大能力在 Python 有一等生态，在 Java 需要自研或引边车（2.1.3 表）。
2. **工作量分布**：交付物的重心是实验与评测（占比 >50%），而 Java 的优势区（服务框架）只占约 10%（2.1.2 表）。
3. **约束匹配**：唯一的性能约束是 5 并发 / P90 10s，其瓶颈由 LLM 生成主导，与语言选择无关（2.1.4 表）。

**同时必须承认**：如果团队是 Java 团队，选 Java 的合理理由是"降低交付风险与排障成本"，而不是"Java 在这个任务上技术更强"。这个理由在考核场景下是成立的，应在选型文档中如实写出，而不是用技术理由包装。**本文档给出的是"在能力与证据产出最优"口径下的结论；若采用组织偏好口径，Java + Python 边车是可辩护的替代方案。**

### 2.2 文档解析与 OCR

语料是四类文档（员工手册、合规指南、技术规范、架构文档），且**含扫描件**。解析质量是检索质量的上限。

| 候选 | 中文 OCR | 依赖重量 | 版面/表格 | 结论 |
|---|---|---|---|---|
| PyMuPDF | —（仅文本层） | 极轻 | 一般 | 数字版 PDF 首选 |
| Docling | 可对接 OCR | 中 | 强（阅读顺序、表格、标题层级） | 结构化解析首选 |
| Unstructured | 可对接 | 重（依赖多） | 中 | 备选 |
| RapidOCR | 好（PaddleOCR 模型 + ONNX） | 轻 | 需自行处理 | **OCR 主选** |
| PaddleOCR | 最好 | 重（paddlepaddle） | 中 | 精度优先时启用 |
| Tesseract | 中文较弱、竖排/表格差 | 轻 | 差 | 不选 |

**设计要点**：OCR 结果必须带置信度标签，低于阈值的块标记为 `low_ocr_confidence` 并在评测中单独统计命中率。这样"扫描件是否真的可检索"就变成可量化结论，而不是主观判断。

### 2.3 切分策略

| 策略 | Context Precision | Faithfulness | 结论 |
|---|---|---|---|
| 固定长度（如 512 token） | 中（易切断语义） | 中（上下文可能不全） | 基线 |
| 结构化递归（按标题层级 + 段落） | 较高 | 较高 | **主选** |
| 纯语义切分 | 高 | 中 | 成本高、结果不稳定，不选 |
| 父子块 small-to-big | 高（小块命中） | 高（父块补上下文） | **与结构化递归叠加使用** |

**尺寸建议**：子块 300–500 token、父块 1200–2000 token、重叠 10–15%。元数据必须包含 `doc_id / section_path / lang / doc_type / page / effective_date / ocr_confidence`，其中 `lang` 与 `effective_date` 直接服务于双语检索与合规时效性问答。

这个设计还有一个额外好处：**"块大小/父块策略"本身就是 NFR4 的一号诊断素材**（切太碎 → Faithfulness 掉；切太大 → Context Precision 掉），天然可产出前后对比数据。

### 2.4 Embedding 模型

| 候选 | 中文 | 英文 | 稀疏向量 | 本地可跑 | 结论 |
|---|---|---|---|---|---|
| bge-m3 | 强 | 强 | ✅ 同时产出稠密/稀疏/ColBERT | ✅（568M，ONNX int8） | **主选** |
| multilingual-e5-large | 强 | 强 | ❌ | ✅ | 备选 |
| text-embedding-3-large | 强 | 强 | ❌ | ❌（API） | 隐私受限时的次选 |
| 单语模型（如 bge-large-zh） | 强 | 弱 | ❌ | ✅ | 不满足双语要求 |

**选 bge-m3 的三条硬理由**：

1. **双语**：题目要求 CN/EN 混合语料，且需要跨语言检索（中文问、英文答），单语模型直接出局。
2. **一模型两通道**：bge-m3 同时输出稠密向量与学习式稀疏权重，使 hybrid 检索的词法通道质量远高于手工 BM25 + 分词，且只需维护一个模型。
3. **隐私**：知识库是内部合规文档，且 FR3 明确要求 PII 处理。本地 embedding 意味着**文档正文不出内网**，这是外部 API embedding 无法提供的（该论据在报告中比"省钱"更有说服力）。

**落地注意**：CPU 上单条 query 编码约在百毫秒量级（需实测）；建库需批量编码，建议 ONNX int8 + 多进程分批，1 万块量级预计数分钟，属于一次性成本。

### 2.5 向量库与 hybrid 检索

| 候选 | hybrid 原生支持 | 单机占用 | 中文 BM25 | 结论 |
|---|---|---|---|---|
| Qdrant | ✅ 稀疏+稠密+native RRF | 低（数百 MB） | 依赖 bge-m3 稀疏向量，无需分词器 | **主选** |
| OpenSearch / Elasticsearch | ✅（ES 8.8+ 有 RRF retriever；OpenSearch 2.11+ 有 hybrid query，RRF 支持需按版本核对） | 高（JVM 2–4GB） | ✅ 内置 CJK 分析器，最成熟 | 备选（企业级说服力强） |
| pgvector + ParadeDB | 部分（融合需自写） | 低 | 需 zhparser/chinese_compatible 分词 | 想统一到 Postgres 时可选 |
| Redis Stack | 部分 | 低 | 一般 | 若已用 Redis 做缓存，可合并组件 |
| Milvus | ✅ | 高（etcd + minio） | 一般 | 单机场景过重 |
| faiss（纯内存） | ❌ 需手写 | 极低 | 需自建 | 仅适合极小语料 |

**决策规则**（在报告中写清，体现工程判断而不是拍脑袋）：

| 条件 | 选择 |
|---|---|
| 语料 < 500 万块、单机部署、追求低延迟与少运维 | **Qdrant** |
| 需要成熟的中文分词/同义词/分析器控制，或企业内已有 ES 运维能力 | OpenSearch |
| 已强依赖 Postgres 且希望单一存储、接受手写融合逻辑 | pgvector + ParadeDB |

Qdrant 的 footprint 对本机（Docker Desktop + 16GB 内存）尤其关键：跑得动 OpenSearch，但会挤占 embedding 与 rerank 的内存预算；而 Qdrant 单节点只占几百 MB。这正是"用本机约束反推选型"的量化论据。

**融合算法**：主选 RRF（对分数尺度不敏感，无需调权重，天然适配稠密+稀疏异构分数），备选加权归一化融合。两者可作为对比实验的一个自变量附加在报告中。

### 2.6 重排器

重排是 Context Precision 提升的主力，也是延迟预算的最大威胁。

| 候选 | 参数量 | 中文 | CPU 可用性 | 结论 |
|---|---|---|---|---|
| bge-reranker-v2-m3 | 568M | 强 | 勉强（需 int8 + 限制候选数） | 有 GPU/预算时首选 |
| bge-reranker-base | 278M | 中英可用 | 好 | **本机主选** |
| jina-reranker-v2-base-multilingual | 278M | 强 | 好 | **本机主选（并列）** |
| Cohere / Jina Rerank API | — | 强 | 无需本地算力，延迟低 | 允许数据出网时的备选 |
| 直接用生成模型打分 | — | 强 | 延迟极高 | 不选 |

**延迟防护三件套**（对应 C1）：

1. 候选数上限 15–20（重排延迟与候选数近似线性）。
2. 硬超时 800ms，超时直接回退到融合结果，日志记录 `rerank_timeout=true`。
3. 批量推理 + ONNX int8；重排分数写入日志，便于量化其增益。

**权衡必须写进报告**：重排提升 Context Precision，但抬高 P90。最终结论应表述为"在 X 候选数、Y 超时下，Context Precision 提升 Z 个百分点，P90 增加 W 毫秒"。

### 2.7 生成模型

约束是三重（质量、成本、延迟）同时成立，且 §8 要求显式给出权衡。做法不是选一个"最好的模型"，而是**先跑同一评测集做三方对照，再给出结论**。

| 档位 | 角色 | 质量 | 单次成本 | 延迟 | 用途 |
|---|---|---|---|---|---|
| 小模型（mini 级） | 主用 | 中 | 低 | 低 | 简单事实型问答（可用路由分流） |
| 中模型 | 兜底 | 高 | 中 | 中 | 复杂/多跳/多轮问题 |
| 旗舰模型 | 离线 judge | 最高 | 高 | 高 | 评测打分，不参与线上链路 |
| 本地 7B 量化 | 降级预案 | 中低 | 极低 | **不达标** | 仅演示"数据不出内网"路径 |

**模型选型实验设计**（直接产出 §8 要求的证据）：

| 项目 | 设计 |
|---|---|
| 自变量 | 3–4 个候选模型（覆盖小/中/旗舰；国内网络建议纳入 Qwen/DeepSeek/GLM 一类，国外 OpenAI/Anthropic 一类） |
| 控制变量 | 同一评测集、同一 prompt 版本、同一 top_n、temperature=0、同一检索配置 |
| 因变量 | Answer Compliance、Faithfulness、Style、P90 延迟、每千次调用成本 |
| 产出 | 三方对照表 + 明确取舍结论（例如"质量差 6pp，但成本降 80%、P90 降 60%"） |
| 附加 | 查询路由实验：简单题走小模型、复杂题走中模型，报告混合成本与质量 |

**工程要求**：模型调用统一走 OpenAI 兼容接口抽象，模型 ID 写在配置里。这样"换模型版本"是改一行配置（满足 C3/NFR2），并且天然支持上面的对照实验。

### 2.8 编排框架

| 候选 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| 自研薄管道（约几百行） | 每阶段耗时/分数/重试完全可控，日志字段能一一对应 | 需要自己写重试与并发 | **主选** |
| LlamaIndex | 入库连接器与解析省事 | 抽象层会隐藏真实耗时归因 | 只用于入库 |
| LangChain | 生态大 | 版本迭代快、黑盒多，诊断能力受损 | 不选 |

理由是**诊断需求（§13、§35）与框架抽象天然冲突**：出现"合规率下降"时，必须能一眼定位是召回变差、重排排序变了，还是 prompt 组装变了。自研管道让日志字段与管线阶段一一对应，这是 NFR4 能落地的前提。

### 2.9 缓存

| 方案 | 命中率 | 风险 | 结论 |
|---|---|---|---|
| 精确匹配（Redis，query 归一化哈希） | 低 | 几乎无 | 必做，作基线 |
| 语义缓存（embedding 相似度 ≥0.95） | 高 | 相似但不同的问题被误命中 | **主选（叠加）** |
| 不缓存 | 0 | 延迟与成本压力大 | 不选 |

**缓存键必须包含**：归一化 query + `config_version` + prompt 版本 + KB 版本 + 模型 ID。漏掉任何一项都会导致切换配置或更新文档后返回陈旧答案 —— 这正是"合规率下降"诊断剧本的候选来源，也是缓存正确率指标必须存在的原因。

### 2.10 可观测性

| 候选 | 用途 | 结论 |
|---|---|---|
| structlog → JSONL 文件 | 结构化日志，直接支撑运维报告统计 | **主选** |
| OpenTelemetry span | 阶段耗时与全链路追踪 | **主选** |
| Langfuse（自托管） | LLM 调用级追踪、prompt 版本对比 | 可选增强 |
| Prometheus + Grafana | 实时监控面板 | 案例场景下偏重，可略 |

本案例的运维报告只需从 JSONL 聚合（p50/p95、token、命中率、拒答率、合规率），无需引入完整监控栈；额外引入的组件都要在报告中解释其必要性，否则徒增复杂度。

### 2.11 评测实现

| 候选 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| 自研指标脚本 + LLM judge | 完全掌控指标定义，与报告口径一致 | 需自行实现与校验 | **主选** |
| RAGAS | 开箱即用 | 其 faithfulness / context precision 定义与本文档口径存在差异，"define your evaluation method" 会被弱化 | 交叉校验 |

**推荐组合**：自研脚本作为主口径，在同一样本子集上用 RAGAS 跑第二遍，报告两者一致率。这既证明方法自洽，又展示了对评测方法本身的不确定性有认知。

### 2.12 安全

| 层次 | 方案 | 衡量指标 |
|---|---|---|
| 输入侧规则 | 长度/格式限制 + 注入特征正则（"忽略以上指令"、索要系统提示、分隔符注入等） | 拦截率 |
| 输入侧分类器 | `protectai/deberta-v3-base-prompt-injection-v2`（184M，CPU 可跑） | 与规则互补的召回增益 |
| 上下文侧 | Spotlighting：检索内容用明确分隔与"以下为不可信数据"标注包裹 | 注入成功率 |
| 输出侧 | 断言级接地校验（与 Faithfulness 复用同一套 judge） | 无据回答率 |
| PII | Presidio（英文）+ 中文正则（身份证/手机号/银行卡/邮箱）+ 内部标识符 | 脱敏漏检率 |

**必须同时报告两个方向**：攻击拦截率（漏防）与正常问题误拦截率（误伤）。只报前者会诱导过度拦截，而过度拦截恰好是"拒答率飙升"诊断剧本的成因。

## 3. 成本模型

§8 要求"每 1000 次调用的 token 成本估算"，因此成本必须可计算、可复算，不能给一个孤立的数字。

**公式**：

```
CostPer1k = 1000 × ( avg_prompt_tokens × P_in / 1e6 + avg_completion_tokens × P_out / 1e6 )
```

**token 画像假设**（需用真实日志校准，报告中须写明）：prompt 约 2,500 token（system + 5 个证据块 + 历史 + 问题），completion 约 250 token。

**示例计算**（价格仅作演示，**落地前必须以官方当期价校准并标注取价日期**）：

| 档位 | 示例单价（输入/输出，每 1M token） | 单次成本 | 每 1000 次调用 |
|---|---|---|---|
| 小模型 | $0.15 / $0.60 | 2500×0.15 + 250×0.60 = 525 单位 → $0.000525 | **$0.53** |
| 中模型 | $0.50 / $1.50 | 1250 + 375 = 1625 单位 → $0.001625 | **$1.63** |
| 旗舰模型 | $2.50 / $10.00 | 6250 + 2500 = 8750 单位 → $0.00875 | **$8.75** |
| 路由混合（60% 小 / 40% 中） | 同上 | — | **$0.97** |

**其他成本项**（必须一并列出，否则估算不完整）：

| 项 | 量级 | 说明 |
|---|---|---|
| Embedding | 约 $0.05 / 千次（外部 API）或 $0（本地） | 本地 bge-m3 直接归零，是选本地方案的经济性论据之一 |
| 重排 | 本地 $0；API 约 $2 / 千次检索 | 本地方案的边际成本为零 |
| 缓存节省 | 按命中率线性抵扣 | 30% 命中率即成本降 30%，需在报告中体现 |
| 评测（judge）成本 | 离线，按样本量计 | 必须与线上成本分开统计，避免混淆 |

**降本手段与量化效果**：top_n 从 10 降到 5（prompt 减半）、缓存命中、查询路由、`max_output_tokens` 硬限制。每一项都要在报告中给出"降本 X%、质量变化 Y"的数据。

## 4. 被排除的方案与理由

| 方案 | 排除理由 |
|---|---|
| 本地 7B 模型做生成 | 本机无 GPU、16GB 内存、需 5 并发下 P90 ≤ 10s，量级不匹配；仅保留为数据不出网的降级预案 |
| Milvus | 单机需 etcd + MinIO，运维成本远超收益；需求只要求单实例 |
| 纯 faiss 内存索引 | 无持久化、无过滤、无原生 hybrid，增量更新与缓存失效难处理 |
| 单语 embedding 模型 | 不满足 CN/EN 双语与跨语言检索 |
| 重型 LangChain 链 | 隐藏阶段耗时，直接损害问题诊断能力 |
| 用同一模型既生成又评判 | 自评偏差，指标不可信；必须模型分离 + 人工抽检 |
| 微调模型 | 无标注数据、无 GPU、时间成本高，且对本任务收益不成比例 |
| Tesseract OCR | 中文与表格版面质量不足，会直接压制检索上限 |

## 5. 风险与切换条件

| 风险 | 触发条件 | 切换动作 |
|---|---|---|
| CPU 上 embedding 太慢 | 单条 query 编码 > 300ms | 换小模型或改 API embedding |
| 本地重排超时频繁 | `rerank_timeout` 比例 > 10% | 降候选数 / 换更小模型 / 改 API 重排 |
| Qdrant 召回与融合不达预期 | Context Precision < 0.70 | 切 OpenSearch，用其分析器与 RRF |
| 单机内存不足 | Docker 总占用 > 12GB | 削减 OpenSearch 类组件、限制 batch、用 int8 |
| API 网络不可达 | 请求失败率上升 | 切换到国内可直连的 OpenAI 兼容服务，或启用本地降级链路 |
| 语义缓存误命中 | 缓存命中请求的 judge 分数显著低于未命中 | 提高相似度阈值 / 加实体一致性校验 |

## 6. 与需求条款的对应

| 需求条款 | 本选型如何满足 |
|---|---|
| §6 延迟与并发 | 本地 embedding/rerank + API 生成；重排超时降级；缓存兜底；k6 压测出证据 |
| §8 成本与选型论证 | 统一成本公式 + 三方模型对照实验 + 路由混合成本 |
| §10 Faithfulness / Context Precision | 父子块切分 + bge-m3 hybrid + 可配置重排 + 标注评测集 |
| §11 / §33 生成质量 | 合规检查表 + 三维风格评分 + 双向拒答指标 + judge 分离 |
| §13 结构化日志 | structlog JSONL + OTel span + 字段字典 |
| §15 安全 | 规则+分类器双层注入检测 + Spotlighting + 输出接地校验 + PII 双路脱敏 |
| §20 检索模式与重排开关 | YAML 配置驱动，Qdrant 原生 hybrid，重排开关零代码切换 |
| §22 拒答 | 三类触发条件分别判定，输出带引导 |
| §24 PII | 输出与日志双路脱敏，缓存键同样不落明文 |
| §26 运维报告 | 从 JSONL 聚合出全部六个强制字段 |
| §29 三配置对比 | 同代码路径 + 配置切换，保证实验可比 |
| §31 可演进 | OpenAI 兼容抽象 + 接口化检索层 + 配置版本化 |
| §35 问题诊断 | 每阶段独立埋点，配置快照入库，前后对比可复现 |

## 7. 落地前必须做的三件事

1. `uv python install 3.12` + 建立项目虚拟环境（当前系统 Python 3.8.2 不足以支撑上述依赖）。
2. `docker compose up` 起 Qdrant + Redis，先跑通"入库 → 检索 → 生成"最小链路，并实测 embedding 与 rerank 的单次耗时 —— 这是后续所有延迟预算的真实基线。
3. 用真实耗时与真实价格替换本文档中所有"示例/估算"数值，标注取价日期与测量环境，形成最终的选型论证章节。

> 提醒：本文档中的价格为示例值、耗时为量级估计。交付物要求"clear, quantitative evidence"，因此**每一处估算都必须在实现阶段替换为实测数据**，否则该处论证不成立。
