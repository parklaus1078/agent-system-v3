import subprocess
from pathlib import Path

from app.git.repo import commit_all, diff_of_commit


def _init(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def test_commit_and_diff(tmp_path):
    repo = _init(tmp_path)
    (repo / "a.txt").write_text("hello\n")
    sha = commit_all(str(repo), "first")
    assert len(sha) >= 7
    d = diff_of_commit(str(repo), sha)
    assert "a.txt" in d and "+hello" in d
