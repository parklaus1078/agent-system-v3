from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session
from unidiff import PatchSet

from ..models import Node, Edge


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
        node_id = f"cr:{tf.path}"
        existing = db.get(Node, node_id)
        if existing is None:
            db.add(
                Node(
                    id=node_id,
                    project_id=project_id,
                    kind="code_region",
                    label=tf.path,
                    data={"commit": commit_sha},
                )
            )
        else:
            # a later step touched the same file — keep the latest commit on the node
            existing.data = {**(existing.data or {}), "commit": commit_sha}
        node_ids.append(node_id)
        edge_id = f"touch:{step_id}:{tf.path}"
        if db.get(Edge, edge_id) is None:
            db.add(
                Edge(id=edge_id, project_id=project_id, src=step_id, dst=node_id, kind="touches")
            )
        edge_ids.append(edge_id)
    db.commit()
    return {"createdNodeIds": node_ids, "createdEdgeIds": edge_ids}

