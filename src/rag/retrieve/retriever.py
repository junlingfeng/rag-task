"""检索编排：向量 / 混合 + 融合 + 可选重排。

三种评测配置只是同一个函数在不同配置下的执行结果，
保证除检索策略外没有任何差异（这是三配置对比可比性的前提）。
"""

from __future__ import annotations

from ..config import Config
from ..rerank import Reranker, rerank_with_timeout
from ..types import Retrieved
from .embedding import Embedder
from .lexical import BM25
from .store import LocalStore


class Retriever:
    def __init__(
        self,
        config: Config,
        store: LocalStore,
        bm25: BM25,
        embedder: Embedder,
        reranker: Reranker | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.bm25 = bm25
        self.embedder = embedder
        self.reranker = reranker

    def _vector_channel(self, query: str, top_k: int) -> dict[int, tuple[int, float]]:
        query_vector = self.embedder.encode([query])[0]
        hits = self.store.search(query_vector, top_k)
        return {index: (rank, score) for rank, (index, score) in enumerate(hits, start=1)}

    def _lexical_channel(self, query: str, top_k: int) -> dict[int, tuple[int, float]]:
        scores = self.bm25.scores(query)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return {index: (rank, scores[index]) for rank, index in enumerate(order, start=1)}

    def _fuse(
        self,
        vector_hits: dict[int, tuple[int, float]],
        lexical_hits: dict[int, tuple[int, float]],
        top_k: int,
    ) -> list[Retrieved]:
        mode = self.config.retrieval.mode
        fusion = self.config.retrieval.fusion
        rrf_k = self.config.retrieval.rrf_k
        weight = self.config.retrieval.vector_weight

        candidates = set(vector_hits) | (set(lexical_hits) if mode == "hybrid" else set())
        max_vector = max((s for _, s in vector_hits.values()), default=1.0) or 1.0
        max_lexical = max((s for _, s in lexical_hits.values()), default=1.0) or 1.0
        channels = 2 if (mode == "hybrid" and lexical_hits) else 1
        ceiling = channels * (1.0 / (rrf_k + 1))

        results: list[Retrieved] = []
        for index in candidates:
            vector = vector_hits.get(index)
            lexical = lexical_hits.get(index) if mode == "hybrid" else None
            if fusion == "rrf":
                raw = 0.0
                if vector:
                    raw += 1.0 / (rrf_k + vector[0])
                if lexical:
                    raw += 1.0 / (rrf_k + lexical[0])
                score = raw / ceiling if ceiling else 0.0
            else:  # weighted：归一化后加权
                vector_part = (vector[1] / max_vector) if vector else 0.0
                lexical_part = (lexical[1] / max_lexical) if lexical else 0.0
                if mode == "vector":
                    score = vector_part
                else:
                    denominator = weight + (1 - weight) if lexical else weight
                    score = (weight * vector_part + (1 - weight) * lexical_part) / (denominator or 1)
            results.append(
                Retrieved(
                    chunk=self.store.chunks[index],
                    score=round(min(max(score, 0.0), 1.0), 6),
                    rank=0,
                    vector_score=round(vector[1], 6) if vector else None,
                    lexical_score=round(lexical[1], 6) if lexical else None,
                    vector_rank=vector[0] if vector else None,
                    lexical_rank=lexical[0] if lexical else None,
                )
            )
        results.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        for position, result in enumerate(results[:top_k], start=1):
            result.rank = position
        return results[:top_k]

    def retrieve(self, query: str) -> tuple[list[Retrieved], dict]:
        top_k = self.config.retrieval.top_k
        top_n = self.config.retrieval.top_n
        vector_hits = self._vector_channel(query, top_k)
        lexical_hits = (
            self._lexical_channel(query, top_k) if self.config.retrieval.mode == "hybrid" else {}
        )
        fused = self._fuse(vector_hits, lexical_hits, top_k)

        meta = {"rerank_timeout": False, "rerank_applied": False}
        if self.config.rerank.enabled and self.reranker is not None and fused:
            candidates = fused[: self.config.rerank.max_candidates]
            reranked, timed_out = rerank_with_timeout(
                self.reranker,
                query,
                candidates,
                top_n=top_n,
                timeout_ms=self.config.rerank.timeout_ms,
            )
            meta["rerank_timeout"] = timed_out
            meta["rerank_applied"] = not timed_out
            return reranked, meta
        return fused[:top_n], meta
