"""重排器：可配置开关，且必须支持超时降级。

三种后端：
  none         -> 不重排
  lexical      -> 无依赖的特征重排（词覆盖 + 短语命中 + 数字一致性）
  cross_encoder-> 真实交叉编码器（sentence-transformers CrossEncoder）

超时策略：重排耗时不可控（本地 CPU 或远程服务），一旦超出 timeout_ms
立即回退到融合结果，避免拖垮 10s 的端到端约束。
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import numpy as np

from ..retrieve.lexical import tokenize
from ..types import Retrieved

_NUMBERS = re.compile(r"\d+(?:\.\d+)?")


class Reranker:
    name = "none"

    def score(self, query: str, documents: list[str]) -> list[float]:
        return [0.0] * len(documents)


class LexicalReranker(Reranker):
    """无依赖重排：适合离线环境，优化方向与真实交叉编码器一致。"""

    name = "lexical"

    def score(self, query: str, documents: list[str]) -> list[float]:
        query_tokens = set(tokenize(query))
        query_numbers = set(_NUMBERS.findall(query))
        compact_query = re.sub(r"\s+", "", query.lower())
        scores: list[float] = []
        for document in documents:
            doc_tokens = set(tokenize(document))
            overlap = len(query_tokens & doc_tokens) / len(query_tokens) if query_tokens else 0.0
            compact_doc = re.sub(r"\s+", "", document.lower())
            phrase = 1.0 if compact_query and compact_query in compact_doc else 0.0
            if query_numbers:
                numbers = len(query_numbers & set(_NUMBERS.findall(document))) / len(query_numbers)
            else:
                numbers = 1.0
            scores.append(round(0.7 * overlap + 0.2 * phrase + 0.1 * numbers, 6))
        return scores


class CrossEncoderReranker(Reranker):
    name = "cross_encoder"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder  # 延迟导入

        self._model = CrossEncoder(model_name)
        self.name = f"cross_encoder:{model_name}"

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        raw = self._model.predict([(query, doc) for doc in documents])
        values = np.asarray(raw, dtype="float32").reshape(-1)
        # 交叉编码器输出无界，用 sigmoid 归一化到 0-1 便于阈值判定
        return list(1.0 / (1.0 + np.exp(-values)))


class OnnxCrossEncoderReranker(Reranker):
    """ONNX Runtime 版交叉编码器重排（无需 PyTorch）。

    为什么必须用真实交叉编码器：实验发现词法重排会**降低**指标
    （Context Precision 0.4346 → 0.4115）。原因是它按词面重叠重新排序，
    把多语言向量通道好不容易找回来的跨语言证据又压了下去。
    交叉编码器同时看 query 与文档，才能与语义检索相匹配。
    """

    def __init__(
        self,
        model_dir: str,
        onnx_file: str = "onnx/model_int8.onnx",
        max_length: int = 512,
    ) -> None:
        from pathlib import Path

        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = Path(model_dir)
        tokenizer_path = directory / "tokenizer.json"
        model_path = directory / onnx_file
        if not tokenizer_path.exists() or not model_path.exists():
            raise FileNotFoundError(f"ONNX 重排模型文件缺失：{tokenizer_path} / {model_path}")
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding()
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.input_names = {spec.name for spec in self.session.get_inputs()}
        self.name = f"onnx_cross_encoder:{directory.name}"

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        encoded = self.tokenizer.encode_batch([(query, doc) for doc in documents])
        input_ids = np.asarray([e.ids for e in encoded], dtype="int64")
        attention = np.asarray([e.attention_mask for e in encoded], dtype="int64")
        feeds: dict[str, np.ndarray] = {}
        if "input_ids" in self.input_names:
            feeds["input_ids"] = input_ids
        if "attention_mask" in self.input_names:
            feeds["attention_mask"] = attention
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.asarray(
                [e.type_ids for e in encoded], dtype="int64"
            )
        logits = np.asarray(self.session.run(None, feeds)[0], dtype="float32").reshape(-1)
        return list(1.0 / (1.0 + np.exp(-logits)))


def get_reranker(
    backend: str,
    model: str,
    onnx_file: str = "onnx/model_int8.onnx",
    max_length: int = 256,
) -> Reranker:
    if backend == "onnx_cross_encoder":
        try:
            return OnnxCrossEncoderReranker(model, onnx_file, max_length=max_length)
        except Exception as exc:  # pragma: no cover - 取决于环境
            print(f"[warn] ONNX 交叉编码器不可用（{exc}），降级为 lexical 重排")
            return LexicalReranker()
    if backend == "cross_encoder":
        try:
            return CrossEncoderReranker(model)
        except Exception as exc:  # pragma: no cover - 取决于环境
            print(f"[warn] cross_encoder 不可用（{exc}），降级为 lexical 重排")
            return LexicalReranker()
    if backend == "lexical":
        return LexicalReranker()
    return Reranker()


def rerank_with_timeout(
    reranker: Reranker,
    query: str,
    candidates: list[Retrieved],
    top_n: int,
    timeout_ms: int,
) -> tuple[list[Retrieved], bool]:
    """执行重排；超时则原样返回融合结果，并返回超时标记。"""
    if not candidates:
        return [], False
    documents = [c.chunk.text for c in candidates]
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            scores = pool.submit(reranker.score, query, documents).result(timeout=timeout_ms / 1000.0)
        for candidate, score in zip(candidates, scores):
            candidate.rerank_score = float(score)
        ordered = sorted(candidates, key=lambda c: (-(c.rerank_score or 0.0), c.rank))
        for position, candidate in enumerate(ordered, start=1):
            candidate.rank = position
            candidate.score = float(candidate.rerank_score or 0.0)
        return ordered[:top_n], False
    except FutureTimeout:
        return candidates[:top_n], True
