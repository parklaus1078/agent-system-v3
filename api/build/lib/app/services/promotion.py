from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node


def _wiki_dir(wiki_root: str | None) -> Path:
    root = wiki_root or os.getenv("ASV3_LLM_WIKI_ROOT", "/home/kay/llm_wiki")
    d = Path(root) / "kay_second_brain" / "wiki" / "decisions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def promote_project(db: Session, project_id: str, memory, wiki_root: str | None = None) -> list[str]:
    """On project completion, distill each Decision into the personal ~/llm_wiki and
    index it so future projects recall it. Idempotent: one file per node (overwrite)."""
    d = _wiki_dir(wiki_root)
    written: list[str] = []
    decisions = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "decision")
    ).all()
    for node in decisions:
        path = d / f"asv3-{project_id}-{node.id}.md"
        path.write_text(
            f"---\ntype: decision\nsource: agent-system-v3\nproject: {project_id}\n"
            f"node_id: {node.id}\n---\n\n# Decision\n\n{node.label}\n",
            encoding="utf-8",
        )
        memory.index_text(
            node.label,
            {
                "wiki_path": str(path),
                "node_id": node.id,
                "kind": "decision",
                "project_id": project_id,
            },
        )
        written.append(str(path))
    return written
