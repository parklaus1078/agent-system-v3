# RAG Memory (LangChain + pgvector) + Wiki Promotion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use Karpathy-skill to think about how to write the actual codes.

**Goal:** Add the semantic memory layer with **LangChain** — `Embeddings` + `PGVector` + `TextSplitter` + `retriever` — indexing `Decision` text so the Planner/Executor get a relevant **context packet**, plus **cross-project promotion**: when a project completes, distill its `Decision` nodes into the personal `~/llm_wiki` and index them so future projects recall them.

**Architecture:** A `MemoryStore` wraps a LangChain `Embeddings` model + a `VectorStore`. Production uses `HuggingFaceEmbeddings` (local sentence-transformers — offline, free) + `langchain-postgres` `PGVector`. Tests use a `DeterministicEmbeddings` (hash-based, no download) + an in-memory store behind the same interface, so they run with zero network and no Postgres. Indexing splits text with a `TextSplitter`. Retrieval returns a context packet injected via Plan 3's `build_step_prompt(rag_context=...)`. **The map (nodes/edges) stays relational — only Decision *text* is embedded** (spec invariant).

**Tech Stack:** Python 3.12, `langchain-core` (`Embeddings`, `Document`), `langchain-text-splitters` (`RecursiveCharacterTextSplitter`), `langchain-postgres` (`PGVector`), `langchain-huggingface` (`HuggingFaceEmbeddings`, production only). Builds on Plan 2 (graph store) + Plan 3 (prompt builder).

## Global Constraints

- Builds on Plan 2 (`api/` graph store, `Node`) and Plan 3 (`build_step_prompt`, `on_step_committed` decision capture).
- **RAG embeds text only (Decisions, promoted wiki pages) — never the map.** Map traversal stays relational (spec invariant).
- **Tests run offline:** use `DeterministicEmbeddings` + in-memory `VectorStore` — never download a model or require Postgres in unit tests. `HuggingFaceEmbeddings`/`PGVector` are lazy-imported and used only in real mode.
- Personal wiki root from env `ASV3_LLM_WIKI_ROOT` (default `/home/kay/llm_wiki`); cross-project promotions go under `kay_second_brain/wiki/decisions/` (the existing convention).
- Every task ends green (`pytest`) and the API boots.

---

## File Structure

```
api/app/
  services/
    embeddings.py        # Embeddings protocol: DeterministicEmbeddings (test) + factory
    memory.py            # MemoryStore: index_decision / retrieve / context_packet
    promotion.py         # on project completion: Decision nodes -> ~/llm_wiki + index
  routers/
    memory.py            # GET /memory/search ; POST /memory/reindex
api/tests/
  test_embeddings.py  test_memory.py  test_promotion.py  test_memory_api.py
```

---

## Task 1: Embeddings (deterministic test + real factory)

**Files:** Create `api/app/services/embeddings.py`; Test `api/tests/test_embeddings.py`

**Interfaces:**
- Produces: `DeterministicEmbeddings(dim=256)` implementing LangChain's `Embeddings` (`embed_documents(list[str])->list[list[float]]`, `embed_query(str)->list[float]`) via a stable hash bag-of-words (unit-normalized) — no model download. `make_embeddings()` returns `HuggingFaceEmbeddings` in real mode, else `DeterministicEmbeddings`.

- [ ] **Step 1: Failing test** `api/tests/test_embeddings.py`

```python
from app.services.embeddings import DeterministicEmbeddings

def test_deterministic_and_similar_texts_score_higher():
    e = DeterministicEmbeddings()
    a = e.embed_query("feature gating via flags")
    b = e.embed_query("feature gating via flags")
    assert a == b  # deterministic
    def dot(x, y): return sum(i * j for i, j in zip(x, y))
    near = dot(a, e.embed_query("gating flags feature"))
    far = dot(a, e.embed_query("database migration tooling"))
    assert near > far
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/embeddings.py`**

```python
from __future__ import annotations
import hashlib, math, os, re
from langchain_core.embeddings import Embeddings

class DeterministicEmbeddings(Embeddings):
    """Offline, hash bag-of-words — for tests and a zero-dep default. Unit-normalized."""
    def __init__(self, dim: int = 256):
        self.dim = dim
    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 (non-crypto)
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]
    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

def make_embeddings() -> Embeddings:
    if os.getenv("ASV3_EMBEDDINGS") == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings  # lazy: heavy dep
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return DeterministicEmbeddings()
```

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services/embeddings.py api/tests/test_embeddings.py && git commit -m "feat(api): LangChain Embeddings (deterministic test default + HF factory)"`

---

## Task 2: MemoryStore (index + retrieve + context packet)

**Files:** Create `api/app/services/memory.py`; Test `api/tests/test_memory.py`

**Interfaces:**
- Produces: `MemoryStore(embeddings, store=None)`:
  - `index_text(text:str, metadata:dict) -> int` (splits via `RecursiveCharacterTextSplitter`, adds `Document`s; returns chunk count)
  - `index_decision(db, project_id, decision_node_id)` (reads a `Decision` node's label, indexes it with `{project_id, node_id, kind:"decision"}`)
  - `retrieve(query:str, k:int=4) -> list[dict]` (`{text, metadata, score}`)
  - `context_packet(query:str, k:int=4) -> str` (formatted block for the prompt)
- Default `store` = an in-memory `VectorStore` so tests need no Postgres; production passes a `PGVector` instance.

- [ ] **Step 1: Failing test** `api/tests/test_memory.py`

```python
from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore

def test_index_and_retrieve_packet():
    m = MemoryStore(DeterministicEmbeddings())
    m.index_text("Gate features with flags, not by branching on subscription tier.",
                 {"node_id": "d1", "kind": "decision"})
    m.index_text("Use Alembic for schema migrations.", {"node_id": "d2", "kind": "decision"})
    hits = m.retrieve("feature flag gating", k=1)
    assert hits and hits[0]["metadata"]["node_id"] == "d1"
    packet = m.context_packet("feature flag gating", k=1)
    assert "flags" in packet
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/memory.py`**

```python
from __future__ import annotations
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session
from ..models import Node

class MemoryStore:
    def __init__(self, embeddings, store=None):
        self.embeddings = embeddings
        self.store = store or InMemoryVectorStore(embeddings)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=80)

    def index_text(self, text: str, metadata: dict) -> int:
        docs = [Document(page_content=c, metadata=metadata) for c in self.splitter.split_text(text)]
        if docs:
            self.store.add_documents(docs)
        return len(docs)

    def index_decision(self, db: Session, project_id: str, node_id: str) -> int:
        node = db.get(Node, node_id)
        if node is None or node.kind != "decision":
            return 0
        return self.index_text(node.label, {"project_id": project_id, "node_id": node_id, "kind": "decision"})

    def retrieve(self, query: str, k: int = 4) -> list[dict]:
        results = self.store.similarity_search_with_score(query, k=k)
        return [{"text": d.page_content, "metadata": d.metadata, "score": float(s)} for d, s in results]

    def context_packet(self, query: str, k: int = 4) -> str:
        hits = self.retrieve(query, k)
        if not hits:
            return ""
        lines = ["## Relevant prior knowledge (RAG over LLM Wiki)"]
        for h in hits:
            tag = h["metadata"].get("wiki_path") or h["metadata"].get("node_id") or ""
            lines.append(f"- ({tag}) {h['text'][:280]}")
        return "\n".join(lines)
```
Production wiring: `from langchain_postgres import PGVector; store = PGVector(embeddings=emb, collection_name="asv3_memory", connection=DATABASE_URL, use_jsonb=True)` then `MemoryStore(emb, store)`.

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services/memory.py api/tests/test_memory.py && git commit -m "feat(api): MemoryStore (splitter + vector store + context packet)"`

---

## Task 3: Inject RAG into the step prompt

**Files:** Modify `api/app/services/prompt_build.py` (accept an optional `memory`), `api/app/routers/lifecycle.py` (pass the shared `MemoryStore`); Test `api/tests/test_prompt_rag.py`

**Interfaces:**
- `build_step_prompt(db, project_id, ticket_id, step, rag_context="")` is unchanged (Plan 3 already takes `rag_context`). Add a helper `step_rag_context(memory, objective, step) -> str = memory.context_packet(f"{objective} {step.intent}")`. The lifecycle router computes it before `build_step_prompt` and passes it in.

- [ ] **Step 1: Failing test** `api/tests/test_prompt_rag.py`

```python
from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore
from app.services.prompt_build import step_rag_context
from app.schemas_plan import StepSpec

def test_step_rag_context_pulls_relevant_decision():
    m = MemoryStore(DeterministicEmbeddings())
    m.index_text("Gate features with flags, not subscription-tier branching.", {"node_id": "d1"})
    ctx = step_rag_context(m, "구독 티어 할일앱", StepSpec(label="게이트", intent="feature flag gate", acceptance="a"))
    assert "flags" in ctx
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Add to `prompt_build.py`**

```python
def step_rag_context(memory, objective: str, step) -> str:
    if memory is None:
        return ""
    return memory.context_packet(f"{objective} {step.intent}")
```
Then in `routers/lifecycle.py`, build a module-level `MEMORY = MemoryStore(make_embeddings(), <PGVector in real mode>)`, and in the graph's `build_prompt` callback do `rag = step_rag_context(MEMORY, state["objective"], StepSpec(**state["steps"][state["current"]]))` then `build_step_prompt(db, pid, tid, step, rag_context=rag)`.

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services api/app/routers && git commit -m "feat(api): inject RAG context packet into step prompts"`

---

## Task 4: Cross-project promotion to ~/llm_wiki

**Files:** Create `api/app/services/promotion.py`; Test `api/tests/test_promotion.py`

**Interfaces:**
- Produces: `promote_project(db, project_id, memory, wiki_root=None) -> list[str]` — for each `Decision` node in the project, write a markdown page under `<wiki_root>/kay_second_brain/wiki/decisions/asv3-<project>-<node>.md` (frontmatter + the decision text), index it into `memory` with `{wiki_path, kind:"decision", project_id}`, and return the written paths. Idempotent (same node → same file path, overwrite).

- [ ] **Step 1: Failing test** `api/tests/test_promotion.py`

```python
from pathlib import Path
from app.graph.store import seed_graph
from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore
from app.services.promotion import promote_project

def test_promote_writes_wiki_and_indexes(session, tmp_path):
    seed_graph(session, "p1",
        nodes=[{"id":"obj","kind":"objective","label":"Todo"},
               {"id":"d1","kind":"decision","label":"Gate features with flags, not tier branching."}],
        edges=[{"id":"e1","from":"obj","to":"d1","kind":"decided"}])
    mem = MemoryStore(DeterministicEmbeddings())
    paths = promote_project(session, "p1", mem, wiki_root=str(tmp_path))
    assert len(paths) == 1 and Path(paths[0]).exists()
    assert "flags" in Path(paths[0]).read_text()
    # now retrievable across projects via the personal wiki layer
    assert mem.retrieve("feature flags gating", k=1)[0]["metadata"]["kind"] == "decision"
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/promotion.py`**

```python
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
        memory.index_text(node.label, {"wiki_path": str(path), "kind": "decision", "project_id": project_id})
        written.append(str(path))
    return written
```

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services/promotion.py api/tests/test_promotion.py && git commit -m "feat(api): promote project Decisions to ~/llm_wiki + index (cross-project recall)"`

---

## Task 5: Memory API

**Files:** Create `api/app/routers/memory.py`; Modify `api/app/main.py` (include router); Test `api/tests/test_memory_api.py`

**Interfaces:**
- `GET /memory/search?q=&k=` → `[{text, metadata, score}]` (over the shared `MemoryStore`).
- `POST /memory/reindex/{project_id}` → re-indexes all of a project's `Decision` nodes; returns `{indexed}`.
- Both use the same module-level `MemoryStore` the lifecycle router uses (single instance — import it).

- [ ] **Step 1: Failing test** `api/tests/test_memory_api.py`

```python
from fastapi.testclient import TestClient
from app.main import app
from app.routers.memory import MEMORY

def test_search_endpoint_returns_indexed_text():
    MEMORY.index_text("Gate features with flags.", {"node_id": "d1", "kind": "decision"})
    hits = TestClient(app).get("/memory/search", params={"q": "feature flags", "k": 1}).json()
    assert hits and "flags" in hits[0]["text"]
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/routers/memory.py`** — define the shared `MEMORY = MemoryStore(make_embeddings(), <PGVector in real mode>)` here (the lifecycle router imports it from this module to avoid two instances). Endpoints call `MEMORY.retrieve` and `memory.index_decision` over each project Decision node. Wire into `main.py`.

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_session
from ..models import Node
from ..services.embeddings import make_embeddings
from ..services.memory import MemoryStore

MEMORY = MemoryStore(make_embeddings())  # real mode swaps in PGVector via make store helper
router = APIRouter(tags=["memory"])

@router.get("/memory/search")
def search(q: str, k: int = 4):
    return MEMORY.retrieve(q, k)

@router.post("/memory/reindex/{project_id}")
def reindex(project_id: str, db: Session = Depends(get_session)):
    nodes = db.scalars(select(Node).where(Node.project_id == project_id, Node.kind == "decision")).all()
    n = sum(MEMORY.index_decision(db, project_id, node.id) for node in nodes)
    return {"indexed": n}
```

- [ ] **Step 4: Run, expect PASS.** Boot check: `/docs` lists the memory endpoints.

- [ ] **Step 5: Commit** — `git add api/app && git commit -m "feat(api): memory search/reindex endpoints"`

---

## Self-Review (done at write time)

- **Spec coverage:** §6 pgvector RAG pipeline = LangChain Embeddings + splitter + VectorStore (T1,T2); context packet injected into Planner/Executor prompts (T3); 3-layer memory promotion to `~/llm_wiki` for cross-project recall (T4); memory API (T5). Map stays relational — only Decision text embedded (invariant honored).
- **Offline tests:** `DeterministicEmbeddings` + `InMemoryVectorStore` everywhere; `HuggingFaceEmbeddings`/`PGVector` lazy, real-mode only. ✔
- **LangChain load-bearing:** `Embeddings`, `Document`, `RecursiveCharacterTextSplitter`, `VectorStore`/`PGVector`, `similarity_search_with_score` — the RAG pipeline IS LangChain components (spec §5.1). ✔
- **Type/name consistency:** `MemoryStore` API (`index_text`/`index_decision`/`retrieve`/`context_packet`) used identically across memory, prompt_build, promotion, and routers; single shared `MEMORY` instance. ✔

## Notes / wiring back to Plan 3

- Plan 3's lifecycle router imports `MEMORY` from `routers/memory.py` and passes `step_rag_context(MEMORY, ...)` into `build_step_prompt`.
- Call `promote_project(db, project_id, MEMORY)` when a project's tickets all reach Completed (hook this into the ticket-completion path).
- Real embeddings model + PGVector collection are the production swaps (env `ASV3_EMBEDDINGS=huggingface`, `DATABASE_URL`); the `Embeddings`/`VectorStore` interfaces mean no call-site changes.
