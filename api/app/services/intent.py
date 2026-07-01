"""CP3 intent router — classify a human's free-form NL steer into the fixed op vocabulary.

`SimulatedIntentRouter` is rule-based + deterministic (offline/test, the SimulatedPlanner
pattern); `LangChainIntentRouter` routes through an LLM in real mode. Ambiguous input maps to
`clarify` — the router never guesses. The core ops this CP: redirect / constrain / answer /
control (reprioritize/scope are CP4).
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

logger = logging.getLogger("asv3.intent")

OPS = ("redirect", "constrain", "reprioritize", "scope", "answer", "control", "ask", "clarify")

# question / chat markers -> the `ask` op (conversational Q&A) instead of a canned clarify.
_QUESTION = (
    "?", "？", "뭐", "무엇", "어때", "어떻", "어떤", "왜 ", "언제", "어디", "누가", "알려",
    "설명", "상태", "현황", "진행", "얼마", "몇 ", "있어", "있나", "인가", "까요", "나요",
    "what", "why", "how", "status", "explain", "tell me", "which", "when", "where", "who",
)


def is_question(text: str) -> bool:
    t = _norm(text)
    if not re.search(r"\w", t):  # bare punctuation ("???") isn't a real question
        return False
    return t.endswith("?") or t.endswith("？") or any(w in t for w in _QUESTION)


class IntentRouter(Protocol):
    def classify(self, text: str, context: dict) -> dict:  # -> {op, scope, args}
        ...


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def throttle_level(text: str) -> str | None:
    """The autonomy level a control instruction names, or None. A level counts only when it is
    the WHOLE instruction or an explicit dial setting (`auto로`/`자동 모드`/`자동으로`), so an
    incidental substring ('automate the auth flow', '자동 저장으로 바꿔') doesn't flip autonomy."""
    t = _norm(text).strip()

    def dial(*words: str) -> bool:
        return any(t == w or re.search(re.escape(w) + r"\s*(로|으로|모드)", t) for w in words)

    if dial("per-step", "perstep", "매 step", "매 스텝"):
        return "per-step"
    if dial("co-pilot", "copilot", "부조종"):
        return "co-pilot"
    if dial("auto", "자동", "오토"):
        return "auto"
    return None


def redirect_target(text: str) -> str:
    """Best-effort subject of a redirect: the token after use/switch-to/대신, or before Korean 로."""
    m = re.search(r"(?:use|switch to|대신)\s+([^\s,.]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip(" .,'\"")
    m = re.search(r"([^\s,]+)\s*로\b", text)
    if m:
        return m.group(1).strip(" .,'\"")
    return (text or "").strip()[:40]


class SimulatedIntentRouter:
    """Deterministic keyword-rule classifier. Order matters: control > constrain > redirect >
    answer(context) > clarify, so 'don't touch X' isn't misread as a redirect and a plain reply
    only becomes `answer` when a question (blocked step) is actually pending."""

    _CONSTRAIN = (
        "don't touch", "dont touch", "do not touch", "hands off", "건드리지", "손대지",
        "건들지", "고정", "constrain", "pin ",
    )
    _REDIRECT = ("use ", "switch to", "instead", "대신", "바꿔", "로 해", "써", "쓰자", "redirect", "재계획")
    _REPRIORITIZE = ("먼저", "우선순위", "우선", "priority", "prioritize", "reprioritize")
    _SCOPE = ("추가", "add ", "새 티켓", "새 일감", "도 만들", "also add", "scope")
    _PAUSE = ("pause", "멈춰", "정지", "일시정지")
    _RESUME = ("resume", "재개", "이어서", "continue")

    def classify(self, text: str, context: dict) -> dict:
        t = _norm(text)
        if not t:
            return {"op": "clarify", "scope": {}, "args": {}}
        scope = dict(context.get("scope") or {})
        # control
        level = throttle_level(t)
        if level:
            return {"op": "control", "scope": {}, "args": {"action": "throttle", "level": level}}
        if any(k in t for k in self._PAUSE):
            return {"op": "control", "scope": {}, "args": {"action": "pause"}}
        if any(k in t for k in self._RESUME):
            return {"op": "control", "scope": {}, "args": {"action": "resume"}}
        # constrain (before redirect)
        if any(k in t for k in self._CONSTRAIN):
            return {"op": "constrain", "scope": scope, "args": {"text": text}}
        # reprioritize (before redirect: "결제 먼저" is a priority change, not a redirect)
        if any(k in t for k in self._REPRIORITIZE):
            return {"op": "reprioritize", "scope": scope, "args": {"text": text}}
        # scope: emergent new work ("다국어도 추가")
        if any(k in t for k in self._SCOPE):
            return {"op": "scope", "scope": {}, "args": {"text": text}}
        # redirect
        if any(k in t for k in self._REDIRECT) or t.endswith("로"):
            return {"op": "redirect", "scope": scope, "args": {"text": text, "target": redirect_target(text)}}
        # ask: a clear question -> answer it, even mid-block (a plain NON-question reply below is
        # what answers the blocked step, so the two don't collide).
        if is_question(text):
            return {"op": "ask", "scope": {}, "args": {"text": text}}
        # answer: a plain reply while a question (blocked step) is pending
        if context.get("has_blocked"):
            return {"op": "answer", "scope": {"step": context.get("blocked_step")}, "args": {"text": text}}
        return {"op": "clarify", "scope": {}, "args": {}}


_CLASSIFY_PROMPT = (
    "Classify the user's instruction into ONE op for an autonomous coding agent:\n"
    "- redirect: change the plan/approach for a ticket (e.g. 'use Stripe')\n"
    "- constrain: a standing constraint/prohibition (e.g. \"don't touch auth\")\n"
    "- reprioritize: run a ticket sooner (e.g. '결제 먼저')\n"
    "- scope: add a new ticket / emergent work (e.g. '다국어도 추가')\n"
    "- answer: a reply to a pending agent question (only if a question is pending)\n"
    "- control: pause / resume / change autonomy throttle\n"
    "- ask: the user is asking a question about the project or just chatting — answer them "
    "(this is NOT a command; use it for '이 프로젝트 상태 어때?', 'why did you...', greetings)\n"
    "- clarify: ambiguous — cannot tell\n\n"
    "A question is pending: {pending}\n"
    "Instruction: {text}\n"
)


def _intent_result(op: str, target: str, level: str, action: str, text: str, context: dict) -> dict:
    """Assemble the {op, scope, args} result from raw classifier fields (shared by LLM + CLI)."""
    op = op if op in OPS else "clarify"
    args: dict = {"text": text}
    if op == "redirect":
        args["target"] = target or redirect_target(text)
    if op == "control":
        args["action"] = action or ("throttle" if level else "pause")
        if level:
            args["level"] = level
    scope = {"step": context.get("blocked_step")} if op == "answer" else dict(context.get("scope") or {})
    return {"op": op, "scope": scope, "args": args}


class LangChainIntentRouter:
    """Real router over an API transport (anthropic-api / openai-api / local) via LangChain,
    structured output forced to the op vocabulary (lazy import so tests/offline don't need it)."""

    def __init__(self, model: str = "claude-opus-4-8", transport: str = "anthropic-api"):
        from pydantic import BaseModel, Field

        from . import llm  # lazy: provider SDKs optional

        class IntentOut(BaseModel):
            op: str = Field(description="one of: " + ", ".join(OPS))
            target: str = Field(default="", description="redirect subject, if any")
            level: str = Field(default="", description="throttle level for control, if any")
            action: str = Field(default="", description="control action: pause|resume|throttle")

        self._IntentOut = IntentOut
        self._llm = llm.make_chat_model(transport, model).with_structured_output(IntentOut)

    def classify(self, text: str, context: dict) -> dict:
        prompt = _CLASSIFY_PROMPT.format(pending=bool(context.get("has_blocked")), text=text)
        try:
            out = self._llm.invoke(prompt)
        except Exception:  # noqa: BLE001 — never crash a steer on a router error; ask to clarify
            logger.exception("intent LLM failed; clarifying")
            return {"op": "clarify", "scope": {}, "args": {}}
        return _intent_result(out.op, out.target, out.level, out.action, text, context)


class CliIntentRouter:
    """Real router over an agentic CLI (`claude -p` / `codex exec`) — same auth as the CLI
    planners/executor. Prompts for a JSON verdict and parses it; any failure clarifies."""

    def __init__(self, brain: str = "claude", model: str = "claude-opus-4-8"):
        self.brain, self.model = brain, model

    def classify(self, text: str, context: dict) -> dict:
        import json

        from . import llm  # lazy

        prompt = _CLASSIFY_PROMPT.format(pending=bool(context.get("has_blocked")), text=text) + (
            '\nRespond with ONLY a JSON object: {"op","target","level","action"}. No prose.'
        )
        try:
            raw = llm.run_cli(self.brain, self.model, prompt, what="intent")
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            obj = json.loads(m.group(0)) if m else {}
        except Exception:  # noqa: BLE001 — never crash a steer on a router error
            logger.exception("intent CLI failed; clarifying")
            return {"op": "clarify", "scope": {}, "args": {}}
        return _intent_result(
            str(obj.get("op", "")), str(obj.get("target", "")), str(obj.get("level", "")),
            str(obj.get("action", "")), text, context,
        )
