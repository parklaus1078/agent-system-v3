"""Shared LLM transport adapters — the single place that maps a governance {transport, model}
to a concrete client for every LLM-*completion* point (project/ticket-planner, intent-router,
agent-message-gen). The executor is deliberately NOT here: it edits files as an agentic CLI,
which is a different shape than a completion call.

Two families:
  - API transports (anthropic-api / openai-api / local) -> a LangChain chat model
  - CLI transports  (claude-cli / codex-cli)            -> a headless subprocess

All provider SDKs are lazy-imported so simulated mode, tests, and offline runs never need them.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time

logger = logging.getLogger("asv3.llm")

API_TRANSPORTS = ("anthropic-api", "openai-api", "local")
CLI_TRANSPORTS = ("claude-cli", "codex-cli")


def brain_of(transport: str) -> str:
    """The CLI 'brain' for a CLI transport: codex-cli -> codex, else claude."""
    return "codex" if transport == "codex-cli" else "claude"


def make_chat_model(transport: str, model: str):
    """A LangChain chat model for an API transport. `local` points ChatOpenAI at an
    OpenAI-compatible endpoint (ollama / vLLM / LM Studio) via ASV3_LOCAL_BASE_URL."""
    if transport == "anthropic-api":
        from langchain_anthropic import ChatAnthropic  # lazy

        return ChatAnthropic(model=model)
    if transport == "openai-api":
        from langchain_openai import ChatOpenAI  # lazy — reads OPENAI_API_KEY from env

        return ChatOpenAI(model=model)
    if transport == "local":
        from langchain_openai import ChatOpenAI  # lazy

        return ChatOpenAI(
            model=model,
            base_url=os.environ.get("ASV3_LOCAL_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.environ.get("ASV3_LOCAL_API_KEY", "sk-local"),  # local endpoints ignore it
        )
    raise ValueError(f"transport {transport!r} is not an API transport")


def cli_cmd(brain: str, model: str, prompt: str) -> list[str]:
    """The headless CLI invocation for a brain: claude -> Claude Code, codex -> Codex CLI."""
    if brain == "codex":
        return ["codex", "exec", "--model", model, prompt]
    return ["claude", "-p", prompt, "--model", model]


def run_cli(brain: str, model: str, prompt: str, *, what: str) -> str:
    """Spawn a headless CLI and return its stdout; raise RuntimeError on a non-zero exit."""
    cmd = cli_cmd(brain, model, prompt)
    logger.info("%s[%s] spawn: model=%s prompt=%dch", what, brain, model, len(prompt))
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    ms = int((time.monotonic() - t0) * 1000)
    logger.info("%s[%s] exit rc=%d %dms out=%dch", what, brain, proc.returncode, ms, len(proc.stdout or ""))
    if proc.returncode != 0:
        logger.warning("%s[%s] stderr: %s", what, brain, (proc.stderr or "")[-400:])
        raise RuntimeError(f"{brain} {what} failed (exit {proc.returncode}): {(proc.stderr or '')[:300]}")
    return proc.stdout or ""
