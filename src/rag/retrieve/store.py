"""索引存储。

默认使用进程内 numpy 存储（无需 Docker，保证一键复现）；
配置 retrieval.store=qdrant 时切换到 Qdrant（需要 stores extras 与运行中的服务）。
两种实现都只负责向量通道，词法通道由 BM25 在本地计算，
融合（RRF）统一在客户端完成，从而保证三配置对比使用完全相同的融合逻辑。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..types import Chunk

INDEX_ROOT = Path("data/index")


class LocalStore:
    name = "local"

    def __init__(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        self.chunks = chunks
        self.vectors = vectors
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        if not len(self.vectors):
            return []
        scores = self.vectors @ query_vector
        order = np.argsort(-scores)[:top_k]
        return [(int(i), float(scores[i])) for i in order]

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / "chunks.jsonl", "w", encoding="utf-8") as handle:
            for chunk in self.chunks:
                handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        np.save(directory / "vectors.npy", self.vectors)

    @staticmethod
    def load(directory: Path) -> "LocalStore":
        chunks = [
            Chunk.from_dict(json.loads(line))
            for line in (directory / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        vectors = np.load(directory / "vectors.npy")
        return LocalStore(chunks, vectors)


class QdrantStore:
    """Qdrant 向量后端（可选）。

    仅承载稠密向量通道；融合仍在客户端完成，便于统一日志与对比。
    """

    name = "qdrant"

    def __init__(self, chunks: list[Chunk], url: str = "http://localhost:6333", collection: str = "kb") -> None:
        from qdrant_client import QdrantClient  # 延迟导入

        self.chunks = chunks
        self.collection = collection
        self.client = QdrantClient(url=url)

    def upsert(self, vectors: np.ndarray) -> None:  # pragma: no cover - 需要外部服务
        from qdrant_client.models import Distance, PointStruct, VectorParams

        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE),
        )
        points = [
            PointStruct(
                id=index,
                vector=vectors[index].tolist(),
                payload={"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id},
            )
            for index, chunk in enumerate(self.chunks)
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[int, float]]:  # pragma: no cover
        hits = self.client.search(
            collection_name=self.collection, query_vector=query_vector.tolist(), limit=top_k
        )
        return [(int(hit.id), float(hit.score)) for hit in hits]

    def save(self, directory: Path) -> None:
        LocalStore(self.chunks, np.zeros((len(self.chunks), 1))).save(directory)

    @staticmethod
    def load(directory: Path) -> "QdrantStore":  # pragma: no cover
        store = LocalStore.load(directory)
        return QdrantStore(store.chunks)
