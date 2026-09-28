# 目标架构与实施路线
> English version: [ARCHITECTURE-AND-ROADMAP.en.md](ARCHITECTURE-AND-ROADMAP.en.md)


## 一、整体架构

```
                    ┌─────────────────────────────────────────────┐
                    │  Ingestion（离线，一次性 + 增量）             │
                    │  PDF/Word/HTML → 解析 → OCR（扫描件）→ 清洗   │
                    │  → 语言识别 → 分块（中英分别策略）→ 元数据     │
                    │  → Embedding → 向量库 + 倒排索引(BM25)        │
                    └─────────────────────────────────────────────┘

   Client ──► API 网关 ──► 会话管理（多轮上下文）
                                │
                                ▼
                        查询改写（指代消解 / 省略补全）
                                │
                                ▼
                          缓存查询（精确 / 语义）
                                │ miss
                                ▼
              ┌──────── 检索层（配置驱动）────────┐
              │  vector-only  或  hybrid           │
              │  向量检索 ∥ BM25 → 融合（RRF）     │
              └──────────────┬────────────────────┘
                             ▼
                   重排器（可配置开关）
                             ▼
              ┌──────── 护栏层 ────────┐
              │ 注入检测 / 越界判定 /   │
              │ 低置信度判定 / 范围检查 │
              └───────────┬────────────┘
                          ▼
                 Prompt 组装（含引用编号）
                          ▼
                    生成（模型可配）
                          ▼
              ┌──────── 后处理层 ────────┐
              │ 引用校验 / 无据则拒答 /   │
              │ PII 脱敏（输出与日志）    │
              └───────────┬─────────────┘
                          ▼
                       响应 + 结构化日志

   ┌──────────────────────────────────────────────────────────┐
   │  Observability：trace/span、配置快照、token、指标聚合      │
   └──────────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────┐
   │  Eval Harness：数据集 → 多配置跑批 → Judge → 指标 → 报告   │
   └──────────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────┐
   │  Ops Report：p50/p95、token、缓存命中率、拒答率、合规率    │
   └──────────────────────────────────────────────────────────┘
```

分层原则（对应 NFR2 可演进性）：检索、重排、融合、生成、判定、评测全部通过接口 + 配置解耦，替换实现不改调用方。

## 二、配置模型（对应 FR1"不改代码即可切换"）

单一 YAML 配置文件驱动，配置版本号随每次请求写入日志。

```yaml
app:
  config_version: v1
  prompt_version: p1

retrieval:
  mode: hybrid            # vector | hybrid
  top_k: 20
  fusion: rrf             # rrf | weighted
  vector_weight: 0.6
  bm25:
    tokenizer: zh_en      # 中文分词 + 英文词干化
  vector:
    collection: kb_v1

rerank:
  enabled: true           # 纯配置开关
  model: bge-reranker-v2-m3
  top_n: 5
  timeout_ms: 800         # 超时降级：直接用融合结果

generation:
  model: <provider/model-id>
  temperature: 0
  max_output_tokens: 600
  require_citation: true

guardrails:
  injection_detection: true
  scope_check: true
  min_retrieval_score: 0.35
  min_support_score: 0.6
  pii:
    redact_output: true
    redact_logs: true

cache:
  enabled: true
  mode: semantic          # exact | semantic
  similarity_threshold: 0.95
  ttl_seconds: 86400
  invalidate_on_reindex: true

observability:
  log_format: json
  sample_rate: 1.0
  log_redaction: hash     # hash | placeholder | drop
```

三种评测配置就是同一份文件的三份变体：

| 配置 | retrieval.mode | rerank.enabled |
|---|---|---|
| C1 vector-only | vector | false |
| C2 hybrid | hybrid | false |
| C3 hybrid+rerank | hybrid | true |

## 三、日志字段字典（交付物要求）

每条日志一行 JSON，`trace_id` 贯穿全链路。示例见本节末尾。

| 字段 | 类型 | 说明 |
|---|---|---|
| ts | string (ISO8601) | 事件时间 |
| trace_id | string | 全链路追踪 id |
| request_id | string | 单次 HTTP 请求 id |
| session_id | string | 会话 id（多轮） |
| turn_index | int | 轮次序号 |
| stage | enum | rewrite / retrieve / rerank / guardrail / generate / postprocess / total |
| latency_ms | number | 该阶段耗时 |
| config_version | string | 配置版本快照 |
| prompt_version | string | Prompt 版本 |
| retrieval_mode | enum | vector / hybrid |
| rerank_enabled | bool | 是否启用重排 |
| top_k | int | 召回数量 |
| top_n | int | 送入生成的数量 |
| retrieved_chunk_ids | string[] | 命中的 chunk id |
| retrieval_scores | number[] | 相似度/融合分数 |
| rerank_scores | number[] | 重排分数 |
| cache_hit | bool | 是否命中缓存 |
| cache_key_hash | string | 缓存键哈希（不落原文） |
| prompt_tokens | int | 输入 token |
| completion_tokens | int | 输出 token |
| total_tokens | int | 合计 token |
| cost_usd | number | 本次请求估算成本 |
| model_id | string | 生成模型版本 |
| answer_status | enum | answered / refused / error |
| refusal_reason | enum | low_confidence / out_of_scope / safety / no_evidence |
| citation_ids | string[] | 答案引用的证据 id |
| support_score | number | 答案证据支撑度 |
| injection_flags | string[] | 命中的注入特征 |
| pii_redacted_fields | string[] | 被脱敏的字段（如 user_query、answer） |
| judge_scores | object | 离线评测时的各项打分 |
| error_type | string | 异常类型（可为空） |

样例日志：

```json
{
  "ts": "2026-09-18T12:00:01.234+08:00",
  "trace_id": "tr_9f3c1a",
  "request_id": "req_88213",
  "session_id": "sess_4410",
  "turn_index": 2,
  "stage": "total",
  "latency_ms": 3120,
  "config_version": "v1",
  "prompt_version": "p1",
  "retrieval_mode": "hybrid",
  "rerank_enabled": true,
  "top_k": 20,
  "top_n": 5,
  "retrieved_chunk_ids": ["doc12#3", "doc07#1", "doc33#5"],
  "retrieval_scores": [0.83, 0.79, 0.71],
  "rerank_scores": [0.94, 0.88, 0.63],
  "cache_hit": false,
  "prompt_tokens": 1840,
  "completion_tokens": 210,
  "total_tokens": 2050,
  "cost_usd": 0.0021,
  "model_id": "gpt-4o-mini-2024-07-18",
  "answer_status": "answered",
  "refusal_reason": null,
  "citation_ids": ["doc12#3", "doc07#1"],
  "support_score": 0.91,
  "injection_flags": [],
  "pii_redacted_fields": ["user_query"],
  "error_type": null
}
```

## 四、三配置对比实验设计（NFR1）

| 项目 | 设计 |
|---|---|
| 自变量 | 仅检索配置（C1/C2/C3） |
| 控制变量 | 评测集、prompt 版本、生成模型、top_n、温度、随机种子 |
| 因变量 | Context Precision、Faithfulness、Compliance、Style、Refusal 双向指标、P50/P90/P95、token 成本、缓存命中率 |
| 样本 | 全量评测集（含单轮、多轮、越界、不安全子集） |
| 产出 | 对比表 + 结论（哪种配置在什么场景更优，为什么） |
| 注意 | 重排会提升精度但增加延迟，结论必须显式体现这一权衡 |

预期结论方向（待数据验证，不可直接照抄）：hybrid 提升召回但可能引入词法噪声，rerank 修复排序从而抬升 Context Precision，代价是 P90 上升；若 P90 触线，需要超时降级或缓存兜底。

## 五、问题诊断剧本（NFR4，至少 2 个）

需求要求"至少 2 个问题 + 日志证据 + 修复理由 + 修复后提升 ≥ 10%"。以下为候选，实际执行时**如实记录真实数据**。

| 候选 | 现象 | 日志证据 | 修复方向 | 提升衡量 |
|---|---|---|---|---|
| A：hybrid 引入噪声 | 切到 hybrid 后 Context Precision 下降 | retrieval_scores 分布右移但 rerank_scores 低位、citation 命中率下降 | 中文分词修正 + RRF 权重调整 + 分数阈值 | Context Precision 提升 ≥ 10% |
| B：拒答率异常升高 | 上线注入过滤后 refusal_rate 从 8% 升到 30% | refusal_reason=safety 占比突增、injection_flags 误命中正常问句 | 收紧正则/改为分类器判定 + 增加白名单 | 正确应答率提升 ≥ 10% |
| C：缓存陈旧答案 | 文档更新后 compliance 下降 | cache_hit=true 的请求 judge 分数显著低于 miss 请求 | 重新索引触发缓存失效 + 缩短 TTL | Compliance 提升 ≥ 10% |
| D：重排导致 P90 超线 | P90 从 7.2s 升至 11.5s | rerank 阶段 span 耗时 p95 > 3s | 超时降级 + 批量重排 + 缓存 | P90 回到 < 10s |

每份诊断报告须包含：现象 → 时间窗 → 日志/指标证据 → 根因分析 → 修复方案与理由 → 修复前后对比数据 → 结论。

## 六、里程碑与验收标准

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| M0 | 评测数据集 + 日志/指标骨架 | 数据集规模达标；日志字段字典成型；样例日志可产出 |
| M1 | vector-only 基线 | 端到端可问答；每请求可打点；基线指标可跑出 |
| M2 | hybrid + 配置化重排 | 改 YAML 即可切换三种配置，无需改代码 |
| M3 | 拒答 / 安全 / PII | 三类拒答触发均生效且带引导；输出与日志双路脱敏 |
| M4 | 一键评测 + 三配置报告 | 单命令产出对比报告与结论 |
| M5 | 缓存 + 运维报告 | txt/CSV 报告含全部强制字段 |
| M6 | 2 处问题诊断 + 前后对比 | 每处均有日志证据与 ≥ 10% 提升数据 |
| M7 | 文档收口 | 代码与配置完整可运行；日志字典与样例齐备 |

## 七、工程约束提醒

- **重排器超时必须降级**：不能让外部重排服务拖垮 10s 预算。
- **检索并行**：向量与 BM25 必须并行发起。
- **配置快照**：每次请求记录生效配置，否则前后对比与问题诊断全部失效。
- **脱敏位置要前置**：查询中的 PII 在进入日志与缓存前就应处理，缓存键同样不能含明文 PII。
- **离线评测与在线服务共用同一检索/生成代码路径**，避免评测结果与线上行为不一致。
