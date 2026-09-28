# 日志字段字典与样例日志

> 本文件由 `scripts/gen_log_docs.py` 从代码常量与真实日志生成，请勿手工编辑。
> English version: [LOG-FIELD-DICTIONARY.en.md](LOG-FIELD-DICTIONARY.en.md)

## 1. 字段字典

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | string | 事件时间（ISO8601，本地时区） |
| `level` | string | 日志级别 |
| `event` | string | 事件名：span 或 request |
| `trace_id` | string | 全链路追踪 id |
| `request_id` | string | 单次请求 id |
| `session_id` | string | 会话 id（多轮） |
| `turn_index` | int | 会话轮次序号 |
| `stage` | enum | rewrite/retrieve/rerank/guardrail/generate/postprocess/cache/total |
| `latency_ms` | number | 该阶段耗时（毫秒） |
| `config_version` | string | 配置版本 |
| `config_fingerprint` | string | 配置指纹（内容哈希） |
| `prompt_version` | string | Prompt 版本 |
| `corpus_version` | string | 知识库版本 |
| `retrieval_mode` | enum | vector | hybrid |
| `rerank_enabled` | bool | 是否启用重排 |
| `top_k` | int | 召回数量 |
| `top_n` | int | 送入生成的证据数量 |
| `retrieved_chunk_ids` | string[] | 召回命中的 chunk id |
| `retrieval_scores` | number[] | 融合后的最终分数 |
| `vector_scores` | number[] | 向量通道分数 |
| `lexical_scores` | number[] | 词法通道分数 |
| `rerank_scores` | number[] | 重排分数 |
| `rerank_timeout` | bool | 重排是否超时降级 |
| `cache_hit` | bool | 是否命中缓存 |
| `cache_key_hash` | string | 缓存键哈希（不落原文） |
| `prompt_tokens` | int | 输入 token 数 |
| `completion_tokens` | int | 输出 token 数 |
| `total_tokens` | int | token 总数 |
| `cost_usd` | number | 本次请求估算成本（美元） |
| `model_id` | string | 生成模型标识 |
| `answer_status` | enum | answered | refused | error |
| `refusal_reason` | enum | low_confidence | out_of_scope | safety | no_evidence |
| `citation_ids` | string[] | 答案引用的证据 chunk id |
| `support_score` | number | 答案被证据支撑的程度 |
| `injection_flags` | string[] | 命中的 prompt 注入特征 |
| `pii_redacted_fields` | string[] | 被脱敏的字段 |
| `user_query` | string | 用户问题（按配置脱敏） |
| `error_type` | string | 异常类型 |

## 2. 日志结构

每次请求产生两类记录：

- `event=span`：单个阶段的埋点（rewrite / cache / retrieve / guardrail / generate / postprocess），
  每条都带 `trace_id` 与 `stage`，用于定位耗时与阶段行为。
- `event=request`：一次请求的汇总记录，运维报告的全部指标都来自这类记录。

## 3. 样例日志

```json
{"stage": "retrieve", "top_n": 5, "retrieved_chunk_ids": ["DOC-HB-02#P000C00", "DOC-CP-S02#P000C00", "DOC-CP-S08#P000C00", "DOC-AR-S06#P000C00", "DOC-HB-S02#P000C00"], "retrieval_scores": [0.4, 0.4, 0.4, 0.3, 0.3], "vector_scores": [0.213142, 0.087873, 0.086476, 0.167598, 0.154395], "lexical_scores": [5.185673, 5.301338, 5.255802, 2.560568, 2.461234], "rerank_scores": [0.4, 0.4, 0.4, 0.3, 0.3], "rerank_timeout": false, "latency_ms": 2.02, "trace_id": "tr_b385fa45917d", "request_id": "req_4175918", "retrieval_mode": "hybrid", "rerank_enabled": true, "top_k": 20, "event": "span", "level": "info", "ts": "2026-09-25T21:49:35.921293"}
{"stage": "guardrail", "injection_flags": [], "scope_coverage": 0.25, "scope_oov": 0.75, "scope_oov_unigram": 0.75, "scope_out_of_scope": true, "latency_ms": 0.17, "trace_id": "tr_b385fa45917d", "request_id": "req_4175918", "event": "span", "level": "info", "ts": "2026-09-25T21:49:35.921621"}
{"stage": "generate", "latency_ms": 0.0, "trace_id": "tr_b385fa45917d", "request_id": "req_4175918", "stage_detail": "refused", "event": "span", "level": "info", "ts": "2026-09-25T21:49:35.921752"}
{"stage": "postprocess", "support_score": 0.0, "grounded": false, "answer_status": "refused", "latency_ms": 1.56, "trace_id": "tr_b385fa45917d", "request_id": "req_4175918", "event": "span", "level": "info", "ts": "2026-09-25T21:49:35.923422"}
{"trace_id": "tr_f24ab8c1981b", "request_id": "req_4175913", "session_id": "eval_low_confidence_10_zh", "turn_index": 1, "stage": "total", "latency_ms": 4.51, "config_version": "exp_scope_fixed", "config_fingerprint": "789efef73a53", "prompt_version": "p1", "corpus_version": "kb_v1", "retrieval_mode": "hybrid", "rerank_enabled": true, "top_k": 20, "top_n": 5, "retrieved_chunk_ids": ["DOC-HB-01#P000C00", "DOC-CP-S02#P000C00", "DOC-CP-S08#P000C00", "DOC-HB-S04#P000C00", "DOC-HB-S02#P000C00"], "retrieval_scores": [0.163636, 0.1, 0.1, 0.1, 0.1], "rerank_scores": [0.163636, 0.1, 0.1, 0.1, 0.1], "rerank_timeout": false, "cache_hit": false, "cache_key_hash": "ec9454ad60ef183d6a7afd6b", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "model_id": "offline-extractive", "answer_status": "refused", "refusal_reason": "out_of_scope", "citation_ids": [], "support_score": 0.0, "injection_flags": [], "pii_redacted_fields": [], "user_query": "年度调薪的幅度区间是多少？", "error_type": null, "event": "request", "level": "info", "ts": "2026-09-25T21:49:35.918654"}
{"trace_id": "tr_b385fa45917d", "request_id": "req_4175918", "session_id": "eval_low_confidence_10_en", "turn_index": 1, "stage": "total", "latency_ms": 4.55, "config_version": "exp_scope_fixed", "config_fingerprint": "789efef73a53", "prompt_version": "p1", "corpus_version": "kb_v1", "retrieval_mode": "hybrid", "rerank_enabled": true, "top_k": 20, "top_n": 5, "retrieved_chunk_ids": ["DOC-HB-02#P000C00", "DOC-CP-S02#P000C00", "DOC-CP-S08#P000C00", "DOC-AR-S06#P000C00", "DOC-HB-S02#P000C00"], "retrieval_scores": [0.4, 0.4, 0.4, 0.3, 0.3], "rerank_scores": [0.4, 0.4, 0.4, 0.3, 0.3], "rerank_timeout": false, "cache_hit": false, "cache_key_hash": "48abefa32f8eacfcdcfab588", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "model_id": "offline-extractive", "answer_status": "refused", "refusal_reason": "out_of_scope", "citation_ids": [], "support_score": 0.0, "injection_flags": [], "pii_redacted_fields": [], "user_query": "What is the annual salary increase range?", "error_type": null, "event": "request", "level": "info", "ts": "2026-09-25T21:49:35.923735"}
```

日志总行数：196606；请求数：30534。

## 4. 脱敏说明

`user_query` 与答案在落盘前经过 PII 脱敏（邮箱、手机号、身份证、银行卡、工号、内部编码），
命中记录写入 `pii_redacted_fields`。默认使用哈希模式，保留可追踪性而不落明文。
