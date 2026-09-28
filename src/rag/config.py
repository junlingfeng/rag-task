"""配置加载：YAML + 深度合并 + 配置指纹。

需求 FR1 要求"通过配置切换检索模式与重排开关，不改代码"，
因此所有可调项都必须落在配置模型里，并被记录到每条请求日志（配置快照）。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 在读取环境变量之前加载 .env（不覆盖已存在的真实环境变量）。
# 这样 key 既可以放在 shell 环境里，也可以放在项目根目录的 .env 里。
load_dotenv(override=False)


class AppCfg(BaseModel):
    config_version: str = "v1"
    prompt_version: str = "p1"
    corpus_version: str = "kb_v1"


class RetrievalCfg(BaseModel):
    mode: str = "hybrid"          # vector | hybrid
    # 多轮追问的处理方式：rules=拼接上一轮问题；llm=用模型改写成完整问句
    conversation_rewrite: str = "rules"   # rules | llm
    top_k: int = 20
    top_n: int = 5
    fusion: str = "rrf"           # rrf | weighted
    rrf_k: int = 60
    vector_weight: float = 0.6
    min_score: float = 0.05
    store: str = "local"          # local | qdrant


class ChunkingCfg(BaseModel):
    """切分参数必须可配置：
    1) 它是 NFR4 问题诊断的主要变量（切太碎掉 Faithfulness、切太大掉 Context Precision）；
    2) 切分策略变更后需要重新入库，属于可演进设计的一部分。
    """

    child_tokens: int = 320
    child_overlap_tokens: int = 50
    parent_tokens: int = 1300


class EmbeddingCfg(BaseModel):
    backend: str = "hashing"      # hashing | onnx | sentence_transformers | openai
    model: str = "models/multilingual-minilm"   # onnx 后端为本地目录；ST 后端为模型名
    onnx_file: str = "onnx/model_int8.onnx"
    dim: int = 512


class RerankCfg(BaseModel):
    enabled: bool = False
    backend: str = "lexical"      # lexical | onnx_cross_encoder | cross_encoder | none
    model: str = "models/bge-reranker-base"
    onnx_file: str = "onnx/model_int8.onnx"
    max_length: int = 256
    # 送入重排的候选数。实测 CPU 上单条候选约 35-60ms：
    # 20 条需要 1553ms（超过 800ms 预算会整批降级），10 条约 368-608ms（安全）。
    max_candidates: int = 10
    top_n: int = 5
    timeout_ms: int = 800


class GenerationCfg(BaseModel):
    backend: str = "offline"      # offline | openai
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    # 允许用环境变量覆盖服务地址与模型 id：国内模型通常只需在 .env 里改这两项，
    # 无需改动任何 YAML。设为 None 可关闭该覆盖行为。
    base_url_env: str | None = "OPENAI_BASE_URL"
    model_env: str | None = "OPENAI_MODEL"
    temperature: float = 0.0
    max_output_tokens: int = 600
    # 不同厂商对输出长度字段名不一致：多数用 max_tokens，
    # 新版 OpenAI 推理模型只接受 max_completion_tokens，因此需要可配置。
    max_tokens_field: str = "max_tokens"   # max_tokens | max_completion_tokens
    timeout_seconds: float = 30.0
    # 额外请求字段（例如某些厂商要求的 top_p、enable_search 等）
    extra_body: dict[str, Any] = Field(default_factory=dict)
    # 调用失败时是否回退到离线生成器。评测场景建议设为 false，
    # 否则 key 配错会静默降级并污染指标。
    fallback_to_offline: bool = True
    require_citation: bool = True
    # 示例价格（美元 / 1M token），落地前必须替换为官方当期价格
    price_in_per_1m: float = 0.15
    price_out_per_1m: float = 0.60


class PiiCfg(BaseModel):
    redact_output: bool = True
    redact_logs: bool = True
    mode: str = "placeholder"     # placeholder | hash


class GuardrailsCfg(BaseModel):
    injection_detection: bool = True
    scope_check: bool = True
    min_support_score: float = 0.30
    min_top_score: float = 0.12
    # 越界判定阈值，由 scripts/calibrate_scope.py 在标注集上标定
    scope_coverage_min: float = 0.15
    scope_oov_max: float = 0.50
    scope_oov_unigram_max: float = 0.40
    pii: PiiCfg = Field(default_factory=PiiCfg)


class CacheCfg(BaseModel):
    enabled: bool = True
    backend: str = "memory"       # memory | redis
    mode: str = "exact"           # exact | semantic
    similarity_threshold: float = 0.95
    ttl_seconds: int = 86400
    max_entries: int = 1000


class ObservabilityCfg(BaseModel):
    log_format: str = "json"
    log_dir: str = "logs"
    log_redaction: str = "hash"
    redact_query_in_logs: bool = True


class EvalCfg(BaseModel):
    judge: str = "rule_based"     # rule_based | llm
    judge_model: str | None = None
    seed: int = 20260918


class Config(BaseModel):
    app: AppCfg = Field(default_factory=AppCfg)
    retrieval: RetrievalCfg = Field(default_factory=RetrievalCfg)
    chunking: ChunkingCfg = Field(default_factory=ChunkingCfg)
    embedding: EmbeddingCfg = Field(default_factory=EmbeddingCfg)
    rerank: RerankCfg = Field(default_factory=RerankCfg)
    generation: GenerationCfg = Field(default_factory=GenerationCfg)
    guardrails: GuardrailsCfg = Field(default_factory=GuardrailsCfg)
    cache: CacheCfg = Field(default_factory=CacheCfg)
    observability: ObservabilityCfg = Field(default_factory=ObservabilityCfg)
    eval: EvalCfg = Field(default_factory=EvalCfg)

    def fingerprint(self) -> str:
        """配置指纹：写入日志，保证前后对比可追溯到具体配置。"""
        payload = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_config(path: str | Path, base_path: str | Path = "configs/base.yaml") -> Config:
    """加载配置：base.yaml 作为底稿，目标文件覆盖其上。"""
    data: dict[str, Any] = {}
    base_file = Path(base_path)
    if base_file.exists() and Path(path).resolve() != base_file.resolve():
        data = load_yaml(base_file)
    data = _deep_merge(data, load_yaml(path))
    return _apply_env_overrides(Config.model_validate(data))


def _apply_env_overrides(config: Config) -> Config:
    """环境变量覆盖：优先级为 环境变量 > YAML > 默认值。

    这样切换国内模型只需在 .env 里写：
        OPENAI_API_KEY=sk-xxx
        OPENAI_BASE_URL=https://api.deepseek.com/v1
        OPENAI_MODEL=deepseek-chat
    不需要为每个厂商维护一份 YAML。

    覆盖结果会体现在 config.fingerprint() 中，因此日志里的配置快照
    能区分"同一份 YAML + 不同端点"的两次评测。
    """
    generation = config.generation
    if generation.base_url_env:
        value = os.environ.get(generation.base_url_env, "").strip()
        if value:
            generation.base_url = value.rstrip("/")
    if generation.model_env:
        value = os.environ.get(generation.model_env, "").strip()
        if value:
            generation.model = value
    return config
