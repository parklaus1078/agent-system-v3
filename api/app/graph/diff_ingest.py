from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session
from unidiff import PatchSet

from ..models import Node, Edge

# A touched file is a TEST (kind="test", shown in the Tests pane) when it lives under a
# tests/__tests__ dir, or is named test_*.py / *_test.py / *.test.* / *.spec.* — otherwise
# it's a code_region. Matches: tests/test_x.py, __tests__/x.ts, test_x.py, x_test.py,
# Shell.test.tsx, x.spec.ts. Rejects: contests/x.py, detest_thing.py, src/test_helpers/util.py.
_TEST_RE = re.compile(
    r"(^|/)(tests|__tests__)/|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
)


def _is_test_path(path: str) -> bool:
    return bool(_TEST_RE.search(path))


@dataclass(frozen=True)
class TouchedFile:
    path: str
    added: int
    removed: int
    patch: str  # the per-file unified diff (so the review UI can render real content)


def parse_diff(diff_text: str) -> list[TouchedFile]:
    """One TouchedFile per file in a unified diff, sorted by path (deterministic)."""
    patch = PatchSet(diff_text)
    out: list[TouchedFile] = []
    for f in patch:
        path = f.path  # unidiff strips a/ b/; new files use the target path
        out.append(TouchedFile(path=path, added=f.added, removed=f.removed, patch=str(f)))
    return sorted(out, key=lambda t: t.path)


def apply_step_diff(
    db: Session, project_id: str, step_id: str, commit_sha: str, diff_text: str
) -> dict:
    """Upsert code_region nodes (cr:{path}) + touches edges (touch:{step}:{path}),
    keyed so re-applying the same (step, commit, diff) is a no-op in the DB. The
    return is the full set this step's diff maps to (so it is identical on every
    re-apply — idempotent return, used as StepDetail.createdNodeIds/EdgeIds)."""
    node_ids: list[str] = []
    edge_ids: list[str] = []
    for tf in parse_diff(diff_text):
        # A committed test file becomes a `test` node (Tests pane) linked by `tested_by`;
        # everything else is a `code_region` linked by `touches`. Mutually exclusive, so a
        # test file never also shows up in the CodeRegion slice.
        is_test = _is_test_path(tf.path)
        node_id = f"{'test' if is_test else 'cr'}:{tf.path}"
        existing = db.get(Node, node_id)
        if existing is None:
            db.add(
                Node(
                    id=node_id,
                    project_id=project_id,
                    kind="test" if is_test else "code_region",
                    label=tf.path,
                    data={"commit": commit_sha},
                )
            )
        else:
            # a later step touched the same file — keep the latest commit on the node
            existing.data = {**(existing.data or {}), "commit": commit_sha}
        node_ids.append(node_id)
        edge_id = f"{'tested_by' if is_test else 'touch'}:{step_id}:{tf.path}"
        if db.get(Edge, edge_id) is None:
            db.add(
                Edge(
                    id=edge_id,
                    project_id=project_id,
                    src=step_id,
                    dst=node_id,
                    kind="tested_by" if is_test else "touches",
                )
            )
        edge_ids.append(edge_id)
    db.commit()
    return {"createdNodeIds": node_ids, "createdEdgeIds": edge_ids}

