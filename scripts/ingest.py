#!/usr/bin/env python
"""一键入库：生成语料 → 解析/OCR → 切分 → 向量化 → 持久化索引。

用法：
    uv run python scripts/ingest.py                      # 完整入库
    uv run python scripts/ingest.py --rebuild-corpus     # 重新生成语料
    uv run python scripts/ingest.py --config configs/base.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.config import load_config  # noqa: E402
from rag.ingest.chunk import chunk_corpus, estimate_tokens  # noqa: E402
from rag.ingest.corpus import MANIFEST_PATH, build_corpus  # noqa: E402
from rag.ingest.parse import parse_corpus  # noqa: E402
from rag.retrieve.embedding import get_embedder  # noqa: E402
from rag.retrieve.store import INDEX_ROOT, LocalStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/base.yaml")
    parser.add_argument("--rebuild-corpus", action="store_true")
    parser.add_argument("--no-ocr", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.rebuild_corpus or not MANIFEST_PATH.exists():
        manifest = build_corpus()
        print(f"[corpus] {json.dumps(manifest['stats'], ensure_ascii=False)}")
    else:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        print(f"[corpus] 复用已有语料：{manifest['stats']}")

    documents = parse_corpus(ocr_enabled=not args.no_ocr)
    engines = {doc.ocr_engine for doc in documents if doc.is_scanned}
    print(f"[parse] 文档 {len(documents)} 篇，扫描件解析引擎：{sorted(engines)}")

    chunks = chunk_corpus(
        documents,
        child_tokens=config.chunking.child_tokens,
        child_overlap_tokens=config.chunking.child_overlap_tokens,
        parent_tokens=config.chunking.parent_tokens,
    )
    average = int(sum(estimate_tokens(c.text) for c in chunks) / len(chunks)) if chunks else 0
    print(f"[chunk] 子块 {len(chunks)} 个，平均 {average} tokens")

    embedder = get_embedder(
        config.embedding.backend,
        config.embedding.model,
        config.embedding.dim,
        config.embedding.onnx_file,
    )
    vectors = embedder.encode([chunk.text for chunk in chunks])
    print(f"[embed] 后端 {embedder.name}，维度 {vectors.shape[1] if len(vectors) else 0}")

    index_dir = INDEX_ROOT / config.app.corpus_version
    store = LocalStore(chunks, vectors)
    store.save(index_dir)
    (index_dir / "meta.json").write_text(
        json.dumps(
            {
                "corpus_version": config.app.corpus_version,
                "embedding_backend": config.embedding.backend,
                "embedding_name": embedder.name,
                "dim": int(vectors.shape[1]) if len(vectors) else 0,
                "chunks": len(chunks),
                "chunking": config.chunking.model_dump(),
                "documents": len(documents),
                "scanned_documents": sum(1 for d in documents if d.is_scanned),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[index] 已写入 {index_dir}")


if __name__ == "__main__":
    main()
