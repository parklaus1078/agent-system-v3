"""agent-message-gen point — rewrite the deterministic channel template in a warmer, clearer
voice via the configured engine. Simulated (the default) and ANY error return the template
unchanged, so tests, offline runs, and the worker hot path stay deterministic and never break
because of message styling."""

from __future__ import annotations

import logging

logger = logging.getLogger("asv3.msggen")

_PROMPT = (
    "Rewrite this developer-tool notification in natural, concise Korean. Keep the SAME meaning, "
    "any quoted '이름', and any 승인/수정요청/인수 options. Return ONLY the rewritten line — no "
    "preamble, no markdown.\n\n{text}"
)


def naturalize(engine: dict | None, base_text: str) -> str:
    """Return `base_text` rewritten via the engine, or `base_text` unchanged for simulated / on
    any failure. `engine` is a governance {transport, model} spec (see resolve_engine)."""
    transport = (engine or {}).get("transport")
    if not transport or transport == "simulated" or not base_text.strip():
        return base_text
    model = (engine or {}).get("model") or "claude-opus-4-8"
    prompt = _PROMPT.format(text=base_text)
    try:
        from . import llm  # lazy

        if transport in llm.API_TRANSPORTS:
            out = llm.make_chat_model(transport, model).invoke(prompt)
            content = getattr(out, "content", out)
            text = content if isinstance(content, str) else str(content)
        else:  # claude-cli / codex-cli
            text = llm.run_cli(llm.brain_of(transport), model, prompt, what="msggen")
        return text.strip() or base_text
    except Exception:  # noqa: BLE001 — message styling must never break the lifecycle
        logger.exception("message-gen (%s) failed; using the template", transport)
        return base_text
