"""多轮查询改写。

两种策略：
  rules —— 把上一轮问题拼接进当前追问（无依赖，离线可用，但会产出畸形复合问句）
  llm   —— 用模型把追问改写成可独立检索与作答的完整问题（推荐，需 API Key）

为什么需要 LLM 改写：评测发现追问轮次的合规率显著低于首问轮次，
根因是把"还有呢？"这类追问直接拼接成"还有呢？ 员工每年有多少天年假？"，
检索与生成都拿这个畸形问句当输入，模型容易答错或拒答。
正确做法是把追问还原成完整问句（conversational query rewriting）。
"""

from __future__ import annotations

import os
import re

import httpx

from .config import Config

REWRITE_SYSTEM = (
    "You rewrite a user's follow-up question into ONE standalone question for a knowledge-base "
    "search, resolving pronouns and omitted context using the conversation history.\n"
    "Rules:\n"
    "- Output ONLY the rewritten question, no explanation, no quotes, no markdown.\n"
    "- Keep the same language as the follow-up question.\n"
    "- The rewritten question MUST be fully understandable on its own, without the history.\n"
    "- Resolve pronouns and references ('it', 'that', 'this policy', '那它', '该规定') using the history.\n"
    "- A follow-up that carries no topic of its own (e.g. 'And what else?', 'Tell me more', "
    "'Any other details?', '还有呢？', '继续') MUST be rewritten so that it explicitly names the "
    "topic discussed in the previous turns. Never return such a question unchanged.\n"
    "- The history may be in a different language than the follow-up; still use it to resolve context.\n"
    "- Only return the follow-up unchanged if it already names its own topic.\n"
    "- Keep the rewrite MINIMAL: resolve references only. Do not add requirements, "
    "constraints or assumptions that the user did not ask for.\n"
    "- Never answer the question."
)

# 指代：必须依赖上文才能理解
_ANAPHORA = re.compile(
    r"\b(it|its|that|this|these|those|they|them|the same)\b"
    r"|它|其|该|此|这|那|上述|同上",
    re.IGNORECASE,
)
# 无主题追问：本身不携带任何话题，必须用上文补全
_TOPICLESS = re.compile(
    r"^(还有呢|还有什么|还有别的|继续说|继续|展开说|详细说|再讲讲)"
    r"|^(and what else|what else|anything else|tell me more|more details|go on|continue)\b",
    re.IGNORECASE,
)


def needs_resolution(question: str) -> bool:
    """追问是否依赖上下文才能理解。

    注意：**不能只用"问句短"作为判据**。实测这样做会把
    "差旅报销需要在多久内提交？"这类独立的新话题问题误判为追问，
    再叠加确定性兜底后，它被替换成上一轮的问题，直接答错话题。
    因此只认两类明确信号：指代词，以及本身不含话题的追问。
    """
    stripped = question.strip()
    return bool(_ANAPHORA.search(stripped)) or bool(_TOPICLESS.search(stripped))


class LLMQueryRewriter:
    name = "llm"

    def __init__(self, config: Config) -> None:
        generation = config.generation
        self.model = generation.model
        self.base_url = (generation.base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.environ.get(generation.api_key_env, "")
        if not self.api_key:
            raise RuntimeError(f"环境变量 {generation.api_key_env} 未设置")
        self.timeout = generation.timeout_seconds
        self.max_tokens_field = generation.max_tokens_field

    def rewrite(self, question: str, history: list[dict]) -> str:
        if not history:
            return question
        result = self._call(question, history)
        if result != question.strip() or not needs_resolution(question):
            return result
        # 模型原样返回了一个依赖上下文的追问：重试一次更严格的指令，
        # 仍失败则用上一轮问题作为独立问句（"还有呢？"本质上就是"再讲讲同一话题"）。
        retry = self._call(question, history, strict=True)
        if retry != question.strip():
            return retry
        # 兜底：用上一轮问题补全主题（仅在问题确实依赖上下文时才会走到这里）
        previous = (history[-1].get("question") or "").strip()
        return f"{previous} {question}".strip() if previous else question

    def _call(self, question: str, history: list[dict], strict: bool = False) -> str:
        recent = history[-3:]
        transcript = "\n".join(
            f"Q: {turn.get('question','')}\nA: {turn.get('answer','')[:160]}" for turn in recent
        )
        extra = (
            "\n\nYour previous attempt returned the follow-up unchanged, which is NOT allowed "
            "because it depends on the conversation. Replace every pronoun/reference with the "
            "explicit topic and output a self-contained question."
            if strict
            else ""
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": REWRITE_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Conversation so far:\n{transcript}\n\n"
                        f"Follow-up question: {question}\n\n"
                        "Rewrite it into one standalone question (same language as the follow-up)."
                        f"{extra}"
                    ),
                },
            ],
            "temperature": 0,
            self.max_tokens_field: 200,
        }
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"rewrite API {response.status_code}: {response.text[:200]}")
        content = (response.json()["choices"][0]["message"]["content"] or "").strip()
        content = re.sub(r"^```[a-z]*\n|\n```$", "", content).strip().strip('"').strip()
        # 防御：模型有时会返回"重写后的问句：xxx"这类前缀
        content = re.sub(r"^(重写后的问题|改写后的问题|Standalone question|Rewritten question)\s*[:：]\s*", "", content)
        return content.split("\n")[0].strip() or question


def get_rewriter(config: Config):
    """按配置构造改写器，失败时返回 None（调用方回退到规则改写）。"""
    if config.retrieval.conversation_rewrite != "llm":
        return None
    try:
        return LLMQueryRewriter(config)
    except Exception as exc:  # pragma: no cover - 取决于环境
        print(f"[warn] LLM 改写不可用（{exc}），回退到规则改写")
        return None
