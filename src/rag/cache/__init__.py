"""缓存：精确匹配 + 语义缓存。

缓存键必须包含配置指纹、提示词版本、知识库版本与模型 ID，
否则切换配置或更新文档后会返回陈旧答案（这是"合规率下降"的典型成因）。
"""

from __future__ import annotations

import hashlib
import time

import numpy as np

from ..config import Config
from ..retrieve.embedding import Embedder


def cache_key(config: Config, question: str, session_id: str | None = None) -> str:
    parts = [
        question.strip().lower(),
        config.generation.model,
        config.app.config_version,
        config.app.prompt_version,
        config.app.corpus_version,
        config.retrieval.mode,
        str(config.rerank.enabled),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:24]


class BaseCache:
    hits = 0
    lookups = 0

    def get(self, key: str, question: str) -> dict | None:  # pragma: no cover - 接口
        raise NotImplementedError

    def put(self, key: str, question: str, value: dict) -> None:  # pragma: no cover - 接口
        raise NotImplementedError

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0


class NullCache(BaseCache):
    def get(self, key: str, question: str) -> dict | None:
        self.lookups += 1
        return None

    def put(self, key: str, question: str, value: dict) -> None:
        return None


class MemoryCache(BaseCache):
    def __init__(self, ttl_seconds: int = 86400, max_entries: int = 1000) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.store: dict[str, tuple[float, dict]] = {}

    def get(self, key: str, question: str) -> dict | None:
        self.lookups += 1
        entry = self.store.get(key)
        if not entry:
            return None
        timestamp, value = entry
        if time.time() - timestamp > self.ttl:
            self.store.pop(key, None)
            return None
        self.hits += 1
        return value

    def put(self, key: str, question: str, value: dict) -> None:
        if len(self.store) >= self.max_entries:
            oldest = min(self.store, key=lambda k: self.store[k][0])
            self.store.pop(oldest, None)
        self.store[key] = (time.time(), value)


class SemanticCache(MemoryCache):
    """在精确匹配之上增加向量相似度匹配。"""

    def __init__(
        self,
        embedder: Embedder,
        threshold: float = 0.95,
        ttl_seconds: int = 86400,
        max_entries: int = 1000,
    ) -> None:
        super().__init__(ttl_seconds, max_entries)
        self.embedder = embedder
        self.threshold = threshold
        self.vectors: list[tuple[str, np.ndarray]] = []

    def get(self, key: str, question: str) -> dict | None:
        exact = super().get(key, question)
        if exact is not None:
            return exact
        if not self.vectors:
            return None
        self.lookups += 1
        query_vector = self.embedder.encode([question])[0]
        best_key, best_score = None, 0.0
        for stored_key, vector in self.vectors:
            score = float(np.dot(query_vector, vector))
            if score > best_score:
                best_key, best_score = stored_key, score
        if best_key and best_score >= self.threshold and best_key in self.store:
            self.hits += 1
            return self.store[best_key][1]
        return None

    def put(self, key: str, question: str, value: dict) -> None:
        super().put(key, question, value)
        self.vectors = [(k, v) for k, v in self.vectors if k != key]
        self.vectors.append((key, self.embedder.encode([question])[0]))
        if len(self.vectors) > self.max_entries:
            self.vectors.pop(0)


def get_cache(config: Config, embedder: Embedder) -> BaseCache:
    if not config.cache.enabled:
        return NullCache()
    if config.cache.mode == "semantic":
        return SemanticCache(
            embedder,
            threshold=config.cache.similarity_threshold,
            ttl_seconds=config.cache.ttl_seconds,
            max_entries=config.cache.max_entries,
        )
    return MemoryCache(ttl_seconds=config.cache.ttl_seconds, max_entries=config.cache.max_entries)
