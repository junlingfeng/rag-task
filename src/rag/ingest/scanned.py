"""把文档渲染成"纯图片 PDF"，用于模拟扫描件。

生成的 PDF 不含任何文本层，必须经过 OCR 才能取出内容，
以此验证需求中"小部分扫描件"的解析链路。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGE_W, PAGE_H = 1240, 1754        # A4 @150dpi
MARGIN_X, MARGIN_Y = 90, 100
LINE_GAP = 12

_FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """按像素宽度折行；中文按字符切，英文按单词切。"""
    lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line.strip():
            lines.append("")
            continue
        is_cjk = sum(1 for ch in raw_line if "\u4e00" <= ch <= "\u9fff") > len(raw_line) * 0.2
        tokens = list(raw_line) if is_cjk else raw_line.split(" ")
        joiner = "" if is_cjk else " "
        current = ""
        for token in tokens:
            candidate = f"{current}{joiner}{token}" if current else token
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = token
        if current:
            lines.append(current)
    return lines


def render_scanned_pdf(doc, output: Path, noise: int = 3, scale: float = 2.0) -> int:
    """把 Document 渲染为多页纯图片 PDF，返回页数。

    scale=2 相当于 300 DPI。实测 150 DPI + 较大噪点时 OCR 会吞掉英文词间空格
    （"Companydataisclassified..."），导致后续标注与检索失配；
    提高分辨率并降低噪点后该问题消失——这是扫描件质量的真实影响。
    """
    import numpy as np

    page_w, page_h = int(PAGE_W * scale), int(PAGE_H * scale)
    margin_x, margin_y = int(MARGIN_X * scale), int(MARGIN_Y * scale)
    title_font = _load_font(int(38 * scale))
    head_font = _load_font(int(30 * scale))
    body_font = _load_font(int(24 * scale))
    line_gap = int(LINE_GAP * scale)
    width = page_w - 2 * margin_x

    pages: list[Image.Image] = []
    image = Image.new("RGB", (page_w, page_h), "white")
    draw = ImageDraw.Draw(image)
    y = margin_y

    def new_page() -> None:
        nonlocal image, draw, y
        pages.append(image)
        image = Image.new("RGB", (page_w, page_h), "white")
        draw = ImageDraw.Draw(image)
        y = margin_y

    def write(text: str, font: ImageFont.FreeTypeFont, gap_after: int | None = None) -> None:
        nonlocal y
        gap = line_gap if gap_after is None else int(gap_after * scale)
        for line in _wrap(draw, text, font, width):
            line_height = font.size + gap
            if y + line_height > page_h - margin_y:
                new_page()
            if line:
                draw.text((margin_x, y), line, fill="black", font=font)
            y += line_height

    from .facts import facts_by_key

    facts = facts_by_key()
    write(doc.title_zh if doc.lang != "en" else doc.title_en, title_font, 18)
    if doc.lang == "mixed":
        write(doc.title_en, head_font, 12)
    y += 10

    for section in doc.sections:
        heading = section.heading_zh if doc.lang != "en" else section.heading_en
        if doc.lang == "mixed":
            heading = f"{section.heading_zh} / {section.heading_en}"
        write(heading, head_font, 12)
        if doc.lang in ("zh", "mixed"):
            for key in section.fact_keys:
                write(facts[key]["zh"], body_font)
            if section.filler_zh:
                write(section.filler_zh, body_font)
        if doc.lang in ("en", "mixed"):
            for key in section.fact_keys:
                write(facts[key]["en"], body_font)
            if section.filler_en:
                write(section.filler_en, body_font)
        y += 8

    pages.append(image)

    if noise:
        noised = []
        for page in pages:
            array = np.asarray(page).astype("float32")
            array = array + np.random.default_rng(42).normal(0, noise, array.shape)
            noised.append(Image.fromarray(array.clip(0, 255).astype("uint8")))
        pages = noised

    output.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(output, "PDF", save_all=True, append_images=pages[1:], resolution=int(150 * scale))
    return len(pages)
