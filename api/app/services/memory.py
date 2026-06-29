from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from ..models import Node


class MemoryStore:
    """Semantic memory: embed Decision/wiki TEXT (never the map) and retrieve a context
    packet for the Planner/Executor. Tests use an in-memory store + DeterministicEmbeddings;
    production passes a PGVector store behind the same VectorStore interface."""

    def __init__(self, embeddings, store=None):
        self.embeddings = embeddings
        self.store = store or InMemoryVectorStore(embeddings)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=80)

    def index_text(self, text: str, metadata: dict) -> int:
        docs = [
            Document(page_content=c, metadata=metadata)
            for c in self.splitter.split_text(text or "")
        ]
        if docs:
            self.store.add_documents(docs)
        return len(docs)

    def index_decision(self, db: Session, project_id: str, node_id: str) -> int:
        node = db.get(Node, node_id)
        if node is None or node.kind != "decision":
            return 0
        return self.index_text(
            node.label, {"project_id": project_id, "node_id": node_id, "kind": "decision"}
        )

    def retrieve(self, query: str, k: int = 4) -> list[dict]:
        results = self.store.similarity_search_with_score(query, k=k)
        return [
            {"text": d.page_content, "metadata": d.metadata, "score": float(s)}
            for d, s in results
        ]

    def context_packet(self, query: str, k: int = 4) -> str:
        hits = self.retrieve(query, k)
        if not hits:
            return ""
        lines = ["## Relevant prior knowledge (RAG over LLM Wiki)"]
        for h in hits:
            tag = h["metadata"].get("wiki_path") or h["metadata"].get("node_id") or ""
            lines.append(f"- ({tag}) {h['text'][:280]}")
        return "\n".join(lines)
