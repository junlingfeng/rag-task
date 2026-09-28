# Configuring a Real Model API Key

> Chinese version: [API-KEY-SETUP.md](API-KEY-SETUP.md)
> Applies to: `src/rag/generate/__init__.py` (OpenAI-compatible client), `src/rag/config.py` (config loading)

## 1. Three ways to inject the key (pick one)

### Option A: `.env` file (recommended; simplest for domestic providers)

```bash
cd /Users/mengling/source-code/rag_task
cp .env.example .env
# edit .env and fill in the real key
```

```ini
# All three together switch to any OpenAI-compatible service — no YAML changes needed
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

HF_ENDPOINT=https://hf-mirror.com
```

`.env` is loaded automatically at startup (`load_dotenv(override=False)` in `config.py`).
**Existing shell environment variables take precedence and are not overwritten by `.env`.**
`.env` is already listed in `.gitignore`.

### Configuration precedence

```
environment variables (including .env)  >  configs/*.yaml  >  defaults
```

For the three fields specifically:

| Environment variable | Overrides | Notes |
|---|---|---|
| `OPENAI_API_KEY` | (name given by `api_key_env`) | Read only from the environment, never stored in YAML |
| `OPENAI_BASE_URL` | `generation.base_url` | Overrides the endpoint; a trailing slash is stripped |
| `OPENAI_MODEL` | `generation.model` | Overrides the model id |

To disable environment overrides, set `base_url_env` / `model_env` to `null` in the configuration.
Overrides are reflected in the configuration fingerprint (`config_fingerprint`), so logs can
distinguish two runs of "same YAML, different endpoint".

### Option B: shell environment variables (recommended for CI / ad-hoc checks)

```bash
export OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/openai_example.yaml
```

### Option C: container environment variables

```yaml
# docker-compose fragment
services:
  rag:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}   # passed from the host, never hard-coded
      - OPENAI_BASE_URL=${OPENAI_BASE_URL}
      - OPENAI_MODEL=${OPENAI_MODEL}
```

## 2. YAML configuration (`configs/openai_example.yaml`)

Minimal working example for a domestic provider:

```ini
# .env — three lines are enough to switch to DeepSeek
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

```bash
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/openai_example.yaml
```

The corresponding fields in `configs/openai_example.yaml` (overridden by the environment above):

```yaml
generation:
  backend: openai
  model: gpt-4o-mini                  # (1) target model id
  base_url: https://api.openai.com/v1 # (2) endpoint (domestic services in section 3)
  api_key_env: OPENAI_API_KEY         # (3) variable name; may differ from the .env name
  base_url_env: OPENAI_BASE_URL       # variable used for the endpoint override; null disables
  model_env: OPENAI_MODEL             # variable used for the model override; null disables
  max_tokens_field: max_tokens        # (4) see below
  temperature: 0
  timeout_seconds: 30
  fallback_to_offline: false          # (5) keep false for evaluation
  price_in_per_1m: 0.15               # (6) replace with the current official price (USD / 1M tokens)
  price_out_per_1m: 0.60
  extra_body: {}                      # (7) provider-specific fields such as top_p, enable_search
```

| # | Notes |
|---|---|
| (1) | The model id must match the provider documentation exactly; a typo returns 404 |
| (2) | Must end with `/v1` (the client appends `/chat/completions`) |
| (3) | The variable name is customisable, e.g. `DEEPSEEK_API_KEY`, but config and `.env` must agree |
| (4) | Most services use `max_tokens`; **newer OpenAI reasoning models only accept `max_completion_tokens`**, otherwise 400 |
| (5) | `false` raises on failure; `true` warns and falls back to the offline generator (`model_id` becomes `offline-extractive`) |
| (6) | The cost report depends directly on these two prices — wrong values produce a wrong cost per 1,000 calls |
| (7) | Provider-specific parameters, merged into the request body |

> If you rename `api_key_env` to `DEEPSEEK_API_KEY`, rename the variable in `.env` to match, otherwise
> you will get "environment variable not set".

## 3. base_url for common services

> Provider endpoints and model ids change. **Check the official documentation before use**; the table
> below is a starting point.

| Service | base_url | Notes |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Requires outbound internet access |
| DeepSeek | `https://api.deepseek.com/v1` | OpenAI-compatible |
| Alibaba Cloud Bailian (Qwen) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible mode |
| Moonshot (Kimi) | `https://api.moonshot.cn/v1` | OpenAI-compatible |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` | Note it is `v4`, not `v1` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | Aggregates multiple providers |
| Local vLLM | `http://localhost:8000/v1` | Any non-empty key works |
| Local Ollama | `http://localhost:11434/v1` | Any non-empty key works |

Local service example (no key validation, but the program requires a non-empty value):

```yaml
generation:
  backend: openai
  model: qwen2.5:7b
  base_url: http://localhost:11434/v1
  api_key_env: OPENAI_API_KEY   # set the value to "not-needed"
```

## 4. Verifying the configuration in three steps

```bash
# 1. Confirm the process can see the key (the key itself is never printed)
uv run python -c "import os; print('key visible:', bool(os.environ.get('OPENAI_API_KEY')))"

# 2. Ask once and check that model_id and tokens come from the real service
uv run python scripts/ask.py "员工每年有多少天年假？" --config configs/openai_example.yaml --json \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['model_id'], d['token_usage'], d['cost_usd'])"

# 3. Inspect the generate-stage latency in the logs
#    (a real model takes hundreds of ms to seconds, not a few milliseconds)
tail -5 logs/rag.jsonl | python -c "
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    if r.get('stage') == 'generate':
        print('generate stage latency:', r.get('latency_ms'), 'ms')
"
```

**Pass criteria**: `model_id` equals the configured model id and the generate stage takes clearly
longer than retrieval — that means the real model was called. If `model_id` shows
`offline-extractive`, a fallback occurred.

## 5. Common errors

| Error | Cause | Action |
|---|---|---|
| `environment variable OPENAI_API_KEY not set` | Key not injected, or variable name mismatch | Check that `api_key_env` matches the `.env` / shell variable name |
| `LLM API 401 ... invalid api key` | Wrong or expired key, or key not valid for this base_url | Confirm the key belongs to that provider |
| `LLM API 404 ...` | Wrong base_url or model id | Check the `/v1` suffix and that the model id matches the vendor docs |
| `LLM API 400 ... max_tokens` | Unsupported field name | Switch to `max_tokens_field: max_completion_tokens` |
| `LLM API 429` | Rate limited or quota exhausted | Reduce concurrency, add retries, check account balance |
| `httpx.ConnectError` | Network unreachable (e.g. cannot reach api.openai.com directly) | Switch to a reachable service, or configure a proxy |
| `response structure abnormal` | The service is not OpenAI-compatible | Use its "compatible mode" endpoint |
| Cost is 0 | The service returned no `usage` block | The code falls back to a local estimate; a persistent 0 means the request failed |

## 6. Security notes

1. **Never put the key in YAML or commit it.** Configuration files carry only the variable name, and
   `.env` is git-ignored.
2. Logs never record the key (the `Authorization` header is not persisted), but they do record
   `model_id`, tokens and error messages.
3. Raw provider error text is truncated and stored in logs for triage; if it may contain sensitive
   content, restrict log access accordingly.
4. Set `fallback_to_offline: false` when evaluating — otherwise a misconfigured key degrades silently
   and disguises a configuration error as poor model quality.

## 7. End-to-end verification already performed on this machine

Because this environment cannot reach `api.openai.com` and has no real key, the bundled mock service
`scripts/mock_llm_server.py` was used to verify the full integration path (it produces **no real model
behaviour**; it only exercises the pipeline):

```bash
uv run python scripts/mock_llm_server.py --port 8123     # terminal 1
export OPENAI_API_KEY=mock-key-for-verification          # terminal 2
uv run python scripts/eval.py --configs configs/mock_local.yaml
```

Verified scenarios:

| Scenario | Result |
|---|---|
| Correct key | `model_id=mock-model`, tokens taken from the API response, cost $0.00017655 matching the formula |
| No key + `fallback_to_offline: false` | Error naming the variable and the two ways to set it |
| Wrong key + `fallback_to_offline: false` | `RuntimeError: LLM API 401 ... invalid api key` (no silent degradation) |
| Wrong key + `fallback_to_offline: true` | Warning printed and fallback applied, `model_id=offline-extractive` |
| Injection via `.env` (no shell variable) | `model_id=mock-model`, proving `.env` is auto-loaded |
| `OPENAI_BASE_URL` / `OPENAI_MODEL` set in `.env` | Overrode the same-named YAML fields; `model_id` and endpoint both changed |
| Full evaluation (216 items) | Ran end-to-end at $0.1505 per 1,000 calls, P90 71 ms (mock has a fixed 50 ms delay) |

With a real key, only three fields in `configs/openai_example.yaml` need changing — `base_url`, `model`
and `price_*` — after which the evaluation can be re-run.
