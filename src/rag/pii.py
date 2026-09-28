"""PII 检测与脱敏。

需求 FR3 要求对**输出与日志**同时脱敏。本模块是两者的共同实现，
保证同一套规则不会出现"输出脱敏了但日志没脱敏"的不一致。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiRule:
    name: str
    pattern: re.Pattern[str]


# 顺序有意义：更具体的模式先匹配，避免被更宽泛的模式吃掉。
RULES: tuple[PiiRule, ...] = (
    PiiRule("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    # OCR 与分句可能把邮箱截断成 "user@domain."，完整规则会漏检，因此补一条宽松规则
    PiiRule("EMAIL_PARTIAL", re.compile(r"[\w.+-]+@[\w-]+\.?")),
    PiiRule("CN_ID", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    PiiRule("BANK_CARD", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    PiiRule("CN_MOBILE", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    # 400/800 企业服务热线：没有区号前缀，需要单独覆盖，否则会漏检
    PiiRule("CN_HOTLINE", re.compile(r"(?<!\d)(?:400|800)[- ]?\d{3}[- ]?\d{4}(?!\d)")),
    PiiRule("CN_LANDLINE", re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")),
    PiiRule("EMPLOYEE_ID", re.compile(r"\bEMP-?\d{4,}\b")),
    PiiRule("INTERNAL_CODE", re.compile(r"\bAIA-[A-Z]{2,}-\d{3,}\b")),
)


def _mask(value: str, kind: str, mode: str) -> str:
    if mode == "hash":
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        return f"[REDACTED:{kind}:{digest}]"
    return f"[REDACTED:{kind}]"


def redact_text(text: str | None, mode: str = "placeholder") -> tuple[str, list[str]]:
    """对文本脱敏，返回 (脱敏后文本, 命中的规则名列表)。"""
    if not text:
        return text or "", []
    hits: list[str] = []
    result = text
    for rule in RULES:
        if rule.pattern.search(result):
            hits.append(rule.name)
            result = rule.pattern.sub(lambda m, r=rule: _mask(m.group(0), r.name, mode), result)
    return result, sorted(set(hits))


def redact_fields(
    payload: dict, fields: tuple[str, ...], mode: str = "placeholder"
) -> tuple[dict, list[str]]:
    """对指定字段做脱敏，用于日志与响应体。"""
    out = dict(payload)
    hits: list[str] = []
    for field in fields:
        value = out.get(field)
        if isinstance(value, str):
            redacted, field_hits = redact_text(value, mode)
            out[field] = redacted
            hits.extend(field_hits)
        elif isinstance(value, list):
            new_list = []
            for item in value:
                if isinstance(item, str):
                    redacted, field_hits = redact_text(item, mode)
                    new_list.append(redacted)
                    hits.extend(field_hits)
                else:
                    new_list.append(item)
            out[field] = new_list
    return out, sorted(set(hits))
