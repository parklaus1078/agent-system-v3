from app.graph.store import seed_graph
from app.services.prompt_build import build_step_prompt
from app.schemas_plan import StepSpec


def test_prompt_is_scoped_to_ticket_neighbors(session):
    seed_graph(
        session,
        "p1",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "Todo 앱"},
            {"id": "t1", "kind": "ticket", "label": "게이팅", "status": "executing"},
            {"id": "cr:x", "kind": "code_region", "label": "src/billing/flags.ts"},
            {"id": "d1", "kind": "decision", "label": "플래그로 분기"},
        ],
        edges=[
            {"id": "e1", "from": "obj", "to": "t1", "kind": "has"},
            {"id": "e2", "from": "t1", "to": "cr:x", "kind": "touches"},
            {"id": "e3", "from": "t1", "to": "d1", "kind": "decided"},
        ],
    )
    prompt = build_step_prompt(session, "p1", "t1", StepSpec(label="s", intent="i", acceptance="a"))
    assert "Todo 앱" in prompt and "src/billing/flags.ts" in prompt and "플래그로 분기" in prompt
    assert "전체 레포" not in prompt  # scoped, not whole-repo
