# 真实模型 API Key 配置指南
> English version: [API-KEY-SETUP.en.md](API-KEY-SETUP.en.md)


适用代码：`src/rag/generate/__init__.py`（OpenAI 兼容客户端）、`src/rag/config.py`（配置加载）

## 1. 三种注入方式（任选其一）

### 方式 A：`.env` 文件（推荐，国内模型用这种方式最省事）

```bash
cd /Users/mengling/source-code/rag_task
cp .env.example .env
# 编辑 .env，填入真实 key
```

```ini
# 三项一起配好，即可切换任意 OpenAI 兼容服务，无需改 YAML
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

HF_ENDPOINT=https://hf-mirror.com
```

程序启动时会自动加载 `.env`（`config.py` 中的 `load_dotenv(override=False)`），
**已存在的 shell 环境变量优先级更高，不会被 `.env` 覆盖**。`.env` 已在 `.gitignore` 中。

### 配置优先级

```
环境变量（含 .env）  >  configs/*.yaml  >  默认值
```

具体到三个字段：

| 环境变量 | 覆盖的配置项 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | （键名由 `api_key_env` 指定） | 只从环境变量读取，不写进 YAML |
| `OPENAI_BASE_URL` | `generation.base_url` | 覆盖服务地址，末尾斜杠会自动去掉 |
| `OPENAI_MODEL` | `generation.model` | 覆盖模型 id |

不想让环境变量覆盖时，把配置里的 `base_url_env` / `model_env` 设为 `null` 即可。
覆盖结果会体现在配置指纹（`config_fingerprint`）里，日志因此能区分
"同一份 YAML + 不同端点"的两次运行。

### 方式 B：shell 环境变量（推荐，CI / 临时验证）

```bash
export OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/openai_example.yaml
```

### 方式 C：容器环境变量

```yaml
# docker-compose 片段
services:
  rag:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}   # 从宿主机环境传入，不写死在文件里
      - OPENAI_BASE_URL=${OPENAI_BASE_URL}
      - OPENAI_MODEL=${OPENAI_MODEL}
```

## 2. YAML 配置项（`configs/openai_example.yaml`）

先给一个国内模型的最小可用示例：

```ini
# .env —— 只改这三行就能切到 DeepSeek
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

```bash
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/openai_example.yaml
```

`configs/openai_example.yaml` 里对应的字段如下（会被上面的环境变量覆盖）：

```yaml
generation:
  backend: openai
  model: gpt-4o-mini                  # ① 目标模型 id
  base_url: https://api.openai.com/v1 # ② 服务地址（国内兼容服务见第 3 节）
  api_key_env: OPENAI_API_KEY         # ③ 环境变量名，可与 .env 中的名字自定义
  base_url_env: OPENAI_BASE_URL        # 地址覆盖用的变量名，null 表示禁用
  model_env: OPENAI_MODEL              # 模型覆盖用的变量名，null 表示禁用
  max_tokens_field: max_tokens        # ④ 见下方说明
  temperature: 0
  timeout_seconds: 30
  fallback_to_offline: false          # ⑤ 评测时务必 false
  price_in_per_1m: 0.15               # ⑥ 必须替换为官方当期价（美元 / 1M token）
  price_out_per_1m: 0.60
  extra_body: {}                      # ⑦ 厂商特有字段，如 top_p、enable_search
```

| 编号 | 说明 |
|---|---|
| ① | 模型 id 必须与厂商文档完全一致，写错会返回 404 |
| ② | 必须以 `/v1` 结尾（客户端会拼接 `/chat/completions`） |
| ③ | 变量名可自定义，例如 `DEEPSEEK_API_KEY`，但配置文件与 `.env` 必须一致 |
| ④ | 多数服务用 `max_tokens`；**新版 OpenAI 推理模型只接受 `max_completion_tokens`**，用错会 400 |
| ⑤ | `false` 时调用失败直接抛错；`true` 时告警并降级到离线生成器（`model_id` 会变成 `offline-extractive`） |
| ⑥ | 成本报告直接依赖这两个价格，不填就会得出错误的每千次调用成本 |
| ⑦ | 用于填厂商特有参数，会被合并进请求体 |

> 若把 `api_key_env` 改成 `DEEPSEEK_API_KEY`，`.env` 里的变量名要同步改，
> 否则会报"环境变量未设置"。

## 3. 常见服务的 base_url

> 各厂商地址与模型 id 会变化，**使用前请以官方文档为准**；下表用于起步。

| 服务 | base_url | 说明 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | 需要外网可达 |
| DeepSeek | `https://api.deepseek.com/v1` | OpenAI 兼容 |
| 阿里云百炼（Qwen） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI 兼容模式 |
| 月之暗面（Kimi） | `https://api.moonshot.cn/v1` | OpenAI 兼容 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | 注意是 `v4` 不是 `v1` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | 聚合多家模型 |
| 本地 vLLM | `http://localhost:8000/v1` | key 随便填一个非空值 |
| 本地 Ollama | `http://localhost:11434/v1` | key 随便填一个非空值 |

本地服务示例（不校验 key，但程序要求非空）：

```yaml
generation:
  backend: openai
  model: qwen2.5:7b
  base_url: http://localhost:11434/v1
  api_key_env: OPENAI_API_KEY   # 值填 not-needed 即可
```

## 4. 配置是否生效：三步验证

```bash
# ① 确认进程能读到 key（不会打印 key 本身）
uv run python -c "import os; print('key 可见:', bool(os.environ.get('OPENAI_API_KEY')))"

# ② 问一次，看 model_id 与 token 是否来自真实服务
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/openai_example.yaml --json \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['model_id'], d['token_usage'], d['cost_usd'])"

# ③ 看日志里的生成阶段耗时（真实模型通常是数百毫秒到数秒，而不是几毫秒）
tail -5 logs/rag.jsonl | python -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    if r.get('stage') == 'generate':
        print('generate 阶段耗时:', r.get('latency_ms'), 'ms')
"
```

**判定标准**：`model_id` 等于你配置的模型 id，且 `generate` 阶段耗时明显大于检索耗时，
说明真实模型已被调用。若 `model_id` 显示 `offline-extractive`，说明发生了降级。

## 5. 常见错误对照

| 报错 | 原因 | 处理 |
|---|---|---|
| `环境变量 OPENAI_API_KEY 未设置` | key 未注入或变量名不一致 | 检查 `api_key_env` 与 `.env` / shell 变量名是否一致 |
| `LLM API 401 ... invalid api key` | key 错误、过期或与 base_url 不匹配 | 确认 key 属于该服务商 |
| `LLM API 404 ...` | base_url 或 model id 写错 | 检查 base_url 是否以 `/v1` 结尾、模型 id 是否与官方一致 |
| `LLM API 400 ... max_tokens` | 字段名不被支持 | 改为 `max_tokens_field: max_completion_tokens` |
| `LLM API 429` | 限流或额度耗尽 | 降低并发、增加重试，或检查账户余额 |
| `httpx.ConnectError` | 网络不可达（如本机无法直连 api.openai.com） | 换用可达的服务，或配置代理 |
| `响应结构异常` | 该服务不是 OpenAI 兼容协议 | 确认使用其"兼容模式"端点 |
| 成本为 0 | 服务未返回 `usage` | 代码会用本地估算兜底；仍为 0 说明请求没成功 |

## 6. 安全注意事项

1. **不要把 key 写进 YAML 或提交到仓库**。配置文件只放环境变量名，`.env` 已被 `.gitignore` 忽略。
2. 日志不会记录 key（`Authorization` 头不落盘），但会记录 `model_id`、token 与错误信息。
3. 服务端返回的错误原文会被截断保存到日志，便于排查；如错误信息可能含敏感内容，注意日志访问权限。
4. 评测时设置 `fallback_to_offline: false`：否则 key 配错会静默降级，把"配置错误"伪装成"模型效果差"。

## 7. 本机已完成的链路验证

由于当前环境无法访问 `api.openai.com` 且没有真实 Key，我用仓库内的模拟服务
`scripts/mock_llm_server.py` 验证了完整接入链路（它**不产生真实模型效果**，只验证管道）：

```bash
uv run python scripts/mock_llm_server.py --port 8123     # 终端 1
export OPENAI_API_KEY=mock-key-for-verification           # 终端 2
uv run python scripts/eval.py --configs configs/mock_local.yaml
```

验证结果：

| 场景 | 结果 |
|---|---|
| 正确 key | `model_id=mock-model`，token 取自 API 返回，成本 $0.00017655 与公式一致 |
| 未设置 key + `fallback_to_offline: false` | 报错并给出变量名与两种配置方式 |
| 错误 key + `fallback_to_offline: false` | `RuntimeError: LLM API 401 ... invalid api key`（不静默降级） |
| 错误 key + `fallback_to_offline: true` | 打印告警并降级，`model_id=offline-extractive` |
| `.env` 方式注入（无 shell 变量） | `model_id=mock-model`，证明 `.env` 已被自动加载 |
| `.env` 中设置 `OPENAI_BASE_URL` / `OPENAI_MODEL` | 覆盖 YAML 中的同名字段，`model_id` 与请求端点随之改变 |
| 全量评测（216 项） | 端到端跑通，成本 $0.1505/千次调用，P90 71 ms（模拟服务固定 50 ms 延迟） |

换成真实 Key 后，只需把 `configs/openai_example.yaml` 的 `base_url`、`model`、
`price_*` 三项改成实际值，再重跑评测即可。
