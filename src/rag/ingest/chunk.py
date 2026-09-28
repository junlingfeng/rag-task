"""结构化切分 + 父子块（small-to-big）。

设计理由：
- 子块小 → 检索命中更精确，有利于 Context Precision；
- 父块大 → 生成时有足够上下文，有利于 Faithfulness；
- 因此用子块索引、父块补全，两者不是二选一。
切分尺寸是本项目 NFR4 的天然诊断素材：切太碎掉 Faithfulness，切太大掉 Context Precision。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import ParsedDocument, detect_lang

CHILD_TOKENS = 320
CHILD_OVERLAP_TOKENS = 50
PARENT_TOKENS = 1300

_CJK = re.compile(r"[\u4e00-\u9fff]")
_HEADING_MAX_LEN = 34


def estimate_tokens(text: str) -> int:
    """混合语料的 token 估算：中文按 1 字 ≈ 1 token，英文按 4 字符 ≈ 1 token。"""
    cjk = len(_CJK.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    other = max(0, len(text) - cjk - latin)
    return int(cjk * 1.0 + latin / 4.0 + other / 4.0) + 1


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    if not stripped or len(stripped) > _HEADING_MAX_LEN:
        return False
    if stripped[-1] in "。．.；;，,：:":
        return False
    # 章节标题通常不含句末标点，且较短；OCR 文本没有 markdown 标记，只能靠启发式
    return bool(re.match(r"^[\u4e00-\u9fffA-Za-z0-9 /·\-（）()、]+$", stripped))


@dataclass
class Block:
    text: str
    section_path: str
    page: int


def _split_blocks(doc: ParsedDocument) -> list[Block]:
    blocks: list[Block] = []
    section = doc.title
    for page in doc.pages:
        buffer: list[str] = []
        for raw_line in page.text.split("\n"):
            line = raw_line.rstrip()
            if _is_heading(line):
                if buffer:
                    blocks.append(Block("\n".join(buffer).strip(), section, page.page))
                    buffer = []
                heading = line.lstrip("#").strip()
                if heading:
                    section = heading
                continue
            if not line.strip():
                if buffer:
                    blocks.append(Block("\n".join(buffer).strip(), section, page.page))
                    buffer = []
                continue
            buffer.append(line)
        if buffer:
            blocks.append(Block("\n".join(buffer).strip(), section, page.page))
    return [b for b in blocks if b.text.strip()]


def _group_blocks(blocks: list[Block], max_tokens: int, overlap_tokens: int) -> list[list[Block]]:
    """把 block 聚合成不超过 max_tokens 的组，组间保留少量重叠。

    返回的是 block 分组而不是合并后的文本，这样父块与子块共享同一份 block，
    不会因为文本重复匹配导致块归属错乱。
    """
    groups: list[list[Block]] = []
    current: list[Block] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        groups.append(current)
        if overlap_tokens <= 0 or len(current) == 1:
            current, current_tokens = [], 0
            return
        tail: list[Block] = []
        tokens = 0
        for block in reversed(current):
            tokens += estimate_tokens(block.text)
            tail.insert(0, block)
            if tokens >= overlap_tokens:
                break
        current = tail if len(tail) < len(current) else []
        current_tokens = sum(estimate_tokens(b.text) for b in current)

    for block in blocks:
        tokens = estimate_tokens(block.text)
        if current and current_tokens + tokens > max_tokens:
            flush()
        if tokens > max_tokens:
            # 超长单块按句子再切
            for sentence in re.split(r"(?<=[。！？!?.])\s*", block.text):
                if not sentence.strip():
                    continue
                sentence_tokens = estimate_tokens(sentence)
                if current and current_tokens + sentence_tokens > max_tokens:
                    flush()
                current.append(Block(sentence.strip(), block.section_path, block.page))
                current_tokens += sentence_tokens
            continue
        if current and current[0].section_path != block.section_path and current_tokens > max_tokens * 0.6:
            flush()
        current.append(block)
        current_tokens += tokens
    flush()
    return groups


def chunk_document(
    doc: ParsedDocument,
    child_tokens: int = CHILD_TOKENS,
    child_overlap_tokens: int = CHILD_OVERLAP_TOKENS,
    parent_tokens: int = PARENT_TOKENS,
) -> list:
    """把一篇文档切成子块，并为每块挂上父块文本。"""
    from ..types import Chunk

    blocks = _split_blocks(doc)
    if not blocks:
        return []
    parents = _group_blocks(blocks, parent_tokens, 0)
    children: list[Chunk] = []

    scanned = doc.is_scanned
    for parent_index, parent_blocks in enumerate(parents):
        parent_id = f"{doc.doc_id}#P{parent_index:03d}"
        parent_text = "\n".join(b.text for b in parent_blocks)
        child_groups = _group_blocks(parent_blocks, child_tokens, child_overlap_tokens) or [parent_blocks]
        for child_index, child_group in enumerate(child_groups):
            child_text = "\n".join(b.text for b in child_group)
            first = child_group[0]
            chunk_id = f"{doc.doc_id}#P{parent_index:03d}C{child_index:02d}"
            children.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    text=child_text,
                    lang=detect_lang(child_text),
                    doc_type=doc.doc_type,
                    section_path=first.section_path,
                    page=first.page,
                    is_scanned=scanned,
                    ocr_confidence=next(
                        (p.ocr_confidence for p in doc.pages if p.page == first.page and p.is_scanned), None
                    ),
                    parent_id=parent_id,
                    parent_text=parent_text,
                )
            )
    return children


def chunk_corpus(
    documents: list[ParsedDocument],
    child_tokens: int = CHILD_TOKENS,
    child_overlap_tokens: int = CHILD_OVERLAP_TOKENS,
    parent_tokens: int = PARENT_TOKENS,
) -> list:
    chunks = []
    for doc in documents:
        chunks.extend(
            chunk_document(doc, child_tokens, child_overlap_tokens, parent_tokens)
        )
    return chunks
