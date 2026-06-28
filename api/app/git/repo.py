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


def commit_all(repo_dir: str, message: str) -> str:
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-q", "-m", message)
    return _git(repo_dir, "rev-parse", "HEAD").strip()


def diff_of_commit(repo_dir: str, sha: str) -> str:
    parents = _git(repo_dir, "rev-list", "--parents", "-n", "1", sha).split()
    base = parents[1] if len(parents) > 1 else EMPTY_TREE
    return _git(repo_dir, "diff", base, sha)
