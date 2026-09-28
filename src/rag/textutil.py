"""文本归一化工具。

OCR 输出的空白与原文不一致（例如把英文单词之间的空格吞掉、
在中文词之间插入空格），如果直接用原文做子串匹配会大面积失配。
因此所有"标注锚点 ↔ chunk 文本"的匹配都必须经过同一套归一化。
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")


def normalize_for_match(text: str) -> str:
    """匹配用归一化：去掉全部空白并统一大小写。

    用于锚点查证，不用于检索文本本身。
    """
    return _WS.sub("", text).lower()


def normalize_ocr_text(text: str) -> str:
    """OCR 结果清洗：去掉中文字符之间的空格，压缩多余空行。

    仅作用于中文之间的空白，不动拉丁文内部结构，
    避免把正常的英文分词进一步破坏。
    """
    cleaned = _CJK_GAP.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return "\n".join(line.rstrip() for line in cleaned.splitlines())
