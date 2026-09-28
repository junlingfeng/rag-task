"""Embedding 后端。

默认 hashing 后端不依赖任何模型，保证在完全离线的环境里也能端到端跑通；
配置 embedding.backend=sentence_transformers 即切换到 bge-m3 / multilingual-e5
一类的真实多语言模型（需要安装 models extras）。

注意：hashing 后端是词法哈希向量，不具备语义泛化能力。
它只用于验证链路与实验方法，**不能作为语义检索效果的证据**；
报告必须基于真实模型重跑（见 reports/ 中的说明）。
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_LATIN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _features(text: str) -> list[str]:
    """提取特征：中文用字符二元组，英文用词，兼顾双语。"""
    lowered = text.lower()
    features: list[str] = []
    for block in _CJK.findall(lowered):
        if len(block) == 1:
            features.append(block)
        else:
            features.extend(block[i : i + 2] for i in range(len(block) - 1))
    features.extend(token for token in _LATIN.findall(lowered) if len(token) > 1)
    return features


class HashingEmbedder:
    """确定性哈希向量：无需模型、可复现，用于离线链路验证。"""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _encode_one(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype="float32")
        counts: dict[str, int] = {}
        for feature in _features(text):
            counts[feature] = counts.get(feature, 0) + 1
        for feature, count in counts.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * (1.0 + np.log(count))
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        return np.vstack([self._encode_one(t) for t in texts])


class SentenceTransformerEmbedder:
    """真实多语言向量模型（bge-m3 / multilingual-e5 等）。"""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # 延迟导入

        self._model = SentenceTransformer(model_name)
        self.name = model_name
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=16,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32")


class OnnxMultilingualEmbedder:
    """ONNX Runtime 版多语言向量模型（无需 PyTorch）。

    为什么需要它：这台机器是 macOS x86_64，PyTorch 已不再提供该平台 wheel，
    sentence-transformers 装不上；而哈希向量没有跨语言语义能力，
    会导致"英文问题检索不到中文文档"（实测 Context Precision 仅 0.38 的根因）。

    ONNX Runtime + tokenizers 可以在无 PyTorch 的前提下跑真正的多语言模型。
    分词、均值池化、L2 归一化按 sentence-transformers 的标准流程实现。
    """

    def __init__(self, model_dir: str, onnx_file: str = "onnx/model_int8.onnx", max_length: int = 256) -> None:
        from pathlib import Path

        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = Path(model_dir)
        tokenizer_path = directory / "tokenizer.json"
        model_path = directory / onnx_file
        if not tokenizer_path.exists() or not model_path.exists():
            raise FileNotFoundError(
                f"ONNX embedding 文件缺失：{tokenizer_path} / {model_path}；"
                f"请按 RUNBOOK 第 5.1 节下载模型"
            )
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding()
        self.session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_names = {spec.name for spec in self.session.get_inputs()}
        self.output_names = [spec.name for spec in self.session.get_outputs()]
        self.dim = self._infer_dim()
        self.name = f"onnx:{directory.name}:{Path(onnx_file).name}"

    def _infer_dim(self) -> int:
        for spec in self.session.get_outputs():
            shape = spec.shape
            if len(shape) == 3 and isinstance(shape[-1], int):
                return int(shape[-1])
        return 384

    def encode(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        vectors: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            encoded = self.tokenizer.encode_batch(batch)
            input_ids = np.asarray([e.ids for e in encoded], dtype="int64")
            attention = np.asarray([e.attention_mask for e in encoded], dtype="int64")
            feeds: dict[str, np.ndarray] = {}
            if "input_ids" in self.input_names:
                feeds["input_ids"] = input_ids
            if "attention_mask" in self.input_names:
                feeds["attention_mask"] = attention
            if "token_type_ids" in self.input_names:
                feeds["token_type_ids"] = np.zeros_like(input_ids)
            outputs = self.session.run(None, feeds)
            hidden = np.asarray(outputs[0], dtype="float32")
            if hidden.ndim == 3:
                # 均值池化：按 attention mask 加权平均，忽略 padding
                mask = attention[..., None].astype("float32")
                summed = (hidden * mask).sum(axis=1)
                counts = np.clip(mask.sum(axis=1), 1e-9, None)
                pooled = summed / counts
            else:
                pooled = hidden
            norm = np.linalg.norm(pooled, axis=1, keepdims=True)
            vectors.append(pooled / np.clip(norm, 1e-9, None))
        return np.vstack(vectors).astype("float32")


def get_embedder(
    backend: str, model: str, dim: int = 512, onnx_file: str = "onnx/model_int8.onnx"
) -> Embedder:
    """按配置构造 embedding 后端，失败时降级并保留可复现性。"""
    if backend == "onnx":
        try:
            return OnnxMultilingualEmbedder(model, onnx_file)
        except Exception as exc:
            # 不静默降级：哈希向量与 ONNX 向量不在同一向量空间，
            # 降级后会在加载索引时报"索引由 X 生成、当前配置为 Y"，把
            # "模型没下载"误导成"索引不一致"，排查成本很高。
            raise RuntimeError(
                f"ONNX 向量后端不可用：{exc}\n"
                f"可选处理：\n"
                f"  1) 按 RUNBOOK 第 5.1 节下载 ONNX 模型到 {model}/；\n"
                f"  2) 或把 embedding.backend 改为 hashing 后重新入库 "
                f"（uv run python scripts/ingest.py --rebuild-corpus）。\n"
                f"提示：configs/c1..c3_*.yaml 使用的就是 hashing 后端，无需下载模型即可运行。"
            ) from exc
    if backend == "sentence_transformers":
        try:
            return SentenceTransformerEmbedder(model)
        except Exception as exc:  # pragma: no cover - 取决于环境
            print(f"[warn] sentence_transformers 后端不可用（{exc}），降级为 hashing 后端")
            return HashingEmbedder(dim)
    return HashingEmbedder(dim)
