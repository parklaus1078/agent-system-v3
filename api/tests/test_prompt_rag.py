from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore
from app.services.prompt_build import step_rag_context
from app.schemas_plan import StepSpec


def test_step_rag_context_pulls_relevant_decision():
    m = MemoryStore(DeterministicEmbeddings())
    m.index_text("Gate features with flags, not subscription-tier branching.", {"node_id": "d1"})
    ctx = step_rag_context(
        m, "구독 티어 할일앱", StepSpec(label="게이트", intent="feature flag gate", acceptance="a")
    )
    assert "flags" in ctx


def test_step_rag_context_is_empty_without_memory():
    assert step_rag_context(None, "obj", StepSpec(label="x", intent="i", acceptance="a")) == ""
