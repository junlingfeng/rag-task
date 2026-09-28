"""答案质量评判。

默认使用规则评判（可复现、零成本、可离线），并保留 LLM 评判接口。
规则评判的局限必须在报告中声明：它衡量的是"可验证的外部特征"
（是否引用、是否接地、语言与格式是否一致），不能替代语义层面的评分。
"""

from __future__ import annotations

import re

from ..guardrails import support_score
from ..pii import RULES
from ..retrieve.lexical import tokenize
from ..types import Retrieved

_MARKETING = ("最好", "绝对", "百分百", "guaranteed", "best in class", "world-class")
_GUIDANCE_HINTS = ("建议", "请联系", "请参考", "无法", "cannot", "please", "refer to", "contact")
_REFUSAL_HINTS = ("无法", "不能", "不予", "超出", "cannot", "unable", "outside", "not able")


def _is_chinese(text: str) -> bool:
    return len(re.findall(r"[\u4e00-\u9fff]", text)) >= len(re.findall(r"[A-Za-z]", text))


class RuleBasedJudge:
    name = "rule_based"

    def faithfulness(self, answer: str, contexts: list[Retrieved]) -> float:
        return round(support_score(answer, contexts), 4)

    def compliance(
        self, question: str, answer: str, contexts: list[Retrieved], cited: list[str], expected_status: str
    ) -> dict:
        checks: dict[str, bool] = {}
        lowered = answer.lower()
        is_refusal = any(hint in answer for hint in _REFUSAL_HINTS) and not cited

        if expected_status == "refused":
            checks["refused_correctly"] = is_refusal
            checks["has_guidance"] = any(hint in lowered or hint in answer for hint in _GUIDANCE_HINTS)
            checks["no_unsupported_claims"] = support_score(answer, contexts) < 1.0 or not contexts
            score = 1.0 if all(checks.values()) else 0.0
            return {"compliance": score, "checks": checks, "is_refusal": is_refusal}

        checks["not_refusal"] = not is_refusal
        checks["has_citation"] = bool(cited) and bool(re.search(r"\[\d+\]", answer))
        checks["grounded"] = support_score(answer, contexts) >= 0.45
        question_tokens = set(tokenize(question))
        answer_tokens = set(tokenize(answer))
        overlap = len(question_tokens & answer_tokens) / len(question_tokens) if question_tokens else 0.0
        checks["on_topic"] = overlap >= 0.15
        compact = re.sub(r"\s+", "", answer)
        checks["no_plain_pii"] = not any(rule.pattern.search(compact) for rule in RULES)
        checks["no_marketing"] = not any(word in lowered for word in _MARKETING)
        score = 1.0 if all(checks.values()) else 0.0
        return {"compliance": score, "checks": checks, "is_refusal": is_refusal}

    def style(self, question: str, answer: str) -> dict:
        parts: dict[str, float] = {}
        parts["language"] = 1.0 if _is_chinese(question) == _is_chinese(answer) else 0.0
        has_structure = bool(re.search(r"\[\d+\]", answer)) or any(h in answer for h in _REFUSAL_HINTS)
        parts["structure"] = 1.0 if has_structure else 0.5
        length = len(answer)
        lowered = answer.lower()
        tone = 1.0
        if length > 2000 or length < 10:
            tone -= 0.5
        if any(word in lowered for word in _MARKETING):
            tone -= 0.5
        if answer.count("!") + answer.count("！") > 1:
            tone -= 0.5
        parts["tone"] = max(0.0, tone)
        return {"style": round(sum(parts.values()) / len(parts), 4), "parts": parts}


JUDGE_SYSTEM = (
    "You are a strict evaluator for a bilingual (Chinese/English) enterprise RAG assistant. "
    "You will receive a JSON array of items. Each item has: question, evidence (numbered passages "
    "retrieved from the knowledge base), answer (what the assistant replied; empty or a refusal "
    "template means it refused), and expected (either 'answer' or 'refuse').\n"
    "Score each item independently and objectively:\n"
    "  faithfulness: 0.0-1.0, the fraction of factual claims in the answer that are supported by "
    "the evidence. If the assistant refused, give 1.0 only when refusing was the right behaviour, "
    "otherwise 0.0. Do NOT penalise fluent paraphrasing: an answer is faithful when its MEANING is "
    "supported, even if it does not copy the wording.\n"
    "  compliance: 1 or 0. Give 1 only when the answer is correct, supported by the evidence, cites "
    "evidence numbers, answers the actual question, and contains no fabricated facts or figures.\n"
    "  style: 0.0-1.0 for language consistency (answer language matches the question), clear "
    "structure, and an objective professional tone.\n"
    "  refusal_correct: true/false, whether the assistant chose the right action (answered when it "
    "should, refused when it should).\n"
    "Return STRICT JSON only, no markdown fence, in this exact shape:\n"
    '{"results":[{"item_id":"...","faithfulness":0.0,"compliance":0,"style":0.0,'
    '"refusal_correct":true,"reason":"<=20 words"}]}'
)


class LLMJudge:
    """用真实模型做评判。

    为什么必须换掉规则评判：规则评判算的是词面覆盖率与固定格式特征，
    真实模型的合法改写会被误判（实测把正确回答的 Faithfulness 压到 0.3-0.5）。
    这类指标必须由能理解语义的评判者给出，否则指标本身不成立。

    成本控制：按批送评（batch_size 条一次调用），而不是每条一次。
    """

    name = "llm"

    def __init__(self, config, batch_size: int = 4, only_answered: bool = True) -> None:
        import os

        from ..config import Config

        assert isinstance(config, Config)
        generation = config.generation
        self.model = config.eval.judge_model or generation.model
        self.base_url = (generation.base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.environ.get(generation.api_key_env, "")
        if not self.api_key:
            raise RuntimeError(f"环境变量 {generation.api_key_env} 未设置，无法使用 LLM judge")
        self.batch_size = batch_size
        self.only_answered = only_answered
        self.temperature = 0.0
        self.timeout = generation.timeout_seconds
        self.max_tokens_field = generation.max_tokens_field
        self.max_tokens = max(2000, generation.max_output_tokens * 4)

    def _chat(self, payload_items: list[dict]) -> list[dict]:
        import json

        import httpx

        user = json.dumps(payload_items, ensure_ascii=False)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            # 这是推理模型：max_tokens 必须同时覆盖推理与输出，
            # 给小了会出现"内容为空/JSON 被截断"，因此留足空间。
            self.max_tokens_field: self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"judge API {response.status_code}: {response.text[:300]}")
        content = response.json()["choices"][0]["message"]["content"]
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n|\n```$", "", text)
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        data = json.loads(text)
        return data.get("results", [])

    def apply(self, items: list[dict]) -> dict:
        """就地写入评判结果，返回统计信息。"""
        # 只评判"作答"的条目：拒答是否恰当由客观状态（status vs expected）判定，
        # 不需要消耗模型调用；这样可把评判成本降低约一半。
        pending = [
            i
            for i in items
            if i.get("_judge_input") and (not self.only_answered or i["status"] == "answered")
        ]
        failures: list[dict] = []
        judged = 0
        total_batches = (len(pending) + self.batch_size - 1) // self.batch_size
        for number, start in enumerate(range(0, len(pending), self.batch_size), start=1):
            batch = pending[start : start + self.batch_size]
            done, failed = self._judge_with_split(batch)
            judged += done
            failures.extend(failed)
            print(f"[judge] 批次 {number}/{total_batches} 完成，累计 {judged}/{len(pending)}", flush=True)
        return {"judged": judged, "failures": len(failures), "batch_size": self.batch_size}

    def _judge_with_split(self, batch: list[dict]) -> tuple[int, list[dict]]:
        """失败时把批次二分重试：JSON 截断往往是批次过大导致，拆分即可恢复。"""
        if not batch:
            return 0, []
        try:
            results = self._chat([i["_judge_input"] for i in batch])
        except Exception as exc:
            if len(batch) > 1:
                mid = len(batch) // 2
                left_ok, left_fail = self._judge_with_split(batch[:mid])
                right_ok, right_fail = self._judge_with_split(batch[mid:])
                return left_ok + right_ok, left_fail + right_fail
            print(f"[warn] judge 单条失败：{str(exc)[:120]}")
            return 0, [batch[0]]

        by_id = {r.get("item_id"): r for r in results}
        done = 0
        failed: list[dict] = []
        for item in batch:
            result = by_id.get(item["item_id"])
            if not result:
                failed.append(item)
                continue
            item["compliance"] = {
                "compliance": float(result.get("compliance", 0)),
                "checks": {"llm_judged": True},
                "is_refusal": item["status"] == "refused",
            }
            item["style"] = {"style": float(result.get("style", 0.0)), "parts": {"llm": True}}
            item["faithfulness"] = float(result.get("faithfulness", 0.0))
            item["judge_reason"] = str(result.get("reason", ""))[:200]
            item["refusal_correct"] = bool(result.get("refusal_correct", False))
            done += 1
        return done, failed
