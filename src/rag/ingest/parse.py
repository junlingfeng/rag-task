"""文档解析与 OCR。

解析顺序：文本层优先，无文本层则判定为扫描件并走 OCR。
OCR 有三条路径，按可用性自动选择：
  rapidocr  -> 真实 OCR（需要安装 ocr extras）
  sidecar   -> 读取预置文本（OCR 依赖不可用时的降级路径，会在清单中标注）
  none      -> 放弃该页并记录告警
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedPage:
    page: int
    text: str
    is_scanned: bool
    ocr_confidence: float | None = None


@dataclass
class ParsedDocument:
    doc_id: str
    doc_type: str
    lang: str
    title: str
    pages: list[ParsedPage]
    ocr_engine: str

    @property
    def is_scanned(self) -> bool:
        return any(p.is_scanned for p in self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


def detect_lang(text: str) -> str:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk == 0:
        return "en"
    if latin == 0:
        return "zh"
    return "mixed" if min(cjk, latin) / max(cjk, latin) > 0.15 else ("zh" if cjk > latin else "en")


class OcrEngine:
    """OCR 引擎封装，自动选择可用实现。"""

    def __init__(self, raw_dir: Path, enabled: bool = True) -> None:
        self.raw_dir = raw_dir
        self.name = "none"
        self._engine = None
        if enabled:
            self._init_engine()

    def _init_engine(self) -> None:
        try:  # pragma: no cover - 依赖是否安装取决于环境
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
            self.name = "rapidocr"
        except Exception:
            self._engine = None
            self.name = "sidecar"

    def run(self, doc_id: str, page_number: int, image_bytes: bytes) -> tuple[str, float | None]:
        if self._engine is not None:
            import numpy as np
            from PIL import Image
            import io

            image = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
            result, _ = self._engine(image)
            if not result:
                return "", 0.0
            texts = [item[1] for item in result]
            scores = [float(item[2]) for item in result]
            return "\n".join(texts), sum(scores) / len(scores)

        # 降级路径：旁路文本按页切分（仅用于 OCR 依赖不可用的环境）
        sidecar = self.raw_dir / f"{doc_id}.ocr.txt"
        if sidecar.exists():
            pages = sidecar.read_text(encoding="utf-8").split("\f")
            if page_number - 1 < len(pages):
                return pages[page_number - 1], None
        return "", None


def parse_markdown(path: Path) -> list[ParsedPage]:
    text = path.read_text(encoding="utf-8")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    return [ParsedPage(page=1, text="\n\n".join(blocks), is_scanned=False)]


def parse_pdf(path: Path, doc_id: str, ocr: OcrEngine, min_text_chars: int = 20) -> list[ParsedPage]:
    import fitz  # PyMuPDF

    pages: list[ParsedPage] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if len(text) >= min_text_chars:
                pages.append(ParsedPage(page=index, text=text, is_scanned=False))
                continue
            pixmap = page.get_pixmap(dpi=200)
            ocr_text, confidence = ocr.run(doc_id, index, pixmap.tobytes("png"))
            from ..textutil import normalize_ocr_text

            pages.append(
                ParsedPage(
                    page=index,
                    text=normalize_ocr_text(ocr_text.strip()),
                    is_scanned=True,
                    ocr_confidence=confidence,
                )
            )
    return pages


def load_manifest(raw_dir: Path) -> dict:
    return json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))


def parse_corpus(raw_dir: Path = Path("data/corpus/raw"), ocr_enabled: bool = True) -> list[ParsedDocument]:
    manifest = load_manifest(raw_dir)
    ocr = OcrEngine(raw_dir, enabled=ocr_enabled)
    documents: list[ParsedDocument] = []
    for entry in manifest["documents"]:
        path = Path(entry["path"])
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.suffix.lower() == ".pdf":
            pages = parse_pdf(path, entry["doc_id"], ocr)
        else:
            pages = parse_markdown(path)
        full_text = "\n".join(p.text for p in pages)
        documents.append(
            ParsedDocument(
                doc_id=entry["doc_id"],
                doc_type=entry["doc_type"],
                lang=entry["lang"] if entry["lang"] != "mixed" else detect_lang(full_text),
                title=entry["title_zh"],
                pages=pages,
                ocr_engine=ocr.name if any(p.is_scanned for p in pages) else "none",
            )
        )
    return documents
