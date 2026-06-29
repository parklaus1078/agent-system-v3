import subprocess
from pathlib import Path

from app.services.executor import SimulatedExecutor


def test_simulated_executor_writes_and_reports(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    def write(repo: str):
        Path(repo, "result.ts").write_text("export const ok = true;\n")

    res = SimulatedExecutor(write).run(str(tmp_path), prompt="anything")
    assert res.ok and (tmp_path / "result.ts").exists()
