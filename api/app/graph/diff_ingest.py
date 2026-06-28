from __future__ import annotations

from dataclasses import dataclass

from unidiff import PatchSet


@dataclass(frozen=True)
class TouchedFile:
    path: str
    added: int
    removed: int


def parse_diff(diff_text: str) -> list[TouchedFile]:
    """One TouchedFile per file in a unified diff, sorted by path (deterministic)."""
    patch = PatchSet(diff_text)
    out: list[TouchedFile] = []
    for f in patch:
        path = f.path  # unidiff strips a/ b/; new files use the target path
        out.append(TouchedFile(path=path, added=f.added, removed=f.removed))
    return sorted(out, key=lambda t: t.path)
