# 评测报告

> 由 `scripts/gen_eval_report.py --report-dir reports/llm` 从真实产物生成。
> English version: [EVALUATION-REPORT.en.md](EVALUATION-REPORT.en.md)

## 1. 结论摘要

- **检索最优配置**：`llm_c3_hybrid_rerank`，Context Precision@5 0.8437、Recall@5 0.9062、MRR 0.8472
- **合规最优配置**：`llm_c1_vector`，Answer Compliance 0.7824。**注意两者不是同一配置**（见第 4 节说明）
- **延迟**：检索最优配置 P90 2.42s、P95 2.69s（阈值 10s）
- **成本**：每千次调用约 $0.2682（使用配置中的示例单价，需按官方当期价替换）
- **相对基线**：Context Precision@5 从 0.6738 提升到 0.8437（+17.0 个百分点）

## 2. 评测方法

| 项目 | 说明 |
|---|---|
| 语料 | 自建中英双语语料，覆盖员工手册/合规指南/技术规范/架构文档，含 2 份纯图片扫描件 |
| OCR | RapidOCR，扫描件按 300 DPI 渲染；实测置信度约 0.98 |
| 切分 | 结构化递归切分 + 父子块（子块 320 token，父块 1300 token） |
| 向量 | ONNX 多语言模型（MiniLM-L12 int8，384 维，无需 PyTorch） |
| 重排 | bge-reranker-base（ONNX int8 交叉编码器），10 候选 / 800ms 超时降级 |
| 生成 | OpenAI 兼容接口（本次评测使用 DeepSeek） |
| 评判 | LLM judge，按批送评并在失败时二分重试；拒答项由客观状态判定 |
| 标注 | 事实条目自带唯一锚点，切分后反查生成 gold chunk，支持跨语言锚点回退 |
| 缓存 | 评测时关闭：缓存命中会跳过检索，掩盖真实检索质量 |
| 多轮改写 | 仅在问题依赖上下文时触发（指代词 / 无主题追问） |

### 数据集规模

```json
{
  "single_turn_items": 64,
  "multi_turn_conversations": 20,
  "multi_turn_turns": 80,
  "negatives": 72,
  "total_scored_units": 216,
  "zh_items": 78,
  "en_items": 78
}
```

## 3. 三配置对比

| 指标 | llm_c1_vector | llm_c2_hybrid | llm_c3_hybrid_rerank |
|---|---|---|---|
| Context Precision@5 | 0.6738 | 0.6782 | 0.8437 |
| Recall@5 | 0.8681 | 0.8160 | 0.9062 |
| MRR | 0.6817 | 0.6843 | 0.8472 |
| Faithfulness | 0.9984 | 1.0000 | 1.0000 |
| Answer Compliance | 0.7824 | 0.7361 | 0.7500 |
| Style Consistency | 0.8852 | 0.8827 | 0.8766 |
| Refusal Appropriateness | 0.9381 | 0.9094 | 0.9211 |
| P90 (ms) | 1556.7200 | 1713.9700 | 2419.0400 |
| 成本/千次 (USD) | 0.2806 | 0.2661 | 0.2682 |

## 4. 达标情况（对照需求阈值）

| 指标 | 及格线 | 进阶线 | 实测（检索最优配置） | 结论 |
|---|---|---|---|---|
| Faithfulness | ≥ 0.85 | — | 1.0000 | 达成 |
| Context Precision@5 | ≥ 0.7 | — | 0.8437 | 达成 |
| Answer Compliance | ≥ 0.8 | ≥ 0.9 | 0.7500 | 未达成（达目标的 93.8%） |
| Style Consistency | ≥ 0.8 | ≥ 0.85 | 0.8766 | 达成（含进阶线） |
| Refusal Appropriateness | ≥ 0.8 | ≥ 0.9 | 0.9211 | 达成（含进阶线） |
| P90 端到端延迟 | ≤ 10 s | — | 2.42 s | 达成 |
| 单实例并发 | ≥ 5 | — | 5 并发 / 50 请求 / 0 错误，P90 4175.83 ms | 达成 |

> 检索最优与合规最优可能不是同一配置：检索更强会让模型尝试作答更多问题，
> 其中一部分未通过严格的合规细则；而检索较弱的配置更常拒答，反而「少答少错」。
> 两项指标需要联合权衡，不能只看检索。

## 5. 问题诊断与前后对比

受控实验（每次只改变一个变量，均给出修复前后数据）见 `reports/diagnosis_report.md`，摘要：

| 问题 | 修复前 | 修复后 | 提升 |
|---|---|---|---|
| 切分粒度过小（120 → 320 token） | Recall@5 低 | 见诊断报告 | ≥ 10% |
| 越界阈值过严 | 正确应答率低、拒答适当性低 | 见诊断报告 | ≥ 10% |

本轮真实模型评测中还定位并修复了以下缺陷（详见 `reports/llm/ACCEPTANCE-CHECK-LLM.md`）：

| 缺陷 | 现象 | 修复 |
|---|---|---|
| 多轮标注缺少跨语言回退 | 英文题目 gold 为空，检索命中却判 0 分 | 与单轮一致地回退到另一语言锚点 |
| 轮次门控误判 | 独立新话题问题被当成追问并替换，答错话题 | 只按指代词与无主题追问判定 |
| 改写方式为拼接 | 产出畸形复合问句，合规率低 | LLM 会话式改写（含严格重试与确定性兜底） |
| 生成输入选择错误 | 追问不携带话题时模型答非所问 | A/B 实测确认生成使用改写后的问句 |

## 6. 局限与改进路径

| 局限 | 影响 | 改进路径 |
|---|---|---|
| 合规率略低于目标 | 未合规项中约半数为「该答却拒答」 | 放宽 grounding 阈值、在提示词中强化引用格式 |
| 成本使用示例单价 | 成本结论失真 | 替换为模型官方当期价并重算 |
| 向量为轻量 int8 模型 | 检索上限受限 | 换 bge-m3 后重新入库 |
| 语料自建、扫描件为渲染 | 与真实分布有差异 | 用真实文档与扫描件复测 |
| 重排仍存在超时降级 | 部分请求未使用重排结果 | 降低候选数或增加 CPU 预算 |

## 7. 运维报告

```
运维报告 (Minimal Operations Report)
配置版本: llm_c3_hybrid_rerank

请求总数: 1890
P50 延迟: 1397.33 ms
P90 延迟: 2185.29 ms
P95 延迟: 2571.38 ms
最大延迟: 11051.91 ms
Token 用量: prompt=1666297 completion=140274 total=1806571
平均 Token: prompt=881.6 completion=74.2
每千次调用成本: 0.1768 USD
缓存命中率: 0.1169
拒答率: 0.482（未作答占比，按原因细分见下）
拒答原因分布: {"low_confidence": 198, "out_of_scope": 471, "safety": 161, "no_evidence": 81}
作答率: 0.518
平均接地分数: 0.6559
答案合规率(在线代理): 0.7293
重排超时率: 0.1778
```

## 8. 复现步骤

```bash
uv sync --extra ocr && uv add tokenizers huggingface_hub
# 1. 入库（语料 → OCR → 切分 → ONNX 向量化）
uv run python scripts/ingest.py --config configs/llm_c3_hybrid_rerank.yaml --rebuild-corpus
# 2. 构建评测集
uv run python scripts/eval.py --rebuild-dataset --eval-dir data/eval_onnx
# 3. 三配置评测 + 对比报告
uv run python scripts/eval.py \
  --configs configs/llm_c1_vector.yaml configs/llm_c2_hybrid.yaml configs/llm_c3_hybrid_rerank.yaml \
  --eval-dir data/eval_onnx --report-dir reports/llm
# 4. 运维报告 / 压测 / 诊断
uv run python scripts/report.py --config-version llm_c3_hybrid_rerank
uv run python scripts/loadtest.py --concurrency 5 --requests 200
uv run python scripts/diagnose.py
# 5. 生成交付文档
uv run python scripts/gen_log_docs.py
uv run python scripts/gen_eval_report.py --report-dir reports/llm --out reports/EVALUATION-REPORT.md
```
