from app.graph.store import seed_graph
from app.services.prompt_build import build_step_prompt
from app.schemas_plan import StepSpec


def test_prompt_is_scoped_to_what_the_ticket_steps_own(session):
    # Realistic graph shape: touches/decided edges originate from STEPS, not the
    # ticket (this is how apply_step_diff + on_step_committed build the graph).
    seed_graph(
        session,
        "p1",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "Todo 앱"},
            {"id": "t1", "kind": "ticket", "label": "게이팅", "status": "executing"},
            {"id": "t1-s1", "kind": "step", "label": "스펙", "status": "done"},
            {"id": "cr:x", "kind": "code_region", "label": "src/billing/flags.ts"},
            {"id": "d1", "kind": "decision", "label": "플래그로 분기"},
        ],
        edges=[
            {"id": "e1", "from": "obj", "to": "t1", "kind": "has"},
            {"id": "e2", "from": "t1", "to": "t1-s1", "kind": "has"},
            {"id": "e3", "from": "t1-s1", "to": "cr:x", "kind": "touches"},
            {"id": "e4", "from": "t1-s1", "to": "d1", "kind": "decided"},
        ],
    )
    prompt = build_step_prompt(session, "p1", "t1", StepSpec(label="s", intent="i", acceptance="a"))
    assert "Todo 앱" in prompt and "src/billing/flags.ts" in prompt and "플래그로 분기" in prompt
    assert "전체 레포" not in prompt  # scoped, not whole-repo
