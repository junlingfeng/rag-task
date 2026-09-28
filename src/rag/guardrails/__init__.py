"""护栏：prompt 注入检测、拒答判定、答案接地校验。"""

from __future__ import annotations

import re

from ..retrieve.lexical import tokenize
from ..types import Retrieved

# 内容词停用表：这些词在判断"问题是否被知识库覆盖"时没有区分度
_STOP = {
    "的", "了", "是", "在", "和", "与", "或", "有", "多少", "什么", "如何", "怎么", "几",
    "请问", "吗", "呢", "可以", "需要", "多久", "哪些", "哪个", "标准", "规定", "要求",
    "the", "a", "an", "is", "are", "of", "to", "for", "and", "or", "how", "many", "what",
    "which", "do", "does", "much", "long", "can", "i", "my", "we", "it",
}
_CITATION = re.compile(r"\[\d+\]")


def _unigrams(text: str) -> list[str]:
    """中文单字 + 英文词，作为二元组信号之外的第二判据。"""
    from ..retrieve.lexical import _CJK, _LATIN

    cjk_chars = [char for block in _CJK.findall(text) for char in block]
    latin_words = [word for word in _LATIN.findall(text.lower()) if len(word) > 2]
    return cjk_chars + latin_words

INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_instructions", re.compile(r"(忽略|无视|忘记).{0,8}(以上|上述|之前|所有).{0,6}(指令|要求|规则)", re.I)),
    ("ignore_instructions_en", re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|prompts)", re.I)),
    ("system_prompt", re.compile(r"(系统提示词|系统提示|system\s*prompt|你的设定|your\s+(instructions|system\s*prompt))", re.I)),
    (
        "role_override",
        re.compile(
            r"(你现在是|从现在起你是|\bDAN\b|unrestricted\s+(assistant|model)|"
            r"act\s+as\s+an?\s+(unrestricted|administrator)|jailbreak|ignore\s+all\s+safety)",
            re.I,
        ),
    ),
    (
        "reveal_secret",
        re.compile(
            r"(输出|告诉我|打印|泄露|reveal|show|print|tell\s+me).{0,12}"
            r"(密钥|密码|token|api[_\s-]?key|secret|credential)",
            re.I,
        ),
    ),
    (
        "exfiltrate",
        re.compile(
            r"(导出|下载|dump|export|give\s+me|list)\s*(全部|所有|all)?\s*.{0,12}"
            r"(数据|记录|明细|薪资|salary|records|id\s+numbers?|personal\s+data)",
            re.I,
        ),
    ),
    (
        "disallowed_action",
        re.compile(
            r"((如何|怎么|帮我|请).{0,8}(销毁|删除|篡改|绕过|规避).{0,8}(审计|记录|日志|凭证|审查|审核|合规)|"
            r"(绕过|规避).{0,4}(合规|审查|审核|风控)|"
            r"(tamper\s+with|delete|destroy|bypass|circumvent).{0,16}(audit|log|record|compliance|review))",
            re.I,
        ),
    ),
    ("unauthorized_identity", re.compile(r"(以管理员身份|其他员工的身份证|other\s+employees?['’]?\s*id)", re.I)),
)

REFUSAL_TEMPLATES: dict[str, dict[str, str]] = {
    "low_confidence": {
        "zh": "知识库中没有找到足够支撑该问题的证据，因此无法给出确定回答。建议补充问题的上下文（例如具体的制度名称或文档编号），我可以据此重新检索。",
        "en": "The knowledge base does not contain enough evidence to answer this reliably. Please add context such as the policy name or document id, and I will search again.",
    },
    "out_of_scope": {
        "zh": "该问题超出了当前知识库的覆盖范围（员工手册、合规指南、技术规范、架构文档）。建议联系相应的业务负责人，或提供更具体的内部文档名称。",
        "en": "This question falls outside the current knowledge base scope (handbook, compliance guides, technical specifications, architecture documents). Please contact the relevant owner or provide a specific internal document.",
    },
    "safety": {
        "zh": "该请求触发了安全策略，无法执行。如需查询合规流程或举报渠道，请参考合规指南中的对应章节。",
        "en": "This request triggered a safety policy and cannot be fulfilled. For compliance processes or reporting channels, please refer to the relevant section of the compliance guide.",
    },
    "no_evidence": {
        "zh": "检索到的内容不足以支撑一个可靠回答，因此不予作答。建议换一种问法或缩小问题范围。",
        "en": "The retrieved content is not sufficient to support a reliable answer. Please rephrase the question or narrow its scope.",
    },
}


def detect_injection(query: str) -> list[str]:
    return [name for name, pattern in INJECTION_PATTERNS if pattern.search(query)]


class ScopeDetector:
    """越界判定器（离线词法实现）。

    设计约束：越界判定必须独立于检索配置，否则"换检索策略"会同时改变
    判定松紧，三配置对比就不再是单一变量实验。因此这里直接在全库上计算
    词法信号，与 vector/hybrid 无关。

    三个信号：
      coverage    = 内容词（中文二元组）在最佳匹配 chunk 中的覆盖率
      oov         = 内容词二元组在全库词表中的未登录比例
      oov_unigram = 内容词单字/英文词的未登录比例（对措辞差异更鲁棒）

    判定规则：coverage < coverage_min，或两个 OOV 信号同时越界 → 越界。
    要求两个 OOV 信号同时越界，是为了降低误拒答：中文二元组对措辞极其敏感，
    只用二元组会把"合规举报的渠道有哪些"这类完全正常的问题判成越界。
    阈值由 scripts/calibrate_scope.py 在标注集上标定。

    **已知局限**：纯词法信号无法处理"换一种说法问同一件事"的情况。
    实测平衡准确率约 0.80（见 reports/diagnosis_*.md），
    进一步提升需要切到语义判据（真实 embedding 或 LLM 范围判定），
    对应配置项见 guardrails.scope_check_backend。
    """

    def __init__(
        self,
        chunks,
        bm25,
        coverage_min: float = 0.15,
        oov_max: float = 0.65,
        oov_unigram_max: float = 0.40,
    ) -> None:
        self.bm25 = bm25
        self.coverage_min = coverage_min
        self.oov_max = oov_max
        self.oov_unigram_max = oov_unigram_max
        self.chunk_tokens = [set(tokenize(chunk.text)) for chunk in chunks]
        self.doc_freq: dict[str, int] = {}
        for tokens in self.chunk_tokens:
            for token in tokens:
                self.doc_freq[token] = self.doc_freq.get(token, 0) + 1
        self.chunk_unigrams = [set(_unigrams(chunk.text)) for chunk in chunks]
        self.unigram_freq: dict[str, int] = {}
        for tokens in self.chunk_unigrams:
            for token in tokens:
                self.unigram_freq[token] = self.unigram_freq.get(token, 0) + 1

    def content_terms(self, query: str) -> list[str]:
        return [t for t in tokenize(query) if t not in _STOP]

    def evaluate(self, query: str) -> dict:
        terms = self.content_terms(query)
        if not terms:
            return {"coverage": 0.0, "oov": 1.0, "oov_unigram": 1.0, "out_of_scope": True, "terms": 0}
        term_set = set(terms)
        scores = self.bm25.scores(query)
        best = max(range(len(scores)), key=lambda i: scores[i]) if scores else None
        coverage = (
            len(term_set & self.chunk_tokens[best]) / len(term_set) if best is not None else 0.0
        )
        oov = sum(1 for term in terms if self.doc_freq.get(term, 0) == 0) / len(terms)
        unigrams = [t for t in _unigrams(query) if t not in _STOP]
        oov_unigram = (
            sum(1 for t in unigrams if self.unigram_freq.get(t, 0) == 0) / len(unigrams)
            if unigrams
            else 1.0
        )
        return {
            "coverage": round(coverage, 4),
            "oov": round(oov, 4),
            "oov_unigram": round(oov_unigram, 4),
            "out_of_scope": coverage < self.coverage_min
            or (oov > self.oov_max and oov_unigram > self.oov_unigram_max),
            "terms": len(terms),
        }


def support_score(answer: str, contexts: list[Retrieved], threshold: float = 0.45) -> float:
    """答案接地校验：被证据支撑的句子占比。

    判定方式为词元覆盖率 + 原文片段包含，属于可复现的轻量实现；
    报告中需说明其局限（不能识别语义等价但用词不同的表述）。
    """
    from ..generate import _split_sentences  # 复用同一套句子切分

    # 引用标记是元数据而不是断言，必须先剥离，否则会破坏原文包含判定
    cleaned = _CITATION.sub("", answer)
    sentences = _split_sentences(cleaned)
    if not sentences:
        return 0.0
    context_tokens = [set(tokenize(c.chunk.text + " " + (c.chunk.parent_text or ""))) for c in contexts]
    supported = 0
    for sentence in sentences:
        tokens = set(tokenize(sentence))
        if not tokens:
            continue
        best = 0.0
        compact = re.sub(r"\s+", "", sentence)
        for index, context in enumerate(contexts):
            ratio = len(tokens & context_tokens[index]) / len(tokens)
            if compact and compact in re.sub(r"\s+", "", context.chunk.text):
                ratio = 1.0
            best = max(best, ratio)
        if best >= threshold:
            supported += 1
    return supported / len(sentences)


_NUM = re.compile(r"\d+(?:\.\d+)?")
# 列表序号（"1."、"2、"、"3)"）不是断言中的数值，必须在数字一致性检查前剔除，
# 否则真实模型输出的编号列表会被误判为"编造数值"而整条回答被拒。
_ENUM = re.compile(r"(?m)^\s*\d+\s*[.、)）]\s*")


def grounding_check(
    answer: str,
    contexts: list[Retrieved],
    min_support: float = 0.30,
    min_cited_ratio: float = 0.5,
) -> tuple[float, bool]:
    """接地判定：返回 (support_score, 是否可信)。

    为什么不能只用 support_score：词面覆盖率会惩罚"合法改写"。
    离线抽取式生成器输出的句子是原文子串，覆盖率天然为 1；
    真实模型会改写（"员工每年享有 15 天年假" vs "每个自然年度享有 15 个工作日带薪年假"），
    覆盖率可能只有 0.4，但答案完全正确。若仍按 0.30 硬判定，会产生大量误拒答。

    因此改为"数字一致性 + 引用覆盖"的组合判据：
      1) 答案中的所有数字必须能在检索上下文里找到（防止编造数值，这是最危险的幻觉）；
      2) 且满足以下任一：词面覆盖达标，或过半数句子带引用标记。
    """
    from ..generate import _split_sentences  # 复用同一套句子切分

    cleaned = _CITATION.sub("", answer)
    cleaned = _ENUM.sub("", cleaned)
    sentences = _split_sentences(cleaned)
    if not sentences:
        return 0.0, False
    support = support_score(answer, contexts)

    answer_numbers = set(_NUM.findall(cleaned))
    context_text = " ".join(
        (c.chunk.parent_text or "") + " " + c.chunk.text for c in contexts
    )
    context_numbers = set(_NUM.findall(context_text))
    numeric_ok = answer_numbers.issubset(context_numbers)

    cited = sum(1 for s in answer.split("。") if _CITATION.search(s))
    cited_ratio = cited / max(1, len(answer.split("。")))
    grounded = numeric_ok and (support >= min_support or cited_ratio >= min_cited_ratio)
    return support, grounded


def refusal_answer(reason: str, question: str) -> str:
    is_chinese = len(re.findall(r"[\u4e00-\u9fff]", question)) >= len(re.findall(r"[A-Za-z]", question))
    language = "zh" if is_chinese else "en"
    return REFUSAL_TEMPLATES.get(reason, REFUSAL_TEMPLATES["no_evidence"])[language]


# 模型"自拒答"识别：真实模型在证据不足时会主动说"资料里没有"。
# 如果管线不识别这种回答，它会被计为"已作答"，拒答率与合规率同时失真
# （实测：关掉词法门后正确应答率 1.0，但正确拒答率 0.0 就是这个问题）。
SELF_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(无法|不能|难以).{0,6}(回答|确定|给出|判断)"),
    re.compile(r"(资料|上下文|知识库|文档|证据)(中|里)?(没有|未|不含|不包含|并不包含).{0,12}(信息|内容|规定|说明|提及|条款)"),
    re.compile(r"(未|没有).{0,6}(提及|包含|说明|提供).{0,8}(相关|该|此)?"),
    re.compile(r"(cannot|can not|unable to|not able to)\s+(answer|determine|provide|find)", re.I),
    re.compile(r"(does not|doesn't|do not|don't)\s+(contain|mention|include|provide|cover)", re.I),
    re.compile(r"no\s+(information|evidence|mention|reference)\s+(about|on|regarding|in)", re.I),
    re.compile(r"(not|isn't|is not)\s+(mentioned|specified|covered|available|present)\s+in", re.I),
)


def looks_like_self_refusal(answer: str) -> bool:
    """判断模型输出是否为"证据不足、无法作答"性质的回答。"""
    if not answer:
        return True
    head = answer[:400]
    return any(pattern.search(head) for pattern in SELF_REFUSAL_PATTERNS)
