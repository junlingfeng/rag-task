"""端到端编排：改写 → 缓存 → 检索 → 重排 → 护栏 → 生成 → 后处理 → 日志。

每个阶段独立埋点，日志字段与阶段一一对应，
这样"合规率下降"这类问题才能被定位到具体阶段（对应需求 §13 与 §35）。
"""

from __future__ import annotations

import time
from pathlib import Path

from .cache import cache_key, get_cache
from .config import Config
from .generate import get_generator
from .guardrails import (
    ScopeDetector,
    detect_injection,
    grounding_check,
    looks_like_self_refusal,
    refusal_answer,
)
from .observability import log_request, new_trace_id, setup_logging, span
from .pii import redact_text
from .rerank import get_reranker
from .rewrite import get_rewriter, needs_resolution
from .retrieve.embedding import get_embedder
from .retrieve.lexical import BM25, tokenize
from .retrieve.retriever import Retriever
from .retrieve.store import INDEX_ROOT, LocalStore
from .types import AnswerResult, Retrieved

ANAPHORA_ZH = ("它", "其", "该", "此", "这", "那", "上述", "同上", "呢", "还有")
ANAPHORA_EN = ("it", "its", "that", "this", "those", "these", "same")
STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "有", "多", "少", "什么", "如何", "怎么",
    "请问", "吗", "呢", "那", "这", "多少", "几", "个", "天", "the", "a", "an", "is",
    "are", "of", "to", "for", "and", "or", "how", "many", "what", "which", "do", "does",
}


def rewrite_query(question: str, history: list[dict]) -> str:
    """多轮改写：把指代与省略补全成可独立检索的查询。

    规则法而非模型法，保证离线可复现；改写效果本身由多轮评测集验证。
    做法是把上一轮问题原文拼接到当前问题之后（会话式检索的经典做法）。
    早期实现只拼接上一轮的高频词元，实测会把中文二元组拼成噪声
    （如"工每/年有/少天"），反而把检索带偏，因此改为拼接完整问句。
    """
    if not history:
        return question
    previous = history[-1].get("question", "")
    if not previous:
        return question
    lowered = question.lower()
    needs_context = any(token in question for token in ANAPHORA_ZH) or any(
        token in lowered.split() for token in ANAPHORA_EN
    )
    if not needs_context and len(tokenize(question)) > 8:
        return question
    return f"{question} {previous.strip()[:120]}"


class RagPipeline:
    def __init__(self, config: Config, index_dir: Path | None = None) -> None:
        self.config = config
        self.index_dir = Path(index_dir or INDEX_ROOT / config.app.corpus_version)
        setup_logging(
            log_dir=config.observability.log_dir,
            redact_query=config.observability.redact_query_in_logs,
            mode=config.observability.log_redaction,
        )
        self.embedder = get_embedder(
            config.embedding.backend,
            config.embedding.model,
            config.embedding.dim,
            config.embedding.onnx_file,
        )
        self.store = LocalStore.load(self.index_dir)
        self._check_index_meta()
        self.bm25 = BM25([chunk.text for chunk in self.store.chunks])
        self.scope_detector = ScopeDetector(
            self.store.chunks,
            self.bm25,
            coverage_min=config.guardrails.scope_coverage_min,
            oov_max=config.guardrails.scope_oov_max,
            oov_unigram_max=config.guardrails.scope_oov_unigram_max,
        )
        self.reranker = (
            get_reranker(
                config.rerank.backend,
                config.rerank.model,
                config.rerank.onnx_file,
                config.rerank.max_length,
            )
            if config.rerank.enabled
            else None
        )
        self.retriever = Retriever(config, self.store, self.bm25, self.embedder, self.reranker)
        self.generator = get_generator(config)
        self.cache = get_cache(config, self.embedder)
        self.rewriter = get_rewriter(config)
        self.sessions: dict[str, list[dict]] = {}

    def _check_index_meta(self) -> None:
        """索引与当前 embedding 后端必须匹配，否则向量空间不一致会静默劣化检索。"""
        meta_path = self.index_dir / "meta.json"
        if not meta_path.exists():
            return
        import json

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("embedding_name") and meta["embedding_name"] != self.embedder.name:
            raise RuntimeError(
                f"索引由 {meta['embedding_name']} 生成，当前配置为 {self.embedder.name}；"
                f"请重新运行 scripts/ingest.py 或把 embedding.backend 改回一致"
            )

    # ------------------------------------------------------------------
    def ask(self, question: str, session_id: str = "default") -> AnswerResult:
        config = self.config
        trace_id = new_trace_id()
        request_id = f"req_{int(time.time() * 1000) % 10_000_000}"
        history = self.sessions.setdefault(session_id, [])
        turn_index = len(history) + 1
        latency: dict[str, float] = {}
        started_all = time.perf_counter()

        # 1) 改写
        with span("rewrite", trace_id=trace_id, request_id=request_id, session_id=session_id) as record:
            rewritten = question
            # 只对真正依赖上下文的追问做改写：独立的新话题问题不该被改写，
            # 否则会白白多一次模型调用，还可能被改坏。
            if history and needs_resolution(question):
                if self.rewriter is not None:
                    try:
                        rewritten = self.rewriter.rewrite(question, history)
                        record["rewriter"] = self.rewriter.name
                    except Exception as exc:
                        print(f"[warn] LLM 改写失败（{exc}），回退规则改写")
                        rewritten = rewrite_query(question, history)
                        record["rewriter"] = "rules_fallback"
                else:
                    rewritten = rewrite_query(question, history)
                    record["rewriter"] = "rules"
            record["rewritten"] = rewritten != question
            record["rewritten_question"] = rewritten[:200]
            # 改写结果同时用于检索与生成。这一点经过 A/B 实测确定：
            #   A2 规则改写用于生成 Comp=0.825 / A3 生成用原始追问 Comp=0.675
            #   B2 LLM 改写用于生成 Comp=0.750 / B3 生成用原始追问 Comp=0.700
            # 原因：追问（"还有呢？"）本身不携带话题，把话题显式写进生成输入后
            # 模型才知道该回答什么，仅靠会话历史不足以稳定消解指代。
        latency["rewrite"] = record["latency_ms"]

        # 2) 缓存
        key = cache_key(config, rewritten, session_id)
        with span("cache", trace_id=trace_id, request_id=request_id) as record:
            cached = self.cache.get(key, rewritten)
            record["cache_hit"] = cached is not None

        injection_flags = detect_injection(question) if config.guardrails.injection_detection else []

        retrieved = []
        rerank_meta = {"rerank_timeout": False, "rerank_applied": False}
        refusal_reason: str | None = None
        if cached is not None and not injection_flags:
            answer_text = cached["answer"]
            citations = cached["citations"]
            generation_usage = cached.get("token_usage", {})
            refusal_reason = cached.get("refusal_reason")
            cache_hit = True
            # 缓存命中必须还原检索上下文：否则响应会丢失引用，
            # 评测里的检索指标也会因为没有证据而全部失真。
            for position, (chunk_id, score) in enumerate(
                zip(cached.get("retrieved_chunk_ids", []), cached.get("retrieval_scores", [])),
                start=1,
            ):
                chunk = self.store.by_id.get(chunk_id)
                if chunk is not None:
                    retrieved.append(Retrieved(chunk=chunk, score=score, rank=position))
        else:
            cache_hit = False
            # 3) 检索（含重排）
            with span(
                "retrieve",
                trace_id=trace_id,
                request_id=request_id,
                retrieval_mode=config.retrieval.mode,
                rerank_enabled=config.rerank.enabled,
                top_k=config.retrieval.top_k,
            ) as record:
                retrieved, rerank_meta = self.retriever.retrieve(rewritten)
                record.update(
                    {
                        "top_n": len(retrieved),
                        "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
                        "retrieval_scores": [round(c.score, 6) for c in retrieved],
                        "vector_scores": [c.vector_score for c in retrieved],
                        "lexical_scores": [c.lexical_score for c in retrieved],
                        "rerank_scores": [c.rerank_score for c in retrieved],
                        "rerank_timeout": rerank_meta["rerank_timeout"],
                    }
                )
            latency["retrieve"] = record["latency_ms"]

            # 4) 护栏前置判定
            refusal_reason: str | None = None
            with span("guardrail", trace_id=trace_id, request_id=request_id) as guard_record:
                scope = (
                    self.scope_detector.evaluate(rewritten)
                    if config.guardrails.scope_check
                    else {"coverage": None, "oov": None, "out_of_scope": False}
                )
                guard_record.update(
                    {
                        "injection_flags": injection_flags,
                        "scope_coverage": scope["coverage"],
                        "scope_oov": scope["oov"],
                        "scope_oov_unigram": scope.get("oov_unigram"),
                        "scope_out_of_scope": scope["out_of_scope"],
                    }
                )
                if injection_flags:
                    refusal_reason = "safety"
                elif scope["out_of_scope"]:
                    refusal_reason = "out_of_scope"

            if refusal_reason:
                answer_text = refusal_answer(refusal_reason, question)
                citations = []
                generation_usage = {"prompt_tokens": 0, "completion_tokens": 0}
                with span("generate", trace_id=trace_id, request_id=request_id, stage_detail="refused"):
                    pass
            else:
                # 5) 生成
                with span("generate", trace_id=trace_id, request_id=request_id) as record:
                    try:
                        # 生成使用改写后的问句 + 历史
                        generated = self.generator.generate(
                            rewritten, retrieved, history, idf=self.bm25.idf
                        )
                    except Exception as exc:
                        # 构造函数层的兜底覆盖不了运行期失败（401/429/超时/5xx），
                        # 这里做第二次兜底，并且只在显式允许时才降级。
                        if not config.generation.fallback_to_offline:
                            raise
                        from .generate import OfflineGenerator, _warn_fallback

                        _warn_fallback(exc)
                        self.generator = OfflineGenerator()
                        generated = self.generator.generate(
                            rewritten, retrieved, history, idf=self.bm25.idf
                        )
                        record["fallback"] = True
                        record["error_type"] = type(exc).__name__
                    answer_text = generated["answer"]
                    citations = generated["citations"]
                    generation_usage = generated.get(
                        "token_usage",
                        {
                            "prompt_tokens": sum(len(tokenize(c.chunk.text)) for c in retrieved),
                            "completion_tokens": len(tokenize(answer_text)),
                        },
                    )
                    record["model_id"] = getattr(self.generator, "name", "offline")
                latency["generate"] = record["latency_ms"]
                if not answer_text:
                    refusal_reason = "no_evidence"
                    answer_text = refusal_answer(refusal_reason, question)
                    citations = []

        # 6) 后处理：接地校验 + PII 脱敏
        with span("postprocess", trace_id=trace_id, request_id=request_id) as record:
            score, grounded = (
                grounding_check(
                    answer_text,
                    retrieved,
                    min_support=config.guardrails.min_support_score,
                )
                if retrieved
                else (0.0, False)
            )
            status = "answered"
            final_reason = refusal_reason if not cache_hit else cached.get("refusal_reason")
            if not final_reason and retrieved and not grounded:
                final_reason = "low_confidence"
            if not final_reason and looks_like_self_refusal(answer_text):
                # 模型自己判断证据不足 → 记为拒答，而不是"已作答"
                final_reason = "no_evidence"
            if final_reason:
                status = "refused"
                if cached is None:
                    answer_text = refusal_answer(final_reason, question)
                    citations = []
            redacted_answer = answer_text
            redacted_fields: list[str] = []
            if config.guardrails.pii.redact_output:
                redacted_answer, hits = redact_text(answer_text, config.guardrails.pii.mode)
                if hits:
                    redacted_fields.extend(hits)
            record["support_score"] = score
            record["grounded"] = grounded
            record["answer_status"] = status

        citation_ids = [c.chunk_id for c in retrieved if c.rank in citations]
        total_ms = (time.perf_counter() - started_all) * 1000.0
        latency["total"] = round(total_ms, 2)

        prompt_tokens = int(generation_usage.get("prompt_tokens", 0))
        completion_tokens = int(generation_usage.get("completion_tokens", 0))
        cost = (
            prompt_tokens * config.generation.price_in_per_1m / 1_000_000
            + completion_tokens * config.generation.price_out_per_1m / 1_000_000
        )

        result = AnswerResult(
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            turn_index=turn_index,
            question=question,
            rewritten_question=rewritten,
            answer=redacted_answer,
            status=status,
            refusal_reason=final_reason if status == "refused" else None,
            citations=citation_ids,
            contexts=retrieved,
            support_score=score,
            latency_ms=latency,
            token_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            cache_hit=cache_hit,
            cost_usd=round(cost, 8),
            config_version=config.app.config_version,
            injection_flags=injection_flags,
            pii_redacted_fields=redacted_fields,
            model_id=getattr(self.generator, "name", "offline"),
        )

        if not cache_hit:
            self.cache.put(
                key,
                rewritten,
                {
                    "answer": answer_text,
                    "citations": citations,
                    "token_usage": generation_usage,
                    "refusal_reason": final_reason if status == "refused" else None,
                    "status": status,
                    "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
                    "retrieval_scores": [round(c.score, 6) for c in retrieved],
                    "citation_ids": [c.chunk_id for c in retrieved if c.rank in citations],
                },
            )

        history.append(
            {"question": question, "answer": result.answer, "turn_index": turn_index, "trace_id": trace_id}
        )

        log_request(
            {
                "trace_id": trace_id,
                "request_id": request_id,
                "session_id": session_id,
                "turn_index": turn_index,
                "stage": "total",
                "latency_ms": latency["total"],
                "config_version": config.app.config_version,
                "config_fingerprint": config.fingerprint(),
                "prompt_version": config.app.prompt_version,
                "corpus_version": config.app.corpus_version,
                "retrieval_mode": config.retrieval.mode,
                "rerank_enabled": config.rerank.enabled,
                "top_k": config.retrieval.top_k,
                "top_n": len(retrieved),
                "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
                "retrieval_scores": [round(c.score, 6) for c in retrieved],
                "rerank_scores": [c.rerank_score for c in retrieved],
                "rerank_timeout": rerank_meta["rerank_timeout"],
                "cache_hit": cache_hit,
                "cache_key_hash": key,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost_usd": result.cost_usd,
                "model_id": result.model_id,
                "answer_status": status,
                "refusal_reason": result.refusal_reason,
                "citation_ids": citation_ids,
                "support_score": round(score, 4),
                "injection_flags": injection_flags,
                "pii_redacted_fields": redacted_fields,
                "user_query": question,
                "error_type": None,
            }
        )
        return result
