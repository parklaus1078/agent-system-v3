from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Protocol

logger = logging.getLogger("asv3.executor")


@dataclass
class ExecResult:
    summary: str
    decision: str | None
    ok: bool
    output: str


class Executor(Protocol):
    def run(self, repo_dir: str, prompt: str) -> ExecResult: ...


class SimulatedExecutor:
    """Deterministic: invokes a write callback to mutate the repo, no model used."""

    def __init__(self, write: Callable[[str], None], decision: str | None = None):
        self._write, self._decision = write, decision

    def run(self, repo_dir: str, prompt: str) -> ExecResult:
        self._write(repo_dir)
        return ExecResult(summary="simulated step done", decision=self._decision, ok=True, output="")


class CliExecutor:
    """Real Executor: the agentic CLI edits files in repo_dir (headless, pre-authorized).
    Claude Code: `claude -p <prompt> --permission-mode acceptEdits`; Codex equivalent.
    Flags are the v1 baseline — verify against the installed CLI version."""

    def __init__(
        self, brain: str = "claude", model: str = "claude-opus-4-8", preset: str = "acceptEdits"
    ):
        self.brain, self.model, self.preset = brain, model, preset

    def _cmd(self, prompt: str) -> list[str]:
        if self.brain == "claude":
            return ["claude", "-p", prompt, "--model", self.model, "--permission-mode", self.preset]
        return ["codex", "exec", "--model", self.model, prompt]

    def run(self, repo_dir: str, prompt: str) -> ExecResult:
        cmd = self._cmd(prompt)
        logger.info(
            "executor[%s] spawn: cwd=%s model=%s prompt=%dch (%s -p …)",
            self.brain, repo_dir, self.model, len(prompt), cmd[0],
        )
        t0 = time.monotonic()
        try:
            proc = subprocess.run(  # noqa: S603
                cmd, cwd=repo_dir, capture_output=True, text=True
            )
            ms = int((time.monotonic() - t0) * 1000)
            logger.info("executor[%s] exit: rc=%d %dms", self.brain, proc.returncode, ms)
            if proc.returncode != 0:
                logger.warning("executor[%s] stderr: %s", self.brain, (proc.stderr or "")[-400:])
            return ExecResult(
                summary=(proc.stdout or "").strip()[:500],
                decision=None,
                ok=proc.returncode == 0,
                output=proc.stdout + proc.stderr,
            )
        except FileNotFoundError as exc:
            logger.error("executor[%s] CLI not found (%s) — is it on PATH?", self.brain, exc)
            return ExecResult(summary="", decision=None, ok=False, output=str(exc))
