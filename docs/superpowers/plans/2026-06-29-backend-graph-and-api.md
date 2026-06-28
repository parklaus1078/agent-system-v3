# Backend: Work Graph + diff→map + API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use Karpathy-skill to think about how to write the actual codes.

**Goal:** Build the backend that stores the per-project **work graph** relationally, ingests **git diffs into graph edges** (the map's source of truth), and serves the exact API contract the frontend's `ApiClient` expects — so the frontend swaps `MockApiClient` → `HttpApiClient` with no UI change.

**Architecture:** FastAPI + SQLAlchemy 2. Graph = two tables (`nodes`, `edges`) with portable column types so tests run on SQLite while deployment is Postgres (pgvector is added in Plan 4, unused here). A pure `diff_ingest` module turns a unified diff into `CodeRegion` upserts + `touches` edges, **idempotently** (same commit → same edges). A `git/repo.py` wraps the *target project* repo (commit per step, diff of a commit). Routers expose `GET /graph`, `GET /steps/{id}`, `GET /owning-path/{nodeId}` returning the frontend DTOs. **No LangGraph / executor / RAG here** (Plans 3–4).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, `unidiff` (diff parsing), stdlib `subprocess` (git). Deployment DB: Postgres 16; tests: SQLite.

## Global Constraints

- Backend lives in `~/agent-system-v3/api/`. Paths below are relative to it unless noted.
- **Graph is relational, never vector** (spec invariant). pgvector is Plan 4 only.
- DTOs returned by the API MUST match the frontend `ApiClient`/`dto.ts` shapes from the frontend plan: `ProjectGraph{nodes,edges}`, `GraphNode{id,kind,label,status?,data?}`, `GraphEdge{id,from,to,kind}`, `StepDetail{node,diff,decision?,acceptance[],createdNodeIds,createdEdgeIds}`, status `planning|executing|awaiting_review|done|blocked`, edge kinds `has|subdivides|touches|tested_by|decided|produced`.
- `diff_ingest` MUST be **deterministic & idempotent**: re-applying the same `(step_id, commit_sha, diff)` yields the same nodes/edges, no duplicates.
- Portable SQLAlchemy types only (no `Vector`, no JSONB-only features) so SQLite tests pass.
- Every task ends green (`pytest`) and the API boots (`uvicorn app.main:app`).

---

## File Structure

```
api/
  pyproject.toml
  app/
    main.py                 # FastAPI app + CORS + router include
    db.py                   # engine/session, Base, init_db()
    models.py               # Node, Edge tables + enums
    schemas.py              # Pydantic DTOs mirroring the frontend ApiClient
    graph/
      store.py              # create/get graph, neighbors, owning_path, step_detail
      diff_ingest.py        # parse_diff(); apply_step_diff() (idempotent)
    git/
      repo.py               # commit target repo, diff_of_commit()
    routers/
      graph.py              # GET /graph, /steps/{id}, /owning-path/{nodeId}
  tests/
    conftest.py             # SQLite session fixture
    test_diff_ingest.py
    test_store.py
    test_api.py
web/src/api/http/HttpApiClient.ts   # frontend bridge (implements ApiClient over REST)
```

---

## Task 1: Scaffold the API package + DB session

**Files:**
- Create: `api/pyproject.toml`, `api/app/__init__.py`, `api/app/db.py`, `api/app/main.py`, `api/tests/conftest.py`
- Test: `api/tests/test_health.py`

**Interfaces:**
- Produces: `db.Base`, `db.get_session()`, `db.init_db(engine)`; FastAPI `app` with `GET /health` → `{"status":"ok"}`.

- [ ] **Step 1: `api/pyproject.toml`**

```toml
[project]
name = "control-tower-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115", "uvicorn[standard]>=0.30", "sqlalchemy>=2.0.30",
  "pydantic>=2.8", "unidiff>=0.7.5",
]
[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.27"]
postgres = ["psycopg[binary]>=3.2", "pgvector>=0.3"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]
```

- [ ] **Step 2: `api/app/db.py`**

```python
from __future__ import annotations
import os
from collections.abc import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

class Base(DeclarativeBase): ...

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

def init_db(eng=engine) -> None:
    from . import models  # noqa: F401 (register tables)
    Base.metadata.create_all(eng)

def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: `api/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db

app = FastAPI(title="Control Tower API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup() -> None:
    init_db()

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: `api/tests/conftest.py`** — in-memory SQLite session per test

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base

@pytest.fixture()
def session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    import app.models  # noqa: F401
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Failing test** `api/tests/test_health.py`

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
```

- [ ] **Step 6: Install + run** — `cd api && pip install -e ".[dev]" && pytest tests/test_health.py` → PASS.

- [ ] **Step 7: Commit** — `git add api && git commit -m "feat(api): scaffold FastAPI + SQLAlchemy session"`

---

## Task 2: Graph models (nodes, edges)

**Files:**
- Create: `api/app/models.py`
- Test: `api/tests/test_models.py`

**Interfaces:**
- Produces: `Node(id:str pk, project_id:str, kind:str, label:str, status:str|None, data:dict)`, `Edge(id:str pk, project_id:str, src:str, dst:str, kind:str)`. `id`s are app-assigned strings (e.g. `s4`, `c-gate`).

- [ ] **Step 1: Failing test** `api/tests/test_models.py`

```python
from app.models import Node, Edge

def test_insert_node_and_edge(session):
    session.add(Node(id="t1", project_id="p1", kind="ticket", label="CRUD", status="executing"))
    session.add(Node(id="s1", project_id="p1", kind="step", label="form", status="done"))
    session.add(Edge(id="e1", project_id="p1", src="t1", dst="s1", kind="has"))
    session.commit()
    assert session.get(Node, "t1").label == "CRUD"
    assert session.get(Edge, "e1").kind == "has"
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/models.py`**

```python
from __future__ import annotations
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(20))      # objective|ticket|step|code_region|test|decision
    label: Mapped[str] = mapped_column(String(500))
    status: Mapped[str | None] = mapped_column(String(20), default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class Edge(Base):
    __tablename__ = "edges"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    src: Mapped[str] = mapped_column(String(64), index=True)
    dst: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(20))      # has|subdivides|touches|tested_by|decided|produced
```

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Commit** — `git add api/app/models.py api/tests/test_models.py && git commit -m "feat(api): Node/Edge graph models"`

---

## Task 3: Diff parser (pure, deterministic)

**Files:**
- Create: `api/app/graph/__init__.py`, `api/app/graph/diff_ingest.py`
- Test: `api/tests/test_diff_ingest.py`

**Interfaces:**
- Produces: `@dataclass TouchedFile(path:str, added:int, removed:int)` and `parse_diff(diff_text:str) -> list[TouchedFile]` (one per file in a unified diff; handles add/modify/delete; sorted by path for determinism).

- [ ] **Step 1: Failing test** `api/tests/test_diff_ingest.py`

```python
from app.graph.diff_ingest import parse_diff

DIFF = """diff --git a/src/billing/FeatureGate.tsx b/src/billing/FeatureGate.tsx
new file mode 100644
--- /dev/null
+++ b/src/billing/FeatureGate.tsx
@@ -0,0 +1,2 @@
+export const Gate = () => null;
+// gate
diff --git a/src/todo/model.ts b/src/todo/model.ts
--- a/src/todo/model.ts
+++ b/src/todo/model.ts
@@ -1,1 +1,2 @@
-old
+new
+added
"""

def test_parse_diff_returns_sorted_touched_files():
    files = parse_diff(DIFF)
    assert [f.path for f in files] == ["src/billing/FeatureGate.tsx", "src/todo/model.ts"]
    assert files[0].added == 2 and files[0].removed == 0
    assert files[1].added == 2 and files[1].removed == 1

def test_parse_diff_is_deterministic():
    assert parse_diff(DIFF) == parse_diff(DIFF)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/graph/diff_ingest.py`** (parser part)

```python
from __future__ import annotations
from dataclasses import dataclass
from unidiff import PatchSet

@dataclass(frozen=True)
class TouchedFile:
    path: str
    added: int
    removed: int

def parse_diff(diff_text: str) -> list[TouchedFile]:
    patch = PatchSet(diff_text)
    out: list[TouchedFile] = []
    for f in patch:
        path = f.path  # unidiff strips a/ b/ ; for new files uses target path
        out.append(TouchedFile(path=path, added=f.added, removed=f.removed))
    return sorted(out, key=lambda t: t.path)
```

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Commit** — `git add api/app/graph api/tests/test_diff_ingest.py && git commit -m "feat(api): deterministic unified-diff parser"`

---

## Task 4: Graph store + idempotent diff ingest

**Files:**
- Create: `api/app/graph/store.py`
- Modify: `api/app/graph/diff_ingest.py` (add `apply_step_diff`)
- Test: `api/tests/test_store.py`

**Interfaces:**
- Produces (in `store.py`):
  - `seed_graph(db, project_id, nodes:list[dict], edges:list[dict])`
  - `get_graph(db, project_id) -> dict` → `{"nodes":[...], "edges":[{"id","from","to","kind"}...]}`
  - `neighbors(db, project_id, node_id, direction) -> list[Node]`
  - `owning_path(db, project_id, node_id) -> list[str]` (code_region→step→ticket→objective)
- Produces (in `diff_ingest.py`):
  - `apply_step_diff(db, project_id, step_id, commit_sha, diff_text) -> dict` → upserts `code_region` nodes (id = `cr:` + path), creates `touches` edges (id = `touch:{step_id}:{path}`), idempotent. Returns `{"createdNodeIds":[...], "createdEdgeIds":[...]}`.

- [ ] **Step 1: Failing test** `api/tests/test_store.py`

```python
from app.graph.store import seed_graph, get_graph, owning_path
from app.graph.diff_ingest import apply_step_diff

DIFF = "diff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@ -0,0 +1 @@\n+x\n"

def _seed(db):
    seed_graph(db, "p1",
        nodes=[{"id":"obj","kind":"objective","label":"O"},
               {"id":"t1","kind":"ticket","label":"T","status":"executing"},
               {"id":"s1","kind":"step","label":"S","status":"awaiting_review"}],
        edges=[{"id":"e1","from":"obj","to":"t1","kind":"has"},
               {"id":"e2","from":"t1","to":"s1","kind":"has"}])

def test_get_graph_roundtrip(session):
    _seed(session)
    g = get_graph(session, "p1")
    assert {n["id"] for n in g["nodes"]} == {"obj","t1","s1"}
    assert {e["from"] for e in g["edges"]} == {"obj","t1"}

def test_apply_step_diff_is_idempotent(session):
    _seed(session)
    r1 = apply_step_diff(session, "p1", "s1", "sha1", DIFF)
    r2 = apply_step_diff(session, "p1", "s1", "sha1", DIFF)
    g = get_graph(session, "p1")
    assert sum(n["kind"] == "code_region" for n in g["nodes"]) == 1   # no duplicate
    assert sum(e["kind"] == "touches" for e in g["edges"]) == 1
    assert r1 == r2

def test_owning_path(session):
    _seed(session)
    apply_step_diff(session, "p1", "s1", "sha1", DIFF)
    assert owning_path(session, "p1", "cr:src/x.ts") == ["cr:src/x.ts","s1","t1","obj"]
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/graph/store.py`**

```python
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Node, Edge

def seed_graph(db: Session, project_id: str, nodes: list[dict], edges: list[dict]) -> None:
    for n in nodes:
        db.add(Node(id=n["id"], project_id=project_id, kind=n["kind"],
                    label=n["label"], status=n.get("status"), data=n.get("data", {})))
    for e in edges:
        db.add(Edge(id=e["id"], project_id=project_id, src=e["from"], dst=e["to"], kind=e["kind"]))
    db.commit()

def get_graph(db: Session, project_id: str) -> dict:
    nodes = db.scalars(select(Node).where(Node.project_id == project_id)).all()
    edges = db.scalars(select(Edge).where(Edge.project_id == project_id)).all()
    return {
        "nodes": [{"id": n.id, "kind": n.kind, "label": n.label,
                   "status": n.status, "data": n.data} for n in nodes],
        "edges": [{"id": e.id, "from": e.src, "to": e.dst, "kind": e.kind} for e in edges],
    }

def neighbors(db: Session, project_id: str, node_id: str, direction: str) -> list[Node]:
    ids: set[str] = set()
    edges = db.scalars(select(Edge).where(Edge.project_id == project_id)).all()
    for e in edges:
        if direction in ("out", "both") and e.src == node_id:
            ids.add(e.dst)
        if direction in ("in", "both") and e.dst == node_id:
            ids.add(e.src)
    return [db.get(Node, i) for i in ids if db.get(Node, i)]

def owning_path(db: Session, project_id: str, node_id: str) -> list[str]:
    order = ["code_region", "step", "ticket", "objective"]
    path = [node_id]
    cur = db.get(Node, node_id)
    if cur is None:
        return path
    idx = order.index(cur.kind) if cur.kind in order else 0
    for i in range(idx, len(order) - 1):
        parents = [p for p in neighbors(db, project_id, path[-1], "in") if p.kind == order[i + 1]]
        if not parents:
            break
        path.append(parents[0].id)
    return path
```

- [ ] **Step 4: Implement `apply_step_diff` in `diff_ingest.py`**

```python
# append to diff_ingest.py
from sqlalchemy.orm import Session
from ..models import Node, Edge

def apply_step_diff(db: Session, project_id: str, step_id: str, commit_sha: str, diff_text: str) -> dict:
    created_nodes, created_edges = [], []
    for tf in parse_diff(diff_text):
        node_id = f"cr:{tf.path}"
        if db.get(Node, node_id) is None:
            db.add(Node(id=node_id, project_id=project_id, kind="code_region",
                        label=tf.path, data={"commit": commit_sha}))
            created_nodes.append(node_id)
        edge_id = f"touch:{step_id}:{tf.path}"
        if db.get(Edge, edge_id) is None:
            db.add(Edge(id=edge_id, project_id=project_id, src=step_id, dst=node_id, kind="touches"))
            created_edges.append(edge_id)
    db.commit()
    return {"createdNodeIds": created_nodes, "createdEdgeIds": created_edges}
```

- [ ] **Step 5: Run, expect PASS** (idempotency + owning_path green).

- [ ] **Step 6: Commit** — `git add api/app/graph api/tests/test_store.py && git commit -m "feat(api): graph store + idempotent diff->graph ingest"`

---

## Task 5: Git repo ops (target project)

**Files:**
- Create: `api/app/git/__init__.py`, `api/app/git/repo.py`
- Test: `api/tests/test_repo.py`

**Interfaces:**
- Produces: `commit_all(repo_dir, message) -> str` (returns sha), `diff_of_commit(repo_dir, sha) -> str` (unified diff of that commit vs its parent, or vs empty tree for the first commit).

- [ ] **Step 1: Failing test** `api/tests/test_repo.py`

```python
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
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/git/repo.py`**

```python
from __future__ import annotations
import subprocess

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's empty tree

def _git(repo_dir: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo_dir, check=True,
                          capture_output=True, text=True).stdout

def commit_all(repo_dir: str, message: str) -> str:
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-q", "-m", message)
    return _git(repo_dir, "rev-parse", "HEAD").strip()

def diff_of_commit(repo_dir: str, sha: str) -> str:
    parents = _git(repo_dir, "rev-list", "--parents", "-n", "1", sha).split()
    base = parents[1] if len(parents) > 1 else EMPTY_TREE
    return _git(repo_dir, "diff", base, sha)
```

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Commit** — `git add api/app/git api/tests/test_repo.py && git commit -m "feat(api): target-repo git ops (commit, diff-of-commit)"`

---

## Task 6: Schemas + graph routers (frontend contract)

**Files:**
- Create: `api/app/schemas.py`, `api/app/routers/__init__.py`, `api/app/routers/graph.py`
- Modify: `api/app/main.py` (include router), `api/app/graph/store.py` (add `step_detail`)
- Test: `api/tests/test_api.py`

**Interfaces:**
- Produces endpoints: `GET /projects/{pid}/graph` → ProjectGraph; `GET /projects/{pid}/steps/{sid}` → StepDetail; `GET /projects/{pid}/owning-path/{nid}` → `{"path":[...]}`. Pydantic models mirror the frontend DTOs.
- `store.step_detail(db, pid, step_id) -> dict` → `{node, diff, decision?, acceptance, createdNodeIds, createdEdgeIds}` (diff read from `code_region.data["commit"]` via `git.repo` is wired in Plan 3; here return touched code-region paths as `diff` stubs `{path, patch:""}` and decision from a `decided` neighbor).

- [ ] **Step 1: Failing test** `api/tests/test_api.py`

```python
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal, init_db
from app.graph.store import seed_graph

def setup_module():
    init_db()
    db = SessionLocal()
    seed_graph(db, "p1",
        nodes=[{"id":"obj","kind":"objective","label":"O"},
               {"id":"t1","kind":"ticket","label":"T","status":"executing"},
               {"id":"s1","kind":"step","label":"S","status":"awaiting_review"},
               {"id":"cr:x","kind":"code_region","label":"src/x.ts"},
               {"id":"d1","kind":"decision","label":"플래그로"}],
        edges=[{"id":"e1","from":"obj","to":"t1","kind":"has"},
               {"id":"e2","from":"t1","to":"s1","kind":"has"},
               {"id":"e3","from":"s1","to":"cr:x","kind":"touches"},
               {"id":"e4","from":"s1","to":"d1","kind":"decided"}])
    db.close()

def test_graph_endpoint():
    c = TestClient(app)
    g = c.get("/projects/p1/graph").json()
    assert {n["id"] for n in g["nodes"]} >= {"obj","t1","s1"}
    assert g["edges"][0].keys() >= {"id","from","to","kind"}

def test_step_detail_and_owning_path():
    c = TestClient(app)
    sd = c.get("/projects/p1/steps/s1").json()
    assert sd["decision"] == "플래그로"
    assert any(b["path"] == "src/x.ts" for b in sd["diff"])
    op = c.get("/projects/p1/owning-path/cr:x").json()
    assert op["path"] == ["cr:x","s1","t1","obj"]
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/schemas.py`**

```python
from __future__ import annotations
from pydantic import BaseModel, Field

class NodeOut(BaseModel):
    id: str; kind: str; label: str
    status: str | None = None; data: dict = {}

class EdgeOut(BaseModel):
    id: str
    src: str = Field(serialization_alias="from")
    to: str
    kind: str
    model_config = {"populate_by_name": True}

class GraphOut(BaseModel):
    nodes: list[NodeOut]; edges: list[EdgeOut]

class DiffBlob(BaseModel):
    path: str; patch: str = ""

class Acceptance(BaseModel):
    text: str; met: bool = False

class StepDetailOut(BaseModel):
    node: NodeOut
    diff: list[DiffBlob] = []
    decision: str | None = None
    acceptance: list[Acceptance] = []
    createdNodeIds: list[str] = []
    createdEdgeIds: list[str] = []
```

- [ ] **Step 4: Add `step_detail` to `store.py`**

```python
def step_detail(db: Session, project_id: str, step_id: str) -> dict:
    node = db.get(Node, step_id)
    touched = [n for n in neighbors(db, project_id, step_id, "out") if n.kind == "code_region"]
    decision = next((n.label for n in neighbors(db, project_id, step_id, "out") if n.kind == "decision"), None)
    return {
        "node": {"id": node.id, "kind": node.kind, "label": node.label,
                 "status": node.status, "data": node.data},
        "diff": [{"path": c.label, "patch": ""} for c in touched],
        "decision": decision,
        "acceptance": [{"text": f"{node.label} 확인", "met": node.status == "done"}],
        "createdNodeIds": [c.id for c in touched],
        "createdEdgeIds": [e.id for e in db.scalars(
            select(Edge).where(Edge.project_id == project_id, Edge.src == step_id)).all()],
    }
```

- [ ] **Step 5: Implement `api/app/routers/graph.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_session
from ..graph import store
from ..schemas import GraphOut, StepDetailOut

router = APIRouter(prefix="/projects/{pid}", tags=["graph"])

@router.get("/graph", response_model=GraphOut)
def get_graph(pid: str, db: Session = Depends(get_session)):
    g = store.get_graph(db, pid)
    return {"nodes": g["nodes"],
            "edges": [{"id": e["id"], "from": e["from"], "to": e["to"], "kind": e["kind"]} for e in g["edges"]]}

@router.get("/steps/{sid}", response_model=StepDetailOut)
def step_detail(pid: str, sid: str, db: Session = Depends(get_session)):
    return store.step_detail(db, pid, sid)

@router.get("/owning-path/{nid}")
def owning_path(pid: str, nid: str, db: Session = Depends(get_session)):
    return {"path": store.owning_path(db, pid, nid)}
```
Wire in `main.py`: `from .routers import graph as graph_router` then `app.include_router(graph_router.router)`.

- [ ] **Step 6: Run, expect PASS.** Boot check: `uvicorn app.main:app` → `GET /docs` lists the endpoints.

- [ ] **Step 7: Commit** — `git add api && git commit -m "feat(api): graph/step/owning-path endpoints (frontend contract)"`

---

## Task 7: Frontend HttpApiClient bridge

**Files:**
- Create: `web/src/api/http/HttpApiClient.ts`
- Modify: `web/src/store/useStore.ts` (select client by `import.meta.env.VITE_API_BASE`)
- Test: `web/src/api/http/HttpApiClient.test.ts`

**Interfaces:**
- Produces: `class HttpApiClient implements ApiClient` calling the Task 6 endpoints; `getGraph`/`getStepDetail`/`owningPath` map responses to the frontend types. `subscribe` uses light polling (e.g. `setInterval(cb, 1500)`) until SSE exists (Plan 3). `proposePlan`/`approvePlan`/`reviewStep` call POST endpoints added in Plan 3 — for now throw `NotImplemented` (frontend still uses Mock for those until Plan 3).

- [ ] **Step 1: Failing test** (mock `fetch`)

```ts
import { HttpApiClient } from './HttpApiClient';

const graph = { nodes: [{ id: 's4', kind: 'step', label: 'gate', status: 'awaiting_review' }], edges: [] };

test('getGraph maps the REST response', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(graph))));
  const api = new HttpApiClient('http://api', 'p1');
  const g = await api.getGraph();
  expect(g.nodes[0].status).toBe('awaiting_review');
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `HttpApiClient.ts`**

```ts
import type { ApiClient } from '../ApiClient';
import type { ProjectGraph } from '../../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal } from '../dto';

export class HttpApiClient implements ApiClient {
  constructor(private base: string, private pid: string) {}
  private async j<T>(path: string): Promise<T> {
    const r = await fetch(`${this.base}/projects/${this.pid}${path}`);
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json() as Promise<T>;
  }
  getGraph(): Promise<ProjectGraph> { return this.j('/graph'); }
  getStepDetail(id: string): Promise<StepDetail> { return this.j(`/steps/${id}`); }
  async owningPath(id: string): Promise<string[]> {
    return (await this.j<{ path: string[] }>(`/owning-path/${id}`)).path;
  }
  proposePlan(_g: string): Promise<PlanProposal> { throw new Error('NotImplemented until Plan 3'); }
  approvePlan(_p: PlanProposal): Promise<void> { throw new Error('NotImplemented until Plan 3'); }
  reviewStep(_id: string, _a: ReviewAction): Promise<void> { throw new Error('NotImplemented until Plan 3'); }
  subscribe(cb: () => void): () => void {
    const t = setInterval(cb, 1500);
    return () => clearInterval(t);
  }
}
```

- [ ] **Step 4: Wire selection in `useStore.ts`** — `const api = import.meta.env.VITE_API_BASE ? new HttpApiClient(import.meta.env.VITE_API_BASE, 'p1') : new MockApiClient();`

- [ ] **Step 5: Run web tests, expect PASS.** Manual: run api + `VITE_API_BASE=http://localhost:8000 npm run dev` → map loads from backend.

- [ ] **Step 6: Commit** — `git add web/src/api web/src/store && git commit -m "feat(web): HttpApiClient bridge to backend graph endpoints"`

---

## Self-Review (done at write time)

- **Spec coverage:** §6 graph (T2), diff→graph idempotent (T3,T4), bug-trace owning-path query (T4,T6), git source-of-truth (T5), frontend contract endpoints + bridge (T6,T7). LangGraph/Planner/Executor (Plan 3), RAG (Plan 4) out of scope.
- **Contract match:** endpoints return exactly `{nodes,edges:[{id,from,to,kind}]}` and `StepDetail`/owning-path shapes the frontend `ApiClient` consumes. The `EdgeOut.from` alias handles Python's reserved word. ✔
- **Idempotency:** `apply_step_diff` keys nodes by `cr:{path}` and edges by `touch:{step}:{path}` → re-apply is a no-op (T4 asserts). ✔
- **Portability:** JSON + String columns only → SQLite tests pass; Postgres is the deploy target (pgvector deferred to Plan 4). ✔
- **Type consistency:** `get_graph`/`step_detail`/`owning_path` names used identically across store, routers, tests, and the HttpApiClient. ✔

## Notes for later plans

- `step_detail.diff` returns `patch:""` stubs here; Plan 3 fills real patches from `git.repo.diff_of_commit` keyed by the step's commit sha.
- POST endpoints (`proposePlan`/`approvePlan`/`reviewStep`) and SSE live updates are Plan 3 (they drive the LangGraph lifecycle).
