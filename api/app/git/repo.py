from __future__ import annotations

import subprocess

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's well-known empty tree


def _git(repo_dir: str, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def commit_all(repo_dir: str, message: str) -> str | None:
    """Stage + commit everything. Returns the new commit sha, or None when the working
    tree had no changes (the executor made no edits) — so a no-op step degrades to an
    empty review gate instead of crashing the lifecycle on git's 'nothing to commit'."""
    _git(repo_dir, "add", "-A")
    if not _git(repo_dir, "status", "--porcelain").strip():
        return None
    _git(repo_dir, "commit", "-q", "-m", message)
    return _git(repo_dir, "rev-parse", "HEAD").strip()


def diff_of_commit(repo_dir: str, sha: str) -> str:
    parents = _git(repo_dir, "rev-list", "--parents", "-n", "1", sha).split()
    base = parents[1] if len(parents) > 1 else EMPTY_TREE
    return _git(repo_dir, "diff", base, sha)


def head_sha(repo_dir: str) -> str | None:
    """The current HEAD commit sha, or None if the repo has no commits yet."""
    try:
        return _git(repo_dir, "rev-parse", "--verify", "-q", "HEAD").strip() or None
    except subprocess.CalledProcessError:
        return None


def diff_since(repo_dir: str, base: str | None) -> str:
    """Unified diff of everything committed from `base` (exclusive) up to HEAD — regardless of
    WHO committed it (a real CLI executor that commits its own work, OR the lifecycle's
    commit_all). `base=None` diffs from the empty tree (a first commit). This is the robust
    capture: commit_all returning None (clean tree) no longer means 'no change' when the
    executor already committed the step's edits itself."""
    head = head_sha(repo_dir)
    if head is None or head == base:
        return ""
    return _git(repo_dir, "diff", base or EMPTY_TREE, head)
