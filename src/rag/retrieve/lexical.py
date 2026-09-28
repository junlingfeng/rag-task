"""词法检索（BM25）与中文分词。

中文没有空格，直接按空格切词会让 BM25 完全失效，因此这里用字符二元组
处理 CJK，用词处理拉丁字母——这是 hybrid 检索在中文场景能成立的前提。
"""

from __future__ import annotations

import math
import re
from collections import Counter

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_LATIN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    tokens: list[str] = []
    for block in _CJK.findall(lowered):
        if len(block) == 1:
            tokens.append(block)
        else:
            tokens.extend(block[i : i + 2] for i in range(len(block) - 1))
    tokens.extend(_LATIN.findall(lowered))
    return tokens


class BM25:
    """标准 BM25（k1=1.5, b=0.75）。"""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.tokenized = [tokenize(doc) for doc in documents]
        self.lengths = [len(tokens) for tokens in self.tokenized]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        self.term_freqs = [Counter(tokens) for tokens in self.tokenized]
        self.doc_freq: Counter[str] = Counter()
        for tokens in self.tokenized:
            self.doc_freq.update(set(tokens))
        self.total_docs = len(self.tokenized)

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        return math.log(1 + (self.total_docs - df + 0.5) / (df + 0.5))

    def idf(self, term: str) -> float:
        """对外暴露 IDF，供生成器做加权句子选择。"""
        return self._idf(term)

    def scores(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        results = [0.0] * self.total_docs
        if not query_terms:
            return results
        for index in range(self.total_docs):
            frequency = self.term_freqs[index]
            length = self.lengths[index] or 1
            score = 0.0
            for term in query_terms:
                tf = frequency.get(term, 0)
                if not tf:
                    continue
                denominator = tf + self.k1 * (1 - self.b + self.b * length / (self.avg_length or 1))
                score += self._idf(term) * tf * (self.k1 + 1) / denominator
            results[index] = score
        return results
